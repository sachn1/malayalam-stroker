# malayalam-stroker (JS)

Renders a `StrokeTrace` JSON (produced by the companion
[`malayalam-stroker` Python package](../python)) as an animated
left-to-right ink reveal — each glyph's solid letterform fills in from
its true leftmost point, no outline/border phase.

No fetch, no modal, no app-specific markup baked in. Bring your own
container element and your own JSON; wire it up however your app needs.

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

## Configuring the reveal

```js
const writer = createStrokeWriter(stage, {
  speed: 1100,            // font-units of glyph width per second
  revealPadRatio: 0.12,   // vertical clip padding, fraction of unitsPerEm
  minGlyphDurationMs: 180,
});

writer.play(trace, { speed: 1.8 }); // per-call speed multiplier, e.g. a "fast" button
```

The reveal always starts at each glyph's real leftmost point — measured
with the browser's native `path.getBBox()`, not whatever vertex happens
to come first in the font's path data. See the comment block at the top
of `src/index.js` if you want to change the reveal direction (e.g.
top-to-bottom) or otherwise customize the animation.

## Styling

Two CSS classes on the rendered SVG, themeable via CSS custom
properties:

```css
.my-stage {
  --ms-ink-color: #1a1a2e;
  --ms-ghost-color: #e0daf5;
}
```

`.ms-fill` is the glyph ink; `.ms-ghost` is a faint full-word preview
shown behind it. Skip `malayalam-stroker/style.css` entirely and write
your own rules against these two classes if you'd rather not use CSS
custom properties.

## License

MIT.
