"""SubRip (.srt) reader that produces an :class:`AssFile`.

The result is a minimal but complete .ass document ([Script Info],
[V4+ Styles] with one ``Default`` style, [Events] with a Format line and one
:data:`~english_extractor.ass.parser.EVENT_PLACEHOLDER` per cue), so the
extractor treats .srt and .ass input identically.

Conversions
-----------
* ``00:01:23,400`` -> ``0:01:23.40`` (rounded to centiseconds)
* ``<i>..</i>`` -> ``{\\i1}..{\\i0}``, ``<b>``/``<u>`` likewise, ``<font ...>``
  and other HTML-ish tags are dropped, ``<br>`` and cue line breaks -> ``\\N``
* HTML entities are unescaped (after tag conversion, so ``&lt;i&gt;`` stays text)
* existing ASS override blocks such as ``{\\an8}`` are passed through unchanged

Tolerated input: BOM, CRLF/LF/CR, missing or non-numeric cue index lines,
3+ blank lines between cues, blank cues (kept as an empty-text event so cue
numbering/timing stay consistent; ``is_translatable`` filters them later),
exact duplicate cues (skipped), overlapping cues (kept in file order),
trailing whitespace.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from .models import DEFAULT_EVENT_FORMAT, AssFile, Event, Section, seconds_to_timestamp
from .parser import EVENT_PLACEHOLDER, decode_bytes

_TIMING = re.compile(
    r"^\s*(\d{1,2}):(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{1,2}):(\d{1,2})[,.](\d{1,3})(?:\s+.*)?$"
)
_INDEX = re.compile(r"^\s*\d+\s*$")
_TAG_MAP = [
    (re.compile(r"<\s*i\s*>", re.I), r"{\\i1}"),
    (re.compile(r"<\s*/\s*i\s*>", re.I), r"{\\i0}"),
    (re.compile(r"<\s*b\s*>", re.I), r"{\\b1}"),
    (re.compile(r"<\s*/\s*b\s*>", re.I), r"{\\b0}"),
    (re.compile(r"<\s*u\s*>", re.I), r"{\\u1}"),
    (re.compile(r"<\s*/\s*u\s*>", re.I), r"{\\u0}"),
    (re.compile(r"<\s*br\s*/?\s*>", re.I), r"\\N"),
]
_DROP_TAG = re.compile(r"<\s*/?\s*(?:font|span|s|em|strong|ruby|rt|rp|c(?:\.[\w-]+)*|v(?:\s[^>]*)?)\s*[^>]*>", re.I)

STYLE_FORMAT = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
                "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
                "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
DEFAULT_STYLE = ("Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
                 "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1")


@dataclass
class SrtCue:
    start: float
    end: float
    lines: list[str]


def _to_seconds(h: str, m: str, s: str, frac: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(frac.ljust(3, "0")) / 1000.0


def convert_markup(line: str) -> str:
    """SRT/HTML inline markup -> ASS override tags; entities unescaped."""
    out = line
    for pat, repl in _TAG_MAP:
        out = pat.sub(repl, out)
    out = _DROP_TAG.sub("", out)
    return html.unescape(out)


def parse_srt_cues(text: str) -> list[SrtCue]:
    """Line-based state machine tolerant of malformed cue separators."""
    if text.startswith("﻿"):
        text = text[1:]
    # "\r\r\n" is a common artefact of CRLF files re-saved in text mode on Windows
    text = text.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[SrtCue] = []
    cur: SrtCue | None = None

    def finish() -> None:
        nonlocal cur
        if cur is None:
            return
        while cur.lines and not cur.lines[-1].strip():
            cur.lines.pop()
        cues.append(cur)               # empty cues are kept (timing stays consistent)
        cur = None

    for raw in text.split("\n"):
        m = _TIMING.match(raw)
        if m:
            if cur is not None and cur.lines and _INDEX.match(cur.lines[-1]):
                cur.lines.pop()            # index of the next cue glued to this one
            finish()
            cur = SrtCue(_to_seconds(*m.groups()[:4]), _to_seconds(*m.groups()[4:]), [])
            continue
        if cur is None:
            continue                       # index line, junk, or leading blank
        if not raw.strip():
            finish()
            continue
        cur.lines.append(raw.rstrip())
    finish()

    # drop exact duplicates (same timing and text), keep file order
    seen: set[tuple[float, float, str]] = set()
    unique: list[SrtCue] = []
    for c in cues:
        key = (c.start, c.end, "\n".join(c.lines))
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique


def cue_to_event(cue: SrtCue, index: int) -> Event:
    lines = [convert_markup(ln).strip() for ln in cue.lines]
    lines = [ln for ln in lines if ln]
    end = max(cue.end, cue.start)
    return Event(
        kind="Dialogue", layer=0,
        start=seconds_to_timestamp(cue.start), end=seconds_to_timestamp(end),
        style="Default", name="", margin_l="0", margin_r="0", margin_v="0", effect="",
        text=r"\N".join(lines), index=index,
    )


def build_ass(events: list[Event], title: str = "") -> AssFile:
    ass = AssFile(encoding="utf-8-sig", newline="\r\n", bom=True)
    ass.event_format = list(DEFAULT_EVENT_FORMAT)
    ass.sections = [
        Section("Script Info", [f"Title: {title}", "ScriptType: v4.00+", "WrapStyle: 0",
                                "ScaledBorderAndShadow: yes", "PlayResX: 1280", "PlayResY: 720", ""]),
        Section("V4+ Styles", [STYLE_FORMAT, DEFAULT_STYLE, ""]),
        Section("Events", ["Format: " + ", ".join(ass.event_format)]
                + [EVENT_PLACEHOLDER] * len(events) + [""]),
    ]
    ass.events = events
    return ass


def parse_srt_string(text: str, title: str = "") -> AssFile:
    events = [cue_to_event(cue, i) for i, cue in enumerate(parse_srt_cues(text))]
    return build_ass(events, title)


def parse_srt_file(path: Union[str, Path]) -> AssFile:
    p = Path(path)
    text, _codec, _bom = decode_bytes(p.read_bytes())
    ass = parse_srt_string(text, title=p.stem)
    ass.path = str(p)
    return ass
