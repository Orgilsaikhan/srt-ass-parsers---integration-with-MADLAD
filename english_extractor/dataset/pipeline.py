"""End-to-end English dataset extraction: discover -> stats -> extract -> clean -> split.

    python -m english_extractor.dataset.pipeline "Raw Files"
    python -m english_extractor.dataset.pipeline "Raw Files" "Unpaired/English" --out some/folder

Everything is written below --out (default: english_extractor/output/); the
project's data/ and reports/ folders are never touched.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from english_extractor import DEFAULT_OUTPUT
from english_extractor.dataset.clean import CleanConfig, iter_jsonl, run_clean
from english_extractor.dataset.discover import build_manifest, write_manifest
from english_extractor.dataset.extract import run_extraction
from english_extractor.dataset.split import run_split
from english_extractor.dataset.statistics import compute_statistics, write_reports


def run_pipeline(raw_roots: Sequence[str | Path], out_root: str | Path = DEFAULT_OUTPUT,
                 seed: int = 42, ratios=(0.8, 0.1, 0.1), test_movies: Optional[list[str]] = None,
                 dedupe: bool = True) -> dict:
    out_root = Path(out_root)
    reports_dir = out_root / "reports"
    extracted_dir, cleaned_dir = out_root / "extracted", out_root / "cleaned"

    # 1. discover English files
    manifest = build_manifest(raw_roots)
    write_manifest(manifest, out_root / "files.json")
    # 2. stats
    stats = compute_statistics(manifest.to_dict())
    write_reports(stats, reports_dir / "dataset_stats.md")
    # 3. extract lines
    extract_summary = run_extraction(manifest.to_dict(), extracted_dir)
    # 4. clean -- only this run's episodes, so files left in extracted/ by an earlier run are never mixed in
    this_run = [extracted_dir / f"{mid}.jsonl" for mid in extract_summary["movies"]]
    clean_result = run_clean(this_run, cleaned_dir, reports_dir / "cleaning_report.md", CleanConfig(dedupe=dedupe))
    # 5. split
    split_manifest = run_split(iter_jsonl(cleaned_dir / "clean.jsonl"), out_root, ratios, seed, test_movies)

    return {
        "out": str(out_root),
        "files": len(manifest.files),
        "skipped": len(manifest.skipped),
        "duplicates": len(manifest.duplicates),
        "stats": {k: stats[k] for k in ("dialogue_entries", "translatable_entries", "words")},
        "extracted": extract_summary["total_lines"],
        "dropped": extract_summary["dropped"],
        "failed": extract_summary["failed"],
        "clean": len(clean_result.clean),
        "review": len(clean_result.review),
        "rejected": len(clean_result.rejected),
        "top_reject_reasons": clean_result.reason_counts.most_common(8),
        "split": split_manifest["line_counts"],
    }


def format_summary(s: dict) -> str:
    lines = [
        "=" * 64,
        "ENGLISH DATASET EXTRACTION SUMMARY",
        "=" * 64,
        f"English files: {s['files']}   skipped (not English / unknown): {s['skipped']}   "
        f"duplicate files: {s['duplicates']}",
        f"Dialogue entries: {s['stats']['dialogue_entries']}   translatable: {s['stats']['translatable_entries']}   "
        f"words: {s['stats']['words']}",
        f"Extracted lines: {s['extracted']}   dropped: {s['dropped']}",
        "",
        f"  >>> {s['clean']} clean English lines <<<",
        f"  review: {s['review']}   rejected: {s['rejected']}",
        f"  top reject/review reasons: {s['top_reject_reasons']}",
        f"Split (lines): {s['split']}",
        f"Output: {s['out']}",
    ]
    if s["failed"]:
        lines.append(f"Unreadable files: {len(s['failed'])} (see extracted/extract_summary.json)")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Extract a clean English subtitle dataset.")
    ap.add_argument("raw_roots", nargs="+", help='folders to scan, e.g. "Raw Files" "Unpaired/English"')
    ap.add_argument("--out", default=str(DEFAULT_OUTPUT), help="output folder (default: english_extractor/output)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--ratios", type=float, nargs=3, default=(0.8, 0.1, 0.1))
    ap.add_argument("--test-movies", nargs="*", default=None)
    ap.add_argument("--no-dedupe", action="store_true", help="keep repeated lines (e.g. 'Yeah.' in every episode)")
    args = ap.parse_args(argv)

    summary = run_pipeline(args.raw_roots, args.out, args.seed, tuple(args.ratios), args.test_movies,
                           not args.no_dedupe)
    print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
