#!/usr/bin/env python3
"""Pre-compute SVG glyph paths for all Malayalam clusters and write glyph-data.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))

from malayalam_stroker import shape_word  # noqa: E402
from malayalam_stroker._chars import (  # noqa: E402
    ANUSVARA,
    AU_LENGTH_MARK,
    CHILLU,
    CONSONANTS,
    INDEPENDENT_VOWELS,
    MATRAS,
    NUMERALS,
    RARE_CONSONANTS,
    RARE_MATRAS,
    RARE_VOWELS,
    VIRAMA,
    VISARGA,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FONT = (
    sys.argv[1]
    if len(sys.argv) > 1
    else str(ROOT / "python" / "tests" / "fixtures" / "Manjari-Regular.ttf")
)

#: Compound vowel signs with a canonical (or, for ai, font-specific) split
#: into simpler marks — see js/src/index.js's SPLIT_VOWEL_PARTS. These never
#: need their own recorded stroke or standalone ghost; they're composed from
#: their parts at runtime instead.
_SPLIT_VOWELS = ("ൊ", "ോ", "ൌ")  # ൊ ോ ൌ


def _standalone_inputs() -> list[str]:
    """Single-codepoint clusters: letters, digits, and standalone diacritics."""
    letters = (
        "".join(INDEPENDENT_VOWELS)
        + "".join(RARE_VOWELS)
        + "".join(CONSONANTS)
        + "".join(RARE_CONSONANTS)
        + "".join(CHILLU)
        + "".join(NUMERALS)
    )
    inputs = list(letters)

    # Anusvara/visarga/au-length-mark appear after any cluster (including
    # conjuncts), so they need their own glyph-data entries.
    inputs += [ANUSVARA, VISARGA, AU_LENGTH_MARK]

    # Virama and matras — give the recorder a real dotted-circle ghost to
    # trace over (same reasoning as above) rather than recording these blind
    # via the recorder's custom-cluster field. _SPLIT_VOWELS are excluded:
    # they compose from simpler marks already covered here instead of
    # needing their own recorded stroke.
    inputs.append(VIRAMA)
    inputs += [m for m in MATRAS + RARE_MATRAS if m not in _SPLIT_VOWELS]
    return inputs


def _consonant_matra_inputs() -> list[str]:
    """Consonant + dependent vowel (every syllable), including rare matras."""
    inputs = [c + m for c in CONSONANTS for m in MATRAS + RARE_MATRAS]
    inputs += [c + m for c in RARE_CONSONANTS for m in MATRAS]
    return inputs


def _conjunct_inputs() -> list[str]:
    """Conjuncts: consonant + virama + consonant.

    consonant+virama (dead-consonant forms) and conjunct+matra are NOT
    brute-forced here (that was 36 + 36*36*12 extra shape_word calls,
    ballooning glyph-data.json from ~5.4MB to 63MB). Both compose cleanly at
    runtime from a base cluster + a mark's prefix/suffix recipe — see
    _build_marks() below and js/src/index.js's composeCluster().
    """
    return [c1 + VIRAMA + c2 for c1 in CONSONANTS for c2 in CONSONANTS]


def _anusvara_visarga_inputs() -> list[str]:
    """Independent vowels and consonants + anusvara / visarga."""
    bases = INDEPENDENT_VOWELS + RARE_VOWELS + CONSONANTS
    return [b + mark for b in bases for mark in (ANUSVARA, VISARGA)]


def _build_input_list() -> list[str]:
    """Return all Unicode cluster strings to be shaped.

    Returns
    -------
    list[str]
        Deduplicated list of cluster strings: standalone characters,
        consonant+matra (2-char), conjuncts (3-char), and mark combinations.
    """
    inputs = (
        _standalone_inputs()
        + _consonant_matra_inputs()
        + _conjunct_inputs()
        + _anusvara_visarga_inputs()
    )

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for item in inputs:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _shape_all(inputs: list[str], font: str) -> dict:
    """Shape every input cluster and collect results.

    Parameters
    ----------
    inputs : list[str]
        Unicode cluster strings to shape.
    font : str
        Path to the TrueType font file.

    Returns
    -------
    dict
        ``{"meta": {...}, "clusters": {cluster: {"glyphs": [...], "advance": N}}}``
    """
    result: dict = {"meta": None, "clusters": {}}
    ok = skipped = 0

    for inp in inputs:
        if inp in result["clusters"]:
            continue
        try:
            trace = shape_word(inp, font)
        except Exception as exc:
            print(f"  skip {inp!r}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        if result["meta"] is None:
            result["meta"] = {
                "unitsPerEm": trace["unitsPerEm"],
                "ascent": trace["ascent"],
                "descent": trace["descent"],
            }

        result["clusters"][inp] = {
            "glyphs": [{"d": g["d"], "x": g["x"], "y": g["y"]} for g in trace["glyphs"]],
            "advance": trace["totalAdvance"],
        }
        ok += 1

    print(f"  shaped {ok} clusters, skipped {skipped}", file=sys.stderr)
    return result


#: Combining marks composable onto an arbitrary base cluster at runtime
#: (virama + every dependent vowel sign, common and rare), plus subjoined
#: conjunct forms (the reduced ya/va/la shape a second consonant takes when
#: attached under a preceding one, e.g. the tail in ക്യ) — verified to
#: follow the exact same dotted-circle-placeholder pattern as ordinary
#: marks: shaping "്യ"/"്വ"/"്ല" alone gives a 2-glyph placeholder+suffix
#: result just like shaping "ീ" alone does, so they need no separate
#: composition mechanism, just more entries in this same table.
#: ്യ/്വ verified exact-match across 35/36 consonants (the only non-match
#: is the nonsensical self-pairing case, e.g. യ+്യ, which never occurs in
#: real text). ്ല is mixed (22/36 simple-suffix, 12/36 font-specific
#: fusion, 2/36 three-glyph outliers) — uses the same "compose as separate
#: entities" fallback as ു/ൂ/ൃ below.
_COMPOSABLE_MARKS = [
    VIRAMA,
    *MATRAS,
    *RARE_MATRAS,
    AU_LENGTH_MARK,  # ൗ — the suffix half of ൌ's decomposition (js/src/index.js's SPLIT_VOWEL_PARTS)
    VIRAMA + "യ",
    VIRAMA + "വ",
    VIRAMA + "ല",
]


def _build_marks(font: str) -> dict:
    """Shape each composable mark alone and split it into prefix/suffix parts.

    HarfBuzz auto-inserts a dotted-circle placeholder glyph when a combining
    mark has no preceding base — its position tells us exactly how the mark
    attaches to *any* base: glyphs before the placeholder print as a prefix
    (the base shifts right by the placeholder's position); glyphs after it
    print as a suffix (positioned right after the base's own advance, flush
    against it — the placeholder's own arbitrary width is irrelevant and
    discarded, not added).

    Verified empirically against real HarfBuzz output across every consonant
    (virama, subjoined ya/va/la) and ~700 conjunct+matra combinations: exact
    match for simple suffix marks (ാ/ി/ീ), virama, and subjoined ya/va on
    any base, and for prefix/compound marks (െ/േ/ൈ/ൊ/ോ/ൌ) *when the base
    is a single glyph* — composing those onto a multi-glyph (non-ligating)
    conjunct base can reorder incorrectly, so callers must check ``prefix``
    is non-empty against the base's glyph count. ു/ൂ/ൃ and subjoined la
    fuse into a glyph unique to the specific preceding consonant in real
    shaping (~45% mismatch composing these generically in testing) —
    composed the same way as any other suffix mark, they render as the
    base's own glyph plus the mark's separate standalone shape: less
    tightly kerned than the true font ligature, but still correct and
    legible.

    Returns
    -------
    dict
        ``{mark: {"shift": N, "prefix": [...], "suffix": [...], "trailingWidth": N}}``
    """
    marks: dict = {}
    for m in _COMPOSABLE_MARKS:
        trace = shape_word(m, font)
        glyphs = trace["glyphs"]
        circle_idx = next(i for i, g in enumerate(glyphs) if g["glyphName"] == "uni25CC")
        shift = glyphs[circle_idx]["x"]
        prefix = [{"d": g["d"], "x": g["x"], "y": g["y"]} for g in glyphs[:circle_idx]]
        suffix_glyphs = glyphs[circle_idx + 1 :]
        # Anchor suffix offsets to the first suffix glyph's own position (not
        # `shift`) — the placeholder's own on-screen width is an artifact of
        # the dotted-circle glyph, not something a real base should inherit.
        anchor = suffix_glyphs[0]["x"] if suffix_glyphs else shift
        suffix = [{"d": g["d"], "x": g["x"] - anchor, "y": g["y"]} for g in suffix_glyphs]
        trailing_width = (trace["totalAdvance"] - anchor) if suffix_glyphs else 0.0
        marks[m] = {
            "shift": shift,
            "prefix": prefix,
            "suffix": suffix,
            "trailingWidth": trailing_width,
        }
    return marks


def main() -> None:
    """Entry point: shape all clusters and write js/src/glyph-data.json."""
    inputs = _build_input_list()
    result = _shape_all(inputs, _FONT)
    result["marks"] = _build_marks(_FONT)

    out_path = ROOT / "js" / "src" / "glyph-data.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))

    size_kb = out_path.stat().st_size // 1024
    print(
        f"Written {out_path.relative_to(ROOT)}  ({size_kb} KB, "
        f"{len(result['clusters'])} clusters)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
