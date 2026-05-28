"""Response schemas for the FraudShield prediction API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RootResponse(BaseModel):
    """Body returned by ``GET /``."""

    name: str
    version: str
    docs: str


class HealthResponse(BaseModel):
    """Body returned by ``GET /health``."""

    status: str
    version: str


class ReadinessResponse(BaseModel):
    """Body returned by ``GET /ready``.

    Phase 4 adds the ``db_connected`` field so orchestrators can distinguish
    "model loaded but DB down" from "model not loaded". A 503 is emitted
    when either is false.
    """

    status: str
    model_loaded: bool
    db_connected: bool = True

    # The ``model_`` prefix collides with Pydantic v2's reserved namespace
    # for configuration, so we tell Pydantic to leave our fields alone.
    model_config = ConfigDict(protected_namespaces=())


class PredictionResponse(BaseModel):
    """Body returned by ``POST /v1/predict`` (and one element per batch item)."""

    transaction_id: str
    fraud_probability: float = Field(..., ge=0.0, le=1.0)
    predicted_label: int = Field(..., ge=0, le=1)
    is_fraud: bool
    model_name: str
    model_version: str
    model_stage: str
    threshold_used: float = Field(..., ge=0.0, le=1.0)
    latency_ms: float = Field(..., ge=0.0)
    timestamp: datetime

    model_config = ConfigDict(protected_namespaces=())


class BatchPredictionResponse(BaseModel):
    """Body returned by ``POST /v1/predict/batch``."""

    predictions: list[PredictionResponse]
    batch_size: int = Field(..., ge=1)
    batch_latency_ms: float = Field(..., ge=0.0)
    timestamp: datetime


class ModelInfoResponse(BaseModel):
    """Body returned by ``GET /v1/model/info``."""

    model_name: str
    model_version: str
    model_stage: str
    model_loaded: bool
    optimal_threshold: float
    feature_count: int
    loaded_at: datetime | None

    model_config = ConfigDict(protected_namespaces=())


class ErrorResponse(BaseModel):
    """Generic error envelope for non-422 errors."""

    detail: str


# ---------------------------------------------------------------------------
# Phase 4 — Prediction log audit-trail schemas
# ---------------------------------------------------------------------------


class PredictionLogSummary(BaseModel):
    """One row in the ``GET /v1/logs`` list response.

    ``input_features`` is omitted on purpose so the list endpoint stays
    cheap. Clients that need the full payload call ``GET /v1/logs/{id}``.
    """

    id: UUID
    transaction_id: str
    timestamp: datetime
    fraud_probability: float = Field(..., ge=0.0, le=1.0)
    predicted_label: int = Field(..., ge=0, le=1)
    is_fraud: bool
    model_name: str
    model_version: str
    model_stage: str | None = None
    latency_ms: float | None = None

    model_config = ConfigDict(protected_namespaces=())


class PredictionLogListResponse(BaseModel):
    """Body returned by ``GET /v1/logs``."""

    logs: list[PredictionLogSummary]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class PredictionLogDetail(PredictionLogSummary):
    """Detailed view returned by ``GET /v1/logs/{log_id}`` — includes inputs."""

    input_features: dict[str, Any]
    optimal_threshold: float = Field(..., ge=0.0, le=1.0)
    created_at: datetime


class PredictionLogStatsResponse(BaseModel):
    """Body returned by ``GET /v1/logs/stats/summary``."""

    total_predictions: int = Field(..., ge=0)
    fraud_predictions: int = Field(..., ge=0)
    legitimate_predictions: int = Field(..., ge=0)
    fraud_rate: float = Field(..., ge=0.0, le=1.0)
    avg_fraud_probability: float = Field(..., ge=0.0, le=1.0)
    avg_latency_ms: float = Field(..., ge=0.0)
    latest_prediction_at: datetime | None = None


# ---------------------------------------------------------------------------
# Phase 5 — Evidently drift detection schemas
# ---------------------------------------------------------------------------


class DriftCheckResponse(BaseModel):
    """Body returned by ``POST /v1/monitoring/drift/check``.

    ``status="skipped"`` is a *success* (HTTP 200) — it just means we
    didn't have enough prediction logs to produce a meaningful report.
    Callers should branch on ``status`` rather than on the HTTP code.
    """

    status: str
    drift_detected: bool = False
    drift_score: float | None = Field(default=None, ge=0.0, le=1.0)
    num_drifted_features: int | None = Field(default=None, ge=0)
    total_features: int | None = Field(default=None, ge=0)
    num_samples: int = Field(..., ge=0)
    report_id: str | None = None
    report_html_url: str | None = None
    reason: str | None = None
    generated_at: datetime


class DriftReportSummary(BaseModel):
    """One row in the ``GET /v1/monitoring/drift-reports`` list response."""

    id: UUID
    report_id: str
    generated_at: datetime
    status: str
    drift_detected: bool
    drift_score: float | None = Field(default=None, ge=0.0, le=1.0)
    num_drifted_features: int | None = None
    total_features: int | None = None
    num_samples: int = Field(..., ge=0)
    report_html_url: str | None = None


class DriftReportListResponse(BaseModel):
    """Body returned by ``GET /v1/monitoring/drift-reports``."""

    reports: list[DriftReportSummary]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class DriftReportDetail(DriftReportSummary):
    """Body returned by ``GET /v1/monitoring/drift-reports/{report_id}``."""

    reference_dataset_path: str | None = None
    current_window_start: datetime | None = None
    current_window_end: datetime | None = None
    report_html_path: str | None = None
    report_json_path: str | None = None
    report_json: dict[str, Any] | None = None
    triggered_retrain: bool = False
    reason: str | None = None
    created_at: datetime


class MonitoringStatsResponse(BaseModel):
    """Body returned by ``GET /v1/monitoring/stats``."""

    latest_drift_score: float | None = Field(default=None, ge=0.0, le=1.0)
    latest_drift_detected: bool | None = None
    last_check_at: datetime | None = None
    total_reports: int = Field(..., ge=0)
    drift_events: int = Field(..., ge=0)
    avg_drift_score: float = Field(..., ge=0.0, le=1.0)
