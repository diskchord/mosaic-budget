"""Add reversible duplicate-account transaction suppression.

Revision ID: 0003_duplicate_accounts
Revises: 0002_month_specific_structure
Create Date: 2026-08-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_duplicate_accounts"
down_revision = "0002_month_specific_structure"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    account_columns = _column_names("accounts")
    if "is_duplicate" not in account_columns:
        op.add_column(
            "accounts",
            sa.Column("is_duplicate", sa.Boolean(), server_default=sa.false(), nullable=False),
        )

    transaction_columns = _column_names("budget_transactions")
    if "suppressed_by_duplicate_account" not in transaction_columns:
        op.add_column(
            "budget_transactions",
            sa.Column(
                "suppressed_by_duplicate_account",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    transaction_columns = _column_names("budget_transactions")
    if "suppressed_by_duplicate_account" in transaction_columns:
        op.drop_column("budget_transactions", "suppressed_by_duplicate_account")

    account_columns = _column_names("accounts")
    if "is_duplicate" in account_columns:
        op.drop_column("accounts", "is_duplicate")
