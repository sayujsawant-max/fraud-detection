"""Integration tests for the ``/v1/retraining/*`` read-side endpoints.

Uses the SQLite-backed ``client`` fixture from ``conftest.py``. We seed
rows through the repository so the same code paths exercised in unit
tests also drive the endpoint tests.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.repositories import RetrainingRunRepository
from src.db.repositories.retraining_runs import (
    STATUS_PROMOTED,
    STATUS_REJECTED,
)


async def _seed_runs(sessionmaker: async_sessionmaker) -> dict:
    """Insert one row per terminal status; return the inserted run UUIDs."""
    async with sessionmaker() as session:
        repo = RetrainingRunRepository(session)
        promoted = await repo.create_run("manual")
        await repo.update_run_success(
            promoted.id,
            status=STATUS_PROMOTED,
            promoted=True,
            challenger_pr_auc=0.9,
            champion_pr_auc=0.85,
        )
        rejected = await repo.create_run("scheduled")
        await repo.update_run_success(
            rejected.id,
            status=STATUS_REJECTED,
            promoted=False,
            challenger_pr_auc=0.75,
            champion_pr_auc=0.80,
        )
        failed = await repo.create_run("drift")
        await repo.update_run_failure(failed.id, error_message="boom")
        return {
            "promoted": str(promoted.id),
            "rejected": str(rejected.id),
            "failed": str(failed.id),
        }


# ---------------------------------------------------------------------------
# /v1/retraining/runs
# ---------------------------------------------------------------------------


def test_list_runs_returns_200_and_pagination(
    client: TestClient,
    sqlite_sessionmaker: async_sessionmaker,
) -> None:
    """``GET /v1/retraining/runs`` returns paginated payload."""
    import asyncio

    asyncio.run(_seed_runs(sqlite_sessionmaker))

    response = client.get("/v1/retraining/runs?limit=10&offset=0")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    assert len(payload["runs"]) == 3


def test_list_runs_filters_by_status(
    client: TestClient,
    sqlite_sessionmaker: async_sessionmaker,
) -> None:
    """``status=promoted`` narrows to one row."""
    import asyncio

    asyncio.run(_seed_runs(sqlite_sessionmaker))

    response = client.get("/v1/retraining/runs?status=promoted")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["runs"][0]["status"] == "promoted"


def test_list_runs_empty_returns_200(client: TestClient) -> None:
    """Empty table → 200 with total=0."""
    response = client.get("/v1/retraining/runs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["runs"] == []


# ---------------------------------------------------------------------------
# /v1/retraining/runs/latest
# ---------------------------------------------------------------------------


def test_latest_returns_404_when_empty(client: TestClient) -> None:
    """No runs yet → 404."""
    response = client.get("/v1/retraining/runs/latest")
    assert response.status_code == 404


def test_latest_returns_newest_run(
    client: TestClient,
    sqlite_sessionmaker: async_sessionmaker,
) -> None:
    """``runs/latest`` returns the most recently inserted row."""
    import asyncio

    asyncio.run(_seed_runs(sqlite_sessionmaker))

    response = client.get("/v1/retraining/runs/latest")
    assert response.status_code == 200
    payload = response.json()
    # ``drift`` row was inserted last in the seed helper.
    assert payload["trigger_reason"] == "drift"
    assert payload["status"] == "failed"


# ---------------------------------------------------------------------------
# /v1/retraining/runs/{run_id}
# ---------------------------------------------------------------------------


def test_get_run_by_id_returns_200(
    client: TestClient,
    sqlite_sessionmaker: async_sessionmaker,
) -> None:
    """Known UUID → 200 with the row payload."""
    import asyncio

    seeded = asyncio.run(_seed_runs(sqlite_sessionmaker))
    promoted_id = seeded["promoted"]

    response = client.get(f"/v1/retraining/runs/{promoted_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == promoted_id
    assert payload["status"] == "promoted"


def test_get_run_by_id_returns_404_for_unknown(client: TestClient) -> None:
    """Unknown UUID → 404."""
    import uuid

    response = client.get(f"/v1/retraining/runs/{uuid.uuid4()}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /v1/retraining/stats
# ---------------------------------------------------------------------------


def test_stats_returns_expected_keys(
    client: TestClient,
    sqlite_sessionmaker: async_sessionmaker,
) -> None:
    """Stats payload has the documented keys + non-zero counts after seeding."""
    import asyncio

    asyncio.run(_seed_runs(sqlite_sessionmaker))

    response = client.get("/v1/retraining/stats")
    assert response.status_code == 200
    payload = response.json()
    for key in (
        "total_runs",
        "promoted_runs",
        "rejected_runs",
        "failed_runs",
        "latest_run_at",
        "latest_status",
    ):
        assert key in payload
    assert payload["total_runs"] == 3
    assert payload["promoted_runs"] == 1
    assert payload["rejected_runs"] == 1
    assert payload["failed_runs"] == 1


def test_stats_empty_returns_zeros(client: TestClient) -> None:
    """Empty table → all counts zero, no error."""
    response = client.get("/v1/retraining/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_runs"] == 0
    assert payload["promoted_runs"] == 0
    assert payload["rejected_runs"] == 0
    assert payload["failed_runs"] == 0
    assert payload["latest_run_at"] is None
    assert payload["latest_status"] is None
