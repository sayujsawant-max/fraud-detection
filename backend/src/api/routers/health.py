"""Health, readiness, and root endpoints.

Liveness (``/health``) stays cheap — it just confirms the process is alive.
Readiness (``/ready``) reports whether (1) the predictor was successfully
loaded at startup and (2) the database is reachable, returning 503 when
either is false. That's the signal Kubernetes / Prometheus blackbox /
Docker healthchecks need to gate traffic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import PREDICTOR_STATE_KEY, get_db_session
from src.api.schemas import HealthResponse, ReadinessResponse, RootResponse
from src.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    """Service root — returns name, version, and docs URL."""
    settings = get_settings()
    return RootResponse(
        name=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        docs="/docs",
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — returns ok if the process is running."""
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.PROJECT_VERSION)


async def _is_db_reachable(session: AsyncSession) -> bool:
    """Run a trivial query to confirm the DB connection is alive.

    ``SELECT 1`` is the cheapest possible probe and works the same way on
    PostgreSQL, SQLite, and MySQL. We deliberately do not raise — the
    readiness handler converts a False return into a 503.
    """
    try:
        await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 — readiness must never crash
        logger.warning("readiness DB probe failed: {}", exc)
        return False


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def ready(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> ReadinessResponse:
    """Readiness probe — reports model + database status.

    Returns HTTP 200 only when both the predictor is loaded and the
    database answers a ``SELECT 1`` query. Anything else flips the status
    code to 503 so traffic management layers can route around the
    instance.
    """
    predictor = getattr(request.app.state, PREDICTOR_STATE_KEY, None)
    model_loaded = predictor is not None
    db_connected = await _is_db_reachable(session)

    if model_loaded and db_connected:
        return ReadinessResponse(status="ready", model_loaded=True, db_connected=True)

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="not_ready",
        model_loaded=model_loaded,
        db_connected=db_connected,
    )
