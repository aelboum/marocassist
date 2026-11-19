"""Apply every migration this deployment needs, in the one valid order.

    python -m marocassist.migrate

1. SaaS-OS's own history (`alembic_version_saas_os`), through the
   installed package.
2. MarocAssist's history (`alembic_version`); it references `core.*`.
3. MarocAssist's permissions, registered into the shared catalog.

Steps 1-2 use `MIGRATIONS_DATABASE_URL` (privileged migration role), step 3
uses `DATABASE_URL` (restricted application role). Safe to run again.
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from saas_os.infra.db import run_core_migrations

from marocassist.permissions import register_permissions

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def migrate() -> None:
    run_core_migrations()
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    command.upgrade(config, "head")
    register_permissions()


if __name__ == "__main__":
    migrate()
    sys.exit(0)
