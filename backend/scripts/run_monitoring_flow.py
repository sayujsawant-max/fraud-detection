"""CLI: run the monitoring flow once and log the result.

Usage::

    python backend/scripts/run_monitoring_flow.py

The script wires the Prefect-decorated ``monitoring_flow`` into asyncio's
event loop and pretty-prints the resulting payload. No Prefect server is
required — running a flow as a normal callable is supported in Prefect 3.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from loguru import logger

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.logging import configure_logging  # noqa: E402
from src.workflows.monitoring_flow import monitoring_flow  # noqa: E402


async def _run() -> int:
    """Run the monitoring flow and return a shell exit code."""
    result = await monitoring_flow()
    logger.info("monitoring flow result: {}", json.dumps(result, default=str, indent=2))
    return 0 if result.get("status") in {"complete", "skipped"} else 1


def main() -> int:
    """Entry point for ``make run-monitoring-flow``."""
    configure_logging()
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
