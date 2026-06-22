"""malayalam_stroker — shape Malayalam text and extract per-glyph SVG
stroke paths for stroke-order / handwriting-trace widgets.

    from malayalam_stroker import shape_word
    trace = shape_word("നന്ദി", "Manjari-Regular.ttf")

See README.md for the full StrokeTrace JSON shape and the companion JS
package (malayalam-stroker on npm) for an animated widget that consumes
this output directly.
"""

from .strokes import MAX_WORD_LENGTH, Glyph, StrokeTrace, shape_word

__version__ = "0.1.0"

__all__ = ["shape_word", "Glyph", "StrokeTrace", "MAX_WORD_LENGTH", "__version__"]
