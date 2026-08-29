"""Add configurable account balance alerts.

Revision ID: 0004_balance_alerts
Revises: 0003_duplicate_accounts
Create Date: 2026-08-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_balance_alerts"
down_revision = "0003_duplicate_accounts"
branch_labels = None
depends_on = None
CHANNELS_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "balance_alerts" not in inspector.get_table_names():
        op.create_table(
            "balance_alerts",
            sa.Column("workspace_id", sa.Uuid(), nullable=False),
            sa.Column("account_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("comparison", sa.String(length=12), nullable=False),
            sa.Column("threshold", sa.Numeric(precision=20, scale=4), nullable=False),
            sa.Column("channels", CHANNELS_TYPE, server_default="[]", nullable=False),
            sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_by_id", sa.Uuid(), nullable=True),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("version", sa.Integer(), server_default="1", nullable=False),
            sa.CheckConstraint(
                "comparison IN ('below', 'above')",
                name=op.f("ck_balance_alerts_balance_alert_comparison_valid"),
            ),
            sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("balance_alerts")}
    if "ix_balance_alerts_workspace_enabled" not in index_names:
        op.create_index("ix_balance_alerts_workspace_enabled", "balance_alerts", ["workspace_id", "enabled"])
    if "ix_balance_alerts_workspace_account_enabled" not in index_names:
        op.create_index(
            "ix_balance_alerts_workspace_account_enabled",
            "balance_alerts",
            ["workspace_id", "account_id", "enabled"],
        )


def downgrade() -> None:
    if "balance_alerts" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("balance_alerts")
