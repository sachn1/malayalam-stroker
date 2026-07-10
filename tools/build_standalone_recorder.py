#!/usr/bin/env python3
"""Bundle stroke-recorder.html + glyph-data.json into a single self-contained file.

The output can be opened directly in any browser (file://) — no server needed.
Copy it to your tablet once; it works fully offline.

The generated file embeds a content hash of its stroke-recorder.{html,css,js}
sources as an HTML comment, so staleness (editing the sources without
regenerating) is always detectable on demand:

    python tools/build_standalone_recorder.py --check

Usage (from repo root):
    python tools/build_standalone_recorder.py
    # → tools/stroke-recorder-standalone.html
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_SRC = ROOT / "tools" / "stroke-recorder.html"
CSS_SRC = ROOT / "tools" / "stroke-recorder.css"
JS_SRC = ROOT / "tools" / "stroke-recorder.js"
GLYPH_DATA = ROOT / "js" / "src" / "glyph-data.json"
STROKE_DATA_RAW = ROOT / "js" / "src" / "stroke-data.raw.json"
OUT = ROOT / "tools" / "stroke-recorder-standalone.html"

_HASH_COMMENT = "<!-- source-hash: {} (do not edit; run tools/build_standalone_recorder.py) -->"
_HASH_RE = re.compile(r"<!-- source-hash: ([0-9a-f]+)")


def _source_hash() -> str:
    """Hash the three stroke-recorder source files together."""
    combined = HTML_SRC.read_bytes() + CSS_SRC.read_bytes() + JS_SRC.read_bytes()
    return hashlib.sha256(combined).hexdigest()[:16]


def build() -> None:
    """Regenerate tools/stroke-recorder-standalone.html from current sources."""
    html = HTML_SRC.read_text(encoding="utf-8")
    css = CSS_SRC.read_text(encoding="utf-8")
    js = JS_SRC.read_text(encoding="utf-8")
    glyph_data = GLYPH_DATA.read_text(encoding="utf-8")
    stroke_data_raw = STROKE_DATA_RAW.read_text(encoding="utf-8")

    # Inline CSS
    html = re.sub(
        r'<link\s+rel="stylesheet"\s+href="stroke-recorder\.css"\s*/?>',
        f"<style>\n{css}\n</style>",
        html,
    )

    # Inject glyph-data and the current stroke-data.raw.json as pre-loaded JS
    # variables before the main script, then patch the drop-zone so it
    # auto-loads on page open — bundling the raw strokes too (not just the
    # glyph outlines) means the reduced-set filter and "already recorded"
    # checkmarks are correct immediately, with no manual "Load existing
    # strokes" step needed before recording the remaining gaps.
    preload_script = f"""<script>
// Data bundled at build time — no file drop needed.
const BUNDLED_GLYPH_DATA = {glyph_data};
const BUNDLED_STROKE_DATA = {stroke_data_raw};
</script>"""

    autoload_patch = """<script>
// Auto-load bundled data once the recorder script has initialised.
window.addEventListener("DOMContentLoaded", () => {
  if (typeof BUNDLED_STROKE_DATA !== "undefined") {
    existingStrokeData = BUNDLED_STROKE_DATA;
    const count = Object.keys(existingStrokeData).length;
    document.getElementById("merge-status").textContent =
      `✓ ${count} existing cluster(s) loaded — export will merge`;
  }
  if (typeof BUNDLED_GLYPH_DATA !== "undefined") {
    parseGlyphData(JSON.stringify(BUNDLED_GLYPH_DATA));
    // Land directly on the first not-yet-recorded atom instead of index 0
    // (almost always already-recorded) — removes any guesswork about where
    // to start.
    document.getElementById("next-missing-btn").click();
  }
});
</script>"""

    # Inline JS (replace the external script tag).
    # Use a callable replacement to avoid re interpreting backslashes in JS source.
    inline_js = f"{preload_script}\n<script>\n{js}\n</script>\n{autoload_patch}"
    html = re.sub(
        r'<script\s+src="stroke-recorder\.js"[^>]*></script>',
        lambda _: inline_js,
        html,
    )

    html = re.sub(r"(<html[^>]*>)", rf"\1\n{_HASH_COMMENT.format(_source_hash())}", html, count=1)

    OUT.write_text(html, encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(f"Written {OUT.relative_to(ROOT)}  ({size_kb:.0f} KB)")
    print("Copy this single file to your tablet — opens offline in any browser.")


def check() -> None:
    """Exit non-zero with a clear message if the standalone file is stale."""
    if not OUT.exists():
        print(f"STALE: {OUT.relative_to(ROOT)} does not exist yet.", file=sys.stderr)
        print("Regenerate with: python tools/build_standalone_recorder.py", file=sys.stderr)
        sys.exit(1)

    existing = OUT.read_text(encoding="utf-8")
    m = _HASH_RE.search(existing)
    current = _source_hash()
    if not m or m.group(1) != current:
        print(
            f"STALE: {OUT.relative_to(ROOT)} is out of sync with "
            "stroke-recorder.{html,css,js}.",
            file=sys.stderr,
        )
        print("Regenerate with: python tools/build_standalone_recorder.py", file=sys.stderr)
        sys.exit(1)

    print(f"{OUT.relative_to(ROOT)} is in sync with its sources.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether the standalone file is in sync instead of regenerating it",
    )
    args = parser.parse_args()
    check() if args.check else build()


if __name__ == "__main__":
    main()
