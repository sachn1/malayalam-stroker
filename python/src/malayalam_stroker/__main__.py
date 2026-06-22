"""CLI: shape one or more words against a font, print JSON to stdout.

    python -m malayalam_stroker Manjari-Regular.ttf "മലയാളം" "നന്ദി" > out.json

Output is a JSON array, one StrokeTrace object per word (with the input
word attached as "word" for convenience), in input order.
"""

from __future__ import annotations

import argparse
import json
import sys

from .strokes import shape_word


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="malayalam_stroker",
        description="Shape words against a font and print stroke-trace JSON.",
    )
    parser.add_argument("font_path", help="Path to a .ttf/.otf font file")
    parser.add_argument("words", nargs="+", help="One or more words to shape")
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    raise SystemExit(main())
