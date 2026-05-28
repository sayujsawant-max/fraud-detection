"""Repository for the ``retraining_runs`` table.

Same contract as :class:`DriftReportRepository`: the only place SQL is
written for the table. Used by the Phase 6 retraining flow (to insert the
``running`` row, then update on completion) and by the
``/v1/retraining`` API endpoints (to list / fetch).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import case, desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DatabaseError
from src.db.models.retraining_run import RetrainingRun

# Valid status values written into ``retraining_runs.status``. Kept here so
# tests and the API layer can import a single source of truth.
STATUS_RUNNING: str = "running"
STATUS_PROMOTED: str = "promoted"
STATUS_REJECTED: str = "rejected"
STATUS_FAILED: str = "failed"


class RetrainingRunRepository:
    """Async CRUD + query helpers for :class:`RetrainingRun` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create_run(
        self,
        trigger_reason: str,
        *,
        started_at: datetime | None = None,
    ) -> RetrainingRun:
        """Insert a new ``running`` retraining run and return the persisted row."""
        run = RetrainingRun(
            trigger_reason=str(trigger_reason),
            status=STATUS_RUNNING,
            promoted=False,
        )
        if started_at is not None:
            run.started_at = started_at

        try:
            self._session.add(run)
            await self._session.commit()
            await self._session.refresh(run)
        except SQLAlchemyError as exc:
            await self._session.rollback()
            logger.exception("create_run failed: {}", exc)
            raise DatabaseError("failed to insert retraining run") from exc
        return run

    async def update_run_success(
        self,
        run_id: uuid.UUID | str,
        *,
        status: str,
        promoted: bool,
        challenger_run_id: str | None = None,
        challenger_model_uri: str | None = None,
        challenger_model_version: str | None = None,
        challenger_pr_auc: float | None = None,
        champion_pr_auc: float | None = None,
        api_reload_status: str | None = None,
        outcome_notes: str | None = None,
        completed_at: datetime | None = None,
    ) -> RetrainingRun:
        """Mark a run as ``promoted`` or ``rejected`` and store its metrics."""
        if status not in (STATUS_PROMOTED, STATUS_REJECTED):
            raise ValueError(
                f"update_run_success expects status in "
                f"{{{STATUS_PROMOTED!r}, {STATUS_REJECTED!r}}}, got {status!r}"
            )

        run = await self._require_run(run_id)
        run.status = status
        run.promoted = bool(promoted)
        run.challenger_run_id = challenger_run_id
        run.challenger_model_uri = challenger_model_uri
        run.challenger_model_version = challenger_model_version
        run.challenger_pr_auc = (
            float(challenger_pr_auc) if challenger_pr_auc is not None else None
        )
        run.champion_pr_auc = (
            float(champion_pr_auc) if champion_pr_auc is not None else None
        )
        run.api_reload_status = api_reload_status
        run.outcome_notes = outcome_notes
        run.completed_at = completed_at or datetime.now(tz=UTC)
        run.error_message = None

        try:
            await self._session.commit()
            await self._session.refresh(run)
        except SQLAlchemyError as exc:
            await self._session.rollback()
            logger.exception("update_run_success failed: {}", exc)
            raise DatabaseError("failed to update retraining run") from exc
        return run

    async def update_run_failure(
        self,
        run_id: uuid.UUID | str,
        *,
        error_message: str,
        completed_at: datetime | None = None,
        outcome_notes: str | None = None,
    ) -> RetrainingRun:
        """Mark a run as ``failed`` and store its error message."""
        run = await self._require_run(run_id)
        run.status = STATUS_FAILED
        run.promoted = False
        run.error_message = str(error_message)
        run.outcome_notes = outcome_notes
        run.completed_at = completed_at or datetime.now(tz=UTC)

        try:
            await self._session.commit()
            await self._session.refresh(run)
        except SQLAlchemyError as exc:
            await self._session.rollback()
            logger.exception("update_run_failure failed: {}", exc)
            raise DatabaseError("failed to update retraining run") from exc
        return run

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_run_by_id(self, run_id: uuid.UUID | str) -> RetrainingRun | None:
        """Return the row with the given UUID, or ``None`` if absent."""
        try:
            uuid_val = (
                run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
            )
        except (ValueError, TypeError):
            return None
        try:
            stmt = select(RetrainingRun).where(RetrainingRun.id == uuid_val)
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.exception("get_run_by_id failed: {}", exc)
            raise DatabaseError("failed to fetch retraining run") from exc

    async def get_latest_run(self) -> RetrainingRun | None:
        """Return the newest retraining run, or ``None`` if the table is empty."""
        try:
            stmt = (
                select(RetrainingRun).order_by(desc(RetrainingRun.started_at)).limit(1)
            )
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.exception("get_latest_run failed: {}", exc)
            raise DatabaseError("failed to fetch latest retraining run") from exc

    async def list_runs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        trigger_reason: str | None = None,
    ) -> tuple[list[RetrainingRun], int]:
        """Return ``(rows, total_matching_filter)`` newest-first."""
        clauses = []
        if status is not None:
            clauses.append(RetrainingRun.status == status)
        if trigger_reason is not None:
            clauses.append(RetrainingRun.trigger_reason == trigger_reason)

        try:
            count_stmt = select(func.count(RetrainingRun.id))
            for clause in clauses:
                count_stmt = count_stmt.where(clause)
            total = int((await self._session.execute(count_stmt)).scalar() or 0)

            stmt = select(RetrainingRun).order_by(desc(RetrainingRun.started_at))
            for clause in clauses:
                stmt = stmt.where(clause)
            stmt = stmt.limit(limit).offset(offset)
            result = await self._session.execute(stmt)
            rows = list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.exception("list_runs failed: {}", exc)
            raise DatabaseError("failed to list retraining runs") from exc

        return rows, total

    async def get_summary_stats(self) -> dict[str, Any]:
        """Aggregate stats for the ``/v1/retraining/stats`` endpoint.

        Returns sensible defaults (zero counts, ``None`` timestamps) when
        the table is empty so the dashboard never sees a NaN.
        """
        try:
            stmt = select(
                func.count(RetrainingRun.id),
                func.coalesce(
                    func.sum(
                        case((RetrainingRun.status == STATUS_PROMOTED, 1), else_=0)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case((RetrainingRun.status == STATUS_REJECTED, 1), else_=0)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(case((RetrainingRun.status == STATUS_FAILED, 1), else_=0)),
                    0,
                ),
                func.max(RetrainingRun.started_at),
            )
            row = (await self._session.execute(stmt)).one()
        except SQLAlchemyError as exc:
            logger.exception("get_summary_stats failed: {}", exc)
            raise DatabaseError("failed to compute retraining summary stats") from exc

        total = int(row[0] or 0)
        promoted = int(row[1] or 0)
        rejected = int(row[2] or 0)
        failed = int(row[3] or 0)
        latest_at = row[4]

        latest_status: str | None = None
        if latest_at is not None:
            latest = await self.get_latest_run()
            if latest is not None:
                latest_status = latest.status

        return {
            "total_runs": total,
            "promoted_runs": promoted,
            "rejected_runs": rejected,
            "failed_runs": failed,
            "latest_run_at": latest_at,
            "latest_status": latest_status,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _require_run(self, run_id: uuid.UUID | str) -> RetrainingRun:
        """Fetch a run by id or raise :class:`DatabaseError`."""
        run = await self.get_run_by_id(run_id)
        if run is None:
            raise DatabaseError(f"retraining_runs row not found: {run_id}")
        return run
