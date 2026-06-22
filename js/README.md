
# malayalam-stroker (JS)

Animates Malayalam text as handwriting — a pen traces each letter left to right,
over a faint ghost of the complete letterform.

Self-contained. No server. No font file at runtime. Glyph shapes are
pre-computed and bundled in `glyph-data.json`.

## Usage

```js
import { createStrokeWriter } from "malayalam-stroker";

const writer = createStrokeWriter(document.getElementById("stage"));
await writer.load();          // fetches glyph-data.json once
await writer.loadStrokes();   // fetches stroke-data.json (no-op if absent)
await writer.play("നന്ദി");   // any Malayalam Unicode text

writer.replay();   // play the same text again
writer.cancel();   // stop mid-animation
writer.destroy();  // cancel + clear the container
```

Not published to npm yet — copy `js/src/` into your project or serve it
locally. Plain ES modules, no build step required.

## Two data files

Both live in `js/` and should be committed to your repo:

| File | What it contains | Font-specific? |
|---|---|---|
| `src/glyph-data.json` | SVG outlines + advance widths for every cluster | Yes — re-run `tools/build_glyph_data.py` when you change fonts |
| `stroke-data.json` | Hand-authored centerline stroke paths | No — commit once, works across fonts |

When `stroke-data.json` has coverage for a cluster, the pen follows those
paths. Otherwise it falls back to tracing the outer contour of the font
outline.

## Regenerating glyph-data.json for a different font

```bash
cd python && poetry install
# defaults to the bundled Manjari-Regular.ttf:
poetry run python ../tools/build_glyph_data.py
# or supply your own:
poetry run python ../tools/build_glyph_data.py /path/to/MyFont.ttf
```

## Authoring stroke-data.json

Open `tools/stroke-recorder.html` in a browser, draw strokes over each ghost
glyph, and export. The output is keyed by Unicode cluster (`"ന"`, `"ക്ഷ"`).
Save it as `js/stroke-data.json` and commit.

## Configuring per-cluster behaviour

```js
import { createStrokeWriter, START_OVERRIDES, DIRECTION_OVERRIDES } from "malayalam-stroker";

// Where on the contour the pen starts (fallback mode only)
START_OVERRIDES["ന"] = "topmost";   // "leftmost" | "rightmost" | "topmost" | "bottommost" | 0..1 fraction
START_OVERRIDES["ക"] = ["leftmost", 0.1]; // per sub-contour array

// Which way around the contour the pen travels (fallback mode only)
DIRECTION_OVERRIDES["ന"] = "reverse";  // "forward" | "reverse"
```

## Styling

```css
.my-stage {
  --ms-ink-color:    #1a1a2e;   /* trace line */
  --ms-ghost-color:  #e0daf5;   /* faint letterform behind the trace */
  --ms-stylus-color: #e8b84b;   /* pen-tip dot */
}
```

`.ms-ghost` and `.ms-stroke` are the two CSS classes on the rendered SVG.
Skip the default `style.css` entirely and write your own if you prefer.

## License

MIT.


## Install

```bash
npm install malayalam-stroker
```

## Usage

```js
import { createStrokeWriter } from "malayalam-stroker";
import "malayalam-stroker/style.css"; // optional default styling

const writer = createStrokeWriter(document.getElementById("stage"));

const trace = await fetch("/api/trace/നന്ദി").then((r) => r.json());
await writer.play(trace);

writer.replay();          // play the same trace again
writer.cancel();          // stop mid-animation
writer.destroy();         // cancel + clear the container
```

See [`examples/demo.html`](examples/demo.html) for a minimal working
page — one pre-shaped word, no server, just open the file. It does not
have a text input; shaping a word you type requires a server (HarfBuzz
needs a font file on disk), so for an actual "type any word" experience
see [`../demo`](../demo) at the repo root instead
(`python demo/serve.py`, then open the page — it has a real, editable
text field wired to live shaping).

## Where does the JSON come from?

Anywhere that can run the shaping pipeline:

- The [Python package](../python) (`pip install malayalam-stroker`) —
  typically run server-side, since it needs HarfBuzz + a font file.
- Precomputed JSON checked into your app for a fixed alphabet/word list.
- Any other implementation that produces the same shape (see below) —
  this package doesn't care how the JSON was made.

## StrokeTrace JSON shape

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

`d` is an SVG path string in y-down coordinates. `x`/`y` are pen-position
offsets to translate each glyph into place.

## Configuring the trace

```js
const writer = createStrokeWriter(stage, {
  speed: 6000,   // font-units of outer contour length traced per second
});

writer.play(trace, { speed: 1.8 }); // per-call speed multiplier
```

### Start point — `START_OVERRIDES`

Controls where on the outer contour the pen begins for each glyph.
Find glyph names with `trace.glyphs.map(g => g.glyphName)`.

```js
import { createStrokeWriter, START_OVERRIDES } from "malayalam-stroker";

START_OVERRIDES["n1"] = "topmost";      // start at the topmost point
START_OVERRIDES["m1"] = 0.25;           // start 25% along the contour
START_OVERRIDES["k1sh"] = ["leftmost", 0.1]; // per sub-contour, if the glyph has multiple
```

Accepted values: `"leftmost"` (default) | `"rightmost"` | `"topmost"` |
`"bottommost"` | a `0..1` fraction of the contour's arc-length | an array
of the above, one entry per outer sub-contour.

### Direction — `DIRECTION_OVERRIDES`

Controls which way around the contour the pen travels.

```js
import { createStrokeWriter, START_OVERRIDES, DIRECTION_OVERRIDES } from "malayalam-stroker";

DIRECTION_OVERRIDES["n1"] = "reverse";  // go the other way around
DIRECTION_OVERRIDES["lh"] = ["forward", "reverse"]; // per sub-contour
```

Accepted values: `"forward"` (default, follows the font's contour direction)
| `"reverse"` (traces the contour in the opposite direction).

For most Malayalam letters, one of the two directions will visually match
how a native writer draws the letter. Set both overrides together to dial
in the exact start point and direction that feel natural.

## Styling

Two CSS classes on the rendered SVG, themeable via CSS custom properties:

```css
.my-stage {
  --ms-ink-color:    #1a1a2e;   /* trace line colour */
  --ms-ghost-color:  #e0daf5;   /* ghosted letter behind the trace */
  --ms-stylus-color: #e8b84b;   /* pen tip dot */
}
```

`.ms-stroke` is the animated trace line; `.ms-ghost` is the faint
complete letterform shown behind it. `stroke-width` on `.ms-stroke` is
set automatically in JS (scales with `unitsPerEm`) but can be overridden
in CSS. Skip `malayalam-stroker/style.css` entirely and write your own
rules if you prefer.

## License

MIT.
