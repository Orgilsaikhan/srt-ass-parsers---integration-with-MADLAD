"""Formatting protection for ASS override tags (plan section 5).

The text of an event is tokenised into segments:

* ``tag``  - an override block ``{...}`` (kept verbatim, never translated)
* ``draw`` - text while drawing mode (``\\p<n>``, n > 0) is active; vector
  drawing commands, never translated
* ``text`` - translatable text, with ``\\N``/``\\n`` turned into ``"\\n"``
  and ``\\h`` into a normal space

:func:`protect` returns the concatenated ``text`` segments as ``plain`` plus a
template that records, for every non-text segment, its character offset into
``plain``.  :func:`restore` re-inserts the segments around a translation.

Restore heuristic
-----------------
* A segment at offset 0 (before any text) stays leading.
* A segment at offset ``len(plain)`` (after all text) stays trailing.
* Any other (inline) segment is placed at
  ``round(offset / len(plain) * len(translated))``, then snapped to the
  nearest whitespace boundary within 3 characters so words are not split.
  Relative order of segments is always preserved.
* ``"\\n"`` in the translation becomes ``\\N``.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

#: An override block: from ``{`` to the next ``}``.
TAG_RE = re.compile(r"\{[^}]*\}")
_DRAW_RE = re.compile(r"\\p(\d+)")
_KARAOKE_RE = re.compile(r"\\(?:kf|ko|K|k)(?=\d|\s|\\|\})")
_BREAK_RE = re.compile(r"\\N|\\n|\\h")
_LETTER_RE = re.compile(r"[^\W\d_]")

_SNAP_DISTANCE = 3


@dataclass
class ProtectedText:
    """Result of :func:`protect`."""
    plain: str
    #: ``(offset_into_plain, kind, raw)`` for every tag/draw segment, in order.
    template: list[tuple[int, str, str]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    karaoke: bool = False
    drawing: bool = False


def _tokenize(text: str) -> list[tuple[str, str]]:
    """Split into ``[(kind, raw)]`` with kind in {"tag", "draw", "text"}."""
    tokens: list[tuple[str, str]] = []
    drawing = False
    pos = 0
    for m in TAG_RE.finditer(text):
        if m.start() > pos:
            tokens.append(("draw" if drawing else "text", text[pos:m.start()]))
        block = m.group(0)
        tokens.append(("tag", block))
        for dm in _DRAW_RE.finditer(block):
            drawing = int(dm.group(1)) > 0
        pos = m.end()
    if pos < len(text):
        tokens.append(("draw" if drawing else "text", text[pos:]))
    return tokens


def _plainify(raw: str) -> str:
    return _BREAK_RE.sub(lambda m: " " if m.group(0) == r"\h" else "\n", raw)


def protect(text: str) -> ProtectedText:
    """Separate translatable text from override tags / drawings."""
    tokens = _tokenize(text)
    plain_parts: list[str] = []
    template: list[tuple[int, str, str]] = []
    tags: list[str] = []
    offset = 0
    karaoke = False
    drawing = False
    for kind, raw in tokens:
        if kind == "text":
            p = _plainify(raw)
            plain_parts.append(p)
            offset += len(p)
        else:
            template.append((offset, kind, raw))
            if kind == "tag":
                tags.append(raw)
                if _KARAOKE_RE.search(raw):
                    karaoke = True
            else:
                drawing = True
    return ProtectedText(
        plain="".join(plain_parts),
        template=template,
        tags=tags,
        karaoke=karaoke,
        drawing=drawing,
    )


def _snap(pos: int, text: str) -> int:
    """Move ``pos`` to the nearest whitespace boundary within a few chars."""
    n = len(text)
    if pos <= 0 or pos >= n:
        return max(0, min(pos, n))
    if text[pos - 1].isspace() or text[pos].isspace():
        return pos
    for d in range(1, _SNAP_DISTANCE + 1):
        for cand in (pos - d, pos + d):
            if 0 < cand < n and (text[cand - 1].isspace() or text[cand].isspace()):
                return cand
    return pos


def restore(protected: ProtectedText, translated_plain: str) -> str:
    """Re-insert protected segments around ``translated_plain``."""
    src_len = len(protected.plain)
    dst_len = len(translated_plain)
    # Compute insertion offsets in the translation, keeping order monotonic.
    inserts: list[tuple[int, str]] = []
    last = 0
    for offset, _kind, raw in protected.template:
        if offset <= 0:
            pos = 0
        elif offset >= src_len:
            pos = dst_len
        elif src_len == 0:
            pos = dst_len
        else:
            pos = _snap(round(offset / src_len * dst_len), translated_plain)
        pos = max(pos, last)
        last = pos
        inserts.append((pos, raw))

    out: list[str] = []
    cursor = 0
    for pos, raw in inserts:
        out.append(translated_plain[cursor:pos].replace("\n", r"\N"))
        out.append(raw)
        cursor = pos
    out.append(translated_plain[cursor:].replace("\n", r"\N"))
    return "".join(out)


def strip_tags(text: str) -> str:
    """Translatable plain text only (see :func:`protect`)."""
    return protect(text).plain


def has_tags(text: str) -> bool:
    """True if the text contains at least one ``{...}`` override block."""
    return TAG_RE.search(text) is not None


def is_translatable(text: str) -> bool:
    """False for empty/whitespace, karaoke, pure drawing/tags, or no letters."""
    p = protect(text)
    if p.karaoke:
        return False
    plain = p.plain.strip()
    if not plain:
        return False
    return _LETTER_RE.search(plain) is not None


def validate_tags(original_text: str, translated_text: str) -> list[str]:
    """Compare override blocks/drawings between original and translation.

    Returns a list of human-readable issues; empty means OK.
    """
    issues: list[str] = []
    if translated_text.count("{") != translated_text.count("}"):
        issues.append("unbalanced braces in translated text")
    orig = Counter(TAG_RE.findall(original_text))
    trans = Counter(TAG_RE.findall(translated_text))
    missing = orig - trans
    extra = trans - orig
    for tag, n in missing.items():
        issues.append(f"missing tag {tag}" + (f" x{n}" if n > 1 else ""))
    for tag, n in extra.items():
        issues.append(f"unexpected tag {tag}" + (f" x{n}" if n > 1 else ""))
    if not missing and not extra:
        orig_order = TAG_RE.findall(original_text)
        trans_order = TAG_RE.findall(translated_text)
        if orig_order != trans_order:
            issues.append("override tags reordered")
    orig_draw = [raw for _o, kind, raw in protect(original_text).template if kind == "draw"]
    trans_draw = [raw for _o, kind, raw in protect(translated_text).template if kind == "draw"]
    if orig_draw != trans_draw:
        issues.append("drawing commands changed or lost")
    return issues
