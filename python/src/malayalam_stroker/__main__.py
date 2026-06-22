"""CLI: shape one or more words against a font, print JSON to stdout.

    python -m malayalam_stroker Manjari-Regular.ttf "മലയാളം" "നന്ദി" > out.json

Output is a JSON array, one StrokeTrace object per word (with the input
word attached as "word" for convenience), in input order.

Sub-commands
------------
alphabet    Shape the full Malayalam base alphabet (all vowels + consonants)
            as a single trace — the fastest way to generate input for the
            stroke recorder tool:

    python -m malayalam_stroker alphabet Manjari-Regular.ttf > alphabet.json
"""

from __future__ import annotations

import argparse
import json
import sys

from .strokes import shape_word

# ── Complete Malayalam character inventory ────────────────────────────────

# 13 independent vowels (standalone at word start)
_INDEPENDENT_VOWELS = "അആഇഈഉഊഋഎഏഐഒഓഔ"

# Regular consonants (33)
_REGULAR_CONSONANTS = "കഖഗഘങചഛജഝഞടഠഡഢണതഥദധനപഫബഭമയരലവശഷസഹ"

# Special consonants (3)
_SPECIAL_CONSONANTS = "ളഴറ"

# Chillu letters (5) — pure consonants, no inherent vowel
_CHILLU = "ൻർൽൾൺ"

# Malayalam numerals (10)
_NUMERALS = "൦൧൨൩൪൫൬൭൮൯"

# Characters above that can be shaped as one long string
_STANDALONE = _INDEPENDENT_VOWELS + _REGULAR_CONSONANTS + _SPECIAL_CONSONANTS + _CHILLU + _NUMERALS

# Dependent vowel signs (12) + anusvara + visarga + virama — shaped with ക
# as a carrier so the shaper emits the matra glyph. The recorder deduplicates
# by glyphName so ക only appears once across all traces.
_MATRA_SYLLABLES = [
    "കാ",  # aa sign  ാ
    "കി",  # i sign   ി
    "കീ",  # ii sign  ീ
    "കു",  # u sign   ു
    "കൂ",  # uu sign  ൂ
    "കൃ",  # vocalic-r sign ൃ
    "കെ",  # e sign   െ
    "കേ",  # ee sign  േ
    "കൈ",  # ai sign  ൈ
    "കൊ",  # o sign   ൊ
    "കോ",  # oo sign  ോ
    "കൗ",  # au sign  ൗ
    "കം",  # anusvara ം  (15th independent vowel form)  # noqa: RUF003
    "കഃ",  # visarga  ഃ  (15th independent vowel form)
    "ക്",  # virama / chandrakkala ്
]


def _cmd_shape(args: argparse.Namespace) -> int:
    """Shape one or more words and print a JSON array to stdout."""
    results = []
    for word in args.words:
        try:
            trace = shape_word(word, args.font_path)
        except ValueError as exc:
            print(f"error shaping {word!r}: {exc}", file=sys.stderr)
            return 1
        results.append({"word": word, **trace})
    json.dump(results, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _cmd_alphabet(args: argparse.Namespace) -> int:
    """Shape the full Malayalam character inventory and print a JSON array."""
    results = []

    # All standalone characters shaped as one long string
    try:
        trace = shape_word(_STANDALONE, args.font_path)
        results.append({"word": "standalone", **trace})
    except (ValueError, OSError) as exc:
        print(f"error shaping standalone characters: {exc}", file=sys.stderr)
        return 1

    # Each matra syllable shaped individually so the vowel sign glyph is emitted
    for syllable in _MATRA_SYLLABLES:
        try:
            trace = shape_word(syllable, args.font_path)
            results.append({"word": syllable, **trace})
        except (ValueError, OSError) as exc:
            print(f"warning: could not shape {syllable!r}: {exc}", file=sys.stderr)

    json.dump(results, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch to the appropriate sub-command.

    Parameters
    ----------
    argv : list[str] or None
        Argument list; defaults to ``sys.argv[1:]`` when ``None``.

    Returns
    -------
    int
        Exit code (0 = success, 1 = error).
    """
    parser = argparse.ArgumentParser(
        prog="malayalam_stroker",
        description="Shape Malayalam text and print stroke-trace JSON.",
    )
    sub = parser.add_subparsers(dest="cmd")

    # ── shape (default) ──────────────────────────────────────────────────
    p_shape = sub.add_parser("shape", help="Shape one or more words (default)")
    p_shape.add_argument("font_path", help="Path to a .ttf/.otf font file")
    p_shape.add_argument("words", nargs="+", help="One or more words to shape")

    # ── alphabet ─────────────────────────────────────────────────────────
    p_alpha = sub.add_parser(
        "alphabet",
        help="Shape the full Malayalam base alphabet — ideal input for the stroke recorder",
    )
    p_alpha.add_argument("font_path", help="Path to a .ttf/.otf font file")

    args = parser.parse_args(argv)

    # Backwards-compatible: no sub-command → treat all positional args as
    # font_path + words (old behaviour).
    if args.cmd is None:
        remaining = argv if argv is not None else sys.argv[1:]
        if not remaining:
            parser.print_help()
            return 0
        # Re-parse as implicit "shape"
        args = parser.parse_args(["shape", *remaining])

    if args.cmd == "alphabet":
        return _cmd_alphabet(args)
    return _cmd_shape(args)


if __name__ == "__main__":
    raise SystemExit(main())
