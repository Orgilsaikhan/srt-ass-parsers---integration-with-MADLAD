from __future__ import annotations

import json
import random
from pathlib import Path

from english_extractor.dataset.split import OUTPUT_FIELDS, run_split, split_by_movie


def test_no_movie_in_two_splits_and_ratios_hold():
    rng = random.Random(1)
    counts = {f"movie_{i:03d}": rng.randint(200, 1500) for i in range(60)}
    assignment = split_by_movie(counts, seed=7)
    assert set(assignment) == set(counts)                 # every movie assigned exactly once
    totals = {"train": 0, "validation": 0, "test": 0}
    for m, s in assignment.items():
        totals[s] += counts[m]
    total = sum(counts.values())
    assert abs(totals["train"] / total - 0.8) < 0.05
    assert abs(totals["validation"] / total - 0.1) < 0.04
    assert abs(totals["test"] / total - 0.1) < 0.04
    # deterministic for the same seed
    assert split_by_movie(counts, seed=7) == assignment


def test_forced_test_movies():
    counts = {f"m{i}": 100 for i in range(20)}
    assignment = split_by_movie(counts, seed=3, test_movies=["m1", "m5"])
    assert assignment["m1"] == "test" and assignment["m5"] == "test"
    assert list(assignment.values()).count("test") == 2


def test_run_split_writes_files(tmp_path: Path):
    records = []
    for m in range(12):
        for k in range(50):
            records.append({"text": f"line {k} of {m}", "movie_id": f"mv{m}", "speaker": None,
                            "context_before": "", "context_after": "", "start": float(k), "end": k + 0.5,
                            "style": "Default", "event_index": k, "status": "clean", "reasons": []})
    manifest = run_split(records, tmp_path, seed=1)
    seen: dict[str, str] = {}
    for split in ("train", "validation", "test"):
        path = tmp_path / split / f"{split}.jsonl"
        assert path.exists()
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            assert set(rec) == set(OUTPUT_FIELDS)          # no style / status / reasons / target
            assert seen.setdefault(rec["movie_id"], split) == split
    assert sum(manifest["line_counts"].values()) == len(records)
    assert manifest["line_counts"]["train"] > manifest["line_counts"]["test"] > 0
    loaded = json.loads((tmp_path / "split_manifest.json").read_text(encoding="utf-8"))
    assert loaded["assignment"] == manifest["assignment"]
