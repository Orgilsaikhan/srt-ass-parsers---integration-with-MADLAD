from __future__ import annotations

from pathlib import Path

from english_extractor.ass.srt import convert_markup, parse_srt_file, parse_srt_string
from english_extractor.dataset.textutil import is_translatable, load_dialogues

SRT = (
    "﻿1\r\n00:00:11,030 --> 00:00:13,210\r\nThe Hardcore Group.   \r\n\r\n"
    "2\r\n00:00:13,210 --> 00:00:19,510\r\n<i>A conglomerate</i> run by\r\nSutou Iku &amp; friends.\r\n\r\n\r\n\r\n"
    "00:00:19,510 --> 00:00:23,740\r\nMissing index, <b>bold</b> <u>under</u> <font color=\"#fff\">font</font>\r\n\r\n"
    "abc\r\n00:00:23,740 --> 00:00:25,590\r\n{\\an8}(Room No. 2)\r\n\r\n"
    "5\r\n00:00:25,590 --> 00:00:26,550\r\n\r\n"
    "6\r\n00:00:26,830 --> 00:00:31,680\r\nGlued cue\r\n7\r\n00:00:31,680 --> 00:00:36,930\r\nNext one\r\n\r\n"
    "8\r\n00:00:31,680 --> 00:00:36,930\r\nNext one\r\n\r\n"
    "9\r\n00:00:35,000 --> 00:00:38,000\r\nOverlapping\r\n"
)


def test_parse_edge_cases():
    ass = parse_srt_string(SRT, title="t")
    ev = ass.dialogues
    texts = [e.text for e in ev]
    assert ev[0].start == "0:00:11.03" and ev[0].end == "0:00:13.21"
    assert texts[0] == "The Hardcore Group."                          # trailing whitespace stripped
    assert texts[1] == r"{\i1}A conglomerate{\i0} run by\NSutou Iku & friends."
    assert texts[2] == r"Missing index, {\b1}bold{\b0} {\u1}under{\u0} font"
    assert texts[3] == r"{\an8}(Room No. 2)"                          # ASS tag passed through
    assert texts[4] == "" and ev[4].start == "0:00:25.59"              # empty cue kept
    assert texts[5] == "Glued cue" and texts[6] == "Next one"          # glued index removed
    assert texts[7] == "Overlapping"                                   # duplicate cue 8 dropped, overlap kept
    assert [e.index for e in ev] == list(range(8))
    assert all(e.kind == "Dialogue" and e.style == "Default" for e in ev)
    assert ass.bom and ass.newline == "\r\n"


def test_empty_cue_not_translatable():
    ass = parse_srt_string("1\n00:00:01,000 --> 00:00:02,000\n\n2\n00:00:02,000 --> 00:00:03,000\nHi\n")
    assert [e.text for e in ass.dialogues] == ["", "Hi"]
    assert [is_translatable(e.text) for e in ass.dialogues] == [False, True]


def test_timestamp_rounding_and_lf():
    ass = parse_srt_string("1\n00:01:23,406 --> 01:02:03,995\nx\n")
    assert ass.dialogues[0].start == "0:01:23.41"
    assert ass.dialogues[0].end == "1:02:04.00"


def test_convert_markup():
    assert convert_markup("<I>a</I><br>b &lt;i&gt; &quot;q&quot;") == r"{\i1}a{\i0}\Nb <i> " + '"q"'


def test_load_dialogues_reads_srt(tmp_path: Path):
    src = tmp_path / "ep.srt"
    src.write_text(SRT, encoding="utf-8")
    assert parse_srt_file(src).path == str(src)
    assert [e.text for e in load_dialogues(src)] == [e.text for e in parse_srt_string(SRT).dialogues]
