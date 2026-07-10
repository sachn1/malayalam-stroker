"""Center stroke points via gradient ascent on a glyph's distance-transform field."""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import svgpathtools
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree

RASTER_SIZE: int = 1024  # px — larger = finer gradient field
BBOX_PAD: float = 100.0  # font units padding around outline bbox

N_ASCENT_STEPS: int = 20  # gradient ascent iterations per point
ASCENT_STEP_PX: float = 0.6  # step size in pixels per iteration (sub-pixel)

#: Maximum a single point can move (font units). Prevents overshooting on
#: complex shapes where the gradient leads to the wrong local ridge.
MAX_SHIFT_FU: float = 80.0


@dataclass
class DistField:
    """Distance-transform field for one glyph, plus the pixel<->font-unit mapping."""

    dist: np.ndarray
    grad_r: np.ndarray
    grad_c: np.ndarray
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    ink_tree: cKDTree | None

    @property
    def w(self) -> float:
        """Bounding-box width in font units."""
        return self.x_max - self.x_min

    @property
    def h(self) -> float:
        """Bounding-box height in font units."""
        return self.y_max - self.y_min


def make_dist_field(glyph_glyphs: list[dict]) -> DistField:
    """Rasterize outlines and compute the distance transform + its gradient.

    Parameters
    ----------
    glyph_glyphs : list[dict]
        Glyph components, each with ``d`` (SVG path), ``x``, ``y``.

    Returns
    -------
    DistField
        The rasterized field, or an empty/degenerate one if `glyph_glyphs`
        has no ink (``ink_tree`` is ``None`` in that case).
    """
    all_pts: list[tuple[float, float]] = []
    comp_polys: list[list[tuple[float, float]]] = []

    for comp in glyph_glyphs:
        dx, dy = comp.get("x", 0), comp.get("y", 0)
        for sub_d in re.findall(r"M[^M]*", comp["d"]):
            try:
                sub = svgpathtools.parse_path(sub_d)
            except Exception:
                continue
            length = sub.length()
            if length <= 0:
                continue
            n_pts = max(64, int(length / 4))
            pts = [
                (sub.point(i / n_pts).real + dx, sub.point(i / n_pts).imag + dy)
                for i in range(n_pts + 1)
            ]
            all_pts.extend(pts)
            comp_polys.append(pts)

    if not all_pts:
        empty = np.zeros((RASTER_SIZE, RASTER_SIZE))
        return DistField(empty, empty, empty, 0.0, 0.0, 1.0, 1.0, None)

    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    x_min, x_max = min(xs) - BBOX_PAD, max(xs) + BBOX_PAD
    y_min, y_max = min(ys) - BBOX_PAD, max(ys) + BBOX_PAD
    w, h = x_max - x_min, y_max - y_min

    img = Image.new("L", (RASTER_SIZE, RASTER_SIZE), 0)
    draw = ImageDraw.Draw(img)

    def to_px(fx: float, fy: float) -> tuple[float, float]:
        return (fx - x_min) / w * RASTER_SIZE, (y_max - fy) / h * RASTER_SIZE

    for poly_pts in comp_polys:
        poly = [to_px(px, py) for px, py in poly_pts]
        if len(poly) >= 3:
            draw.polygon(poly, fill=255)

    bitmap = np.array(img) > 128
    dist = distance_transform_edt(bitmap).astype(float)
    grad_r, grad_c = np.gradient(dist)

    ink_rows, ink_cols = np.nonzero(dist > 0)
    ink_tree = None
    if len(ink_rows) > 0:
        ink_tree = cKDTree(np.column_stack([ink_rows, ink_cols]))

    return DistField(dist, grad_r, grad_c, x_min, y_min, x_max, y_max, ink_tree)


def fu_to_px(field: DistField, fx: float, fy: float) -> tuple[float, float]:
    """Convert a font-unit coordinate to a (row, col) pixel position in `field`.

    Parameters
    ----------
    field : DistField
        The distance field whose raster mapping to use.
    fx, fy : float
        Coordinate in font units.

    Returns
    -------
    tuple[float, float]
        ``(row, col)`` pixel position.
    """
    col = (fx - field.x_min) / field.w * RASTER_SIZE
    row = (field.y_max - fy) / field.h * RASTER_SIZE
    return row, col


def px_to_fu(field: DistField, row: float, col: float) -> tuple[float, float]:
    """Convert a (row, col) pixel position in `field` back to font units.

    Parameters
    ----------
    field : DistField
        The distance field whose raster mapping to use.
    row, col : float
        Pixel position.

    Returns
    -------
    tuple[float, float]
        ``(fx, fy)`` coordinate in font units.
    """
    fx = col / RASTER_SIZE * field.w + field.x_min
    fy = field.y_max - row / RASTER_SIZE * field.h
    return fx, fy


def _ascend(field: DistField, row: float, col: float) -> tuple[float, float]:
    """Climb the distance field from (row, col) to the local ink ridge (centerline)."""
    dist, grad_r, grad_c = field.dist, field.grad_r, field.grad_c
    height, width = dist.shape
    r, c = float(row), float(col)

    if not (0 <= r < height and 0 <= c < width) or dist[int(r), int(c)] < 0.5:
        if field.ink_tree is None:
            return r, c
        _, idx = field.ink_tree.query([[r, c]])
        ink_rc = field.ink_tree.data
        r, c = float(ink_rc[idx[0], 0]), float(ink_rc[idx[0], 1])

    for _ in range(N_ASCENT_STEPS):
        ri, ci = int(r), int(c)
        if not (0 < ri < height - 1 and 0 < ci < width - 1):
            break
        gr, gc = grad_r[ri, ci], grad_c[ri, ci]
        mag = (gr * gr + gc * gc) ** 0.5
        if mag < 1e-6:
            break
        r += ASCENT_STEP_PX * gr / mag
        c += ASCENT_STEP_PX * gc / mag

    return r, c


#: Width (in points) of the moving-average filter applied to the ascent's
#: displacement field before it's applied. Gradient ascent moves each point
#: independently, so on a narrow section of ink (a thin connecting stroke
#: between two bowls, say) neighboring points can end up pulled toward
#: slightly different parts of the ridge — small in absolute terms, but
#: large relative to how narrow the ink is there, which shows up as a
#: visible bulge/doubling in an otherwise-single line. Smoothing the
#: displacement *along the stroke* keeps the overall centering correction
#: while removing that point-to-point jitter. 0 or 1 disables smoothing.
DISPLACEMENT_SMOOTHING_WINDOW: int = 7


def center_points(
    pts: np.ndarray,
    field: DistField,
    max_shift_fu: float = MAX_SHIFT_FU,
    smoothing_window: int = DISPLACEMENT_SMOOTHING_WINDOW,
) -> np.ndarray:
    """Move each point toward the local center of the ink at its position.

    A point that would move further than *max_shift_fu* is blended back
    toward its original position instead — a guard against the gradient
    leading to the wrong local ridge on complex/self-intersecting shapes.
    The resulting per-point displacement is then smoothed along the stroke
    (see ``DISPLACEMENT_SMOOTHING_WINDOW``) before being applied, so the
    correction stays coherent from point to point instead of each one
    landing wherever its own independent ascent happened to stop.

    Parameters
    ----------
    pts : np.ndarray
        Stroke points to center, shape ``(n, 2)``.
    field : DistField
        The glyph's distance-transform field to center against.
    max_shift_fu : float, optional
        Maximum allowed movement per point, in font units.
    smoothing_window : int, optional
        Moving-average window (in points) for the displacement field;
        ``0`` or ``1`` disables smoothing.

    Returns
    -------
    np.ndarray
        Centered points, same shape as `pts`. Returned unchanged if `field`
        has no ink (``field.ink_tree`` is ``None``).
    """
    if field.ink_tree is None:
        return pts

    raw_targets = []
    for fx, fy in pts:
        row, col = fu_to_px(field, fx, fy)
        row2, col2 = _ascend(field, row, col)
        cx, cy = px_to_fu(field, row2, col2)
        shift = ((cx - fx) ** 2 + (cy - fy) ** 2) ** 0.5
        if shift > max_shift_fu:
            t = max_shift_fu / shift
            cx = fx + (cx - fx) * t
            cy = fy + (cy - fy) * t
        raw_targets.append((cx, cy))

    displacement = np.array(raw_targets) - pts
    if smoothing_window > 1 and len(pts) >= smoothing_window:
        kernel = np.ones(smoothing_window) / smoothing_window
        displacement = np.column_stack(
            [
                np.convolve(displacement[:, 0], kernel, mode="same"),
                np.convolve(displacement[:, 1], kernel, mode="same"),
            ]
        )

    return pts + displacement
