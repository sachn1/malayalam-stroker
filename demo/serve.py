"""Static file server and shaping API for the jayasree demo."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "python" / "src"))

from jayasree import shape_word  # noqa: E402

FONT_PATH = _REPO_ROOT / "python" / "tests" / "fixtures" / "Manjari-Regular.ttf"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".gif": "image/gif",
}


class DemoHandler(BaseHTTPRequestHandler):
    """HTTP request handler for static files and the /api/shape/ endpoint."""

    def do_GET(self) -> None:
        """Handle GET requests, routing to static or shape handler."""
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/shape/"):
            self._handle_shape(unquote(parsed.path[len("/api/shape/") :]))
            return
        self._serve_static(parsed.path)

    def _serve_static(self, path: str) -> None:
        """Serve a file from the repo root, rejecting path-traversal attempts."""
        rel = path.lstrip("/") or "index.html"
        # Mirror GitHub Pages' directory-index behavior for the demo URL.
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
            "Content-Type",
            _CONTENT_TYPES.get(file_path.suffix, "application/octet-stream"),
        )
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _handle_shape(self, word: str) -> None:
        """Shape *word* with HarfBuzz and return StrokeTrace JSON."""
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

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default access-log output."""


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("0.0.0.0", port), DemoHandler)
    import socket

    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"jayasree demo running at http://127.0.0.1:{port}/demo/")
    print(f"On your tablet (same Wi-Fi): http://{local_ip}:{port}/tools/stroke-recorder.html")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
