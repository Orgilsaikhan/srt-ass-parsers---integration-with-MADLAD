"""Shared data model for .ass subtitle files.

This is the contract between the parser (english_extractor/ass) and everything
downstream (english_extractor/dataset). Keep it dependency-free.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Field order used by Aegisub / libass for Dialogue and Comment events when the
# [Events] section has no explicit Format line.
DEFAULT_EVENT_FORMAT = [
    "Layer", "Start", "End", "Style", "Name",
    "MarginL", "MarginR", "MarginV", "Effect", "Text",
]


@dataclass
class Event:
    """One line in [Events] (Dialogue, Comment, or other kinds)."""
    kind: str = "Dialogue"          # "Dialogue" | "Comment" | "Picture" | "Sound" | "Movie" | "Command"
    layer: int = 0
    start: str = "0:00:00.00"       # keep as the original string, never reformat
    end: str = "0:00:00.00"
    style: str = "Default"
    name: str = ""
    margin_l: str = "0"             # keep as strings: some files use "0000"
    margin_r: str = "0"
    margin_v: str = "0"
    effect: str = ""
    text: str = ""
    # Extra fields when the Format line has more columns than the default 10.
    extra: dict[str, str] = field(default_factory=dict)
    # Position of this line in the original file (0-based within the section), for ordering.
    index: int = 0

    @property
    def is_dialogue(self) -> bool:
        return self.kind == "Dialogue"

    @property
    def start_seconds(self) -> float:
        return timestamp_to_seconds(self.start)

    @property
    def end_seconds(self) -> float:
        return timestamp_to_seconds(self.end)

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass
class Section:
    """A generic [Section] with its raw lines preserved verbatim."""
    name: str                       # e.g. "Script Info", "V4+ Styles", "Events"
    lines: list[str] = field(default_factory=list)   # raw lines excluding the header


@dataclass
class AssFile:
    """Parsed .ass document.

    `sections` preserves every section in original order with raw lines so the
    writer can emit them byte-for-byte. `events` is the structured view of the
    [Events] section; the writer re-serialises events from these objects using
    `event_format`.
    """
    sections: list[Section] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    event_format: list[str] = field(default_factory=lambda: list(DEFAULT_EVENT_FORMAT))
    # Original file characteristics so the writer can reproduce them.
    encoding: str = "utf-8-sig"
    newline: str = "\r\n"
    bom: bool = True
    path: Optional[str] = None

    @property
    def dialogues(self) -> list[Event]:
        return [e for e in self.events if e.is_dialogue]

    def section(self, name: str) -> Optional[Section]:
        for s in self.sections:
            if s.name.lower() == name.lower():
                return s
        return None


def timestamp_to_seconds(ts: str) -> float:
    """'0:01:23.40' -> 83.40. Tolerates missing centiseconds and extra digits."""
    ts = ts.strip()
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, (m, s) = "0", parts
    else:
        raise ValueError(f"Bad ASS timestamp: {ts!r}")
    return int(h) * 3600 + int(m) * 60 + float(s)


def seconds_to_timestamp(seconds: float) -> str:
    """83.40 -> '0:01:23.40' (ASS uses centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    h, rem = divmod(total_cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
