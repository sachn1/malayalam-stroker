"""Shape Malayalam text and extract per-glyph SVG stroke paths - see README.md for usage."""

from .strokes import MAX_WORD_LENGTH, Glyph, StrokeTrace, shape_word

__version__ = "0.2.0"

__all__ = ["MAX_WORD_LENGTH", "Glyph", "StrokeTrace", "__version__", "shape_word"]
