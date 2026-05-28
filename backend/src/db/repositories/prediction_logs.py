"""Repository for the ``prediction_logs`` table.

The router layer never writes SQL directly — it goes through this class.
That separation is what keeps the integration test suite from needing a
real Postgres: in tests we bind ``PredictionLogRepository`` to a SQLite
session and the public method surface is identical.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import and_, desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DatabaseError
from src.db.models.prediction import PredictionLog


class PredictionLogRepository:
    """Async CRUD + query helpers for :class:`PredictionLog` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create_log(
        self,
        *,
        transaction_id: str,
        input_features: dict[str, Any],
        fraud_probability: float,
        predicted_label: int,
        model_name: str,
        model_version: str,
        model_stage: str | None,
        optimal_threshold: float,
        latency_ms: float | None,
        timestamp: datetime | None = None,
    ) -> PredictionLog:
        """Insert a single prediction log and return the persisted row."""
        log = PredictionLog(
            transaction_id=transaction_id,
            input_features=input_features,
            fraud_probability=float(fraud_probability),
            predicted_label=int(predicted_label),
            model_name=model_name,
            model_version=str(model_version),
            model_stage=model_stage,
            optimal_threshold=float(optimal_threshold),
            latency_ms=float(latency_ms) if latency_ms is not None else None,
        )
        # Allow the caller to backfill historical rows with an explicit
        # timestamp (used by the seed script). When omitted we let the
        # DB default fire so multi-replica setups stay clock-agnostic.
        if timestamp is not None:
            log.timestamp = timestamp

        try:
            self._session.add(log)
            await self._session.commit()
            await self._session.refresh(log)
        except SQLAlchemyError as exc:
            await self._session.rollback()
            logger.exception("create_log failed: {}", exc)
            raise DatabaseError("failed to insert prediction log") from exc
        return log

    async def create_many_logs(self, records: list[dict[str, Any]]) -> int:
        """Bulk-insert prediction logs and return the count inserted.

        ``records`` is a list of kwargs matching :meth:`create_log`. We use
        ``add_all`` + a single commit so a 100-row batch is one transaction
        instead of 100.
        """
        if not records:
            return 0

        logs: list[PredictionLog] = []
        for record in records:
            timestamp = record.pop("timestamp", None)
            log = PredictionLog(**record)
            if timestamp is not None:
                log.timestamp = timestamp
            logs.append(log)

        try:
            self._session.add_all(logs)
            await self._session.commit()
        except SQLAlchemyError as exc:
            await self._session.rollback()
            logger.exception("create_many_logs failed: {}", exc)
            raise DatabaseError("failed to bulk-insert prediction logs") from exc
        return len(logs)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def list_logs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        label: int | None = None,
        min_prob: float | None = None,
        max_prob: float | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> tuple[list[PredictionLog], int]:
        """Return ``(rows, total_matching_filter)`` for the prediction-log feed.

        The ``total`` is computed with the same filter clauses but no
        limit/offset so the UI can render pagination without an extra
        request from the client.
        """
        clauses = self._build_filter_clauses(
            label=label,
            min_prob=min_prob,
            max_prob=max_prob,
            start_date=start_date,
            end_date=end_date,
        )

        try:
            count_stmt = select(func.count(PredictionLog.id))
            if clauses:
                count_stmt = count_stmt.where(and_(*clauses))
            total = int((await self._session.execute(count_stmt)).scalar() or 0)

            stmt = select(PredictionLog).order_by(desc(PredictionLog.timestamp))
            if clauses:
                stmt = stmt.where(and_(*clauses))
            stmt = stmt.limit(limit).offset(offset)
            result = await self._session.execute(stmt)
            rows = list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.exception("list_logs failed: {}", exc)
            raise DatabaseError("failed to list prediction logs") from exc

        return rows, total

    async def get_log_by_id(self, log_id: uuid.UUID | str) -> PredictionLog | None:
        """Return one log by id, or ``None`` if it does not exist."""
        try:
            identifier = (
                log_id if isinstance(log_id, uuid.UUID) else uuid.UUID(str(log_id))
            )
        except (ValueError, AttributeError):
            return None

        try:
            stmt = select(PredictionLog).where(PredictionLog.id == identifier)
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.exception("get_log_by_id failed: {}", exc)
            raise DatabaseError("failed to fetch prediction log") from exc

    async def get_summary_stats(self) -> dict[str, Any]:
        """Aggregate stats used by ``/v1/logs/stats/summary``.

        Returns zeroes when the table is empty rather than raising — keeps
        the dashboard render path predictable on a fresh database.
        """
        try:
            stmt = select(
                func.count(PredictionLog.id),
                func.coalesce(func.sum(PredictionLog.predicted_label), 0),
                func.coalesce(func.avg(PredictionLog.fraud_probability), 0.0),
                func.coalesce(func.avg(PredictionLog.latency_ms), 0.0),
                func.max(PredictionLog.timestamp),
            )
            row = (await self._session.execute(stmt)).one()
        except SQLAlchemyError as exc:
            logger.exception("get_summary_stats failed: {}", exc)
            raise DatabaseError("failed to compute summary stats") from exc

        total = int(row[0] or 0)
        fraud = int(row[1] or 0)
        avg_prob = float(row[2] or 0.0)
        avg_latency = float(row[3] or 0.0)
        latest = row[4]

        return {
            "total_predictions": total,
            "fraud_predictions": fraud,
            "legitimate_predictions": max(total - fraud, 0),
            "fraud_rate": (fraud / total) if total else 0.0,
            "avg_fraud_probability": avg_prob,
            "avg_latency_ms": avg_latency,
            "latest_prediction_at": latest,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filter_clauses(
        *,
        label: int | None,
        min_prob: float | None,
        max_prob: float | None,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> list[Any]:
        """Translate query-params into a list of SQLAlchemy filter clauses."""
        clauses: list[Any] = []
        if label is not None:
            clauses.append(PredictionLog.predicted_label == int(label))
        if min_prob is not None:
            clauses.append(PredictionLog.fraud_probability >= float(min_prob))
        if max_prob is not None:
            clauses.append(PredictionLog.fraud_probability <= float(max_prob))
        if start_date is not None:
            clauses.append(PredictionLog.timestamp >= start_date)
        if end_date is not None:
            clauses.append(PredictionLog.timestamp <= end_date)
        return clauses
