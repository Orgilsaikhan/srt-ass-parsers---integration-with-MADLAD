"""Extraction tests built from synthetic Event lists (adapted from tests/test_alignment.py)."""
from __future__ import annotations

import json
from pathlib import Path

from english_extractor.ass.models import Event, seconds_to_timestamp
from english_extractor.dataset.extract import ExtractConfig, extract_lines, run_extraction, to_records


def ev(idx: int, start: float, end: float, text: str, style: str = "Default", name: str = "",
       effect: str = "") -> Event:
    return Event(kind="Dialogue", start=seconds_to_timestamp(start), end=seconds_to_timestamp(end),
                 style=style, name=name, text=text, effect=effect, index=idx)


EN = [
    ev(0, 1.0, 3.0, "Hello."),
    ev(1, 4.0, 6.5, "How are you?"),
    ev(2, 7.0, 9.0, "I'm fine."),
]


def test_sign_lines_are_skipped():
    events = list(EN) + [ev(3, 1.0, 3.0, "{\\an8}BAKERY", style="Sign"),
                         ev(4, 4.0, 6.5, "{\\pos(10,10)\\p1}m 0 0 l 10 10{\\p0}"),
                         ev(5, 4.0, 6.5, "OP lyrics", style="OP-EN"),
                         ev(6, 7.0, 9.0, "1234"),
                         ev(7, 20.0, 23.0, "Scroll", effect="Banner;10"),
                         ev(8, 9.5, 10.0, "Store", style="sign_generic"),
                         ev(9, 11.0, 12.0, "{\\k20}ka{\\k30}ra")]
    lines, dropped = extract_lines(events)
    assert [ln.index for ln in lines] == [0, 1, 2]
    assert dropped == {"not_translatable": 3, "skipped_style": 3, "skipped_effect": 1, "bad_timestamp": 0}


def test_lines_sorted_by_time_with_context_and_speaker():
    events = [ev(0, 5.0, 6.0, "Second.", name="Bob"),
              ev(1, 1.0, 3.0, r"{\i1}First.{\i0}", name="Anna"),
              ev(2, 7.0, 6.0, "Third,\\Nsplit over two lines.")]
    lines, _ = extract_lines(events)
    recs = to_records(lines, "ks_07")
    assert [r["text"] for r in recs] == ["First.", "Second.", "Third, split over two lines."]
    assert [r["speaker"] for r in recs] == ["Anna", "Bob", None]
    assert recs[0]["context_before"] == "" and recs[0]["context_after"] == "Second."
    assert recs[1]["context_before"] == "First." and recs[2]["context_after"] == ""
    assert recs[0]["has_tags"] is True and recs[1]["has_tags"] is False
    assert recs[2]["start"] == 7.0 and recs[2]["end"] == 7.0          # end before start is clamped
    assert recs[0]["movie_id"] == "ks_07" and recs[0]["event_index"] == 1


def test_style_and_effect_filters_can_be_disabled():
    events = [ev(0, 1.0, 2.0, "BAKERY", style="Sign"), ev(1, 2.0, 3.0, "Scroll", effect="Banner;10")]
    assert extract_lines(events)[0] == []
    lines, _ = extract_lines(events, ExtractConfig(skip_style_pattern="", skip_nonempty_effect=False))
    assert [ln.text for ln in lines] == ["BAKERY", "Scroll"]


def test_run_extraction_writes_files(tmp_path: Path):
    srt = tmp_path / "ks_07_EN.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi there.\n\n2\n00:00:03,000 --> 00:00:04,000\n<i>Bye.</i>\n",
                   encoding="utf-8")
    manifest = {"files": [{"id": "ks_07", "path": str(srt)},
                          {"id": "broken", "path": str(tmp_path / "missing.srt")}]}
    summary = run_extraction(manifest, tmp_path / "extracted")
    assert summary["total_lines"] == 2 and summary["movies"]["ks_07"]["extracted"] == 2
    assert [f["id"] for f in summary["failed"]] == ["broken"]
    rows = [json.loads(x) for x in (tmp_path / "extracted" / "ks_07.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["text"] for r in rows] == ["Hi there.", "Bye."]
    assert rows[1]["has_tags"] is True
    assert (tmp_path / "extracted" / "extract_summary.json").exists()
