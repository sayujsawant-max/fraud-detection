"""Repository for the ``drift_reports`` table.

The router layer never writes SQL directly — it goes through this class
so the SQLite-backed integration tests are bit-for-bit identical to the
production Postgres path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DatabaseError
from src.db.models.drift_report import DriftReport


class DriftReportRepository:
    """Async CRUD + query helpers for :class:`DriftReport` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create_report(
        self,
        *,
        report_id: str,
        drift_detected: bool,
        num_samples: int,
        status: str = "complete",
        drift_score: float | None = None,
        num_drifted_features: int | None = None,
        total_features: int | None = None,
        reference_dataset_path: str | None = None,
        current_window_start: datetime | None = None,
        current_window_end: datetime | None = None,
        report_html_path: str | None = None,
        report_json_path: str | None = None,
        report_json: dict[str, Any] | None = None,
        reason: str | None = None,
        generated_at: datetime | None = None,
        triggered_retrain: bool = False,
    ) -> DriftReport:
        """Insert a single drift report and return the persisted row."""
        report = DriftReport(
            report_id=report_id,
            drift_detected=bool(drift_detected),
            num_samples=int(num_samples),
            status=status,
            drift_score=float(drift_score) if drift_score is not None else None,
            num_drifted_features=num_drifted_features,
            total_features=total_features,
            reference_dataset_path=reference_dataset_path,
            current_window_start=current_window_start,
            current_window_end=current_window_end,
            report_html_path=report_html_path,
            report_json_path=report_json_path,
            report_json=report_json,
            reason=reason,
            triggered_retrain=bool(triggered_retrain),
        )
        if generated_at is not None:
            report.generated_at = generated_at

        try:
            self._session.add(report)
            await self._session.commit()
            await self._session.refresh(report)
        except SQLAlchemyError as exc:
            await self._session.rollback()
            logger.exception("create_report failed: {}", exc)
            raise DatabaseError("failed to insert drift report") from exc
        return report

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def list_reports(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
        drift_detected: bool | None = None,
    ) -> tuple[list[DriftReport], int]:
        """Return ``(rows, total_matching_filter)`` newest-first."""
        clauses = []
        if drift_detected is not None:
            clauses.append(DriftReport.drift_detected == bool(drift_detected))

        try:
            count_stmt = select(func.count(DriftReport.id))
            for clause in clauses:
                count_stmt = count_stmt.where(clause)
            total = int((await self._session.execute(count_stmt)).scalar() or 0)

            stmt = select(DriftReport).order_by(desc(DriftReport.generated_at))
            for clause in clauses:
                stmt = stmt.where(clause)
            stmt = stmt.limit(limit).offset(offset)
            result = await self._session.execute(stmt)
            rows = list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.exception("list_reports failed: {}", exc)
            raise DatabaseError("failed to list drift reports") from exc

        return rows, total

    async def get_report_by_id(self, report_id: str) -> DriftReport | None:
        """Return the row whose ``report_id`` matches, or ``None``."""
        try:
            stmt = select(DriftReport).where(DriftReport.report_id == report_id)
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.exception("get_report_by_id failed: {}", exc)
            raise DatabaseError("failed to fetch drift report") from exc

    async def get_latest_report(self) -> DriftReport | None:
        """Return the newest drift report, or ``None`` if the table is empty."""
        try:
            stmt = select(DriftReport).order_by(desc(DriftReport.generated_at)).limit(1)
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.exception("get_latest_report failed: {}", exc)
            raise DatabaseError("failed to fetch latest drift report") from exc

    async def get_summary_stats(self) -> dict[str, Any]:
        """Aggregate stats for ``/v1/monitoring/stats``.

        Returns sensible defaults (zero counts, ``None`` timestamps) when
        the table is empty so the dashboard never sees a NaN.
        """
        try:
            stmt = select(
                func.count(DriftReport.id),
                func.coalesce(
                    func.sum(
                        # COUNT(*) FILTER (WHERE drift_detected) isn't
                        # portable to SQLite. Use a CASE expression instead.
                        func.coalesce(DriftReport.drift_detected, 0)
                    ),
                    0,
                ),
                func.coalesce(func.avg(DriftReport.drift_score), 0.0),
                func.max(DriftReport.generated_at),
            )
            row = (await self._session.execute(stmt)).one()
        except SQLAlchemyError as exc:
            logger.exception("get_summary_stats failed: {}", exc)
            raise DatabaseError("failed to compute drift summary stats") from exc

        total = int(row[0] or 0)
        events = int(row[1] or 0)
        avg = float(row[2] or 0.0)
        latest = row[3]

        latest_score: float | None = None
        latest_detected: bool | None = None
        if latest is not None:
            latest_report = await self.get_latest_report()
            if latest_report is not None:
                latest_score = latest_report.drift_score
                latest_detected = latest_report.drift_detected

        return {
            "total_reports": total,
            "drift_events": events,
            "avg_drift_score": avg,
            "last_check_at": latest,
            "latest_drift_score": latest_score,
            "latest_drift_detected": latest_detected,
        }
