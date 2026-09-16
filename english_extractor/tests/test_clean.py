from __future__ import annotations

from pathlib import Path

from english_extractor.dataset.clean import CleanConfig, classify_line, clean_records, run_clean, write_jsonl


def test_clean_line():
    assert classify_line("Where are you going?") == ("clean", [])


def test_empty_and_punctuation_only():
    assert classify_line("") == ("rejected", ["empty_text"])
    assert classify_line("   ") == ("rejected", ["empty_text"])
    s, r = classify_line("...")
    assert s == "rejected" and "punctuation_only" in r


def test_mongolian_line_rejected():
    s, r = classify_line("Би маргааш өглөө буцаж ирнэ.")
    assert s == "rejected" and "cyrillic_text" in r
    assert classify_line("Do you like the new iPhone Pro Max?")[0] == "clean"


def test_corruption_markers():
    s, r = classify_line("Hello th�re my friend")
    assert s == "rejected" and "replacement_char" in r
    s, r = classify_line("Сайн уу".encode("utf-8").decode("latin-1"))   # UTF-8 bytes read as Latin-1
    assert s == "rejected" and "mojibake" in r
    s, r = classify_line("Hello\x07 there")
    assert s == "rejected" and "control_chars" in r


def test_residual_tags_html_credits():
    s, r = classify_line("{\\i1}Hello{\\i0} there")
    assert s == "rejected" and "residual_ass_tags" in r
    s, r = classify_line("Hello\\Nthere")
    assert s == "rejected" and "residual_ass_tags" in r
    s, r = classify_line("<i>Hello</i> there")
    assert s == "rejected" and "html_tags" in r
    s, r = classify_line("Subtitles by John")
    assert s == "rejected" and "credit_or_url" in r
    s, r = classify_line("Visit www.example.com now")
    assert s == "rejected" and "credit_or_url" in r


def test_very_long_is_review():
    s, r = classify_line("word " * 150)
    assert s == "review" and r == ["very_long"]


def test_caption_rule():
    s, r = classify_line("(The 100 Girlfriends Who Really, Really, Really Love You)")
    assert s == "review" and r == ["caption"]
    s, r = classify_line("[Room No. 2]")
    assert s == "review" and "caption" in r
    s, r = classify_line("AROUND 10 YEARS AGO SOMEWHERE IN THE U.S.A.")
    assert s == "review" and "caption" in r
    assert classify_line("NO!")[0] == "clean"                       # too few words
    cfg = CleanConfig(flag_captions=False)
    assert classify_line("(The 100 Girlfriends Who Really Love You)", cfg)[0] == "clean"


def test_dedupe_exact_and_near():
    recs = [
        {"text": "Hello.", "movie_id": "a"},
        {"text": "Hello.", "movie_id": "b"},
        {"text": "hello!", "movie_id": "c"},
        {"text": "Goodbye.", "movie_id": "c"},
    ]
    res = clean_records(recs)
    assert [r["movie_id"] for r in res.clean] == ["a", "c"]
    assert [r["reasons"] for r in res.rejected] == [["duplicate_exact"], ["duplicate_near"]]
    assert res.reason_counts["duplicate_exact"] == 1
    assert res.total == 4
    assert len(clean_records(recs, CleanConfig(dedupe=False)).clean) == 4


def test_run_clean_writes_outputs(tmp_path: Path):
    extracted = tmp_path / "extracted"
    write_jsonl([
        {"text": "Hello.", "movie_id": "a"},
        {"text": "Сайн уу.", "movie_id": "a"},
        {"text": "(ROOM NO. 2)", "movie_id": "a"},
    ], extracted / "a.jsonl")
    (extracted / "extract_summary.json").write_text("{}", encoding="utf-8")   # non-jsonl files are ignored
    res = run_clean(extracted, tmp_path / "cleaned", tmp_path / "reports" / "cleaning_report.md")
    assert (len(res.clean), len(res.review), len(res.rejected)) == (1, 1, 1)
    assert (tmp_path / "cleaned" / "clean.jsonl").read_text(encoding="utf-8").count("\n") == 1
    report = (tmp_path / "reports" / "cleaning_report.md").read_text(encoding="utf-8")
    assert "cyrillic_text" in report and "caption" in report
