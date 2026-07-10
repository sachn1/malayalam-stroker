# Roadmap

Things worth doing that aren't done yet — not commitments or a schedule,
just a running list so ideas raised in passing (in an issue, a chat, a
review comment) don't get lost. Move an item out once it's actually done
(delete it here, mention it in the README/CHANGELOG instead of duplicating
it forever).

## Docs & discoverability

- **A github.io page.** The README now has step-by-step instructions, but a
  dedicated GitHub Pages site could host the same content plus a *live*
  interactive version of `docs/CENTERING_EXPERIMENTS.md`'s worked example —
  a word typed in, with sliders/tabs to flip between raw → centered →
  smoothed → straightened in real time, instead of four static SVGs. Explicitly
  deferred for now (see that doc's intro) in favor of expanding the README
  first; revisit once the pipeline itself is stable enough that a fancier
  presentation is worth the upkeep.
- **Publish the packages.** Neither `js/` nor `python/` is published yet
  (`README.md`, `python/README.md`) — both `authors`/repo URLs are still
  placeholders. Once the API is stable enough to commit to: `npm publish`
  for the JS package, and a PyPI release for the Python one (currently
  positioned as a build-time-only tool, so this may never be worth doing
  for it specifically).

## Multi-language support

Everything Malayalam-specific currently lives in one place per layer:
`python/src/malayalam_stroker/_chars.py` (character inventory) and the two
committed JSON files (`js/src/glyph-data.json`, `stroke-data(.raw).json`).
Adding a second script (Tamil is the obvious next candidate, per early
conversations about this project) means:

- A `_chars_ta.py`-equivalent character inventory module, and a decision on
  whether `cli.py`/`build_glyph_data.py` become script-parametrized or get
  a sibling per script.
- Splitting the committed JSON data per script (`glyph-data.ml.json`,
  `glyph-data.ta.json`, ...) so a page using one language doesn't fetch
  another's data — see "Data size & deployment" in the README. The format
  is already per-cluster keyed, so this is a file-naming/build-tooling
  change, not a data-model rewrite.
- Re-auditing every place that currently assumes "the only script" — the
  segmentation regex bounds in `index.js`, the CLI's standalone-alphabet
  list, `validate_data.py`'s hardcoded filenames — for hidden Malayalam-only
  assumptions.
- A second recorder pass with native speakers of the new language, plus
  re-running the centering/straightening pipeline against a font that
  supports it.

## Data & scale

- **Git LFS**, once the committed JSON data (currently low hundreds of KB)
  grows into the tens of MB — from a second language, or a much larger
  font's outlines. See the README's "Data size & deployment" section for
  the full reasoning; not needed yet.
- **Prune `glyph-data.json`** to only the consonant+vowel-sign/conjunct
  combinations that occur in real Malayalam, instead of pre-shaping every
  combination HarfBuzz can produce (see README's "Status" section). Needs a
  real-word corpus to prune against first.

## Deployment

The library is fully static today (`index.js` fetches the two JSON files at
runtime; nothing is built server-side — see the README). Nothing here is
blocking, but worth deciding deliberately rather than by default once there's
a real hosted deployment target:

- A domain + hosting choice for a live demo (GitHub Pages is the free
  default; a custom domain is a separate, optional step on top of that).
- Cache headers / CDN in front of the JSON data files once real traffic
  exists — they're static and content-hashed-by-commit, so they're
  trivially cacheable, just not configured anywhere yet.

## Testing & tooling

- **Headless-browser coverage for `index.js`'s DOM-dependent code** — the
  actual SVG animation (`buildStage`, `traceSub`, `buildTracePath`) needs
  real `getTotalLength()`/`getPointAtLength()`, which jsdom doesn't
  implement, so it's currently only exercised manually via the demo. A
  Playwright-driven test (or visual-regression check) would close this gap;
  deliberately not added yet to avoid pulling in a browser-binary dependency
  for what's still a small project — see the discussion in the session that
  rebuilt `demo/jayasree.svg`, which hit this exact limitation.
- **Ligature coverage for the vowel signs that currently compose
  imperfectly** — ു/ൂ/ൃ and the reduced la-form fuse into a
  consonant-specific shape in real font rendering that generic mark
  composition can't reproduce (see README's "Composing combinations"
  section); they're recorded as separate atoms instead of true ligatures.
  Revisit if this becomes visually noticeable enough to matter.
