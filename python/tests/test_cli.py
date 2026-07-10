"""Tests for malayalam_stroker.cli — the `shape`/`alphabet` CLI.

Uses the same bundled test fixture font as test_strokes.py (see that
module's docstring). The CLI's argument-parsing/dispatch logic is
script-agnostic; the words shaped here are Malayalam only because that's
this package's motivating use case, per _chars.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from malayalam_stroker.cli import main

FONT = str(Path(__file__).parent / "fixtures" / "Manjari-Regular.ttf")


def test_dash_m_invocation_reaches_cli_main_via_the_shim() -> None:
    """Ensure that `python -m malayalam_stroker` still works through __main__.py's shim."""
    result = subprocess.run(
        [sys.executable, "-m", "malayalam_stroker", "shape", FONT, "നന്ദി"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    (parsed,) = json.loads(result.stdout)
    assert parsed["word"] == "നന്ദി"


class TestShapeCommand:
    """`malayalam_stroker shape <font> <words...>` — explicit sub-command form."""

    def test_shapes_a_single_word(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Ensure that shaping one word prints a one-element JSON array."""
        code = main(["shape", FONT, "നന്ദി"])
        assert code == 0
        (result,) = json.loads(capsys.readouterr().out)
        assert result["word"] == "നന്ദി"
        assert "glyphs" in result

    def test_shapes_multiple_words_in_order(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Ensure that multiple words are shaped and printed in input order."""
        code = main(["shape", FONT, "അമ്മ", "നന്ദി"])
        assert code == 0
        results = json.loads(capsys.readouterr().out)
        assert [r["word"] for r in results] == ["അമ്മ", "നന്ദി"]

    def test_empty_word_is_a_clean_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Ensure that an invalid (empty) word prints a clean error and exits 1."""
        code = main(["shape", FONT, ""])
        assert code == 1
        assert "error shaping" in capsys.readouterr().err

    def test_missing_font_is_a_clean_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Ensure that a nonexistent font path prints a clean error, not a traceback."""
        code = main(["shape", "/nonexistent/font.ttf", "test"])
        assert code == 1
        assert "error shaping" in capsys.readouterr().err


class TestImplicitShapeCommand:
    """Backwards-compatible form: no sub-command, first arg is the font path."""

    def test_no_subcommand_behaves_like_shape(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Ensure that omitting the sub-command still shapes words like `shape` does."""
        code = main([FONT, "നന്ദി"])
        assert code == 0
        (result,) = json.loads(capsys.readouterr().out)
        assert result["word"] == "നന്ദി"

    def test_no_arguments_prints_help_and_exits_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ensure that calling with no arguments at all prints help instead of erroring."""
        code = main([])
        assert code == 0
        assert "usage" in capsys.readouterr().out.lower()


class TestAlphabetCommand:
    """`malayalam_stroker alphabet <font>` — shape the full base alphabet."""

    def test_produces_a_standalone_entry_and_matra_syllables(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ensure that the alphabet command includes the standalone run and matra syllables."""
        code = main(["alphabet", FONT])
        assert code == 0
        results = json.loads(capsys.readouterr().out)
        words = [r["word"] for r in results]
        assert "standalone" in words
        assert len(words) > 1  # standalone + at least some matra syllables
