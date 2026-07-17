## v0.3.0 (2026-07-17)

### Feat

- **demo**: add speech-to-text word input; load the wordmark as a static image

## v0.2.1 (2026-07-16)

### Fix

- **py**: pin Poetry venv to python/.venv via committed poetry.toml
- **js**: normalize legacy chillu encoding and compose prefix marks onto multi-glyph bases

## v0.2.0 (2026-07-15)

### Feat

- **tools**: give the stroke recorder a real ghost for missing matra
- publish jayasree to npm, add automated publish workflow
- repo rename, add more security
- remove site-verification html and instead use metadata in index
- add sitemap owenership verification and update package status
- update documentation, add sem-ver, github pages

### Fix

- **demo**: remove redundant animated logo from the demo page
- **js**: recursively resolve intermediate mark-chain glyphs and fix mark-vs-direct-match precedence
- **js**: render inter-word spaces and register a maatra  as a composable mark

## v0.1.0 (2026-07-13)

### Feat

- add the configurables to the UI
- add favicon
- add linters, makefile, docstrings, readme
- completed strokes and minor fixes to the rendition
- refine stroking with centering and straightening wrt ghost font, refine recorder ui, add logo and name, update readme
- add standalone support for tab for strokes
- add more character combinations, update the stroke-recorder html
- self-contained JS animator with bundled glyph data and stroke recorder
- initial malayalam-stroker monorepo

### Fix

- remove incorrect backslash from index.js

### Refactor

- add docstrings, split monolithic html files, add linters
