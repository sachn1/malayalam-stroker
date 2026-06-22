"""Tests for malayalam_stroker.strokes, run offline against the bundled
test fixture font (tests/fixtures/Manjari-Regular.ttf, SIL OFL — see
tests/fixtures/OFL.txt). This fixture exists purely for deterministic
testing; the package itself does not bundle or require this specific
font.
"""

import re
from pathlib import Path

import pytest

from malayalam_stroker import shape_word
from malayalam_stroker.strokes import MAX_WORD_LENGTH

FONT = str(Path(__file__).parent / "fixtures" / "Manjari-Regular.ttf")

# Conjunct (ന്ദ), triple cluster (സ്ത്ര), classical ligature (ക്ഷ).
CONJUNCT_WORDS = ["നന്ദി", "സ്ത്രീ", "ക്ഷമിക്കണം"]


def test_returns_expected_keys() -> None:
    """The exact values are tested in other tests; here we just check the overall structure."""
    trace = shape_word("നന്ദി", FONT)
    assert set(trace.keys()) == {"unitsPerEm", "ascent", "descent", "totalAdvance", "glyphs"}


def test_produces_at_least_one_glyph() -> None:
    """Ensure that shaping a word produces at least one glyph."""
    trace = shape_word("നന്ദി", FONT)
    assert len(trace["glyphs"]) >= 1


@pytest.mark.parametrize("word", CONJUNCT_WORDS)
def test_conjuncts_collapse_to_fewer_glyphs_than_codepoints(word: str) -> None:
    """Ensure that conjuncts collapse to fewer glyphs than codepoints."""
    trace = shape_word(word, FONT)
    assert len(trace["glyphs"]) < len(word), (
        f"{word!r} shaped to {len(trace['glyphs'])} glyphs, "
        f"expected fewer than its {len(word)} codepoints (no conjunct collapse?)"
    )


@pytest.mark.parametrize("word", [*CONJUNCT_WORDS, "മലയാളം", "ആലയം", "സ്നേഹം"])
def test_no_missing_glyphs(word: str) -> None:
    """Ensure that shaping a word does not produce missing glyphs."""
    trace = shape_word(word, FONT)
    names = [g["glyphName"] for g in trace["glyphs"]]
    assert all(not n.startswith(".notdef") for n in names), (word, names)


def test_paths_are_well_formed_svg_commands() -> None:
    """Ensure that glyph paths are well-formed SVG commands."""
    trace = shape_word("മലയാളം", FONT)
    for g in trace["glyphs"]:
        d = g["d"]
        assert d, "empty path data"
        assert d[0] == "M", f"path does not start with moveto: {d[:20]!r}"
        commands = re.findall(r"[MLHVCSQTAZ]", d, re.IGNORECASE)
        assert commands


def test_glyphs_ordered_left_to_right() -> None:
    """Ensure that glyphs are ordered from left to right."""
    trace = shape_word("മലയാളം", FONT)
    xs = [g["x"] for g in trace["glyphs"]]
    assert xs == sorted(xs)


def test_result_is_cached() -> None:
    """Ensure that shaping the same word multiple times returns the cached result."""
    a = shape_word("നന്ദി", FONT)
    b = shape_word("നന്ദി", FONT)
    assert a is b


def test_rejects_empty_string() -> None:
    """Ensure that shaping an empty string raises an exception."""
    with pytest.raises(ValueError):
        shape_word("", FONT)


def test_rejects_overlong_input() -> None:
    """Ensure that shaping a word longer than MAX_WORD_LENGTH raises an exception."""
    with pytest.raises(ValueError):
        shape_word("a" * (MAX_WORD_LENGTH + 1), FONT)


def test_rejects_missing_font() -> None:
    """Ensure that shaping a word with a missing font raises an exception."""
    with pytest.raises(Exception):  # fontTools/OS error, not swallowed
        shape_word("test", "/nonexistent/font.ttf")


def test_works_with_non_malayalam_text() -> None:
    """The package is script-agnostic by design — anything HarfBuzz +
    the font can shape should work, not just Malayalam.
    """
    trace = shape_word("hello", FONT)
    assert len(trace["glyphs"]) == 5
