"""FastAPI application entrypoint.

Wires together configuration, logging, CORS, Prometheus instrumentation,
exception handlers, and all routers. The lifespan hook loads the
production fraud-detector model from MLflow (or a dummy fallback) and
stores the resulting :class:`FraudPredictor` on ``app.state`` so the
dependency-injection layer can hand it to every router.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.dependencies import set_predictor
from src.api.middleware import PrometheusMiddleware
from src.api.routers import admin as admin_router
from src.api.routers import health, predict
from src.api.routers import logs as logs_router
from src.api.routers import model as model_router
from src.api.routers import monitoring as monitoring_router
from src.api.routers import retraining as retraining_router
from src.core.config import get_settings
from src.core.exceptions import (
    FraudShieldError,
    InvalidModelOutputError,
    ModelNotLoadedError,
    PredictionError,
)
from src.core.logging import configure_logging
from src.core.metrics import record_model_loaded
from src.db.session import dispose_engine
from src.models.loader import load_model_safely
from src.models.predictor import FraudPredictor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging and load the production model at startup.

    Loading uses :func:`load_model_safely` so the app starts even when the
    MLflow tracking server is unreachable. The readiness probe then reports
    503 until the operator fixes the registry (unless ``ALLOW_DUMMY_MODEL``
    is True, in which case a dummy estimator was substituted).
    """
    configure_logging()
    settings = get_settings()
    logger.info(
        "FraudShield API starting | version={} | env={} | allow_dummy={}",
        settings.PROJECT_VERSION,
        settings.ENVIRONMENT,
        settings.ALLOW_DUMMY_MODEL,
    )

    loaded = load_model_safely(settings)
    if loaded is not None:
        set_predictor(app, FraudPredictor(loaded))
        record_model_loaded(
            model_name=loaded.model_name,
            model_version=loaded.model_version,
            model_stage=loaded.model_stage,
            loaded_at_epoch=loaded.loaded_at.timestamp(),
        )
        logger.info(
            "predictor ready | name={} version={} stage={} dummy={}",
            loaded.model_name,
            loaded.model_version,
            loaded.model_stage,
            loaded.is_dummy,
        )
    else:
        set_predictor(app, None)
        logger.error(
            "predictor unavailable — /v1/predict and /v1/model/info will return 503"
        )

    yield
    logger.info("FraudShield API shutting down")
    # Close the async DB engine so the pool drains cleanly on shutdown.
    try:
        await dispose_engine()
    except Exception as exc:  # noqa: BLE001 — shutdown must not raise
        logger.warning("dispose_engine failed during shutdown: {}", exc)


def _install_exception_handlers(app: FastAPI) -> None:
    """Register handlers that turn domain errors into safe HTTP responses.

    Stack traces are logged server-side but never returned to the caller.
    """

    @app.exception_handler(ModelNotLoadedError)
    async def _model_not_loaded(
        _request: Request, exc: ModelNotLoadedError
    ) -> JSONResponse:
        logger.warning("ModelNotLoadedError: {}", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Model is not loaded."},
        )

    @app.exception_handler(PredictionError)
    async def _prediction_error(
        _request: Request, exc: PredictionError
    ) -> JSONResponse:
        logger.exception("PredictionError: {}", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Prediction failed."},
        )

    @app.exception_handler(InvalidModelOutputError)
    async def _invalid_output(
        _request: Request, exc: InvalidModelOutputError
    ) -> JSONResponse:
        logger.exception("InvalidModelOutputError: {}", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Model returned invalid output."},
        )

    @app.exception_handler(FraudShieldError)
    async def _generic_fraudshield(
        _request: Request, exc: FraudShieldError
    ) -> JSONResponse:
        logger.exception("FraudShieldError: {}", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )

    # Keep FastAPI's default 422 envelope for Pydantic validation errors —
    # this handler exists only to log the failure, not to reshape it.
    # ``jsonable_encoder`` handles the non-JSON-native objects that Pydantic
    # may stash in the ``ctx`` field (e.g. the raw ValueError instance).
    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.info("422 validation error on {}", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": jsonable_encoder(exc.errors())},
        )


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
    # The custom Prometheus middleware emits the ``fraudshield_*`` series
    # (request count, latency histogram, in-progress gauge) alongside the
    # default instrumentator ``http_*`` series.
    app.add_middleware(PrometheusMiddleware)

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health", "/ready"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    _install_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(predict.router)
    app.include_router(model_router.router)
    app.include_router(logs_router.router)
    app.include_router(monitoring_router.router)
    app.include_router(admin_router.router)
    app.include_router(retraining_router.router)

    return app


app = create_app()
