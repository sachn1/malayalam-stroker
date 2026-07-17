# Contributing

Thanks for wanting to help! There are two very different ways to contribute
here, and the most valuable one needs no coding at all.

## Contributing stroke data (no code needed)

The heart of this project is hand-drawn stroke data from people who actually
write the script. Open the [stroke recorder](tools/stroke-recorder.html) (or
the offline `tools/stroke-recorder-standalone.html`), trace the characters
marked ○ (missing), export, and open a PR with the updated
`js/src/stroke-data.raw.json`.

Rules that keep the data trustworthy:

- **Whitespace and punctuation never get a recorded stroke.** Space, `.`,
  `,`, `!`, `?`, `;`, `:`, and a few others (`UNIVERSAL_CHARS` in
  `js/src/index.js`) are handled entirely outside this pipeline - they're
  rendered as plain static text, not traced handwriting, since they aren't
  part of any script's letterforms. The recorder itself refuses to add one
  ("Add custom cluster" rejects them with an explanation), and
  `tools/validate_data.py` fails CI if one ever ends up in any committed
  data file, so this isn't something you need to remember - just know why
  you won't find them in the recorder's list.
- **Never hand-edit `stroke-data.raw.json`.** Only the recorder writes it.
  It is the project's source of truth; everything else is derived from it.
- **Don't edit `stroke-data.json` or `glyph-data.json` at all** - they're
  generated (`make process-strokes`, `make build-glyph-data`). Regenerate,
  don't patch.
- **Changing an already-recorded character is a deliberate act.** The
  snapshot test will fail until you run `make update-snapshot` and commit
  the updated snapshot *in the same PR* - that's by design, so every change
  to previously-recorded data is explicit and reviewable, never a silent
  side effect. New characters don't need this; only changed/removed ones do.
- **Licensing:** by contributing stroke data you agree it's released under
  the project's data license (CC BY 4.0 - see [LICENSE-DATA](LICENSE-DATA)).
  You'll be credited in the git history; if you'd like more prominent
  attribution, say so in the PR.

## Contributing code

Ground rules, enforced by CI (`make ci` runs exactly what CI runs - if it's
green locally, it's green there):

- **Tests are not optional.** New behavior comes with tests; bug fixes come
  with a regression test that fails before the fix. Aim to keep coverage
  where it is or better (Python is ~95%; don't dilute it).
- **Clean code is enforced, not aspirational.** `ruff` (lint + format,
  NumPy-style docstrings, type hints everywhere) and `eslint` gate every
  commit via pre-commit and CI. Public functions document their Parameters
  and Returns. If a linter and this document disagree, the linter wins.
- **Match the code around you** - comment density, naming, idiom. Comments
  explain *why*, not *what*.

Setup:

```bash
make install     # poetry + npm dependencies
make test        # pytest + vitest
make lint        # ruff + interrogate + eslint
make precommit   # every pre-commit hook, as CI runs them
```

## Commit messages & versioning

This repo uses [conventional commits](https://www.conventionalcommits.org/)
enforced by commitizen (a `commit-msg` pre-commit hook rejects anything
else - run `pre-commit install --hook-type commit-msg` once after cloning,
or let `cz commit` write the message interactively for you):

```
<type>(<scope>): <description>

feat(js): add per-play speed multiplier
fix(py): keep straight runs straight through loop-adjacent pieces
data(ml): record the remaining chillu letters
docs: explain the snapshot re-approval flow
```

Types follow the standard set (`feat`, `fix`, `docs`, `refactor`, `test`,
`build`, `ci`, `chore`, `perf`). Use the scope for where the change lives:

- `js` - the runtime library (`js/src/`)
- `py` - the Python package (`python/`)
- `data` - the committed JSON data (suffix the language, e.g. `data(ml)`)
- `tools` / `demo` / `docs` / `ci` - the corresponding directories

Releases are semantic-versioned from the commit history: bumping picks the
next version (`feat` -> minor, `fix` -> patch, a `BREAKING CHANGE` footer ->
major), rewrites every version reference (Python package, JS package, the
version badge on the website), updates CHANGELOG.md, and tags. Don't edit
version numbers by hand anywhere.

Merging a PR into `master` is what triggers a release:
`.github/workflows/release-on-merge.yml` runs the version bump
automatically once a PR is merged, if the merged commits include anything
release-worthy (`feat`/`fix`/a breaking change). A PR of only
`docs`/`chore`/`ci`/non-breaking `refactor` commits merges normally with no
release triggered. The bump commit + tag it pushes cascades everything
else: `pages.yml` redeploys, `publish.yml` attempts an npm publish.

One version number covers the npm package, the (unpublished) Python
build-tool package, and the site's version badge together - simpler than
tracking independent version schemes per package, at the cost that plenty
of tagged releases don't touch anything npm actually ships (e.g. a
`docs`/`demo`-only `fix`). `publish.yml` accounts for this: it only runs
`npm publish` if `js/src/`, `js/README.md`, or `js/LICENSE` actually
changed since the previous tag - the tag/CHANGELOG entry still always
happens, only the redundant npm publish is skipped. A manual
`workflow_dispatch` run bypasses this check and always publishes.

## Adding a new language

The core is deliberately script-agnostic - geometry, centering,
straightening, and composition know nothing about Malayalam. The tests
mirror that split: `test_geometry.py`/`test_stroke_compose.py` use synthetic
fixtures, while everything Malayalam-specific lives in
`test_chars_malayalam.py` and the data files. Keep it that way:

- **A new language must not touch the existing one.** No edits to
  `_chars.py`, `stroke-data.raw.json`, or Malayalam tests. If a "common"
  feature needs changes to shared code, the existing language's tests must
  pass unmodified - if you had to change them, the feature wasn't common.
- Add a sibling character-inventory module (e.g. `_chars_tamil.py`), its own
  data files (see the README's "Data size & deployment" on per-script
  splitting), and its own test module mirroring `test_chars_malayalam.py`.
- Recording needs a native speaker/writer of that script - strokes drawn by
  someone who doesn't write it daily are worse than no strokes (the outline
  fallback is always correct, just less handwriting-like).
- Whitespace/punctuation handling (`UNIVERSAL_CHARS` in `js/src/index.js`)
  is already script-agnostic - it's checked before any language-specific
  lookup and never touches per-language data. Nothing to add per language.

## Data integrity & governance

How this repo keeps its data trustworthy, in layers - worth understanding
before touching any `js/src/*.json`:

1. **Structural validation** - `tools/validate_data.py` checks every stroke
   and glyph entry is well-formed, and that every hand-authored cluster
   survived into the processed file. Runs in pre-commit and CI; a
   structurally corrupt commit can't land.
2. **Content snapshot** - a per-cluster content hash
   (`python/tests/snapshots/`) fails the test suite if previously-recorded
   data is lost or silently altered. Re-approval (`make update-snapshot`) is
   a visible, reviewable diff in the same PR as the change it approves.
3. **Generated vs. source separation** - `stroke-data.raw.json` is the only
   hand-made data file; everything else regenerates from it, so corruption
   in derived files is always recoverable.
4. **Review + history** - all changes land via PR; git history is the
   provenance record of who contributed which strokes and when.
5. **Read-only runtime** - the published site and library only ever *fetch*
   the data. Nothing a visitor does can write back; the recorder runs
   entirely client-side and produces a file the contributor must
   deliberately submit through a PR.

If you find a way to corrupt the data that slips past all of this, that's a
bug - please open an issue.
