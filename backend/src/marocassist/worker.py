"""MarocAssist worker process.

    python -m marocassist.worker            # long-running worker
    python -m marocassist.worker --check    # container health probe

SaaS-OS's production worker with MarocAssist's jobs added: same startup
order, same fail-closed database-role guard, same health probe, every
platform job still running. Run this instead of `python -m
saas_os.api.worker`, never next to it.
"""

from __future__ import annotations

import logging
import sys

from saas_os.api.worker import main
from saas_os.infra.observability import configure_logging, safe_exception_type

logger = logging.getLogger(__name__)


def run(argv: list[str] | None = None) -> int:
    try:
        from marocassist.jobs import CRON_JOBS, JOB_FUNCTIONS  # noqa: PLC0415 -- resolves REDIS_URL
    except Exception as exc:  # noqa: BLE001 -- every startup failure must exit non-zero
        configure_logging()
        logger.error("worker_startup_failed", extra={"error_type": safe_exception_type(exc)})
        return 1
    return int(main(argv, extra_functions=JOB_FUNCTIONS, extra_cron_jobs=CRON_JOBS))


if __name__ == "__main__":
    sys.exit(run())
