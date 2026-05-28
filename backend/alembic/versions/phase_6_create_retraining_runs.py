"""Phase 6 — create retraining_runs table.

Revision ID: phase_6_create_retraining_runs
Revises: phase_5_create_drift_reports
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "phase_6_create_retraining_runs"
down_revision: Union[str, None] = "phase_5_create_drift_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``retraining_runs`` audit table + supporting indexes."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(length=36)
    promoted_default = sa.text("false") if is_postgres else sa.text("0")

    op.create_table(
        "retraining_runs",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("trigger_reason", sa.String(length=32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="running",
        ),
        sa.Column("challenger_run_id", sa.String(length=128), nullable=True),
        sa.Column("challenger_model_uri", sa.Text(), nullable=True),
        sa.Column("challenger_model_version", sa.String(length=64), nullable=True),
        sa.Column("challenger_pr_auc", sa.Float(), nullable=True),
        sa.Column("champion_pr_auc", sa.Float(), nullable=True),
        sa.Column(
            "promoted",
            sa.Boolean(),
            nullable=False,
            server_default=promoted_default,
        ),
        sa.Column("api_reload_status", sa.String(length=32), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index(
        "ix_retraining_runs_started_at",
        "retraining_runs",
        ["started_at"],
    )
    op.create_index(
        "ix_retraining_runs_started_at_desc",
        "retraining_runs",
        ["started_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_retraining_runs_status",
        "retraining_runs",
        ["status"],
    )
    op.create_index(
        "ix_retraining_runs_trigger_reason",
        "retraining_runs",
        ["trigger_reason"],
    )


def downgrade() -> None:
    """Drop indexes and the ``retraining_runs`` table."""
    op.drop_index("ix_retraining_runs_trigger_reason", table_name="retraining_runs")
    op.drop_index("ix_retraining_runs_status", table_name="retraining_runs")
    op.drop_index("ix_retraining_runs_started_at_desc", table_name="retraining_runs")
    op.drop_index("ix_retraining_runs_started_at", table_name="retraining_runs")
    op.drop_table("retraining_runs")
