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


def _build_input_list() -> list[str]:
    """Return all Unicode cluster strings to be shaped.

    Returns
    -------
    list[str]
        Deduplicated list of cluster strings: standalone characters,
        consonant+matra (2-char), conjuncts (3-char), and mark combinations.
    """
    inputs: list[str] = []

    # Standalone characters (single codepoint)
    standalone = (
        "".join(INDEPENDENT_VOWELS)
        + "".join(RARE_VOWELS)
        + "".join(CONSONANTS)
        + "".join(RARE_CONSONANTS)
        + "".join(CHILLU)
        + "".join(NUMERALS)
    )
    inputs.extend(standalone)

    # Standalone diacritics — anusvara and visarga appear after any cluster
    # (including conjuncts), so they need their own glyph-data entries.
    inputs.append(ANUSVARA)
    inputs.append(VISARGA)
    inputs.append(AU_LENGTH_MARK)

    # Consonant + dependent vowel (every syllable), including rare matras
    for c in CONSONANTS:
        for m in MATRAS + RARE_MATRAS:
            inputs.append(c + m)

    # Rare consonants + matras
    for c in RARE_CONSONANTS:
        for m in MATRAS:
            inputs.append(c + m)

    # Conjuncts: consonant + virama + consonant
    for c1 in CONSONANTS:
        for c2 in CONSONANTS:
            inputs.append(c1 + VIRAMA + c2)

    # Virama as final marker
    inputs.append("ക്")

    # Independent vowels + anusvara / visarga
    for v in INDEPENDENT_VOWELS + RARE_VOWELS:
        inputs.append(v + ANUSVARA)
        inputs.append(v + VISARGA)

    # Consonants + anusvara / visarga
    for c in CONSONANTS:
        inputs.append(c + ANUSVARA)
        inputs.append(c + VISARGA)

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
            "glyphs": [
                {"d": g["d"], "x": g["x"], "y": g["y"]} for g in trace["glyphs"]
            ],
            "advance": trace["totalAdvance"],
        }
        ok += 1

    print(f"  shaped {ok} clusters, skipped {skipped}", file=sys.stderr)
    return result


def main() -> None:
    """Entry point: shape all clusters and write js/src/glyph-data.json."""
    inputs = _build_input_list()
    result = _shape_all(inputs, _FONT)

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
