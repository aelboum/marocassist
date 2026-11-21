"""Personal-data scan for knowledge content (rights document section 9,
security review T-3).

Knowledge holds no user data. Public office contact details are allowed only
in the consulate `contact` and `address` attributes, which the loader does
not pass through this scan. Everywhere else a hit refuses the content:

- e-mail addresses;
- phone numbers (nine or more digits in one number);
- identifier formats: BSN (Dutch citizen service number, eleven-test),
  CNIE and passport numbers (letters followed by digits), IBAN.

Deliberately over-inclusive: a false positive costs an editor a rewrite, a
false negative publishes personal data to every user.
"""

from __future__ import annotations

import re
from typing import Final

_DIGITS: Final = str.maketrans(
    {chr(base + i): str(i) for base in (0x0660, 0x06F0) for i in range(10)}
)

_EMAIL: Final = re.compile(
    r"[A-Za-z0-9._%+-]+\s*(?:@|\(at\)|\[at\])\s*[A-Za-z0-9-]+\.[A-Za-z0-9.-]+"
)
_PHONE: Final = re.compile(r"(?<![\w])(?:\+|00)?\d[\d \-./()]{6,}\d(?![\w])")
_PHONE_MIN_DIGITS: Final = 9
_DOCUMENT_NUMBER: Final = re.compile(r"\b[A-Z]{1,2}\d{5,7}\b")
_IBAN: Final = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
_BSN: Final = re.compile(r"(?<!\d)\d{8,9}(?!\d)")


def _is_bsn(candidate: str) -> bool:
    digits = candidate.zfill(9)
    total = sum(int(d) * w for d, w in zip(digits[:8], range(9, 1, -1), strict=True))
    return (total - int(digits[8])) % 11 == 0


def scan(text: str) -> list[str]:
    """Names of the personal-data patterns found in `text` (empty if none)."""
    text = text.translate(_DIGITS)
    hits: list[str] = []
    if _EMAIL.search(text):
        hits.append("email")
    for match in _PHONE.finditer(text):
        if sum(c.isdigit() for c in match.group()) >= _PHONE_MIN_DIGITS:
            hits.append("phone")
            break
    if _DOCUMENT_NUMBER.search(text):
        hits.append("document_number")
    if _IBAN.search(text):
        hits.append("iban")
    if any(_is_bsn(m.group()) for m in _BSN.finditer(text)):
        hits.append("bsn")
    return hits
