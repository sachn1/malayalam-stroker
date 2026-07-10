"""Tests for malayalam_stroker.stroke_compose — per-glyph stroke composition.

Deliberately script-agnostic: fixtures use synthetic single-letter "clusters"
(A, B, M) shaped like glyph-data.json entries, never real Malayalam clusters.
The composition algorithm only cares about character/glyph counts and x/y
offsets — it has no Malayalam-specific logic, so a new script's stroke
pipeline should never need to touch this file or its tests.
"""

from __future__ import annotations

from malayalam_stroker.stroke_compose import (
    _char_dx,
    compose_all,
    compose_per_glyph,
    find_matching_standalone_glyph_x,
    offset_svg_path,
)

# "M" mimics a mark like anusvara: 2 standalone glyphs (placeholder at x=0,
# real content at x=30) — see find_matching_standalone_glyph_x's docstring.
CLUSTERS = {
    "A": {"glyphs": [{"x": 0.0, "y": 0.0}], "advance": 100.0},
    "B": {"glyphs": [{"x": 0.0, "y": 0.0}], "advance": 100.0},
    "M": {"glyphs": [{"x": 0.0, "y": 0.0}, {"x": 30.0, "y": 0.0}], "advance": 100.0},
    "AB": {"glyphs": [{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.0}], "advance": 200.0},
    "AM": {"glyphs": [{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.0}], "advance": 200.0},
    "AM3": {
        "glyphs": [{"x": 0.0, "y": 0.0}, {"x": 50.0, "y": 0.0}, {"x": 100.0, "y": 0.0}],
        "advance": 200.0,
    },
}
STROKE_DATA = {
    "A": {"strokes": [{"d": "M5 5 L15 5"}]},
    "B": {"strokes": [{"d": "M2 2 L12 2"}]},
    "M": {"strokes": [{"d": "M30 0 L35 0"}]},
}
NO_MARKS: dict = {}


class TestOffsetSvgPath:
    """offset_svg_path: shift all absolute coordinates in an SVG path."""

    def test_zero_offset_returns_input_unchanged(self) -> None:
        """Ensure that a (0, 0) offset returns the exact same string, unreformatted."""
        d = "M5 5 L15 5"
        assert offset_svg_path(d, 0, 0) is d

    def test_shifts_moveto_and_lineto_coordinates(self) -> None:
        """Ensure that M/L coordinate pairs are both shifted by (dx, dy)."""
        result = offset_svg_path("M0 0 L10 10", 100, 5)
        assert result == "M 100.0 5.0 L 110.0 15.0"

    def test_shifts_horizontal_and_vertical_commands(self) -> None:
        """Ensure that H/V single-axis commands are shifted on their own axis only."""
        result = offset_svg_path("M0 0 H10 V20", 5, 3)
        assert result == "M 5.0 3.0 H 15.0 V 23.0"

    def test_shifts_cubic_bezier_control_points(self) -> None:
        """Ensure that all three coordinate pairs of a C command are shifted."""
        result = offset_svg_path("M0 0 C1 1 2 2 3 3", 10, 10)
        assert result == "M 10.0 10.0 C 11.0 11.0 12.0 12.0 13.0 13.0"


class TestFindMatchingStandaloneGlyphX:
    """find_matching_standalone_glyph_x: content-glyph x in a standalone entry."""

    def test_single_glyph_standalone_returns_its_own_x(self) -> None:
        """Ensure that a plain single-glyph character returns that glyph's x."""
        assert find_matching_standalone_glyph_x("A", CLUSTERS) == 0.0

    def test_multi_glyph_standalone_returns_last_glyphs_x(self) -> None:
        """Ensure that a mark-like 2-glyph standalone returns the *last* (content) glyph's x."""
        assert find_matching_standalone_glyph_x("M", CLUSTERS) == 30.0

    def test_unknown_character_returns_zero(self) -> None:
        """Ensure that a character with no clusters entry at all returns 0.0."""
        assert find_matching_standalone_glyph_x("Z", CLUSTERS) == 0.0


class TestCharDx:
    """_char_dx: how far to shift a character's own stroke to a target x."""

    def test_simple_character_uses_target_directly(self) -> None:
        """Ensure that a single-glyph character (standalone x=0) offsets by the raw target."""
        assert _char_dx("A", 0.0, CLUSTERS) == 0.0
        assert _char_dx("A", 250.0, CLUSTERS) == 250.0

    def test_mark_like_character_corrects_for_its_own_anchor(self) -> None:
        """Ensure that a 2-glyph standalone character's offset subtracts its content anchor."""
        assert _char_dx("M", 100.0, CLUSTERS) == 70.0  # 100 - 30 (M's own content x)

    def test_unknown_character_falls_back_to_target(self) -> None:
        """Ensure that a character absent from clusters just returns the raw target."""
        assert _char_dx("Z", 42.0, CLUSTERS) == 42.0


class TestComposePerGlyph:
    """compose_per_glyph: compose a cluster's stroke from its own characters' strokes."""

    def test_composes_two_simple_characters(self) -> None:
        """Ensure that two single-glyph characters compose into two offset strokes."""
        result = compose_per_glyph("AB", CLUSTERS["AB"], STROKE_DATA, CLUSTERS, NO_MARKS)
        assert result == [
            {"d": "M5 5 L15 5"},
            {"d": "M 102.0 2.0 L 112.0 2.0"},
        ]

    def test_composes_with_mark_anchor_correction(self) -> None:
        """Ensure that a mark-like component's own anchor is correctly subtracted out."""
        result = compose_per_glyph("AM", CLUSTERS["AM"], STROKE_DATA, CLUSTERS, NO_MARKS)
        assert result == [
            {"d": "M5 5 L15 5"},
            {"d": "M 100.0 0.0 L 105.0 0.0"},
        ]

    def test_returns_none_for_single_character_cluster(self) -> None:
        """Ensure that a 1-character cluster key can't be decomposed this way."""
        assert compose_per_glyph("A", CLUSTERS["A"], STROKE_DATA, CLUSTERS, NO_MARKS) is None

    def test_returns_none_when_glyph_count_is_below_two(self) -> None:
        """Ensure that a cluster resolving to fewer than 2 glyphs is rejected."""
        single_glyph_cluster = {"glyphs": [{"x": 0.0, "y": 0.0}], "advance": 100.0}
        result = compose_per_glyph("AB", single_glyph_cluster, STROKE_DATA, CLUSTERS, NO_MARKS)
        assert result is None

    def test_returns_none_when_char_count_and_glyph_count_mismatch(self) -> None:
        """Ensure that a cluster where chars != glyphs is rejected (mark-attachment shape)."""
        result = compose_per_glyph("AM3", CLUSTERS["AM3"], STROKE_DATA, CLUSTERS, NO_MARKS)
        assert result is None

    def test_returns_none_when_a_component_has_no_stroke(self) -> None:
        """Ensure that a missing component stroke aborts composition entirely."""
        partial_stroke_data = {"A": STROKE_DATA["A"]}  # B is missing
        result = compose_per_glyph("AB", CLUSTERS["AB"], partial_stroke_data, CLUSTERS, NO_MARKS)
        assert result is None

    def test_returns_none_when_a_character_is_a_prefix_mark(self) -> None:
        """Ensure a prefix-type mark's glyph reordering isn't naively lockstep-mapped.

        Regression test for a real bug: for cluster "ടെ" (2 chars, 2
        glyphs), HarfBuzz visually reorders the prefix vowel sign's glyph
        *before* the consonant's own glyph, so glyph index no longer
        matches character index — composing it as if they still matched
        put both characters' strokes on top of each other at the mark's
        position, leaving the base's own slot empty.
        """
        prefix_marks = {"B": {"prefix": [{"d": "M0 0", "x": 0, "y": 0}]}}
        result = compose_per_glyph("AB", CLUSTERS["AB"], STROKE_DATA, CLUSTERS, prefix_marks)
        assert result is None

    def test_suffix_mark_is_unaffected_by_the_prefix_check(self) -> None:
        """Ensure a character with an empty-prefix (suffix-only) mark composes normally."""
        suffix_marks = {"B": {"prefix": [], "suffix": [{"d": "M0 0", "x": 0, "y": 0}]}}
        result = compose_per_glyph("AB", CLUSTERS["AB"], STROKE_DATA, CLUSTERS, suffix_marks)
        assert result is not None


class TestComposeAll:
    """compose_all: compose strokes for every glyph-data cluster still missing one."""

    def test_composes_all_composable_clusters(self) -> None:
        """Ensure that every composable cluster gets a generated stroke."""
        glyph_data = {"clusters": CLUSTERS}
        out, generated, skipped = compose_all(glyph_data, STROKE_DATA)
        assert generated == 2  # AB and AM
        assert skipped == 1  # AM3 (char/glyph mismatch)
        # AM3 failed to compose, so it's never added to the output at all.
        assert set(out) == {"A", "B", "M", "AB", "AM"}

    def test_already_authored_clusters_are_left_untouched(self) -> None:
        """Ensure that a cluster already having strokes is never recomposed."""
        glyph_data = {"clusters": CLUSTERS}
        out, _, _ = compose_all(glyph_data, STROKE_DATA)
        assert out["A"] == STROKE_DATA["A"]

    def test_newly_composed_clusters_are_added_to_the_output(self) -> None:
        """Ensure that a newly-composed cluster's strokes appear in the output dict."""
        glyph_data = {"clusters": CLUSTERS}
        out, _, _ = compose_all(glyph_data, STROKE_DATA)
        assert out["AB"]["strokes"] == [
            {"d": "M5 5 L15 5"},
            {"d": "M 102.0 2.0 L 112.0 2.0"},
        ]
