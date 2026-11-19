"""Write packages/contracts/openapi.json from the application.

uv run python -m tests.export_openapi
"""

from __future__ import annotations

import json

import tests.conftest  # noqa: F401 -- sets the test environment before saas_os imports
from tests.test_unit import CONTRACT

from marocassist.app import create_app

CONTRACT.write_text(
    json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(f"wrote {CONTRACT}")
