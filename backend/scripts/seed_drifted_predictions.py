"""Seed prediction_logs with intentionally-shifted feature distributions.

Used to demo the drift detection pipeline end-to-end without waiting for
real production traffic to drift. The shifted rows lean hard on the
features the synthetic generator already correlates with fraud:

* higher transaction_amount
* more foreign / high-risk-country transactions
* higher ip_risk_score
* more late-night transactions
* longer distance_from_home_km

Run from project root:

.. code-block:: bash

   python backend/scripts/seed_drifted_predictions.py --n 500
"""

from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from loguru import logger  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.db.models.prediction import PredictionLog  # noqa: E402

DEFAULT_RECORD_COUNT = 500

MERCHANT_CATEGORIES_DRIFTED = [
    # Shift the categorical mix toward higher-risk merchant categories.
    "crypto_exchange",
    "gambling",
    "luxury_goods",
    "online_retail",
    "electronics",
]
TRANSACTION_TYPES = ["purchase", "withdrawal", "transfer"]
CARD_TYPES = ["visa", "mastercard", "amex", "discover"]
DEVICE_TYPES = ["mobile", "desktop"]
BROWSER_TYPES = ["chrome", "safari", "firefox", "other"]


def _drifted_features(rng: random.Random) -> dict[str, object]:
    """Build one feature payload whose distribution diverges from reference.

    Numeric shifts roughly 2–5x the reference mean. Categorical shifts
    concentrate the mass on the high-risk vocabulary. Both shapes are
    chosen to push ``share_of_drifted_columns`` past the default 0.30
    threshold reliably.
    """
    amount = round(rng.uniform(800.0, 5000.0), 2)  # was ~100 baseline
    avg_30d = round(rng.uniform(50.0, 200.0), 2)
    ratio = round(amount / avg_30d, 3)
    return {
        "transaction_amount": amount,
        "transaction_hour": rng.choice([0, 1, 2, 3, 22, 23]),  # late-night skew
        "transaction_day_of_week": rng.randint(0, 6),
        "is_weekend": rng.choice([0, 1]),
        "merchant_category": rng.choice(MERCHANT_CATEGORIES_DRIFTED),
        "transaction_type": rng.choice(TRANSACTION_TYPES),
        "card_type": rng.choice(CARD_TYPES),
        "transaction_count_24h": rng.randint(8, 25),  # high velocity skew
        "transaction_count_7d": rng.randint(30, 120),
        "avg_transaction_amount_30d": avg_30d,
        "amount_to_avg_ratio": ratio,
        "unique_merchants_7d": rng.randint(10, 40),
        "is_first_transaction_merchant": rng.choice([0, 1]),
        "distance_from_home_km": round(rng.uniform(300.0, 3000.0), 2),
        "is_foreign_transaction": 1,  # always foreign
        "is_high_risk_country": rng.choice([1, 1, 0]),  # mostly high-risk
        "device_type": rng.choice(DEVICE_TYPES),
        "browser_type": rng.choice(BROWSER_TYPES),
        "ip_risk_score": round(rng.uniform(0.6, 1.0), 3),  # was ~0.3 baseline
        "account_age_days": rng.randint(1, 90),  # young accounts
        "user_age": rng.randint(18, 30),  # younger users
        "credit_limit": round(rng.uniform(500.0, 5000.0), 2),
        "credit_utilization": round(rng.uniform(0.7, 1.0), 3),
        "previous_fraud_flag": rng.choice([0, 1, 1]),
        "log_amount": round(rng.uniform(6.5, 8.5), 3),
        "is_high_velocity": 1,
        "is_new_account": 1,
        "is_late_night": 1,
        "amount_z_score": round(rng.uniform(2.0, 5.0), 3),
    }


def seed(count: int = DEFAULT_RECORD_COUNT, seed_value: int = 1337) -> int:
    """Insert ``count`` drifted rows and return how many landed."""
    settings = get_settings()
    rng = random.Random(seed_value)
    threshold = settings.DEFAULT_THRESHOLD

    engine = create_engine(settings.database_url_sync, future=True)
    inserted = 0
    base_ts = datetime.now(tz=UTC)
    try:
        with Session(engine) as session:
            rows = []
            for i in range(count):
                # Drifted rows are far more likely to score above threshold —
                # boost the simulated probability so the predicted_label
                # distribution drifts too.
                probability = round(rng.uniform(0.45, 0.97), 4)
                rows.append(
                    PredictionLog(
                        id=uuid.uuid4(),
                        transaction_id=f"drift-tx-{i:04d}",
                        timestamp=base_ts - timedelta(minutes=i),
                        input_features=_drifted_features(rng),
                        fraud_probability=probability,
                        predicted_label=1 if probability >= threshold else 0,
                        model_name="fraud-detector",
                        model_version="1",
                        model_stage="Production",
                        optimal_threshold=threshold,
                        latency_ms=round(rng.uniform(5.0, 25.0), 2),
                    )
                )
            session.add_all(rows)
            session.commit()
            inserted = len(rows)
            logger.info("inserted {} drifted prediction logs", inserted)
    finally:
        engine.dispose()
    return inserted


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n", type=int, default=DEFAULT_RECORD_COUNT, help="row count"
    )
    parser.add_argument(
        "--seed", type=int, default=1337, help="RNG seed for reproducibility"
    )
    args = parser.parse_args(argv)
    seed(count=args.n, seed_value=args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
