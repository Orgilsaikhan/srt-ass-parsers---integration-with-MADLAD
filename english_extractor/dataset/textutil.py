"""Text helpers for the dataset pipeline.

This module keeps `english_extractor/dataset` self-sufficient: it prefers the shared
implementations in `english_extractor.ass.tags` / `english_extractor.ass.validator` / `english_extractor.ass.parser`
when they exist, and falls back to small local equivalents otherwise.
Only `Event` from `english_extractor.ass.models` is a hard dependency.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Callable, Iterable

import regex

from english_extractor.ass.models import DEFAULT_EVENT_FORMAT, Event

# ---------------------------------------------------------------------------
# Local fallbacks (used only when english_extractor.ass.tags / english_extractor.ass.validator are absent)
# ---------------------------------------------------------------------------

_OVERRIDE_BLOCK = regex.compile(r"\{[^}]*\}")
_DRAWING = regex.compile(r"\\p[1-9]")
_KARAOKE = regex.compile(r"\\(?:k[fo]?|K)\d")
_HARD_SPACE = regex.compile(r"\\h")
_LINE_BREAK = regex.compile(r"\\[Nn]")
_MULTI_SPACE = regex.compile(r"[ \t]+")
_LETTER = regex.compile(r"\p{L}")
_LATIN = regex.compile(r"\p{Script=Latin}")
_CYRILLIC = regex.compile(r"\p{Script=Cyrillic}")
_WORD = regex.compile(r"[\p{L}\p{N}][\p{L}\p{M}\p{N}'’\-]*")


def _local_strip_tags(text: str) -> str:
    """Remove override blocks, turn \\N into newlines, normalise whitespace."""
    if not text:
        return ""
    out = _OVERRIDE_BLOCK.sub("", text)
    out = _LINE_BREAK.sub("\n", out)
    out = _HARD_SPACE.sub(" ", out)
    lines = [_MULTI_SPACE.sub(" ", ln).strip() for ln in out.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


def _local_is_translatable(text: str) -> bool:
    if not text or not text.strip():
        return False
    if _DRAWING.search(text) or _KARAOKE.search(text):
        return False
    plain = _local_strip_tags(text)
    if not plain:
        return False
    return _LETTER.search(plain) is not None


def _local_latin_ratio(text: str) -> float:
    letters = _LETTER.findall(text or "")
    if not letters:
        return 0.0
    return len(_LATIN.findall(text)) / len(letters)


def _local_cyrillic_ratio(text: str) -> float:
    letters = _LETTER.findall(text or "")
    if not letters:
        return 0.0
    return len(_CYRILLIC.findall(text)) / len(letters)


# ---------------------------------------------------------------------------
# Resolution: prefer the shared modules when present
# ---------------------------------------------------------------------------

strip_tags: Callable[[str], str]
is_translatable: Callable[[str], bool]
latin_ratio: Callable[[str], float]
cyrillic_ratio: Callable[[str], float]

try:  # pragma: no cover - depends on the sibling package landing
    from english_extractor.ass.tags import is_translatable, strip_tags  # type: ignore[no-redef]
except Exception:  # ImportError or a partially built module
    strip_tags = _local_strip_tags
    is_translatable = _local_is_translatable

try:  # pragma: no cover
    from english_extractor.ass.validator import cyrillic_ratio, latin_ratio  # type: ignore[no-redef]
except Exception:
    latin_ratio = _local_latin_ratio
    cyrillic_ratio = _local_cyrillic_ratio


def plain_text(text: str) -> str:
    """Translatable text of an event, tags removed, on a single line."""
    return " ".join(strip_tags(text).split())


def words(text: str) -> list[str]:
    """Tokens that contain at least one letter or digit."""
    return _WORD.findall(text or "")


def word_count(text: str) -> int:
    return len(words(text))


def has_override_tags(text: str) -> bool:
    """True if the raw event text carries at least one ``{...}`` override block."""
    return _OVERRIDE_BLOCK.search(text or "") is not None


def has_control_chars(text: str) -> bool:
    for ch in text:
        if ch in "\n\t":
            continue
        if unicodedata.category(ch) in ("Cc", "Cf") and ch != "\u200b":
            return True
    return False


# ---------------------------------------------------------------------------
# Dialogue loading with a guarded fallback parser
# ---------------------------------------------------------------------------

def _decode(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _fallback_parse_events(path: Path) -> list[Event]:
    """Minimal [Events] reader used only when english_extractor.ass.parser is unavailable."""
    text = _decode(Path(path).read_bytes())
    events: list[Event] = []
    fmt = list(DEFAULT_EVENT_FORMAT)
    in_events = False
    idx = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_events = stripped.lower() == "[events]"
            continue
        if not in_events or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        if key.lower() == "format":
            fmt = [f.strip() for f in value.split(",")]
            continue
        if key not in ("Dialogue", "Comment", "Picture", "Sound", "Movie", "Command"):
            continue
        parts = value.lstrip().split(",", len(fmt) - 1)
        if len(parts) < len(fmt):
            parts += [""] * (len(fmt) - len(parts))
        row = dict(zip(fmt, parts))
        ev = Event(
            kind=key,
            layer=int(row.get("Layer", "0") or 0) if str(row.get("Layer", "0")).lstrip("-").isdigit() else 0,
            start=row.get("Start", "0:00:00.00"),
            end=row.get("End", "0:00:00.00"),
            style=row.get("Style", "Default"),
            name=row.get("Name", ""),
            margin_l=row.get("MarginL", "0"),
            margin_r=row.get("MarginR", "0"),
            margin_v=row.get("MarginV", "0"),
            effect=row.get("Effect", ""),
            text=row.get("Text", ""),
            index=idx,
        )
        idx += 1
        events.append(ev)
    return events


SUBTITLE_EXTENSIONS = (".ass", ".ssa", ".srt")


def load_dialogues(path: str | Path) -> list[Event]:
    """Dialogue events of a subtitle file, dispatching on extension:
    ``.srt`` -> english_extractor.ass.srt.parse_srt_file, ``.ass``/``.ssa`` -> english_extractor.ass.parser."""
    path = Path(path)
    if path.suffix.lower() == ".srt":
        from english_extractor.ass.srt import parse_srt_file

        return list(parse_srt_file(path).dialogues)
    try:
        from english_extractor.ass.parser import parse_file  # type: ignore
    except Exception:
        parse_file = None  # type: ignore[assignment]
    if parse_file is not None:
        try:
            return list(parse_file(str(path)).dialogues)
        except Exception:
            pass  # fall through to the tolerant local reader
    return [e for e in _fallback_parse_events(path) if e.is_dialogue]


def translatable_plain_texts(events: Iterable[Event]) -> list[str]:
    return [plain_text(e.text) for e in events if is_translatable(e.text)]
