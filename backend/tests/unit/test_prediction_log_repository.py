"""Unit tests for :class:`PredictionLogRepository`.

All cases run against an in-memory async SQLite engine provided by the
``db_session`` fixture in ``conftest.py``. No real Postgres required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories import PredictionLogRepository


def _record_kwargs(
    *,
    transaction_id: str = "tx-100",
    fraud_probability: float = 0.42,
    predicted_label: int = 0,
    latency_ms: float | None = 12.0,
    model_stage: str | None = "Production",
) -> dict:
    return {
        "transaction_id": transaction_id,
        "input_features": {"amount": 100.0, "category": "groceries"},
        "fraud_probability": fraud_probability,
        "predicted_label": predicted_label,
        "model_name": "fraud-detector",
        "model_version": "1",
        "model_stage": model_stage,
        "optimal_threshold": 0.5,
        "latency_ms": latency_ms,
    }


@pytest.mark.asyncio
async def test_create_log_inserts_record(db_session: AsyncSession) -> None:
    """``create_log`` persists a row and returns it with id/timestamp set."""
    repo = PredictionLogRepository(db_session)
    log = await repo.create_log(**_record_kwargs())
    assert isinstance(log.id, uuid.UUID)
    assert log.transaction_id == "tx-100"
    assert log.timestamp is not None
    assert log.fraud_probability == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_list_logs_returns_inserted_rows(db_session: AsyncSession) -> None:
    """``list_logs`` returns inserted records, newest first."""
    repo = PredictionLogRepository(db_session)
    base = datetime.now(tz=UTC)
    # Manually stagger timestamps so the ordering assertion is meaningful.
    for i in range(3):
        log = await repo.create_log(**_record_kwargs(transaction_id=f"tx-{i}"))
        log.timestamp = base - timedelta(minutes=i)
        await db_session.commit()

    rows, total = await repo.list_logs(limit=10, offset=0)
    assert total == 3
    assert len(rows) == 3
    # Newest first ordering: tx-0 should come before tx-2.
    ordered_ids = [r.transaction_id for r in rows]
    assert ordered_ids[0] == "tx-0"


@pytest.mark.asyncio
async def test_list_logs_filters_by_label(db_session: AsyncSession) -> None:
    """``label`` filter narrows the result set to that class only."""
    repo = PredictionLogRepository(db_session)
    await repo.create_log(**_record_kwargs(transaction_id="legit", predicted_label=0))
    await repo.create_log(**_record_kwargs(transaction_id="fraud", predicted_label=1))

    fraud_rows, fraud_total = await repo.list_logs(label=1)
    assert fraud_total == 1
    assert fraud_rows[0].transaction_id == "fraud"

    legit_rows, legit_total = await repo.list_logs(label=0)
    assert legit_total == 1
    assert legit_rows[0].transaction_id == "legit"


@pytest.mark.asyncio
async def test_list_logs_filters_by_probability(db_session: AsyncSession) -> None:
    """``min_prob`` and ``max_prob`` apply inclusive bounds."""
    repo = PredictionLogRepository(db_session)
    await repo.create_log(
        **_record_kwargs(transaction_id="low", fraud_probability=0.10)
    )
    await repo.create_log(
        **_record_kwargs(transaction_id="mid", fraud_probability=0.50)
    )
    await repo.create_log(
        **_record_kwargs(transaction_id="high", fraud_probability=0.90)
    )

    _rows, total_high = await repo.list_logs(min_prob=0.70)
    assert total_high == 1

    _rows, total_low = await repo.list_logs(max_prob=0.20)
    assert total_low == 1

    _rows, total_mid = await repo.list_logs(min_prob=0.20, max_prob=0.80)
    assert total_mid == 1


@pytest.mark.asyncio
async def test_list_logs_pagination(db_session: AsyncSession) -> None:
    """``limit`` and ``offset`` cap and skip results."""
    repo = PredictionLogRepository(db_session)
    for i in range(5):
        await repo.create_log(**_record_kwargs(transaction_id=f"tx-{i}"))

    rows, total = await repo.list_logs(limit=2, offset=0)
    assert total == 5
    assert len(rows) == 2

    rows, _ = await repo.list_logs(limit=2, offset=4)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_summary_stats_returns_expected_keys(db_session: AsyncSession) -> None:
    """``get_summary_stats`` returns the contract dict shape on a non-empty table."""
    repo = PredictionLogRepository(db_session)
    await repo.create_log(
        **_record_kwargs(transaction_id="a", predicted_label=0, fraud_probability=0.2)
    )
    await repo.create_log(
        **_record_kwargs(transaction_id="b", predicted_label=1, fraud_probability=0.8)
    )

    stats = await repo.get_summary_stats()
    expected_keys = {
        "total_predictions",
        "fraud_predictions",
        "legitimate_predictions",
        "fraud_rate",
        "avg_fraud_probability",
        "avg_latency_ms",
        "latest_prediction_at",
    }
    assert expected_keys.issubset(stats.keys())
    assert stats["total_predictions"] == 2
    assert stats["fraud_predictions"] == 1
    assert stats["legitimate_predictions"] == 1
    assert stats["fraud_rate"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_summary_stats_on_empty_table(db_session: AsyncSession) -> None:
    """An empty table returns zeroes, not a crash."""
    repo = PredictionLogRepository(db_session)
    stats = await repo.get_summary_stats()
    assert stats["total_predictions"] == 0
    assert stats["fraud_rate"] == 0.0
    assert stats["latest_prediction_at"] is None


@pytest.mark.asyncio
async def test_get_log_by_id_returns_record(db_session: AsyncSession) -> None:
    """``get_log_by_id`` fetches the persisted row by primary key."""
    repo = PredictionLogRepository(db_session)
    log = await repo.create_log(**_record_kwargs())
    fetched = await repo.get_log_by_id(log.id)
    assert fetched is not None
    assert fetched.id == log.id


@pytest.mark.asyncio
async def test_get_log_by_id_missing_returns_none(db_session: AsyncSession) -> None:
    """Unknown UUID returns ``None`` rather than raising."""
    repo = PredictionLogRepository(db_session)
    fetched = await repo.get_log_by_id(uuid.uuid4())
    assert fetched is None


@pytest.mark.asyncio
async def test_get_log_by_id_bad_uuid_returns_none(db_session: AsyncSession) -> None:
    """Malformed UUID string returns ``None`` (the 404 path)."""
    repo = PredictionLogRepository(db_session)
    fetched = await repo.get_log_by_id("not-a-uuid")
    assert fetched is None


@pytest.mark.asyncio
async def test_create_many_logs_bulk_inserts(db_session: AsyncSession) -> None:
    """``create_many_logs`` inserts in one transaction and returns the count."""
    repo = PredictionLogRepository(db_session)
    payloads = [_record_kwargs(transaction_id=f"bulk-{i}") for i in range(5)]
    inserted = await repo.create_many_logs(payloads)
    assert inserted == 5

    _rows, total = await repo.list_logs()
    assert total == 5
