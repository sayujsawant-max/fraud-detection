"""Drift-detection API endpoints (Phase 5).

The router orchestrates the three monitoring building blocks:

* :mod:`src.monitoring.data_loader` — reference + current DataFrames.
* :mod:`src.monitoring.drift`        — Evidently runner + result type.
* :mod:`src.monitoring.reports`      — filesystem artifact storage.

All database writes go through :class:`DriftReportRepository` so the same
flow is testable on SQLite and reusable from the Phase 6 Prefect schedule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session
from src.api.schemas import (
    DriftCheckRequest,
    DriftCheckResponse,
    DriftReportDetail,
    DriftReportListResponse,
    DriftReportSummary,
    MonitoringStatsResponse,
)
from src.core.config import get_settings
from src.core.exceptions import (
    DatabaseError,
    DriftDataError,
    DriftError,
)
from src.core.metrics import record_drift_check
from src.db.models.drift_report import DriftReport
from src.db.repositories import DriftReportRepository
from src.monitoring import (
    DriftDetectionResult,
    DriftDetector,
    DriftReportStore,
    build_current_dataset,
    generate_report_id,
    load_prediction_log_rows,
    load_reference_dataset,
    run_drift_detection,
)

router = APIRouter(prefix="/v1/monitoring", tags=["monitoring"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _html_url_for(report_id: str) -> str:
    """Return the URL clients should fetch to download the HTML artifact."""
    return f"/v1/monitoring/drift-reports/{report_id}/html"


def _summary_from_row(row: DriftReport) -> DriftReportSummary:
    """Project a :class:`DriftReport` ORM row to the summary schema."""
    return DriftReportSummary(
        id=row.id,
        report_id=row.report_id,
        generated_at=row.generated_at,
        status=row.status,
        drift_detected=row.drift_detected,
        drift_score=row.drift_score,
        num_drifted_features=row.num_drifted_features,
        total_features=row.total_features,
        num_samples=row.num_samples,
        report_html_url=_html_url_for(row.report_id) if row.report_html_path else None,
    )


def _detail_from_row(row: DriftReport) -> DriftReportDetail:
    """Project a :class:`DriftReport` ORM row to the detail schema."""
    return DriftReportDetail(
        id=row.id,
        report_id=row.report_id,
        generated_at=row.generated_at,
        status=row.status,
        drift_detected=row.drift_detected,
        drift_score=row.drift_score,
        num_drifted_features=row.num_drifted_features,
        total_features=row.total_features,
        num_samples=row.num_samples,
        report_html_url=_html_url_for(row.report_id) if row.report_html_path else None,
        reference_dataset_path=row.reference_dataset_path,
        current_window_start=row.current_window_start,
        current_window_end=row.current_window_end,
        report_html_path=row.report_html_path,
        report_json_path=row.report_json_path,
        report_json=row.report_json,
        triggered_retrain=row.triggered_retrain,
        reason=row.reason,
        created_at=row.created_at,
    )


async def _persist_report(
    session: AsyncSession,
    result: DriftDetectionResult,
    *,
    reference_path: str,
) -> DriftReport:
    """Insert one drift_reports row capturing the run."""
    repo = DriftReportRepository(session)
    return await repo.create_report(
        report_id=result.report_id or generate_report_id(),
        drift_detected=result.drift_detected,
        num_samples=result.num_samples,
        status=result.status,
        drift_score=result.drift_score,
        num_drifted_features=result.num_drifted_features,
        total_features=result.total_features,
        reference_dataset_path=reference_path,
        current_window_start=result.current_window_start,
        current_window_end=result.current_window_end,
        report_html_path=result.report_html_path,
        report_json_path=result.report_json_path,
        report_json=result.report_json,
        reason=result.reason,
        generated_at=result.generated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/drift/check",
    response_model=DriftCheckResponse,
    responses={
        422: {"description": "Reference data unavailable or malformed"},
        500: {"description": "Evidently failed to compute drift"},
    },
)
async def drift_check(
    request: Request,
    payload: DriftCheckRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> DriftCheckResponse:
    """Run an on-demand drift check against the recent prediction window.

    Returns ``status="skipped"`` (still HTTP 200) when there are fewer
    than ``DRIFT_MIN_SAMPLES`` rows in ``prediction_logs`` — that's the
    "we don't have enough data yet" signal rather than a server error.
    """
    settings = get_settings()
    body = payload or DriftCheckRequest()
    limit = body.limit or settings.DRIFT_LOOKBACK_LIMIT
    min_samples = body.min_samples or settings.DRIFT_MIN_SAMPLES

    # ---- Reference data ----
    try:
        reference_df = load_reference_dataset(settings)
    except DriftDataError as exc:
        logger.warning("drift check could not load reference data: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # ---- Current window ----
    rows = await load_prediction_log_rows(session, limit=limit)
    if len(rows) < min_samples:
        logger.info(
            "drift check skipped — {} rows < min_samples={}", len(rows), min_samples
        )
        record_drift_check(status="skipped", drift_score=None, drift_detected=False)
        return DriftCheckResponse(
            status="skipped",
            drift_detected=False,
            num_samples=len(rows),
            reason="insufficient_prediction_logs",
            generated_at=datetime.now(tz=UTC),
        )

    current_df = build_current_dataset(
        rows, reference_columns=list(reference_df.columns)
    )

    # ---- Run Evidently ----
    try:
        result, snapshot = run_drift_detection(
            reference_df, current_df, settings=settings
        )
    except DriftError as exc:
        logger.exception("Evidently drift run failed: {}", exc)
        record_drift_check(status="failed", drift_score=None, drift_detected=False)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Drift detection failed — see server logs.",
        ) from exc

    # Stamp the window from the rows we actually scored (newest first).
    result.current_window_end = rows[0].timestamp if rows else None
    result.current_window_start = rows[-1].timestamp if rows else None

    # ---- Persist artifacts + DB row ----
    if body.save_report:
        store = DriftReportStore(settings)
        report_id = generate_report_id(result.generated_at)
        html_path, json_path = store.paths_for(report_id)
        try:
            DriftDetector(settings).save_artifacts(snapshot, html_path, json_path)
        except DriftError as exc:
            logger.exception("failed to save drift artifacts: {}", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Drift detection succeeded but report storage failed.",
            ) from exc

        result.report_id = report_id
        result.report_html_path = str(html_path)
        result.report_json_path = str(json_path)

        try:
            await _persist_report(
                session,
                result,
                reference_path=settings.REFERENCE_DATA_PATH,
            )
        except DatabaseError as exc:
            # Best-effort: artifacts on disk are still there; just log.
            logger.error("drift report DB write failed: {}", exc)

    record_drift_check(
        status=result.status,
        drift_score=result.drift_score,
        drift_detected=bool(result.drift_detected),
    )

    return DriftCheckResponse(
        status=result.status,
        drift_detected=result.drift_detected,
        drift_score=result.drift_score,
        num_drifted_features=result.num_drifted_features,
        total_features=result.total_features,
        num_samples=result.num_samples,
        report_id=result.report_id,
        report_html_url=_html_url_for(result.report_id) if result.report_id else None,
        reason=result.reason,
        generated_at=result.generated_at,
    )


@router.get(
    "/drift-reports",
    response_model=DriftReportListResponse,
)
async def list_drift_reports(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    drift_detected: bool | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> DriftReportListResponse:
    """Return paginated, newest-first drift reports."""
    repo = DriftReportRepository(session)
    try:
        rows, total = await repo.list_reports(
            limit=limit, offset=offset, drift_detected=drift_detected
        )
    except DatabaseError as exc:
        logger.exception("list_drift_reports failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Drift report database is unavailable.",
        ) from exc

    return DriftReportListResponse(
        reports=[_summary_from_row(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/drift-reports/latest",
    response_model=DriftReportDetail,
    responses={404: {"description": "No drift reports yet"}},
)
async def latest_drift_report(
    session: AsyncSession = Depends(get_db_session),
) -> DriftReportDetail:
    """Return the most recent drift report or 404 if none exist yet."""
    repo = DriftReportRepository(session)
    try:
        row = await repo.get_latest_report()
    except DatabaseError as exc:
        logger.exception("latest_drift_report failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Drift report database is unavailable.",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No drift reports have been generated yet.",
        )
    return _detail_from_row(row)


@router.get(
    "/stats",
    response_model=MonitoringStatsResponse,
)
async def monitoring_stats(
    session: AsyncSession = Depends(get_db_session),
) -> MonitoringStatsResponse:
    """Aggregate counts/averages over the drift_reports table."""
    repo = DriftReportRepository(session)
    try:
        stats = await repo.get_summary_stats()
    except DatabaseError as exc:
        logger.exception("monitoring_stats failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Drift report database is unavailable.",
        ) from exc
    return MonitoringStatsResponse(**stats)


@router.get(
    "/drift-reports/{report_id}",
    response_model=DriftReportDetail,
    responses={404: {"description": "Drift report not found"}},
)
async def get_drift_report(
    report_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> DriftReportDetail:
    """Return one drift report by its filename-safe ``report_id``."""
    repo = DriftReportRepository(session)
    try:
        row = await repo.get_report_by_id(report_id)
    except DatabaseError as exc:
        logger.exception("get_drift_report failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Drift report database is unavailable.",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drift report not found: {report_id}",
        )
    return _detail_from_row(row)


@router.get(
    "/drift-reports/{report_id}/html",
    response_class=FileResponse,
    responses={
        200: {"content": {"text/html": {}}},
        404: {"description": "Drift report HTML missing"},
    },
)
async def get_drift_report_html(
    report_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    """Stream the Evidently HTML artifact back to the client.

    We consult the database first so a 404 here means "we have no record
    of this report id" vs "the file is gone but the DB still references
    it" — the operator-facing message tells the two apart.
    """
    repo = DriftReportRepository(session)
    try:
        row = await repo.get_report_by_id(report_id)
    except DatabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Drift report database is unavailable.",
        ) from exc

    if row is None or not row.report_html_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drift report not found: {report_id}",
        )

    html_path = Path(row.report_html_path)
    if not html_path.exists():
        logger.warning(
            "drift report HTML missing on disk | report_id={} path={}",
            report_id,
            html_path,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Drift report HTML artifact is missing from disk.",
        )
    return FileResponse(
        path=html_path,
        media_type="text/html",
        filename=f"{report_id}.html",
    )
