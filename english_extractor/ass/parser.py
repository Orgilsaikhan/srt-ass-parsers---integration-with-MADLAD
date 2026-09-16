"""Reader for .ass (Advanced SubStation Alpha) files.

Design notes
------------
* Every section keeps its raw lines verbatim in ``Section.lines``.  For the
  [Events] section, each event line is replaced by :data:`EVENT_PLACEHOLDER`
  so the writer can re-emit events (from the structured ``Event`` objects) in
  their original position relative to Format/comment/blank lines.
* The file is split on the detected newline style.  The final element of the
  split is kept as a (possibly empty) line, which is how "file ends with a
  newline" vs "missing final newline" round-trips: the writer simply joins all
  lines with the newline and adds nothing.
* Lines that appear before the first section header are stored in a
  :class:`Section` whose ``name`` is ``""`` (the writer emits no header for it).
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from .models import DEFAULT_EVENT_FORMAT, AssFile, Event, Section

#: Token stored in ``Section.lines`` of [Events] where an event line was.
EVENT_PLACEHOLDER = "\x00EVENT\x00"

#: Line keys in [Events] that are parsed into :class:`Event` objects.
EVENT_KINDS = frozenset({"Dialogue", "Comment", "Picture", "Sound", "Movie", "Command"})

# Map from Format column name (lower-cased) to Event attribute.
_COLUMN_TO_ATTR = {
    "layer": "layer",
    "start": "start",
    "end": "end",
    "style": "style",
    "name": "name",
    "marginl": "margin_l",
    "marginr": "margin_r",
    "marginv": "margin_v",
    "effect": "effect",
    "text": "text",
}

_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"
_UTF8_BOM = b"\xef\xbb\xbf"


def detect_encoding(data: bytes) -> tuple[str, bool]:
    """Return ``(codec_name, has_bom)`` for raw file bytes.

    Tries BOM sniffing first, then strict UTF-8, then cp1251 (never fails with
    errors="replace" downstream).
    """
    if data.startswith(_UTF8_BOM):
        return "utf-8", True
    if data.startswith(_UTF16_LE_BOM):
        return "utf-16-le", True
    if data.startswith(_UTF16_BE_BOM):
        return "utf-16-be", True
    try:
        data.decode("utf-8")
        return "utf-8", False
    except UnicodeDecodeError:
        pass
    try:
        data.decode("cp1251")
        return "cp1251", False
    except UnicodeDecodeError:
        return "latin-1", False


def decode_bytes(data: bytes) -> tuple[str, str, bool]:
    """Decode raw bytes -> ``(text_without_bom, codec_name, has_bom)``."""
    codec, bom = detect_encoding(data)
    if bom:
        data = data[len(_UTF8_BOM) if codec == "utf-8" else 2:]
    return data.decode(codec, errors="replace"), codec, bom


def detect_newline(text: str) -> str:
    """Return ``"\\r\\n"`` if the text uses CRLF anywhere, else ``"\\n"``."""
    return "\r\n" if "\r\n" in text else "\n"


def _split_key_value(line: str) -> tuple[str, str] | None:
    """Split ``"Key: value"`` into ``("Key", "value")``; None if no colon."""
    colon = line.find(":")
    if colon < 0:
        return None
    return line[:colon].strip(), line[colon + 1:].lstrip()


def parse_format_line(value: str) -> list[str]:
    """``"Layer, Start, End"`` -> ``["Layer", "Start", "End"]``."""
    return [f.strip() for f in value.split(",")]


def parse_event_line(kind: str, value: str, fmt: list[str], index: int = 0) -> Event:
    """Build an :class:`Event` from the value part of an event line.

    ``value`` is everything after ``"Dialogue:"`` (leading whitespace
    stripped).  Only the first ``len(fmt) - 1`` commas split fields, so the
    final column (normally Text) may contain commas freely.
    """
    ncols = len(fmt)
    fields = value.split(",", ncols - 1) if ncols > 0 else [value]
    ev = Event(kind=kind, index=index)
    for i, col in enumerate(fmt):
        if i >= len(fields):
            break  # short line: keep Event defaults for the missing columns
        raw = fields[i]
        attr = _COLUMN_TO_ATTR.get(col.lower())
        if attr is None:
            ev.extra[col] = raw
        elif attr == "layer":
            try:
                ev.layer = int(raw.strip())
            except ValueError:
                # Non-numeric layer (e.g. "Marked=0" in SSA files): keep raw.
                ev.extra[col] = raw
        else:
            setattr(ev, attr, raw)
    return ev


def parse_string(text: str) -> AssFile:
    """Parse .ass content from a string.

    A leading U+FEFF is treated as a BOM and stripped (``ass.bom = True``).
    Newline style is detected from the content.
    """
    ass = AssFile()
    if text.startswith("\ufeff"):
        text = text[1:]
        ass.bom = True
        ass.encoding = "utf-8-sig"
    else:
        ass.bom = False
        ass.encoding = "utf-8"
    ass.newline = detect_newline(text)
    ass.event_format = list(DEFAULT_EVENT_FORMAT)

    lines = text.split(ass.newline)
    current = Section(name="")  # preamble (lines before the first header)
    ass.sections.append(current)
    in_events = False
    line_no_in_section = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]") and len(stripped) > 2:
            name = stripped[1:-1].strip()
            current = Section(name=name)
            ass.sections.append(current)
            in_events = name.lower() == "events"
            line_no_in_section = 0
            continue

        if in_events and stripped and not stripped.startswith(";"):
            kv = _split_key_value(line)
            if kv is not None:
                key, value = kv
                if key.lower() == "format":
                    ass.event_format = parse_format_line(value)
                    current.lines.append(line)
                    line_no_in_section += 1
                    continue
                kind = _canonical_kind(key)
                if kind is not None:
                    ev = parse_event_line(kind, value, ass.event_format, index=line_no_in_section)
                    ass.events.append(ev)
                    current.lines.append(EVENT_PLACEHOLDER)
                    line_no_in_section += 1
                    continue
        current.lines.append(line)
        line_no_in_section += 1

    # Drop an empty preamble so `sections` starts with the first real section.
    if not ass.sections[0].lines and ass.sections[0].name == "":
        ass.sections.pop(0)
    return ass


def _canonical_kind(key: str) -> str | None:
    for k in EVENT_KINDS:
        if k.lower() == key.lower():
            return k
    return None


def parse_bytes(data: bytes) -> AssFile:
    """Parse raw bytes, detecting BOM/encoding and newline style."""
    text, codec, bom = decode_bytes(data)
    ass = parse_string(text)
    ass.bom = bom
    if codec == "utf-8":
        ass.encoding = "utf-8-sig" if bom else "utf-8"
    else:
        ass.encoding = codec
    return ass


def parse_file(path: Union[str, Path]) -> AssFile:
    """Read and parse an .ass file from disk."""
    p = Path(path)
    ass = parse_bytes(p.read_bytes())
    ass.path = str(p)
    return ass


def parse_styles(ass: AssFile) -> dict[str, dict[str, str]]:
    """Read the [V4+ Styles] (or [V4 Styles]) section into ``{name: {field: value}}``.

    Returns an empty dict when the file has no style section.  Field names
    come from the section's Format line (default: the ASS v4+ style format).
    """
    section = ass.section("V4+ Styles") or ass.section("V4 Styles") or ass.section("V4+ Styles+")
    if section is None:
        return {}
    fmt = list(DEFAULT_STYLE_FORMAT)
    styles: dict[str, dict[str, str]] = {}
    for line in section.lines:
        kv = _split_key_value(line)
        if kv is None:
            continue
        key, value = kv
        if key.lower() == "format":
            fmt = parse_format_line(value)
        elif key.lower() == "style":
            fields = value.split(",", len(fmt) - 1)
            fields = [f.strip() for f in fields]
            row = {col: (fields[i] if i < len(fields) else "") for i, col in enumerate(fmt)}
            name = row.get("Name", fields[0] if fields else "")
            styles[name] = row
    return styles


DEFAULT_STYLE_FORMAT = [
    "Name", "Fontname", "Fontsize", "PrimaryColour", "SecondaryColour",
    "OutlineColour", "BackColour", "Bold", "Italic", "Underline", "StrikeOut",
    "ScaleX", "ScaleY", "Spacing", "Angle", "BorderStyle", "Outline", "Shadow",
    "Alignment", "MarginL", "MarginR", "MarginV", "Encoding",
]
