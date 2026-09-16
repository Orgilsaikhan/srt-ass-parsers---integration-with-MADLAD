"""Tests for english_extractor.ass.tags."""
from __future__ import annotations

import pytest

from english_extractor.ass import has_tags, is_translatable, protect, restore, strip_tags, validate_tags

PLAN_TAGS = [r"{\i1}", r"{\i0}", r"{\b1}", r"{\b0}", r"{\pos(100,200)}", r"{\an8}", r"{\fs30}", r"{\c&HFFFFFF&}", r"{\fad(500,500)}"]


@pytest.mark.parametrize("tag", PLAN_TAGS)
def test_each_plan_tag_is_protected_and_restored(tag: str) -> None:
    text = f"{tag}Hello, John!"
    p = protect(text)
    assert p.plain == "Hello, John!"
    assert p.tags == [tag]
    assert has_tags(text)
    assert restore(p, "Сайн уу, Жон!") == f"{tag}Сайн уу, Жон!"
    assert validate_tags(text, restore(p, "Сайн уу, Жон!")) == []


def test_plan_example_italic_pair() -> None:
    p = protect(r"{\i1}Hello, John!{\i0}")
    assert p.plain == "Hello, John!"
    assert p.tags == [r"{\i1}", r"{\i0}"]
    assert restore(p, "Сайн уу, Жон!") == r"{\i1}Сайн уу, Жон!{\i0}"


def test_complex_inline_example() -> None:
    text = r"{\pos(100,200)}Hello{\i1}there{\i0}\Nworld"
    p = protect(text)
    assert p.plain == "Hellothere\nworld"
    assert p.tags == [r"{\pos(100,200)}", r"{\i1}", r"{\i0}"]
    assert not p.karaoke and not p.drawing
    out = restore(p, "Сайн уу тэнд\nдэлхий")
    assert out.startswith(r"{\pos(100,200)}")
    assert out.endswith(r"\Nдэлхий")
    assert "\n" not in out
    assert out.index(r"{\i1}") < out.index(r"{\i0}")
    assert validate_tags(text, out) == []
    # identity restore keeps the tags in the same places
    assert restore(p, p.plain) == text


def test_inline_tags_placed_proportionally_and_snapped_to_word_boundary() -> None:
    p = protect(r"That's {\b1}my{\b0} seat.")
    assert p.plain == "That's my seat."
    out = restore(p, "Энэ бол миний суудал.")
    # tags land on whitespace boundaries, in order, not inside a word
    assert out.count("{") == 2
    i1, i0 = out.index(r"{\b1}"), out.index(r"{\b0}")
    assert i1 < i0
    plain_out = out.replace(r"{\b1}", "").replace(r"{\b0}", "")
    assert plain_out == "Энэ бол миний суудал."
    for i in (i1, i0):
        assert out[i - 1] == " " or out[i + 5] == " " or out[i + 5] == "{"


def test_leading_and_trailing_tags_stay_put_regardless_of_length() -> None:
    p = protect(r"{\an8\fad(500,500)}Tokyo Station{\fs30}")
    assert restore(p, "Т") == r"{\an8\fad(500,500)}Т{\fs30}"
    assert restore(p, "Токиогийн төв галт тэрэгний буудал") == r"{\an8\fad(500,500)}Токиогийн төв галт тэрэгний буудал{\fs30}"


def test_hard_breaks_and_hard_space() -> None:
    p = protect(r"I told you already.\NWe're not going.")
    assert p.plain == "I told you already.\nWe're not going."
    assert restore(p, "Хэлсэн.\nЯвахгүй.") == r"Хэлсэн.\NЯвахгүй."
    # soft break \n also becomes a newline in plain, and is emitted as \N on restore
    assert strip_tags(r"a\nb") == "a\nb"
    assert restore(protect(r"a\nb"), "а\nб") == r"а\Nб"
    # \h -> normal space
    assert strip_tags(r"Mitsuha...\hAre you okay?") == "Mitsuha... Are you okay?"


def test_drawing_mode_excluded_and_kept_verbatim() -> None:
    text = r"{\an7\pos(0,0)\p1\c&H000000&\alpha&H60&}m 0 0 l 1920 0 1920 140 0 140{\p0}"
    p = protect(text)
    assert p.plain == ""
    assert p.drawing
    assert not is_translatable(text)
    assert restore(p, "") == text
    assert restore(p, p.plain) == text
    assert validate_tags(text, text) == []
    assert validate_tags(text, r"{\an7\pos(0,0)\p1\c&H000000&\alpha&H60&}m 0 0{\p0}") == ["drawing commands changed or lost"]


def test_drawing_followed_by_text() -> None:
    text = r"{\p1}m 0 0 l 10 0 10 10{\p0}Label"
    p = protect(text)
    assert p.plain == "Label"
    assert restore(p, "Шошго") == r"{\p1}m 0 0 l 10 0 10 10{\p0}Шошго"
    # \p4 (scaled drawing) also starts drawing mode
    assert strip_tags(r"{\p4}m 0 0 l 1 1{\p0}") == ""


def test_karaoke_detection() -> None:
    text = r"{\fad(200,200)}{\k25}Ki{\k30}mi {\k40}no {\k35}na{\k20}wa"
    p = protect(text)
    assert p.karaoke
    assert p.plain == "Kimi no nawa"
    assert not is_translatable(text)
    for tag in (r"{\K30}", r"{\kf30}", r"{\ko30}"):
        assert protect(tag + "la").karaoke
    # \kerning-like or unrelated tags do not trigger it
    assert not protect(r"{\fsp2}la").karaoke
    assert not protect(r"{\blur2}la").karaoke


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", False),
        ("   ", False),
        (r"\N", False),
        (r"\N\N", False),
        (r"{\i1}{\i0}", False),
        (r"{\p1}m 0 0 l 1 1{\p0}", False),
        ("123", False),
        ("2013", False),
        ("...", False),
        ("!?", False),
        (r"{\an8}Coming!", True),
        ("Hello", True),
        ("Сайн уу", True),
        (r"{\k20}Hel{\k30}lo", False),
        ("a", True),
    ],
)
def test_is_translatable(text: str, expected: bool) -> None:
    assert is_translatable(text) is expected


def test_has_tags() -> None:
    assert has_tags(r"{\i1}x")
    assert has_tags("{comment}x")
    assert not has_tags("plain")
    assert not has_tags(r"\N")


def test_unbalanced_braces_treated_as_text() -> None:
    p = protect(r"{\i1 broken")
    assert p.plain == r"{\i1 broken"
    assert p.tags == []
    p = protect("close} first")
    assert p.plain == "close} first"
    # Nested-looking braces: block runs from "{" to the next "}"
    p = protect(r"{\i1{\b1}}x")
    assert p.tags == [r"{\i1{\b1}"]
    assert p.plain == "}x"


def test_validate_tags_reports_problems() -> None:
    assert validate_tags(r"{\i1}a{\i0}", r"{\i1}б") == ["missing tag {\\i0}"]
    assert validate_tags("a", r"{\i1}б") == ["unexpected tag {\\i1}"]
    issues = validate_tags(r"{\i1}a{\i0}", r"{\i1}б{\i0")
    assert "unbalanced braces in translated text" in issues
    assert validate_tags(r"{\i1}a{\i0}", r"{\i0}б{\i1}") == ["override tags reordered"]
    assert validate_tags(r"{\i1}a{\i1}b", r"{\i1}б") == ["missing tag {\\i1}"]
    assert validate_tags(r"{\c&H00FFFF&}Warning!{\c} Get down!", r"{\c&H00FFFF&}Анхаар!{\c} Доош бууг!") == []


def test_restore_with_empty_translation_keeps_tags() -> None:
    p = protect(r"{\i1}Hello{\i0}")
    assert restore(p, "") == r"{\i1}{\i0}"


def test_tags_with_inline_comment_blocks() -> None:
    text = r"{Note: sign}{\an8}Exit"
    p = protect(text)
    assert p.plain == "Exit"
    assert restore(p, "Гарц") == r"{Note: sign}{\an8}Гарц"


@pytest.mark.parametrize(
    "text",
    [
        r"{\i1}Hello, John!{\i0}",
        r"{\pos(100,200)}Hello{\i1}there{\i0}\Nworld",
        r"Plain, with commas, and {braces}",
        r"{\fad(500,500)\an8}Sign text",
        r"{\c&H00FFFF&}Warning!{\c} Get down!",
        r"{\p1}m 0 0 l 1 1{\p0}",
        r"a\Nb\Nc",
    ],
)
def test_identity_round_trip(text: str) -> None:
    p = protect(text)
    assert restore(p, p.plain) == text
