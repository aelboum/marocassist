"""Publishing loader: the only writer of global knowledge (Phase 3 WP B;
security review T-1, T-2, T-3; decision P3-D10).

    python -m marocassist.knowledge.loader --dry-run knowledge/
    python -m marocassist.knowledge.loader knowledge/

Runs at deploy time under the **migrations role** (`MIGRATIONS_DATABASE_URL`),
never inside the running app: the application role has `SELECT` only on
knowledge. Import-linter forbids importing this module from the app, API,
worker and feature modules. It is the second module allowed to import
SQLAlchemy directly (the first being migrations): the knowledge tables use
PostgreSQL text arrays and JSONB, which SaaS-OS's ORM primitives do not
cover. It uses SQLAlchemy Core on reflected tables only, never string-built
SQL.

A publication:

1. reads the bundle and checks it (`content.py`, `validate.py`); any problem
   refuses the whole bundle before the database is touched;
2. takes an installation-wide advisory lock, so two deploys cannot
   interleave;
3. compares the content version (a hash of the parsed content) with the
   latest publication: unchanged content is a no-op, so a load is
   idempotent;
4. otherwise replaces all global knowledge in **one transaction**, with a new
   `knowledge_publications` row, and writes one audit row in the editorial
   tenant (`record_system_action_in_transaction`) in the same transaction.
   Readers see the old or the new content, never a mix.

The audit metadata holds the content version and counts only, never text.
Editorial fields (`review`, `notes`, `owner_reviewer`) are not written.

`--dry-run` performs steps 1 only, needs no database, and is what CI runs.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

import sqlalchemy as sa
from saas_os.core.audit_log import record_system_action_in_transaction
from saas_os.core.authority import SystemActor, SystemActorKind
from saas_os.infra.db import (
    IntegrityError,
    Session,
    acquire_global_advisory_lock,
    build_engine,
    build_session_factory,
    get_migrations_database_config,
    tenant_session_scope,
)
from sqlalchemy.orm import sessionmaker

from marocassist.config import ConfigurationError, editorial_tenant_id
from marocassist.knowledge.chunking import chunk_body
from marocassist.knowledge.content import Bundle, ContentRejectedError, Item, Problem, read_bundle
from marocassist.knowledge.validate import validate_bundle

SCHEMA: Final = "marocassist"
# Parents before children; deleted in reverse.
WRITE_ORDER: Final = (
    "knowledge_sources",
    "knowledge_items",
    "knowledge_item_texts",
    "knowledge_chunks",
    "knowledge_facts",
    "knowledge_citations",
    "knowledge_terms",
    "consulates",
    "consulate_attributes",
    "consulate_jurisdictions",
)
LOCK_NAMESPACE: Final = "marocassist.knowledge"
LOCK_KEY: Final = "publish"
ACTOR: Final = SystemActor(SystemActorKind.MAINTENANCE, "marocassist.knowledge.loader")
AUDIT_ACTION: Final = "marocassist.knowledge.publish"
AUDIT_RESOURCE: Final = "marocassist.knowledge_publication"

Row = dict[str, Any]


class PublishError(Exception):
    """The database refused the publication; nothing was written."""


@dataclass(frozen=True)
class PublishResult:
    content_version: str
    changed: bool
    publication_id: uuid.UUID | None
    counts: dict[str, int]


def check(root: Path, *, today: date | None = None) -> Bundle:
    """Read and check a bundle; raise `ContentRejectedError` with every
    problem. This is the whole dry run."""
    bundle = read_bundle(root)
    problems = validate_bundle(bundle, today=today or date.today())
    if problems:
        raise ContentRejectedError(problems)
    return bundle


def _items_in_insert_order(items: list[Item]) -> list[Item]:
    """Successors before the items they supersede (self-referencing FK)."""
    by_id = {i.item_id: i for i in items}
    ordered: list[Item] = []
    placed: set[str] = set()

    def place(item: Item) -> None:
        if item.item_id in placed:
            return
        placed.add(item.item_id)
        if item.superseded_by is not None:
            place(by_id[item.superseded_by])
        ordered.append(item)

    for item in items:
        place(item)
    return ordered


def build_rows(bundle: Bundle, publication_id: uuid.UUID) -> dict[str, list[Row]]:
    """Database rows per table. Editorial-only fields are left out (T-3)."""
    rows: dict[str, list[Row]] = {name: [] for name in WRITE_ORDER}
    for s in bundle.sources:
        rows["knowledge_sources"].append(
            s.model_dump(exclude={"review", "notes", "owner_reviewer", "review_override_reason"})
        )
    for item in _items_in_insert_order(bundle.items):
        rows["knowledge_items"].append(
            {
                **item.model_dump(
                    include={
                        "item_id",
                        "kind",
                        "rights_class",
                        "country_scope",
                        "consulate_scope",
                        "topic_keys",
                        "status",
                        "version",
                        "review_due_at",
                        "superseded_by",
                    }
                ),
                "publication_id": publication_id,
            }
        )
        for lang, text in item.texts.items():
            rows["knowledge_item_texts"].append(
                {
                    "item_id": item.item_id,
                    "lang": lang,
                    "title": text.title,
                    "body": text.body,
                    "keywords": text.keywords,
                    "lang_status": text.lang_status,
                    "verified_at": text.verified_at,
                }
            )
            rows["knowledge_chunks"].extend(
                {
                    "item_id": item.item_id,
                    "lang": lang,
                    "ordinal": c.ordinal,
                    "heading": c.heading,
                    "body": c.body,
                }
                for c in chunk_body(text.body)
            )
        rows["knowledge_citations"].extend(
            {
                "item_id": item.item_id,
                "fact_id": None,
                "source_id": c.source_id,
                "locator": c.locator,
            }
            for c in item.citations
        )
    for fact in bundle.facts:
        rows["knowledge_facts"].append(
            {
                **fact.model_dump(
                    exclude={"citations", "review", "notes", "review_override_reason"}
                ),
                "publication_id": publication_id,
            }
        )
        rows["knowledge_citations"].extend(
            {
                "item_id": None,
                "fact_id": fact.fact_id,
                "source_id": c.source_id,
                "locator": c.locator,
            }
            for c in fact.citations
        )
    if bundle.terms is not None:
        rows["knowledge_terms"].extend(t.model_dump() for t in bundle.terms.terms)
    for consulate in bundle.consulates:
        rows["consulates"].append(
            consulate.model_dump(include={"code", "country", "kind", "active"})
        )
        rows["consulate_attributes"].extend(
            {
                **a.model_dump(exclude={"review", "lang", "review_override_reason"}),
                "code": consulate.code,
                "lang": a.lang or "und",
            }
            for a in consulate.attributes
        )
        rows["consulate_jurisdictions"].extend(
            {**j.model_dump(exclude={"review"}), "code": consulate.code}
            for j in consulate.jurisdictions
        )
    return rows


def _tables(session: Session) -> dict[str, sa.Table]:
    metadata = sa.MetaData()
    connection = session.connection()
    return {
        name: sa.Table(name, metadata, schema=SCHEMA, autoload_with=connection)
        for name in (*WRITE_ORDER, "knowledge_publications")
    }


@contextmanager
def _migrations_session_factory() -> Iterator[sessionmaker[Session]]:
    engine = build_engine(get_migrations_database_config())
    try:
        yield build_session_factory(engine)
    finally:
        engine.dispose()


def publish(
    bundle: Bundle,
    *,
    tenant_id: uuid.UUID,
    session_factory: sessionmaker[Session] | None = None,
) -> PublishResult:
    """Publish a checked bundle (see the module docstring). `tenant_id` is
    the editorial tenant; `session_factory` must use the migrations role."""
    if session_factory is None:
        with _migrations_session_factory() as factory:
            return publish(bundle, tenant_id=tenant_id, session_factory=factory)

    version = bundle.content_version()
    try:
        with tenant_session_scope(tenant_id, session_factory=session_factory) as session:
            acquire_global_advisory_lock(session, LOCK_NAMESPACE, LOCK_KEY)
            tables = _tables(session)
            publications = tables["knowledge_publications"]
            latest = session.execute(
                sa.select(publications.c.content_version)
                .order_by(publications.c.published_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest == version:
                return PublishResult(version, changed=False, publication_id=None, counts={})

            publication_id = uuid.uuid4()
            rows = build_rows(bundle, publication_id)
            counts = {name: len(table_rows) for name, table_rows in rows.items()}
            session.execute(
                sa.insert(publications).values(
                    publication_id=publication_id,
                    content_version=version,
                    item_count=len(bundle.items),
                    fact_count=len(bundle.facts),
                )
            )
            for name in reversed(WRITE_ORDER):
                session.execute(sa.delete(tables[name]))
            for name in WRITE_ORDER:
                if name == "knowledge_items":
                    # One row at a time: a successor must exist before the
                    # item that points to it.
                    for row in rows[name]:
                        session.execute(sa.insert(tables[name]).values(**row))
                elif rows[name]:
                    session.execute(sa.insert(tables[name]), rows[name])
            record_system_action_in_transaction(
                session,
                tenant_id=tenant_id,
                actor=ACTOR,
                action=AUDIT_ACTION,
                resource_type=AUDIT_RESOURCE,
                resource_id=str(publication_id),
                metadata={"content_version": version, "counts": counts},
            )
    except IntegrityError as exc:
        # The message names the constraint, never row content.
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        raise PublishError(
            f"database refused the publication ({constraint or 'integrity'})"
        ) from exc
    return PublishResult(version, changed=True, publication_id=publication_id, counts=counts)


def _print_problems(problems: list[Problem], out: Callable[[str], object]) -> None:
    for problem in problems:
        out(str(problem))
    out(f"{len(problems)} problem(s); nothing was published.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m marocassist.knowledge.loader")
    parser.add_argument("bundle", type=Path, help="content bundle directory")
    parser.add_argument("--dry-run", action="store_true", help="check only; no database access")
    args = parser.parse_args(argv)

    def out(line: str) -> None:
        sys.stdout.write(line + "\n")

    try:
        bundle = check(args.bundle)
    except ContentRejectedError as exc:
        _print_problems(exc.problems, out)
        return 1
    version = bundle.content_version()
    if args.dry_run:
        out(f"ok: {version} ({len(bundle.items)} items, {len(bundle.facts)} facts); dry run")
        return 0
    try:
        tenant_id = editorial_tenant_id()
    except ConfigurationError as exc:
        out(str(exc))
        return 2
    try:
        result = publish(bundle, tenant_id=tenant_id)
    except PublishError as exc:
        out(str(exc))
        return 1
    if result.changed:
        out(f"published {version} as {result.publication_id}")
    else:
        out(f"unchanged: {version} is already published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
