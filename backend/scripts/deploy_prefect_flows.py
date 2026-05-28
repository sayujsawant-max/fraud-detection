"""CLI: register Prefect deployments for the monitoring + retraining flows.

Usage::

    python backend/scripts/deploy_prefect_flows.py

The script blocks in :func:`prefect.serve` so it should be run in its own
terminal (or as the entrypoint of a Docker service). It schedules:

* ``fraud-monitoring`` on ``PREFECT_MONITORING_CRON`` (default ``0 */6 * * *``).
* ``fraud-retraining`` on ``PREFECT_RETRAINING_CRON`` (default ``0 2 * * 0``).

Stop with Ctrl+C.

The flows can also be inspected/manually triggered through the Prefect UI
at http://localhost:4200 once the deployments are registered.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.config import get_settings  # noqa: E402
from src.core.logging import configure_logging  # noqa: E402
from src.workflows.deployment import serve_all_flows  # noqa: E402


def main() -> int:
    """Entry point for ``make deploy-prefect-flows``."""
    configure_logging()
    settings = get_settings()
    logger.info(
        "deploying Prefect flows | api_url={} monitoring_cron={} retraining_cron={}",
        settings.PREFECT_API_URL,
        settings.PREFECT_MONITORING_CRON,
        settings.PREFECT_RETRAINING_CRON,
    )
    serve_all_flows(settings=settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
