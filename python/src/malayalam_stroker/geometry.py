"""Shared stroke-path geometry: sampling, simplification, and corner-aware smoothing.

Used by the stroke-processing pipeline (see ``tools/process_strokes.py``) for
its smoothing stage, and by ghost-reference straightening for splitting a
stroke into corner-free pieces to match against font geometry.
"""

from __future__ import annotations

import numpy as np
import svgpathtools
from scipy.interpolate import splev, splprep

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


def fit_piece(pts: np.ndarray, n_out: int) -> list[str]:
    """Fit one corner-free piece and return its path commands (no leading M).

    Falls back to straight `L` segments when there aren't enough distinct
    points left for a cubic spline (also the natural result for a piece
    that's just two corner points with nothing in between).
    """
    x, y = pts[:, 0], pts[:, 1]

    # Remove near-duplicate consecutive points (splprep requires distinct knots)
    keep = np.ones(len(x), dtype=bool)
    for i in range(1, len(x)):
        if abs(x[i] - x[i - 1]) < 0.1 and abs(y[i] - y[i - 1]) < 0.1:
            keep[i] = False
    x, y = x[keep], y[keep]

    if len(x) < 2:
        return []
    if len(x) < 4:
        return [f"L {x[i]:.1f} {y[i]:.1f}" for i in range(1, len(x))]

    try:
        tck, _ = splprep([x, y], s=0, k=3)
    except Exception:
        return [f"L {x[i]:.1f} {y[i]:.1f}" for i in range(1, len(x))]

    n_out = max(n_out, 2)
    u = np.linspace(0, 1, n_out)
    xs, ys = splev(u, tck)
    dxs, dys = splev(u, tck, der=1)

    # Hermite → bezier: CP1 = P[i] + d[i]/3·dt,  CP2 = P[i+1] - d[i+1]/3·dt
    dt = 1.0 / (n_out - 1)
    parts = []
    for i in range(n_out - 1):
        cp1x = xs[i] + dxs[i] * dt / 3
        cp1y = ys[i] + dys[i] * dt / 3
        cp2x = xs[i + 1] - dxs[i + 1] * dt / 3
        cp2y = ys[i + 1] - dys[i + 1] * dt / 3
        parts.append(
            f"C {cp1x:.1f} {cp1y:.1f} {cp2x:.1f} {cp2y:.1f}"
            f" {xs[i + 1]:.1f} {ys[i + 1]:.1f}"
        )
    return parts


def smooth_points(
    pts: np.ndarray,
    rdp_epsilon: float = 20.0,
    n_out: int = 50,
    corner_angle_deg: float = CORNER_ANGLE_DEG,
) -> str | None:
    """Fit smooth cubic B-splines through an already-sampled point array.

    Core of :func:`smooth_stroke`, split out so a pipeline stage that has
    already moved the points (e.g. centering) can feed them straight in
    without a round trip through an SVG path string.

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
    piece_lens = [
        float(np.sum(np.linalg.norm(np.diff(piece, axis=0), axis=1))) if len(piece) > 1 else 0.0
        for piece in pieces
    ]
    total_len = sum(piece_lens) or 1.0

    d_parts = [f"M {pieces[0][0, 0]:.1f} {pieces[0][0, 1]:.1f}"]
    for piece, piece_len in zip(pieces, piece_lens):
        piece_n_out = max(4, round(n_out * piece_len / total_len))
        d_parts.extend(fit_piece(piece, piece_n_out))

    return " ".join(d_parts) if len(d_parts) > 1 else None


def smooth_stroke(
    stroke_d: str,
    n_samples: int = 120,
    rdp_epsilon: float = 20.0,
    n_out: int = 50,
    corner_angle_deg: float = CORNER_ANGLE_DEG,
) -> str:
    """Fit smooth cubic B-splines to a hand-authored SVG stroke.

    The RDP-simplified waypoints are split into corner-free pieces (see
    ``corner_angle_deg``), each fit independently and stitched back
    together. A stroke with no sharp corners is fit as a single global
    spline; one with genuine corners gets a clean tangent break at each
    instead of the spline overshooting to stay smooth there.

    Parameters
    ----------
    stroke_d : str
        Raw SVG ``d`` string from the stroke recorder.

    Returns
    -------
    str
        Smoothed SVG ``d`` string. Falls back to *stroke_d* unchanged
        if the input is too short.
    """
    pts = sample_path(stroke_d, n_samples)
    result = smooth_points(pts, rdp_epsilon, n_out, corner_angle_deg)
    return result if result is not None else stroke_d
