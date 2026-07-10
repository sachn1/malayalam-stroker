"""Tests for tools/validate_data.py — data-integrity checks for the committed files.

Deliberately script-agnostic: fixtures are synthetic stroke/glyph structures,
not real Malayalam data (that's exercised separately by running the script
against the real files in CI — see .github/workflows/ci.yml).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))

from validate_data import (
    cross_check_raw_in_processed,
    validate_glyph_data,
    validate_stroke_d,
    validate_stroke_data,
)


class TestValidateStrokeD:
    """validate_stroke_d: one stroke's `d` value."""

    def test_valid_path_has_no_errors(self) -> None:
        """Ensure that a well-formed moveto-starting path has no errors."""
        assert validate_stroke_d("M0 0 L10 10", "x") == []

    def test_non_string_is_an_error(self) -> None:
        """Ensure that a non-string value is rejected."""
        assert validate_stroke_d(42, "x") != []

    def test_empty_string_is_an_error(self) -> None:
        """Ensure that an empty or whitespace-only string is rejected."""
        assert validate_stroke_d("", "x") != []
        assert validate_stroke_d("   ", "x") != []

    def test_non_moveto_start_is_an_error(self) -> None:
        """Ensure that a path not starting with a moveto command is rejected."""
        assert validate_stroke_d("L10 10", "x") != []
        assert validate_stroke_d("garbage", "x") != []


class TestValidateStrokeData:
    """validate_stroke_data: a full stroke-data(.raw).json structure."""

    def test_valid_data_has_no_errors(self) -> None:
        """Ensure that well-formed stroke data passes with no errors."""
        data = {"A": {"strokes": [{"d": "M0 0 L10 10"}]}}
        assert validate_stroke_data(data, "test.json") == []

    def test_non_dict_top_level_is_an_error(self) -> None:
        """Ensure that a non-object top level is rejected."""
        assert validate_stroke_data([], "test.json") != []

    def test_missing_strokes_key_is_an_error(self) -> None:
        """Ensure that a cluster entry missing 'strokes' is rejected."""
        errors = validate_stroke_data({"A": {}}, "test.json")
        assert len(errors) == 1
        assert "missing 'strokes'" in errors[0]

    def test_empty_strokes_list_is_an_error(self) -> None:
        """Ensure that a cluster with zero strokes is rejected."""
        errors = validate_stroke_data({"A": {"strokes": []}}, "test.json")
        assert len(errors) == 1
        assert "empty" in errors[0]

    def test_stroke_missing_d_key_is_an_error(self) -> None:
        """Ensure that a stroke object missing 'd' is rejected."""
        errors = validate_stroke_data({"A": {"strokes": [{}]}}, "test.json")
        assert len(errors) == 1
        assert "missing 'd'" in errors[0]

    def test_multiple_clusters_report_multiple_errors(self) -> None:
        """Ensure that errors accumulate across multiple bad clusters."""
        data = {"A": {"strokes": []}, "B": {"strokes": []}}
        assert len(validate_stroke_data(data, "test.json")) == 2


class TestValidateGlyphData:
    """validate_glyph_data: glyph-data.json's structure."""

    def test_valid_data_has_no_errors(self) -> None:
        """Ensure that well-formed glyph data passes with no errors."""
        data = {
            "meta": {"unitsPerEm": 2048},
            "clusters": {"A": {"glyphs": [{"d": "M0 0 L1 1", "x": 0, "y": 0}]}},
        }
        assert validate_glyph_data(data) == []

    def test_missing_clusters_key_is_an_error(self) -> None:
        """Ensure that a missing 'clusters' key is rejected."""
        assert validate_glyph_data({}) != []

    def test_empty_clusters_is_an_error(self) -> None:
        """Ensure that an empty clusters object is rejected."""
        errors = validate_glyph_data({"meta": {"unitsPerEm": 2048}, "clusters": {}})
        assert errors != []

    def test_missing_units_per_em_is_an_error(self) -> None:
        """Ensure that a meta object missing unitsPerEm is rejected."""
        data = {"meta": {}, "clusters": {"A": {"glyphs": [{"d": "M0 0", "x": 0, "y": 0}]}}}
        errors = validate_glyph_data(data)
        assert any("unitsPerEm" in e for e in errors)

    def test_empty_glyph_d_is_allowed(self) -> None:
        """Ensure that an empty glyph outline (a space character) is not flagged."""
        data = {
            "meta": {"unitsPerEm": 2048},
            "clusters": {" ": {"glyphs": [{"d": "", "x": 0, "y": 0}]}},
        }
        assert validate_glyph_data(data) == []


class TestCrossCheckRawInProcessed:
    """cross_check_raw_in_processed: every raw cluster must survive processing."""

    def test_no_errors_when_all_raw_clusters_present(self) -> None:
        """Ensure that no errors are reported when nothing is missing."""
        assert cross_check_raw_in_processed({"A": {}, "B": {}}, {"A": {}, "B": {}, "AB": {}}) == []

    def test_reports_each_missing_cluster(self) -> None:
        """Ensure that a dropped raw cluster is reported by name."""
        errors = cross_check_raw_in_processed({"A": {}, "B": {}}, {"A": {}})
        assert len(errors) == 1
        assert "'B'" in errors[0]


@pytest.mark.parametrize(
    "filename", ["glyph-data.json", "stroke-data.raw.json", "stroke-data.json"]
)
def test_real_committed_files_are_valid(filename: str) -> None:
    """Ensure that the actual committed data files pass validation right now."""
    import json

    from validate_data import GLYPH_DATA, STROKE_DATA, STROKE_DATA_RAW

    path = {
        "glyph-data.json": GLYPH_DATA,
        "stroke-data.raw.json": STROKE_DATA_RAW,
        "stroke-data.json": STROKE_DATA,
    }[filename]
    data = json.loads(path.read_text(encoding="utf-8"))
    if filename == "glyph-data.json":
        errors = validate_glyph_data(data)
    else:
        errors = validate_stroke_data(data, filename)
    assert errors == [], f"{filename} failed validation: {errors[:5]}"
