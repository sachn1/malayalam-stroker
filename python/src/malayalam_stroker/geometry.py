"""Shared stroke-path geometry: sampling, simplification, and corner-aware smoothing."""

from __future__ import annotations

import numpy as np
import svgpathtools

#: Turning angle (degrees) at an RDP waypoint above which the stroke is
#: treated as a genuine corner rather than part of a continuous curve.
#: A single global spline forces C1 continuity everywhere, so a real
#: corner (e.g. a stroke reversing from a downstroke into a foot) makes it
#: swing wide to stay smooth — that overshoot is what produces spurious
#: loops. Splitting into independent pieces at these corners lets the fit
#: break tangent cleanly instead.
CORNER_ANGLE_DEG: float = 50.0


def sample_path(d: str, n: int) -> np.ndarray:
    """Sample *n* arc-length-uniform points from an SVG path.

    Parameters
    ----------
    d : str
        SVG path ``d`` attribute string.
    n : int
        Number of equally-spaced samples.

    Returns
    -------
    np.ndarray
        Array of shape ``(n, 2)`` with ``(x, y)`` coordinates,
        or ``(0, 2)`` if the path is empty or unparseable.
    """
    try:
        path = svgpathtools.parse_path(d)
    except Exception:
        return np.empty((0, 2))

    length = path.length()
    if length <= 0:
        return np.empty((0, 2))

    pts: list[tuple[float, float]] = []
    for i in range(n):
        s = (i / (n - 1)) * length
        try:
            t = path.ilength(s)
        except Exception:
            t = i / (n - 1)
        p = path.point(t)
        pts.append((p.real, p.imag))

    return np.array(pts)


def _rdp_indices(pts: np.ndarray, epsilon: float) -> list[int]:
    """Return the indices of the RDP-simplified polyline."""
    if len(pts) < 3:
        return list(range(len(pts)))

    start, end = pts[0], pts[-1]
    seg = end - start
    seg_len = float(np.linalg.norm(seg))

    if seg_len < 1e-9:
        dists = np.linalg.norm(pts - start, axis=1)
    else:
        delta = pts - start
        dists = np.abs(seg[0] * delta[:, 1] - seg[1] * delta[:, 0]) / seg_len

    idx = int(np.argmax(dists))
    if dists[idx] > epsilon:
        left = _rdp_indices(pts[: idx + 1], epsilon)
        right = _rdp_indices(pts[idx:], epsilon)
        return left[:-1] + [i + idx for i in right]

    return [0, len(pts) - 1]


def rdp(pts: np.ndarray, epsilon: float) -> np.ndarray:
    """Simplify a polyline with the Ramer-Douglas-Peucker algorithm.

    Parameters
    ----------
    pts : np.ndarray
        Input polyline, shape ``(n, 2)``.
    epsilon : float
        Maximum allowable perpendicular deviation for point removal.

    Returns
    -------
    np.ndarray
        Simplified polyline, shape ``(m, 2)`` where ``m <= n``.
    """
    return pts[_rdp_indices(pts, epsilon)]


def turn_angles(way: np.ndarray) -> np.ndarray:
    """Compute the turning angle (degrees) at each interior point of a polyline.

    Endpoints are 0 (no turn is defined there).

    Parameters
    ----------
    way : np.ndarray
        Waypoint polyline, shape ``(n, 2)``.

    Returns
    -------
    np.ndarray
        Turning angle in degrees at each waypoint, shape ``(n,)``.
    """
    angles = np.zeros(len(way))
    for i in range(1, len(way) - 1):
        v1 = way[i] - way[i - 1]
        v2 = way[i + 1] - way[i]
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        cosang = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
        angles[i] = np.degrees(np.arccos(cosang))
    return angles


def split_at_corners(
    way: np.ndarray, corner_angle_deg: float = CORNER_ANGLE_DEG
) -> list[np.ndarray]:
    """Split a waypoint polyline into pieces at sharp direction changes.

    Consecutive pieces share their boundary waypoint so the fitted curve
    stays positionally connected, while each piece is fit independently —
    letting the curve break tangent sharply at a real corner instead of
    being forced smooth across it by one global spline.

    Parameters
    ----------
    way : np.ndarray
        Waypoint polyline, shape ``(n, 2)``.
    corner_angle_deg : float, optional
        Turning angle above which a waypoint is treated as a corner.

    Returns
    -------
    list[np.ndarray]
        One or more polyline pieces; consecutive pieces share their
        boundary waypoint.
    """
    if len(way) < 3:
        return [way]
    angles = turn_angles(way)
    corner_idx = [i for i in range(1, len(way) - 1) if angles[i] > corner_angle_deg]
    if not corner_idx:
        return [way]
    pieces = []
    start = 0
    for idx in corner_idx:
        pieces.append(way[start : idx + 1])
        start = idx
    pieces.append(way[start:])
    return pieces


def fit_piece(pts: np.ndarray) -> list[str]:
    """Fit one corner-free piece and return its path commands (no leading M).

    Each consecutive pair of waypoints becomes one cubic bezier segment,
    using a centripetal-Catmull-Rom tangent at each waypoint (estimated
    from its immediate neighbors only) converted to Hermite-equivalent
    bezier control points. This is a *local* fit — each segment's shape
    depends only on that waypoint and its neighbors — deliberately unlike a
    single global interpolating spline through the whole piece, which
    forces every segment to satisfy one shared curvature constraint. That
    global constraint is what previously made an otherwise-straight run
    bulge into a visible wave whenever it followed a very differently
    curved section (e.g. a loop feeding into a straight downstroke, which
    share a piece whenever their junction isn't a sharp-enough corner to
    split on) — verified concretely on ബ's middle stroke, whose straight
    vertical connector was rendered as a curve for exactly this reason
    before switching to local tangents.

    Falls back to straight `L` segments when there aren't enough distinct
    points left for a curve (also the natural result for a piece that's
    just two corner points with nothing in between).

    Parameters
    ----------
    pts : np.ndarray
        Corner-free piece of a waypoint polyline, shape ``(n, 2)``.

    Returns
    -------
    list[str]
        SVG path commands (``L`` or ``C``) continuing from `pts`'s
        first point, or ``[]`` if fewer than 2 distinct points remain.
    """
    x, y = pts[:, 0], pts[:, 1]

    # Remove near-duplicate consecutive points (zero-length segments have no
    # meaningful tangent).
    keep = np.ones(len(x), dtype=bool)
    for i in range(1, len(x)):
        if abs(x[i] - x[i - 1]) < 0.1 and abs(y[i] - y[i - 1]) < 0.1:
            keep[i] = False
    pts = np.column_stack([x[keep], y[keep]])

    n = len(pts)
    if n < 2:
        return []
    if n < 4:
        return [f"L {pts[i, 0]:.1f} {pts[i, 1]:.1f}" for i in range(1, n)]

    def tangent(i: int) -> np.ndarray:
        if i == 0:
            return pts[1] - pts[0]
        if i == n - 1:
            return pts[-1] - pts[-2]
        return (pts[i + 1] - pts[i - 1]) / 2.0

    parts = []
    for i in range(n - 1):
        p0, p1 = pts[i], pts[i + 1]
        m0, m1 = tangent(i), tangent(i + 1)
        # Hermite (p0, m0, p1, m1) -> bezier: CP1 = p0 + m0/3, CP2 = p1 - m1/3
        cp1 = p0 + m0 / 3
        cp2 = p1 - m1 / 3
        parts.append(
            f"C {cp1[0]:.1f} {cp1[1]:.1f} {cp2[0]:.1f} {cp2[1]:.1f} {p1[0]:.1f} {p1[1]:.1f}"
        )
    return parts


def smooth_points(
    pts: np.ndarray,
    rdp_epsilon: float = 20.0,
    corner_angle_deg: float = CORNER_ANGLE_DEG,
) -> str | None:
    """Fit smooth local (Catmull-Rom-tangent) cubic beziers through sampled points.

    Core of :func:`smooth_stroke`, split out so a pipeline stage that has
    already moved the points (e.g. centering) can feed them straight in
    without a round trip through an SVG path string.

    Parameters
    ----------
    pts : np.ndarray
        Already-sampled stroke points, shape ``(n, 2)``.
    rdp_epsilon : float, optional
        Maximum perpendicular deviation for RDP waypoint simplification.
    corner_angle_deg : float, optional
        Turning angle above which a waypoint is treated as a corner.

    Returns
    -------
    str | None
        Smoothed SVG ``d`` string, or ``None`` if there aren't enough points.
    """
    if len(pts) < 4:
        return None

    waypts = rdp(pts, rdp_epsilon)
    if len(waypts) < 4:
        waypts = pts

    pieces = split_at_corners(waypts, corner_angle_deg)

    d_parts = [f"M {pieces[0][0, 0]:.1f} {pieces[0][0, 1]:.1f}"]
    for piece in pieces:
        d_parts.extend(fit_piece(piece))

    return " ".join(d_parts) if len(d_parts) > 1 else None


def smooth_stroke(
    stroke_d: str,
    n_samples: int = 120,
    rdp_epsilon: float = 20.0,
    corner_angle_deg: float = CORNER_ANGLE_DEG,
) -> str:
    """Fit smooth local (Catmull-Rom-tangent) cubic beziers to a hand-authored stroke.

    The RDP-simplified waypoints are split into corner-free pieces (see
    ``corner_angle_deg``), each fit independently (:func:`fit_piece`) and
    stitched back together. A stroke with no sharp corners is fit as one
    continuous run of local-tangent segments; one with genuine corners gets
    a clean tangent break at each instead of a global spline overshooting to
    stay smooth there.

    Parameters
    ----------
    stroke_d : str
        Raw SVG ``d`` string from the stroke recorder.
    n_samples : int, optional
        Number of arc-length-uniform points to sample from `stroke_d`.
    rdp_epsilon : float, optional
        Maximum perpendicular deviation for RDP waypoint simplification.
    corner_angle_deg : float, optional
        Turning angle above which a waypoint is treated as a corner.

    Returns
    -------
    str
        Smoothed SVG ``d`` string. Falls back to *stroke_d* unchanged
        if the input is too short.
    """
    pts = sample_path(stroke_d, n_samples)
    result = smooth_points(pts, rdp_epsilon, corner_angle_deg)
    return result if result is not None else stroke_d
