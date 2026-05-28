"""Request schemas for the FraudShield prediction API.

The categorical Literal types are derived from
:mod:`src.features.constants` so that the values accepted by the API are
exactly the values the sklearn pipeline saw at training time. This is the
serving half of the no-training-serving-skew guarantee described in
``FRAUDSHIELD_BLUEPRINT.md`` §9.
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.config import get_settings
from src.features.constants import (
    BROWSER_TYPES,
    CARD_TYPES,
    DEVICE_TYPES,
    MERCHANT_CATEGORIES,
    TRANSACTION_TYPES,
)

# Literal types built from the training-time vocabulary. Pydantic v2 accepts
# tuple[str, ...] arguments to Literal, but mypy/IDE completion is happier
# with an explicitly typed alias.
MerchantCategory = Literal[tuple(MERCHANT_CATEGORIES)]  # type: ignore[valid-type]
TransactionTypeLiteral = Literal[tuple(TRANSACTION_TYPES)]  # type: ignore[valid-type]
CardType = Literal[tuple(CARD_TYPES)]  # type: ignore[valid-type]
DeviceType = Literal[tuple(DEVICE_TYPES)]  # type: ignore[valid-type]
BrowserType = Literal[tuple(BROWSER_TYPES)]  # type: ignore[valid-type]


class TransactionRequest(BaseModel):
    """Single fraud-detection transaction.

    Mirrors the feature columns produced by the synthetic data generator
    and consumed by the MLflow-logged sklearn pipeline.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Optional client-supplied id — generated if missing so every response
    # carries a transaction_id we can join on later for prediction logging.
    transaction_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Client-supplied transaction id; auto-generated UUID if omitted.",
    )

    # ---- Time / amount ----
    transaction_amount: float = Field(
        ..., gt=0, description="Transaction amount in account currency."
    )
    transaction_hour: int = Field(..., ge=0, le=23)
    transaction_day_of_week: int = Field(..., ge=0, le=6)
    is_weekend: int = Field(..., ge=0, le=1)

    # ---- Categorical ----
    merchant_category: MerchantCategory
    transaction_type: TransactionTypeLiteral
    card_type: CardType

    # ---- Velocity / history ----
    transaction_count_24h: int = Field(..., ge=0)
    transaction_count_7d: int = Field(..., ge=0)
    avg_transaction_amount_30d: float = Field(..., gt=0)
    amount_to_avg_ratio: float = Field(..., ge=0)
    unique_merchants_7d: int = Field(..., ge=0)
    is_first_transaction_merchant: int = Field(..., ge=0, le=1)

    # ---- Geo / device ----
    distance_from_home_km: float = Field(..., ge=0)
    is_foreign_transaction: int = Field(..., ge=0, le=1)
    is_high_risk_country: int = Field(..., ge=0, le=1)
    device_type: DeviceType
    browser_type: BrowserType
    ip_risk_score: float = Field(..., ge=0, le=1)

    # ---- Account ----
    account_age_days: int = Field(..., ge=0)
    user_age: int = Field(..., ge=18, le=100)
    credit_limit: float = Field(..., gt=0)
    credit_utilization: float = Field(..., ge=0, le=1)
    previous_fraud_flag: int = Field(..., ge=0, le=1)

    # ---- Engineered ----
    log_amount: float
    is_high_velocity: int = Field(..., ge=0, le=1)
    is_new_account: int = Field(..., ge=0, le=1)
    is_late_night: int = Field(..., ge=0, le=1)
    amount_z_score: float

    @field_validator("transaction_id", mode="before")
    @classmethod
    def _default_transaction_id(cls, value: object) -> str:
        """Generate a UUID v4 if the caller passed null/empty for transaction_id."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return str(uuid4())
        return str(value)


class DriftCheckRequest(BaseModel):
    """Optional body for ``POST /v1/monitoring/drift/check``.

    All fields default to ``None`` so callers can ``POST`` an empty body
    and get the configured defaults from :class:`Settings`.
    """

    model_config = ConfigDict(extra="forbid")

    limit: int | None = Field(
        default=None,
        ge=1,
        le=10000,
        description="How many recent prediction logs to score (defaults to DRIFT_LOOKBACK_LIMIT).",
    )
    min_samples: int | None = Field(
        default=None,
        ge=1,
        description="Below this many rows the run is skipped (defaults to DRIFT_MIN_SAMPLES).",
    )
    save_report: bool = Field(
        default=True,
        description="Whether to persist HTML + JSON artifacts and a DB row.",
    )


class BatchPredictionRequest(BaseModel):
    """Batched prediction request — wraps a list of :class:`TransactionRequest`."""

    model_config = ConfigDict(extra="forbid")

    transactions: list[TransactionRequest] = Field(..., min_length=1)

    @field_validator("transactions")
    @classmethod
    def _enforce_batch_cap(
        cls, value: list[TransactionRequest]
    ) -> list[TransactionRequest]:
        """Reject batches larger than ``Settings.MAX_BATCH_SIZE``.

        Raising a ``ValueError`` here causes FastAPI to return 422, which the
        spec calls out explicitly for over-sized batches.
        """
        cap = get_settings().MAX_BATCH_SIZE
        if len(value) > cap:
            raise ValueError(f"batch size {len(value)} exceeds maximum of {cap}")
        return value
