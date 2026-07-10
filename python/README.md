# malayalam-stroker (Python)

Build-time tool: shapes Malayalam text against a font using HarfBuzz and
outputs per-glyph SVG path data as JSON. Used to generate
`js/src/glyph-data.json` — the file the JS animator bundles at runtime.

Not a runtime dependency. Not published to PyPI. Run it once (or when you
change fonts) and commit the output.

## Setup

```bash
cd python && poetry install
```

Requires Python 3.10+. Dependencies: `fonttools`, `uharfbuzz`, `svgpathtools`,
`numpy`, `scipy`, `pillow`.

## Generate glyph-data.json

```bash
# Uses the bundled Manjari-Regular.ttf by default:
poetry run python ../tools/build_glyph_data.py

# Supply a different font:
poetry run python ../tools/build_glyph_data.py /path/to/MyFont.ttf
```

Output: `js/src/glyph-data.json`. Commit this file.

## Usage

```python
from malayalam_stroker import shape_word

trace = shape_word("നന്ദി", "/path/to/Manjari-Regular.ttf")

trace["unitsPerEm"]   # 2048
trace["glyphs"][0]    # {"glyphName": "n1", "cluster": 0, "d": "M...Z", "x": 0, "y": 0}
```

`d` is an SVG path string in y-down coordinates (already flipped from the
font's native y-up space), so you can drop it straight into an `<svg>`.

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

`x`/`y` are pen-position offsets (already includes any HarfBuzz positioning
adjustments) — translate each glyph's `<path d={d}>` by `(x, y)` to place it
correctly relative to the others.

## CLI

```bash
# Shape one or more words, print a JSON array (one StrokeTrace per word,
# each with the input word attached as "word"), in input order:
poetry run python -m malayalam_stroker Manjari-Regular.ttf "മലയാളം" "നന്ദി" > out.json

# Shape the full Malayalam base alphabet as one trace — quick input for
# tools/stroke-recorder.html without running the full build pipeline:
poetry run python -m malayalam_stroker alphabet tests/fixtures/Manjari-Regular.ttf > alphabet.json
```

## Why shaping matters

Malayalam (like most Brahmic scripts) isn't a 1:1 codepoint-to-glyph
mapping — consonant clusters collapse into ligatures, vowel signs can
reorder visually:

```python
>>> word = "ക്ഷമിക്കണം"
>>> len(word)                              # 10 Unicode codepoints
10
>>> len(shape_word(word, font)["glyphs"])  # 6 shaped glyphs
6
```

ക്ഷ (4 codepoints: ക + ് + ഷ, plus the following vowel sign) shapes to a
single ligature glyph. Anything that just walks codepoints and looks up a
font's cmap directly will get this wrong.

## Fonts

This package doesn't bundle a font for its own distribution — bring your
own. Tested against [Manjari](https://fonts.google.com/specimen/Manjari)
and [Chilanka](https://fonts.google.com/specimen/Chilanka) (both SIL OFL,
free); any font with proper Malayalam GSUB/GPOS tables should work. No
GSUB/GPOS support generally means broken conjuncts — check your font choice
if shaped output looks wrong. The bundled *test* fixture is
`tests/fixtures/Manjari-Regular.ttf` (SIL OFL — see `tests/fixtures/OFL.txt`).

## Scope

Despite the name, nothing here is Malayalam-specific at the code level —
`shape_word` will happily shape Latin, Devanagari, or anything else
HarfBuzz and your font support. The name reflects the motivating use case
(there wasn't an existing stroke-order tool for Malayalam).

## License

MIT.
