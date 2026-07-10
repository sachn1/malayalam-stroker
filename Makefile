.PHONY: help install install-py install-js \
	lint lint-py lint-js format format-py \
	test test-py test-js \
	validate-data precommit \
	ci ci-py ci-js \
	demo record build-glyph-data process-strokes build-recorder update-snapshot \
	clean

# Single source of truth for the commands used both by contributors locally
# and by .github/workflows/ci.yml — the workflow calls `make ci-py`/`make
# ci-js` rather than duplicating these commands, so there's exactly one place
# that defines "lint" or "test" for this repo.

help:
	@echo "malayalam-stroker — common commands"
	@echo ""
	@echo "  make install        install both Python (poetry) and JS (npm) dependencies"
	@echo "  make lint           lint Python + JS"
	@echo "  make format         auto-fix formatting (Python only — see lint-js for JS)"
	@echo "  make test           run Python + JS test suites"
	@echo "  make validate-data  structural validation of the 3 committed JSON data files"
	@echo "  make precommit      run every pre-commit hook against all files"
	@echo "  make ci             everything CI runs, for both languages, in one shot"
	@echo "  make demo           serve the demo AND the stroke recorder (same server, see"
	@echo "                      its printed URLs) at :8000 — alias: make record"
	@echo "  make build-glyph-data [FONT=/path/to/Font.ttf]   regenerate glyph-data.json"
	@echo "  make process-strokes                              regenerate stroke-data.json"
	@echo "  make build-recorder                                bundle the standalone recorder"
	@echo "  make update-snapshot                               re-approve the data snapshot"
	@echo "  make clean          remove venvs/node_modules/coverage artifacts"

# ── Install ──────────────────────────────────────────────────────────────

install: install-py install-js

install-py:
	cd python && poetry install

install-js:
	npm ci

# ── Lint / format ────────────────────────────────────────────────────────

lint: lint-py lint-js

lint-py:
	cd python && poetry run ruff check .. && poetry run ruff format --check ..
	cd python && poetry run interrogate --fail-under=90 --ignore-init-module --ignore-magic src ../tools

lint-js:
	npm run lint

format: format-py

format-py:
	cd python && poetry run ruff format ..

# ── Test ─────────────────────────────────────────────────────────────────

test: test-py test-js

test-py:
	cd python && poetry run pytest

test-js:
	npm test

# ── Data integrity ───────────────────────────────────────────────────────

validate-data:
	python3 tools/validate_data.py

update-snapshot:
	python3 tools/validate_data.py --update-snapshot

# ── Everything at once ───────────────────────────────────────────────────

precommit:
	cd python && poetry run pre-commit run --all-files

# ci-py / ci-js mirror the two parallel jobs in .github/workflows/ci.yml
# exactly — each is what that job's "run" steps reduce to after checkout
# and toolchain setup (which only make sense inside the runner, not here).
ci-py: install-py lint-py test-py validate-data

ci-js: install-js lint-js test-js

ci: ci-py ci-js

# ── App commands ─────────────────────────────────────────────────────────

# One server, two jobs: it serves the interactive demo (demo/demo_index.html)
# *and* the whole repo as static files, which is what makes the stroke
# recorder (tools/stroke-recorder.html) reachable through it too — serve.py
# prints both URLs on startup for exactly this reason. `record` is just a
# more discoverable name for anyone who only wants the recorder.
demo record:
	python3 demo/serve.py

build-glyph-data:
	cd python && poetry run python ../tools/build_glyph_data.py $(FONT)

process-strokes:
	python3 tools/process_strokes.py --preset=malayalam

build-recorder:
	python3 tools/build_standalone_recorder.py

# ── Housekeeping ─────────────────────────────────────────────────────────

clean:
	rm -rf python/.venv node_modules python/.pytest_cache python/htmlcov .coverage
