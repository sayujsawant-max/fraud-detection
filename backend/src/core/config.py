"""Application settings loaded from environment variables.

Uses pydantic-settings v2 for type-safe configuration. All settings can be
overridden via environment variables or a .env file at the project root.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Driver prefixes we know how to translate to/from the async equivalent. The
# values are the *async* drivers we want SQLAlchemy to dispatch through inside
# the FastAPI process; Alembic + sync scripts keep using the sync drivers.
_ASYNC_DRIVER_MAP: dict[str, str] = {
    "postgresql://": "postgresql+asyncpg://",
    "postgresql+psycopg2://": "postgresql+asyncpg://",
    "postgresql+psycopg://": "postgresql+asyncpg://",
    "sqlite://": "sqlite+aiosqlite://",
}
_SYNC_DRIVER_MAP: dict[str, str] = {
    "postgresql+asyncpg://": "postgresql+psycopg2://",
    "sqlite+aiosqlite://": "sqlite://",
}


class Settings(BaseSettings):
    """FraudShield runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---------- Project metadata ----------
    PROJECT_NAME: str = "FraudShield API"
    PROJECT_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development")

    # ---------- Database ----------
    # Accept either sync (psycopg2) or async (asyncpg) DATABASE_URL. The async
    # FastAPI engine consumes :pyattr:`database_url_async` while Alembic and
    # one-off scripts consume :pyattr:`database_url_sync`.
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://fraudshield:fraudshield_password@postgres:5432/fraudshield_db"
    )
    DB_ECHO: bool = Field(default=False)
    DB_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)

    # ---------- MLflow ----------
    MLFLOW_TRACKING_URI: str = Field(default="http://mlflow:5000")
    MLFLOW_MODEL_NAME: str = Field(default="fraud-detector")
    # Logical pointer to the model to load. We try the MLflow Stage taxonomy
    # first (``models:/<name>/<Stage>``) and fall back to aliases
    # (``models:/<name>@<alias>``) for MLflow 3.x where Stages were removed.
    MLFLOW_MODEL_STAGE: str = Field(default="Production")

    # ---------- Security ----------
    API_KEY: str = Field(default="change-me")

    # ---------- Drift ----------
    DRIFT_THRESHOLD: float = Field(default=0.30, ge=0.0, le=1.0)
    # Minimum number of prediction-log rows needed to compute a drift report.
    # Below this the API/script returns ``status="skipped"`` rather than
    # generating an unreliable report on too little data.
    DRIFT_MIN_SAMPLES: int = Field(default=200, ge=1)
    # Default window of recent prediction logs to feed into Evidently. The
    # API caller can override per-request via the ``limit`` body field.
    DRIFT_LOOKBACK_LIMIT: int = Field(default=1000, ge=1)
    # Filesystem paths used by the drift layer. Both are resolved relative to
    # the project root (current working directory at process start) so the
    # same .env works from ``backend/`` and from the repo root.
    REFERENCE_DATA_PATH: str = Field(default="backend/data/reference/reference.parquet")
    DRIFT_REPORT_DIR: str = Field(default="backend/reports/drift")

    # ---------- Frontend / CORS ----------
    FRONTEND_URL: str = Field(default="http://localhost:3000")

    # ---------- Prefect ----------
    PREFECT_API_URL: str = Field(default="http://prefect:4200/api")
    PREFECT_API_KEY: str = Field(default="")
    PREFECT_WORK_POOL: str = Field(default="fraudshield-pool")
    # Cron schedules used by ``backend/scripts/deploy_prefect_flows.py``.
    PREFECT_MONITORING_CRON: str = Field(default="0 */6 * * *")
    PREFECT_RETRAINING_CRON: str = Field(default="0 2 * * 0")

    # ---------- Retraining (Phase 6) ----------
    # Minimum PR-AUC improvement required to promote a challenger model.
    # 0.01 = "at least one percentage point" — tightly bounded so noisy
    # runs don't trigger a promotion churn.
    MODEL_PROMOTION_MIN_DELTA: float = Field(default=0.01, ge=0.0, le=1.0)
    # URL the retraining flow uses to call /v1/admin/reload-model after a
    # successful promotion. Defaults to the API container's docker-compose
    # alias so the flow works inside the stack out of the box.
    API_BASE_URL: str = Field(default="http://api:8000")

    # ---------- Serving ----------
    # When True and MLflow loading fails, the API falls back to a
    # DummyFraudModel so the rest of the system can be exercised end-to-end
    # without a registered model. Set False in production.
    ALLOW_DUMMY_MODEL: bool = Field(default=True)
    # Threshold used when neither the optimal_threshold.json artifact nor an
    # MLflow run metric is available.
    DEFAULT_THRESHOLD: float = Field(default=0.5, ge=0.0, le=1.0)
    # Hard cap on a single batch prediction request. Returned as 422 when
    # exceeded so the API does not silently accept huge payloads.
    MAX_BATCH_SIZE: int = Field(default=100, ge=1)

    # ------------------------------------------------------------------
    # Database URL helpers
    # ------------------------------------------------------------------

    @property
    def database_url_async(self) -> str:
        """Return DATABASE_URL normalised to an async SQLAlchemy driver.

        FastAPI runs SQLAlchemy 2.0 in async mode. If the operator supplies a
        sync URL (e.g. ``postgresql+psycopg2://...``) we transparently rewrite
        it to the async equivalent — this keeps a single ``DATABASE_URL``
        variable across local dev, Docker, and CI.
        """
        url = self.DATABASE_URL
        for prefix, replacement in _ASYNC_DRIVER_MAP.items():
            if url.startswith(prefix) and not url.startswith(replacement):
                return replacement + url[len(prefix) :]
        return url

    @property
    def database_url_sync(self) -> str:
        """Return DATABASE_URL normalised to a *sync* SQLAlchemy driver.

        Used by Alembic, ``scripts/init_db.py``, and ``scripts/seed_prediction_logs.py``,
        which all run outside the async event loop.
        """
        url = self.DATABASE_URL
        for prefix, replacement in _SYNC_DRIVER_MAP.items():
            if url.startswith(prefix):
                return replacement + url[len(prefix) :]
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
