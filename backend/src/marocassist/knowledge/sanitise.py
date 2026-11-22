"""Entry sanitiser for editorial text, per security review section 3, control 2.

Pure Python, no I/O. Used by the publishing loader on every text field that
can reach a user or the answer model, and later by editor tooling.

Policy:

- **Normalised automatically:** Unicode NFKC. This only folds presentation
  forms and compatibility characters (Arabic presentation forms to base
  letters, ligatures, non-breaking spaces) and never changes meaning.
- **Refused, never stripped silently:** bidi controls and marks ("Trojan
  Source"), zero-width and other invisible characters (variation selectors,
  filler letters, the braille blank), other control characters and line or
  paragraph separators, HTML or markup (including markdown comments and
  reference definitions), URLs in free text, since only the source register
  supplies links (T-8); words that mix Latin, Cyrillic or Greek letters
  (homoglyphs); the evidence delimiters and role markers of the answer
  prompt, and imperative phrases aimed at an AI in EN, FR, NL, AR and Darija.
  Stripping would hide an attack attempt and make the database differ from
  the reviewed file; a refusal makes the editor fix the file instead. The
  red-team suite (tests/fixtures/knowledge/redteam.json) lists the attacks
  each rule exists for, and benign texts that must keep passing.

The source is ASCII only: Arabic patterns are built from code points.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final


def _chars(*codepoints: int) -> str:
    return "".join(chr(c) for c in codepoints)


BIDI_CONTROLS: Final = frozenset(
    _chars(0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))
)
ZERO_WIDTH: Final = frozenset(_chars(0x200B, 0x200C, 0x200D, 0xFEFF))
# Characters that render as nothing (or as blank space) but are letters,
# marks or symbols, so the control-category check misses them: variation
# selectors (used to smuggle data), Hangul and Khmer fillers, braille blank.
INVISIBLE: Final = frozenset(
    _chars(
        *range(0xFE00, 0xFE10),
        *range(0xE0100, 0xE01F0),
        0x115F,
        0x1160,
        0x17B4,
        0x17B5,
        0x2800,
        0x3164,
        0xFFA0,
    )
)
_ALLOWED_CONTROLS: Final = frozenset("\n")
_REFUSED_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

# The last alternative is a markdown reference definition or comment
# ("[//]: # (...)"), which renders as nothing.
_MARKUP: Final = re.compile(
    r"<\s*[A-Za-z/!?|]|&[A-Za-z]+;|&#[0-9]+;|!\[|\]\(|^[ \t]{0,3}\[[^\]\n]*\]:", re.MULTILINE
)
_URL: Final = re.compile(r"(?i)\b(?:https?|ftp|javascript|data|file)\s*:|\bwww\.[a-z0-9-]")
_ROLE_MARKER: Final = re.compile(
    r"(?i)\b(?:system|assistant|developer)\s*:|\|>|\[/?inst\]|</?\s*(?:source|evidence|fact)\b"
)

# Arabic words, from code points, already in the folded form `fold()`
# produces (hamza seats unified, ta marbuta as ha, alif maqsura as ya).
# Verbs: tajahal ("ignore"), insa / insi ("forget", m./f.), Darija nsa,
# ahmil ("neglect"). Objects: al-ta'limat ("the instructions"), al-awamir
# ("the orders"). Phrases: ta'limat jadida ("new instructions"), anta al-an
# ("you are now").
_AR_IGNORE_VERBS: Final = "|".join(
    (
        _chars(0x062A, 0x062C, 0x0627, 0x0647, 0x0644),
        _chars(0x0627, 0x0646, 0x0633),
        _chars(0x0627, 0x0646, 0x0633, 0x064A),
        _chars(0x0646, 0x0633, 0x0627),
        _chars(0x0646, 0x0633, 0x064A),
        _chars(0x0627, 0x0647, 0x0645, 0x0644),
    )
)
_AR_INSTRUCTIONS: Final = "|".join(
    (
        _chars(0x0627, 0x0644, 0x062A, 0x0639, 0x0644, 0x064A, 0x0645, 0x0627, 0x062A),
        _chars(0x0627, 0x0644, 0x0627, 0x0648, 0x0627, 0x0645, 0x0631),
    )
)
_AR_NEW_INSTRUCTIONS: Final = (
    _chars(0x062A, 0x0639, 0x0644, 0x064A, 0x0645, 0x0627, 0x062A)
    + r"\s+"
    + _chars(0x062C, 0x062F, 0x064A, 0x062F, 0x0647)
)
_AR_YOU_ARE_NOW: Final = (
    _chars(0x0627, 0x0646, 0x062A) + r"\s+" + _chars(0x0627, 0x0644, 0x0627, 0x0646)
)
_GAP: Final = r"\s+(?:\S+\s+){0,2}"

# Matched against `fold()` output (lowercase, no accents, Arabic normalised).
# Second-person phrases use the informal singular ("tu", "je", "anta"),
# which procedural texts do not use: "vous etes maintenant inscrit" and "u
# bent nu ingeschreven" stay allowed.
INJECTION_PATTERNS: Final = tuple(
    re.compile(p)
    for p in (
        rf"\b(?:ignore|disregard|forget){_GAP}(?:previous|prior|above|earlier)\b",
        r"\byou are now\b",
        r"\bnew instructions\b",
        r"\b(?:system\s*prompt|prompt\s+systeme|systeemprompt)\b",
        rf"\b(?:ignore[rz]?|oublie[rz]?){_GAP}(?:instructions|consignes|regles)\b",
        r"\bnouvelles?\s+(?:instructions|consignes)\b",
        r"\btu es maintenant\b",
        rf"\b(?:negeer|vergeet){_GAP}(?:instructies|opdrachten)\b",
        r"\bnieuwe\s+instructies\b",
        r"\bje bent nu\b",
        rf"\b(?:{_AR_IGNORE_VERBS}){_GAP}(?:{_AR_INSTRUCTIONS})\b",
        rf"\b{_AR_NEW_INSTRUCTIONS}\b",
        rf"\b{_AR_YOU_ARE_NOW}\b",
    )
)

# Scripts whose letters look alike: one word that mixes them is a homoglyph
# attack (a Cyrillic "o" in "ignore"), never a real word.
_CONFUSABLE_SCRIPTS: Final = ("LATIN", "CYRILLIC", "GREEK")
_WORD: Final = re.compile(r"\w+")

_ARABIC_FOLD: Final = str.maketrans(
    {
        **dict.fromkeys(_chars(0x0623, 0x0625, 0x0622, 0x0671), chr(0x0627)),
        chr(0x0629): chr(0x0647),
        chr(0x0649): chr(0x064A),
        chr(0x0640): None,
    }
)


def fold(text: str) -> str:
    """Lowercase, without accents or Arabic diacritics, Arabic letter
    variants unified: the form the pattern checks run on."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return stripped.translate(_ARABIC_FOLD)


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


def _describe(char: str) -> str:
    return f"U+{ord(char):04X}"


def _mixed_script(text: str) -> bool:
    for word in _WORD.findall(text):
        scripts = {
            script
            for char in word
            if char.isalpha()
            for script in _CONFUSABLE_SCRIPTS
            if unicodedata.name(char, "").startswith(script)
        }
        if len(scripts) > 1:
            return True
    return False


def check_text(text: str, *, multiline: bool = False) -> tuple[str, list[Finding]]:
    """Return the NFKC-normalised text and every refusal reason. The text
    is acceptable only when the list is empty."""
    normalised = unicodedata.normalize("NFKC", text)
    findings: list[Finding] = []
    for char in sorted(set(normalised)):
        if char in BIDI_CONTROLS:
            findings.append(Finding("bidi_control", f"bidi control character {_describe(char)}"))
        elif char in ZERO_WIDTH:
            findings.append(Finding("zero_width", f"zero-width character {_describe(char)}"))
        elif char in INVISIBLE:
            findings.append(Finding("invisible", f"invisible character {_describe(char)}"))
        elif unicodedata.category(char) in _REFUSED_CATEGORIES and not (
            multiline and char in _ALLOWED_CONTROLS
        ):
            findings.append(
                Finding("control", f"control, separator or unassigned character {_describe(char)}")
            )
    if _MARKUP.search(normalised):
        findings.append(Finding("markup", "HTML, entity or markdown link/image markup"))
    if _URL.search(normalised):
        findings.append(Finding("url", "URL in free text; link through a registered source"))
    if _mixed_script(normalised):
        findings.append(Finding("mixed_script", "a word mixes Latin, Cyrillic or Greek letters"))
    if _ROLE_MARKER.search(normalised):
        findings.append(Finding("role_marker", "prompt delimiter or role marker"))
    folded = fold(normalised)
    if any(p.search(folded) for p in INJECTION_PATTERNS):
        findings.append(Finding("injection_phrase", "imperative phrase aimed at an AI"))
    return normalised, findings
