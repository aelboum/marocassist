"""Query preparation for knowledge search (Phase 3 WP C; search architecture
section 4). Pure Python: no database, no I/O.

A user's query is untrusted. It is capped, NFKC-normalised, stripped of
control, format (bidi, zero-width) and other invisible characters, and
reduced to plain words. The words are rebuilt into a `websearch_to_tsquery`
string by `build_tsquery`, so no operator or quote a user typed ever reaches
PostgreSQL, only the ones this module writes.

The Arabic folding mirrors the SQL normaliser `kn_normalise_arabic` in
migration 0003 (a test keeps the two identical). Accents and case are folded
again in SQL by `kn_normalise`, on both the index and the query side.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

LANGS: tuple[str, ...] = ("nl", "fr", "ar", "en")
DEFAULT_LANG = "nl"
MAX_QUERY_CHARS = 256
MAX_WORDS = 12
MAX_ALTERNATIVES = 6


def _arabic_table() -> tuple[str, str, str]:
    """(from, to, deleted): the same characters as the SQL translate()."""
    alef, heh, yeh = chr(0x0627), chr(0x0647), chr(0x064A)
    mapped_from = "".join(chr(c) for c in (0x0623, 0x0625, 0x0622, 0x0671, 0x0629, 0x0649))
    mapped_to = alef * 4 + heh + yeh
    digits_from = "".join(chr(c) for c in range(0x0660, 0x066A)) + "".join(
        chr(c) for c in range(0x06F0, 0x06FA)
    )
    digits_to = "0123456789" * 2
    deleted = "".join(chr(c) for c in range(0x064B, 0x0653)) + chr(0x0670) + chr(0x0640)
    return mapped_from + digits_from, mapped_to + digits_to, deleted


ARABIC_FROM, ARABIC_TO, ARABIC_DELETED = _arabic_table()
_ARABIC = str.maketrans(ARABIC_FROM, ARABIC_TO, ARABIC_DELETED)

# Letters and digits only: everything else (punctuation, websearch operators,
# quotes, symbols) separates words.
_WORD = re.compile(r"[^\W_]+")
# websearch_to_tsquery treats a bare "or" as an operator.
_OPERATOR_WORDS = frozenset({"or"})

# Small, high-frequency hint words per language. They only choose an extra
# search language; the UI language is always searched.
_HINTS: Mapping[str, frozenset[str]] = {
    "nl": frozenset(
        "de het een ik mijn hoe wat waar wanneer kan moet voor van bij met niet "
        "aanvragen verlengen paspoort consulaat afspraak kosten nodig welke "
        "geboorteakte huwelijk kind".split()
    ),
    "fr": frozenset(
        "le la les un une je mon ma mes comment quoi quand pour du des au est "
        "faut demande renouveler passeport consulat rendez vous acte naissance "
        "mariage enfant combien quels".split()
    ),
    "en": frozenset(
        "the a an my how what where when can must for of with is do does need "
        "apply renew passport consulate appointment birth certificate marriage "
        "child cost which".split()
    ),
}
_FRENCH_LETTERS = frozenset(
    "\u00e9\u00e8\u00ea\u00eb\u00e0\u00e2\u00e7\u00f9\u00fb\u00f4\u00ee\u00ef\u0153"
)


@dataclass(frozen=True)
class PreparedQuery:
    text: str
    words: tuple[str, ...]
    detected: str | None
    langs: tuple[str, ...]


def _visible(char: str) -> bool:
    return unicodedata.category(char)[0] != "C"


def clean(query: str) -> str:
    """Cap, NFKC, replace invisible characters by spaces, fold Arabic,
    collapse whitespace."""
    text = unicodedata.normalize("NFKC", query[: MAX_QUERY_CHARS * 2])
    text = "".join(ch if _visible(ch) else " " for ch in text)
    text = text.translate(_ARABIC)
    return " ".join(text.split())[:MAX_QUERY_CHARS]


def tokenise(text: str) -> list[str]:
    """Lowercased words without duplicates, operator words removed, at most
    MAX_WORDS. A single character is kept only when it is a digit."""
    words: list[str] = []
    for match in _WORD.finditer(text.lower()):
        word = match.group()
        if word in _OPERATOR_WORDS or (len(word) == 1 and not word.isdigit()):
            continue
        if word not in words:
            words.append(word)
        if len(words) == MAX_WORDS:
            break
    return words


def _is_arabic(char: str) -> bool:
    return "\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f"


def detect_language(text: str) -> str | None:
    """Arabic by script; NL, FR or EN by hint words (French accented letters
    count for French). None when nothing decides."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return None
    if sum(1 for ch in letters if _is_arabic(ch)) / len(letters) >= 0.3:
        return "ar"
    lowered = text.lower()
    words = [m.group() for m in _WORD.finditer(lowered)]
    scores = {lang: sum(1 for w in words if w in hints) for lang, hints in _HINTS.items()}
    scores["fr"] += sum(1 for ch in lowered if ch in _FRENCH_LETTERS)
    best = max(scores.values())
    leaders = [lang for lang, score in scores.items() if score == best]
    if best == 0 or len(leaders) > 1:
        return None
    return leaders[0]


def query_langs(ui_lang: str, detected: str | None) -> tuple[str, ...]:
    """The UI language first, then the detected query language."""
    first = ui_lang if ui_lang in LANGS else DEFAULT_LANG
    if detected and detected != first:
        return (first, detected)
    return (first,)


def prepare(query: str, ui_lang: str) -> PreparedQuery:
    text = clean(query)
    detected = detect_language(text)
    return PreparedQuery(
        text=text,
        words=tuple(tokenise(text)),
        detected=detected,
        langs=query_langs(ui_lang, detected),
    )


def _alternative(term: str) -> str | None:
    words = tokenise(clean(term))
    if not words:
        return None
    joined = " ".join(words)
    return f'"{joined}"' if len(words) > 1 else joined


def build_tsquery(
    words: Sequence[str],
    expansions: Mapping[str, Sequence[str]] | None = None,
    *,
    match_all: bool = True,
) -> str:
    """A `websearch_to_tsquery` string. Each word becomes a group
    `word or alt or "multi word alt"`; groups are joined by AND (a space)
    when `match_all`, else by `or`. websearch binds `or` tighter than the
    implicit AND, so `a or b c` means (a | b) & c. Expansion terms are
    re-tokenised, so they cannot inject operators either."""
    expansions = expansions or {}
    groups: list[str] = []
    for word in words:
        alternatives = [word]
        for term in expansions.get(word, ()):
            if len(alternatives) > MAX_ALTERNATIVES:
                break
            alt = _alternative(term)
            if alt and alt not in alternatives:
                alternatives.append(alt)
        groups.append(" or ".join(alternatives))
    return (" " if match_all else " or ").join(groups)
