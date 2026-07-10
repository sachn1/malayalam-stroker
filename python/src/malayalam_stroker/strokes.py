"""Shape Malayalam text against a font and extract per-glyph SVG path data."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TypedDict

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

__all__ = ["MAX_WORD_LENGTH", "Glyph", "StrokeTrace", "shape_word"]

# Font space is y-up; SVG is y-down — flip the y axis.
_FLIP: tuple[int, int, int, int, int, int] = (1, 0, 0, -1, 0, 0)

#: Soft ceiling on shapeable input length.
MAX_WORD_LENGTH: int = 200


class Glyph(TypedDict):
    """Shaped glyph with its SVG outline and pen position."""

    glyphName: str
    cluster: int
    d: str
    x: float
    y: float


class StrokeTrace(TypedDict):
    """Full shaping result for one input string."""

    unitsPerEm: int
    ascent: int
    descent: int
    totalAdvance: float
    glyphs: list[Glyph]


class _ShapingFont:
    """Font outlines plus a HarfBuzz shaper, loaded once and reused."""

    def __init__(self, path: Path) -> None:
        """Load font metrics, glyph set, and HarfBuzz face from *path*."""
        tt = TTFont(str(path))
        self.glyph_set = tt.getGlyphSet()
        self.glyph_order = tt.getGlyphOrder()
        self.units_per_em: int = tt["head"].unitsPerEm
        self.ascent: int = tt["hhea"].ascent
        self.descent: int = tt["hhea"].descent

        blob = hb.Blob.from_file_path(str(path))
        self.hb_font = hb.Font(hb.Face(blob))


@lru_cache(maxsize=16)
def _font(resolved_path: str) -> _ShapingFont:
    """Return a cached ``_ShapingFont`` for *resolved_path*."""
    return _ShapingFont(Path(resolved_path))


def _glyph_path_d(glyph_set: object, glyph_name: str) -> str:
    """Return the SVG ``d`` string for *glyph_name*, flipped into y-down space."""
    svg_pen = SVGPathPen(glyph_set)
    transform_pen = TransformPen(svg_pen, _FLIP)
    glyph_set[glyph_name].draw(transform_pen)
    return svg_pen.getCommands()


@lru_cache(maxsize=4096)
def _shape_word_cached(font_path: str, word: str) -> StrokeTrace:
    """Shape *word* with HarfBuzz and extract per-glyph SVG outlines (cached)."""
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
    """Shape *word* against the font at *font_path* and return stroke-trace data.

    Results are cached per ``(font_path, word)``.  Shaping and outline
    extraction are the only non-trivial costs; the same words and fonts
    typically repeat in real usage.

    Parameters
    ----------
    word : str
        Non-empty Malayalam (or other HarfBuzz-supported) text.
    font_path : str or Path
        Path to a TrueType or OpenType font file.

    Returns
    -------
    StrokeTrace
        Dictionary with ``unitsPerEm``, ``ascent``, ``descent``,
        ``totalAdvance``, and ``glyphs`` (list of :class:`Glyph`).

    Raises
    ------
    ValueError
        If *word* is empty or exceeds :data:`MAX_WORD_LENGTH`.
    OSError
        If the font file cannot be read (propagated from fontTools).
    """
    if not word:
        raise ValueError("word must not be empty")
    if len(word) > MAX_WORD_LENGTH:
        raise ValueError(f"word must be at most {MAX_WORD_LENGTH} characters")

    resolved = str(Path(font_path).resolve())
    return _shape_word_cached(resolved, word)
