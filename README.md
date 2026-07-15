
# Jayasree ![ജയശ്രീ - animated stroke trace](demo/jayasree.svg)

### malayalam stroker

A JavaScript library for animating Malayalam script as handwriting - showing
*how* to write a letter or word, not just what it looks like. Think
[Hanzi Writer](https://hanziwriter.org/) but for Malayalam.

**Live site & demo:** <https://sachn1.github.io/jayasree/> -
deployed from this repo by `.github/workflows/pages.yml` (one-time setup:
repo Settings → Pages → Source: *GitHub Actions*).

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
                                 (commit this - never overwritten by anything)
        │
        ▼
tools/process_strokes.py --preset=malayalam
        │
        ▼
js/src/stroke-data.json       ← centered + smoothed + ghost-straightened +
                                 composed (commit this - this is what loads)
        │
        ▼
js/src/index.js               ← self-contained animator; no runtime dependencies
```

Three committed JSON files power the widget:

- **`glyph-data.json`** - font-specific outlines used for the ghost letterform
  and cluster segmentation, plus a `marks` table (see below). Re-generate if
  you switch fonts.
- **`stroke-data.raw.json`** - font-agnostic, hand-authored centerline
  strokes, exactly as drawn. The source of truth; only `stroke-recorder.html`
  writes to it.
- **`stroke-data.json`** - the processed, composed, ready-to-load file.
  Generated from `stroke-data.raw.json` by `process_strokes.py`; regenerating
  it never touches the raw source, so re-processing with different settings
  is always possible without re-recording anything. This is the file
  `writer.loadStrokes()` fetches by default.

### Composing combinations instead of pre-shaping every one

Most Malayalam clusters - consonant+vowel-sign, consonant+virama,
conjunct+vowel-sign, and the reduced ya/va/la forms used in many
conjuncts - compose predictably from a small base + a reusable recipe,
rather than needing every combination individually shaped or hand-drawn.
`glyph-data.json`'s `marks` table captures this once per mark (derived from
how HarfBuzz auto-inserts a placeholder glyph when a mark has no preceding
base - see `tools/build_glyph_data.py`'s `_build_marks()` docstring for the
full derivation and its accuracy limits). `index.js` composes glyph outlines
from it at runtime; it composes hand-drawn *strokes* the same way
(recursively, so a multi-link mark chain like ദ + ്യ + ു resolves down to
its atoms instead of stopping at the first not-yet-cached link), using
whichever parts are already recorded. Compound vowel signs (ൊ/ോ/ൌ)
decompose into simpler marks first - matching Unicode's own canonical
decomposition - rather than needing a stroke of their own. A handful of
vowel signs (ു/ൂ/ൃ) and the reduced la-form fuse into a shape unique to the
specific preceding consonant in real font shaping and can't be
reconstructed generically - those compose as separate (correct, just less
tightly kerned) parts rather than a true font ligature.

See **`docs/CENTERING_EXPERIMENTS.md`** for the full depth on this - how
centering/smoothing/straightening work, and two real composition bugs this
project shipped and fixed (an anchor-correction regression, and a
segmentation ordering bug), kept as worked examples for anyone extending
this further.

## Creating handwriting from scratch

Step by step, starting from nothing but a font file. (If `glyph-data.json`
and `stroke-data.raw.json` already exist for your font - the common case -
skip to step 2.)

### 1. Generate `glyph-data.json` (once per font)

```bash
make install
make build-glyph-data FONT=/path/to/YourFont.ttf
```

Shapes the full Malayalam character inventory
(`python/src/malayalam_stroker/_chars.py`) through HarfBuzz and writes every
cluster's outline, advance width, and mark-composition recipe to
`js/src/glyph-data.json`. This is what supplies the ghost outline you trace
over in step 2, and what `stroke-data.json` gets centered/straightened
against in step 3. Re-run it whenever you switch fonts - see
"Using a different font" below for what does and doesn't carry over.

### 2. Record strokes

`stroke-recorder.html`'s dropdown defaults to a **reduced set** - only the
~290-ish atoms that genuinely need a hand-drawn stroke (standalone
characters, the vowel signs that fuse into consonant-specific shapes, and
true ligature conjuncts) - not the full ~2050 clusters `glyph-data.json`
covers, most of which compose automatically from those atoms (see
"Composing combinations" above). Each entry is marked ✓ (recorded) or ○
(missing); a "⇥ Next missing" button jumps to the next gap. Check "Show all
clusters" to browse the full ~2050 (useful for spot-checking a composed
result against its ghost).

```bash
make build-recorder                # only if stroke-recorder.html changed
open tools/stroke-recorder.html    # or the standalone version, offline
```

**With a ghost font (the normal case)** - the character is already one of
the atoms `glyph-data.json` covers:

1. Drop `glyph-data.json` into the recorder.
2. Pick a character from the dropdown - its ghost outline appears
   automatically, no setup needed.
3. Trace it in stroke order.
4. Load your existing `stroke-data.raw.json` (if any) to merge into it
   rather than starting over.
5. Export, and save the result over `js/src/stroke-data.raw.json`.

**Without a ghost font (blind)** - a combination outside the standard set
`build_glyph_data.py` generates, so it has no outline in `glyph-data.json`
at all. Two options:

- Add it to `build_glyph_data.py`'s input list and re-run step 1 so it gets
  a real ghost outline like everything else - preferred for anything meant
  to stay in the project, since centering/straightening (step 3) need a
  reference outline to work against.
- Or use the recorder's "Add custom cluster" field to draw it freehand with
  no outline to trace over. Useful for a quick one-off, but the result
  skips centering/straightening entirely (there's nothing to center or
  straighten against) - expect it to look rougher than a traced stroke.

### 3. Process

```bash
make process-strokes
```

Centers each stroke against `glyph-data.json`'s outline (gradient ascent
onto the ink's centerline), smooths it (corner-aware spline fit), straightens
it against detected straight ghost edges, and composes any cluster still
missing a stroke from parts that do exist. Writes `js/src/stroke-data.json`
- the only stroke file `index.js` loads at runtime; `stroke-data.raw.json`
is never touched, so re-processing with different settings is always
possible without re-recording. Stages can be run individually if you want
to compare them - `python tools/process_strokes.py --help` lists
`--center`/`--smooth`/`--straighten`/`--expand`, each independently
toggleable. See `docs/CENTERING_EXPERIMENTS.md` for a worked example of
each stage's effect on a real stroke.

### 4. See it animate

```bash
make demo
```

Open http://127.0.0.1:8000/demo/ and type the word.

### Using a different font

Are the hand-drawn strokes specific to Manjari (the font this project was
recorded against), or portable to any Malayalam font? They're centerline
traces of Manjari's letterforms, so in that sense yes - they're tuned to
Manjari's specific proportions, stroke count, and junction points. But
`process_strokes.py`'s centering and straightening stages re-fit each stroke
against *whichever* font's `glyph-data.json` you feed them: centering nudges
points onto the new font's ink, straightening re-aligns straight runs to the
new font's actual edges. So swapping fonts and re-running
`process_strokes.py` (no re-recording) pulls existing strokes toward the new
font's shape automatically - but only as far as a bounded nudge (see
`centering.py`'s `MAX_SHIFT_FU`); it won't invent a different stroke count
or fix a letterform that's structurally different from Manjari's.

- **Similar-style font**: regenerate `glyph-data.json` for it (step 1) and
  re-run `process_strokes.py` (step 3) - no re-recording needed.
- **Structurally different font** (e.g. one where a letter has an extra loop
  or a fundamentally different construction): expect to re-record the atoms
  that genuinely differ, and spot-check the rest against the new ghost.

### Data size & deployment

The library is fully static: `index.js` `fetch()`s `glyph-data.json` and
`stroke-data.json` at runtime, and nothing is built or generated
server-side - deploying is just serving `js/src/` (or your own bundle of it)
as static files. Both JSON files are committed to the repo and currently
small (low hundreds of KB combined); that's fine to check into git as-is.

If a second language's data gets added, or a much larger font's outlines
push the combined size into the tens of MB, plain git starts to get slow to
clone/diff. At that point, two options worth considering rather than
letting it grow unchecked:

- **Git LFS** for the JSON data files - keeps the repo itself small; git
  only fetches the actual blobs on checkout.
- **Split per-script** (`glyph-data.ml.json`/`stroke-data.ml.json`,
  `glyph-data.ta.json`/... for a hypothetical Tamil addition) so a page using
  one language doesn't fetch another's data. Nothing on the Python or JS
  side does this yet - `_chars.py`'s character inventory and the two
  committed JSON files are Malayalam-only today - but the format is
  already per-cluster keyed data, so splitting it by script is a
  file-naming/build-tooling change, not a data-model rewrite.

## Quickstart

```bash
git clone https://github.com/sachn1/jayasree
cd jayasree
make install

# (optional) regenerate glyph-data.json for a different font:
make build-glyph-data FONT=/path/to/MyFont.ttf

# run the demo (static file server, no shaping backend needed):
make demo
```

Open http://127.0.0.1:8000/demo/ - type any Malayalam word and watch it animate.

## Using the JS library

```js
import { createStrokeWriter } from "jayasree";

const writer = createStrokeWriter(document.getElementById("stage"));
await writer.load();          // fetches glyph-data.json once
await writer.loadStrokes();   // fetches stroke-data.json (optional, graceful no-op if absent)
await writer.play("നന്ദി");
```

```bash
npm install jayasree
```

Published at [npmjs.com/package/jayasree](https://www.npmjs.com/package/jayasree).
`.github/workflows/publish.yml` publishes future version bumps automatically
on a version tag push (or a manual run), authenticated via npm Trusted
Publishing (OIDC) - no token stored in this repo. Until the trusted publisher
is configured on npmjs.com, cut releases with `npm publish --access public`
from `js/`. You can still copy `js/src/` into your project or serve it
locally instead - it's plain ES modules, no build step required.

### Configurable options

`createStrokeWriter(container, options)` accepts:

| Option | Default | What it does |
| --- | --- | --- |
| `speed` | `6000` | Nominal pen speed, in font-units/second. Higher = faster trace. |
| `tighten` | `0.06` | Inter-cluster spacing tightening, as a fraction of `unitsPerEm` trimmed from each cluster's advance - the font's own advance widths read as a little loose for a handwriting UI. `0` reproduces the font's raw spacing. |
| `strokeWidth` | `0.022` | Ink line thickness, as a fraction of `unitsPerEm`. |
| `outlineOnly` | `false` | Ignore authored strokes entirely and always animate the outer-contour outline fallback - useful for a consistent tracing style independent of authoring coverage (e.g. a wordmark mixing authored and not-yet-authored clusters). |
| `glyphData` | `null` | Pre-loaded glyph data object, skipping `load()`'s own fetch. |

```js
const writer = createStrokeWriter(document.getElementById("stage"), {
  speed: 8000,       // faster pen
  strokeWidth: 0.03,  // thicker ink line
});
```

`play(text, playOptions)` and `replay(playOptions)` additionally accept:

| Option | Default | What it does |
| --- | --- | --- |
| `speed` | `1` | Speed *multiplier* for this call only (applied on top of the writer's own `speed`). `2` traces twice as fast. |
| `count` | `1` | Number of times to trace the word in a row, pausing briefly between repeats. A new `play()`/`replay()` call, or `cancel()`, stops the sequence before its next repeat. |

```js
await writer.play("നന്ദി", { count: 3 });   // trace it three times in a row
await writer.replay({ speed: 0.5, count: 2 }); // replay slower, twice
```

### Detecting approximated clusters

Not every cluster has (or can be composed from) recorded handwriting - when
one doesn't, `play()` falls back to animating the printed glyph's own outer
contour instead, which looks like tracing a border rather than real
handwriting. `getFallbackClusters()` returns which clusters from the most
recent `play()`/`replay()` call did this, so a caller can tell the user the
trace is only approximated for part of a word instead of silently rendering
a border-trace as if it were normal handwriting:

```js
await writer.play("ഖ്ര");
if (writer.getFallbackClusters().length) {
  // e.g. ["ഖ്ര"] - no authored stroke, and no composable mark recipe
  // (subjoined-ra) to build one from other recordings.
  showNote("Some strokes are approximated - handwriting for this exact letter combination isn't recorded yet.");
}
```

## Repo layout

```
jayasree/
├── js/
│   ├── src/index.js               # main export - segmentation, composition, animation
│   ├── src/glyph-data.json        # pre-computed font outlines + marks table (commit)
│   ├── src/stroke-data.raw.json   # hand-authored strokes, source of truth (commit)
│   └── src/stroke-data.json       # processed, ready-to-load (commit - generated)
├── python/                        # build-time shaper + stroke-processing library (Poetry project)
│   ├── src/malayalam_stroker/
│   │   ├── cli.py                 # `shape`/`alphabet` CLI (see python/README.md)
│   │   ├── strokes.py             # HarfBuzz shaping
│   │   ├── geometry.py            # corner-aware smoothing
│   │   ├── centering.py           # gradient-ascent centering
│   │   ├── ghost_reference.py     # ghost-outline-guided straightening
│   │   └── stroke_compose.py      # multi-glyph + mark stroke composition
│   └── tests/snapshots/           # committed data-integrity snapshot (see "Data integrity")
├── tools/
│   ├── build_glyph_data.py            # generates js/src/glyph-data.json
│   ├── process_strokes.py             # generates js/src/stroke-data.json
│   ├── validate_data.py               # structural validation + content-snapshot tooling
│   ├── stroke-recorder.html/.css/.js  # browser tool for authoring stroke-data.raw.json
│   └── build_standalone_recorder.py   # bundles the recorder into one offline file
├── demo/
│   ├── index.html / demo.js / demo.css
│   ├── logo-preview.html          # standalone preview of the animated wordmark
│   └── serve.py
├── docs/
│   ├── CENTERING_EXPERIMENTS.md   # pipeline architecture + experiments log
│   ├── centering-example/         # before/after SVGs referenced from that doc
│   └── ROADMAP.md                 # planned/not-yet-done work
├── tests/index.test.js             # vitest - index.js's composition/segmentation engine
├── index.html                      # landing page (GitHub Pages site root)
├── .github/workflows/ci.yml        # thin wrapper around `make ci-py` / `make ci-js`
├── .github/workflows/pages.yml     # deploys landing page + demo + recorder to GitHub Pages
├── Makefile                        # single source of truth for local + CI commands
├── pyproject.toml                  # ruff config only (repo root - see file header for why)
├── eslint.config.js / vitest.config.js / package.json   # repo-level JS dev tooling
├── CONTRIBUTING.md                 # ground rules: code, tests, data integrity, new languages
├── LICENSE / LICENSE-DATA          # MIT (code) / CC BY 4.0 (stroke data + artwork)
└── README.md
```

## Development

A `Makefile` at the repo root is the single source of truth for the
commands below - `.github/workflows/ci.yml` calls `make ci-py`/`make ci-js`
rather than duplicating them, so local and CI behavior can't drift apart.
Run `make help` for the full list.

```bash
make install       # poetry install (python/) + npm ci (repo root)
make lint           # ruff (lint + format check) + interrogate + eslint
make test           # pytest (+ coverage) + vitest (+ coverage)
make validate-data   # structural check of the 3 committed JSON data files
make precommit       # every pre-commit hook against all files
make ci              # everything CI runs, both languages, in one shot
```

Individual pieces are also available split by language (`make lint-py`,
`make lint-js`, `make test-py`, `make test-js`, ...) or as `make ci-py`/
`make ci-js` - exactly what each CI job runs.

Both linters also run automatically via `pre-commit` (`.pre-commit-config.yaml`).
DOM-dependent parts of `index.js` (the actual SVG animation) aren't covered
by the JS unit tests - they need real browser SVG geometry APIs that jsdom
doesn't implement; verify those with the demo (`make demo`) or a
Playwright-driven check instead.

## Data integrity

The hand-authored strokes in `stroke-data.raw.json` are the actual content
of this project - everything else (composition, centering, smoothing,
straightening) is derived from them. Two checks guard against that data
being silently lost or corrupted, whether by an editing mistake, a bad
merge, or (since the recorder is a plain client-side HTML page anyone can
open against a checked-out repo) a malicious or buggy export:

- **`tools/validate_data.py`** - structural validation of all three
  committed JSON files: every stroke has a well-formed SVG `d` string, every
  cluster has the keys it's supposed to, and every hand-authored cluster in
  `stroke-data.raw.json` actually survived into `stroke-data.json`. Run via
  `make validate-data`; wired into pre-commit and CI, so a commit
  that corrupts the data structurally is rejected before it lands.
- **`python/tests/test_data_snapshot.py`** - a content snapshot
  (`python/tests/snapshots/stroke_data_raw_snapshot.json`, a hash per
  cluster, built by hashing functions that live in `validate_data.py`
  alongside the structural checks above) asserts no previously-recorded
  cluster in
  `stroke-data.raw.json` goes missing or silently changes shape. Adding a
  new cluster doesn't fail the test - only losing or altering an existing
  one does. If a change is intentional (a genuine re-recording), regenerate
  the snapshot with `make update-snapshot` and commit the
  result alongside the data change, so the diff is explicit and reviewable.

Both run in CI (`.github/workflows/ci.yml`) on every push, alongside the
regular Python/JS test suites.

## Status

Early / v0.1.0. ~290 atoms are hand-authored (see "Composing combinations"
above); composition extends them to the ~2050 clusters `glyph-data.json`
covers. `glyph-data.json` currently pre-shapes every consonant+vowel-sign
and conjunct combination via HarfBuzz rather than pruning to only
combinations that occur in real Malayalam - fine at this prototyping stage,
but a planned cleanup once there's a real-word corpus to prune against.
See **`docs/ROADMAP.md`** for this and other not-yet-done work (a github.io
docs site, multi-language support, Git LFS, deployment, ...).

## License & credit

- **Code** - MIT ([LICENSE](LICENSE)), both packages.
- **Hand-drawn stroke data & generated artwork** (`stroke-data*.json`, the
  animated wordmark, the pipeline illustrations) - [CC BY
  4.0](https://creativecommons.org/licenses/by/4.0/): free to use and build
  on, **with credit**. Please attribute as *"Jayasree / malayalam-stroker" by
  Sachin Nandakumar*, with a link back to this repository. See
  [LICENSE-DATA](LICENSE-DATA) for exactly which files this covers.
- **Letterforms** - `glyph-data.json` (and the outlines inside the generated
  SVGs) derive from the [Manjari](https://smc.org.in/fonts/manjari) typeface
  (SIL OFL 1.1) by Santhosh Thottingal & Swathanthra Malayalam Computing.
