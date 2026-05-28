"""Integration tests for the audit-logging side-effect of ``/v1/predict``.

These cases assert two things:

1. A successful 200 response actually inserts a row into ``prediction_logs``.
2. A DB-side failure is swallowed — the prediction still returns 200.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.repositories import PredictionLogRepository


def test_predict_returns_200(client: TestClient, sample_transaction: dict) -> None:
    """Smoke test — predict still returns 200 with Phase 4 logging wired in."""
    response = client.post("/v1/predict", json=sample_transaction)
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_predict_writes_row_to_db(
    client: TestClient,
    sample_transaction: dict,
    sqlite_sessionmaker: async_sessionmaker,
) -> None:
    """A 200 response materialises a prediction_logs row with the right payload."""
    response = client.post("/v1/predict", json=sample_transaction)
    assert response.status_code == 200, response.text

    async with sqlite_sessionmaker() as session:
        repo = PredictionLogRepository(session)
        rows, total = await repo.list_logs(limit=10)
    assert total == 1
    row = rows[0]
    assert row.transaction_id == response.json()["transaction_id"]
    # input_features must NOT include transaction_id (that lives in its own column).
    assert "transaction_id" not in row.input_features
    assert (
        row.input_features["transaction_amount"]
        == sample_transaction["transaction_amount"]
    )
    assert row.model_name
    assert row.predicted_label in (0, 1)
    assert row.optimal_threshold == pytest.approx(0.5)


def test_predict_succeeds_even_if_logging_fails(
    client: TestClient, sample_transaction: dict
) -> None:
    """If the DB write blows up, the API still returns the prediction."""
    with patch.object(
        PredictionLogRepository,
        "create_log",
        new=AsyncMock(side_effect=RuntimeError("simulated DB failure")),
    ):
        response = client.post("/v1/predict", json=sample_transaction)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "fraud_probability" in body


@pytest.mark.asyncio
async def test_predict_batch_logs_each_row(
    client: TestClient,
    sample_transaction: dict,
    sqlite_sessionmaker: async_sessionmaker,
) -> None:
    """Every item in a batch produces a separate prediction_logs row."""
    payload = {
        "transactions": [sample_transaction, sample_transaction, sample_transaction]
    }
    response = client.post("/v1/predict/batch", json=payload)
    assert response.status_code == 200, response.text

    async with sqlite_sessionmaker() as session:
        repo = PredictionLogRepository(session)
        _rows, total = await repo.list_logs(limit=10)
    assert total == 3


def test_predict_batch_succeeds_even_if_logging_fails(
    client: TestClient, sample_transaction: dict
) -> None:
    """Logging exceptions never propagate out of ``/v1/predict/batch``."""
    with (
        patch.object(
            PredictionLogRepository,
            "create_many_logs",
            new=AsyncMock(side_effect=RuntimeError("bulk failure")),
        ),
        patch.object(
            PredictionLogRepository,
            "create_log",
            new=AsyncMock(side_effect=RuntimeError("per-row failure")),
        ),
    ):
        response = client.post(
            "/v1/predict/batch",
            json={"transactions": [sample_transaction, sample_transaction]},
        )
    assert response.status_code == 200, response.text
