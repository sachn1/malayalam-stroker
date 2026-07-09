"""Compose multi-character cluster strokes from individually-authored parts.

Per-glyph composition (the original ``expand_combinations.py`` approach):
for a cluster where every individual character has its own authored stroke,
offset each by its target position from ``glyph-data.json``'s cluster glyph
list.

Mark composition (consonant+virama, conjunct+matra, subjoined conjunct
forms) is deliberately *not* done here — it happens at runtime instead, in
``js/src/index.js``'s ``tryComposeStroke()``, mirroring the same
shift/prefix/suffix ``marks`` recipe ``composeMark()`` already uses for
glyph outlines. Pre-baking it here was tried and reverted: it composes a
candidate for every recorded base times every recorded mark regardless of
whether that combination ever gets traced, which bloated
``stroke-data.json`` from ~600KB to 28.7MB and added ~2 seconds to every
page load for combinations most words never use. Composing at request time
costs nothing extra for the combinations actually traced, and skips the
rest entirely.
"""

from __future__ import annotations

import re


def offset_svg_path(d: str, dx: float, dy: float) -> str:
    """Offset all absolute coordinates in an SVG path by (dx, dy)."""
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


def compose_per_glyph(
    cluster_key: str, cluster_entry: dict, stroke_data: dict, clusters: dict
) -> list[dict] | None:
    """Compose a cluster's stroke from each character's own authored stroke.

    Each character's stroke is offset to its target glyph position in the
    cluster (from ``glyph-data.json``). Returns ``None`` if any character is
    missing a stroke, or the cluster resolves to fewer than 2 glyphs (a
    single-glyph ligature can't be decomposed this way).
    """
    chars = list(cluster_key)
    if len(chars) < 2:
        return None
    glyphs = cluster_entry["glyphs"]
    if len(glyphs) < 2:
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

        char_entry = clusters.get(ch)
        if char_entry and len(char_entry["glyphs"]) > 1:
            standalone_content_x = find_matching_standalone_glyph_x(ch, clusters)
            dx = target_gx - standalone_content_x
        elif char_entry:
            standalone_x = char_entry["glyphs"][0].get("x", 0) if char_entry["glyphs"] else 0
            dx = target_gx - standalone_x
        else:
            dx = target_gx
        dy = target_gy

        for s in sub["strokes"]:
            composed_strokes.append({"d": offset_svg_path(s["d"], dx, dy)})

    return composed_strokes or None


def compose_all(glyph_data: dict, stroke_data: dict) -> tuple[dict, int, int]:
    """Compose strokes for every glyph-data cluster still missing one.

    Returns
    -------
    (out, generated, skipped)
    """
    clusters = glyph_data["clusters"]
    out = dict(stroke_data)
    generated = 0
    skipped = 0

    for cluster_key in sorted(clusters, key=len):
        if cluster_key in out and len(out[cluster_key].get("strokes", [])) > 0:
            continue
        composed = compose_per_glyph(cluster_key, clusters[cluster_key], out, clusters)
        if composed:
            out[cluster_key] = {"strokes": composed}
            generated += 1
        else:
            skipped += 1

    return out, generated, skipped
