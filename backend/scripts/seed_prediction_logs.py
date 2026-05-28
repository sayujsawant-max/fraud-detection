"""Seed the ``prediction_logs`` table with demo records.

Generates ~100 synthetic prediction logs spread across the previous week so
the Phase 5 drift dashboard and the frontend logs page have something to
render before any real traffic arrives.

Run from project root:

.. code-block:: bash

   python backend/scripts/seed_prediction_logs.py
"""

from __future__ import annotations

import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Make ``src.*`` importable when running from project root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from loguru import logger  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.db.models.prediction import PredictionLog  # noqa: E402

DEFAULT_RECORD_COUNT = 100


MERCHANT_CATEGORIES = [
    "groceries",
    "restaurants",
    "gas_station",
    "online_retail",
    "electronics",
    "travel",
    "entertainment",
    "healthcare",
    "utilities",
    "gambling",
    "crypto_exchange",
    "luxury_goods",
]
TRANSACTION_TYPES = ["purchase", "withdrawal", "transfer", "refund", "subscription"]
CARD_TYPES = ["visa", "mastercard", "amex", "discover"]
DEVICE_TYPES = ["mobile", "desktop", "tablet", "pos_terminal"]
BROWSER_TYPES = ["chrome", "safari", "firefox", "edge", "other", "native_app"]


def _random_features(rng: random.Random) -> dict[str, float | int | str]:
    """Build one realistic feature payload matching the API contract."""
    amount = round(rng.uniform(2.0, 1500.0), 2)
    avg_30d = round(rng.uniform(50.0, 300.0), 2)
    ratio = round(amount / avg_30d, 3)
    return {
        "transaction_amount": amount,
        "transaction_hour": rng.randint(0, 23),
        "transaction_day_of_week": rng.randint(0, 6),
        "is_weekend": rng.choice([0, 1]),
        "merchant_category": rng.choice(MERCHANT_CATEGORIES),
        "transaction_type": rng.choice(TRANSACTION_TYPES),
        "card_type": rng.choice(CARD_TYPES),
        "transaction_count_24h": rng.randint(0, 15),
        "transaction_count_7d": rng.randint(0, 60),
        "avg_transaction_amount_30d": avg_30d,
        "amount_to_avg_ratio": ratio,
        "unique_merchants_7d": rng.randint(1, 30),
        "is_first_transaction_merchant": rng.choice([0, 1]),
        "distance_from_home_km": round(rng.uniform(0.0, 500.0), 2),
        "is_foreign_transaction": rng.choice([0, 1]),
        "is_high_risk_country": rng.choice([0, 1]),
        "device_type": rng.choice(DEVICE_TYPES),
        "browser_type": rng.choice(BROWSER_TYPES),
        "ip_risk_score": round(rng.uniform(0.0, 1.0), 3),
        "account_age_days": rng.randint(1, 3650),
        "user_age": rng.randint(18, 90),
        "credit_limit": round(rng.uniform(500.0, 25000.0), 2),
        "credit_utilization": round(rng.uniform(0.0, 1.0), 3),
        "previous_fraud_flag": rng.choice([0, 1]),
        "log_amount": round(rng.uniform(0.5, 7.5), 3),
        "is_high_velocity": rng.choice([0, 1]),
        "is_new_account": rng.choice([0, 1]),
        "is_late_night": rng.choice([0, 1]),
        "amount_z_score": round(rng.uniform(-3.0, 3.0), 3),
    }


def _build_record(
    rng: random.Random,
    *,
    threshold: float,
    base_ts: datetime,
    index: int,
) -> PredictionLog:
    """Construct a single PredictionLog ORM instance with realistic values."""
    fraud_probability = round(rng.betavariate(2, 8), 4)
    predicted_label = 1 if fraud_probability >= threshold else 0
    timestamp = base_ts - timedelta(minutes=index * 15)

    return PredictionLog(
        id=uuid.uuid4(),
        transaction_id=f"seed-tx-{index:04d}",
        timestamp=timestamp,
        input_features=_random_features(rng),
        fraud_probability=fraud_probability,
        predicted_label=predicted_label,
        model_name="fraud-detector",
        model_version="1",
        model_stage="Production",
        optimal_threshold=threshold,
        latency_ms=round(rng.uniform(5.0, 40.0), 2),
        created_at=timestamp,
    )


def seed(count: int = DEFAULT_RECORD_COUNT, seed_value: int = 42) -> int:
    """Insert ``count`` demo records and return how many actually landed.

    Uses the *sync* SQLAlchemy URL from settings so the script does not
    have to spin up an asyncio event loop just to seed a table.
    """
    settings = get_settings()
    rng = random.Random(seed_value)
    threshold = settings.DEFAULT_THRESHOLD

    engine = create_engine(settings.database_url_sync, future=True)
    inserted = 0
    base_ts = datetime.now(tz=UTC)
    try:
        with Session(engine) as session:
            records = [
                _build_record(rng, threshold=threshold, base_ts=base_ts, index=i)
                for i in range(count)
            ]
            session.add_all(records)
            session.commit()
            inserted = len(records)
            logger.info("inserted {} demo prediction logs", inserted)
    finally:
        engine.dispose()
    return inserted


if __name__ == "__main__":
    seed()
