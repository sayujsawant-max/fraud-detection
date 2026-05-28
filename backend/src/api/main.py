"""FastAPI application entrypoint.

Wires together configuration, logging, CORS, Prometheus instrumentation, and
the health router. Phase 0 deliberately omits prediction/monitoring/admin
routers — those are introduced in later phases.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.routers import health
from src.core.config import get_settings
from src.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — startup and shutdown hooks.

    Phase 3 will load the production MLflow model and initialise the database
    session factory here. Phase 0 just logs startup/shutdown events.
    """
    configure_logging()
    settings = get_settings()
    logger.info(
        "FraudShield API starting | version={} | env={}",
        settings.PROJECT_VERSION,
        settings.ENVIRONMENT,
    )
    yield
    logger.info("FraudShield API shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        description=(
            "FraudShield MLOps — real-time fraud detection API with MLflow, "
            "Evidently drift detection, Prefect orchestration, and Prometheus "
            "observability."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health", "/ready"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    app.include_router(health.router)

    return app


app = create_app()
