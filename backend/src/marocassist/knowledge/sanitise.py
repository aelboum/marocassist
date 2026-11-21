"""Entry sanitiser for editorial text, per security review section 3, control 2.

Pure Python, no I/O. Used by the publishing loader on every text field that
can reach a user or the answer model, and later by editor tooling.

Policy:

- **Normalised automatically:** Unicode NFKC. This only folds presentation
  forms and compatibility characters (Arabic presentation forms to base
  letters, ligatures, non-breaking spaces) and never changes meaning.
- **Refused, never stripped silently:** bidi controls ("Trojan Source"),
  zero-width characters, other control characters, HTML or markup, URLs in
  free text, since only the source register supplies links (T-8); the evidence
  delimiters and role markers of the answer prompt, and imperative phrases
  aimed at an AI. Stripping would hide an attack attempt and make the
  database differ from the reviewed file; a refusal makes the editor fix
  the file instead.

The source is ASCII only: Arabic patterns are built from code points.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final


def _chars(*codepoints: int) -> str:
    return "".join(chr(c) for c in codepoints)


BIDI_CONTROLS: Final = frozenset(_chars(*range(0x202A, 0x202F), *range(0x2066, 0x206A)))
ZERO_WIDTH: Final = frozenset(_chars(0x200B, 0x200C, 0x200D, 0xFEFF))
_ALLOWED_CONTROLS: Final = frozenset("\n")

_MARKUP: Final = re.compile(r"<\s*[A-Za-z/!?|]|&[A-Za-z]+;|&#[0-9]+;|!\[|\]\(")
_URL: Final = re.compile(r"(?i)\b(?:https?|ftp|javascript|data|file)\s*:|\bwww\.[a-z0-9-]")
_ROLE_MARKER: Final = re.compile(
    r"(?i)\b(?:system|assistant|developer)\s*:|\|>|\[/?inst\]|</?\s*(?:source|evidence|fact)\b"
)

# Arabic words, from code points: tajahal ("ignore"), al-ta'limat ("the
# instructions"), already in the folded form `fold()` produces.
_AR_IGNORE: Final = _chars(0x062A, 0x062C, 0x0627, 0x0647, 0x0644)
_AR_INSTRUCTIONS: Final = _chars(
    0x0627, 0x0644, 0x062A, 0x0639, 0x0644, 0x064A, 0x0645, 0x0627, 0x062A
)
_GAP: Final = r"\s+(?:\S+\s+){0,2}"

# Matched against `fold()` output (lowercase, no accents, Arabic normalised).
INJECTION_PATTERNS: Final = tuple(
    re.compile(p)
    for p in (
        rf"\b(?:ignore|disregard|forget){_GAP}(?:previous|prior|above|earlier)\b",
        r"\byou are now\b",
        r"\bnew instructions\b",
        rf"\b(?:ignore|ignorez|oublie|oubliez){_GAP}instructions\b",
        rf"\bnegeer{_GAP}instructies\b",
        rf"{_AR_IGNORE}{_GAP}{_AR_INSTRUCTIONS}",
    )
)

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
        elif unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co", "Cn"} and not (
            multiline and char in _ALLOWED_CONTROLS
        ):
            findings.append(
                Finding("control", f"control or unassigned character {_describe(char)}")
            )
    if _MARKUP.search(normalised):
        findings.append(Finding("markup", "HTML, entity or markdown link/image markup"))
    if _URL.search(normalised):
        findings.append(Finding("url", "URL in free text; link through a registered source"))
    if _ROLE_MARKER.search(normalised):
        findings.append(Finding("role_marker", "prompt delimiter or role marker"))
    folded = fold(normalised)
    if any(p.search(folded) for p in INJECTION_PATTERNS):
        findings.append(Finding("injection_phrase", "imperative phrase aimed at an AI"))
    return normalised, findings
