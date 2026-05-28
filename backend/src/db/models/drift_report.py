"""``drift_reports`` ORM model — one row per Evidently drift run.

The row is the durable record of a drift computation: when it ran, which
reference dataset, which window of prediction logs, the headline metrics,
and the filesystem paths to the HTML/JSON artifacts. The Phase 6 Prefect
flow will write one row per scheduled tick, and Phase 7 will render them
in the frontend monitoring page.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.db.models.prediction import GUID, JSONType


class DriftReport(Base):
    """One drift-detection run."""

    __tablename__ = "drift_reports"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # Human-readable, filename-safe id (e.g. ``drift_20260528_143000_123456``).
    # Used as the basename for the HTML/JSON artifacts on disk so the API can
    # resolve files from the id alone.
    report_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    drift_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    drift_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    num_drifted_features: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_features: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_dataset_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    report_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full Evidently JSON kept inline as well so we can render summaries
    # without re-reading the artifact file. Optional because large reports
    # may be cheaper to keep only on disk.
    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    triggered_retrain: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # ``complete`` | ``skipped`` | ``failed`` — keeps the timeline intact for
    # runs that produced no Evidently artifact (e.g. insufficient samples).
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="complete", server_default="complete"
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_drift_reports_generated_at_desc",
            "generated_at",
            postgresql_using="btree",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover — debug helper
        return (
            f"DriftReport(id={self.id} report_id={self.report_id} "
            f"score={self.drift_score} detected={self.drift_detected})"
        )
