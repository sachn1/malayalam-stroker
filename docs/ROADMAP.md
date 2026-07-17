# Roadmap

Things worth doing that aren't done yet - not commitments or a schedule,
just a running list so ideas raised in passing (in an issue, a chat, a
review comment) don't get lost. Move an item out once it's actually done
(delete it here, mention it in the README/CHANGELOG instead of duplicating
it forever).

## Docs & discoverability

- **Live pipeline explorer on the Pages site.** The GitHub Pages site
  (landing page + demo, deployed by `.github/workflows/pages.yml`) shows the
  worked example as four static SVGs; a *live* version - a word typed in,
  with sliders/tabs to flip between raw → centered → smoothed → straightened
  in real time - is still open. Revisit once the pipeline is stable enough
  that a fancier presentation is worth the upkeep.
- **Publish the Python package**, if it's ever worth it. `js/` publishes to
  npm now (Trusted Publishing via `.github/workflows/publish.yml`); `python/`
  is still deliberately unpublished - a build-time-only tool
  (`python/README.md`), so this may never be worth doing for it specifically.

## Smoothing: reduce spurious hard corners

Raised in passing: smoothed strokes (`geometry.py`'s `smooth_stroke`) still
show more hard corners than expected, even accounting for the fact that
corner preservation is deliberate (see `docs/CENTERING_EXPERIMENTS.md`'s
smoothing section - a single global spline through a genuine corner
overshoots into a spurious loop, which is the whole reason corners are
detected and split on rather than smoothed through). The question is
whether the *detection* is over-eager, not whether corners should exist
at all.

**Likely root cause, from reading `split_at_corners`/`turn_angles`:**
corner detection runs on `CORNER_ANGLE_DEG` (50°), a flat angle threshold
between adjacent RDP-simplified waypoints - but it doesn't account for how
far apart those waypoints are. Two waypoints close together (common in a
tightly-curved section like a loop or curl, which Malayalam letterforms
have a lot of) need only a small physical deviation to register a large
*angle*, so a continuously-curving-but-tight section can trip the same
threshold a genuine sharp reversal does. That's a scale/noise-sensitivity
problem inherent to raw-angle corner detection, not a bug exactly, but
possibly tuned too sensitively.

**Quick empirical check already done** (read-only, not implemented):
re-ran `split_at_corners` against a 40-cluster sample of real recorded
strokes from `stroke-data.raw.json`, varying `CORNER_ANGLE_DEG`:

| threshold | avg pieces/stroke |
|---|---|
| 50° (current) | 2.45 |
| 60° | 2.00 |
| 70° | 1.96 |
| 80° | 1.91 |

Real, measurable effect, with diminishing returns past 60°. But piece
count isn't the same as visual quality - raising the threshold too far
risks under-detecting genuine corners and reintroducing the exact
spurious-bulge failure mode this design exists to avoid. This needs a
human's eye (ideally the project owner, a native writer, per this
project's usual bar for judging letterform correctness) comparing
before/after renders across a representative sample, not just a piece
count.

**Feasible next steps, in order of risk:**

1. Try `CORNER_ANGLE_DEG` in the 60-65° range first - single-constant
   change, cheapest to test, matches where the empirical curve above
   already flattens out.
2. If that's not enough on its own, make corner detection *curvature-aware*
   instead of raw-angle: normalize the turning angle by the local segment
   length (or equivalently, threshold on angle-per-arc-length) so a tight
   continuous curve and a genuine sharp reversal are told apart by their
   actual curvature, not just by how closely RDP happened to space
   waypoints there. More correct, more implementation/test effort.
3. Retune `rdp_epsilon` (20.0) jointly with whichever of the above lands -
   it controls how many waypoints survive simplification before corner
   detection ever runs, so it interacts with both.

**Validation plan:** regenerate `stroke-data.json` from the existing
`stroke-data.raw.json` corpus (`make process-strokes`, no re-recording
needed) with each candidate change, and visually compare a representative
sample - not just ജ (the one worked example currently in
`docs/ARCHITECTURE.md`), since a single letter won't surface every corner
shape Malayalam script produces. `test_geometry.py` should also grow a
regression test once a concrete change lands, mirroring how the existing
Catmull-Rom-tangent fix already has one
(`test_straight_line_through_a_curved_piece_stays_straight`).

Scoped as a separate PR, not blocking anything else - this is a quality
tuning pass on already-shipped, already-working smoothing, not a bug fix.

## Learning features

- **"Vanilla form" tooltips for fused/compound clusters** (opt-in, e.g.
  `explain: true` on `createStrokeWriter`; default off). Malayalam can write
  the same thing fused or spelled out - a conjunct like ഴ്ച where ച written bellow ഴ is nothing but ഴ + ് + ച and a learner meeting the fused shape has no way to know that. A small tap/click
  affordance (ⓘ per cluster; hover alone won't work on tablets) showing the
  cluster's parts *as rendered glyphs* (standalone entries already exist in
  glyph-data.json) bridges that gap: "this shape, in its vanilla form, is
  these parts."

  Deliberately curated, not blanket: per the project owner, only *some*
  cluster types genuinely confuse (ു/ൂ-type fused vowel signs, chandrakkala
  conjuncts, ...), and they'll label/select which categories warrant a
  tooltip - so the design needs an inclusion list (by mark/cluster type, not
  per-cluster hand-authoring), not "tooltip on everything."

  Implementation sketch: decomposition comes free from the cluster string
  itself (the *text-level* Unicode sequence - correct even for true
  ligatures like ക്ഷ where stroke composition is bypassed); the only new
  data is a small display-name table for marks (chandrakkala, each matra,
  anusvaram, ...). Also expose the raw data as a public
  `writer.explain(cluster)` API so embedders can build their own UI.
  Optional later flourish (not the core of the feature): tag composed
  strokes with their source character so the tooltip can highlight which
  strokes belong to which part.

## Multi-language support

Everything Malayalam-specific currently lives in one place per layer:
`python/src/jayasree/_chars.py` (character inventory) and the two
committed JSON files (`js/src/glyph-data.json`, `stroke-data(.raw).json`).
Adding a second script (Tamil is the obvious next candidate, per early
conversations about this project) means:

- A `_chars_ta.py`-equivalent character inventory module, and a decision on
  whether `cli.py`/`build_glyph_data.py` become script-parametrized or get
  a sibling per script.
- Splitting the committed JSON data per script (`glyph-data.ml.json`,
  `glyph-data.ta.json`, ...) so a page using one language doesn't fetch
  another's data - see "Data size & deployment" in the README. The format
  is already per-cluster keyed, so this is a file-naming/build-tooling
  change, not a data-model rewrite.
- Re-auditing every place that currently assumes "the only script" - the
  segmentation regex bounds in `index.js`, the CLI's standalone-alphabet
  list, `validate_data.py`'s hardcoded filenames - for hidden Malayalam-only
  assumptions.
- A second recorder pass with native speakers of the new language, plus
  re-running the centering/straightening pipeline against a font that
  supports it.

## Data & scale

- **Git LFS**, once the committed JSON data (currently low hundreds of KB)
  grows into the tens of MB - from a second language, or a much larger
  font's outlines. See the README's "Data size & deployment" section for
  the full reasoning; not needed yet.
- **Prune `glyph-data.json`** to only the consonant+vowel-sign/conjunct
  combinations that occur in real Malayalam, instead of pre-shaping every
  combination HarfBuzz can produce (see README's "Status" section). Needs a
  real-word corpus to prune against first.

## Deployment

The site (landing page + demo + recorder) deploys to GitHub Pages via
`.github/workflows/pages.yml` - decided against a custom domain for now;
`<user>.github.io/jayasree` is enough. Still open:

- Cache headers / CDN in front of the JSON data files once real traffic
  exists - they're static and content-hashed-by-commit, so they're
  trivially cacheable, but GitHub Pages' default caching is what we get
  until/unless the site moves somewhere configurable.
- A custom domain, if the project ever outgrows the github.io URL.

## Bug-report → data pipeline

Right now, diagnosing "this word/letter renders wrong" is entirely manual -
today's session doing exactly that (the space-rendering gap, the ത്സ്യ
composition bug, and the ്ര missing-mark gap) took reading through
`resolveSegments`/`tryComposeStroke` by hand, shaping clusters directly via
`shape_word()` in a scratch script, and cross-referencing three JSON files.
That's not sustainable once reports come from real users instead of one
person reading the source. Needs a proper pipeline:

- **A one-command diagnostic**, e.g. `tools/diagnose.py <word>` (or a JS
  equivalent for browser-side use), that takes a reported word and reports,
  per cluster: directly authored / composed-from-authored / outline-fallback
  - and *why* for the fallback case specifically (missing base stroke?
    missing mark recipe entirely, like ്ര today? mark recipe exists but the
    composition itself failed - the resolveGhostEntry-shaped bug class?).
  This is the exact investigation this session did by hand, made reusable.
  `getFallbackClusters()` (added this session, see README's "Detecting
  approximated clusters") already gives runtime code the *first* signal
  (which clusters fell back); this tool would be the next layer down -
  explaining *why*, for whoever's triaging the report.
- **A standing coverage gate**, not just point fixes. `composition-coverage.test.js`
  (added this session) systematically checks conjunct+mark chains resolve
  instead of silently bailing, and already caught a real regression that a
  hand-written unit test's fixture had accidentally masked (its intermediate
  cluster was pre-registered in the mock, which real glyph-data.json never
  does). Worth extending as new mark chains and multi-word phrases come up,
  so composition regressions are caught in CI, not by a user report.
- **A frictionless report → record loop.** Once a report is confirmed as a
  genuine missing-stroke gap (not a bug), recording the fix currently means:
  open the recorder, manually type the exact cluster string into "Add
  custom cluster" (no ghost, no reduced-set prompt for it since it isn't in
  `clusters` - true for every subjoined mark, not just ്ര), record, export,
  merge into `stroke-data.json`, regenerate `glyph-data.json` +
  `stroke-recorder-standalone.html`. `tools/diagnose.py` above could end
  with "run this to jump straight to recording it" instead of the reporter
  (or whoever triages) having to reconstruct those steps.
- **Catch embedded-data staleness**, not just source staleness.
  `build_standalone_recorder.py --check` only hashes
  `stroke-recorder.{html,css,js}` + the favicon - it happily reports "in
  sync" even when the *embedded* `glyph-data.json`/`stroke-data.raw.json`
  snapshot is stale (discovered this session: the standalone tool's bundled
  marks table was missing ്ര right after it was added to the real file,
  with `--check` passing the whole time). The hash should cover the bundled
  data files too.

## Testing & tooling

- **Headless-browser coverage for `index.js`'s DOM-dependent code** - the
  actual SVG animation (`buildStage`, `traceSub`, `buildTracePath`) needs
  real `getTotalLength()`/`getPointAtLength()`, which jsdom doesn't
  implement, so it's currently only exercised manually via the demo. A
  Playwright-driven test (or visual-regression check) would close this gap;
  deliberately not added yet to avoid pulling in a browser-binary dependency
  for what's still a small project - see the discussion in the session that
  rebuilt `demo/jayasree.svg`, which hit this exact limitation.
- **Ligature coverage for the vowel signs that currently compose
  imperfectly** - ു/ൂ/ൃ and the reduced la-form fuse into a
  consonant-specific shape in real font rendering that generic mark
  composition can't reproduce (see `docs/ARCHITECTURE.md`'s "Composition"
  section); they're recorded as separate atoms instead of true ligatures.
  Revisit if this becomes visually noticeable enough to matter.
