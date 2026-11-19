"""MarocAssist background jobs.

Phase 1 registers no product job yet; the worker still runs every SaaS-OS
platform job (outbox, notification email, session cleanup, audit digests).
A product job is added with `saas_os.infra.jobs.register_tenant_job`, a
`marocassist_` name prefix and an idempotent handler that takes the tenant
from the validated job context only.

Importing this module may resolve `REDIS_URL`; import it from the worker
entrypoint only.
"""

from __future__ import annotations

from typing import Any

JOB_FUNCTIONS: list[Any] = []
