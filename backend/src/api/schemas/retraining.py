"""Phase 6 request + response schemas for the admin / retraining routers.

Kept in their own module to avoid bloating the existing request/response
files. The aggregate ``__init__`` re-exports the public names so router
code can keep importing from ``src.api.schemas``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TriggerReasonLiteral = Literal["manual", "drift", "scheduled"]
RetrainingStatusLiteral = Literal["running", "promoted", "rejected", "failed"]


# ---------------------------------------------------------------------------
# Admin endpoint schemas
# ---------------------------------------------------------------------------


class RetrainTriggerRequest(BaseModel):
    """Body for ``POST /v1/admin/retrain``.

    ``trigger_reason`` defaults to ``manual`` for the convenience case of
    posting an empty body from curl/Postman.
    """

    model_config = ConfigDict(extra="forbid")

    trigger_reason: TriggerReasonLiteral = Field(
        default="manual",
        description="Why the retrain was kicked off — surfaces in the audit row.",
    )


class RetrainTriggerResponse(BaseModel):
    """Body returned by ``POST /v1/admin/retrain``."""

    status: str = Field(..., description='"triggered" — flow handed off to background')
    trigger_reason: TriggerReasonLiteral
    message: str


class ReloadModelResponse(BaseModel):
    """Body returned by ``POST /v1/admin/reload-model``."""

    status: str
    model_name: str
    model_version: str
    model_stage: str
    is_dummy: bool
    loaded_at: datetime

    model_config = ConfigDict(protected_namespaces=())


class MonitoringRunResponse(BaseModel):
    """Body returned by ``POST /v1/admin/monitoring/run``."""

    status: str
    message: str


# ---------------------------------------------------------------------------
# Retraining read-side schemas
# ---------------------------------------------------------------------------


class RetrainingRunDetail(BaseModel):
    """Full :class:`RetrainingRun` row projection."""

    id: UUID
    trigger_reason: str
    started_at: datetime
    completed_at: datetime | None = None
    status: RetrainingStatusLiteral
    challenger_run_id: str | None = None
    challenger_model_uri: str | None = None
    challenger_model_version: str | None = None
    challenger_pr_auc: float | None = None
    champion_pr_auc: float | None = None
    promoted: bool = False
    api_reload_status: str | None = None
    outcome_notes: str | None = None
    error_message: str | None = None
    created_at: datetime


class RetrainingRunListResponse(BaseModel):
    """Body returned by ``GET /v1/retraining/runs``."""

    runs: list[RetrainingRunDetail]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)


class RetrainingStatsResponse(BaseModel):
    """Body returned by ``GET /v1/retraining/stats``."""

    total_runs: int = Field(..., ge=0)
    promoted_runs: int = Field(..., ge=0)
    rejected_runs: int = Field(..., ge=0)
    failed_runs: int = Field(..., ge=0)
    latest_run_at: datetime | None = None
    latest_status: RetrainingStatusLiteral | None = None
