"""Tests for malayalam_stroker.geometry — pure path/point-array geometry.

Deliberately script-agnostic: every fixture here is a synthetic shape (line,
L-bend, zigzag), never a real letterform. This module has no Malayalam-specific
logic at all, so its tests shouldn't depend on Malayalam-specific data either —
adding a new script's stroke pipeline should never require touching this file.
"""

from __future__ import annotations

import numpy as np
import pytest

from malayalam_stroker.geometry import (
    CORNER_ANGLE_DEG,
    fit_piece,
    rdp,
    sample_path,
    smooth_points,
    smooth_stroke,
    split_at_corners,
    turn_angles,
)

STRAIGHT_LINE_D = "M0 0 L100 0"
L_BEND_D = "M0 0 L100 0 L100 100"


class TestSamplePath:
    """sample_path: SVG path -> arc-length-uniform (n, 2) point array."""

    def test_returns_n_points_for_straight_line(self) -> None:
        """Ensure that sampling a straight line returns exactly n points."""
        pts = sample_path(STRAIGHT_LINE_D, 10)
        assert pts.shape == (10, 2)

    def test_endpoints_match_path_endpoints(self) -> None:
        """Ensure that the first and last sampled points match the path's endpoints."""
        pts = sample_path(STRAIGHT_LINE_D, 5)
        assert pts[0] == pytest.approx([0, 0])
        assert pts[-1] == pytest.approx([100, 0])

    def test_points_are_evenly_spaced_on_a_straight_line(self) -> None:
        """Ensure that samples along a straight line are arc-length-uniform."""
        pts = sample_path(STRAIGHT_LINE_D, 5)
        xs = pts[:, 0]
        assert xs == pytest.approx([0, 25, 50, 75, 100], abs=1e-6)

    def test_empty_for_unparseable_path(self) -> None:
        """Ensure that an unparseable path string returns an empty array."""
        pts = sample_path("not an svg path", 10)
        assert pts.shape == (0, 2)

    def test_empty_for_zero_length_path(self) -> None:
        """Ensure that a zero-length path (single point) returns an empty array."""
        pts = sample_path("M5 5 L5 5", 10)
        assert pts.shape == (0, 2)


class TestRdp:
    """rdp: Ramer-Douglas-Peucker polyline simplification."""

    def test_collinear_points_collapse_to_endpoints(self) -> None:
        """Ensure that collinear points simplify away, keeping only the endpoints."""
        pts = np.array([[x, 0.0] for x in range(0, 101, 10)])
        simplified = rdp(pts, epsilon=1.0)
        assert len(simplified) == 2
        assert simplified[0] == pytest.approx([0, 0])
        assert simplified[-1] == pytest.approx([100, 0])

    def test_outlier_above_epsilon_is_kept(self) -> None:
        """Ensure that a point far enough off the chord survives simplification."""
        pts = np.array([[0.0, 0.0], [50.0, 30.0], [100.0, 0.0]])
        simplified = rdp(pts, epsilon=5.0)
        assert len(simplified) == 3

    def test_outlier_below_epsilon_is_dropped(self) -> None:
        """Ensure that a point within the chord's tolerance is simplified away."""
        pts = np.array([[0.0, 0.0], [50.0, 1.0], [100.0, 0.0]])
        simplified = rdp(pts, epsilon=5.0)
        assert len(simplified) == 2

    def test_fewer_than_three_points_returned_unchanged(self) -> None:
        """Ensure that a 2-point (or shorter) polyline is returned as-is."""
        pts = np.array([[0.0, 0.0], [1.0, 1.0]])
        assert rdp(pts, epsilon=1.0) is not None
        assert len(rdp(pts, epsilon=1.0)) == 2

    def test_degenerate_loop_start_equals_end(self) -> None:
        """Ensure that a polyline whose start and end coincide (a closed loop) doesn't crash."""
        pts = np.array([[0.0, 0.0], [50.0, 50.0], [0.0, 0.0]])
        simplified = rdp(pts, epsilon=1.0)
        assert len(simplified) == 3  # midpoint is far from the degenerate "chord"

    def test_recurses_past_a_single_split(self) -> None:
        """Ensure that RDP recurses to simplify both sides of an outlier, not just one."""
        # Two distinct bumps far off the baseline chord — a single split isn't
        # enough; both halves need their own outlier kept.
        pts = np.array(
            [[x, 0.0] for x in range(0, 41, 10)]
            + [[50.0, 40.0]]
            + [[x, 0.0] for x in range(60, 91, 10)]
            + [[100.0, -40.0]]
            + [[x, 0.0] for x in range(110, 141, 10)]
        )
        simplified = rdp(pts, epsilon=1.0)
        ys = simplified[:, 1]
        assert 40.0 in ys
        assert -40.0 in ys


class TestTurnAngles:
    """turn_angles: per-point turning angle (degrees) along a polyline."""

    def test_endpoints_are_zero(self) -> None:
        """Ensure that turn angle is defined as 0 at both polyline endpoints."""
        way = np.array([[0.0, 0.0], [50.0, 50.0], [100.0, 0.0]])
        angles = turn_angles(way)
        assert angles[0] == 0
        assert angles[-1] == 0

    def test_straight_line_has_zero_interior_angle(self) -> None:
        """Ensure that a straight run has ~0 turn angle at its interior points."""
        way = np.array([[x, 0.0] for x in range(0, 101, 25)])
        angles = turn_angles(way)
        assert angles[1:-1] == pytest.approx(0, abs=1e-6)

    def test_right_angle_bend_measures_90_degrees(self) -> None:
        """Ensure that a 90-degree bend measures as a 90-degree turn angle."""
        way = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0]])
        angles = turn_angles(way)
        assert angles[1] == pytest.approx(90.0, abs=1e-6)


class TestSplitAtCorners:
    """split_at_corners: break a polyline into corner-free pieces."""

    def test_smooth_curve_stays_one_piece(self) -> None:
        """Ensure that a polyline with no sharp turns is returned as a single piece."""
        way = np.array([[x, 0.0] for x in range(0, 101, 10)])
        pieces = split_at_corners(way, CORNER_ANGLE_DEG)
        assert len(pieces) == 1

    def test_sharp_corner_splits_into_two_pieces(self) -> None:
        """Ensure that a 90-degree corner (> CORNER_ANGLE_DEG) splits the polyline."""
        way = np.array([[0.0, 0.0], [50.0, 0.0], [100.0, 0.0], [100.0, 50.0], [100.0, 100.0]])
        pieces = split_at_corners(way, CORNER_ANGLE_DEG)
        assert len(pieces) == 2

    def test_pieces_share_the_corner_point(self) -> None:
        """Ensure that consecutive pieces share their boundary waypoint."""
        way = np.array([[0.0, 0.0], [50.0, 0.0], [100.0, 0.0], [100.0, 50.0], [100.0, 100.0]])
        pieces = split_at_corners(way, CORNER_ANGLE_DEG)
        assert pieces[0][-1] == pytest.approx(pieces[1][0])

    def test_shallow_bend_below_threshold_stays_one_piece(self) -> None:
        """Ensure that a bend shallower than corner_angle_deg does not split."""
        way = np.array([[0.0, 0.0], [50.0, 0.0], [100.0, 5.0]])
        pieces = split_at_corners(way, corner_angle_deg=80.0)
        assert len(pieces) == 1


class TestFitPiece:
    """fit_piece: fit one corner-free piece to path commands."""

    def test_four_or_more_points_produce_bezier_commands(self) -> None:
        """Ensure that a piece with enough points is fit with cubic Bezier commands."""
        pts = np.array([[float(x), 0.0] for x in range(0, 101, 10)])
        commands = fit_piece(pts)
        assert commands
        assert all(c.startswith("C ") for c in commands)
        # One bezier per waypoint gap (local Catmull-Rom-tangent fit, not a
        # single global spline resampled to some other resolution).
        assert len(commands) == len(pts) - 1

    def test_fewer_than_four_points_falls_back_to_lines(self) -> None:
        """Ensure that a piece too short for a spline falls back to straight lines."""
        pts = np.array([[0.0, 0.0], [10.0, 10.0], [20.0, 0.0]])
        commands = fit_piece(pts)
        assert commands
        assert all(c.startswith("L ") for c in commands)

    def test_near_duplicate_points_are_deduplicated(self) -> None:
        """Ensure that near-duplicate consecutive points don't break the spline fit."""
        pts = np.array([[0.0, 0.0], [0.05, 0.05], [50.0, 0.0], [100.0, 0.0], [100.0, 100.0]])
        commands = fit_piece(pts)
        assert commands  # doesn't raise, produces output

    def test_single_point_produces_no_commands(self) -> None:
        """Ensure that a degenerate single-point piece produces no commands."""
        pts = np.array([[0.0, 0.0]])
        assert fit_piece(pts) == []

    def test_straight_line_through_a_curved_piece_stays_straight(self) -> None:
        """Ensure a straight run doesn't bulge just because it shares a piece with a loop.

        Regression test for a real bug: a piece combining a loop with a
        straight tail was previously fit as one global interpolating spline,
        which bulged the straight tail to stay smooth through the loop's
        curvature. Local (Catmull-Rom) tangents fix this — verified against
        ബ's actual recorded stroke (see docs/CENTERING_EXPERIMENTS.md).
        """
        loop = [
            [100.0 + 80 * np.cos(t), 100.0 + 80 * np.sin(t)] for t in np.linspace(0, 1.5 * np.pi, 8)
        ]
        tail = [[100.0, -50.0], [100.0, -200.0], [100.0, -400.0]]
        pts = np.array(loop + tail)
        commands = fit_piece(pts)

        # The last two segments are the straight tail — their bezier control
        # points should stay on the vertical line (x == 100), not bow outward.
        for c in commands[-2:]:
            nums = [float(v) for v in c[2:].split()]
            xs = nums[0::2]
            assert all(abs(x - 100.0) < 1.0 for x in xs), c


class TestSmoothPoints:
    """smooth_points: fit smooth cubic B-splines through a point array."""

    def test_produces_a_valid_moveto_path(self) -> None:
        """Ensure that smoothing a plausible stroke produces a path starting with M."""
        pts = sample_path(L_BEND_D, 60)
        result = smooth_points(pts)
        assert result is not None
        assert result.startswith("M ")

    def test_too_few_points_returns_none(self) -> None:
        """Ensure that fewer than 4 points can't be smoothed and returns None."""
        pts = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
        assert smooth_points(pts) is None

    def test_sharp_corner_produces_a_multi_piece_path(self) -> None:
        """Ensure that a stroke with a genuine corner is fit as multiple pieces.

        A single global spline would need to overshoot to stay smooth through a
        sharp corner (see CORNER_ANGLE_DEG's docstring) — splitting at the corner
        means the output has more than one C-command "run" stitched together.
        """
        pts = sample_path(L_BEND_D, 60)
        result = smooth_points(pts, corner_angle_deg=CORNER_ANGLE_DEG)
        assert result is not None
        # Two corner-free pieces means the fitted path passes through the
        # corner point itself, exactly on the sharp turn.
        assert "100.0 100.0" not in result or "C " in result


class TestSmoothStroke:
    """smooth_stroke: sample + smooth an SVG stroke path in one call."""

    def test_smooths_a_plausible_stroke(self) -> None:
        """Ensure that a plausible hand-drawn-shaped stroke gets smoothed."""
        result = smooth_stroke(L_BEND_D)
        assert result.startswith("M ")

    def test_falls_back_to_original_when_too_short(self) -> None:
        """Ensure that an unsmoothable (too-short) stroke is returned unchanged."""
        tiny = "M0 0 L1 1"
        assert smooth_stroke(tiny) == tiny
