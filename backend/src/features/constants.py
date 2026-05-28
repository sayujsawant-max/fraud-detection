"""Canonical feature lists and metadata for the FraudShield dataset.

This module is the single source of truth for column names, dtypes, and
categorical values used by the synthetic data generator, the sklearn
preprocessing pipeline, the validators, and (later) the FastAPI Pydantic
schemas. Keeping them here prevents drift between training and serving.
"""

from __future__ import annotations

from typing import Final

TARGET_COLUMN: Final[str] = "is_fraud"

NUMERIC_FEATURES: Final[list[str]] = [
    "transaction_amount",
    "transaction_hour",
    "transaction_day_of_week",
    "is_weekend",
    "transaction_count_24h",
    "transaction_count_7d",
    "avg_transaction_amount_30d",
    "amount_to_avg_ratio",
    "unique_merchants_7d",
    "is_first_transaction_merchant",
    "distance_from_home_km",
    "is_foreign_transaction",
    "is_high_risk_country",
    "ip_risk_score",
    "account_age_days",
    "user_age",
    "credit_limit",
    "credit_utilization",
    "previous_fraud_flag",
    "log_amount",
    "is_high_velocity",
    "is_new_account",
    "is_late_night",
    "amount_z_score",
]

CATEGORICAL_FEATURES: Final[list[str]] = [
    "merchant_category",
    "transaction_type",
    "card_type",
    "device_type",
    "browser_type",
]

FEATURE_COLUMNS: Final[list[str]] = NUMERIC_FEATURES + CATEGORICAL_FEATURES

ALL_COLUMNS: Final[list[str]] = FEATURE_COLUMNS + [TARGET_COLUMN]

MERCHANT_CATEGORIES: Final[list[str]] = [
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

TRANSACTION_TYPES: Final[list[str]] = [
    "purchase",
    "withdrawal",
    "transfer",
    "refund",
    "subscription",
]

CARD_TYPES: Final[list[str]] = ["visa", "mastercard", "amex", "discover"]

DEVICE_TYPES: Final[list[str]] = ["mobile", "desktop", "tablet", "pos_terminal"]

BROWSER_TYPES: Final[list[str]] = [
    "chrome",
    "safari",
    "firefox",
    "edge",
    "other",
    "native_app",
]

DEFAULT_DATASET_SIZE: Final[int] = 120_000
DEFAULT_TEST_SIZE: Final[float] = 0.20
DEFAULT_REFERENCE_ROWS: Final[int] = 5_000
DEFAULT_FRAUD_RATE_TARGET: Final[tuple[float, float]] = (0.04, 0.05)
