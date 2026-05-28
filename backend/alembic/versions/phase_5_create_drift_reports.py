"""Phase 5 — create drift_reports table.

Revision ID: phase_5_create_drift_reports
Revises: phase_4_create_prediction_logs
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "phase_5_create_drift_reports"
down_revision: str | None = "phase_4_create_prediction_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``drift_reports`` audit table + supporting indexes."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    json_type = postgresql.JSONB() if is_postgres else sa.JSON()
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(length=36)

    op.create_table(
        "drift_reports",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("report_id", sa.String(length=128), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("drift_detected", sa.Boolean(), nullable=False),
        sa.Column("drift_score", sa.Float(), nullable=True),
        sa.Column("num_drifted_features", sa.Integer(), nullable=True),
        sa.Column("total_features", sa.Integer(), nullable=True),
        sa.Column("num_samples", sa.Integer(), nullable=False),
        sa.Column("reference_dataset_path", sa.Text(), nullable=True),
        sa.Column("current_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_html_path", sa.Text(), nullable=True),
        sa.Column("report_json_path", sa.Text(), nullable=True),
        sa.Column("report_json", json_type, nullable=True),
        sa.Column(
            "triggered_retrain",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0") if not is_postgres else sa.text("false"),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="complete",
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("report_id", name="uq_drift_reports_report_id"),
    )

    op.create_index(
        "ix_drift_reports_report_id",
        "drift_reports",
        ["report_id"],
    )
    op.create_index(
        "ix_drift_reports_generated_at",
        "drift_reports",
        ["generated_at"],
    )
    op.create_index(
        "ix_drift_reports_generated_at_desc",
        "drift_reports",
        ["generated_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_drift_reports_drift_detected",
        "drift_reports",
        ["drift_detected"],
    )


def downgrade() -> None:
    """Drop indexes and the ``drift_reports`` table."""
    op.drop_index("ix_drift_reports_drift_detected", table_name="drift_reports")
    op.drop_index("ix_drift_reports_generated_at_desc", table_name="drift_reports")
    op.drop_index("ix_drift_reports_generated_at", table_name="drift_reports")
    op.drop_index("ix_drift_reports_report_id", table_name="drift_reports")
    op.drop_table("drift_reports")
