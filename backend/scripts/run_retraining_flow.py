"""CLI: run the retraining flow once.

Usage::

    python backend/scripts/run_retraining_flow.py --trigger manual

The ``--trigger`` value is validated against ``ALLOWED_TRIGGERS`` inside
the flow itself, so passing an unsupported value surfaces a friendly
``RetrainingError`` rather than a SQL-level failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from loguru import logger

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.logging import configure_logging  # noqa: E402
from src.workflows.retraining_flow import (  # noqa: E402
    ALLOWED_TRIGGERS,
    retraining_flow,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the FraudShield retraining flow once",
    )
    parser.add_argument(
        "--trigger",
        choices=list(ALLOWED_TRIGGERS),
        default="manual",
        help="Why this retraining run was kicked off (default: manual).",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Skip the API hot-reload step after promotion.",
    )
    return parser.parse_args()


async def _run(trigger: str, perform_reload: bool) -> int:
    """Run the retraining flow and return a shell exit code."""
    result = await retraining_flow(
        trigger_reason=trigger, perform_reload=perform_reload
    )
    logger.info("retraining flow result: {}", json.dumps(result, default=str, indent=2))
    return 0 if result.get("status") in {"promoted", "rejected"} else 1


def main() -> int:
    """Entry point for ``make run-retraining-flow``."""
    configure_logging()
    args = _parse_args()
    return asyncio.run(_run(args.trigger, not args.no_reload))


if __name__ == "__main__":
    raise SystemExit(main())
