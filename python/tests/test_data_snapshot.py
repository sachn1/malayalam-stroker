"""Snapshot test for js/src/stroke-data.raw.json — the hand-authored source of truth.

Every *previously-snapshotted* cluster's stroke content is hashed and
compared against a committed snapshot
(python/tests/snapshots/stroke_data_raw_snapshot.json). This fails if an
existing cluster disappears or its content silently changes — whether from
an accidental edit, a bad merge, or a future script/feature change that
touches this file unexpectedly. New clusters (recording work in progress)
are *not* flagged — only regressions to what was already there.

A deliberate, reviewed change to an *existing* cluster (a re-recorded
improvement, an intentional removal) is expected to fail here until you
explicitly run:

    python tools/validate_data.py --update-snapshot

and commit the updated snapshot alongside your data change. That's the
point: every change to previously-recorded data should be a conscious,
reviewed one — not a silent side effect of something else.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from validate_data import build_snapshot  # noqa: E402

STROKE_DATA_RAW = ROOT / "js" / "src" / "stroke-data.raw.json"
SNAPSHOT = Path(__file__).parent / "snapshots" / "stroke_data_raw_snapshot.json"


def test_raw_stroke_data_matches_snapshot() -> None:
    """Ensure that every snapshotted cluster's content is unchanged, with none missing."""
    raw = json.loads(STROKE_DATA_RAW.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    current = build_snapshot(raw)

    missing = sorted(set(snapshot) - set(current))
    changed = sorted(
        cluster
        for cluster in snapshot
        if cluster in current and current[cluster] != snapshot[cluster]
    )
    added = sorted(set(current) - set(snapshot))

    assert not missing, (
        f"{len(missing)} cluster(s) present in the snapshot are now missing "
        f"from stroke-data.raw.json: {missing}. If this is intentional, run "
        f"`python tools/validate_data.py --update-snapshot` and commit the result."
    )
    assert not changed, (
        f"{len(changed)} cluster(s) changed content since the snapshot was "
        f"taken: {changed}. If this is an intentional re-recording, run "
        f"`python tools/validate_data.py --update-snapshot` and commit the result."
    )
    # New clusters (added, not in the old snapshot) are fine and expected as
    # recording work continues — not asserted on, just informational.
    if added:
        print(f"\n{len(added)} new cluster(s) not yet in the snapshot: {added[:10]}...")
