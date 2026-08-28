"""Add month-specific section and category availability.

Revision ID: 0002_month_specific_structure
Revises: 0001_initial
Create Date: 2026-08-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_month_specific_structure"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

EPOCH_SQL = "'1900-01-01'"


def _inspector():
    return sa.inspect(op.get_bind())


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _check_names(table: str) -> set[str]:
    return {constraint.get("name") for constraint in _inspector().get_check_constraints(table)}


def _has_check(table: str, logical_name: str, names: set[str] | None = None) -> bool:
    # SQLAlchemy's metadata naming convention prefixes explicit logical names
    # with ck_<table>_. Existing installations created by Alembic may expose
    # either form depending on how the constraint was introduced.
    names = names if names is not None else _check_names(table)
    return logical_name in names or f"ck_{table}_{logical_name}" in names


def _index_names(table: str) -> set[str]:
    return {index.get("name") for index in _inspector().get_indexes(table)}


def _add_lifetime_columns(table: str, prefix: str) -> None:
    columns = _column_names(table)
    if "starts_month" not in columns:
        op.add_column(table, sa.Column("starts_month", sa.Date(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET starts_month = {EPOCH_SQL} WHERE starts_month IS NULL"))
        op.alter_column(
            table,
            "starts_month",
            existing_type=sa.Date(),
            nullable=False,
            server_default=sa.text(EPOCH_SQL),
        )
    if "ends_before_month" not in columns:
        op.add_column(table, sa.Column("ends_before_month", sa.Date(), nullable=True))

    checks = _check_names(table)
    starts_name = f"{prefix}_starts_month_first_day"
    ends_name = f"{prefix}_ends_month_first_day"
    range_name = f"{prefix}_month_range_valid"
    if not _has_check(table, starts_name, checks):
        op.create_check_constraint(starts_name, table, "date_part('day', starts_month) = 1")
    if not _has_check(table, ends_name, checks):
        op.create_check_constraint(
            ends_name,
            table,
            "ends_before_month IS NULL OR date_part('day', ends_before_month) = 1",
        )
    if not _has_check(table, range_name, checks):
        op.create_check_constraint(
            range_name,
            table,
            "ends_before_month IS NULL OR ends_before_month >= starts_month",
        )


def upgrade() -> None:
    tables = set(_inspector().get_table_names())
    _add_lifetime_columns("sections", "section")
    _add_lifetime_columns("categories", "category")

    section_indexes = _index_names("sections")
    if "ix_sections_workspace_lifetime" not in section_indexes:
        op.create_index(
            "ix_sections_workspace_lifetime",
            "sections",
            ["workspace_id", "starts_month", "ends_before_month"],
        )
    category_indexes = _index_names("categories")
    if "ix_categories_section_lifetime" not in category_indexes:
        op.create_index(
            "ix_categories_section_lifetime",
            "categories",
            ["section_id", "starts_month", "ends_before_month"],
        )

    if "section_month_exclusions" not in tables:
        op.create_table(
            "section_month_exclusions",
            sa.Column("section_id", sa.Uuid(), nullable=False),
            sa.Column("month", sa.Date(), nullable=False),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("date_part('day', month) = 1", name="section_exclusion_month_first_day"),
            sa.ForeignKeyConstraint(["section_id"], ["sections.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("section_id", "month", name="uq_section_month_exclusion"),
        )
        op.create_index(
            "ix_section_month_exclusions_month",
            "section_month_exclusions",
            ["month", "section_id"],
        )

    if "category_month_exclusions" not in tables:
        op.create_table(
            "category_month_exclusions",
            sa.Column("category_id", sa.Uuid(), nullable=False),
            sa.Column("month", sa.Date(), nullable=False),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("date_part('day', month) = 1", name="category_exclusion_month_first_day"),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("category_id", "month", name="uq_category_month_exclusion"),
        )
        op.create_index(
            "ix_category_month_exclusions_month",
            "category_month_exclusions",
            ["month", "category_id"],
        )


def downgrade() -> None:
    tables = set(_inspector().get_table_names())
    if "category_month_exclusions" in tables:
        op.drop_table("category_month_exclusions")
    if "section_month_exclusions" in tables:
        op.drop_table("section_month_exclusions")

    if "ix_categories_section_lifetime" in _index_names("categories"):
        op.drop_index("ix_categories_section_lifetime", table_name="categories")
    if "ix_sections_workspace_lifetime" in _index_names("sections"):
        op.drop_index("ix_sections_workspace_lifetime", table_name="sections")

    for table, prefix in (("categories", "category"), ("sections", "section")):
        checks = _check_names(table)
        for name in (
            f"{prefix}_month_range_valid",
            f"{prefix}_ends_month_first_day",
            f"{prefix}_starts_month_first_day",
        ):
            if _has_check(table, name, checks):
                actual_name = name if name in checks else f"ck_{table}_{name}"
                op.drop_constraint(actual_name, table, type_="check")
        columns = _column_names(table)
        if "ends_before_month" in columns:
            op.drop_column(table, "ends_before_month")
        if "starts_month" in columns:
            op.drop_column(table, "starts_month")
