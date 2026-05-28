"""Async SQLAlchemy engine and session factory.

The engine is lazily constructed on first use so importing this module does
not fire a network call. ``get_sessionmaker()`` returns a process-wide
:class:`async_sessionmaker` bound to the configured ``DATABASE_URL`` (in
its async form — see :mod:`src.core.config`).

Tests override ``AsyncSessionLocal`` via the FastAPI dependency-injection
``app.dependency_overrides`` mechanism rather than mutating module state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import Settings, get_settings

# Module-level singletons. They are populated lazily so unit tests that do
# not touch the database never open a connection. ``AsyncSessionLocal`` is
# the public name routers/repositories import.
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _build_engine(settings: Settings) -> AsyncEngine:
    """Construct the async SQLAlchemy engine from settings.

    SQLite uses a different connect-args shape (``check_same_thread``) and
    does not understand pool sizing, so we branch on the URL scheme. This
    is also what lets the in-memory SQLite test fixture share a connection
    across coroutines.
    """
    url = settings.database_url_async
    engine_kwargs: dict[str, Any] = {"echo": settings.DB_ECHO, "future": True}
    if url.startswith("sqlite"):
        # SQLite (async via aiosqlite) — no pool sizing, single connection.
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
        engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
        engine_kwargs["pool_pre_ping"] = True

    logger.debug("creating async SQLAlchemy engine | url={}", _safe_url(url))
    return create_async_engine(url, **engine_kwargs)


def _safe_url(url: str) -> str:
    """Redact credentials so the URL is safe to log."""
    if "@" not in url:
        return url
    scheme_creds, host_path = url.split("@", 1)
    if "://" not in scheme_creds:
        return url
    scheme, _ = scheme_creds.split("://", 1)
    return f"{scheme}://***@{host_path}"


def get_engine() -> AsyncEngine:
    """Return the process-wide :class:`AsyncEngine`, building it on first use."""
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings())
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide :class:`async_sessionmaker`."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def AsyncSessionLocal() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an ``AsyncSession`` per request.

    Wrapping the session in ``async with`` ensures the connection is
    released back to the pool even if the request handler raises. The
    repository layer commits explicitly; this dependency does NOT commit on
    exit so router code keeps full control of transaction boundaries.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close the engine and drop the cached sessionmaker.

    Used by the FastAPI lifespan shutdown hook and by tests that need to
    rebuild the engine between cases.
    """
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
