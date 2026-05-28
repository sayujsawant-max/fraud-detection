"""Phase 6 retraining read-side router.

Mounted under ``/v1/retraining``. The endpoints here only ever READ from
``retraining_runs`` — write paths live in the admin router (which kicks
off the actual flow). Splitting the surfaces is what lets us protect the
write side with an API key while keeping the audit-trail read side open
to the Phase 7 dashboard without exposing a token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session
from src.api.schemas import (
    RetrainingRunDetail,
    RetrainingRunListResponse,
    RetrainingStatsResponse,
)
from src.core.exceptions import DatabaseError
from src.db.models.retraining_run import RetrainingRun
from src.db.repositories import RetrainingRunRepository

router = APIRouter(prefix="/v1/retraining", tags=["retraining"])


def _detail_from_row(row: RetrainingRun) -> RetrainingRunDetail:
    """Project a :class:`RetrainingRun` ORM row to the detail schema."""
    return RetrainingRunDetail(
        id=row.id,
        trigger_reason=row.trigger_reason,
        started_at=row.started_at,
        completed_at=row.completed_at,
        status=row.status,
        challenger_run_id=row.challenger_run_id,
        challenger_model_uri=row.challenger_model_uri,
        challenger_model_version=row.challenger_model_version,
        challenger_pr_auc=row.challenger_pr_auc,
        champion_pr_auc=row.champion_pr_auc,
        promoted=row.promoted,
        api_reload_status=row.api_reload_status,
        outcome_notes=row.outcome_notes,
        error_message=row.error_message,
        created_at=row.created_at,
    )


@router.get(
    "/runs",
    response_model=RetrainingRunListResponse,
)
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    trigger_reason: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> RetrainingRunListResponse:
    """Return paginated, newest-first retraining runs."""
    repo = RetrainingRunRepository(session)
    try:
        rows, total = await repo.list_runs(
            limit=limit,
            offset=offset,
            status=status_filter,
            trigger_reason=trigger_reason,
        )
    except DatabaseError as exc:
        logger.exception("list_runs failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retraining database is unavailable.",
        ) from exc

    return RetrainingRunListResponse(
        runs=[_detail_from_row(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/runs/latest",
    response_model=RetrainingRunDetail,
    responses={404: {"description": "No retraining runs yet"}},
)
async def get_latest_run(
    session: AsyncSession = Depends(get_db_session),
) -> RetrainingRunDetail:
    """Return the most recent retraining run or 404 if none exist yet."""
    repo = RetrainingRunRepository(session)
    try:
        row = await repo.get_latest_run()
    except DatabaseError as exc:
        logger.exception("get_latest_run failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retraining database is unavailable.",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No retraining runs have been recorded yet.",
        )
    return _detail_from_row(row)


@router.get(
    "/stats",
    response_model=RetrainingStatsResponse,
)
async def get_stats(
    session: AsyncSession = Depends(get_db_session),
) -> RetrainingStatsResponse:
    """Aggregate counts over the ``retraining_runs`` table."""
    repo = RetrainingRunRepository(session)
    try:
        stats = await repo.get_summary_stats()
    except DatabaseError as exc:
        logger.exception("get_stats failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retraining database is unavailable.",
        ) from exc
    return RetrainingStatsResponse(**stats)


@router.get(
    "/runs/{run_id}",
    response_model=RetrainingRunDetail,
    responses={404: {"description": "Retraining run not found"}},
)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RetrainingRunDetail:
    """Return one retraining run by UUID."""
    repo = RetrainingRunRepository(session)
    try:
        row = await repo.get_run_by_id(run_id)
    except DatabaseError as exc:
        logger.exception("get_run failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retraining database is unavailable.",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retraining run not found: {run_id}",
        )
    return _detail_from_row(row)
