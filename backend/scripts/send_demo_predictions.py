"""Generate demo prediction traffic against the FraudShield API.

Used to populate the dashboard, the prediction-log table, and the
``fraudshield_*`` Prometheus metrics so Grafana panels have something to
render during an interview demo. The payload mix follows a roughly
realistic ~5% fraud rate.

Usage::

    python backend/scripts/send_demo_predictions.py --n 100
    python backend/scripts/send_demo_predictions.py --base-url http://localhost:8001 --n 500  # Docker
    python backend/scripts/send_demo_predictions.py --base-url http://localhost:8000 --n 500  # make dev

The script never raises on individual request failures; it reports the
pass/fail tally at the end so a flaky network doesn't poison the demo.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
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


def _baseline_payload() -> dict[str, Any]:
    """Load the legit baseline payload as the starting point."""
    return json.loads(SAMPLE_PAYLOAD_PATH.read_text(encoding="utf-8"))


def _make_legit(rng: random.Random) -> dict[str, Any]:
    """Return a low-risk transaction with small per-call jitter."""
    payload = _baseline_payload()
    payload["transaction_amount"] = round(rng.uniform(10, 250), 2)
    payload["amount_to_avg_ratio"] = round(rng.uniform(0.5, 1.3), 2)
    payload["ip_risk_score"] = round(rng.uniform(0.0, 0.2), 3)
    payload["distance_from_home_km"] = round(rng.uniform(0.5, 50.0), 2)
    payload["transaction_hour"] = rng.randint(8, 22)
    return payload


def _make_suspicious(rng: random.Random) -> dict[str, Any]:
    """Mid-risk transaction — moderately anomalous on a few axes."""
    payload = _baseline_payload()
    payload["transaction_amount"] = round(rng.uniform(500, 1500), 2)
    payload["amount_to_avg_ratio"] = round(rng.uniform(4.0, 9.0), 2)
    payload["ip_risk_score"] = round(rng.uniform(0.4, 0.7), 3)
    payload["is_high_velocity"] = 1
    payload["is_late_night"] = 1
    payload["distance_from_home_km"] = round(rng.uniform(100, 500), 2)
    payload["transaction_hour"] = rng.choice([2, 3, 23])
    return payload


def _make_fraud(rng: random.Random) -> dict[str, Any]:
    """High-risk transaction — fraud pattern across multiple axes."""
    payload = _baseline_payload()
    payload["transaction_amount"] = round(rng.uniform(1500, 5000), 2)
    payload["amount_to_avg_ratio"] = round(rng.uniform(15, 30), 2)
    payload["ip_risk_score"] = round(rng.uniform(0.85, 1.0), 3)
    payload["is_foreign_transaction"] = 1
    payload["is_high_risk_country"] = 1
    payload["is_high_velocity"] = 1
    payload["is_late_night"] = 1
    payload["is_new_account"] = 1
    payload["previous_fraud_flag"] = 1
    payload["distance_from_home_km"] = round(rng.uniform(2000, 8000), 2)
    payload["transaction_hour"] = rng.choice([1, 2, 3, 4])
    payload["merchant_category"] = rng.choice(["online", "electronics"])
    payload["transaction_type"] = "cash_advance"
    return payload


def _sample_payload(rng: random.Random) -> tuple[str, dict[str, Any]]:
    """Pick a payload kind with realistic class proportions."""
    roll = rng.random()
    if roll < 0.05:
        return "fraud", _make_fraud(rng)
    if roll < 0.20:
        return "suspicious", _make_suspicious(rng)
    return "legit", _make_legit(rng)


def send_traffic(
    base_url: str, count: int, *, delay_seconds: float = 0.0
) -> dict[str, int]:
    """Fire ``count`` /v1/predict requests. Returns success/error tallies."""
    base = base_url.rstrip("/")
    rng = random.Random(42)
    stats = {"sent": 0, "ok": 0, "err": 0, "fraud": 0, "suspicious": 0, "legit": 0}

    with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        for idx in range(count):
            kind, payload = _sample_payload(rng)
            stats["sent"] += 1
            stats[kind] += 1
            try:
                response = client.post(f"{base}/v1/predict", json=payload)
                if response.status_code == 200:
                    stats["ok"] += 1
                else:
                    stats["err"] += 1
                    logger.warning(
                        "non-200 from /v1/predict | idx={} status={} body={}",
                        idx,
                        response.status_code,
                        response.text[:120],
                    )
            except httpx.HTTPError as exc:
                stats["err"] += 1
                logger.warning("HTTP error from /v1/predict | idx={} err={}", idx, exc)

            if delay_seconds > 0:
                time.sleep(delay_seconds)

            # Light progress logging so 500-call runs don't look hung.
            if (idx + 1) % 25 == 0:
                logger.info(
                    "progress | sent={}/{} ok={} err={}",
                    idx + 1,
                    count,
                    stats["ok"],
                    stats["err"],
                )

    return stats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"FraudShield API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=100,
        help="Number of /v1/predict requests to send (default: 100).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Optional inter-request delay in seconds (default: no delay).",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point used by ``make load-test``."""
    configure_logging()
    args = _parse_args()
    logger.info(
        "sending {} demo predictions to {} (delay={}s)",
        args.n,
        args.base_url,
        args.delay,
    )
    stats = send_traffic(args.base_url, args.n, delay_seconds=args.delay)
    logger.info(
        "done | sent={} ok={} err={} legit={} suspicious={} fraud={}",
        stats["sent"],
        stats["ok"],
        stats["err"],
        stats["legit"],
        stats["suspicious"],
        stats["fraud"],
    )
    return 0 if stats["err"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
