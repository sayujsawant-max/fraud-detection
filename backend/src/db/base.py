"""SQLAlchemy declarative base and shared metadata.

All ORM models inherit from :class:`Base` so Alembic autogenerate and
``Base.metadata.create_all`` (used by the SQLite test fixture) see the same
table set. Keeping the base in its own module avoids the circular-import
trap where models import the engine and the engine imports the models.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base for all SQLAlchemy ORM models."""

    # Subclasses set ``__tablename__`` explicitly. We do not derive it from
    # the class name because we want migration files to read naturally
    # (``prediction_logs``, not ``predictionlog``).
