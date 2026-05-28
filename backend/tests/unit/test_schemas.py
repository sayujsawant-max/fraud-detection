"""Unit tests for the request and response Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.schemas import BatchPredictionRequest, TransactionRequest
from src.core.config import get_settings


def test_valid_transaction_passes(sample_transaction: dict) -> None:
    """A transaction inside every range and using known categoricals validates."""
    parsed = TransactionRequest.model_validate(sample_transaction)
    assert parsed.transaction_amount == sample_transaction["transaction_amount"]
    # transaction_id should be auto-generated.
    assert parsed.transaction_id is not None
    assert len(parsed.transaction_id) > 0


def test_transaction_id_preserved_when_provided(sample_transaction: dict) -> None:
    """A caller-supplied transaction_id must round-trip."""
    payload = dict(sample_transaction, transaction_id="tx-abc-123")
    parsed = TransactionRequest.model_validate(payload)
    assert parsed.transaction_id == "tx-abc-123"


def test_negative_transaction_amount_fails(sample_transaction: dict) -> None:
    """transaction_amount must be > 0."""
    payload = dict(sample_transaction, transaction_amount=-1.0)
    with pytest.raises(ValidationError):
        TransactionRequest.model_validate(payload)


def test_invalid_transaction_hour_fails(sample_transaction: dict) -> None:
    """transaction_hour must be in [0, 23]."""
    payload = dict(sample_transaction, transaction_hour=25)
    with pytest.raises(ValidationError):
        TransactionRequest.model_validate(payload)


def test_invalid_categorical_value_fails(sample_transaction: dict) -> None:
    """An unknown merchant_category must be rejected."""
    payload = dict(sample_transaction, merchant_category="not-a-real-category")
    with pytest.raises(ValidationError):
        TransactionRequest.model_validate(payload)


def test_credit_utilization_out_of_range_fails(sample_transaction: dict) -> None:
    """credit_utilization must be in [0, 1]."""
    payload = dict(sample_transaction, credit_utilization=1.5)
    with pytest.raises(ValidationError):
        TransactionRequest.model_validate(payload)


def test_user_age_below_minimum_fails(sample_transaction: dict) -> None:
    """user_age must be at least 18."""
    payload = dict(sample_transaction, user_age=15)
    with pytest.raises(ValidationError):
        TransactionRequest.model_validate(payload)


def test_extra_fields_rejected(sample_transaction: dict) -> None:
    """``extra='forbid'`` should reject unknown fields."""
    payload = dict(sample_transaction, surprise_field="🚨")
    with pytest.raises(ValidationError):
        TransactionRequest.model_validate(payload)


def test_batch_under_cap_passes(sample_transaction: dict) -> None:
    """A small batch validates without issue."""
    batch = BatchPredictionRequest.model_validate(
        {"transactions": [sample_transaction, sample_transaction]}
    )
    assert len(batch.transactions) == 2


def test_batch_over_cap_fails(sample_transaction: dict) -> None:
    """A batch exceeding ``MAX_BATCH_SIZE`` must fail validation (→ 422)."""
    cap = get_settings().MAX_BATCH_SIZE
    payload = {"transactions": [sample_transaction] * (cap + 1)}
    with pytest.raises(ValidationError):
        BatchPredictionRequest.model_validate(payload)


def test_empty_batch_fails() -> None:
    """An empty transactions list must fail (min_length=1)."""
    with pytest.raises(ValidationError):
        BatchPredictionRequest.model_validate({"transactions": []})
