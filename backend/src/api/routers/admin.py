"""Phase 6 admin router — protected by API key.

Mounted under ``/v1/admin``. Three operator-facing endpoints:

* ``POST /v1/admin/retrain``           — trigger the retraining flow.
* ``POST /v1/admin/reload-model``      — hot-reload the production model.
* ``POST /v1/admin/monitoring/run``    — run the monitoring flow once.

The admin router does NOT block on long-running flows: ``retrain`` and
``monitoring/run`` hand the work off to FastAPI's ``BackgroundTasks`` and
return immediately. This keeps curl-based smoke tests snappy and means
the flow can take its time without timing out the HTTP request.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from loguru import logger

from src.api.dependencies import set_predictor, verify_api_key
from src.api.schemas import (
    MonitoringRunResponse,
    ReloadModelResponse,
    RetrainTriggerRequest,
    RetrainTriggerResponse,
)
from src.core.config import get_settings
from src.core.exceptions import ModelNotLoadedError
from src.core.metrics import record_model_loaded
from src.models.loader import LoadedModel, load_model_safely
from src.models.predictor import FraudPredictor

router = APIRouter(prefix="/v1/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Background-task launchers — exported so tests can patch them
# ---------------------------------------------------------------------------


async def _run_retraining_in_background(trigger_reason: str) -> None:
    """Background entrypoint that drives the retraining flow.

    Lives at module scope so tests can ``monkeypatch.setattr`` it without
    needing to spin up Prefect.
    """
    # Lazy import: keeps the FastAPI startup path free of Prefect when no
    # one ever calls /v1/admin/retrain.
    from src.workflows.retraining_flow import retraining_flow

    try:
        result = await retraining_flow(trigger_reason=trigger_reason)
        logger.info(
            "background retraining flow complete | status={} promoted={}",
            result.get("status"),
            result.get("promoted"),
        )
    except Exception as exc:  # noqa: BLE001 — background tasks must not crash the worker
        logger.exception("background retraining flow failed: {}", exc)


async def _run_monitoring_in_background() -> None:
    """Background entrypoint that drives the monitoring flow."""
    from src.workflows.monitoring_flow import monitoring_flow

    try:
        result = await monitoring_flow()
        logger.info(
            "background monitoring flow complete | status={} drift_detected={}",
            result.get("status"),
            result.get("drift_detected"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("background monitoring flow failed: {}", exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/retrain",
    response_model=RetrainTriggerResponse,
    responses={
        403: {"description": "Missing or invalid API key"},
        503: {"description": "Admin API key is not configured"},
    },
)
async def trigger_retrain(
    background_tasks: BackgroundTasks,
    payload: RetrainTriggerRequest | None = None,
    _: str = Depends(verify_api_key),
) -> RetrainTriggerResponse:
    """Kick off the retraining flow as a background task."""
    body = payload or RetrainTriggerRequest()
    background_tasks.add_task(_run_retraining_in_background, body.trigger_reason)
    logger.info("retraining flow queued | trigger_reason={}", body.trigger_reason)
    return RetrainTriggerResponse(
        status="triggered",
        trigger_reason=body.trigger_reason,
        message="Retraining flow started",
    )


@router.post(
    "/reload-model",
    response_model=ReloadModelResponse,
    responses={
        403: {"description": "Missing or invalid API key"},
        503: {"description": "Model could not be loaded"},
    },
)
async def reload_model(
    request: Request,
    _: str = Depends(verify_api_key),
) -> ReloadModelResponse:
    """Reload the production model from MLflow into the live predictor."""
    settings = get_settings()
    try:
        loaded: LoadedModel | None = load_model_safely(settings)
    except ModelNotLoadedError as exc:
        logger.error("reload-model failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model could not be reloaded.",
        ) from exc

    if loaded is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model could not be reloaded.",
        )

    set_predictor(request.app, FraudPredictor(loaded))
    record_model_loaded(
        model_name=loaded.model_name,
        model_version=loaded.model_version,
        model_stage=loaded.model_stage,
        loaded_at_epoch=loaded.loaded_at.timestamp(),
    )
    logger.info(
        "model reloaded | name={} version={} stage={} dummy={}",
        loaded.model_name,
        loaded.model_version,
        loaded.model_stage,
        loaded.is_dummy,
    )
    return ReloadModelResponse(
        status="reloaded",
        model_name=loaded.model_name,
        model_version=loaded.model_version,
        model_stage=loaded.model_stage,
        is_dummy=loaded.is_dummy,
        loaded_at=loaded.loaded_at,
    )


@router.post(
    "/monitoring/run",
    response_model=MonitoringRunResponse,
    responses={
        403: {"description": "Missing or invalid API key"},
    },
)
async def trigger_monitoring(
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_api_key),
) -> MonitoringRunResponse:
    """Manually run the monitoring flow once (useful for demos)."""
    background_tasks.add_task(_run_monitoring_in_background)
    logger.info("monitoring flow queued via /v1/admin/monitoring/run")
    return MonitoringRunResponse(
        status="triggered",
        message="Monitoring flow started",
    )
