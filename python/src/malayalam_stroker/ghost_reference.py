"""Build straight reference segments from a glyph's ghost outline, in centerline space.

A hand-drawn stroke is a *centerline* running through the middle of the ink,
offset from the outline boundary by roughly half the local stroke width — so
straightening/angle-correction can't use outline edges directly as a
reference (see module docstring history in git log for the outline-snap
approach this replaced). Instead: find straight edges on the raw outline
(:func:`find_straight_segments`), then gradient-ascend them into the ink
using :mod:`malayalam_stroker.centering` — climbing from the boundary to the
local ridge of the distance field gives the centerline that edge implies, at
whatever the local stroke width is. A line fit through the ascended points is
kept only if it's clean (low residual) — this discards edges near
corners/junctions where ascent can wander to the wrong local ridge.
"""

from __future__ import annotations

import re

import numpy as np
import svgpathtools

from .centering import DistField, center_points
from .geometry import CORNER_ANGLE_DEG

N_GHOST_SAMPLES_PER_UNIT = 0.3  # ghost outline sampling density (pts per font unit)
STRAIGHT_TOLERANCE = 5.0  # max deviation (fu) for an outline edge to count as "straight"
STRAIGHT_MIN_LENGTH = 50.0  # min length (fu) for an outline edge segment

REF_MIN_LENGTH = 60.0  # ignore outline edges too short to trust as a reference
REF_MAX_RESIDUAL = 30.0  # max fu deviation from a straight line after ascent

# -- Hand-drawn stroke: corner splitting + straight-run matching --
STRAIGHT_RESIDUAL_TOLERANCE = 15.0  # max fu deviation for a piece to count as "meant to be straight"
MIN_STRAIGHT_PIECE_LENGTH = 40.0  # ignore tiny nubs
ANGLE_MATCH_TOLERANCE_DEG = 22.0
DIST_MATCH_TOLERANCE = 45.0


def sample_outline(glyph_glyphs: list[dict]) -> list[np.ndarray]:
    """Sample points along each ghost outline contour."""
    contours = []
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
            n_pts = max(50, int(length * N_GHOST_SAMPLES_PER_UNIT))
            pts = []
            for i in range(n_pts + 1):
                p = sub.point(i / n_pts)
                pts.append([p.real + dx, p.imag + dy])
            contours.append(np.array(pts))
    return contours


def find_straight_segments(contours: list[np.ndarray]) -> list[dict]:
    """Find straight edge segments in the raw ghost outline (boundary space)."""
    segments = []
    for contour in contours:
        n = len(contour)
        if n < 5:
            continue

        i = 0
        while i < n - 3:
            best_end = -1
            for j in range(i + 3, min(i + n // 2, n)):
                chord = contour[j] - contour[i]
                chord_len = np.linalg.norm(chord)
                if chord_len < 1e-6:
                    continue
                delta = contour[i + 1 : j] - contour[i]
                perp_dist = np.abs(
                    chord[0] * delta[:, 1] - chord[1] * delta[:, 0]
                ) / chord_len
                if np.max(perp_dist) <= STRAIGHT_TOLERANCE:
                    if chord_len >= STRAIGHT_MIN_LENGTH:
                        best_end = j
                else:
                    break

            if best_end >= 0:
                start_pt = contour[i]
                end_pt = contour[best_end]
                length = np.linalg.norm(end_pt - start_pt)
                segments.append({"start": start_pt, "end": end_pt, "length": length})
                i = best_end
            else:
                i += 1

    return segments


def fit_line(
    pts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """Fit the best line through points via PCA.

    Returns (mean, unit_direction, max_perp_residual, proj_min, proj_max).
    """
    mean = pts.mean(axis=0)
    centered = pts - mean
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    direction = vt[0]
    direction = direction / np.linalg.norm(direction)
    proj = centered @ direction
    perp = centered - np.outer(proj, direction)
    residual = float(np.max(np.linalg.norm(perp, axis=1))) if len(perp) else 0.0
    return mean, direction, residual, float(proj.min()), float(proj.max())


def build_reference_segments(glyph_glyphs: list[dict], field: DistField) -> list[dict]:
    """Build straight reference segments in centerline space.

    Each outer straight outline edge is sampled and gradient-ascended into
    the ink (:func:`~malayalam_stroker.centering.center_points`); a line fit
    through the ascended points is kept only if it's clean (low residual) —
    this discards edges near corners/junctions where ascent can wander to
    the wrong local ridge.
    """
    if field.ink_tree is None:
        return []

    contours = sample_outline(glyph_glyphs)
    outer_segments = find_straight_segments(contours)

    refs = []
    for seg in outer_segments:
        if seg["length"] < REF_MIN_LENGTH:
            continue
        n_sample = max(6, int(seg["length"] / 40))
        chord = seg["end"] - seg["start"]
        sample_pts = np.array(
            [seg["start"] + t * chord for t in np.linspace(0.15, 0.85, n_sample)]
        )
        ascended = center_points(sample_pts, field, max_shift_fu=float("inf"))

        mean, direction, residual, pmin, pmax = fit_line(ascended)
        length = pmax - pmin
        if residual > REF_MAX_RESIDUAL or length < REF_MIN_LENGTH * 0.5:
            continue

        angle = np.degrees(np.arctan2(direction[1], direction[0])) % 180
        refs.append({
            "start": mean + direction * pmin,
            "end": mean + direction * pmax,
            "direction": direction,
            "angle": angle,
            "length": length,
        })
    return refs


# ---------------------------------------------------------------------------
# Hand-drawn stroke: corner splitting + straight-run matching
# ---------------------------------------------------------------------------

def split_path_into_pieces(path: svgpathtools.Path) -> list[list]:
    """Group path segments into corner-free pieces via tangent-angle breaks.

    Mirrors the corner detection in :mod:`malayalam_stroker.geometry`, but
    works directly off the parsed segments' tangents rather than resampled
    points — the corner is already a real geometric feature of the smoothed
    path (a tangent break between two pieces), not something that needs
    re-inferring.
    """
    if len(path) == 0:
        return []
    pieces = [[path[0]]]
    for i in range(1, len(path)):
        d_prev = path[i - 1].derivative(1.0)
        d_cur = path[i].derivative(0.0)
        if abs(d_prev) < 1e-9 or abs(d_cur) < 1e-9:
            angle = 0.0
        else:
            cosang = (d_prev.real * d_cur.real + d_prev.imag * d_cur.imag) / (
                abs(d_prev) * abs(d_cur)
            )
            cosang = max(-1.0, min(1.0, cosang))
            angle = np.degrees(np.arccos(cosang))
        if angle > CORNER_ANGLE_DEG:
            pieces.append([path[i]])
        else:
            pieces[-1].append(path[i])
    return pieces


def sample_piece(segs: list, n: int = 30) -> np.ndarray:
    """Sample n arc-length-uniform points along a piece's parsed path segments."""
    sub = svgpathtools.Path(*segs)
    length = sub.length()
    if length <= 0:
        p = segs[0].start
        return np.array([[p.real, p.imag]])
    pts = []
    for i in range(n):
        s = i / (n - 1) * length
        try:
            t = sub.ilength(s)
        except Exception:
            t = i / (n - 1)
        p = sub.point(t)
        pts.append([p.real, p.imag])
    return np.array(pts)


def match_reference(
    piece_pts: np.ndarray, piece_direction: np.ndarray, refs: list[dict]
) -> dict | None:
    """Find the best reference segment matching a straight hand-drawn run, if any."""
    piece_angle = np.degrees(np.arctan2(piece_direction[1], piece_direction[0])) % 180
    best, best_dist = None, None
    for ref in refs:
        da = abs(piece_angle - ref["angle"])
        da = min(da, 180 - da)
        if da > ANGLE_MATCH_TOLERANCE_DEG:
            continue
        rel = piece_pts - ref["start"]
        proj = rel @ ref["direction"]
        perp = rel - np.outer(proj, ref["direction"])
        avg_dist = float(np.mean(np.linalg.norm(perp, axis=1)))
        if avg_dist > DIST_MATCH_TOLERANCE:
            continue
        if best_dist is None or avg_dist < best_dist:
            best_dist, best = avg_dist, ref
    return best


def _emit_translated(segs: list, delta: np.ndarray) -> list[str]:
    """Emit path commands for segs rigidly translated by delta (no reshaping)."""
    dc = complex(delta[0], delta[1])
    parts = []
    for seg in segs:
        e = seg.end + dc
        if isinstance(seg, svgpathtools.CubicBezier):
            c1, c2 = seg.control1 + dc, seg.control2 + dc
            parts.append(
                f"C {c1.real:.1f} {c1.imag:.1f} {c2.real:.1f} {c2.imag:.1f}"
                f" {e.real:.1f} {e.imag:.1f}"
            )
        else:
            parts.append(f"L {e.real:.1f} {e.imag:.1f}")
    return parts


def refine_stroke(stroke_d: str, refs: list[dict]) -> str:
    """Refine one stroke: match corner-free straight runs to reference segments.

    Each straight run is rigidly rotated about its (fixed) start point to the
    matched reference's exact angle — correcting the drawn angle to the
    font's actual angle. Runs with no good match, or that aren't straight,
    are kept as authored (rigidly translated to stay attached at the corner
    after a neighboring correction).
    """
    try:
        path = svgpathtools.parse_path(stroke_d)
    except Exception:
        return stroke_d
    if len(path) == 0:
        return stroke_d

    pieces = split_path_into_pieces(path)

    d_parts: list[str] = []
    running_offset = np.zeros(2)
    for segs in pieces:
        orig_start = np.array([segs[0].start.real, segs[0].start.imag])
        orig_end = np.array([segs[-1].end.real, segs[-1].end.imag])
        actual_start = orig_start + running_offset

        if not d_parts:
            d_parts.append(f"M {actual_start[0]:.1f} {actual_start[1]:.1f}")

        pts = sample_piece(segs)
        _, direction, residual, pmin, pmax = fit_line(pts)
        is_straight = (
            residual < STRAIGHT_RESIDUAL_TOLERANCE
            and (pmax - pmin) > MIN_STRAIGHT_PIECE_LENGTH
        )
        match = match_reference(pts, direction, refs) if (is_straight and refs) else None

        if match is not None:
            vec = orig_end - orig_start
            ref_dir = match["direction"]
            if np.dot(vec, ref_dir) < 0:
                ref_dir = -ref_dir
            new_end = actual_start + ref_dir * np.dot(vec, ref_dir)
            d_parts.append(f"L {new_end[0]:.1f} {new_end[1]:.1f}")
            running_offset = new_end - orig_end
        else:
            d_parts.extend(_emit_translated(segs, running_offset))
            # running_offset unchanged: the whole piece moved by it uniformly,
            # so its end (this piece's contribution to the next start) is
            # already exactly orig_end + running_offset.

    return " ".join(d_parts)
