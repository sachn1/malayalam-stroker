
# malayalam-stroker ![malayalam-stroker — writing the letter മ](demo/ma.gif)

A JavaScript library for animating Malayalam script as handwriting — showing
*how* to write a letter or word, not just what it looks like. Think
[Hanzi Writer](https://hanziwriter.org/) but for Malayalam.

The JS package is self-contained: glyph shapes are pre-computed and bundled.
No server, no font file, no HarfBuzz at runtime.

## How it works

```
tools/build_glyph_data.py   ← run once (or when you change fonts)
        │
        ▼
js/src/glyph-data.json      ← font outlines + advance widths (commit this)

tools/stroke-recorder.html  ← native speakers draw centerline strokes
        │
        ▼
js/stroke-data.json         ← hand-authored stroke paths (commit this)
        │
        ▼
js/src/index.js             ← self-contained animator; no runtime dependencies
```

Two committed JSON files power the widget:

- **`glyph-data.json`** — font-specific outlines used for the ghost letterform
  and cluster segmentation. Re-generate if you switch fonts.
- **`stroke-data.json`** — font-agnostic, hand-authored centerline strokes that
  animate like a pen. Commit once; works across fonts. Falls back to
  outer-contour tracing when missing.

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

## Repo layout

```
malayalam-stroker/
├── js/                    # the JS animator library
│   ├── src/index.js       # main export
│   ├── src/glyph-data.json  # pre-computed font outlines (commit)
│   └── stroke-data.json   # hand-authored stroke paths (commit when ready)
├── python/                # build-time shaper (Poetry project)
│   └── src/malayalam_stroker/
├── tools/
│   ├── build_glyph_data.py    # generates js/src/glyph-data.json
│   └── stroke-recorder.html   # browser tool for authoring stroke-data.json
├── demo/
│   ├── demo_index.html
│   └── serve.py
└── README.md
```

## Status

Early / v0.1.0. The font-outline fallback works end-to-end; hand-authored
strokes in `stroke-data.json` are not yet populated (the recorder tool is
ready — someone needs to sit down and draw them).

## License

MIT, both packages.
