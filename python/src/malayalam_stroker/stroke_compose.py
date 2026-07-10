"""Compose multi-character cluster strokes from individually-authored parts.

Mark composition (consonant+virama, conjunct+matra, subjoined conjunct forms)
is deliberately not done here — see js/src/index.js's tryComposeStroke() and
docs/CENTERING_EXPERIMENTS.md's "Stroke composition" section for why.
"""

from __future__ import annotations

import re


def offset_svg_path(d: str, dx: float, dy: float) -> str:
    """Offset all absolute coordinates in an SVG path by (dx, dy).

    Parameters
    ----------
    d : str
        SVG path ``d`` attribute string, using absolute commands.
    dx, dy : float
        Offset to add to x and y coordinates respectively.

    Returns
    -------
    str
        The offset SVG path ``d`` string, unchanged if `dx` and `dy`
        are both 0.
    """
    if dx == 0 and dy == 0:
        return d

    def replacer(m: re.Match) -> str:
        cmd = m.group(1)
        coords = list(map(float, m.group(2).strip().split()))
        upper = cmd.upper()
        if upper == "H":
            shifted = [v + dx for v in coords]
        elif upper == "V":
            shifted = [v + dy for v in coords]
        else:
            # M, L, C, S, Q, T — pairs of (x, y)
            shifted = [v + dx if i % 2 == 0 else v + dy for i, v in enumerate(coords)]
        return f"{cmd} {' '.join(f'{v:.1f}' for v in shifted)}"

    return re.sub(r"([MLCSQTHVmlcsqthv])\s*([-\d.e]+(?:\s+[-\d.e]+)*)", replacer, d)


def find_matching_standalone_glyph_x(ch: str, clusters: dict) -> float:
    """Find the x position of the content glyph in a character's standalone entry.

    For a character like ം with 2 standalone glyphs (base placeholder at
    x=0, circle at x=1131), we need the standalone x of the *content* glyph
    (the last one) to compute how far to offset its stroke when placing it
    in a target cluster.

    Parameters
    ----------
    ch : str
        The character to look up.
    clusters : dict
        The full ``glyph-data.json`` ``clusters`` mapping.

    Returns
    -------
    float
        The x position of `ch`'s content glyph in its standalone entry,
        or 0.0 if `ch` has no standalone entry.
    """
    char_entry = clusters.get(ch)
    if not char_entry:
        return 0.0
    standalone_glyphs = char_entry["glyphs"]
    if len(standalone_glyphs) <= 1:
        return standalone_glyphs[0].get("x", 0) if standalone_glyphs else 0.0
    # Multi-glyph standalone — the last glyph is the actual content
    # (e.g. for ം: glyph[0]=base placeholder, glyph[1]=anusvara circle).
    return standalone_glyphs[-1].get("x", 0)


def _char_dx(ch: str, target_gx: float, clusters: dict) -> float:
    """Compute how far to shift `ch`'s own recorded stroke to `target_gx`."""
    char_entry = clusters.get(ch)
    if not char_entry:
        return target_gx
    if len(char_entry["glyphs"]) > 1:
        standalone_content_x = find_matching_standalone_glyph_x(ch, clusters)
        return target_gx - standalone_content_x
    standalone_x = char_entry["glyphs"][0].get("x", 0) if char_entry["glyphs"] else 0
    return target_gx - standalone_x


def compose_per_glyph(
    cluster_key: str, cluster_entry: dict, stroke_data: dict, clusters: dict, marks: dict
) -> list[dict] | None:
    """Compose a cluster's stroke from each character's own authored stroke.

    Each character's stroke is offset to its target glyph position in the
    cluster (from ``glyph-data.json``).

    That last-glyph-count-mismatch case is exactly the shape of a mark
    attachment (e.g. a compound vowel sign contributing 2 glyphs — a prefix
    and a suffix piece — for 1 character), which this function assumes never
    happens: it walks `chars` and `glyphs` in lockstep, one glyph per
    character. Attempting it anyway silently misassigns glyph slots —
    verified concretely for "കൊ" (2 chars, 3 glyphs): ക's stroke was left
    unshifted instead of moving to the middle slot, and ൊ's own stroke
    absorbed a shift meant for a different sub-part, landing both in the
    wrong place. Per this module's docstring, mark attachment is runtime's
    job (tryComposeStroke), not this one's — bailing here leaves it to
    compose correctly there.

    A *prefix*-type mark (e.g. െ/േ/ൈ) is a second, subtler case of the same
    principle even when the character count does equal the glyph count:
    HarfBuzz visually reorders a prefix mark's glyph *before* its base's own
    glyph, so `glyphs`' order no longer matches `chars`' text order —
    verified concretely for "ടെ" (2 chars, 2 glyphs): both ട's and െ's
    strokes landed on top of each other at the mark's position, ട's own
    slot left empty, because this function assumed glyph *i* belongs to
    character *i*. Bailing whenever any character has a registered
    non-empty ``prefix`` recipe in `marks` avoids this the same way.

    Parameters
    ----------
    cluster_key : str
        The cluster's character sequence (e.g. ``"ക്ക"``).
    cluster_entry : dict
        The cluster's entry from ``glyph-data.json``, with a ``glyphs`` list.
    stroke_data : dict
        Existing per-character stroke data to draw parts from.
    clusters : dict
        The full ``glyph-data.json`` ``clusters`` mapping.
    marks : dict
        The full ``glyph-data.json`` ``marks`` mapping.

    Returns
    -------
    list[dict] | None
        Composed strokes (each a ``{"d": ...}`` dict), or ``None`` if any
        character is missing a stroke, the cluster resolves to fewer than
        2 glyphs (a single-glyph ligature can't be decomposed this way),
        the character count doesn't match the glyph count, or any
        character is a prefix-type mark (glyph order wouldn't match text
        order — see above).
    """
    chars = list(cluster_key)
    if len(chars) < 2:
        return None
    glyphs = cluster_entry["glyphs"]
    if len(glyphs) < 2 or len(glyphs) != len(chars):
        return None
    if any(marks.get(ch, {}).get("prefix") for ch in chars):
        return None

    composed_strokes: list[dict] = []
    glyph_idx = 0
    for ch in chars:
        sub = stroke_data.get(ch)
        if not sub or not sub.get("strokes"):
            return None

        if glyph_idx < len(glyphs):
            target_gx = glyphs[glyph_idx].get("x", 0)
            target_gy = glyphs[glyph_idx].get("y", 0)
            glyph_idx += 1
        else:
            target_gx = glyphs[-1].get("x", 0)
            target_gy = glyphs[-1].get("y", 0)

        dx = _char_dx(ch, target_gx, clusters)
        dy = target_gy

        for s in sub["strokes"]:
            composed_strokes.append({"d": offset_svg_path(s["d"], dx, dy)})

    return composed_strokes or None


def compose_all(glyph_data: dict, stroke_data: dict) -> tuple[dict, int, int]:
    """Compose strokes for every glyph-data cluster still missing one.

    Parameters
    ----------
    glyph_data : dict
        Parsed ``glyph-data.json``, with a ``clusters`` mapping.
    stroke_data : dict
        Existing per-cluster stroke data (e.g. from ``stroke-data.json``).

    Returns
    -------
    tuple[dict, int, int]
        ``(out, generated, skipped)`` — `stroke_data` merged with newly
        composed clusters, the count generated, and the count skipped
        (clusters that couldn't be composed from existing parts).
    """
    clusters = glyph_data["clusters"]
    marks = glyph_data.get("marks", {})
    out = dict(stroke_data)
    generated = 0
    skipped = 0

    for cluster_key in sorted(clusters, key=len):
        if cluster_key in out and len(out[cluster_key].get("strokes", [])) > 0:
            continue
        composed = compose_per_glyph(cluster_key, clusters[cluster_key], out, clusters, marks)
        if composed:
            out[cluster_key] = {"strokes": composed}
            generated += 1
        else:
            skipped += 1

    return out, generated, skipped
