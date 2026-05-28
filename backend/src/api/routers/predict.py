"""Prediction endpoints.

``POST /v1/predict`` scores a single transaction.
``POST /v1/predict/batch`` scores up to ``MAX_BATCH_SIZE`` transactions in
one round trip — useful for backfills and batch evaluation.

Phase 4 wires both endpoints into the PostgreSQL audit-log table via the
:class:`PredictionLogRepository`. Logging failures are swallowed and
reported via Loguru so the prediction path never fails because of a
downstream database hiccup — see
``docs/interview-guide.md`` for the design rationale.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session, get_predictor
from src.api.schemas import (
    BatchPredictionRequest,
    BatchPredictionResponse,
    PredictionResponse,
    TransactionRequest,
)
from src.core.exceptions import (
    InvalidModelOutputError,
    PredictionError,
)
from src.core.metrics import record_batch, record_prediction
from src.db.repositories import PredictionLogRepository
from src.models.predictor import FraudPredictor, PredictionResult

router = APIRouter(prefix="/v1", tags=["predict"])


def _result_to_response(result_dict: dict) -> PredictionResponse:
    """Build a :class:`PredictionResponse` from a predictor result dict."""
    return PredictionResponse(**result_dict)


def _log_record_kwargs(
    result: PredictionResult, features: dict[str, Any]
) -> dict[str, Any]:
    """Translate a predictor result + input dict into repository kwargs."""
    return {
        "transaction_id": result.transaction_id,
        "input_features": features,
        "fraud_probability": result.fraud_probability,
        "predicted_label": result.predicted_label,
        "model_name": result.model_name,
        "model_version": result.model_version,
        "model_stage": result.model_stage,
        "optimal_threshold": result.threshold_used,
        "latency_ms": result.latency_ms,
    }


async def _safe_log_prediction(
    session: AsyncSession,
    result: PredictionResult,
    features: dict[str, Any],
) -> None:
    """Best-effort prediction log. Never raises.

    The API contract promises a 200 on a successful score even if our
    audit-log write fails. We log the exception so operators can chase it
    in observability without blocking the user.
    """
    repo = PredictionLogRepository(session)
    try:
        await repo.create_log(**_log_record_kwargs(result, features))
    except Exception as exc:  # noqa: BLE001 — audit logging is best effort
        logger.error(
            "prediction logging failed | tx={} err={}",
            result.transaction_id,
            exc,
        )


async def _safe_log_batch(
    session: AsyncSession,
    results: list[PredictionResult],
    inputs: list[dict[str, Any]],
) -> None:
    """Best-effort batch insert with per-record fallback.

    On bulk-insert failure we fall back to inserting one row at a time so a
    single bad record doesn't poison the rest of the batch.
    """
    repo = PredictionLogRepository(session)
    records = [_log_record_kwargs(r, f) for r, f in zip(results, inputs, strict=True)]
    try:
        await repo.create_many_logs(records)
        return
    except Exception as exc:  # noqa: BLE001 — best-effort fall-through
        logger.error("batch prediction logging failed at bulk insert: {}", exc)

    for record in records:
        try:
            await repo.create_log(**record)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "per-record logging failed | tx={} err={}",
                record.get("transaction_id"),
                exc,
            )


@router.post(
    "/predict",
    response_model=PredictionResponse,
    responses={
        500: {"description": "Prediction failed"},
        503: {"description": "Model is not loaded"},
    },
)
async def predict(
    payload: TransactionRequest,
    predictor: FraudPredictor = Depends(get_predictor),
    session: AsyncSession = Depends(get_db_session),
) -> PredictionResponse:
    """Score a single transaction and return fraud probability + label."""
    payload_dict = payload.model_dump()
    try:
        result = predictor.predict(payload_dict)
    except (PredictionError, InvalidModelOutputError) as exc:
        # Log with full context; expose only a generic message to the caller.
        logger.exception("prediction failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction failed — see server logs.",
        ) from exc

    # Audit-log the prediction *after* we've decided to return success. We
    # capture only the model-input features (transaction_id sits beside the
    # JSON blob in its own column already).
    features = {k: v for k, v in payload_dict.items() if k != "transaction_id"}
    await _safe_log_prediction(session, result, features)
    record_prediction(result.predicted_label, result.fraud_probability)

    return _result_to_response(result.as_dict())


@router.post(
    "/predict/batch",
    response_model=BatchPredictionResponse,
    responses={
        422: {"description": "Validation error (e.g., batch over MAX_BATCH_SIZE)"},
        500: {"description": "Prediction failed"},
        503: {"description": "Model is not loaded"},
    },
)
async def predict_batch(
    payload: BatchPredictionRequest,
    predictor: FraudPredictor = Depends(get_predictor),
    session: AsyncSession = Depends(get_db_session),
) -> BatchPredictionResponse:
    """Score a batch of transactions in a single call."""
    start = time.perf_counter()
    transaction_dicts = [tx.model_dump() for tx in payload.transactions]
    try:
        results = predictor.predict_batch(transaction_dicts)
    except (PredictionError, InvalidModelOutputError) as exc:
        logger.exception("batch prediction failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch prediction failed — see server logs.",
        ) from exc
    batch_latency_ms = (time.perf_counter() - start) * 1000.0

    feature_payloads = [
        {k: v for k, v in tx.items() if k != "transaction_id"}
        for tx in transaction_dicts
    ]
    await _safe_log_batch(session, results, feature_payloads)
    record_batch([(r.predicted_label, r.fraud_probability) for r in results])

    return BatchPredictionResponse(
        predictions=[_result_to_response(r.as_dict()) for r in results],
        batch_size=len(results),
        batch_latency_ms=batch_latency_ms,
        timestamp=datetime.now(tz=UTC),
    )
