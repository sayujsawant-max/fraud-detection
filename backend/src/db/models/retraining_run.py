"""``retraining_runs`` ORM model — one row per Prefect retraining flow run.

Each retraining flow run (manual, drift-triggered, or scheduled) writes
exactly one row here so the API and Phase 7 dashboard have a durable,
queryable audit trail of every challenger model that was trained and
either promoted or rejected.

The table is deliberately schema-symmetric with :class:`DriftReport`:
filename-safe / lookup-friendly columns first, then the headline metrics,
then large free-text columns last. This keeps the Postgres heap warm for
the common "list latest N" query path.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.db.models.prediction import GUID


class RetrainingRun(Base):
    """One end-to-end retraining flow execution."""

    __tablename__ = "retraining_runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # ``manual`` | ``drift`` | ``scheduled``. Stored as a free string rather
    # than an enum so adding new triggers later doesn't require a migration.
    trigger_reason: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # ``running`` | ``promoted`` | ``rejected`` | ``failed``.
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="running",
        server_default="running",
        index=True,
    )
    challenger_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    challenger_model_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    challenger_model_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    challenger_pr_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    champion_pr_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    promoted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # ``skipped`` | ``reloaded`` | ``failed`` — best-effort signal whether
    # the API hot-reload after promotion succeeded.
    api_reload_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_retraining_runs_started_at_desc",
            "started_at",
            postgresql_using="btree",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover — debug helper
        return (
            f"RetrainingRun(id={self.id} trigger={self.trigger_reason} "
            f"status={self.status} promoted={self.promoted})"
        )
