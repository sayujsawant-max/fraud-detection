"""Shared pytest fixtures for the FraudShield backend test suite.

The fixtures here let tests exercise the API without MLflow, PostgreSQL, or
Docker. A :class:`DummyFraudModel`-backed :class:`FraudPredictor` is
materialised once per test session and attached to ``app.state`` so the
``Depends(get_predictor)`` chain returns a real, working predictor. Phase 4
adds a SQLite in-memory async fixture so prediction-logging and
``/v1/logs`` integration tests can run without a Postgres container.
"""

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio

# Keep Prefect in a fully-local, no-API mode for the whole test run. Set
# BEFORE the workflows package is imported so Prefect doesn't try to
# stand up a temporary server or push logs out to a tracking API.
os.environ.setdefault("PREFECT_API_URL", "")
os.environ.setdefault("PREFECT_LOGGING_TO_API_ENABLED", "false")
os.environ.setdefault("PREFECT_LOGGING_LEVEL", "ERROR")
os.environ.setdefault("PREFECT_SERVER_LOGGING_LEVEL", "ERROR")
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")
os.environ.setdefault("PREFECT_HOME", ".prefect-test")
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Patch the loader the lifespan hook reaches for BEFORE importing the FastAPI
# app — otherwise startup tries to contact http://mlflow:5000 and stalls.
import src.api.main as _main_module  # noqa: E402
import src.db.models  # noqa: F401,E402  — registers tables on Base.metadata
from src.api.dependencies import (  # noqa: E402
    get_db_session,
    set_predictor,
)
from src.db.base import Base  # noqa: E402
from src.features.constants import FEATURE_COLUMNS  # noqa: E402
from src.models.loader import (  # noqa: E402
    DUMMY_MODEL_NAME,
    DUMMY_MODEL_STAGE,
    DUMMY_MODEL_VERSION,
    DummyFraudModel,
    LoadedModel,
)
from src.models.predictor import FraudPredictor  # noqa: E402


def _no_op_loader(_settings=None) -> None:
    """Return None so the lifespan hook treats the model as not-yet-loaded.

    Each fixture below then injects its own predictor (or leaves it None)
    via :func:`set_predictor` after the TestClient lifespan completes.
    """
    return None


_main_module.load_model_safely = _no_op_loader  # type: ignore[assignment]

from src.api.main import app  # noqa: E402,I001  (must follow patch)


def _build_dummy_predictor(threshold: float = 0.5) -> FraudPredictor:
    """Return a :class:`FraudPredictor` wrapping a :class:`DummyFraudModel`."""
    loaded = LoadedModel(
        model=DummyFraudModel(),
        model_name=DUMMY_MODEL_NAME,
        model_version=DUMMY_MODEL_VERSION,
        model_stage=DUMMY_MODEL_STAGE,
        threshold=threshold,
        loaded_at=datetime.now(tz=UTC),
        feature_count=len(FEATURE_COLUMNS),
        is_dummy=True,
    )
    return FraudPredictor(loaded)


@pytest.fixture(scope="session")
def dummy_predictor() -> FraudPredictor:
    """Session-scoped dummy predictor used for predict/info tests."""
    return _build_dummy_predictor()


# ---------------------------------------------------------------------------
# Async SQLite database fixtures (Phase 4)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def sqlite_sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Per-test SQLite in-memory engine with prediction_logs created.

    A fresh URL keeps tests isolated from each other; ``StaticPool`` is not
    required because we hand the engine straight into a sessionmaker and
    never spread connections across coroutines.
    """
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(
        bind=engine, expire_on_commit=False, autoflush=False
    )
    try:
        yield sessionmaker
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(
    sqlite_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield one :class:`AsyncSession` bound to the in-memory SQLite engine."""
    async with sqlite_sessionmaker() as session:
        yield session


@pytest.fixture()
def client(
    dummy_predictor: FraudPredictor,
    sqlite_sessionmaker: async_sessionmaker[AsyncSession],
) -> Iterator[TestClient]:
    """TestClient with the dummy predictor + SQLite DB wired in.

    Using ``TestClient`` as a context manager triggers the lifespan hook,
    which attempts to load a real model. We override ``app.state.predictor``
    afterwards so the dummy is what the routers see. The ``get_db_session``
    dependency is overridden to point at the in-memory SQLite engine.
    """

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with sqlite_sessionmaker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_get_db_session

    with TestClient(app) as test_client:
        set_predictor(app, dummy_predictor)
        yield test_client
        set_predictor(app, None)

    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture()
def client_without_model(
    sqlite_sessionmaker: async_sessionmaker[AsyncSession],
) -> Iterator[TestClient]:
    """TestClient with the predictor explicitly cleared (no model loaded)."""

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with sqlite_sessionmaker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_get_db_session

    with TestClient(app) as test_client:
        set_predictor(app, None)
        yield test_client

    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture()
def sample_transaction() -> dict:
    """A single, valid transaction payload for the API.

    Values lie inside every range constraint and use training-time
    categorical vocabulary so the dummy model can score it.
    """
    return {
        "transaction_amount": 142.50,
        "transaction_hour": 14,
        "transaction_day_of_week": 2,
        "is_weekend": 0,
        "merchant_category": "groceries",
        "transaction_type": "purchase",
        "card_type": "visa",
        "transaction_count_24h": 3,
        "transaction_count_7d": 12,
        "avg_transaction_amount_30d": 110.0,
        "amount_to_avg_ratio": 1.30,
        "unique_merchants_7d": 5,
        "is_first_transaction_merchant": 0,
        "distance_from_home_km": 4.2,
        "is_foreign_transaction": 0,
        "is_high_risk_country": 0,
        "device_type": "mobile",
        "browser_type": "chrome",
        "ip_risk_score": 0.12,
        "account_age_days": 540,
        "user_age": 34,
        "credit_limit": 8000.0,
        "credit_utilization": 0.34,
        "previous_fraud_flag": 0,
        "log_amount": 4.96,
        "is_high_velocity": 0,
        "is_new_account": 0,
        "is_late_night": 0,
        "amount_z_score": 0.22,
    }


@pytest.fixture()
def risky_transaction(sample_transaction: dict) -> dict:
    """A high-risk transaction the dummy model should flag as fraud."""
    risky = dict(sample_transaction)
    risky.update(
        {
            "amount_to_avg_ratio": 6.0,
            "is_high_velocity": 1,
            "is_foreign_transaction": 1,
            "is_high_risk_country": 1,
            "ip_risk_score": 0.95,
            "is_late_night": 1,
            "is_new_account": 1,
        }
    )
    return risky
