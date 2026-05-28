"""Health, readiness, and root endpoints.

In Phase 0 these are intentionally minimal. The /ready endpoint will be
extended in Phase 3 to verify the database connection and that a production
MLflow model is loaded.
"""

from fastapi import APIRouter

from src.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, str]:
    """Service root — returns name, version, and docs URL."""
    settings = get_settings()
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "docs": "/docs",
    }


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — returns ok if the process is running."""
    settings = get_settings()
    return {"status": "ok", "version": settings.PROJECT_VERSION}


@router.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness probe — Phase 0 always returns ready.

    Phase 3 will check database connectivity and model load state here.
    """
    return {"status": "ready"}
