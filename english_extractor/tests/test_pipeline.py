from __future__ import annotations

import json
from pathlib import Path

from english_extractor.dataset.pipeline import format_summary, run_pipeline

HEADER = "[Script Info]\nTitle: t\nScriptType: v4.00+\n\n[Events]\n" \
         "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"


def ass(lines: list[str]) -> str:
    body = "".join(f"Dialogue: 0,0:00:{i:02d}.00,0:00:{i + 1:02d}.50,Default,,0,0,0,,{t}\n"
                   for i, t in enumerate(lines))
    return HEADER + body


def test_pipeline_end_to_end(tmp_path: Path):
    raw = tmp_path / "Raw Files"
    (raw / "English").mkdir(parents=True)
    (raw / "Mongolian").mkdir()
    for ep in range(1, 11):
        lines = [f"Episode {ep} line {k} is here." for k in range(20)] + ["Yeah."]
        (raw / "English" / f"show_{ep:02d}_EN.ass").write_text(ass(lines), encoding="utf-8")
        (raw / "Mongolian" / f"show_{ep:02d}_MN.ass").write_text(ass(["Сайн уу."] * 3), encoding="utf-8")
    out = tmp_path / "out"
    stale = out / "extracted" / "old_episode.jsonl"
    stale.parent.mkdir(parents=True)
    stale.write_text(json.dumps({"text": "From an earlier run.", "movie_id": "old_episode"}) + "\n", encoding="utf-8")

    s = run_pipeline([raw], out)
    assert s["files"] == 10 and s["skipped"] == 10
    assert s["extracted"] == 210
    assert s["clean"] == 201 and s["rejected"] == 9                  # "Yeah." kept once
    assert sum(s["split"].values()) == 201
    assert stale.exists()                                            # never deleted ...
    clean_rows = (out / "cleaned" / "clean.jsonl").read_text(encoding="utf-8").splitlines()
    assert "old_episode" not in {json.loads(x)["movie_id"] for x in clean_rows}   # ... and never mixed in
    for rel in ("files.json", "reports/dataset_stats.md", "reports/dataset_stats.json", "reports/cleaning_report.md",
                "extracted/extract_summary.json", "train/train.jsonl", "validation/validation.jsonl",
                "test/test.jsonl", "split_manifest.json"):
        assert (out / rel).exists(), rel
    assert "clean English lines" in format_summary(s)
