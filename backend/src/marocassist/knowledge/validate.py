"""Bundle-wide publishing rules (Phase 3 WP B; rights document sections 2,
3 and 5; security review T-2, T-8, T-11, T-13).

`content.py` checks each field; this module checks the rules that span
records. It is pure (no database, no network) so CI can run it as a dry run
on every pull request. Every rule reports a `Problem` with a stable code; the
loader refuses the whole bundle when any problem is found.

The dates are checked against `today` only where the future would be
impossible (verified or approved tomorrow). Expiry itself is never checked
here: content that reaches its review date stays loadable and is shown as
expired when read (T-10), so a redeploy never fails because time passed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from typing import Final

from marocassist.knowledge import pii, sanitise
from marocassist.knowledge.chunking import ChunkingError, chunk_body
from marocassist.knowledge.content import (
    Bundle,
    Citation,
    ConsulateAttribute,
    Fact,
    Item,
    Problem,
    Review,
    Source,
)
from marocassist.knowledge.domains import allowed_source_types, is_allowed_url

# Owner decision P3-D12 (2026-11-20): until the legal questions are
# answered, only own explanations, cited facts and own-words summaries.
POLICY_ALLOWED_RIGHTS_CLASSES: Final = frozenset({"R1", "R2", "R3"})

# What each rights class needs from every source it relies on (rights doc 3).
RIGHTS_REQUIREMENTS: Final[Mapping[str, frozenset[str]]] = {
    "R1": frozenset({"link"}),
    "R2": frozenset({"link", "cite_fact"}),
    "R3": frozenset({"link", "summary"}),
    "R4": frozenset({"link", "short_quote"}),
    "R5": frozenset({"link", "redistribute_document"}),
    "R6": frozenset({"link"}),
}
# Uses that need a recorded permission or open licence, not just reachability.
_PERMISSION_USES: Final = frozenset({"short_quote", "verbatim", "redistribute_document"})

PRIMARY_SOURCE_TYPES: Final = frozenset({"official", "consulate", "government"})

# Review periods after verification (decision P3-D6; rights doc 5.2).
ITEM_REVIEW_DAYS: Final[Mapping[str, int]] = {"procedure": 180, "faq": 180, "explanation": 365}
FEE_REVIEW_DAYS: Final = 90
FACT_REVIEW_DAYS: Final = 180
SOURCE_REVIEW_DAYS: Final = 180
ATTRIBUTE_REVIEW_DAYS: Final[Mapping[str, int]] = {"opening_hours": 90}
DEFAULT_ATTRIBUTE_REVIEW_DAYS: Final = 180


class _Checker:
    def __init__(self, bundle: Bundle, today: date) -> None:
        self.bundle = bundle
        self.today = today
        self.problems: list[Problem] = []
        self.sources: dict[str, Source] = {s.source_id: s for s in bundle.sources}
        self.consulates = {c.code for c in bundle.consulates}
        self.authors = {e.handle for e in bundle.manifest.editors if "author" in e.roles}
        self.reviewers = {e.handle for e in bundle.manifest.editors if "reviewer" in e.roles}

    def add(self, where: str, code: str, message: str) -> None:
        self.problems.append(Problem(where, code, message))

    # --- shared rules ------------------------------------------------------------------

    def duplicates(self, where: str, keys: Iterable[object], what: str) -> None:
        for key, count in Counter(keys).items():
            if count > 1:
                self.add(where, "duplicate", f"{what} {key} appears {count} times")

    def review(self, where: str, review: Review, *, approval_required: bool, since: date) -> None:
        if review.author not in self.authors:
            self.add(where, "unknown_editor", "author is not a registered author")
        if review.approver is None:
            if approval_required:
                self.add(where, "four_eyes_missing", "an approver is required")
            return
        if review.approver == review.author:
            self.add(where, "four_eyes_same", "approver must not be the author")
        if review.approver not in self.reviewers:
            self.add(where, "not_a_reviewer", "approver is not a registered reviewer")
        if review.approved_at is None:
            self.add(where, "approval_date", "approved_at is required with an approver")
        elif not since <= review.approved_at <= self.today:
            self.add(where, "approval_date", "approved_at must be between verification and today")

    def not_future(self, where: str, field: str, value: date | None) -> None:
        if value is not None and value > self.today:
            self.add(where, "dates", f"{field} is in the future")

    def review_due(
        self,
        where: str,
        *,
        due: date,
        base: date,
        days: int,
        override: str | None,
        valid_until: date | None = None,
    ) -> None:
        if due < base:
            self.add(where, "review_period", "review_due_at is before verification")
        if due > base + timedelta(days=days) and override is None:
            self.add(
                where,
                "review_period",
                f"review_due_at is more than {days} days after verification;"
                " give review_override_reason",
            )
        if valid_until is not None and due > valid_until:
            self.add(where, "review_after_validity", "review_due_at is after valid_until")

    def consulate_ref(self, where: str, code: str) -> None:
        if code not in self.consulates:
            self.add(where, "unknown_consulate", f"consulate {code} is not in consulates.json")

    def scope(self, where: str, scope: str) -> None:
        if scope.startswith("consulate:"):
            self.consulate_ref(where, scope.removeprefix("consulate:"))

    def citations(
        self, where: str, citations: list[Citation], *, uses: frozenset[str], current: bool
    ) -> list[Source]:
        self.duplicates(where, (c.source_id for c in citations), "citation of source")
        found: list[Source] = []
        for index, citation in enumerate(citations):
            here = f"{where}.citations.{index}"
            source = self.sources.get(citation.source_id)
            if source is None:
                self.add(here, "unknown_source", f"source {citation.source_id} is not registered")
                continue
            found.append(source)
            missing = uses - set(source.allowed_use)
            if missing:
                self.add(
                    here,
                    "rights_not_permitted",
                    f"source does not allow {', '.join(sorted(missing))}",
                )
            if current and source.status != "verified":
                self.add(here, "source_not_verified", f"source status is {source.status}")
        return found

    def json_text(self, where: str, value: object, *, scan_pii: bool) -> None:
        """Sanitise every string inside a JSON value."""
        if isinstance(value, str):
            normalised, findings = sanitise.check_text(value)
            for finding in findings:
                self.add(where, "unsafe_text", finding.message)
            if normalised != value:
                self.add(where, "not_normalised", "text is not in Unicode NFKC form")
            if scan_pii and pii.scan(value):
                self.add(where, "personal_data", "possible personal data")
        elif isinstance(value, list):
            for index, element in enumerate(value):
                self.json_text(f"{where}.{index}", element, scan_pii=scan_pii)
        elif isinstance(value, dict):
            for key, element in value.items():
                self.json_text(f"{where}.{key}", element, scan_pii=scan_pii)

    # --- records -----------------------------------------------------------------------

    def manifest(self) -> None:
        self.duplicates(
            "manifest.json: editors", (e.handle for e in self.bundle.manifest.editors), "editor"
        )
        if not self.reviewers:
            self.add("manifest.json: editors", "no_reviewer", "at least one reviewer is required")

    def source(self, index: int, source: Source) -> None:
        where = f"sources.json: {index}"
        if source.status not in {"verified", "expired", "withdrawn"}:
            self.add(where, "source_not_ready", f"status {source.status} is not publishable")
        if source.status == "verified" and source.verified_at is None:
            self.add(where, "dates", "a verified source needs verified_at")
        self.not_future(where, "consulted_at", source.consulted_at)
        self.not_future(where, "verified_at", source.verified_at)
        if source.verified_at is not None and source.verified_at < source.consulted_at:
            self.add(where, "dates", "verified_at is before consulted_at")
        base = source.verified_at or source.consulted_at
        self.review_due(
            where,
            due=source.review_due_at,
            base=base,
            days=SOURCE_REVIEW_DAYS,
            override=source.review_override_reason,
            valid_until=source.valid_until,
        )
        if source.source_type not in allowed_source_types(source.official_url):
            self.add(
                where,
                "domain_not_allowed",
                f"official_url domain is not allow-listed for type {source.source_type}",
            )
        if source.licence != "unknown" and source.rights_evidence_ref is None:
            self.add(where, "rights_evidence", "a licence other than unknown needs evidence")
        permitted = source.licence.startswith(("written_permission:", "open_licence:"))
        excess = _PERMISSION_USES & set(source.allowed_use)
        if excess and not permitted:
            self.add(
                where,
                "allowed_use_exceeds_licence",
                f"{', '.join(sorted(excess))} needs a written permission or open licence",
            )
        if "link" not in source.allowed_use:
            self.add(where, "link_required", "every source must allow link")
        self.duplicates(where, source.allowed_use, "allowed_use")
        for code in source.consulate_codes:
            self.consulate_ref(where, code)
        self.scope(where, source.geo_scope)
        self.review(where, source.review, approval_required=True, since=base)

    def permission_evidence(self, where: str, rights_class: str, sources: list[Source]) -> None:
        """R4-R6 also need recorded evidence; R5 and R6 a written permission
        (rights doc 3)."""
        if rights_class not in {"R4", "R5", "R6"}:
            return
        for source in sources:
            if source.rights_evidence_ref is None:
                self.add(where, "rights_evidence", "every source needs rights evidence")
            if rights_class != "R4" and not source.licence.startswith("written_permission:"):
                self.add(where, "rights_evidence", "every source needs written permission")

    def item(self, item: Item, item_ids: set[str]) -> None:
        where = f"items/{item.item_id}.json"
        if item.rights_class not in POLICY_ALLOWED_RIGHTS_CLASSES:
            self.add(
                where,
                "rights_class_not_allowed",
                f"{item.rights_class} is not allowed until the legal questions are answered",
            )
        current = item.status == "published"
        sources = self.citations(
            where, item.citations, uses=RIGHTS_REQUIREMENTS[item.rights_class], current=current
        )
        self.permission_evidence(where, item.rights_class, sources)
        for code in item.consulate_scope:
            self.consulate_ref(where, code)
        self.duplicates(where, item.consulate_scope, "consulate")
        self.duplicates(where, item.country_scope, "country")
        if item.superseded_by is not None:
            if item.status != "withdrawn":
                self.add(where, "superseded_by", "only a withdrawn item can be superseded")
            if item.superseded_by == item.item_id or item.superseded_by not in item_ids:
                self.add(
                    where, "superseded_by", "superseded_by must name another item in the bundle"
                )

        published = [t for t in item.texts.values() if t.lang_status == "published"]
        if current and not published:
            self.add(where, "no_published_text", "a published item needs a published text")
        for lang, text in item.texts.items():
            here = f"{where}: texts.{lang}"
            self.not_future(here, "verified_at", text.verified_at)
            self.review(
                here,
                text.review,
                approval_required=text.lang_status == "published" or text.ai_assisted,
                since=text.verified_at,
            )
            try:
                chunk_body(text.body)
            except ChunkingError as exc:
                self.add(f"{here}.body", "chunking", str(exc))
        if published:
            validity = [s.valid_until for s in sources if s.valid_until is not None]
            self.review_due(
                where,
                due=item.review_due_at,
                base=min(t.verified_at for t in published),
                days=ITEM_REVIEW_DAYS[item.kind],
                override=item.review_override_reason,
                valid_until=min(validity) if validity else None,
            )

    def fact(self, index: int, fact: Fact) -> None:
        where = f"facts.json: {index}"
        current = fact.status != "withdrawn"
        sources = self.citations(
            where, fact.citations, uses=RIGHTS_REQUIREMENTS["R2"], current=current
        )
        if current and not any(s.source_type in PRIMARY_SOURCE_TYPES for s in sources):
            self.add(where, "no_primary_source", "a fact needs an official or government source")
        for c_index, citation in enumerate(fact.citations):
            if citation.locator is None:
                self.add(f"{where}.citations.{c_index}", "locator_required", "facts need a locator")
        self.scope(where, fact.scope)
        self.not_future(where, "verified_at", fact.verified_at)
        if fact.valid_until is not None and fact.valid_until < fact.valid_from:
            self.add(where, "dates", "valid_until is before valid_from")
        if fact.value is None:
            self.add(where, "value", "value must not be null")
        self.json_text(f"{where}.value", fact.value, scan_pii=True)
        is_fee = fact.fact_key.startswith("fee.")
        if is_fee and fact.unit is None:
            self.add(where, "unit_required", "a fee needs a unit")
        self.review_due(
            where,
            due=fact.review_due_at,
            base=fact.verified_at,
            days=FEE_REVIEW_DAYS if is_fee else FACT_REVIEW_DAYS,
            override=fact.review_override_reason,
            valid_until=fact.valid_until,
        )
        self.review(where, fact.review, approval_required=True, since=fact.verified_at)

    def attribute(self, where: str, attribute: ConsulateAttribute) -> None:
        is_name = attribute.attribute == "display_name"
        if is_name != (attribute.lang is not None):
            self.add(where, "attribute_lang", "lang is required for display_name and only there")
        if attribute.attribute == "opening_hours" and attribute.status != "verified":
            # Decision P3-D5: opening hours stay "not available" until verified.
            self.add(where, "opening_hours_unverified", "opening hours must be verified")
        source = self.sources.get(attribute.source_id)
        if source is None:
            self.add(where, "unknown_source", f"source {attribute.source_id} is not registered")
        else:
            if "cite_fact" not in source.allowed_use:
                self.add(where, "rights_not_permitted", "source does not allow cite_fact")
            if attribute.status != "withdrawn" and source.status != "verified":
                self.add(where, "source_not_verified", f"source status is {source.status}")
        value = attribute.value
        if attribute.attribute in {"display_name", "physical_city"}:
            if not isinstance(value, str) or not value.strip():
                self.add(where, "value", "value must be a non-empty string")
        elif not isinstance(value, dict) or not value:
            self.add(where, "value", "value must be a non-empty object")
        elif attribute.attribute == "contact":
            url = value.get("url")
            if url is not None and not (isinstance(url, str) and is_allowed_url(url)):
                self.add(where, "domain_not_allowed", "contact url is not allow-listed")
            value = {k: v for k, v in value.items() if k != "url"}
        # Office contact details are allowed in address and contact only (rights doc 9).
        self.json_text(
            f"{where}.value",
            value,
            scan_pii=attribute.attribute not in {"address", "contact"},
        )
        self.not_future(where, "verified_at", attribute.verified_at)
        self.review_due(
            where,
            due=attribute.review_due_at,
            base=attribute.verified_at,
            days=ATTRIBUTE_REVIEW_DAYS.get(attribute.attribute, DEFAULT_ATTRIBUTE_REVIEW_DAYS),
            override=attribute.review_override_reason,
        )
        self.review(where, attribute.review, approval_required=True, since=attribute.verified_at)

    def consulate(self, index: int) -> None:
        consulate = self.bundle.consulates[index]
        where = f"consulates.json: {index}"
        self.duplicates(where, ((a.attribute, a.lang) for a in consulate.attributes), "attribute")
        for a_index, attribute in enumerate(consulate.attributes):
            self.attribute(f"{where}.attributes.{a_index}", attribute)
        self.duplicates(
            where, (j.municipality_code for j in consulate.jurisdictions), "municipality"
        )
        for j_index, jurisdiction in enumerate(consulate.jurisdictions):
            here = f"{where}.jurisdictions.{j_index}"
            # Never derived (search doc 6): only from a verified official source.
            if jurisdiction.status != "verified":
                self.add(here, "jurisdiction_unverified", "jurisdiction must be verified")
            source = self.sources.get(jurisdiction.source_id)
            if source is None:
                self.add(
                    here, "unknown_source", f"source {jurisdiction.source_id} is not registered"
                )
            elif source.source_type not in PRIMARY_SOURCE_TYPES or source.status != "verified":
                self.add(here, "no_primary_source", "needs a verified official source")
            self.not_future(here, "verified_at", jurisdiction.verified_at)
            self.review(
                here, jurisdiction.review, approval_required=True, since=jurisdiction.verified_at
            )

    def succession_cycles(self) -> None:
        successor = {i.item_id: i.superseded_by for i in self.bundle.items if i.superseded_by}
        for start in successor:
            seen = {start}
            current = successor.get(start)
            while current is not None:
                if current in seen:
                    self.add(f"items/{start}.json", "superseded_by", "superseded_by forms a cycle")
                    break
                seen.add(current)
                current = successor.get(current)

    def run(self) -> list[Problem]:
        bundle = self.bundle
        self.manifest()
        self.duplicates("sources.json", (s.source_id for s in bundle.sources), "source_id")
        self.duplicates("items", (i.item_id for i in bundle.items), "item_id")
        self.duplicates("facts.json", (f.fact_id for f in bundle.facts), "fact_id")
        self.duplicates("consulates.json", (c.code for c in bundle.consulates), "code")
        for index, source in enumerate(bundle.sources):
            self.source(index, source)
        item_ids = {i.item_id for i in bundle.items}
        for item in bundle.items:
            self.item(item, item_ids)
        self.succession_cycles()
        for index, fact in enumerate(bundle.facts):
            self.fact(index, fact)
        if bundle.terms is not None:
            self.duplicates(
                "terms.json",
                ((t.lang, t.term, t.canonical_key, t.kind) for t in bundle.terms.terms),
                "term",
            )
            self.review(
                "terms.json: review", bundle.terms.review, approval_required=True, since=date.min
            )
        for index in range(len(bundle.consulates)):
            self.consulate(index)
        return self.problems


def validate_bundle(bundle: Bundle, *, today: date) -> list[Problem]:
    """Every bundle-wide problem; empty means the bundle may be published."""
    return _Checker(bundle, today).run()
