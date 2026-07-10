"""Complete Unicode character inventory for the Malayalam script."""

from __future__ import annotations

# All constants are tuple[str, ...] (ordered, hashable) so callers can
# iterate them or pass them directly to frozenset when order doesn't matter.

__all__ = [
    "ANUSVARA",
    "AU_LENGTH_MARK",
    "CHILLU",
    "CONSONANTS",
    "INDEPENDENT_VOWELS",
    "MATRAS",
    "NUMERALS",
    "RARE_CONSONANTS",
    "RARE_MATRAS",
    "RARE_VOWELS",
    "REGULAR_CONSONANTS",
    "SPECIAL_CONSONANTS",
    "VIRAMA",
    "VISARGA",
]

#: 13 independent vowels (standalone at word start).
INDEPENDENT_VOWELS: tuple[str, ...] = tuple("അആഇഈഉഊഋഎഏഐഒഓഔ")

#: 3 rare independent vowels used only in Sanskrit loanwords.
#: ൠ = long vocalic R, ഌ = vocalic L, ൡ = long vocalic L.
RARE_VOWELS: tuple[str, ...] = ("ൠ", "ഌ", "ൡ")

#: 33 regular consonants.
REGULAR_CONSONANTS: tuple[str, ...] = tuple("കഖഗഘങചഛജഝഞടഠഡഢണതഥദധനപഫബഭമയരലവശഷസഹ")

#: 3 special consonants (Dravidian, not in Sanskrit).
SPECIAL_CONSONANTS: tuple[str, ...] = tuple("ളഴറ")

#: 2 rare/archaic consonants: ഩ (alveolar na, U+0D29), ഺ (alveolar ta, U+0D3A).
#: These appear in some traditional texts and are included for completeness.
RARE_CONSONANTS: tuple[str, ...] = ("ഩ", "ഺ")

#: All 36 consonants (regular + special), in standard order.
#: Does not include RARE_CONSONANTS — add those explicitly if needed.
CONSONANTS: tuple[str, ...] = REGULAR_CONSONANTS + SPECIAL_CONSONANTS

#: 6 chillu letters (pure consonants, no inherent vowel).
#: ൻ ർ ൽ ൾ ൺ ൿ (chillu ka, U+0D7F).
CHILLU: tuple[str, ...] = tuple("ൻർൽൾൺൿ")

#: 10 Malayalam digit characters.
NUMERALS: tuple[str, ...] = tuple("൦൧൨൩൪൫൬൭൮൯")

#: 12 dependent vowel signs (matras) for common Malayalam.
#: Uses U+0D4C (ൌ) for the au vowel sign — this is the canonical form
#: that triggers the full split-vowel rendering (component before + after the base).
MATRAS: tuple[str, ...] = tuple("ാിീുൂൃെേൈൊോൌ")

#: Au length mark (U+0D57 ൗ) — a separate codepoint sometimes used standalone
#: or as a component; distinct from the au vowel sign U+0D4C in MATRAS above.
AU_LENGTH_MARK: str = "\u0d57"

#: 3 rare matra signs used only in Sanskrit loanwords.
#: ൄ = vocalic RR sign (U+0D44), ൢ = vocalic L sign (U+0D62), ൣ = vocalic LL sign (U+0D63).
RARE_MATRAS: tuple[str, ...] = ("\u0d44", "\u0d62", "\u0d63")

#: Virama (chandrakkala) — suppresses the inherent vowel.
VIRAMA: str = "\u0d4d"

#: Anusvara — nasalisation sign ം.  # noqa: RUF003
ANUSVARA: str = "\u0d02"

#: Visarga — aspiration sign ഃ.
VISARGA: str = "\u0d03"
