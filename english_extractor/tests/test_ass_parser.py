"""Tests for english_extractor.ass.parser."""
from __future__ import annotations

from pathlib import Path

import pytest

from english_extractor.ass import DEFAULT_EVENT_FORMAT, EVENT_PLACEHOLDER, parse_bytes, parse_file, parse_string, parse_styles
from english_extractor.ass.parser import detect_encoding, parse_event_line

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_FILES = sorted(FIXTURES.glob("*.ass"))


def test_fixtures_exist() -> None:
    assert len(FIXTURE_FILES) >= 5


def test_plan_example_dialogue() -> None:
    ass = parse_string("[Events]\nDialogue: 0,0:01:23.40,0:01:25.80,Default,John,0,0,0,,Hello!\n")
    assert len(ass.events) == 1
    ev = ass.events[0]
    assert ev.kind == "Dialogue"
    assert ev.layer == 0
    assert ev.start == "0:01:23.40"
    assert ev.end == "0:01:25.80"
    assert ev.style == "Default"
    assert ev.name == "John"
    assert (ev.margin_l, ev.margin_r, ev.margin_v) == ("0", "0", "0")
    assert ev.effect == ""
    assert ev.text == "Hello!"
    assert ev.is_dialogue
    assert ev.start_seconds == pytest.approx(83.40)


def test_minimal_fixture_sections_and_events() -> None:
    ass = parse_file(FIXTURES / "minimal_aegisub.ass")
    assert [s.name for s in ass.sections] == ["Script Info", "Aegisub Project Garbage", "V4+ Styles", "Events"]
    assert ass.encoding == "utf-8-sig" and ass.bom is True and ass.newline == "\r\n"
    assert ass.event_format == DEFAULT_EVENT_FORMAT
    assert len(ass.events) == 6
    assert len(ass.dialogues) == 5
    assert ass.events[4].kind == "Comment"
    assert ass.events[5].text == ""  # empty text still parsed
    assert ass.path == str(FIXTURES / "minimal_aegisub.ass")


def test_events_section_keeps_non_event_lines_with_placeholders() -> None:
    ass = parse_file(FIXTURES / "minimal_aegisub.ass")
    ev_section = ass.section("events")  # case-insensitive lookup
    assert ev_section is not None
    assert ev_section.lines[0].startswith("Format:")
    assert ev_section.lines.count(EVENT_PLACEHOLDER) == len(ass.events)
    assert ev_section.lines[-1] == ""  # file ends with a newline


def test_event_index_is_line_position_within_section() -> None:
    ass = parse_file(FIXTURES / "minimal_aegisub.ass")
    assert ass.events[0].index == 1  # line 0 is the Format line
    assert [e.index for e in ass.events] == [1, 2, 3, 4, 5, 6]


def test_text_with_commas_only_splits_on_first_nine_commas() -> None:
    ass = parse_file(FIXTURES / "anime_heavy.ass")
    ev = next(e for e in ass.events if e.name == "Tsukasa")
    assert ev.text == "Well, I mean, it's not like I care, you know."
    taki = [e for e in ass.events if e.name == "Taki"]
    assert any("someone, something, for a long time." in e.text for e in taki)


def test_custom_events_format_populates_extra() -> None:
    ass = parse_file(FIXTURES / "custom_format.ass")
    assert ass.event_format[0] == "Marked"
    assert len(ass.event_format) == 11
    ev = ass.events[0]
    assert ev.extra == {"Marked": "Marked=0"}
    assert ev.layer == 0
    assert ev.margin_l == "0000"  # margins kept as strings
    assert ev.text == "Where were you last night?"
    banner = ass.events[2]
    assert banner.layer == 1
    assert banner.effect == "Banner;10;0;20"
    assert banner.text.startswith("BREAKING NEWS")


def test_reordered_format_columns() -> None:
    text = (
        "[Events]\n"
        "Format: Start, End, Layer, Text, Style\n"  # Text not last; still handled
        "Dialogue: 0:00:01.00,0:00:02.00,3,Hi there,Default\n"
    )
    ass = parse_string(text)
    ev = ass.events[0]
    assert (ev.start, ev.end, ev.layer, ev.text, ev.style) == ("0:00:01.00", "0:00:02.00", 3, "Hi there", "Default")


def test_unknown_section_kept_verbatim_and_preamble() -> None:
    ass = parse_file(FIXTURES / "lf_nobom.ass")
    assert ass.encoding == "utf-8" and ass.bom is False and ass.newline == "\n"
    assert ass.sections[0].name == ""
    assert ass.sections[0].lines == ["; exported by a non-Aegisub tool, no BOM"]
    custom = ass.section("Custom Metadata")
    assert custom is not None
    assert custom.lines[1] == "Notes: keep this section verbatim, the parser does not know it"
    # trailing whitespace preserved in raw lines and in event text
    assert ass.section("Script Info").lines[0] == "Title: LF file  "
    assert ass.events[1].text.endswith("rain.   ")
    # blank line inside [Events] preserved as a raw line
    assert "" in ass.section("Events").lines[:-1] or ass.section("Events").lines.count("") >= 1


def test_missing_final_newline() -> None:
    ass = parse_file(FIXTURES / "lf_nobom.ass")
    assert ass.section("Events").lines[-1] == EVENT_PLACEHOLDER  # no trailing "" line
    ass2 = parse_file(FIXTURES / "minimal_aegisub.ass")
    assert ass2.section("Events").lines[-1] == ""


def test_comment_lines_and_blank_lines_inside_events() -> None:
    text = "[Events]\r\n; a comment\r\n\r\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hi\r\n"
    ass = parse_string(text)
    assert ass.section("Events").lines == ["; a comment", "", EVENT_PLACEHOLDER, ""]
    assert ass.newline == "\r\n"


def test_other_event_kinds() -> None:
    text = (
        "[Events]\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hi\n"
        "Comment: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,note\n"
        "Picture: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,logo.png\n"
        "Sound: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,ding.wav\n"
        "Movie: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,clip.avi\n"
        "Command: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,SSA:Pause\n"
        "Unknown: something that is not an event\n"
    )
    ass = parse_string(text)
    assert [e.kind for e in ass.events] == ["Dialogue", "Comment", "Picture", "Sound", "Movie", "Command"]
    assert "Unknown: something that is not an event" in ass.section("Events").lines


def test_section_names_case_insensitive() -> None:
    text = "[script info]\nTitle: t\n\n[v4+ styles]\n\n[EVENTS]\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,x\n"
    ass = parse_string(text)
    assert ass.section("Script Info") is not None
    assert ass.section("V4+ Styles") is not None
    assert len(ass.events) == 1
    assert ass.sections[2].name == "EVENTS"  # original spelling kept


@pytest.mark.parametrize("name", ["Script Info", "V4+ Styles", "V4 Styles", "V4+ Styles+", "Events", "Fonts", "Graphics", "Aegisub Project Garbage"])
def test_all_plan_section_names(name: str) -> None:
    ass = parse_string(f"[{name}]\nfoo: bar\n")
    assert ass.section(name) is not None
    assert ass.section(name).lines[0] == "foo: bar"


def test_bom_in_string_is_stripped() -> None:
    ass = parse_string("﻿[Script Info]\nTitle: x\n")
    assert ass.bom is True
    assert ass.sections[0].name == "Script Info"


@pytest.mark.parametrize(
    "data, codec, bom",
    [
        (b"\xef\xbb\xbf[Script Info]\r\n", "utf-8", True),
        (b"[Script Info]\r\n", "utf-8", False),
        ("[Script Info]\r\n".encode("utf-16-le"), "utf-16-le", False),  # no BOM: undetectable, falls to utf-8
        (b"\xff\xfe" + "[Script Info]\r\n".encode("utf-16-le"), "utf-16-le", True),
        (b"\xfe\xff" + "[Script Info]\r\n".encode("utf-16-be"), "utf-16-be", True),
        ("[Script Info]\r\nTitle: Привет\r\n".encode("cp1251"), "cp1251", False),
    ],
)
def test_detect_encoding(data: bytes, codec: str, bom: bool) -> None:
    detected_codec, detected_bom = detect_encoding(data)
    if codec == "utf-16-le" and not bom:
        assert detected_bom is False  # ASCII-range UTF-16 w/o BOM decodes as utf-8
    else:
        assert (detected_codec, detected_bom) == (codec, bom)


def test_parse_bytes_utf16_and_cp1251() -> None:
    text = "[Script Info]\r\nTitle: Сайн уу\r\n\r\n[Events]\r\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Сайн уу\r\n"
    ass = parse_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
    assert ass.encoding == "utf-16-le" and ass.bom is True
    assert ass.events[0].text == "Сайн уу"
    ass = parse_bytes(text.encode("cp1251"))
    assert ass.encoding == "cp1251" and ass.bom is False
    assert ass.events[0].text == "Сайн уу"


def test_invalid_utf8_falls_back_with_replacement_not_exception() -> None:
    data = b"[Events]\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,caf\xe9 \x98\n"
    ass = parse_bytes(data)
    assert len(ass.events) == 1
    assert ass.events[0].text.startswith("caf")


def test_parse_event_line_with_fewer_fields_than_format() -> None:
    ev = parse_event_line("Dialogue", "0,0:00:00.00,0:00:01.00", list(DEFAULT_EVENT_FORMAT))
    assert ev.style == "Default"  # default retained
    assert ev.text == ""


def test_parse_styles() -> None:
    ass = parse_file(FIXTURES / "anime_heavy.ass")
    styles = parse_styles(ass)
    assert set(styles) == {"Default", "Narration", "OP-Romaji", "OP-English", "Sign"}
    assert styles["Default"]["Fontname"] == "Open Sans Semibold"
    assert styles["Sign"]["Alignment"] == "5"
    assert styles["OP-Romaji"]["Encoding"] == "1"
    assert parse_styles(parse_string("[Script Info]\nTitle: x\n")) == {}


def test_anime_fixture_details() -> None:
    ass = parse_file(FIXTURES / "anime_heavy.ass")
    assert len(ass.events) == 22
    kinds = [e.kind for e in ass.events]
    assert kinds.count("Comment") == 3
    karaoke = [e for e in ass.events if e.effect == "karaoke"]
    assert len(karaoke) == 2 and "\\k" in karaoke[0].text
    assert any("\\p1" in e.text for e in ass.events)
    assert any(e.layer == 1 for e in ass.events)
    styles = {e.style for e in ass.events}
    assert {"Default", "Narration", "OP-Romaji", "OP-English", "Sign"} <= styles
