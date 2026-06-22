# malayalam-stroker

Two small packages, one job: turn Malayalam (or any HarfBuzz-shapeable
script) text into an animated stroke-trace / handwriting widget.

- **[`python/`](python)** — `pip install malayalam-stroker`. Shapes text
  against a font (fontTools + uharfbuzz) and outputs per-glyph SVG path
  JSON. Runs server-side, since shaping needs a font file on disk.
- **[`js/`](js)** — `npm install malayalam-stroker`. Takes that JSON and
  animates it client-side as a left-to-right ink reveal.

Neither package depends on the other at the code level — the contract
between them is just the `StrokeTrace` JSON shape, documented in both
READMEs. Use one without the other if that's all you need (e.g. the
Python package alone for a stroke-order dataset; the JS package alone
if you're generating/precomputing JSON some other way).

## Why this exists

There's no equivalent of [Hanzi Writer](https://hanziwriter.org/) (the
well-known CJK stroke-order JS library) for Malayalam. This is a first
attempt at filling that gap, starting from a real integration
([lingua·ആലയം](https://github.com/sachn1/linguaalayam), a Malayalam
dictionary app) as the reference implementation.

## Quickstart

```bash
# Server-side: shape a word
pip install malayalam-stroker
python -m malayalam_stroker Manjari-Regular.ttf "നന്ദി" > trace.json
```

```js
// Client-side: animate it
import { createStrokeWriter } from "malayalam-stroker";
const writer = createStrokeWriter(document.getElementById("stage"));
writer.play(await fetch("/trace.json").then(r => r.json()));
```

## Try it

```bash
pip install -e python/
python demo/serve.py
```

Open http://127.0.0.1:8000/demo/ — type any Malayalam word, press Trace.
This is the only piece in the repo that needs a server running: shaping
happens server-side (HarfBuzz needs a font file on disk), so a plain
static HTML page can't shape arbitrary typed text on its own. See
`js/examples/demo.html` for the simpler static-JSON version (one
pre-shaped word, no server, just `open` the file).

## Status

Early / v0.1.0. Extracted from a single real-world integration, not yet
battle-tested across many fonts or many consuming apps. Issues and PRs
welcome once this is public — see CONTRIBUTING below.

## Repo layout

```
malayalam-stroker/
├── python/        # PyPI package: malayalam-stroker
├── js/            # npm package: malayalam-stroker
├── demo/          # interactive live-typing demo (needs `python demo/serve.py`)
└── README.md      # this file
```

Monorepo, not two separate repos — the two packages version together
and share the same JSON contract, so keeping them in one place avoids
drift between them. If that stops being true (e.g. the JS package grows
its own independent release cadence, or someone wants to consume just
one without cloning both), splitting is straightforward later.

## Publishing checklist (not yet done)

- [ ] Confirm `your-name-here` / `your-username` placeholders replaced
      throughout (pyproject.toml, package.json, LICENSE files)
- [ ] Re-verify `malayalam-stroker` still free on PyPI + npm at publish
      time (checked clear as of this writing, but registries change)
- [ ] `python/`: `python -m build`, `twine upload dist/*`
- [ ] `js/`: `npm publish`
- [ ] Tag a GitHub release once pushed
- [ ] Add CI (GitHub Actions: pytest for python/, a basic Playwright
      smoke test for js/) — not included yet, worth adding before v1.0

## License

MIT, both packages.
