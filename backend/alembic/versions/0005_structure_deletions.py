"""Add permanent month-forward structure deletion tombstones.

Revision ID: 0005_structure_deletions
Revises: 0004_balance_alerts
Create Date: 2026-08-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_structure_deletions"
down_revision = "0004_balance_alerts"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _check_names(table: str) -> set[str]:
    return {constraint.get("name") for constraint in _inspector().get_check_constraints(table)}


def _has_check(table: str, logical_name: str, names: set[str]) -> bool:
    return logical_name in names or f"ck_{table}_{logical_name}" in names


def upgrade() -> None:
    for table, prefix in (("sections", "section"), ("categories", "category")):
        add_column = "deleted_from_month" not in _column_names(table)
        checks = _check_names(table)
        first_day = f"{prefix}_deleted_month_first_day"
        add_check = not _has_check(table, first_day, checks)
        if not add_column and not add_check:
            continue
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch_op:
                if add_column:
                    batch_op.add_column(sa.Column("deleted_from_month", sa.Date(), nullable=True))
                if add_check:
                    batch_op.create_check_constraint(
                        first_day,
                        "deleted_from_month IS NULL OR date_part('day', deleted_from_month) = 1",
                    )
        else:
            if add_column:
                op.add_column(table, sa.Column("deleted_from_month", sa.Date(), nullable=True))
            if add_check:
                op.create_check_constraint(
                    first_day,
                    table,
                    "deleted_from_month IS NULL OR date_part('day', deleted_from_month) = 1",
                )


def downgrade() -> None:
    for table, prefix in (("categories", "category"), ("sections", "section")):
        checks = _check_names(table)
        logical_name = f"{prefix}_deleted_month_first_day"
        actual_name = None
        if logical_name in checks:
            actual_name = logical_name
        elif _has_check(table, logical_name, checks):
            actual_name = f"ck_{table}_{logical_name}"
        drop_column = "deleted_from_month" in _column_names(table)
        if actual_name is None and not drop_column:
            continue
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch_op:
                if actual_name is not None:
                    batch_op.drop_constraint(op.f(actual_name), type_="check")
                if drop_column:
                    batch_op.drop_column("deleted_from_month")
        else:
            if actual_name is not None:
                op.drop_constraint(actual_name, table, type_="check")
            if drop_column:
                op.drop_column(table, "deleted_from_month")
