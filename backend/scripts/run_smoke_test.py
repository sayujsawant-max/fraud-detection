"""End-to-end smoke test for the FraudShield API.

Pings the seven endpoints the dashboard depends on and reports a green
or red summary. Exits non-zero if any *critical* check fails so it's
safe to wire into ``make smoke-full`` + CI.

Usage::

    python backend/scripts/run_smoke_test.py
    python backend/scripts/run_smoke_test.py --base-url http://localhost:8001  # Docker
    python backend/scripts/run_smoke_test.py --base-url http://localhost:8000  # make dev
    python backend/scripts/run_smoke_test.py --strict

Strict mode treats every check as critical; otherwise the metrics + logs
checks are advisory (they fail gracefully when no traffic has been
recorded yet).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.logging import configure_logging  # noqa: E402

DEFAULT_BASE_URL = "http://localhost:8001"
SAMPLE_PAYLOAD_PATH = _BACKEND_ROOT / "scripts" / "sample_transaction.json"


@dataclass
class CheckResult:
    """Outcome of a single endpoint probe."""

    name: str
    ok: bool
    status_code: int | None
    detail: str
    critical: bool

    @property
    def label(self) -> str:
        return "PASS" if self.ok else "FAIL"


def _check(
    name: str,
    fn: Callable[[], httpx.Response],
    *,
    critical: bool = True,
    expected_status: tuple[int, ...] = (200,),
) -> CheckResult:
    """Wrap an httpx call in a uniform result type that never raises."""
    try:
        response = fn()
    except httpx.HTTPError as exc:
        return CheckResult(
            name=name, ok=False, status_code=None, detail=str(exc), critical=critical
        )
    ok = response.status_code in expected_status
    detail = response.text[:200] if not ok else f"{response.status_code} OK"
    return CheckResult(
        name=name,
        ok=ok,
        status_code=response.status_code,
        detail=detail,
        critical=critical,
    )


def _load_sample_payload() -> dict[str, Any]:
    """Read the shared sample transaction JSON."""
    return json.loads(SAMPLE_PAYLOAD_PATH.read_text(encoding="utf-8"))


def run_smoke_checks(base_url: str, *, strict: bool = False) -> list[CheckResult]:
    """Execute every smoke check and return the result list."""
    base = base_url.rstrip("/")
    payload = _load_sample_payload()

    with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        checks: list[CheckResult] = []

        checks.append(_check("GET /", lambda: client.get(f"{base}/")))
        checks.append(_check("GET /health", lambda: client.get(f"{base}/health")))
        # /ready may return 503 when the model isn't loaded — still "alive"
        # from a smoke-test point of view.
        checks.append(
            _check(
                "GET /ready",
                lambda: client.get(f"{base}/ready"),
                expected_status=(200, 503),
            )
        )
        checks.append(
            _check(
                "GET /v1/model/info",
                lambda: client.get(f"{base}/v1/model/info"),
                expected_status=(200, 503),
            )
        )
        checks.append(
            _check(
                "POST /v1/predict",
                lambda: client.post(f"{base}/v1/predict", json=payload),
                expected_status=(200, 503),
            )
        )
        checks.append(
            _check(
                "GET /v1/logs/stats/summary",
                lambda: client.get(f"{base}/v1/logs/stats/summary"),
                # Advisory unless --strict — fresh installs return 200 with zero counts,
                # but a DB-down 503 isn't a hard fail for the smoke test.
                critical=strict,
                expected_status=(200, 503),
            )
        )
        checks.append(
            _check(
                "GET /metrics",
                lambda: client.get(f"{base}/metrics"),
                expected_status=(200,),
            )
        )

    return checks


def _summarise(results: list[CheckResult]) -> int:
    """Pretty-print the results and return an exit code (0/1)."""
    width = max(len(r.name) for r in results) + 2
    logger.info("=" * (width + 30))
    logger.info("FraudShield smoke-test results")
    logger.info("=" * (width + 30))

    failures_critical = 0
    failures_advisory = 0
    for r in results:
        label = r.label
        status = r.status_code if r.status_code is not None else "—"
        marker = "•" if r.critical else "○"
        line = f"  {marker} {r.name:<{width}} {label:>4}  HTTP {status}"
        if r.ok:
            logger.info(line)
        elif r.critical:
            failures_critical += 1
            logger.error(line + f"  {r.detail}")
        else:
            failures_advisory += 1
            logger.warning(line + f"  {r.detail}")

    logger.info("=" * (width + 30))
    if failures_critical:
        logger.error(
            "smoke test failed | critical={} advisory={}",
            failures_critical,
            failures_advisory,
        )
        return 1
    if failures_advisory:
        logger.warning(
            "smoke test passed with advisory warnings | advisory={}",
            failures_advisory,
        )
    else:
        logger.info("smoke test passed — all critical + advisory checks green")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"FraudShield API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat advisory checks as critical too.",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point used by ``make smoke-full``."""
    configure_logging()
    args = _parse_args()
    logger.info("running smoke test against {}", args.base_url)
    results = run_smoke_checks(args.base_url, strict=args.strict)
    return _summarise(results)


if __name__ == "__main__":
    raise SystemExit(main())
