"""Tests for malayalam_stroker._chars — the Malayalam Unicode character inventory.

Explicitly Malayalam-specific (unlike test_geometry.py/test_centering.py/
test_ghost_reference.py/test_stroke_compose.py, which test the
script-agnostic engine). A future script's own character inventory should
get its own `test_chars_<script>.py` file rather than touching this one.
"""

from __future__ import annotations

from malayalam_stroker import _chars

# Malayalam Unicode block, per the Unicode Standard.
MALAYALAM_BLOCK = range(0x0D00, 0x0D80)

TUPLE_CONSTANTS = [
    "INDEPENDENT_VOWELS",
    "RARE_VOWELS",
    "REGULAR_CONSONANTS",
    "SPECIAL_CONSONANTS",
    "RARE_CONSONANTS",
    "CONSONANTS",
    "CHILLU",
    "NUMERALS",
    "MATRAS",
    "RARE_MATRAS",
]

SCALAR_CONSTANTS = ["AU_LENGTH_MARK", "VIRAMA", "ANUSVARA", "VISARGA"]


class TestExpectedCounts:
    """Each category has the specific count documented in its own comment."""

    def test_independent_vowels_count(self) -> None:
        """Ensure that there are exactly 13 independent vowels."""
        assert len(_chars.INDEPENDENT_VOWELS) == 13

    def test_rare_vowels_count(self) -> None:
        """Ensure that there are exactly 3 rare independent vowels."""
        assert len(_chars.RARE_VOWELS) == 3

    def test_regular_consonants_count(self) -> None:
        """Ensure that there are exactly 33 regular consonants."""
        assert len(_chars.REGULAR_CONSONANTS) == 33

    def test_special_consonants_count(self) -> None:
        """Ensure that there are exactly 3 special (Dravidian) consonants."""
        assert len(_chars.SPECIAL_CONSONANTS) == 3

    def test_consonants_is_regular_plus_special(self) -> None:
        """Ensure that CONSONANTS is exactly REGULAR_CONSONANTS + SPECIAL_CONSONANTS."""
        assert _chars.CONSONANTS == _chars.REGULAR_CONSONANTS + _chars.SPECIAL_CONSONANTS
        assert len(_chars.CONSONANTS) == 36

    def test_rare_consonants_count(self) -> None:
        """Ensure that there are exactly 2 rare/archaic consonants."""
        assert len(_chars.RARE_CONSONANTS) == 2

    def test_chillu_count(self) -> None:
        """Ensure that there are exactly 6 chillu letters."""
        assert len(_chars.CHILLU) == 6

    def test_numerals_count(self) -> None:
        """Ensure that there are exactly 10 Malayalam digits."""
        assert len(_chars.NUMERALS) == 10

    def test_matras_count(self) -> None:
        """Ensure that there are exactly 12 common dependent vowel signs."""
        assert len(_chars.MATRAS) == 12

    def test_rare_matras_count(self) -> None:
        """Ensure that there are exactly 3 rare dependent vowel signs."""
        assert len(_chars.RARE_MATRAS) == 3


class TestNoDuplicates:
    """No category contains the same character twice."""

    def test_each_tuple_constant_has_unique_characters(self) -> None:
        """Ensure that every tuple constant contains only distinct characters."""
        for name in TUPLE_CONSTANTS:
            value = getattr(_chars, name)
            assert len(value) == len(set(value)), f"{name} has duplicate characters"


class TestNoOverlapBetweenCategories:
    """No character belongs to two different top-level categories."""

    def test_categories_are_pairwise_disjoint(self) -> None:
        """Ensure that no character appears in more than one distinct category."""
        categories = {
            "INDEPENDENT_VOWELS": set(_chars.INDEPENDENT_VOWELS),
            "RARE_VOWELS": set(_chars.RARE_VOWELS),
            "CONSONANTS": set(_chars.CONSONANTS),
            "RARE_CONSONANTS": set(_chars.RARE_CONSONANTS),
            "CHILLU": set(_chars.CHILLU),
            "NUMERALS": set(_chars.NUMERALS),
            "MATRAS": set(_chars.MATRAS),
            "RARE_MATRAS": set(_chars.RARE_MATRAS),
        }
        names = list(categories)
        for i, name_a in enumerate(names):
            for name_b in names[i + 1 :]:
                overlap = categories[name_a] & categories[name_b]
                assert not overlap, f"{name_a} and {name_b} overlap: {overlap}"


class TestAllCharactersAreInTheMalayalamBlock:
    """Every character constant falls within U+0D00-U+0D7F."""

    def test_tuple_constants(self) -> None:
        """Ensure that every character in every tuple constant is in the Malayalam block."""
        for name in TUPLE_CONSTANTS:
            for ch in getattr(_chars, name):
                assert ord(ch) in MALAYALAM_BLOCK, f"{name} contains {ch!r} outside the block"

    def test_scalar_constants(self) -> None:
        """Ensure that every scalar (single-character) constant is in the Malayalam block."""
        for name in SCALAR_CONSTANTS:
            ch = getattr(_chars, name)
            assert ord(ch) in MALAYALAM_BLOCK, f"{name} ({ch!r}) is outside the block"


class TestPublicApi:
    """__all__ matches exactly what's importable, with no accidental omissions."""

    def test_all_matches_module_exports(self) -> None:
        """Ensure that __all__ lists exactly the tuple and scalar constants."""
        expected = set(TUPLE_CONSTANTS) | set(SCALAR_CONSTANTS)
        assert set(_chars.__all__) == expected
