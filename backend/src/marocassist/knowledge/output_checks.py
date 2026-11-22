"""Deterministic checks on a model answer (Phase 3 WP H, ready for Phase 4;
search architecture section 5; security review section 3, control 6).

`check_answer` takes the raw answer and the evidence pack it was given and
returns the text to show, the findings, and whether the answer is blocked.
A blocked answer is replaced by `fallback_reply`: the fixed "I cannot
confirm this" text with the official source cards of the pack.

Repaired, not blocked:

- citations to ids that are not in the pack are removed;
- a status the answer must state (expired, conflict, secondary-only, under
  review) is appended as a fixed notice when the answer lacks it.

Blocked:

- a procedural sentence (a number, or a procedural word such as
  appointment, bring, pay, fee) without a citation;
- an amount with a currency that equals no fact value in the pack, or a
  sentence citing a fact with a different number;
- a link or domain that is not one of the pack's source-card URLs;
- a request for a password, code, PIN, CNIE, passport, BSN, card or bank
  number, or for a money transfer;
- contact details (phone, e-mail), personal identifiers, messaging apps or
  intermediaries: only the official sources may be referred to;
- hidden characters (bidi, zero-width, invisible, control);
- an answer in another language than the pack's;
- any answer to an empty pack other than the fixed reply.

The rules err on the side of blocking: an answer such as "never share your
DigiD code" is blocked too and replaced by the fixed reply, which is safe.
Messages and notices are fixed texts per language, in answer_texts.json;
findings never repeat the answer text.

The source is ASCII only: non-Latin text is written as escapes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from importlib import resources
from typing import Final

from marocassist.knowledge import normalise, pii, sanitise
from marocassist.knowledge.evidence import EvidencePack

# --- Fixed texts -------------------------------------------------------------------

_TEXTS: Final = json.loads(
    resources.files("marocassist.knowledge").joinpath("answer_texts.json").read_text("utf-8")
)
NOTICES: Final[dict[str, dict[str, str]]] = _TEXTS["notices"]
NO_EVIDENCE: Final[dict[str, str]] = _TEXTS["no_evidence"]
CLARIFY_CONSULATE: Final[dict[str, str]] = _TEXTS["clarify_consulate"]

BLOCKING: Final = frozenset(
    {
        "uncited_claim",
        "fact_mismatch",
        "url_not_allowed",
        "credential_request",
        "payment_request",
        "contact_not_allowed",
        "hidden_characters",
        "wrong_language",
        "no_evidence",
    }
)

# --- Patterns (matched against `sanitise.fold` output where noted) -----------------

_CITATION: Final = re.compile(r"\[\s*([SF]\d{1,2}(?:\s*,\s*[SF]\d{1,2})*)\s*\]")
_LABEL: Final = re.compile(r"[SF]\d{1,2}")
_SENTENCE: Final = re.compile(r"(?<=[.!?\u061f])\s+|\n+")
_DIGIT: Final = re.compile(r"\d")
_NUMBER: Final = r"\d+(?:[.,]\d+)?"
_CURRENCY: Final = r"(?:mad|dhs?|dirhams?|\u062f\u0631\u0647\u0645|eur|euros?|\u20ac)"
_AMOUNT: Final = re.compile(
    rf"(?:(?P<a>{_NUMBER})\s?(?P<u1>{_CURRENCY})(?!\w)|(?P<u2>{_CURRENCY})\s?(?P<b>{_NUMBER}))",
    re.IGNORECASE,
)
_UNIT_OF: Final = {"mad": "MAD", "dh": "MAD", "dhs": "MAD", "eur": "EUR", "\u20ac": "EUR"}
_URL: Final = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>()\[\]\"']+")
_DOMAIN: Final = re.compile(
    r"(?i)\b(?:[a-z0-9-]+\.)+(?:nl|ma|be|fr|de|eu|com|org|net|info|io|gov)\b(?:/[^\s]*)?"
)

# Procedural words, folded.
_PROCEDURAL: Final = re.compile(
    r"\b(?:"
    r"afspraak|meenemen|neem|betaal\w*|kosten|leges|aanvra\w*|inschrij\w*|legalise\w*"
    r"|formulier|document\w*|rendez-vous|apportez|payez|frais|droits|demand\w*|depos\w*"
    r"|formulaire|appointment|bring|pay|fees?|apply|register\w*|form"
    r"|\u0645\u0648\u0639\u062f"
    r"|\u0627\u062d\u0636\u0631"
    r"|\u0627\u0644\u0631\u0633\u0648\u0645"
    r"|\u0627\u062f\u0641\u0639"
    r"|\u0648\u062b\u064a\u0642\u0647"
    r")\b"
)
_REQUEST_VERBS: Final = (
    r"send|give|share|enter|provide|tell|type|submit|email|text|reply"
    r"|stuur\w*|geef|geeft|geven|deel|deelt|delen|vul|invullen|noem|doorgeven|sturen"
    r"|envoye[rz]|donne[rz]|communique[rz]|saisisse[rz]|indique[rz]|partage[rz]|transmet\w*"
    r"|\u0627\u0631\u0633\u0644"
    r"|\u0627\u0639\u0637"
    r"|\u0634\u0627\u0631\u0643"
    r"|\u0627\u062f\u062e\u0644"
    r"|\u0627\u0643\u062a\u0628"
)
_SECRETS: Final = (
    r"password|passcode|pin|pincode|wachtwoord|digid\S*|sms[- ]?code|verificatiecode|inlogcode"
    r"|code|codes|mot de passe|code secret|numero de passeport|numero de carte|cnie|bsn|iban"
    r"|rekeningnummer|creditcard|credit card|card number|kaartnummer|cvv|passport number"
    r"|paspoortnummer|burgerservicenummer"
    r"|\u0643\u0644\u0645\u0647 \u0627\u0644\u0633\u0631"
    r"|\u0643\u0644\u0645\u0647 \u0627\u0644\u0645\u0631\u0648\u0631"
    r"|(?:\u0627\u0644)?\u0631\u0645\u0632"
    r"|\u0631\u0642\u0645 \u062c\u0648\u0627\u0632"
    r"|\u0631\u0642\u0645 \u0627\u0644\u0628\u0637\u0627\u0642\u0647"
)
_WINDOW: Final = r"(?:\W+\w+){0,5}?\W+"
_CREDENTIAL: Final = re.compile(
    rf"\b(?:{_REQUEST_VERBS})\b{_WINDOW}(?:{_SECRETS})\b"
    rf"|\b(?:{_SECRETS})\b{_WINDOW}(?:{_REQUEST_VERBS})\b"
)
_PAYMENT: Final = re.compile(
    r"\b(?:overmak\w*|maak\w* \w+ over|transfer\w*|virement|western union|moneygram|tikkie"
    r"|betaalverzoek|paypal|crypto\w*|bitcoin|\u062a\u062d\u0648\u064a\u0644)\b"
)
_UNOFFICIAL: Final = re.compile(
    r"\b(?:whatsapp|telegram|snapchat|instagram|facebook|tiktok|bemiddelaar|tussenpersoon"
    r"|intermediaire|\u0633\u0645\u0633\u0627\u0631|\u0648\u0633\u064a\u0637)\b"
)
_HIDDEN_CODES: Final = frozenset({"bidi_control", "zero_width", "invisible", "control"})


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str

    @property
    def blocking(self) -> bool:
        return self.code in BLOCKING


@dataclass(frozen=True)
class AnswerCheck:
    text: str
    findings: tuple[Finding, ...]

    @property
    def blocked(self) -> bool:
        return any(f.blocking for f in self.findings)

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(f.code for f in self.findings)


# --- Helpers -----------------------------------------------------------------------


def _lang(pack: EvidencePack) -> str:
    return pack.lang if pack.lang in NO_EVIDENCE else "nl"


def _ascii_digits(text: str) -> str:
    return "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)


def _number(raw: str) -> float:
    return float(_ascii_digits(raw).replace(",", "."))


def _fact_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, dict):
        return _fact_number(value.get("amount"))
    return None


def _unit(raw: str) -> str:
    folded = raw.casefold()
    if folded.startswith("dirham") or folded == "\u062f\u0631\u0647\u0645":
        return "MAD"
    if folded.startswith("euro"):
        return "EUR"
    return _UNIT_OF.get(folded, folded.upper())


def _strip_unknown_citations(text: str, pack: EvidencePack) -> tuple[str, list[str]]:
    unknown: list[str] = []

    def keep(match: re.Match[str]) -> str:
        labels = _LABEL.findall(match.group(1))
        known = [label for label in labels if label in pack.labels]
        unknown.extend(label for label in labels if label not in pack.labels)
        return f"[{', '.join(known)}]" if known else ""

    cleaned = _CITATION.sub(keep, text)
    return re.sub(r"[ \t]+([.,;:!?])", r"\1", re.sub(r"[ \t]{2,}", " ", cleaned)), unknown


def _url_allowed(url: str, allowed: frozenset[str]) -> bool:
    url = url.rstrip(".,;:!?")
    if not url.lower().startswith("http"):
        url = "https://" + url
    targets = {a.rstrip("/") for a in allowed}
    return url.rstrip("/") in targets


def _allowed_hosts(allowed: frozenset[str]) -> set[str]:
    return {re.sub(r"^https?://", "", a).split("/", 1)[0].lower() for a in allowed}


def fallback_reply(pack: EvidencePack) -> str:
    """The fixed reply, with the pack's official source cards."""
    lang = _lang(pack)
    lines = [NO_EVIDENCE[lang]]
    lines += [
        f"- {c.publisher}: {c.url}"
        for c in pack.cards
        if c.badge == "official" and c.status == "current"
    ]
    return "\n".join(lines)


# --- The check ---------------------------------------------------------------------


def check_answer(answer: str, pack: EvidencePack) -> AnswerCheck:
    lang = _lang(pack)
    findings: list[Finding] = []
    text = unicodedata.normalize("NFKC", answer).strip()

    _normalised, text_findings = sanitise.check_text(text, multiline=True)
    if any(f.code in _HIDDEN_CODES for f in text_findings):
        findings.append(Finding("hidden_characters", "bidi, invisible or control characters"))

    if pack.empty:
        if text != NO_EVIDENCE[lang]:
            findings.append(Finding("no_evidence", "the pack is empty; only the fixed reply"))
        return _result(text, findings, pack)

    text, unknown = _strip_unknown_citations(text, pack)
    if unknown:
        findings.append(Finding("unknown_citation", f"removed: {', '.join(sorted(set(unknown)))}"))

    templates = {t for by_lang in NOTICES.values() for t in by_lang.values()}
    for index, sentence in enumerate(s for s in _SENTENCE.split(text) if s.strip()):
        cited = set(_LABEL.findall(" ".join(_CITATION.findall(sentence))))
        folded = sanitise.fold(sentence)
        procedural = bool(_DIGIT.search(sentence) or _PROCEDURAL.search(folded))
        if procedural and not cited and sentence.strip() not in templates:
            findings.append(Finding("uncited_claim", f"sentence {index + 1} has no citation"))
        findings.extend(_amount_findings(index, sentence, cited, pack))

    findings.extend(_link_findings(text, pack))
    findings.extend(_safety_findings(text))

    detected = normalise.detect_language(text)
    if detected is not None and detected != lang:
        findings.append(Finding("wrong_language", f"answer is {detected}, expected {lang}"))

    for notice in sorted(pack.notices):
        template = NOTICES[notice][lang]
        if template not in text:
            text = f"{text}\n\n{template}"
            findings.append(Finding("notice_appended", notice))
    return _result(text, findings, pack)


def _result(text: str, findings: list[Finding], pack: EvidencePack) -> AnswerCheck:
    check = AnswerCheck(text=text, findings=tuple(findings))
    if check.blocked:
        return AnswerCheck(text=fallback_reply(pack), findings=check.findings)
    return check


def _amount_findings(
    index: int, sentence: str, cited: set[str], pack: EvidencePack
) -> list[Finding]:
    findings = []
    known = {
        (number, fact.unit)
        for fact in pack.facts
        if (number := _fact_number(fact.value)) is not None
    }
    for match in _AMOUNT.finditer(sentence):
        raw = match.group("a") or match.group("b")
        unit = _unit(match.group("u1") or match.group("u2"))
        if (_number(raw), unit) not in known:
            findings.append(
                Finding("fact_mismatch", f"sentence {index + 1}: amount not in the evidence")
            )
    numbers = [_number(n) for n in re.findall(_NUMBER, _ascii_digits(sentence))]
    for label in sorted(cited):
        fact = pack.fact(label)
        if fact is None or not numbers:
            continue
        expected = _fact_number(fact.value)
        if expected is not None and expected not in numbers:
            findings.append(
                Finding("fact_mismatch", f"sentence {index + 1}: {label} has another value")
            )
    return findings


def _link_findings(text: str, pack: EvidencePack) -> list[Finding]:
    findings = []
    allowed = pack.allowed_urls
    for url in _URL.findall(text):
        if not _url_allowed(url, allowed):
            findings.append(Finding("url_not_allowed", "a link that is not a source card"))
    hosts = _allowed_hosts(allowed)
    for match in _DOMAIN.finditer(_URL.sub(" ", text)):
        if match.group().split("/", 1)[0].lower() not in hosts:
            findings.append(Finding("url_not_allowed", "a domain that is not a source card"))
    return findings


def _safety_findings(text: str) -> list[Finding]:
    findings = []
    folded = sanitise.fold(text)
    if _CREDENTIAL.search(folded):
        findings.append(Finding("credential_request", "asks for a password, code or number"))
    if _PAYMENT.search(folded):
        findings.append(Finding("payment_request", "asks for a money transfer"))
    kinds = pii.scan(_URL.sub(" ", text))
    if kinds or _UNOFFICIAL.search(folded):
        detail = ", ".join(kinds) if kinds else "messaging app or intermediary"
        findings.append(Finding("contact_not_allowed", detail))
    return findings
