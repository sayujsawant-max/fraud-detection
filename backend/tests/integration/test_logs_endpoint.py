"""Integration tests for the ``/v1/logs`` audit-trail endpoints."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.repositories import PredictionLogRepository


async def _insert_logs(
    sessionmaker: async_sessionmaker, count: int, label_flip: bool = True
) -> list[uuid.UUID]:
    """Helper — populate the table with ``count`` deterministic rows."""
    ids: list[uuid.UUID] = []
    async with sessionmaker() as session:
        repo = PredictionLogRepository(session)
        for i in range(count):
            log = await repo.create_log(
                transaction_id=f"seed-{i}",
                input_features={"transaction_amount": 100.0 + i, "feature_a": i},
                fraud_probability=0.1 + (0.05 * i),
                predicted_label=(i % 2) if label_flip else 0,
                model_name="fraud-detector",
                model_version="1",
                model_stage="Production",
                optimal_threshold=0.5,
                latency_ms=10.0 + i,
            )
            ids.append(log.id)
    return ids


def test_get_logs_returns_200(client: TestClient) -> None:
    """The endpoint must always respond 200 with a list, even on empty table."""
    response = client.get("/v1/logs")
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("logs", "total", "limit", "offset"):
        assert key in body
    assert body["total"] == 0
    assert body["logs"] == []


@pytest.mark.asyncio
async def test_get_logs_respects_limit_and_offset(
    client: TestClient, sqlite_sessionmaker: async_sessionmaker
) -> None:
    """Pagination honours ``limit`` and ``offset`` query parameters."""
    await _insert_logs(sqlite_sessionmaker, count=5)
    response = client.get("/v1/logs", params={"limit": 2, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["logs"]) == 2

    response = client.get("/v1/logs", params={"limit": 2, "offset": 4})
    body = response.json()
    assert len(body["logs"]) == 1


@pytest.mark.asyncio
async def test_get_logs_filters_by_label(
    client: TestClient, sqlite_sessionmaker: async_sessionmaker
) -> None:
    """``label=1`` returns only fraud rows."""
    await _insert_logs(sqlite_sessionmaker, count=6)
    response = client.get("/v1/logs", params={"label": 1})
    body = response.json()
    assert all(log["predicted_label"] == 1 for log in body["logs"])
    assert body["total"] == 3


@pytest.mark.asyncio
async def test_get_logs_summary_returns_expected_keys(
    client: TestClient, sqlite_sessionmaker: async_sessionmaker
) -> None:
    """``/v1/logs/stats/summary`` returns the dashboard contract."""
    await _insert_logs(sqlite_sessionmaker, count=4)
    response = client.get("/v1/logs/stats/summary")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "total_predictions",
        "fraud_predictions",
        "legitimate_predictions",
        "fraud_rate",
        "avg_fraud_probability",
        "avg_latency_ms",
        "latest_prediction_at",
    ):
        assert key in body
    assert body["total_predictions"] == 4


@pytest.mark.asyncio
async def test_get_log_detail_includes_input_features(
    client: TestClient, sqlite_sessionmaker: async_sessionmaker
) -> None:
    """``GET /v1/logs/{id}`` returns the full row with input_features."""
    ids = await _insert_logs(sqlite_sessionmaker, count=1)
    response = client.get(f"/v1/logs/{ids[0]}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(ids[0])
    assert "input_features" in body
    assert body["input_features"]["transaction_amount"] == 100.0
    assert "optimal_threshold" in body


def test_get_log_detail_missing_returns_404(client: TestClient) -> None:
    """An unknown log id returns 404."""
    response = client.get(f"/v1/logs/{uuid.uuid4()}")
    assert response.status_code == 404


def test_get_log_detail_bad_uuid_returns_404(client: TestClient) -> None:
    """A malformed UUID also returns 404 (no row matched)."""
    response = client.get("/v1/logs/not-a-uuid")
    assert response.status_code == 404


def test_get_logs_query_param_validation(client: TestClient) -> None:
    """Out-of-range query params return 422."""
    response = client.get("/v1/logs", params={"limit": 1000})
    assert response.status_code == 422

    response = client.get("/v1/logs", params={"label": 5})
    assert response.status_code == 422
