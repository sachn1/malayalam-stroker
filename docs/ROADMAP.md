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
- **Publish the packages.** Neither `js/` nor `python/` is published yet
  (`README.md`, `python/README.md`). Once the API is stable enough to
  commit to: `npm publish` for the JS package, and a PyPI release for the
  Python one (currently positioned as a build-time-only tool, so this may
  never be worth doing for it specifically).

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
`python/src/malayalam_stroker/_chars.py` (character inventory) and the two
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

### Automated releases on PR merge (manual releases stay manual)

Right now every release is manual: `make bump` (`cz bump`) locally computes
the version from conventional-commit history, updates version_files +
CHANGELOG.md, and tags - then `git push --follow-tags` is what actually
triggers `publish.yml` (it only fires on a `v*` tag arriving, never on an
ordinary push - see that workflow's own header comment). Nothing
auto-releases today, on a PR merge or otherwise.

Decided direction (not yet built): keep it that way for direct pushes to
master, but auto-release when a PR is merged - the PR-review act itself is
the "deliberate, reviewed" signal that a plain push doesn't have. The two
paths are genuinely distinguishable in GitHub Actions, not just a
convention to self-enforce:

- **PR merged to master** → a new job triggered by `pull_request: types:
  [closed]` with `if: github.event.pull_request.merged == true` (a
  different trigger than `push` entirely) runs an automated release - e.g.
  release-please, which maintains a standing "Release PR" that accumulates
  pending changes and computes the next version, so the actual publish
  moment is still one deliberate merge, just of the release PR instead of a
  manual `make bump` run.
- **Direct push to master** → unchanged: `make bump` + `git push
  --follow-tags`, same as today.

Commit *type* already does the "which changes count as a release" filtering
for free under the Conventional Commits convention release-please and
similar tools follow: `feat`/`fix`/breaking-change commits trigger a
version bump, `docs`/`chore`/`ci`/`test`/non-breaking `refactor` don't - no
extra scoping rule needed for e.g. CI-only changes to be excluded.

Deliberately not built yet: there's no real PR workflow to exercise it
against currently (solo dev, direct pushes only) - worth building once PRs
are actually in use, not speculatively ahead of that.

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
  composition can't reproduce (see README's "Composing combinations"
  section); they're recorded as separate atoms instead of true ligatures.
  Revisit if this becomes visually noticeable enough to matter.
