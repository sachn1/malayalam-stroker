"""Tests for malayalam_stroker.centering — gradient-ascent stroke centering.

Deliberately script-agnostic: the fixture "glyph" is a synthetic rectangular
bar, not a real letterform. Centering is pure geometry over an arbitrary
filled outline; it has no Malayalam-specific logic, so a new script's stroke
pipeline should never need to touch this file or its tests.
"""

from __future__ import annotations

import numpy as np
import pytest

from malayalam_stroker.centering import (
    DistField,
    center_points,
    fu_to_px,
    make_dist_field,
    px_to_fu,
)

# A simple filled rectangular bar: x in [0, 200], y in [-1000, 0].
# Its vertical centerline (the "ink ridge" for any horizontal slice) is x=100.
BAR_GLYPH = [{"d": "M0 0 L200 0 L200 -1000 L0 -1000 Z", "x": 0.0, "y": 0.0}]


@pytest.fixture
def bar_field() -> DistField:
    """Build a DistField for the synthetic vertical-bar glyph."""
    return make_dist_field(BAR_GLYPH)


class TestMakeDistField:
    """make_dist_field: rasterize outlines into a distance-transform field."""

    def test_bounding_box_covers_the_glyph(self, bar_field: DistField) -> None:
        """Ensure that the field's bounding box covers the glyph outline plus padding."""
        assert bar_field.x_min < 0
        assert bar_field.x_max > 200
        assert bar_field.y_min < -1000
        assert bar_field.y_max > 0

    def test_has_an_ink_tree(self, bar_field: DistField) -> None:
        """Ensure that a non-empty glyph produces a queryable ink tree."""
        assert bar_field.ink_tree is not None

    def test_empty_glyph_list_has_no_ink(self) -> None:
        """Ensure that an empty glyph (no outlines at all) has no ink tree."""
        field = make_dist_field([])
        assert field.ink_tree is None

    def test_width_and_height_properties(self, bar_field: DistField) -> None:
        """Ensure that the w/h properties match the bounding box extents."""
        assert bar_field.w == pytest.approx(bar_field.x_max - bar_field.x_min)
        assert bar_field.h == pytest.approx(bar_field.y_max - bar_field.y_min)


class TestPixelConversion:
    """fu_to_px / px_to_fu: font-unit <-> raster-pixel coordinate mapping."""

    def test_round_trip_recovers_original_coordinate(self, bar_field: DistField) -> None:
        """Ensure that converting to pixels and back recovers the original point."""
        fx, fy = 100.0, -500.0
        row, col = fu_to_px(bar_field, fx, fy)
        fx2, fy2 = px_to_fu(bar_field, row, col)
        assert (fx2, fy2) == pytest.approx((fx, fy), abs=1.0)


class TestCenterPoints:
    """center_points: gradient-ascend stroke points toward the local ink ridge."""

    def test_no_ink_tree_returns_points_unchanged(self) -> None:
        """Ensure that centering against an empty field is a no-op."""
        field = make_dist_field([])
        pts = np.array([[1.0, 2.0], [3.0, 4.0]])
        result = center_points(pts, field)
        assert result is pts

    def test_already_centered_point_stays_put(self, bar_field: DistField) -> None:
        """Ensure that a point already on the ink ridge barely moves."""
        pts = np.array([[100.0, -500.0]] * 4)
        result = center_points(pts, bar_field)
        assert result[0] == pytest.approx([100.0, -500.0], abs=5.0)

    def test_off_center_point_moves_toward_the_ridge(self, bar_field: DistField) -> None:
        """Ensure that a point near one edge of the bar shifts toward its centerline.

        Gradient ascent takes a fixed, small number of steps per call (see
        N_ASCENT_STEPS/ASCENT_STEP_PX) — a deliberate "nudge toward center"
        rather than a full snap, so the assertion checks direction and a
        modest minimum movement, not that it reaches x=100.
        """
        pts = np.array([[20.0, y] for y in np.linspace(-800, -200, 10)])
        result = center_points(pts, bar_field)
        assert result[:, 0].mean() > 20.0 + 1.0  # moved toward center (x=100), however slightly

    def test_max_shift_guard_limits_movement(self, bar_field: DistField) -> None:
        """Ensure that max_shift_fu bounds how far a point is allowed to move."""
        pts = np.array([[20.0, y] for y in np.linspace(-800, -200, 10)])
        result = center_points(pts, bar_field, max_shift_fu=1.0, smoothing_window=0)
        shift = np.linalg.norm(result - pts, axis=1)
        assert np.all(shift <= 1.0 + 1e-6)

    def test_point_far_outside_ink_still_returns_finite_result(self, bar_field: DistField) -> None:
        """Ensure that a point far from any ink snaps toward the nearest ink first."""
        pts = np.array([[5000.0, 5000.0]])
        result = center_points(pts, bar_field)
        assert np.all(np.isfinite(result))
