"""FastAPI dependency-injection providers.

Routers consume the :class:`FraudPredictor`, the underlying
:class:`LoadedModel`, and an :class:`AsyncSession` via these providers so
unit/integration tests can override them with mocks/dummies without
monkey-patching.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import ModelNotLoadedError
from src.db.session import get_sessionmaker
from src.models.loader import LoadedModel
from src.models.predictor import FraudPredictor

API_KEY_HEADER: str = "X-API-Key"

# Key under which we stash the predictor on ``app.state``. Kept as a module
# constant so tests can poke values in/out without string typos.
PREDICTOR_STATE_KEY: str = "predictor"


def get_predictor(request: Request) -> FraudPredictor:
    """Return the active :class:`FraudPredictor`, or raise 503 if absent.

    The predictor is materialised by the FastAPI lifespan hook and attached
    to ``app.state``. When MLflow loading fails and ``ALLOW_DUMMY_MODEL`` is
    False, ``app.state.predictor`` is ``None`` and we surface a clean 503 so
    clients can distinguish "no model" from "prediction failed".
    """
    predictor = getattr(request.app.state, PREDICTOR_STATE_KEY, None)
    if predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not loaded — check MLflow connectivity or set ALLOW_DUMMY_MODEL=true for local dev.",
        )
    return predictor


def get_loaded_model(request: Request) -> LoadedModel:
    """Return the underlying :class:`LoadedModel` or raise 503."""
    predictor = get_predictor(request)
    return predictor.loaded_model


def set_predictor(request_app: object, predictor: FraudPredictor | None) -> None:
    """Attach (or clear) the predictor on ``app.state``.

    Used by the lifespan hook and by tests. Accepts ``object`` so it can be
    called with both a ``FastAPI`` instance and a ``Starlette`` test app.
    """
    state = request_app.state  # type: ignore[attr-defined]
    setattr(state, PREDICTOR_STATE_KEY, predictor)


def fail_if_model_not_loaded(predictor: FraudPredictor | None) -> None:
    """Helper for non-router code paths that need the same 503 semantics."""
    if predictor is None:
        raise ModelNotLoadedError("predictor is not initialised")


def verify_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> str:
    """Reject requests without a valid ``X-API-Key`` header (admin routes).

    Returns the (validated) key so handlers can log a hashed prefix if
    they want — they MUST NOT log the raw value. ``constant_time``-ish
    string comparison via ``hmac.compare_digest`` defends against the
    pathological timing oracle the FastAPI examples gloss over.
    """
    import hmac

    settings = get_settings()
    expected = settings.API_KEY or ""
    presented = x_api_key or ""
    if not expected:
        # Misconfiguration — we refuse to allow admin access when the
        # operator left ``API_KEY`` empty. Surfacing a 503 makes the
        # cause discoverable in dev without leaking what's expected.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key is not configured.",
        )
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key.",
        )
    return presented


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields one :class:`AsyncSession` per request.

    The session is closed when the request completes. The dependency does
    NOT commit on exit — the repository layer commits inside ``create_log``
    so callers can mix multiple writes inside a single request boundary
    later without us double-committing.

    Tests override this dependency via ``app.dependency_overrides`` to
    point at a SQLite in-memory session.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
