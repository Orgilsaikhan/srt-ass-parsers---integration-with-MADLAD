from __future__ import annotations

from pathlib import Path

import pytest

from english_extractor.dataset.discover import (build_manifest, language_from_content, language_from_filename,
                                                load_manifest, strip_language_token, write_manifest)

HEADER = "[Script Info]\nTitle: t\nScriptType: v4.00+\n\n[Events]\n" \
         "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"


def ass(lines: list[str]) -> str:
    body = "".join(f"Dialogue: 0,0:00:{i:02d}.00,0:00:{i + 1:02d}.50,Default,,0,0,0,,{t}\n"
                   for i, t in enumerate(lines))
    return HEADER + body


EN_TEXT = ass(["Hello there.", "How are you?", "I'm fine, thanks."])
MN_TEXT = ass(["Сайн уу.", "Сайн байна уу?", "Би сайн байна, баярлалаа."])
SRT_EN = "1\r\n00:00:01,000 --> 00:00:02,500\r\nHello there.\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,500\r\n<i>How are you?</i>\r\n\r\n"


def test_language_from_filename():
    assert language_from_filename("english.ass") == "en"
    assert language_from_filename("Movie_MN.ass") == "mn"
    assert language_from_filename("movie.en.ass") == "en"
    assert language_from_filename("Movie (2020) mongolian.ass") == "mn"
    assert language_from_filename("Strength.ass") is None
    assert language_from_filename("movie_en_mn.ass") is None
    assert strip_language_token("Movie.2020.mn") == "movie_2020"
    assert strip_language_token("english") == ""


def test_language_from_content(tmp_path: Path):
    (tmp_path / "a.ass").write_text(EN_TEXT, encoding="utf-8")
    (tmp_path / "b.ass").write_text(MN_TEXT, encoding="utf-8")
    assert language_from_content(tmp_path / "a.ass") == "en"
    assert language_from_content(tmp_path / "b.ass") == "mn"


def test_language_folder_layout_keeps_only_english(tmp_path: Path):
    raw = tmp_path / "Raw Files"
    (raw / "English").mkdir(parents=True)
    (raw / "Mongolian").mkdir()
    (raw / "English" / "yani_07_EN.srt").write_text(SRT_EN, encoding="utf-8")
    (raw / "English" / "hanaori_03_EN.ass").write_text(EN_TEXT, encoding="utf-8")
    (raw / "English" / "S101 - mislabeled.ass").write_text(MN_TEXT, encoding="utf-8")   # Mongolian text in English/
    (raw / "Mongolian" / "yani_07_MN.ass").write_text(MN_TEXT, encoding="utf-8")
    (raw / "notes.srt").write_text("no cues here", encoding="utf-8")

    manifest = build_manifest(raw)
    by_id = {f["id"]: f for f in manifest.files}
    assert set(by_id) == {"yani_07", "hanaori_03"}
    assert by_id["yani_07"]["path"].endswith("yani_07_EN.srt") and len(by_id["yani_07"]["sha1"]) == 40
    skipped = {Path(s["path"]).name: s["reason"] for s in manifest.skipped}
    assert skipped == {"S101 - mislabeled.ass": "not_english", "yani_07_MN.ass": "not_english",
                       "notes.srt": "language_unknown"}


def test_duplicates_multiple_roots_and_unique_ids(tmp_path: Path):
    a = tmp_path / "Raw Files" / "English"
    b = tmp_path / "Unpaired" / "English"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "ks_07_EN.srt").write_text(SRT_EN, encoding="utf-8")
    (b / "ks_07 copy_EN.srt").write_text(SRT_EN, encoding="utf-8")                      # byte-identical copy
    (b / "ks_07_EN.srt").write_text(SRT_EN.replace("Hello", "Hi"), encoding="utf-8")   # same id, other content

    manifest = build_manifest([tmp_path / "Raw Files", tmp_path / "Unpaired"])
    assert [f["id"] for f in manifest.files] == ["ks_07", "ks_07_2"]
    assert manifest.files[0]["path"].startswith(str(tmp_path / "Raw Files"))
    assert len(manifest.duplicates) == 1 and manifest.duplicates[0]["duplicate_of"] == manifest.files[0]["path"]

    out = write_manifest(manifest, tmp_path / "out" / "files.json")
    assert load_manifest(out)["files"][0]["id"] == "ks_07"


def test_missing_root_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        build_manifest(tmp_path / "nope")
