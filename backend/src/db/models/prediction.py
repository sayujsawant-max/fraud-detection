"""``prediction_logs`` ORM model — one row per scored transaction.

The table is the source-of-truth audit trail for every prediction the API
serves. It powers the ``/v1/logs/*`` endpoints today and the Phase 5
Evidently drift reports later (which read ``input_features`` to compare
against the reference distribution).

Design notes
------------
* ``input_features`` uses PostgreSQL ``JSONB`` in production and falls back
  to plain ``JSON`` on SQLite (used in tests). The
  :class:`JSON` ``with_variant`` call below is the SQLAlchemy idiom for
  per-dialect column types.
* ``timestamp`` defaults to ``now()`` on the server so multi-instance
  deployments do not race the clock between API replicas.
* The primary key is a UUID v4 — easier to use across services than a
  bigserial and avoids ID collisions when drift tooling exports logs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator

from src.db.base import Base


class GUID(TypeDecorator):
    """Platform-agnostic UUID type.

    Stores PostgreSQL ``UUID`` natively where available and falls back to a
    36-char string on SQLite. This is what lets the same ORM model power
    both the production Postgres deployment and the SQLite test fixture.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return (
            str(value) if isinstance(value, uuid.UUID) else str(uuid.UUID(str(value)))
        )

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


# JSON column that prefers JSONB on Postgres and falls back to JSON elsewhere.
# Keeping this in a module constant means migrations and tests share the same
# definition.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class PredictionLog(Base):
    """Audit-trail record for a single prediction served by the API."""

    __tablename__ = "prediction_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    input_features: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    fraud_probability: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_label: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    optimal_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Descending timestamp index — the dashboard and /v1/logs both list
        # most-recent-first, and Postgres can use this directly for an index
        # scan that avoids sorting.
        Index(
            "ix_prediction_logs_timestamp_desc", "timestamp", postgresql_using="btree"
        ),
        Index("ix_prediction_logs_predicted_label", "predicted_label"),
    )

    def __repr__(self) -> str:  # pragma: no cover — debug helper
        return (
            f"PredictionLog(id={self.id} tx={self.transaction_id} "
            f"label={self.predicted_label} prob={self.fraud_probability:.3f})"
        )
