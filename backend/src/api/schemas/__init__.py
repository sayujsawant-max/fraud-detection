"""Pydantic v2 schemas for the FraudShield prediction API.

The schemas live in their own package so they can be imported by routers,
the predictor, and the test suite without creating a circular dependency on
``src.api.main``.
"""

from src.api.schemas.request import (
    BatchPredictionRequest,
    DriftCheckRequest,
    TransactionRequest,
)
from src.api.schemas.response import (
    BatchPredictionResponse,
    DriftCheckResponse,
    DriftReportDetail,
    DriftReportListResponse,
    DriftReportSummary,
    HealthResponse,
    ModelInfoResponse,
    MonitoringStatsResponse,
    PredictionLogDetail,
    PredictionLogListResponse,
    PredictionLogStatsResponse,
    PredictionLogSummary,
    PredictionResponse,
    ReadinessResponse,
    RootResponse,
)
from src.api.schemas.retraining import (
    MonitoringRunResponse,
    ReloadModelResponse,
    RetrainingRunDetail,
    RetrainingRunListResponse,
    RetrainingStatsResponse,
    RetrainTriggerRequest,
    RetrainTriggerResponse,
)

__all__ = [
    "BatchPredictionRequest",
    "BatchPredictionResponse",
    "DriftCheckRequest",
    "DriftCheckResponse",
    "DriftReportDetail",
    "DriftReportListResponse",
    "DriftReportSummary",
    "HealthResponse",
    "ModelInfoResponse",
    "MonitoringRunResponse",
    "MonitoringStatsResponse",
    "PredictionLogDetail",
    "PredictionLogListResponse",
    "PredictionLogStatsResponse",
    "PredictionLogSummary",
    "PredictionResponse",
    "ReadinessResponse",
    "ReloadModelResponse",
    "RetrainTriggerRequest",
    "RetrainTriggerResponse",
    "RetrainingRunDetail",
    "RetrainingRunListResponse",
    "RetrainingStatsResponse",
    "RootResponse",
    "TransactionRequest",
]
