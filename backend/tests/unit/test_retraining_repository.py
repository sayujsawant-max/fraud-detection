"""Unit tests for :class:`RetrainingRunRepository`.

Runs against the in-memory async SQLite fixture in ``conftest.py`` — no
real Postgres, MLflow, or Prefect needed.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DatabaseError
from src.db.repositories import RetrainingRunRepository
from src.db.repositories.retraining_runs import (
    STATUS_FAILED,
    STATUS_PROMOTED,
    STATUS_REJECTED,
    STATUS_RUNNING,
)


@pytest.mark.asyncio
async def test_create_run_inserts_running_row(db_session: AsyncSession) -> None:
    """``create_run`` returns a row whose status is ``running``."""
    repo = RetrainingRunRepository(db_session)
    row = await repo.create_run("manual")
    assert row.id is not None
    assert row.trigger_reason == "manual"
    assert row.status == STATUS_RUNNING
    assert row.promoted is False
    assert row.started_at is not None


@pytest.mark.asyncio
async def test_update_run_success_promoted(db_session: AsyncSession) -> None:
    """``update_run_success`` flips status to ``promoted`` and stores metrics."""
    repo = RetrainingRunRepository(db_session)
    row = await repo.create_run("drift")
    updated = await repo.update_run_success(
        row.id,
        status=STATUS_PROMOTED,
        promoted=True,
        challenger_run_id="run-abc",
        challenger_model_uri="models:/fraud-detector/2",
        challenger_model_version="2",
        challenger_pr_auc=0.88,
        champion_pr_auc=0.86,
        api_reload_status="reloaded",
        outcome_notes="challenger wins by 0.02",
    )
    assert updated.status == STATUS_PROMOTED
    assert updated.promoted is True
    assert updated.challenger_pr_auc == pytest.approx(0.88)
    assert updated.champion_pr_auc == pytest.approx(0.86)
    assert updated.api_reload_status == "reloaded"
    assert updated.completed_at is not None
    assert updated.error_message is None


@pytest.mark.asyncio
async def test_update_run_success_rejected(db_session: AsyncSession) -> None:
    """``update_run_success`` with status=rejected records the rejection."""
    repo = RetrainingRunRepository(db_session)
    row = await repo.create_run("scheduled")
    updated = await repo.update_run_success(
        row.id,
        status=STATUS_REJECTED,
        promoted=False,
        challenger_pr_auc=0.82,
        champion_pr_auc=0.85,
        outcome_notes="challenger worse than champion",
    )
    assert updated.status == STATUS_REJECTED
    assert updated.promoted is False


@pytest.mark.asyncio
async def test_update_run_success_invalid_status_raises(
    db_session: AsyncSession,
) -> None:
    """Status must be ``promoted`` or ``rejected``."""
    repo = RetrainingRunRepository(db_session)
    row = await repo.create_run("manual")
    with pytest.raises(ValueError):
        await repo.update_run_success(row.id, status="running", promoted=False)


@pytest.mark.asyncio
async def test_update_run_failure_stores_error(db_session: AsyncSession) -> None:
    """``update_run_failure`` writes the error message + completed_at."""
    repo = RetrainingRunRepository(db_session)
    row = await repo.create_run("manual")
    updated = await repo.update_run_failure(row.id, error_message="MLflow timeout")
    assert updated.status == STATUS_FAILED
    assert updated.promoted is False
    assert updated.error_message == "MLflow timeout"
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_update_run_unknown_id_raises(db_session: AsyncSession) -> None:
    """Updating a non-existent UUID raises :class:`DatabaseError`."""
    import uuid

    repo = RetrainingRunRepository(db_session)
    with pytest.raises(DatabaseError):
        await repo.update_run_failure(uuid.uuid4(), error_message="boom")


@pytest.mark.asyncio
async def test_list_runs_filters_by_status(db_session: AsyncSession) -> None:
    """``list_runs(status=...)`` narrows to matching rows only."""
    repo = RetrainingRunRepository(db_session)

    promoted = await repo.create_run("manual")
    await repo.update_run_success(
        promoted.id, status=STATUS_PROMOTED, promoted=True, challenger_pr_auc=0.9
    )
    rejected = await repo.create_run("scheduled")
    await repo.update_run_success(
        rejected.id, status=STATUS_REJECTED, promoted=False, challenger_pr_auc=0.7
    )

    rows, total = await repo.list_runs(status=STATUS_PROMOTED)
    assert total == 1
    assert rows[0].id == promoted.id

    rejected_rows, rej_total = await repo.list_runs(status=STATUS_REJECTED)
    assert rej_total == 1
    assert rejected_rows[0].id == rejected.id


@pytest.mark.asyncio
async def test_list_runs_filters_by_trigger_reason(
    db_session: AsyncSession,
) -> None:
    """``list_runs(trigger_reason=...)`` narrows to matching trigger only."""
    repo = RetrainingRunRepository(db_session)
    await repo.create_run("manual")
    await repo.create_run("drift")
    await repo.create_run("scheduled")

    drift_rows, total = await repo.list_runs(trigger_reason="drift")
    assert total == 1
    assert drift_rows[0].trigger_reason == "drift"


@pytest.mark.asyncio
async def test_get_latest_run_returns_newest(db_session: AsyncSession) -> None:
    """``get_latest_run`` returns the most-recent insert."""
    repo = RetrainingRunRepository(db_session)
    await repo.create_run("manual")
    await repo.create_run("drift")
    latest_inserted = await repo.create_run("scheduled")

    latest = await repo.get_latest_run()
    assert latest is not None
    assert latest.id == latest_inserted.id


@pytest.mark.asyncio
async def test_get_latest_run_returns_none_when_empty(
    db_session: AsyncSession,
) -> None:
    """Empty table → ``None``."""
    repo = RetrainingRunRepository(db_session)
    assert await repo.get_latest_run() is None


@pytest.mark.asyncio
async def test_get_run_by_id_returns_match(db_session: AsyncSession) -> None:
    """Round-trip insert → fetch."""
    repo = RetrainingRunRepository(db_session)
    row = await repo.create_run("manual")
    found = await repo.get_run_by_id(row.id)
    assert found is not None
    assert found.id == row.id


@pytest.mark.asyncio
async def test_get_run_by_id_handles_bad_uuid(db_session: AsyncSession) -> None:
    """A non-UUID-looking string returns ``None`` without raising."""
    repo = RetrainingRunRepository(db_session)
    assert await repo.get_run_by_id("not-a-uuid") is None


@pytest.mark.asyncio
async def test_summary_stats_returns_expected_keys(
    db_session: AsyncSession,
) -> None:
    """Stats payload has the documented keys + correct counts."""
    repo = RetrainingRunRepository(db_session)

    promoted = await repo.create_run("manual")
    await repo.update_run_success(
        promoted.id, status=STATUS_PROMOTED, promoted=True, challenger_pr_auc=0.9
    )
    rejected = await repo.create_run("scheduled")
    await repo.update_run_success(
        rejected.id, status=STATUS_REJECTED, promoted=False, challenger_pr_auc=0.7
    )
    failed = await repo.create_run("drift")
    await repo.update_run_failure(failed.id, error_message="kaboom")

    stats = await repo.get_summary_stats()
    expected = {
        "total_runs",
        "promoted_runs",
        "rejected_runs",
        "failed_runs",
        "latest_run_at",
        "latest_status",
    }
    assert expected.issubset(stats.keys())
    assert stats["total_runs"] == 3
    assert stats["promoted_runs"] == 1
    assert stats["rejected_runs"] == 1
    assert stats["failed_runs"] == 1
    assert stats["latest_run_at"] is not None


@pytest.mark.asyncio
async def test_summary_stats_empty_table(db_session: AsyncSession) -> None:
    """Empty table → zeros, not nulls."""
    repo = RetrainingRunRepository(db_session)
    stats = await repo.get_summary_stats()
    assert stats["total_runs"] == 0
    assert stats["promoted_runs"] == 0
    assert stats["rejected_runs"] == 0
    assert stats["failed_runs"] == 0
    assert stats["latest_run_at"] is None
    assert stats["latest_status"] is None
