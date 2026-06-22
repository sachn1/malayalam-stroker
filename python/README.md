# malayalam-stroker (Python)

Shape Malayalam text against any font and get back per-glyph SVG stroke
paths, ready for a handwriting-trace or stroke-order animation.

It's the missing piece between "I have a font" and "I have a stroke-order
JSON" — built on [fontTools](https://github.com/fonttools/fonttools) +
[uharfbuzz](https://github.com/harfbuzz/uharfbuzz), so shaping correctly
handles conjunct/ligature collapse and vowel-sign reordering rather than
treating each Unicode codepoint as one glyph.

Pairs with the companion JS package
[`malayalam-stroker`](../js) for an animated widget that consumes the
JSON this produces directly — but the output here is plain JSON, useful
on its own too.

## Install

```bash
pip install malayalam-stroker
```

## Usage

```python
from malayalam_stroker import shape_word

trace = shape_word("നന്ദി", "/path/to/Manjari-Regular.ttf")

trace["unitsPerEm"]   # 2048
trace["glyphs"][0]    # {"glyphName": "n1", "cluster": 0, "d": "M...Z", "x": 0, "y": 0}
```

`d` is an SVG path string in y-down coordinates (already flipped from the
font's native y-up space), so you can drop it straight into an `<svg>`.

### Why shaping matters

Malayalam (like most Brahmic scripts) isn't a 1:1 codepoint-to-glyph
mapping — consonant clusters collapse into ligatures, vowel signs can
reorder visually. Compare:

```python
>>> word = "ക്ഷമിക്കണം"
>>> len(word)                       # 10 Unicode codepoints
10
>>> len(shape_word(word, font)["glyphs"])   # 6 shaped glyphs
6
```

ക്ഷ (4 codepoints: ക + ്  + ഷ) shapes to a single ligature glyph. Anything
that just walks codepoints and looks up a font's cmap will get this
wrong.

### CLI

```bash
python -m malayalam_stroker Manjari-Regular.ttf "മലയാളം" "നന്ദി" > out.json
```

Prints a JSON array, one trace per word (each with the input word
attached as `"word"`), in input order.

## StrokeTrace shape

```ts
{
  unitsPerEm: number,
  ascent: number,
  descent: number,
  totalAdvance: number,
  glyphs: [
    { glyphName: string, cluster: number, d: string, x: number, y: number },
    ...
  ]
}
```

`x`/`y` are pen-position offsets (already includes any HarfBuzz
positioning adjustments) — translate each glyph's `<path d={d}>` by
`(x, y)` to place it correctly relative to the others.

## Fonts

This package doesn't bundle a font — bring your own. Tested against
[Manjari](https://fonts.google.com/specimen/Manjari) and
[Chilanka](https://fonts.google.com/specimen/Chilanka) (both SIL OFL,
free), but any font with proper Malayalam GSUB/GPOS tables should work.
No GSUB/GPOS support generally means broken conjuncts — check your font
choice if shaped output looks wrong.

## Scope

Despite the name, nothing here is Malayalam-specific at the code level —
`shape_word` will happily shape Latin, Devanagari, or anything else
HarfBuzz and your font support. The name reflects the motivating use
case (there wasn't an existing stroke-order tool for Malayalam).

## License

MIT.
