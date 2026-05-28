"""Phase 6 monitoring flow — scheduled Evidently drift check.

The flow reuses the Phase 5 monitoring building blocks (the same loader,
the same Evidently runner, the same artifact store) rather than
re-implementing them. That keeps "drift check from the API endpoint" and
"drift check from the Prefect schedule" bit-for-bit identical so we never
debug two parallel implementations.

The flow returns a plain ``dict`` (not a Prefect ``State``) so the test
suite can assert on it without importing Prefect internals.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.core.config import Settings, get_settings
from src.core.exceptions import DriftDataError, DriftError
from src.core.metrics import record_drift_check
from src.db.repositories import DriftReportRepository
from src.db.session import get_sessionmaker
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
from src.workflows.tasks import flow, task

MONITORING_FLOW_NAME: str = "fraud-monitoring"


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@task(name="fetch_recent_predictions")
async def fetch_recent_predictions_task(
    settings: Settings | None = None,
) -> list[Any]:
    """Load the most-recent ``DRIFT_LOOKBACK_LIMIT`` prediction-log rows."""
    settings = settings or get_settings()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = await load_prediction_log_rows(
            session, limit=settings.DRIFT_LOOKBACK_LIMIT
        )
    logger.info("fetched {} prediction log rows", len(rows))
    return rows


@task(name="load_reference_dataset")
def load_reference_dataset_task(settings: Settings | None = None):
    """Load the reference DataFrame using the Phase 5 loader."""
    settings = settings or get_settings()
    return load_reference_dataset(settings)


@task(name="run_drift_detection")
def run_drift_detection_task(
    reference_df,
    current_df,
    *,
    settings: Settings | None = None,
    save_report: bool = True,
) -> DriftDetectionResult:
    """Run Evidently and (optionally) persist the HTML/JSON artifacts."""
    settings = settings or get_settings()
    result, snapshot = run_drift_detection(reference_df, current_df, settings=settings)

    if save_report and snapshot is not None:
        store = DriftReportStore(settings)
        report_id = generate_report_id(result.generated_at)
        html_path, json_path = store.paths_for(report_id)
        try:
            DriftDetector(settings).save_artifacts(snapshot, html_path, json_path)
            result.report_id = report_id
            result.report_html_path = str(html_path)
            result.report_json_path = str(json_path)
        except DriftError as exc:
            logger.error("failed to save drift artifacts inside flow: {}", exc)
    return result


@task(name="persist_drift_report")
async def persist_drift_report_task(
    result: DriftDetectionResult,
    settings: Settings | None = None,
    *,
    triggered_retrain: bool = False,
) -> None:
    """Insert one ``drift_reports`` row capturing the flow result."""
    settings = settings or get_settings()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        repo = DriftReportRepository(session)
        await repo.create_report(
            report_id=result.report_id or generate_report_id(result.generated_at),
            drift_detected=result.drift_detected,
            num_samples=result.num_samples,
            status=result.status,
            drift_score=result.drift_score,
            num_drifted_features=result.num_drifted_features,
            total_features=result.total_features,
            reference_dataset_path=settings.REFERENCE_DATA_PATH,
            current_window_start=result.current_window_start,
            current_window_end=result.current_window_end,
            report_html_path=result.report_html_path,
            report_json_path=result.report_json_path,
            report_json=result.report_json,
            reason=result.reason,
            generated_at=result.generated_at,
            triggered_retrain=triggered_retrain,
        )


@task(name="evaluate_drift")
def evaluate_drift_task(
    result: DriftDetectionResult, settings: Settings | None = None
) -> bool:
    """Return True when the Evidently result crosses the drift threshold."""
    settings = settings or get_settings()
    if result.drift_score is None:
        return False
    threshold = float(settings.DRIFT_THRESHOLD)
    return bool(result.drift_detected) and float(result.drift_score) > threshold


@task(name="trigger_retraining")
async def trigger_retraining_task(
    drift_detected: bool,
    trigger_reason: str = "drift",
) -> dict[str, Any] | None:
    """Call the retraining flow when drift is detected; no-op otherwise."""
    if not drift_detected:
        return None
    # Imported lazily to avoid a circular import between the two flow
    # modules and keep the unit tests for monitoring fast.
    from src.workflows.retraining_flow import retraining_flow

    logger.info("drift detected — kicking off retraining flow")
    return await retraining_flow(trigger_reason=trigger_reason)


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


@flow(name=MONITORING_FLOW_NAME, validate_parameters=False)
async def monitoring_flow(
    settings: Settings | None = None,
    *,
    save_report: bool = True,
    trigger_retraining_on_drift: bool = True,
) -> dict[str, Any]:
    """Run one drift check and trigger retraining if drift is detected.

    Returns a plain dict so callers (API endpoint, scripts, tests) can
    assert on the result without importing Prefect.
    """
    settings = settings or get_settings()

    rows = await fetch_recent_predictions_task(settings)
    min_samples = settings.DRIFT_MIN_SAMPLES
    if len(rows) < min_samples:
        logger.info(
            "monitoring flow skipped — {} rows < min_samples={}",
            len(rows),
            min_samples,
        )
        record_drift_check(status="skipped", drift_score=None, drift_detected=False)
        return {
            "status": "skipped",
            "reason": "insufficient_prediction_logs",
            "num_samples": len(rows),
            "drift_detected": False,
            "retraining_triggered": False,
            "generated_at": datetime.now(tz=UTC).isoformat(),
        }

    try:
        reference_df = load_reference_dataset_task(settings)
    except DriftDataError as exc:
        logger.error("monitoring flow could not load reference data: {}", exc)
        record_drift_check(status="failed", drift_score=None, drift_detected=False)
        return {
            "status": "failed",
            "reason": str(exc),
            "num_samples": len(rows),
            "drift_detected": False,
            "retraining_triggered": False,
            "generated_at": datetime.now(tz=UTC).isoformat(),
        }

    current_df = build_current_dataset(
        rows, reference_columns=list(reference_df.columns)
    )

    try:
        result = run_drift_detection_task(
            reference_df, current_df, settings=settings, save_report=save_report
        )
    except DriftError as exc:
        logger.exception("monitoring flow drift run failed: {}", exc)
        record_drift_check(status="failed", drift_score=None, drift_detected=False)
        return {
            "status": "failed",
            "reason": f"drift_run_failed: {exc}",
            "num_samples": len(rows),
            "drift_detected": False,
            "retraining_triggered": False,
            "generated_at": datetime.now(tz=UTC).isoformat(),
        }

    result.current_window_end = rows[0].timestamp if rows else None
    result.current_window_start = rows[-1].timestamp if rows else None

    drift_detected = evaluate_drift_task(result, settings)

    retraining_triggered = False
    retraining_run_id: str | None = None
    if drift_detected and trigger_retraining_on_drift:
        retraining_payload = await trigger_retraining_task(True, trigger_reason="drift")
        if retraining_payload is not None:
            retraining_triggered = True
            retraining_run_id = retraining_payload.get("retraining_run_id")

    try:
        await persist_drift_report_task(
            result, settings, triggered_retrain=retraining_triggered
        )
    except Exception as exc:  # noqa: BLE001 — best-effort, never fail the flow
        logger.error("persist_drift_report failed inside flow: {}", exc)

    record_drift_check(
        status=result.status,
        drift_score=result.drift_score,
        drift_detected=bool(drift_detected),
    )

    payload: dict[str, Any] = {
        "status": "complete",
        "drift_detected": bool(drift_detected),
        "drift_score": result.drift_score,
        "num_samples": result.num_samples,
        "num_drifted_features": result.num_drifted_features,
        "total_features": result.total_features,
        "report_id": result.report_id,
        "retraining_triggered": retraining_triggered,
        "generated_at": result.generated_at.isoformat(),
    }
    if retraining_run_id is not None:
        payload["retraining_run_id"] = retraining_run_id
    return payload
