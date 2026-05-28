"""Model-metadata endpoints (``/v1/model/...``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_predictor
from src.api.schemas import ModelInfoResponse
from src.models.predictor import FraudPredictor

router = APIRouter(prefix="/v1/model", tags=["model"])


@router.get(
    "/info",
    response_model=ModelInfoResponse,
    responses={503: {"description": "Model is not loaded"}},
)
async def model_info(
    predictor: FraudPredictor = Depends(get_predictor),
) -> ModelInfoResponse:
    """Return identity + threshold + load-time of the currently-served model."""
    return ModelInfoResponse(**predictor.get_model_info())
