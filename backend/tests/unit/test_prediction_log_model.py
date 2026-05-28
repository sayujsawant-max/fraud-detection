"""Unit tests for the :class:`PredictionLog` ORM model.

We only test surface contracts here — the model's columns, defaults, and
behaviour against an in-memory SQLite session. Repository-level behaviour
lives in ``test_prediction_log_repository.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.prediction import PredictionLog

REQUIRED_COLUMNS = {
    "id",
    "transaction_id",
    "timestamp",
    "input_features",
    "fraud_probability",
    "predicted_label",
    "model_name",
    "model_version",
    "model_stage",
    "optimal_threshold",
    "latency_ms",
    "created_at",
}


def test_model_declares_all_required_columns() -> None:
    """The ORM definition must expose every contract column."""
    column_names = {col.name for col in inspect(PredictionLog).columns}
    missing = REQUIRED_COLUMNS - column_names
    assert not missing, f"PredictionLog is missing columns: {missing}"


def test_table_name_is_prediction_logs() -> None:
    """The table is named ``prediction_logs`` (used by Alembic migration)."""
    assert PredictionLog.__tablename__ == "prediction_logs"


def test_nullable_columns_match_spec() -> None:
    """``model_stage`` and ``latency_ms`` are the only nullable columns."""
    columns = {col.name: col for col in inspect(PredictionLog).columns}
    assert columns["model_stage"].nullable is True
    assert columns["latency_ms"].nullable is True
    for required in (
        "transaction_id",
        "timestamp",
        "input_features",
        "fraud_probability",
        "predicted_label",
        "model_name",
        "model_version",
        "optimal_threshold",
        "created_at",
    ):
        assert columns[required].nullable is False, f"{required} must be NOT NULL"


@pytest.mark.asyncio
async def test_model_accepts_dict_input_features(db_session: AsyncSession) -> None:
    """``input_features`` accepts a plain dict and round-trips it."""
    payload = {"amount": 99.5, "merchant": "groceries", "flags": [0, 1, 2]}
    log = PredictionLog(
        transaction_id="tx-1",
        input_features=payload,
        fraud_probability=0.42,
        predicted_label=0,
        model_name="fraud-detector",
        model_version="1",
        model_stage="Production",
        optimal_threshold=0.5,
        latency_ms=12.3,
        timestamp=datetime.now(tz=UTC),
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)

    assert isinstance(log.id, uuid.UUID)
    assert log.input_features == payload
    assert log.predicted_label == 0
    assert log.fraud_probability == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_predicted_label_persisted_as_int(db_session: AsyncSession) -> None:
    """``predicted_label`` round-trips as an integer 0/1."""
    log = PredictionLog(
        transaction_id="tx-2",
        input_features={"x": 1},
        fraud_probability=0.91,
        predicted_label=1,
        model_name="fraud-detector",
        model_version="1",
        model_stage="Production",
        optimal_threshold=0.5,
        latency_ms=None,
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)

    assert log.predicted_label == 1
    assert isinstance(log.predicted_label, int)
    assert log.latency_ms is None
