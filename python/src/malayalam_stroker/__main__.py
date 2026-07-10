"""Entry point for `python -m malayalam_stroker` — see cli.py for the actual logic."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
