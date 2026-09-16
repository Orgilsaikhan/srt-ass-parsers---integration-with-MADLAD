"""Train/validation/test split BY EPISODE (copied from src/dataset/split.py, plan §10).

Episodes are sorted by line count (descending, seeded tie-break) and each is
assigned greedily to the split whose current fill (lines / target lines) is
lowest, so line counts approximate the requested ratios while no episode ever
appears in two splits.  A fixed list of held-out test episodes can be forced.
Only the output record differs from the original: English text, no target.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

from english_extractor import DEFAULT_OUTPUT
from english_extractor.dataset.clean import iter_jsonl, write_jsonl

SPLITS = ("train", "validation", "test")
OUTPUT_FIELDS = ("text", "context_before", "context_after", "speaker", "movie_id", "start", "end")


def split_by_movie(line_counts: dict[str, int], ratios: tuple[float, float, float] = (0.8, 0.1, 0.1),
                   seed: int = 42, test_movies: Optional[Iterable[str]] = None) -> dict[str, str]:
    """Map movie_id -> split name."""
    if abs(sum(ratios) - 1.0) > 1e-6:
        raise ValueError(f"ratios must sum to 1, got {ratios}")
    total = sum(line_counts.values())
    targets = {name: max(ratio * total, 1e-9) for name, ratio in zip(SPLITS, ratios)}
    current: dict[str, int] = {name: 0 for name in SPLITS}
    assignment: dict[str, str] = {}

    forced = set(test_movies or [])
    for mid in sorted(forced):
        if mid in line_counts:
            assignment[mid] = "test"
            current["test"] += line_counts[mid]

    rng = random.Random(seed)
    remaining = [m for m in line_counts if m not in assignment]
    rng.shuffle(remaining)                                # seeded tie-break
    remaining.sort(key=lambda m: line_counts[m], reverse=True)

    for mid in remaining:
        # split with the lowest fill fraction; ties -> train, validation, test order
        best = min(SPLITS, key=lambda s: (current[s] / targets[s], SPLITS.index(s)))
        assignment[mid] = best
        current[best] += line_counts[mid]
    return assignment


def to_output_record(rec: dict) -> dict:
    return {
        "text": rec.get("text") or "",
        "context_before": rec.get("context_before") or "",
        "context_after": rec.get("context_after") or "",
        "speaker": rec.get("speaker"),
        "movie_id": rec.get("movie_id"),
        "start": rec.get("start"),
        "end": rec.get("end"),
    }


def run_split(records: Iterable[dict], out_root: str | Path, ratios=(0.8, 0.1, 0.1), seed: int = 42,
              test_movies: Optional[Iterable[str]] = None) -> dict:
    records = list(records)
    by_movie: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_movie[str(r.get("movie_id"))].append(r)
    counts = {m: len(v) for m, v in by_movie.items()}
    assignment = split_by_movie(counts, ratios, seed, test_movies)

    out_root = Path(out_root)
    buckets: dict[str, list[dict]] = {s: [] for s in SPLITS}
    for mid, recs in by_movie.items():
        buckets[assignment[mid]].extend(to_output_record(r) for r in recs)
    for s in SPLITS:
        write_jsonl(buckets[s], out_root / s / f"{s}.jsonl")

    total = len(records) or 1
    manifest = {
        "seed": seed,
        "ratios": dict(zip(SPLITS, ratios)),
        "forced_test_movies": sorted(set(test_movies or [])),
        "line_counts": {s: len(buckets[s]) for s in SPLITS},
        "line_shares": {s: round(len(buckets[s]) / total, 4) for s in SPLITS},
        "movie_counts": dict(Counter(assignment.values())),
        "movies": {s: sorted(m for m, a in assignment.items() if a == s) for s in SPLITS},
        "assignment": assignment,
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "split_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
    return manifest


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Split cleaned English lines by episode id.")
    ap.add_argument("source", nargs="?", default=str(DEFAULT_OUTPUT / "cleaned" / "clean.jsonl"))
    ap.add_argument("--out", default=str(DEFAULT_OUTPUT), help="root containing train/ validation/ test/")
    ap.add_argument("--ratios", type=float, nargs=3, default=(0.8, 0.1, 0.1), metavar=("TRAIN", "VAL", "TEST"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--test-movies", nargs="*", default=None, help="episode ids forced into the test split")
    args = ap.parse_args(argv)

    m = run_split(iter_jsonl(args.source), args.out, tuple(args.ratios), args.seed, args.test_movies)
    print(json.dumps({k: m[k] for k in ("line_counts", "line_shares", "movie_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
