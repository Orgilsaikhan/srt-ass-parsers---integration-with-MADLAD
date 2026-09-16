"""Discover English subtitle files (.ass/.ssa/.srt) under one or more roots.

Derived from src/dataset/pair_files.py with the pairing removed.  A file's
language comes from a filename token (`_EN`, `.en`, `english`, ...), else from a
language folder (English/EN/eng), and the script of its dialogue text is ALWAYS
checked too: when the text is clearly Cyrillic or Latin it wins, so a Mongolian
file sitting in an English folder is skipped.  Byte-identical copies are kept
once (first root, then first path, wins).  Episode id = folder path without
language folders + filename without the language token (`yani_07_EN.ass` -> `yani_07`).

Output: a manifest dict / `files.json`:
    {"roots": [...], "files": [{id, path, sha1, language_source}],
     "skipped": [{path, language, reason}], "duplicates": [{sha1, path, duplicate_of}]}
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import regex

from english_extractor import DEFAULT_OUTPUT

EN_TOKENS = {"english", "en", "eng", "engl"}
MN_TOKENS = {"mongolian", "mn", "mon", "mng", "mongol", "khalkha"}
SUBTITLE_EXTENSIONS = {".ass", ".ssa", ".srt"}

_SPLIT = regex.compile(r"[\s._\-()\[\]{}]+")
_UNSAFE = regex.compile(r"[^A-Za-z0-9_.\-]+")


@dataclass
class SubtitleFileInfo:
    path: Path
    rel_dir: str                     # directory relative to root (may include a language folder)
    group_dir: str                   # rel_dir with language folder components removed
    stem: str
    base_key: str
    language: Optional[str]          # "en" | "mn" | None
    language_source: str             # "filename" | "folder" | "content" | "unknown"
    sha1: str = ""


@dataclass
class Manifest:
    roots: list[str] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"roots": self.roots, "files": self.files, "skipped": self.skipped, "duplicates": self.duplicates}


# ---------------------------------------------------------------------------
# Discovery helpers (copied from pair_files.py)
# ---------------------------------------------------------------------------

def discover_subtitle_files(root: str | Path) -> list[Path]:
    root = Path(root)
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUBTITLE_EXTENSIONS]
    return sorted(files, key=lambda p: str(p).lower())


def _tokens(stem: str) -> list[str]:
    return [t for t in _SPLIT.split(stem.lower()) if t]


def language_from_filename(path: str | Path) -> Optional[str]:
    """'en'/'mn' if the filename carries an unambiguous language token, else None."""
    toks = _tokens(Path(path).stem)
    has_en = any(t in EN_TOKENS for t in toks)
    has_mn = any(t in MN_TOKENS for t in toks)
    if has_en and not has_mn:
        return "en"
    if has_mn and not has_en:
        return "mn"
    return None


def strip_language_token(stem: str) -> str:
    """Base key of a filename with language tokens removed and separators normalised."""
    toks = [t for t in _tokens(stem) if t not in EN_TOKENS and t not in MN_TOKENS]
    return "_".join(toks)


def language_from_folder(rel_dir: str) -> tuple[Optional[str], str]:
    """Language implied by a directory component named English/EN/Mongolian/MN...
    Returns (language, rel_dir without those components)."""
    lang: Optional[str] = None
    kept: list[str] = []
    for comp in [c for c in rel_dir.split("/") if c]:
        low = comp.lower()
        if low in EN_TOKENS:
            lang = lang or "en"
        elif low in MN_TOKENS:
            lang = lang or "mn"
        else:
            kept.append(comp)
    return lang, "/".join(kept)


def language_from_content(path: str | Path, max_lines: int = 300) -> Optional[str]:
    """Detect language by script of dialogue text."""
    from english_extractor.dataset.textutil import cyrillic_ratio, latin_ratio, load_dialogues, translatable_plain_texts

    try:
        events = load_dialogues(path)
    except Exception:
        return None
    texts = translatable_plain_texts(events[: max_lines * 3])[:max_lines]
    if not texts:
        return None
    sample = "\n".join(texts)
    cyr = cyrillic_ratio(sample)
    lat = latin_ratio(sample)
    if cyr >= 0.5:
        return "mn"
    if lat >= 0.5:
        return "en"
    return None


def sha1_of(path: str | Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_file(path: Path, root: Path) -> SubtitleFileInfo:
    rel_dir = path.parent.relative_to(root).as_posix() if path.parent != root else ""
    folder_lang, group_dir = language_from_folder(rel_dir)
    lang = language_from_filename(path)
    source = "filename" if lang else "unknown"
    if lang is None and folder_lang is not None:
        lang, source = folder_lang, "folder"
    detected = language_from_content(path)     # always checked: folder/filename labels have been wrong before
    if detected is not None and detected != lang:
        lang, source = detected, "content"
    return SubtitleFileInfo(
        path=path,
        rel_dir=rel_dir,
        group_dir=group_dir,
        stem=path.stem,
        base_key=strip_language_token(path.stem),
        language=lang,
        language_source=source,
        sha1=sha1_of(path),
    )


def make_id(rel_dir: str, base_key: str) -> str:
    parts = [p for p in (rel_dir.replace("/", "_"), base_key) if p]
    raw = "_".join(parts) or "root"
    return _UNSAFE.sub("_", raw).strip("_") or "root"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def build_manifest(roots: str | Path | Iterable[str | Path]) -> Manifest:
    root_list = [Path(roots)] if isinstance(roots, (str, Path)) else [Path(r) for r in roots]
    manifest = Manifest(roots=[str(r) for r in root_list])
    kept_by_sha: dict[str, str] = {}
    used_ids: set[str] = set()

    for root in root_list:
        if not root.is_dir():
            raise FileNotFoundError(f"not a directory: {root}")
        for path in discover_subtitle_files(root):
            info = inspect_file(path, root)
            if info.language != "en":
                manifest.skipped.append({"path": str(path), "language": info.language,
                                         "reason": "not_english" if info.language else "language_unknown"})
                continue
            if info.sha1 in kept_by_sha:
                manifest.duplicates.append({"sha1": info.sha1, "path": str(path),
                                            "duplicate_of": kept_by_sha[info.sha1]})
                continue
            pid = make_id(info.group_dir, info.base_key)
            uid, n = pid, 1
            while uid in used_ids:
                n += 1
                uid = f"{pid}_{n}"
            used_ids.add(uid)
            kept_by_sha[info.sha1] = str(path)
            manifest.files.append({"id": uid, "path": str(path), "sha1": info.sha1,
                                   "language_source": info.language_source})
    return manifest


def write_manifest(manifest: Manifest, out: str | Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_manifest(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Find English subtitle files.")
    ap.add_argument("roots", nargs="+", help='folders to scan, e.g. "Raw Files" "Unpaired/English"')
    ap.add_argument("--out", default=str(DEFAULT_OUTPUT / "files.json"))
    args = ap.parse_args(argv)

    manifest = build_manifest(args.roots)
    write_manifest(manifest, args.out)
    print(f"english files: {len(manifest.files)}  skipped: {len(manifest.skipped)}  "
          f"duplicates: {len(manifest.duplicates)}  -> {args.out}")
    for s in manifest.skipped[:20]:
        print(f"  skipped [{s['reason']}] {s['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
