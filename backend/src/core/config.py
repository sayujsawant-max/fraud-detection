"""Application settings loaded from environment variables.

Uses pydantic-settings v2 for type-safe configuration. All settings can be
overridden via environment variables or a .env file at the project root.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://fraudshield:fraudshield_password@postgres:5432/fraudshield_db"
    )

    # ---------- MLflow ----------
    MLFLOW_TRACKING_URI: str = Field(default="http://mlflow:5000")
    MLFLOW_MODEL_NAME: str = Field(default="fraud-detector")
    MLFLOW_MODEL_STAGE: str = Field(default="Production")

    # ---------- Security ----------
    API_KEY: str = Field(default="change-me")

    # ---------- Drift ----------
    DRIFT_THRESHOLD: float = Field(default=0.30, ge=0.0, le=1.0)

    # ---------- Frontend / CORS ----------
    FRONTEND_URL: str = Field(default="http://localhost:3000")

    # ---------- Prefect ----------
    PREFECT_API_URL: str = Field(default="http://prefect:4200/api")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
