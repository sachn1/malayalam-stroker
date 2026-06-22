"""malayalam_stroker.strokes

Shape Malayalam (or any HarfBuzz-supported script) text against a font and
extract each shaped glyph's outline as SVG path data, in left-to-right
visual order. Built on fontTools + uharfbuzz: shaping handles conjunct/
ligature collapse and vowel-sign reordering correctly; fontTools pulls the
real glyph outlines out of the font.

Pairs with the malayalam-stroker JS package, which animates the output as
a stroke-trace "draw-on" widget — but the JSON shape here is plain and
font/runtime-agnostic, so it's useful on its own (stroke-order datasets,
glyph-outline analysis, etc).

    from malayalam_stroker import shape_word
    trace = shape_word("നന്ദി", "/path/to/font.ttf")
    trace["glyphs"][0]["d"]   # SVG path 'd' string, y-down

Unlike the original linguaalayam-internal version this is forked from,
this is font-agnostic (no bundled/hardcoded font) and not tied to any
single web framework.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TypedDict

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

__all__ = ["shape_word", "Glyph", "StrokeTrace", "MAX_WORD_LENGTH"]

_FLIP = (1, 0, 0, -1, 0, 0)  # font space is y-up; SVG is y-down

# Soft ceiling on shapeable input. Override by calling _shape_word_uncached
# directly if you genuinely need longer strings (full sentences, etc).
MAX_WORD_LENGTH = 200


class Glyph(TypedDict):
    glyphName: str
    cluster: int
    d: str
    x: float
    y: float


class StrokeTrace(TypedDict):
    unitsPerEm: int
    ascent: int
    descent: int
    totalAdvance: float
    glyphs: list[Glyph]


class _ShapingFont:
    """A font's outlines plus a HarfBuzz shaper, loaded once and reused."""

    def __init__(self, path: Path) -> None:
        tt = TTFont(str(path))
        self.glyph_set = tt.getGlyphSet()
        self.glyph_order = tt.getGlyphOrder()
        self.units_per_em = tt["head"].unitsPerEm
        self.ascent = tt["hhea"].ascent
        self.descent = tt["hhea"].descent

        blob = hb.Blob.from_file_path(str(path))
        self.hb_font = hb.Font(hb.Face(blob))


@lru_cache(maxsize=16)
def _font(resolved_path: str) -> _ShapingFont:
    """Load a font once per resolved path and keep it resident.

    Cache key is the resolved path string (lru_cache needs hashable args;
    Path objects are hashable too, but normalising to str avoids surprises
    if callers pass equivalent-but-distinct Path instances).
    """
    return _ShapingFont(Path(resolved_path))


def _glyph_path_d(glyph_set, glyph_name: str) -> str:
    """SVG path 'd' string for one glyph, flipped into SVG's y-down space."""
    svg_pen = SVGPathPen(glyph_set)
    transform_pen = TransformPen(svg_pen, _FLIP)
    glyph_set[glyph_name].draw(transform_pen)
    return svg_pen.getCommands()


@lru_cache(maxsize=4096)
def _shape_word_cached(font_path: str, word: str) -> StrokeTrace:
    font = _font(font_path)
    buf = hb.Buffer()
    buf.add_str(word)
    buf.guess_segment_properties()
    hb.shape(font.hb_font, buf)

    glyphs: list[Glyph] = []
    pen_x = pen_y = 0.0
    path_cache: dict[str, str] = {}
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        name = font.glyph_order[info.codepoint]
        if name not in path_cache:
            path_cache[name] = _glyph_path_d(font.glyph_set, name)
        glyphs.append(
            {
                "glyphName": name,
                "cluster": int(info.cluster),
                "d": path_cache[name],
                "x": pen_x + pos.x_offset,
                "y": pen_y - pos.y_offset,
            }
        )
        pen_x += pos.x_advance
        pen_y += pos.y_advance

    return {
        "unitsPerEm": font.units_per_em,
        "ascent": font.ascent,
        "descent": font.descent,
        "totalAdvance": pen_x,
        "glyphs": glyphs,
    }


def shape_word(word: str, font_path: str | Path) -> StrokeTrace:
    """Shape `word` against the font at `font_path` and return stroke-trace
    path data.

    Results are cached per (font_path, word): shaping + outline extraction
    is the only non-trivial cost, and the same words/fonts tend to repeat
    in real usage. Raises ValueError for empty input or input over
    MAX_WORD_LENGTH. Raises OSError/fontTools errors if the font can't be
    read — those aren't caught here, since a missing/corrupt font is a
    setup problem the caller needs to see, not silently swallow.
    """
    if not word:
        raise ValueError("word must not be empty")
    if len(word) > MAX_WORD_LENGTH:
        raise ValueError(f"word must be at most {MAX_WORD_LENGTH} characters")

    resolved = str(Path(font_path).resolve())
    return _shape_word_cached(resolved, word)
