"""Publish the fixture knowledge bundle into the local development database
for the browser end-to-end check (e2e/knowledge.e2e.mjs).

    uv run python -m tests.publish_e2e_fixtures

Development stack only: fixture content, never real content. The copy
differs from the fixture in one way: the Rotterdam visit item has a review
date in the past, so the end-to-end check can see the "not recently
verified" notice. The editorial audit row goes to a dedicated local
"e2e-editor" workspace.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import tests.conftest  # noqa: F401 -- sets the test environment before saas_os imports
from saas_os.core.identity import get_or_create_user_for_external_identity
from saas_os.infra.db import build_engine, build_session_factory, get_migrations_database_config

from marocassist.accounts.provisioning import ensure_personal_workspace
from marocassist.knowledge.loader import check, publish

VALID = Path(__file__).parent / "fixtures" / "knowledge" / "valid"
EXPIRED_ITEM = "fixture.consulate-visit"
PAST_REVIEW_DATE = "2026-11-15"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "bundle"
        shutil.copytree(VALID, root)
        path = root / "items" / f"{EXPIRED_ITEM}.json"
        item = json.loads(path.read_text(encoding="utf-8"))
        item["review_due_at"] = PAST_REVIEW_DATE
        path.write_bytes(json.dumps(item, ensure_ascii=False, indent=2).encode("utf-8"))
        bundle = check(root)
    editor = get_or_create_user_for_external_identity("http://zitadel.localhost:8081", "e2e-editor")
    tenant_id, _created = ensure_personal_workspace(editor.id)
    engine = build_engine(get_migrations_database_config())
    try:
        result = publish(bundle, tenant_id=tenant_id, session_factory=build_session_factory(engine))
    finally:
        engine.dispose()
    print(f"{'published' if result.changed else 'unchanged'}: {bundle.content_version()}")


if __name__ == "__main__":
    main()
