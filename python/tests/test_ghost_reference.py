"""Tests for malayalam_stroker.ghost_reference — ghost-outline-guided straightening.

Deliberately script-agnostic: the fixture "glyph" is a synthetic rectangle,
not a real letterform — straightening works from any filled outline's own
straight edges, with no Malayalam-specific logic. A new script's stroke
pipeline should never need to touch this file or its tests.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest

from malayalam_stroker.centering import make_dist_field
from malayalam_stroker.ghost_reference import (
    build_reference_segments,
    find_straight_segments,
    fit_line,
    match_reference,
    refine_stroke,
    sample_outline,
    sample_piece,
    split_path_into_pieces,
)

# A simple filled rectangle: x in [0, 300], y in [-300, 0]. Its four edges
# are exactly straight and axis-aligned (angles 0/90/180 mod 180).
RECT_GLYPH = [{"d": "M0 0 L300 0 L300 -300 L0 -300 Z", "x": 0.0, "y": 0.0}]


class TestSampleOutline:
    """sample_outline: sample points along a ghost outline's contours."""

    def test_one_contour_for_a_simple_rectangle(self) -> None:
        """Ensure that a single-subpath outline produces exactly one contour."""
        contours = sample_outline(RECT_GLYPH)
        assert len(contours) == 1

    def test_contour_has_many_sampled_points(self) -> None:
        """Ensure that the contour is densely sampled (not just the corners)."""
        contours = sample_outline(RECT_GLYPH)
        assert len(contours[0]) > 50

    def test_empty_glyph_list_gives_no_contours(self) -> None:
        """Ensure that an empty glyph list produces no contours."""
        assert sample_outline([]) == []

    def test_unparseable_path_is_skipped(self) -> None:
        """Ensure that an unparseable path string is silently skipped."""
        assert sample_outline([{"d": "garbage", "x": 0, "y": 0}]) == []


class TestFindStraightSegments:
    """find_straight_segments: locate straight edges within sampled contours."""

    def test_finds_all_four_edges_of_a_rectangle(self) -> None:
        """Ensure that all four straight edges of a rectangle are detected."""
        contours = sample_outline(RECT_GLYPH)
        segments = find_straight_segments(contours)
        assert len(segments) == 4

    def test_segment_lengths_are_plausible(self) -> None:
        """Ensure that detected segment lengths are close to the rectangle's 300-unit sides."""
        contours = sample_outline(RECT_GLYPH)
        segments = find_straight_segments(contours)
        assert all(250 < s["length"] <= 301 for s in segments)

    def test_tiny_contour_yields_no_segments(self) -> None:
        """Ensure that a contour with fewer than 5 points is skipped entirely."""
        tiny = [np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])]
        assert find_straight_segments(tiny) == []


class TestFitLine:
    """fit_line: PCA best-fit line through a point cloud."""

    def test_perfect_horizontal_line_has_zero_residual(self) -> None:
        """Ensure that points already on a horizontal line fit with zero residual."""
        pts = np.array([[x, 0.0] for x in range(0, 101, 10)])
        _, direction, residual, pmin, pmax = fit_line(pts)
        assert residual == pytest.approx(0.0, abs=1e-9)
        assert abs(direction[0]) == pytest.approx(1.0, abs=1e-9)
        assert pmax - pmin == pytest.approx(100.0)

    def test_perfect_vertical_line_direction(self) -> None:
        """Ensure that a vertical line's fitted direction is a vertical unit vector."""
        pts = np.array([[0.0, y] for y in range(0, 101, 10)])
        _, direction, residual, _, _ = fit_line(pts)
        assert residual == pytest.approx(0.0, abs=1e-9)
        assert abs(direction[1]) == pytest.approx(1.0, abs=1e-9)


class TestBuildReferenceSegments:
    """build_reference_segments: straight references in centerline space."""

    def test_finds_references_for_a_rectangle(self) -> None:
        """Ensure that a rectangle's straight edges yield centerline reference segments."""
        field = make_dist_field(RECT_GLYPH)
        refs = build_reference_segments(RECT_GLYPH, field)
        assert len(refs) == 4

    def test_reference_angles_are_axis_aligned(self) -> None:
        """Ensure that a rectangle's references have angles near 0 or 90 degrees."""
        field = make_dist_field(RECT_GLYPH)
        refs = build_reference_segments(RECT_GLYPH, field)
        for ref in refs:
            near_0_or_180 = min(ref["angle"], abs(180 - ref["angle"])) < 5.0
            near_90 = abs(ref["angle"] - 90) < 5.0
            assert near_0_or_180 or near_90

    def test_no_ink_tree_yields_no_references(self) -> None:
        """Ensure that an empty field (no ink) produces no reference segments."""
        empty_field = make_dist_field([])
        assert build_reference_segments(RECT_GLYPH, empty_field) == []


class TestSplitPathIntoPieces:
    """split_path_into_pieces: break a parsed path at sharp tangent breaks."""

    def test_l_shape_splits_into_two_pieces(self) -> None:
        """Ensure that an L-shaped path splits at its 90-degree corner."""
        import svgpathtools

        path = svgpathtools.parse_path("M0 0 L100 0 L100 100")
        pieces = split_path_into_pieces(path)
        assert len(pieces) == 2

    def test_straight_path_stays_one_piece(self) -> None:
        """Ensure that a path with no corners stays a single piece."""
        import svgpathtools

        path = svgpathtools.parse_path("M0 0 L50 0 L100 0")
        pieces = split_path_into_pieces(path)
        assert len(pieces) == 1

    def test_empty_path_yields_no_pieces(self) -> None:
        """Ensure that an empty path produces no pieces."""
        import svgpathtools

        assert split_path_into_pieces(svgpathtools.Path()) == []


class TestSamplePiece:
    """sample_piece: arc-length-uniform sampling of a piece's segments."""

    def test_samples_n_points_along_a_line_segment(self) -> None:
        """Ensure that sampling a line segment produces n points from start to end."""
        import svgpathtools

        path = svgpathtools.parse_path("M0 0 L100 0")
        pts = sample_piece(list(path), n=10)
        assert pts.shape == (10, 2)
        assert pts[0] == pytest.approx([0, 0])
        assert pts[-1] == pytest.approx([100, 0])

    def test_zero_length_piece_returns_its_single_start_point(self) -> None:
        """Ensure that a degenerate (zero-length) piece returns just its start point."""
        import svgpathtools

        path = svgpathtools.parse_path("M5 5 L5 5")
        pts = sample_piece(list(path))
        assert pts.shape == (1, 2)
        assert pts[0] == pytest.approx([5, 5])


class TestMatchReference:
    """match_reference: find the best-matching straight reference for a hand-drawn run."""

    HORIZONTAL_REF: ClassVar = {
        "angle": 0.0,
        "start": np.array([0.0, 0.0]),
        "direction": np.array([1.0, 0.0]),
    }
    VERTICAL_REF: ClassVar = {
        "angle": 90.0,
        "start": np.array([0.0, 0.0]),
        "direction": np.array([0.0, 1.0]),
    }

    def test_matches_a_parallel_nearby_run(self) -> None:
        """Ensure that a piece running parallel to (and near) a reference matches it."""
        pts = np.array([[x, 2.0] for x in range(0, 101, 10)])
        match = match_reference(pts, np.array([1.0, 0.0]), [self.HORIZONTAL_REF, self.VERTICAL_REF])
        assert match is self.HORIZONTAL_REF

    def test_no_match_when_angle_is_too_far_off(self) -> None:
        """Ensure that a piece at a very different angle matches nothing."""
        pts = np.array([[x, x * 2.0] for x in range(0, 51, 5)])  # ~63 degrees
        match = match_reference(pts, np.array([1.0, 2.0]) / np.sqrt(5), [self.HORIZONTAL_REF])
        assert match is None

    def test_no_match_when_too_far_away(self) -> None:
        """Ensure that a piece far from the reference's line matches nothing."""
        pts = np.array([[x, 1000.0] for x in range(0, 101, 10)])
        match = match_reference(pts, np.array([1.0, 0.0]), [self.HORIZONTAL_REF])
        assert match is None


class TestRefineStroke:
    """refine_stroke: straighten a hand-drawn stroke against reference segments."""

    def test_unparseable_stroke_returned_unchanged(self) -> None:
        """Ensure that an unparseable stroke string is returned as-is."""
        assert refine_stroke("garbage", []) == "garbage"

    def test_no_references_keeps_stroke_as_authored(self) -> None:
        """Ensure that with no references to match against, the stroke is unchanged."""
        result = refine_stroke("M0 0 L100 0 L100 100", [])
        assert result == "M 0.0 0.0 L 100.0 0.0 L 100.0 100.0"

    def test_crooked_straight_run_is_rotated_to_match_reference(self) -> None:
        """Ensure that a nearly-straight, nearly-horizontal run snaps to the true angle.

        The reference's angle is derived from a real rectangle's horizontal
        edge (~179.4 degrees, i.e. very close to exactly horizontal after
        gradient-ascent into the ink) — a hand-drawn run at a slightly
        different angle should be rotated (about its fixed start point) to
        match it, changing its end y-coordinate but not its start.
        """
        field = make_dist_field(RECT_GLYPH)
        refs = build_reference_segments(RECT_GLYPH, field)

        crooked = "M20 -5 L280 -12"
        result = refine_stroke(crooked, refs)

        assert result.startswith("M 20.0 -5.0")
        # End y-coordinate corrected toward the reference's near-horizontal
        # angle — no longer -12 (the drawn, uncorrected slope).
        assert " -12.0" not in result
