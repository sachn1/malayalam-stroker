"""Minimal usage example.

Run from the python/ directory:
    python examples/shape_and_render.py

Renders a quick PNG so you can eyeball that shaping/outlines look right,
using only stdlib + the package's own dependencies (no extra installs).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from malayalam_stroker import shape_word  # noqa: E402

FONT = Path(__file__).parent.parent / "tests" / "fixtures" / "Manjari-Regular.ttf"
WORD = "മലയാളം"

trace = shape_word(WORD, FONT)
print(f"{WORD!r} -> {len(trace['glyphs'])} glyphs (unitsPerEm={trace['unitsPerEm']})")

svg_parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" '
    f'viewBox="0 0 {trace[\"totalAdvance\"] + 200} {trace[\"unitsPerEm\"]}">'
]
for g in trace["glyphs"]:
    svg_parts.append(
        f'<path d="{g["d"]}" transform="translate({g["x"] + 100},'
        f'{trace["ascent"] + 100})" fill="black"/>'
    )
svg_parts.append("</svg>")

out_path = Path(__file__).parent / "demo_output.svg"
out_path.write_text("".join(svg_parts), encoding="utf-8")
print(f"wrote {out_path}")
