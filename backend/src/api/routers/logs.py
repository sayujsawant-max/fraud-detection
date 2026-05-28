"""Prediction-log audit-trail endpoints (Phase 4).

``GET /v1/logs``                  — paginated, filterable list of predictions
``GET /v1/logs/{log_id}``         — full detail incl. ``input_features``
``GET /v1/logs/stats/summary``    — aggregate counts and averages

The router is intentionally thin: every database query lives in
:class:`PredictionLogRepository` so the same logic can be exercised from
the Phase 5 drift-detection flow without going through HTTP.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session
from src.api.schemas import (
    PredictionLogDetail,
    PredictionLogListResponse,
    PredictionLogStatsResponse,
    PredictionLogSummary,
)
from src.core.exceptions import DatabaseError
from src.db.models.prediction import PredictionLog
from src.db.repositories import PredictionLogRepository

router = APIRouter(prefix="/v1/logs", tags=["logs"])


def _summary_from_row(row: PredictionLog) -> PredictionLogSummary:
    """Project a :class:`PredictionLog` ORM row to the list-response shape."""
    return PredictionLogSummary(
        id=row.id,
        transaction_id=row.transaction_id,
        timestamp=row.timestamp,
        fraud_probability=row.fraud_probability,
        predicted_label=row.predicted_label,
        is_fraud=bool(row.predicted_label),
        model_name=row.model_name,
        model_version=row.model_version,
        model_stage=row.model_stage,
        latency_ms=row.latency_ms,
    )


def _detail_from_row(row: PredictionLog) -> PredictionLogDetail:
    """Project a :class:`PredictionLog` row to the detail response."""
    return PredictionLogDetail(
        id=row.id,
        transaction_id=row.transaction_id,
        timestamp=row.timestamp,
        fraud_probability=row.fraud_probability,
        predicted_label=row.predicted_label,
        is_fraud=bool(row.predicted_label),
        model_name=row.model_name,
        model_version=row.model_version,
        model_stage=row.model_stage,
        latency_ms=row.latency_ms,
        input_features=row.input_features or {},
        optimal_threshold=row.optimal_threshold,
        created_at=row.created_at,
    )


@router.get(
    "",
    response_model=PredictionLogListResponse,
    responses={503: {"description": "Database unavailable"}},
)
async def list_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    label: int | None = Query(
        None, ge=0, le=1, description="Filter by predicted_label"
    ),
    min_prob: float | None = Query(None, ge=0.0, le=1.0),
    max_prob: float | None = Query(None, ge=0.0, le=1.0),
    start_date: datetime | None = Query(
        None, description="Inclusive lower bound (ISO 8601)"
    ),
    end_date: datetime | None = Query(
        None, description="Inclusive upper bound (ISO 8601)"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> PredictionLogListResponse:
    """Return a paginated, filtered list of prediction logs."""
    repo = PredictionLogRepository(session)
    try:
        rows, total = await repo.list_logs(
            limit=limit,
            offset=offset,
            label=label,
            min_prob=min_prob,
            max_prob=max_prob,
            start_date=start_date,
            end_date=end_date,
        )
    except DatabaseError as exc:
        logger.exception("list_logs failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction log database is unavailable.",
        ) from exc

    return PredictionLogListResponse(
        logs=[_summary_from_row(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stats/summary",
    response_model=PredictionLogStatsResponse,
    responses={503: {"description": "Database unavailable"}},
)
async def logs_summary(
    session: AsyncSession = Depends(get_db_session),
) -> PredictionLogStatsResponse:
    """Aggregate counts/averages over the entire prediction-log table."""
    repo = PredictionLogRepository(session)
    try:
        stats = await repo.get_summary_stats()
    except DatabaseError as exc:
        logger.exception("logs_summary failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction log database is unavailable.",
        ) from exc

    return PredictionLogStatsResponse(**stats)


@router.get(
    "/{log_id}",
    response_model=PredictionLogDetail,
    responses={
        404: {"description": "Prediction log not found"},
        503: {"description": "Database unavailable"},
    },
)
async def get_log(
    log_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> PredictionLogDetail:
    """Return one prediction log with its full ``input_features`` payload."""
    repo = PredictionLogRepository(session)
    try:
        row = await repo.get_log_by_id(log_id)
    except DatabaseError as exc:
        logger.exception("get_log failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction log database is unavailable.",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prediction log not found: {log_id}",
        )
    return _detail_from_row(row)
