"""MarocAssist background jobs.

The worker runs every SaaS-OS platform job (outbox, notification email,
session cleanup, audit digests) plus these. A product job is added with
`saas_os.infra.jobs.register_tenant_job` or `register_system_job`, a
`marocassist_` name prefix and an idempotent handler that takes any tenant
from the validated job context or from configuration, never a payload.

- `marocassist_knowledge_review` (Phase 3 WP F): a system job scheduled
  every minute (`system_cron` only offers sub-minute periods). It writes
  the daily editor review report once per UTC day in the editorial tenant
  and is a cheap no-op otherwise, or when no editorial tenant is set.

Importing this module may resolve `REDIS_URL`; import it from the worker
entrypoint only.
"""

from __future__ import annotations

import asyncio
from typing import Any

from saas_os.infra.jobs import SystemJobContext, register_system_job
from saas_os.infra.jobs.queue import system_cron

from marocassist.knowledge.review import run_daily_review

REVIEW_TICK_SECONDS = 60


async def marocassist_knowledge_review(_context: SystemJobContext) -> None:
    await asyncio.to_thread(run_daily_review)


KNOWLEDGE_REVIEW_JOB = register_system_job(marocassist_knowledge_review)

# A scheduled job is passed to the worker as a cron job only, never also as
# a function: arq keys both by name, and SaaS-OS refuses the duplicate.
JOB_FUNCTIONS: list[Any] = []
CRON_JOBS: list[Any] = [system_cron(KNOWLEDGE_REVIEW_JOB, every_seconds=REVIEW_TICK_SECONDS)]
