"""Post-translation validation (plan section 19).

:func:`validate_structure` checks that everything except the translatable
text survived untouched; :func:`validate_translation` checks the quality of
the Mongolian output at a coarse, heuristic level.  Both return lists of
human-readable issue strings (empty = OK).
"""
from __future__ import annotations

import re
import unicodedata

from .models import AssFile, Event
from .tags import is_translatable, strip_tags, validate_tags

_LATIN_RE = re.compile(r"[A-Za-zÀ-ɏ]")
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
_LETTER_RE = re.compile(r"[^\W\d_]")
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")

#: Sections whose raw lines must be byte-identical between input and output.
_FROZEN_SECTIONS = ("script info", "v4+ styles", "v4 styles", "v4+ styles+", "aegisub project garbage")

#: Structural fields of an Event that translation must never alter.
_FROZEN_EVENT_FIELDS = ("kind", "layer", "start", "end", "style", "name",
                        "margin_l", "margin_r", "margin_v", "effect", "extra")


def latin_ratio(text: str) -> float:
    """Share of letters that are Latin script (0.0 when there are no letters)."""
    letters = _LETTER_RE.findall(text)
    if not letters:
        return 0.0
    return len(_LATIN_RE.findall(text)) / len(letters)


def cyrillic_ratio(text: str) -> float:
    """Share of letters that are Cyrillic (U+0400-U+04FF); 0.0 without letters."""
    letters = _LETTER_RE.findall(text)
    if not letters:
        return 0.0
    return len(_CYRILLIC_RE.findall(text)) / len(letters)


def _event_label(ev: Event) -> str:
    return f"{ev.kind} #{ev.index} [{ev.start} -> {ev.end}]"


def validate_structure(original: AssFile, output: AssFile) -> list[str]:
    """Check that output preserves everything but the event text."""
    issues: list[str] = []

    orig_names = [s.name for s in original.sections]
    out_names = [s.name for s in output.sections]
    if orig_names != out_names:
        issues.append(f"section list differs: {orig_names} != {out_names}")

    for name in _FROZEN_SECTIONS:
        a = original.section(name)
        b = output.section(name)
        if a is None and b is None:
            continue
        if a is None or b is None:
            issues.append(f"[{name}] present in only one file")
        elif a.lines != b.lines:
            issues.append(f"[{name}] lines changed")

    if original.event_format != output.event_format:
        issues.append("Events Format line differs")

    if len(original.events) != len(output.events):
        issues.append(f"event count differs: {len(original.events)} != {len(output.events)}")

    for a, b in zip(original.events, output.events):
        for f in _FROZEN_EVENT_FIELDS:
            va, vb = getattr(a, f), getattr(b, f)
            if va != vb:
                issues.append(f"{_event_label(a)}: {f} changed ({va!r} -> {vb!r})")
        for tag_issue in validate_tags(a.text, b.text):
            issues.append(f"{_event_label(a)}: {tag_issue}")
    return issues


def _looks_like_name_or_symbol(plain: str) -> bool:
    """Short capitalised words, numbers or symbols - fine to leave untranslated."""
    stripped = plain.strip()
    if not _LETTER_RE.search(stripped):
        return True
    words = _WORD_RE.findall(stripped)
    if not words:
        return True
    if len(words) <= 2 and all(w[0].isupper() for w in words):
        return True
    return False


def _bad_chars(text: str) -> list[str]:
    found: list[str] = []
    for ch in text:
        if ch == "�":
            found.append("U+FFFD")
        elif ch not in "\n\t" and unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cn"):
            found.append(f"U+{ord(ch):04X}")
    return sorted(set(found))


def validate_translation(
    original: AssFile,
    output: AssFile,
    *,
    max_untranslated_ratio: float = 0.02,
    max_latin_ratio: float = 0.25,
) -> list[str]:
    """Heuristic checks on the translated text of dialogue lines."""
    issues: list[str] = []
    translatable = 0
    untranslated: list[str] = []
    all_out_text: list[str] = []
    prev: tuple[str, str] | None = None

    for a, b in zip(original.events, output.events):
        if not is_translatable(a.text):
            continue
        translatable += 1
        src = strip_tags(a.text)
        dst = strip_tags(b.text)
        all_out_text.append(dst)

        if not dst.strip():
            issues.append(f"{_event_label(a)}: empty translation for {src.strip()!r}")
            continue
        bad = _bad_chars(b.text)
        if bad:
            issues.append(f"{_event_label(a)}: unexpected characters {', '.join(bad)}")
        if src.strip() == dst.strip() and not _looks_like_name_or_symbol(src):
            untranslated.append(f"{_event_label(a)}: {src.strip()!r}")
        if a.is_dialogue and prev is not None:
            prev_src, prev_dst = prev
            if dst.strip() == prev_dst and src.strip() != prev_src and len(dst.strip()) > 3:
                issues.append(f"{_event_label(a)}: duplicated translation {dst.strip()!r}")
        if a.is_dialogue:
            prev = (src.strip(), dst.strip())

    if translatable:
        ratio = len(untranslated) / translatable
        if ratio > max_untranslated_ratio:
            sample = "; ".join(untranslated[:5])
            issues.append(
                f"{len(untranslated)}/{translatable} translatable lines identical to source "
                f"({ratio:.1%} > {max_untranslated_ratio:.1%}): {sample}"
            )
        joined = "\n".join(all_out_text)
        lr = latin_ratio(joined)
        if lr > max_latin_ratio:
            issues.append(f"Latin-script ratio in output is {lr:.1%} (> {max_latin_ratio:.0%})")
    return issues
