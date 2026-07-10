#!/usr/bin/env python3
"""Validate the structural integrity of the committed data files.

Catches accidental corruption (malformed JSON, empty/invalid stroke paths,
missing required keys) before it's committed — run via pre-commit/CI, or:

    python tools/validate_data.py

Also owns the stroke-data.raw.json content-hash snapshot used by
python/tests/test_data_snapshot.py (a *content* check, complementing this
file's *structural* one — see that test's docstring). Regenerate it after a
deliberate, reviewed change to previously-recorded data:

    python tools/validate_data.py --update-snapshot
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GLYPH_DATA = ROOT / "js" / "src" / "glyph-data.json"
STROKE_DATA_RAW = ROOT / "js" / "src" / "stroke-data.raw.json"
STROKE_DATA = ROOT / "js" / "src" / "stroke-data.json"
SNAPSHOT = ROOT / "python" / "tests" / "snapshots" / "stroke_data_raw_snapshot.json"

_SVG_PATH_RE = re.compile(r"^M\s*-?[\d.]+\s+-?[\d.]+")


def validate_stroke_d(d: Any, where: str) -> list[str]:
    """Validate one stroke's `d` value, returning a list of error messages.

    Parameters
    ----------
    d : Any
        The value to validate as an SVG path ``d`` string.
    where : str
        Human-readable location (for error messages), e.g. ``"ക.strokes[0]"``.

    Returns
    -------
    list[str]
        Error messages; empty if `d` is valid.
    """
    if not isinstance(d, str):
        return [f"{where}: 'd' is not a string ({type(d).__name__})"]
    if not d.strip():
        return [f"{where}: 'd' is empty"]
    if not _SVG_PATH_RE.match(d):
        return [f"{where}: 'd' does not start with a valid moveto command: {d[:30]!r}"]
    return []


def validate_stroke_data(data: Any, filename: str) -> list[str]:
    """Validate a stroke-data(.raw).json structure, returning error messages.

    Parameters
    ----------
    data : Any
        Parsed JSON content to validate.
    filename : str
        Name used in error messages (e.g. ``"stroke-data.raw.json"``).

    Returns
    -------
    list[str]
        Error messages; empty if the structure is fully valid.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{filename}: top level must be an object, got {type(data).__name__}"]

    for cluster, entry in data.items():
        where = f"{filename}:{cluster!r}"
        if not isinstance(entry, dict) or "strokes" not in entry:
            errors.append(f"{where}: missing 'strokes' key")
            continue
        strokes = entry["strokes"]
        if not isinstance(strokes, list):
            errors.append(f"{where}.strokes: must be a list, got {type(strokes).__name__}")
            continue
        if not strokes:
            errors.append(
                f"{where}.strokes: empty — a recorded cluster must have at least one stroke"
            )
        for i, stroke in enumerate(strokes):
            if not isinstance(stroke, dict) or "d" not in stroke:
                errors.append(f"{where}.strokes[{i}]: missing 'd' key")
                continue
            errors.extend(validate_stroke_d(stroke["d"], f"{where}.strokes[{i}]"))

    return errors


def validate_glyph_data(data: Any) -> list[str]:
    """Validate glyph-data.json's structure, returning error messages.

    Parameters
    ----------
    data : Any
        Parsed JSON content to validate.

    Returns
    -------
    list[str]
        Error messages; empty if the structure is fully valid.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["glyph-data.json: top level must be an object"]
    if "clusters" not in data:
        errors.append("glyph-data.json: missing 'clusters' key")
        return errors
    if "meta" not in data or not isinstance(data.get("meta"), dict):
        errors.append("glyph-data.json: missing or invalid 'meta' key")
    elif "unitsPerEm" not in data["meta"]:
        errors.append("glyph-data.json.meta: missing 'unitsPerEm'")

    clusters = data["clusters"]
    if not isinstance(clusters, dict) or not clusters:
        errors.append("glyph-data.json.clusters: must be a non-empty object")
        return errors

    for cluster, entry in clusters.items():
        where = f"glyph-data.json.clusters:{cluster!r}"
        if not isinstance(entry, dict) or "glyphs" not in entry:
            errors.append(f"{where}: missing 'glyphs' key")
            continue
        glyphs = entry["glyphs"]
        if not isinstance(glyphs, list) or not glyphs:
            errors.append(f"{where}.glyphs: must be a non-empty list")
            continue
        for i, glyph in enumerate(glyphs):
            if not isinstance(glyph, dict) or "d" not in glyph:
                errors.append(f"{where}.glyphs[{i}]: missing 'd' key")
                continue
            # A glyph's own outline `d` may legitimately be empty (a space
            # character has no ink) — only check well-formedness when present.
            if glyph["d"] and not _SVG_PATH_RE.match(glyph["d"]):
                errors.append(
                    f"{where}.glyphs[{i}]: 'd' does not start with a valid moveto command"
                )

    return errors


def cross_check_raw_in_processed(raw: dict, processed: dict) -> list[str]:
    """Verify every hand-authored cluster survived into the processed file.

    Parameters
    ----------
    raw : dict
        Parsed stroke-data.raw.json content.
    processed : dict
        Parsed stroke-data.json content.

    Returns
    -------
    list[str]
        One error message per raw cluster missing from the processed file.
    """
    missing = sorted(set(raw) - set(processed))
    return [f"stroke-data.json: missing hand-authored cluster {c!r} from raw" for c in missing]


def hash_strokes(entry: dict) -> str:
    """Compute a stable content hash for one cluster's recorded strokes.

    Parameters
    ----------
    entry : dict
        A single ``stroke-data.raw.json`` value, i.e. ``{"strokes": [...]}}``.

    Returns
    -------
    str
        A short, stable hex digest of the entry's stroke path data.
    """
    d_values = [s.get("d", "") for s in entry.get("strokes", [])]
    payload = "|".join(d_values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_snapshot(raw: dict) -> dict[str, str]:
    """Build a ``{cluster: content_hash}`` snapshot from raw stroke data.

    Parameters
    ----------
    raw : dict
        Parsed ``stroke-data.raw.json`` content.

    Returns
    -------
    dict[str, str]
        Mapping of cluster key to its stroke-content hash.
    """
    return {cluster: hash_strokes(entry) for cluster, entry in raw.items()}


def update_snapshot(raw: dict) -> None:
    """Regenerate the stroke-data.raw.json content-hash snapshot from `raw` and write it.

    Parameters
    ----------
    raw : dict
        Parsed ``stroke-data.raw.json`` content.
    """
    snapshot = build_snapshot(raw)
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {SNAPSHOT.relative_to(ROOT)} ({len(snapshot)} clusters).")


def main() -> int:
    """Load and validate all three committed data files, printing any errors.

    Also handles ``--update-snapshot``, which regenerates the content-hash
    snapshot instead of validating.

    Returns
    -------
    int
        Exit code (0 = success, 1 = validation errors found).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-snapshot",
        action="store_true",
        help="Regenerate the stroke-data.raw.json content-hash snapshot instead of validating.",
    )
    args = parser.parse_args()

    try:
        raw = json.loads(STROKE_DATA_RAW.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FATAL: could not read/parse {STROKE_DATA_RAW}: {exc}", file=sys.stderr)
        return 1

    if args.update_snapshot:
        update_snapshot(raw)
        return 0

    errors: list[str] = []

    try:
        glyph_data = json.loads(GLYPH_DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FATAL: could not read/parse {GLYPH_DATA}: {exc}", file=sys.stderr)
        return 1
    errors.extend(validate_glyph_data(glyph_data))
    errors.extend(validate_stroke_data(raw, "stroke-data.raw.json"))

    try:
        processed = json.loads(STROKE_DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FATAL: could not read/parse {STROKE_DATA}: {exc}", file=sys.stderr)
        return 1
    errors.extend(validate_stroke_data(processed, "stroke-data.json"))
    errors.extend(cross_check_raw_in_processed(raw, processed))

    if errors:
        print(f"Found {len(errors)} data integrity error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    n_glyph_clusters = len(glyph_data["clusters"])
    print(
        f"OK: {len(raw)} raw clusters, {len(processed)} processed clusters, "
        f"{n_glyph_clusters} glyph clusters — all valid."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
