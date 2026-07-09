# Stroke Centering — Experiments Log

Goal: programmatically correct human-labelled strokes so they run through the
visual centre of the Manjari ghost glyph, without altering the animation or
the original `stroke-data.json`.

---

## Attempt 1 — Rigid Translation (`center_strokes.py`)

**Idea:** Compute the bounding-box centroid of the ghost outline and of the
stroke cloud. Translate all stroke points by the difference vector.

**Result:** Strokes moved visibly (shifts of 20–45 font units), but shape and
jitter were completely unchanged. Centering and smoothing are independent.

**Why it falls short:** A rigid translation corrects the gross offset but
cannot fix per-point deviations. A stroke labelled off-centre on the left side
of a glyph and off-centre on the right will still be wrong after translation.

---

## Attempt 2 — Global Skeleton Snap (first version of `skeleton_strokes.py`)

**Idea:**
1. Rasterize the ghost outline → binary bitmap (512 px over full ascent/descent box).
2. `skimage.skeletonize()` → thinned centerline.
3. For every stroke point, snap it to the globally nearest skeleton pixel (KD-tree).
4. Fit a bezier through the snapped cloud.

**Result:** Stroke completely destroyed. Points near branch junctions teleported
to wrong branches on the opposite side of the letter.

**Root cause:** Global nearest-neighbour without a radius guard makes every
point near a junction ambiguous. The assembled point cloud had no topological
coherence with the original stroke path.

---

## Attempt 3 — Local Nudge with Radius Guard (second version)

**Idea:** Same skeleton, but instead of hard-snapping, only pull points within
`SNAP_RADIUS = 60` font units toward the skeleton by `SNAP_ALPHA = 0.8`.
Points further away are left untouched.

**Result:** Better than attempt 2, but SNAP_RADIUS was too small (~3% of UPM).
Only 22–60% of points were nudged; the rest stayed in their original (wrong)
positions.

---

## Attempt 4 — Tight Bounding Box + `medial_axis` + Larger Radius

**Changes:**
- Raster viewport switched from full ascent/descent box to the outline's own
  tight bounding box → ~4× finer pixel resolution.
- Resolution increased from 512 → 1024 px.
- `skeletonize` replaced with `medial_axis` (distance-transform ridge, more
  geometrically precise).
- `SNAP_RADIUS` raised to 300 font units → 100% of points nudged.

**Result:** 100% of points nudged, but output is visually garbled — jagged
outlines, wrong shapes.

**Root cause (fundamental):** The medial axis of a *filled* glyph outline is
NOT the stroke trajectory. For a thick letter like ജ:
- The skeleton runs through the geometric centre of the ink width.
- It branches at every curve, loop junction, and serif.
- None of those branches correspond to a human writing gesture.
- Snapping a stroke path onto this branching structure scatters points
  to geometrically valid but semantically wrong locations.

---

## Why the Problem Is Hard

A rendered glyph encodes *what* to draw (filled shapes), not *how* to draw it
(ordered pen strokes). The mapping from filled outline → stroke trajectory is
the reverse of what a calligrapher does, and is not injective:
- Multiple distinct stroke orderings can produce the same glyph shape.
- Thick strokes look the same whether drawn left-to-right or right-to-left.
- Loops in the medial axis correspond to circular strokes, but the skeleton
  gives a ring with no start/end — the human stroke resolves this implicitly.

---

## Possible Forward Paths

### A — Accept the human stroke as authoritative; only smooth it
Use `snap_strokes.py` (cubic B-spline fit). The stroke is already roughly
centred if the labeller was careful. This is the current production path.

### B — Per-point projection onto the *nearest outline edge* (not skeleton)
Instead of pulling toward the skeleton, project each stroke point onto the
nearest point on the glyph *outline contour*. Then pull inward by half the
local stroke width (estimated from the distance transform at that point).
This is a local operation with no branch ambiguity.

### C — Thin-plate spline warp
Manually or automatically identify a sparse set of anchor points where the
human stroke clearly deviates from the skeleton branch it belongs to, then
fit a thin-plate spline that maps stroke points to corrected positions while
preserving the overall topology.

### D — Train a small model
Given enough (stroke, glyph) pairs, a sequence model could learn to map raw
stroke point sequences to corrected ones. Requires labelled data.

### E — Better labelling tooling
Add a live skeleton overlay to `stroke-recorder.html` so the labeller can see
the medial axis while drawing and aim for it directly. Removes the need for
post-processing correction entirely.

---

## Resolution — Gradient Ascent (adopted)

A variant of B that turned out to work: rather than snapping to the
skeleton or projecting onto the outline, walk each stroke point a small,
fixed number of steps *up the gradient* of the distance-transform field
(toward higher "depth inside the ink"). Following the local gradient from a
point's own neighbourhood — rather than a global nearest-skeleton-pixel
search — is what avoids the "teleport to the wrong branch near a junction"
failure that sank Attempts 2–4: the point can only climb the ridge it's
already closest to, not jump across it.

This is the approach now used in production, consolidated (from the
`center_strokes_v2.py` / `refine_with_ghost.py` prototypes referenced above)
into `python/src/malayalam_stroker/centering.py`, and run via
`tools/process_strokes.py --center`. The exploratory scripts this log
documents (`center_strokes.py`, `skeleton_strokes.py`, `center_strokes_v2.py`)
have been removed now that their logic lives in the shared module; this file
is kept as the record of why the simpler approaches didn't work.
