from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    STRUCTURE_EPOCH,
    Category,
    CategoryMonthExclusion,
    Section,
    SectionMonthExclusion,
)
from ..utils import month_floor


def structure_month(value: date) -> date:
    """Normalize and validate a month used by structure availability."""
    month = month_floor(value)
    if month < STRUCTURE_EPOCH:
        raise ValueError(f"Budget structure months cannot be earlier than {STRUCTURE_EPOCH.isoformat()[:7]}")
    return month


def lifetime_active(item: Section | Category, month: date) -> bool:
    month = month_floor(month)
    if item.archived_at is not None:
        return False
    if month < item.starts_month:
        return False
    return item.ends_before_month is None or month < item.ends_before_month


def deleted_in_month(item: Section | Category, month: date) -> bool:
    month = month_floor(month)
    return item.deleted_from_month is not None and month >= item.deleted_from_month


def visibility_reason(item: Section | Category, month: date, *, excluded: bool = False) -> str | None:
    month = month_floor(month)
    if deleted_in_month(item, month):
        return "deleted"
    if item.archived_at is not None:
        return "archived"
    if month < item.starts_month:
        return "not_started"
    if item.ends_before_month is not None and month >= item.ends_before_month:
        return "ended"
    if excluded:
        return "hidden_this_month"
    return None


def availability_dict(item: Section | Category) -> dict[str, Any]:
    return {
        "starts_month": item.starts_month.isoformat()[:7],
        "ends_before_month": item.ends_before_month.isoformat()[:7] if item.ends_before_month else None,
        "deleted_from_month": item.deleted_from_month.isoformat()[:7] if item.deleted_from_month else None,
    }


def month_exclusion_ids(
    db: Session,
    month: date,
    *,
    section_ids: set[uuid.UUID] | None = None,
    category_ids: set[uuid.UUID] | None = None,
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    month = month_floor(month)
    excluded_sections: set[uuid.UUID] = set()
    excluded_categories: set[uuid.UUID] = set()
    if section_ids:
        excluded_sections = set(
            db.scalars(
                select(SectionMonthExclusion.section_id).where(
                    SectionMonthExclusion.month == month,
                    SectionMonthExclusion.section_id.in_(section_ids),
                )
            ).all()
        )
    if category_ids:
        excluded_categories = set(
            db.scalars(
                select(CategoryMonthExclusion.category_id).where(
                    CategoryMonthExclusion.month == month,
                    CategoryMonthExclusion.category_id.in_(category_ids),
                )
            ).all()
        )
    return excluded_sections, excluded_categories


def section_visible_in_month(db: Session, section: Section, month: date) -> bool:
    if not lifetime_active(section, month):
        return False
    return (
        db.scalar(
            select(SectionMonthExclusion.id).where(
                SectionMonthExclusion.section_id == section.id,
                SectionMonthExclusion.month == month_floor(month),
            ).limit(1)
        )
        is None
    )


def category_visible_in_month(db: Session, category: Category, month: date) -> bool:
    if not lifetime_active(category, month):
        return False
    if not lifetime_active(category.section, month):
        return False
    month = month_floor(month)
    if db.scalar(
        select(SectionMonthExclusion.id).where(
            SectionMonthExclusion.section_id == category.section_id,
            SectionMonthExclusion.month == month,
        ).limit(1)
    ):
        return False
    return (
        db.scalar(
            select(CategoryMonthExclusion.id).where(
                CategoryMonthExclusion.category_id == category.id,
                CategoryMonthExclusion.month == month,
            ).limit(1)
        )
        is None
    )
