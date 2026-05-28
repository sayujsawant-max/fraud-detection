"""Phase 4 — create prediction_logs table.

Revision ID: phase_4_create_prediction_logs
Revises:
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers used by Alembic.
revision: str = "phase_4_create_prediction_logs"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``prediction_logs`` audit table + supporting indexes."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # JSONB on Postgres so we can run drift queries against the column.
    # Plain JSON on every other backend so the SQLite test fixture works.
    input_features_type = postgresql.JSONB() if is_postgres else sa.JSON()
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(length=36)

    op.create_table(
        "prediction_logs",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("transaction_id", sa.String(length=128), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("input_features", input_features_type, nullable=False),
        sa.Column("fraud_probability", sa.Float(), nullable=False),
        sa.Column("predicted_label", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("model_stage", sa.String(length=64), nullable=True),
        sa.Column("optimal_threshold", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index(
        "ix_prediction_logs_transaction_id",
        "prediction_logs",
        ["transaction_id"],
    )
    op.create_index(
        "ix_prediction_logs_timestamp",
        "prediction_logs",
        ["timestamp"],
    )
    op.create_index(
        "ix_prediction_logs_timestamp_desc",
        "prediction_logs",
        ["timestamp"],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_prediction_logs_predicted_label",
        "prediction_logs",
        ["predicted_label"],
    )


def downgrade() -> None:
    """Drop the indexes and the ``prediction_logs`` table."""
    op.drop_index("ix_prediction_logs_predicted_label", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_timestamp_desc", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_timestamp", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_transaction_id", table_name="prediction_logs")
    op.drop_table("prediction_logs")
