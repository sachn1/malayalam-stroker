#!/usr/bin/env python3
"""Smooth hand-authored strokes via cubic B-spline fitting and write stroke-data-snapped.json."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import svgpathtools
from scipy.interpolate import splev, splprep

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
STROKE_DATA = ROOT / "js" / "src" / "stroke-data.json"
OUT_PATH = ROOT / "js" / "src" / "stroke-data-snapped.json"

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

#: Arc-length-uniform points sampled from each raw stroke.
N_SAMPLES: int = 120

#: Ramer-Douglas-Peucker epsilon in font units (~1000 UPM).
#: Increase (toward 20) for smoother output; decrease (toward 5) to
#: stay closer to the hand-drawn shape.
RDP_EPSILON: float = 20.0

#: Number of cubic bezier segments in the output path.
N_OUT: int = 50


# ---------------------------------------------------------------------------
# SVG path sampling
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Ramer-Douglas-Peucker polyline simplification
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Bezier spline fitting
# ---------------------------------------------------------------------------


def smooth_stroke(stroke_d: str) -> str:
    """Fit a smooth cubic B-spline to a hand-authored SVG stroke.

    The spline interpolates the RDP-simplified waypoints exactly,
    preserving the stroke's overall shape, start, end, and direction.
    The output uses C1-continuous cubic bezier segments derived via
    Hermite-to-bezier conversion.

    Parameters
    ----------
    stroke_d : str
        Raw SVG ``d`` string from the stroke recorder.

    Returns
    -------
    str
        Smoothed SVG ``d`` string.  Falls back to *stroke_d* unchanged
        if the input is too short or spline fitting fails.
    """
    pts = sample_path(stroke_d, N_SAMPLES)
    if len(pts) < 4:
        return stroke_d

    waypts = rdp(pts, RDP_EPSILON)
    if len(waypts) < 4:
        waypts = pts

    x, y = waypts[:, 0], waypts[:, 1]

    # Remove near-duplicate consecutive points (splprep requires distinct knots)
    keep = np.ones(len(x), dtype=bool)
    for i in range(1, len(x)):
        if abs(x[i] - x[i - 1]) < 0.1 and abs(y[i] - y[i - 1]) < 0.1:
            keep[i] = False
    x, y = x[keep], y[keep]

    if len(x) < 4:
        return stroke_d

    try:
        tck, _ = splprep([x, y], s=0, k=3)
    except Exception:
        return stroke_d

    u = np.linspace(0, 1, N_OUT)
    xs, ys = splev(u, tck)
    dxs, dys = splev(u, tck, der=1)

    # Hermite → bezier: CP1 = P[i] + d[i]/3·dt,  CP2 = P[i+1] - d[i+1]/3·dt
    dt = 1.0 / (N_OUT - 1)
    parts = [f"M {xs[0]:.1f} {ys[0]:.1f}"]
    for i in range(N_OUT - 1):
        cp1x = xs[i] + dxs[i] * dt / 3
        cp1y = ys[i] + dys[i] * dt / 3
        cp2x = xs[i + 1] - dxs[i + 1] * dt / 3
        cp2y = ys[i + 1] - dys[i + 1] * dt / 3
        parts.append(
            f"C {cp1x:.1f} {cp1y:.1f} {cp2x:.1f} {cp2y:.1f}"
            f" {xs[i + 1]:.1f} {ys[i + 1]:.1f}"
        )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Read stroke-data.json, smooth every stroke, and write stroke-data-snapped.json."""
    stroke_data: dict = json.loads(STROKE_DATA.read_text(encoding="utf-8"))
    out: dict = {}

    for cluster, entry in stroke_data.items():
        smoothed: list[dict] = []
        for i, stroke in enumerate(entry.get("strokes", [])):
            result_d = smooth_stroke(stroke["d"])
            smoothed.append({"d": result_d})
            label = "smoothed" if result_d != stroke["d"] else "unchanged (too short)"
            print(f"  {cluster!r} stroke {i + 1}: {label}")
        out[cluster] = {"strokes": smoothed}

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWritten {OUT_PATH.relative_to(ROOT)}")
    print("Drop stroke-data-snapped.json onto the demo drop zone to compare.")


if __name__ == "__main__":
    main()
