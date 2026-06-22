"""Tiny local server for the interactive malayalam-stroker demo.

This exists because shaping happens server-side (HarfBuzz needs a font
file on disk) — the JS package only *animates* pre-shaped JSON, it can't
shape arbitrary typed text by itself in the browser. So unlike
js/examples/demo.html (a single static word, no server needed), this
demo lets you type any word and traces it live.

Serves the whole repo root as static files (so demo/index.html can
import ../js/src/index.js directly, no build step, no duplication) plus
one dynamic route:

    GET /api/shape/<word> -> StrokeTrace JSON, shaped on the fly

stdlib only — no Flask/FastAPI dependency, just `python demo/serve.py`.

Run:
    python demo/serve.py
Then open http://127.0.0.1:8000/demo/
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "python" / "src"))

from malayalam_stroker import shape_word  # noqa: E402

FONT_PATH = _REPO_ROOT / "python" / "tests" / "fixtures" / "Manjari-Regular.ttf"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
}


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/shape/"):
            self._handle_shape(unquote(parsed.path[len("/api/shape/") :]))
            return
        self._serve_static(parsed.path)

    def _serve_static(self, path: str) -> None:
        rel = path.lstrip("/") or "demo/index.html"
        if rel == "demo" or rel == "demo/":
            rel = "demo/index.html"
        file_path = (_REPO_ROOT / rel).resolve()

        # Don't serve anything outside the repo root.
        if _REPO_ROOT not in file_path.parents and file_path != _REPO_ROOT:
            self.send_error(403)
            return
        if not file_path.is_file():
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header(
            "Content-Type", _CONTENT_TYPES.get(file_path.suffix, "application/octet-stream")
        )
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _handle_shape(self, word: str) -> None:
        try:
            trace = shape_word(word, FONT_PATH)
            body = json.dumps(trace, ensure_ascii=False).encode("utf-8")
            status = 200
        except ValueError as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            status = 400

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # quiet by default
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), DemoHandler)
    print(f"malayalam-stroker demo running at http://127.0.0.1:{port}/demo/")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
