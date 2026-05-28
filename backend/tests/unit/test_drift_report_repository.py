"""Unit tests for :class:`DriftReportRepository`.

Run against the in-memory async SQLite fixture in ``conftest.py`` — no
real Postgres needed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories import DriftReportRepository


def _record_kwargs(
    *,
    report_id: str = "drift_test_001",
    drift_detected: bool = False,
    drift_score: float | None = 0.10,
    status: str = "complete",
    num_samples: int = 500,
) -> dict:
    return {
        "report_id": report_id,
        "drift_detected": drift_detected,
        "drift_score": drift_score,
        "num_drifted_features": 3,
        "total_features": 28,
        "num_samples": num_samples,
        "status": status,
        "reference_dataset_path": "backend/data/reference/reference.parquet",
    }


@pytest.mark.asyncio
async def test_create_report_inserts(db_session: AsyncSession) -> None:
    """``create_report`` persists a row and returns it with id set."""
    repo = DriftReportRepository(db_session)
    row = await repo.create_report(**_record_kwargs())
    assert row.id is not None
    assert row.report_id == "drift_test_001"
    assert row.drift_detected is False
    assert row.status == "complete"


@pytest.mark.asyncio
async def test_list_reports_returns_newest_first(db_session: AsyncSession) -> None:
    """``list_reports`` orders by generated_at descending."""
    repo = DriftReportRepository(db_session)
    base = datetime.now(tz=UTC)
    for i in range(3):
        row = await repo.create_report(
            **_record_kwargs(report_id=f"drift_{i}", drift_detected=(i == 2)),
            generated_at=base - timedelta(minutes=i),
        )
        assert row is not None

    rows, total = await repo.list_reports(limit=10)
    assert total == 3
    # Newest (smallest minutes offset) comes first.
    assert rows[0].report_id == "drift_0"


@pytest.mark.asyncio
async def test_list_reports_filters_by_drift_detected(
    db_session: AsyncSession,
) -> None:
    """``drift_detected`` filter narrows to flagged-only reports."""
    repo = DriftReportRepository(db_session)
    await repo.create_report(**_record_kwargs(report_id="d0", drift_detected=False))
    await repo.create_report(**_record_kwargs(report_id="d1", drift_detected=True))

    flagged, total_flagged = await repo.list_reports(drift_detected=True)
    assert total_flagged == 1
    assert flagged[0].report_id == "d1"


@pytest.mark.asyncio
async def test_get_latest_report_returns_newest(db_session: AsyncSession) -> None:
    """``get_latest_report`` returns the newest row when the table is non-empty."""
    repo = DriftReportRepository(db_session)
    base = datetime.now(tz=UTC)
    for i in range(3):
        await repo.create_report(
            **_record_kwargs(report_id=f"latest_{i}"),
            generated_at=base - timedelta(minutes=i),
        )

    latest = await repo.get_latest_report()
    assert latest is not None
    assert latest.report_id == "latest_0"


@pytest.mark.asyncio
async def test_get_latest_report_returns_none_when_empty(
    db_session: AsyncSession,
) -> None:
    """Empty table → ``None``, not a crash."""
    repo = DriftReportRepository(db_session)
    assert await repo.get_latest_report() is None


@pytest.mark.asyncio
async def test_get_report_by_id_returns_match(db_session: AsyncSession) -> None:
    """``get_report_by_id`` matches by ``report_id`` (the filename-safe id)."""
    repo = DriftReportRepository(db_session)
    await repo.create_report(**_record_kwargs(report_id="findme"))
    found = await repo.get_report_by_id("findme")
    assert found is not None
    assert found.report_id == "findme"


@pytest.mark.asyncio
async def test_get_report_by_id_returns_none_when_missing(
    db_session: AsyncSession,
) -> None:
    """Unknown id returns ``None``."""
    repo = DriftReportRepository(db_session)
    assert await repo.get_report_by_id("nope") is None


@pytest.mark.asyncio
async def test_summary_stats_returns_expected_keys(db_session: AsyncSession) -> None:
    """``get_summary_stats`` returns the dashboard contract dict."""
    repo = DriftReportRepository(db_session)
    await repo.create_report(
        **_record_kwargs(report_id="a", drift_detected=False, drift_score=0.10)
    )
    await repo.create_report(
        **_record_kwargs(report_id="b", drift_detected=True, drift_score=0.40)
    )

    stats = await repo.get_summary_stats()
    expected = {
        "total_reports",
        "drift_events",
        "avg_drift_score",
        "last_check_at",
        "latest_drift_score",
        "latest_drift_detected",
    }
    assert expected.issubset(stats.keys())
    assert stats["total_reports"] == 2
    assert stats["drift_events"] == 1
    assert stats["avg_drift_score"] == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_summary_stats_empty_table(db_session: AsyncSession) -> None:
    """An empty table returns zeroes, not NaN."""
    repo = DriftReportRepository(db_session)
    stats = await repo.get_summary_stats()
    assert stats["total_reports"] == 0
    assert stats["drift_events"] == 0
    assert stats["avg_drift_score"] == 0.0
    assert stats["last_check_at"] is None
