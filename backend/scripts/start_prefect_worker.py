"""CLI: start a Prefect 3 worker against the FraudShield work pool.

The simpler ``deploy_prefect_flows.py`` script uses ``flow.serve()`` which
embeds the worker into the same process — that's the recommended option
for local Docker Compose and what the Phase 6 acceptance criteria assume.

This script is provided for setups that prefer the work-pool / worker
pattern. It creates the work pool if it does not yet exist and starts a
``process`` worker against it. Use either deploy_prefect_flows.py OR
start_prefect_worker.py — not both — to avoid duplicate flow runs.

Usage::

    python backend/scripts/start_prefect_worker.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from loguru import logger

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.config import get_settings  # noqa: E402
from src.core.logging import configure_logging  # noqa: E402


def main() -> int:
    """Entry point for ``make start-prefect-worker``."""
    configure_logging()
    settings = get_settings()
    pool = settings.PREFECT_WORK_POOL or "fraudshield-pool"

    logger.info("ensuring work pool {!r} exists", pool)
    subprocess.run(
        ["prefect", "work-pool", "create", "--type", "process", pool],
        check=False,
    )

    logger.info("starting Prefect worker for pool {!r}", pool)
    completed = subprocess.run(
        ["prefect", "worker", "start", "--pool", pool],
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
