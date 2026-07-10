#!/usr/bin/env python3
"""Unified stroke-processing pipeline: center, smooth, straighten, expand.

Replaces the earlier separate snap_strokes.py / straighten_lines.py /
refine_with_ghost.py / center_strokes_v2.py / expand_combinations.py scripts
(and their six intermediate/duplicate output files) with one configurable
pass over the hand-authored js/src/stroke-data.raw.json, writing a single
UI-ready file: js/src/stroke-data.json — the name index.js's loadStrokes()
already defaults to fetching, and the file demo.js loads. Re-running this
script always refreshes that one file in place, so it's always the latest
processed version; js/src/stroke-data.raw.json (edited by
tools/stroke-recorder.html) is untouched, so re-processing with different
flags is always possible without re-recording anything.

Stages (each independently toggleable):
  --center      Gradient-ascent centering onto the glyph's ink ridge
                (malayalam_stroker.centering)
  --smooth      Corner-aware piecewise spline fit — the baseline cleanup
                (malayalam_stroker.geometry)
  --straighten  Ghost-guided angle correction: straight runs are matched
                against reference segments derived from the font outline
                and rotated to the font's exact angle
                (malayalam_stroker.ghost_reference)
  --expand      Per-glyph composition: a cluster where every individual
                character already has its own authored stroke gets one
                composed from them (malayalam_stroker.stroke_compose).
                Mark composition (consonant+virama, conjunct+matra,
                subjoined conjunct forms) is *not* done here — it happens
                at runtime in js/src/index.js instead, so stroke-data.json
                doesn't pre-bake a candidate for every base times every
                mark regardless of whether it's ever traced.

--preset=malayalam enables all four (sensible defaults for this project's
current single-language scope); pass explicit --center/--no-center etc. to
override any of them.

Usage (from repo root):
    python tools/process_strokes.py --preset=malayalam
    python tools/process_strokes.py --smooth --expand   # no centering/straightening
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))

from malayalam_stroker import centering, geometry, ghost_reference, stroke_compose  # noqa: E402

STROKE_DATA = ROOT / "js" / "src" / "stroke-data.raw.json"
GLYPH_DATA = ROOT / "js" / "src" / "glyph-data.json"
DEFAULT_OUTPUT = ROOT / "js" / "src" / "stroke-data.json"

N_SAMPLES = 120  # arc-length-uniform points sampled per stroke before center/smooth

PRESETS: dict[str, dict[str, bool]] = {
    "malayalam": {"center": True, "smooth": True, "straighten": True, "expand": True},
}


def parse_args() -> argparse.Namespace:
    """Parse CLI args, resolving `--preset` defaults for any stage flag left unset.

    Returns
    -------
    argparse.Namespace
        Parsed arguments, with every stage flag (``center``, ``smooth``,
        ``straighten``, ``expand``) resolved to an explicit bool.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--preset", choices=sorted(PRESETS), help="Apply a named default set of stages"
    )
    parser.add_argument("--center", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--smooth", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--straighten", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--expand", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--input", type=Path, default=STROKE_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    preset = PRESETS.get(args.preset, {})
    for stage in ("center", "smooth", "straighten", "expand"):
        if getattr(args, stage) is None:
            setattr(args, stage, preset.get(stage, False))
    return args


def _reference_glyphs(cluster: str, cluster_info: dict, marks: dict) -> list[dict]:
    """Return the glyphs to use as the centering/straightening reference for `cluster`.

    A single-character mark's own standalone entry includes HarfBuzz's
    dotted-circle placeholder (see tools/build_glyph_data.py's
    ``_standalone_inputs()``) alongside its real content glyph — the human
    only traced the content, so the placeholder must be excluded here, or
    it corrupts the distance field with a second, spurious "ink" blob the
    gradient ascent can wander into (shows up as wiggle right where the
    content starts, next to where the circle would have been). ``marks``
    already knows, per mark, whether content is glyphs[0] (prefix marks,
    which render before the circle) or glyphs[-1] (suffix marks, circle
    first) — see ``_build_marks()``'s docstring in build_glyph_data.py.
    """
    glyphs = cluster_info["glyphs"]
    if len(cluster) != 1 or len(glyphs) != 2:
        return glyphs
    mark = marks.get(cluster)
    if not mark:
        return glyphs
    return [glyphs[0]] if mark["prefix"] else [glyphs[-1]]


def _process_stroke(
    d: str,
    field: centering.DistField | None,
    refs: list[dict],
    args: argparse.Namespace,
) -> str:
    """Run one stroke through the center/smooth/straighten stages, in that order."""
    if args.center or args.smooth:
        pts = geometry.sample_path(d, N_SAMPLES)
        if len(pts) >= 4:
            if args.center and field is not None:
                pts = centering.center_points(pts, field)
            if args.smooth:
                smoothed = geometry.smooth_points(pts)
                if smoothed:
                    d = smoothed
            else:
                # Centered but not smoothed: emit a raw polyline through the
                # moved points rather than silently dropping the centering.
                d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)

    if args.straighten and refs:
        d = ghost_reference.refine_stroke(d, refs)

    return d


def main() -> None:
    """Run the requested stages over `stroke-data.raw.json` and write the output file."""
    args = parse_args()
    args.input = args.input.resolve()
    args.output = args.output.resolve()
    if not (args.center or args.smooth or args.straighten or args.expand):
        print(
            "Nothing to do — pass --preset=malayalam or at least one stage flag.",
            file=sys.stderr,
        )
        sys.exit(1)

    stroke_data: dict = json.loads(args.input.read_text(encoding="utf-8"))
    glyph_data: dict = json.loads(GLYPH_DATA.read_text(encoding="utf-8"))
    clusters = glyph_data["clusters"]
    marks = glyph_data.get("marks", {})

    needs_dist_field = args.center or args.straighten
    out: dict = {}

    for cluster, entry in stroke_data.items():
        cluster_info = clusters.get(cluster)

        field = None
        refs: list[dict] = []
        if needs_dist_field and cluster_info is not None:
            ref_glyphs = _reference_glyphs(cluster, cluster_info, marks)
            field = centering.make_dist_field(ref_glyphs)
            if args.straighten:
                refs = ghost_reference.build_reference_segments(ref_glyphs, field)

        new_strokes = [
            {"d": _process_stroke(s["d"], field, refs, args)} for s in entry.get("strokes", [])
        ]
        out[cluster] = {"strokes": new_strokes}

    if args.expand:
        out, generated, skipped = stroke_compose.compose_all(glyph_data, out)
        print(f"Expansion: generated {generated} composed clusters, {skipped} skipped")

    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    stages = [s for s in ("center", "smooth", "straighten", "expand") if getattr(args, s)]
    try:
        output_display = args.output.relative_to(ROOT)
    except ValueError:
        output_display = args.output
    print(f"Stages: {', '.join(stages) or 'none'}")
    print(f"Written {output_display} ({len(out)} clusters)")


if __name__ == "__main__":
    main()
