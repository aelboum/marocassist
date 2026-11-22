"""Content bundle format: the files editors write and the publishing loader
reads (Phase 3 WP B; rights document sections 2-5; decision P3-D2).

A bundle is a directory:

    manifest.json      format version and the editor register
    sources.json       list of sources (the source register)
    items/<id>.json    one knowledge item per file; the file name is the item id
    facts.json         list of structured facts
    terms.json         {"review": ..., "terms": [...]} search terms
    consulates.json    list of consulates with their attributes

Only `manifest.json` is required. The JSON schema editors can validate
against is generated from these models (`knowledge/content.schema.json`, kept
in sync by a test).

Field validation here is per field: shapes, patterns, lengths, and the
sanitiser and personal-data scan on every free-text field. Rules that span
records (citations, rights, four-eyes, dates) are in `validate.py`.

Editors are identified by a pseudonymous handle (`ed-...`), never by name,
e-mail or SaaS-OS user id, because content files live in a public
repository. Editorial-only fields (`review`, `notes`, `owner_reviewer`) are
never written to the database (T-3).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
)
from pydantic_core import PydanticCustomError

from marocassist.knowledge import pii, sanitise

FORMAT_VERSION: Final = 1
MAX_FILE_BYTES: Final = 1_000_000

# --- Text fields -----------------------------------------------------------------------


def _clean(value: str, *, multiline: bool) -> str:
    normalised, findings = sanitise.check_text(value, multiline=multiline)
    if findings:
        raise PydanticCustomError(
            "unsafe_text", "refused: {reasons}", {"reasons": "; ".join(f.message for f in findings)}
        )
    hits = pii.scan(normalised)
    if hits:
        raise PydanticCustomError(
            "personal_data", "possible personal data: {kinds}", {"kinds": ", ".join(hits)}
        )
    stripped = normalised.strip()
    if not stripped:
        raise PydanticCustomError("empty_text", "must not be blank")
    return stripped


def _line(value: str) -> str:
    return _clean(value, multiline=False)


def _block(value: str) -> str:
    return _clean(value, multiline=True)


Line200 = Annotated[str, StringConstraints(max_length=200), AfterValidator(_line)]
Line300 = Annotated[str, StringConstraints(max_length=300), AfterValidator(_line)]
Keyword = Annotated[str, StringConstraints(max_length=60), AfterValidator(_line)]
TermText = Annotated[str, StringConstraints(max_length=120), AfterValidator(_line)]
Body = Annotated[str, StringConstraints(max_length=20000), AfterValidator(_block)]
Note = Annotated[str, StringConstraints(max_length=2000), AfterValidator(_block)]

# --- Identifiers -----------------------------------------------------------------------

Lang = Literal["nl", "fr", "ar", "en"]
Handle = Annotated[str, StringConstraints(pattern=r"^ed-[a-z0-9-]{2,30}$")]
SourceId = Annotated[str, StringConstraints(pattern=r"^src-[a-z0-9-]{2,76}$")]
ItemId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]{1,79}$")]
FactId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")]
FactKey = Annotated[str, StringConstraints(max_length=120, pattern=r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")]
CanonicalKey = Annotated[
    str, StringConstraints(max_length=120, pattern=r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
]
TopicKey = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{2,40}$")]
ConsulateCode = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{2,32}$")]
Country = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
Scope = Annotated[
    str,
    StringConstraints(
        pattern=r"^(global|country:[A-Z]{2}|consulate:[a-z0-9-]{2,32}|region:[a-z0-9-]{2,32})$"
    ),
]
HttpsUrl = Annotated[
    str, StringConstraints(max_length=2000, pattern=r"^https://[A-Za-z0-9.-]+(/[^\s]*)?$")
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Licence = Annotated[
    str,
    StringConstraints(
        pattern=r"^(unknown|all_rights_reserved|open_licence:[A-Za-z0-9.-]{1,80}"
        r"|written_permission:[A-Za-z0-9._/-]{1,80})$"
    ),
]
EvidenceRef = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._/:-]{1,200}$")]
AllowedUse = Literal[
    "link", "cite_fact", "summary", "short_quote", "verbatim", "redistribute_document"
]
RightsClass = Literal["R1", "R2", "R3", "R4", "R5", "R6"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Review(_Model):
    """Four-eyes record (rights document 5.1, gate 5). Checked in
    `validate.py`: the approver must be a registered reviewer and not the
    author."""

    author: Handle
    approver: Handle | None = None
    approved_at: date | None = None


class Citation(_Model):
    source_id: SourceId
    locator: Line200 | None = None


class Source(_Model):
    source_id: SourceId
    title: Line300
    official_url: HttpsUrl
    publisher: Line200
    publisher_key: Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{2,40}$")]
    source_type: Literal["official", "government", "consulate", "secondary", "internal"]
    country: Country
    geo_scope: Scope
    consulate_codes: list[ConsulateCode] = Field(default_factory=list, max_length=20)
    language: Lang
    consulted_at: date
    verified_at: date | None = None
    review_due_at: date
    review_override_reason: Line200 | None = None
    valid_until: date | None = None
    licence: Licence
    allowed_use: list[AllowedUse] = Field(min_length=1)
    rights_evidence_ref: EvidenceRef | None = None
    status: Literal["draft", "pending_review", "verified", "expired", "withdrawn"]
    content_hash: Sha256 | None = None
    owner_reviewer: Handle | None = None
    notes: Note | None = None
    review: Review


class ItemText(_Model):
    title: Line200
    body: Body
    keywords: list[Keyword] = Field(default_factory=list, max_length=20)
    lang_status: Literal["published", "pending_review"]
    verified_at: date
    ai_assisted: bool = False
    review: Review


class Item(_Model):
    item_id: ItemId
    kind: Literal["procedure", "explanation", "faq"]
    rights_class: RightsClass
    country_scope: list[Country] = Field(min_length=1, max_length=10)
    consulate_scope: list[ConsulateCode] = Field(default_factory=list, max_length=20)
    topic_keys: list[TopicKey] = Field(default_factory=list, max_length=10)
    status: Literal["published", "withdrawn"]
    version: Annotated[int, Field(ge=1)]
    review_due_at: date
    review_override_reason: Line200 | None = None
    superseded_by: ItemId | None = None
    citations: list[Citation] = Field(min_length=1, max_length=20)
    texts: dict[Lang, ItemText] = Field(min_length=1)
    notes: Note | None = None


class Fact(_Model):
    fact_id: FactId
    fact_key: FactKey
    scope: Scope
    value: JsonValue
    unit: Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{1,16}$")] | None = None
    valid_from: date
    valid_until: date | None = None
    status: Literal["published", "under_review", "withdrawn"]
    verified_at: date
    review_due_at: date
    review_override_reason: Line200 | None = None
    citations: list[Citation] = Field(min_length=1, max_length=10)
    notes: Note | None = None
    review: Review


class Term(_Model):
    term: TermText
    lang: Literal["nl", "fr", "ar", "en", "ary"]
    canonical_key: CanonicalKey
    kind: Literal["synonym", "transliteration", "plural", "alias", "abbreviation"]


class TermList(_Model):
    review: Review
    terms: list[Term] = Field(default_factory=list, max_length=5000)


class ConsulateAttribute(_Model):
    attribute: Literal["display_name", "physical_city", "address", "contact", "opening_hours"]
    lang: Lang | None = None
    value: JsonValue
    source_id: SourceId
    verified_at: date
    review_due_at: date
    review_override_reason: Line200 | None = None
    status: Literal["pending_review", "verified", "withdrawn"]
    review: Review


class Jurisdiction(_Model):
    municipality_code: Annotated[str, StringConstraints(pattern=r"^GM[0-9]{4}$")]
    source_id: SourceId
    verified_at: date
    status: Literal["pending_review", "verified", "withdrawn"]
    review: Review


class Consulate(_Model):
    code: ConsulateCode
    country: Country
    kind: Literal["consulate_general", "consulate", "embassy"]
    active: bool
    attributes: list[ConsulateAttribute] = Field(default_factory=list, max_length=50)
    jurisdictions: list[Jurisdiction] = Field(default_factory=list, max_length=500)


class Editor(_Model):
    handle: Handle
    roles: list[Literal["author", "reviewer"]] = Field(min_length=1)


class Manifest(_Model):
    format: Literal[1]
    editors: list[Editor] = Field(min_length=1, max_length=50)


class Bundle(_Model):
    manifest: Manifest
    sources: list[Source] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    terms: TermList | None = None
    consulates: list[Consulate] = Field(default_factory=list)

    def content_version(self) -> str:
        """Stable hash of the parsed content: the same content gives the
        same version whatever the file formatting, so a second load of
        unchanged content is a no-op."""
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Reading ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Problem:
    """One reason content is refused. `where` names the file and field;
    the message never repeats the offending text."""

    where: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: [{self.code}] {self.message}"


class ContentRejectedError(Exception):
    def __init__(self, problems: list[Problem]) -> None:
        self.problems = problems
        super().__init__(f"content refused: {len(problems)} problem(s)")


def _problems(where: str, exc: ValidationError) -> list[Problem]:
    return [
        Problem(
            f"{where}: {'.'.join(str(p) for p in err['loc']) or '(root)'}",
            err["type"],
            err["msg"],
        )
        for err in exc.errors(include_input=False, include_url=False)
    ]


def _read(path: Path, problems: list[Problem], where: str) -> bytes | None:
    if path.is_symlink():
        problems.append(Problem(where, "symlink", "symbolic links are not read"))
        return None
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        problems.append(Problem(where, "too_large", f"file exceeds {MAX_FILE_BYTES} bytes"))
        return None
    return path.read_bytes()


def _parse[M: BaseModel](
    model: type[M], path: Path, where: str, problems: list[Problem]
) -> M | None:
    raw = _read(path, problems, where)
    if raw is None:
        return None
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        problems.extend(_problems(where, exc))
        return None


class _SourceList(_Model):
    items: list[Source]


class _FactList(_Model):
    items: list[Fact]


class _ConsulateList(_Model):
    items: list[Consulate]


def _parse_list[M: BaseModel](
    wrapper: type[M], path: Path, where: str, problems: list[Problem]
) -> M | None:
    raw = _read(path, problems, where)
    if raw is None:
        return None
    try:
        return wrapper.model_validate_json(b'{"items":' + raw + b"}")
    except ValidationError as exc:
        found = _problems(where, exc)
        problems.extend(
            Problem(p.where.replace(f"{where}: items.", f"{where}: ", 1), p.code, p.message)
            for p in found
        )
        return None


def read_bundle(root: Path) -> Bundle:
    """Parse a bundle directory, or raise `ContentRejectedError` listing
    every field problem found (not only the first)."""
    problems: list[Problem] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ContentRejectedError([Problem("manifest.json", "missing", "required file not found")])
    manifest = _parse(Manifest, manifest_path, "manifest.json", problems)

    sources = facts = consulates = None
    if (root / "sources.json").is_file():
        sources = _parse_list(_SourceList, root / "sources.json", "sources.json", problems)
    if (root / "facts.json").is_file():
        facts = _parse_list(_FactList, root / "facts.json", "facts.json", problems)
    if (root / "consulates.json").is_file():
        consulates = _parse_list(
            _ConsulateList, root / "consulates.json", "consulates.json", problems
        )
    terms = None
    if (root / "terms.json").is_file():
        terms = _parse(TermList, root / "terms.json", "terms.json", problems)

    items: list[Item] = []
    items_dir = root / "items"
    if items_dir.is_dir():
        for path in sorted(items_dir.iterdir()):
            where = f"items/{path.name}"
            if path.suffix != ".json" or not path.is_file():
                problems.append(Problem(where, "unexpected_file", "only .json files belong here"))
                continue
            item = _parse(Item, path, where, problems)
            if item is None:
                continue
            if item.item_id != path.stem:
                problems.append(Problem(where, "file_name", "file name must equal item_id"))
            items.append(item)

    if problems or manifest is None:
        raise ContentRejectedError(problems)
    return Bundle(
        manifest=manifest,
        sources=sources.items if sources else [],
        items=items,
        facts=facts.items if facts else [],
        terms=terms,
        consulates=consulates.items if consulates else [],
    )


def json_schema() -> dict[str, object]:
    """JSON schema of a whole bundle, for editors' tooling."""
    return Bundle.model_json_schema()


def json_schema_text() -> str:
    """The schema as committed in `knowledge/content.schema.json` (ASCII, LF)."""
    return json.dumps(json_schema(), indent=2, ensure_ascii=True, sort_keys=True) + "\n"


if __name__ == "__main__":
    import sys

    Path(sys.argv[1]).write_bytes(json_schema_text().encode("ascii"))
