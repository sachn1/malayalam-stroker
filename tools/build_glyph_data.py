#!/usr/bin/env python3
"""Pre-compute SVG glyph paths for all Malayalam clusters and write glyph-data.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))

from malayalam_stroker import shape_word  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FONT = (
    sys.argv[1]
    if len(sys.argv) > 1
    else str(ROOT / "python" / "tests" / "fixtures" / "Manjari-Regular.ttf")
)

_CONSONANTS = list("കഖഗഘങചഛജഝഞടഠഡഢണതഥദധനപഫബഭമയരലവശഷസഹളഴറ")
_MATRAS = list("ാിീുൂൃെേൈൊോൗ")
_VIRAMA = "\u0d4d"
_ANUSVARA = "\u0d02"
_VISARGA = "\u0d03"
_INDEPENDENT_VOWELS = list("അആഇഈഉഊഋഎഏഐഒഓഔ")


def _build_input_list() -> list[str]:
    """Return all Unicode cluster strings to be shaped.

    Parameters
    ----------
    None

    Returns
    -------
    list[str]
        Deduplicated list of cluster strings: standalone characters,
        consonant+matra (2-char), conjuncts (3-char), and mark combinations.
    """
    inputs: list[str] = []

    # Standalone characters
    standalone = (
        "".join(_INDEPENDENT_VOWELS) + "".join(_CONSONANTS) + "ൻർൽൾൺ" + "൦൧൨൩൪൫൬൭൮൯"
    )
    inputs.extend(standalone)

    # Consonant + dependent vowel (every syllable)
    for c in _CONSONANTS:
        for m in _MATRAS:
            inputs.append(c + m)

    # Conjuncts: consonant + virama + consonant (longest-match, checked first)
    for c1 in _CONSONANTS:
        for c2 in _CONSONANTS:
            inputs.append(c1 + _VIRAMA + c2)

    # Virama as final marker
    inputs.append("ക്")

    # Independent vowels + anusvara / visarga
    for v in _INDEPENDENT_VOWELS:
        inputs.append(v + _ANUSVARA)
        inputs.append(v + _VISARGA)

    # Consonants + anusvara / visarga
    for c in _CONSONANTS:
        inputs.append(c + _ANUSVARA)
        inputs.append(c + _VISARGA)

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
    """Entry point: shape all clusters and write js/src/glyph-data.json.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
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
