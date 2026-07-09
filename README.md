
# Jayasree ![ജയശ്രീ — animated stroke trace](demo/jayasree.svg)

### malayalam stroker

A JavaScript library for animating Malayalam script as handwriting — showing
*how* to write a letter or word, not just what it looks like. Think
[Hanzi Writer](https://hanziwriter.org/) but for Malayalam.

The JS package is self-contained: glyph shapes are pre-computed and bundled.
No server, no font file, no HarfBuzz at runtime.

## How it works

```
tools/build_glyph_data.py     ← run once (or when you change fonts)
        │
        ▼
js/src/glyph-data.json        ← font outlines + advance widths + composable
                                 mark recipes (commit this)

tools/stroke-recorder.html    ← native speakers draw centerline strokes
        │
        ▼
js/src/stroke-data.raw.json   ← hand-authored strokes, exactly as drawn
                                 (commit this — never overwritten by anything)
        │
        ▼
tools/process_strokes.py --preset=malayalam
        │
        ▼
js/src/stroke-data.json       ← centered + smoothed + ghost-straightened +
                                 composed (commit this — this is what loads)
        │
        ▼
js/src/index.js               ← self-contained animator; no runtime dependencies
```

Three committed JSON files power the widget:

- **`glyph-data.json`** — font-specific outlines used for the ghost letterform
  and cluster segmentation, plus a `marks` table (see below). Re-generate if
  you switch fonts.
- **`stroke-data.raw.json`** — font-agnostic, hand-authored centerline
  strokes, exactly as drawn. The source of truth; only `stroke-recorder.html`
  writes to it.
- **`stroke-data.json`** — the processed, composed, ready-to-load file.
  Generated from `stroke-data.raw.json` by `process_strokes.py`; regenerating
  it never touches the raw source, so re-processing with different settings
  is always possible without re-recording anything. This is the file
  `writer.loadStrokes()` fetches by default.

### Composing combinations instead of pre-shaping every one

Most Malayalam clusters — consonant+vowel-sign, consonant+virama,
conjunct+vowel-sign, and the reduced ya/va/la forms used in many
conjuncts — compose predictably from a small base + a reusable recipe,
rather than needing every combination individually shaped or hand-drawn.
`glyph-data.json`'s `marks` table captures this once per mark (derived from
how HarfBuzz auto-inserts a placeholder glyph when a mark has no preceding
base — see `tools/build_glyph_data.py`'s `_build_marks()` docstring for the
full derivation and its accuracy limits). `index.js` composes glyph outlines
from it at runtime; `process_strokes.py --expand` composes hand-drawn
*strokes* the same way, using whichever parts are already recorded. A
handful of vowel signs (ു/ൂ/ൃ) and the reduced la-form fuse into a shape
unique to the specific preceding consonant in real font shaping and can't be
reconstructed generically — those compose as separate (correct, just less
tightly kerned) parts rather than a true font ligature.

## Adding new characters

The common case — recording a stroke for a character that's missing one,
out of the ~2000 clusters `glyph-data.json` already covers:

```bash
python tools/build_standalone_recorder.py   # only if stroke-recorder.html changed
open tools/stroke-recorder.html             # or the standalone version, offline
```

Drop `glyph-data.json` in, pick a character from the dropdown (it'll show
the ghost outline automatically — no setup needed), draw, load your current
`stroke-data.raw.json` to merge with it, export, and save over
`js/src/stroke-data.raw.json`.

Rarer case — the character doesn't exist in `glyph-data.json` at all (a
combination outside the standard set `build_glyph_data.py` generates): add it
to that script's input list first (or use the recorder's "Add custom
cluster" field, though you'll be drawing without a ghost reference to trace
over), then regenerate:

```bash
cd python && poetry install
poetry run python ../tools/build_glyph_data.py
```

Either way, once `stroke-data.raw.json` has what you need:

```bash
python tools/process_strokes.py --preset=malayalam
```

regenerates `js/src/stroke-data.json` — the file the demo and the library
actually load. That's the only command needed after any recording session.

Stages can be run individually if you want to compare them —
`python tools/process_strokes.py --help` lists `--center`/`--smooth`/
`--straighten`/`--expand`, each independently toggleable.

## Quickstart

```bash
git clone https://github.com/your-username/malayalam-stroker
cd malayalam-stroker

# (optional) regenerate glyph-data.json for a different font:
cd python && poetry install
poetry run python ../tools/build_glyph_data.py /path/to/MyFont.ttf

# run the demo (static file server, no shaping backend needed):
python demo/serve.py
```

Open http://127.0.0.1:8000/demo/ — type any Malayalam word and watch it animate.

## Using the JS library

```js
import { createStrokeWriter } from "malayalam-stroker";

const writer = createStrokeWriter(document.getElementById("stage"));
await writer.load();          // fetches glyph-data.json once
await writer.loadStrokes();   // fetches stroke-data.json (optional, graceful no-op if absent)
await writer.play("നന്ദി");
```

Not published to npm yet. Copy `js/src/` into your project or serve it
locally — it's plain ES modules, no build step required.

Two extra options tune the trace: `speed` (font-units/second) and `tighten`
(inter-cluster spacing tightening — the font's own advance widths read as a
little loose for a handwriting UI; see `js/src/index.js`'s
`DEFAULT_TIGHTEN_FRACTION`).

## Repo layout

```
malayalam-stroker/
├── js/
│   ├── src/index.js               # main export — segmentation, composition, animation
│   ├── src/glyph-data.json        # pre-computed font outlines + marks table (commit)
│   ├── src/stroke-data.raw.json   # hand-authored strokes, source of truth (commit)
│   └── src/stroke-data.json       # processed, ready-to-load (commit — generated)
├── python/                        # build-time shaper + stroke-processing library (Poetry project)
│   └── src/malayalam_stroker/
│       ├── strokes.py             # HarfBuzz shaping
│       ├── geometry.py            # corner-aware smoothing
│       ├── centering.py           # gradient-ascent centering
│       ├── ghost_reference.py     # ghost-outline-guided straightening
│       └── stroke_compose.py      # multi-glyph + mark stroke composition
├── tools/
│   ├── build_glyph_data.py            # generates js/src/glyph-data.json
│   ├── process_strokes.py             # generates js/src/stroke-data.json
│   ├── stroke-recorder.html/.css/.js  # browser tool for authoring stroke-data.raw.json
│   └── build_standalone_recorder.py   # bundles the recorder into one offline file
├── demo/
│   ├── demo_index.html / demo.js / demo.css
│   ├── logo-preview.html          # standalone preview of the animated wordmark
│   └── serve.py
└── README.md
```

## Status

Early / v0.1.0. 200+ clusters are hand-authored; composition (see above)
extends real pen strokes to several thousand combinations built from them.
`glyph-data.json` currently pre-shapes every consonant+vowel-sign and
conjunct combination via HarfBuzz rather than pruning to only combinations
that occur in real Malayalam — fine at this prototyping stage, but a
planned cleanup once there's a real-word corpus to prune against.

## License

MIT, both packages.
