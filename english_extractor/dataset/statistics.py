"""English dataset statistics (adapted from src/dataset/statistics.py, plan §3).

Input: a files manifest (files.json) or a raw directory (discovered on the fly).
Output: `dataset_stats.md` and `dataset_stats.json`.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from english_extractor import DEFAULT_OUTPUT
from english_extractor.dataset.discover import build_manifest, load_manifest
from english_extractor.dataset.textutil import is_translatable, load_dialogues, plain_text, word_count


@dataclass
class FileStats:
    id: str
    path: str
    dialogue_count: int
    translatable_count: int
    words: int
    chars: int

    @property
    def avg_chars(self) -> float:
        return self.chars / self.translatable_count if self.translatable_count else 0.0

    @property
    def avg_words(self) -> float:
        return self.words / self.translatable_count if self.translatable_count else 0.0


def file_stats(file_id: str, path: str | Path) -> FileStats:
    events = load_dialogues(path)
    texts = [plain_text(e.text) for e in events if is_translatable(e.text)]
    return FileStats(
        id=file_id,
        path=str(path),
        dialogue_count=len(events),
        translatable_count=len(texts),
        words=sum(word_count(t) for t in texts),
        chars=sum(len(t) for t in texts),
    )


def compute_statistics(manifest: dict) -> dict:
    totals = {"files": 0, "dialogues": 0, "translatable": 0, "words": 0, "chars": 0}
    per_file: list[dict] = []
    failed: list[dict] = []
    ext: dict[str, int] = {}
    for f in manifest.get("files", []):
        try:
            fs = file_stats(f["id"], f["path"])
        except Exception as exc:  # extraction reports the same file; keep the report going
            failed.append({"id": f["id"], "error": repr(exc)})
            continue
        totals["files"] += 1
        totals["dialogues"] += fs.dialogue_count
        totals["translatable"] += fs.translatable_count
        totals["words"] += fs.words
        totals["chars"] += fs.chars
        d = asdict(fs)
        d["avg_chars"] = round(fs.avg_chars, 2)
        d["avg_words"] = round(fs.avg_words, 2)
        per_file.append(d)
        e = Path(f["path"]).suffix.lower()
        ext[e] = ext.get(e, 0) + 1

    skipped = manifest.get("skipped", [])
    t = totals["translatable"]
    return {
        "files": totals["files"],
        "extensions": ext,
        "skipped": {reason: sum(1 for s in skipped if s.get("reason") == reason)
                    for reason in ("not_english", "language_unknown")},
        "duplicates": len(manifest.get("duplicates", [])),
        "dialogue_entries": totals["dialogues"],
        "translatable_entries": t,
        "words": totals["words"],
        "characters": totals["chars"],
        "average_subtitle_length": {
            "chars": round(totals["chars"] / t, 2) if t else 0.0,
            "words": round(totals["words"] / t, 2) if t else 0.0,
        },
        "failed": failed,
        "per_file": per_file,
    }


def render_markdown(stats: dict) -> str:
    a = stats["average_subtitle_length"]
    lines = [
        "# English dataset statistics", "",
        "| Metric | Value |", "|---|---:|",
        f"| English files | {stats['files']} |",
        f"| Dialogue entries | {stats['dialogue_entries']} |",
        f"| Translatable entries | {stats['translatable_entries']} |",
        f"| Words | {stats['words']} |",
        f"| Characters | {stats['characters']} |",
        f"| Avg. subtitle length (chars) | {a['chars']} |",
        f"| Avg. subtitle length (words) | {a['words']} |",
        "",
        f"Extensions: {stats['extensions']}  ·  Skipped (not English): {stats['skipped']['not_english']}  ·  "
        f"Skipped (language unknown): {stats['skipped']['language_unknown']}  ·  "
        f"Duplicate files: {stats['duplicates']}  ·  Unreadable: {len(stats['failed'])}", "",
        "## Per-file table", "",
        "| id | dialogues | translatable | words | chars | file |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in stats["per_file"]:
        lines.append(f"| {r['id']} | {r['dialogue_count']} | {r['translatable_count']} | {r['words']} | "
                     f"{r['chars']} | {r['path']} |")
    return "\n".join(lines) + "\n"


def write_reports(stats: dict, md_path: str | Path) -> tuple[Path, Path]:
    md_path = Path(md_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(stats), encoding="utf-8")
    json_path = md_path.with_suffix(".json")
    json_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Compute English dataset statistics.")
    ap.add_argument("source", nargs="?", default=str(DEFAULT_OUTPUT / "files.json"),
                    help="files.json manifest or a raw directory")
    ap.add_argument("--out", default=str(DEFAULT_OUTPUT / "reports" / "dataset_stats.md"))
    args = ap.parse_args(argv)

    src = Path(args.source)
    manifest = build_manifest(src).to_dict() if src.is_dir() else load_manifest(src)
    stats = compute_statistics(manifest)
    md, js = write_reports(stats, args.out)
    print(render_markdown(stats).split("## Per-file table")[0])
    print(f"written: {md}, {js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
