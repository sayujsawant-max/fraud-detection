"""Database layer for the FraudShield backend.

The package wires together the SQLAlchemy 2.0 declarative base, the async
engine + session factory, and the per-table ORM models. Routers should not
import from this package directly — they go through
``src.db.repositories`` so the data-access layer stays swappable for tests.
"""

from src.db.base import Base
from src.db.session import (
    AsyncSessionLocal,
    dispose_engine,
    get_engine,
    get_sessionmaker,
)

__all__ = [
    "AsyncSessionLocal",
    "Base",
    "dispose_engine",
    "get_engine",
    "get_sessionmaker",
]
