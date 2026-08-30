from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    STRUCTURE_EPOCH,
    Category,
    CategoryBudget,
    CategoryMonthExclusion,
    Section,
    SectionMonthExclusion,
)
from ..schemas import (
    BudgetAmountRequest,
    CategoryCreateRequest,
    CategoryUpdateRequest,
    SectionCreateRequest,
    SectionUpdateRequest,
    StructureVisibilityRequest,
)
from ..services.audit import write_audit
from ..services.budgets import ensure_month_records, get_budget_state
from ..services.structure import (
    availability_dict,
    category_visible_in_month,
    lifetime_active,
    structure_month,
)
from ..utils import money_str, next_month, parse_decimal, parse_month, utcnow
from .deps import AuthContext, current_auth, require_write

router = APIRouter(prefix="/api", tags=["budget"])


def section_dict(section: Section) -> dict:
    return {
        "id": str(section.id),
        "name": section.name,
        "icon": section.icon,
        "accent": section.accent,
        "sort_order": section.sort_order,
        "is_income": section.is_income,
        **availability_dict(section),
        "archived_at": section.archived_at.isoformat() if section.archived_at else None,
        "version": section.version,
    }


def category_dict(category: Category) -> dict:
    return {
        "id": str(category.id),
        "section_id": str(category.section_id),
        "name": category.name,
        "sort_order": category.sort_order,
        "rollover": category.rollover,
        "default_planned": money_str(category.default_planned),
        "note": category.note,
        **availability_dict(category),
        "archived_at": category.archived_at.isoformat() if category.archived_at else None,
        "version": category.version,
    }


def _section_for_user(db: Session, section_id: uuid.UUID, workspace_id: uuid.UUID, *, lock: bool = False) -> Section:
    query = select(Section).where(Section.id == section_id, Section.workspace_id == workspace_id)
    if lock:
        query = query.with_for_update()
    section = db.scalar(query)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


def _category_for_user(db: Session, category_id: uuid.UUID, workspace_id: uuid.UUID, *, lock: bool = False) -> Category:
    query = select(Category).join(Section).where(Category.id == category_id, Section.workspace_id == workspace_id)
    if lock:
        query = query.with_for_update()
    category = db.scalar(query)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def _reorder_sections(
    db: Session,
    workspace_id: uuid.UUID,
    moving: Section | None = None,
    target_index: int | None = None,
) -> None:
    rows = db.scalars(
        select(Section)
        .where(
            Section.workspace_id == workspace_id,
            Section.is_income.is_(False),
            Section.archived_at.is_(None),
        )
        .order_by(Section.sort_order, Section.name)
        .with_for_update()
    ).all()
    ordered = [row for row in rows if moving is None or row.id != moving.id]
    if moving is not None and moving.archived_at is None:
        index = len(ordered) if target_index is None else max(0, min(int(target_index), len(ordered)))
        ordered.insert(index, moving)
    for index, row in enumerate(ordered, start=1):
        if row.sort_order != index:
            row.sort_order = index
            if moving is None or row.id != moving.id:
                row.version += 1


def _reorder_categories(
    db: Session,
    section_id: uuid.UUID,
    moving: Category | None = None,
    target_index: int | None = None,
) -> None:
    rows = db.scalars(
        select(Category)
        .where(Category.section_id == section_id, Category.archived_at.is_(None))
        .order_by(Category.sort_order, Category.name)
        .with_for_update()
    ).all()
    ordered = [row for row in rows if moving is None or row.id != moving.id]
    if moving is not None and moving.archived_at is None and moving.section_id == section_id:
        index = len(ordered) if target_index is None else max(0, min(int(target_index), len(ordered)))
        ordered.insert(index, moving)
    for index, row in enumerate(ordered):
        if row.sort_order != index:
            row.sort_order = index
            if moving is None or row.id != moving.id:
                row.version += 1


def _change_visibility(
    db: Session,
    *,
    target: Section | Category,
    payload: StructureVisibilityRequest,
    exclusion_model,
    target_column,
) -> bool:
    try:
        month = structure_month(payload.month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if isinstance(target, Section) and target.is_income and not payload.visible:
        raise HTTPException(status_code=400, detail="The Income section is protected and must exist in every month")

    changed = False
    target_id = target.id

    if payload.visible:
        if payload.scope == "month":
            if not lifetime_active(target, month):
                raise HTTPException(
                    status_code=400,
                    detail="This item is outside its month range. Restore it from this month forward instead.",
                )
            result = db.execute(
                delete(exclusion_model).where(target_column == target_id, exclusion_model.month == month)
            )
            changed = bool(result.rowcount)
        elif payload.scope == "forward":
            if target.archived_at is not None:
                raise HTTPException(
                    status_code=400,
                    detail="An item archived in every month must be restored to all months before changing its range.",
                )
            if month < target.starts_month:
                target.starts_month = month
                changed = True
            old_end = target.ends_before_month
            if old_end is not None and month >= old_end:
                # Preserve the finite gap between the former end and the new
                # resumption month as explicit one-month exclusions.
                gap_months = []
                cursor = old_end
                while cursor < month:
                    gap_months.append(cursor)
                    cursor = next_month(cursor)
                existing_gap = set(
                    db.scalars(
                        select(exclusion_model.month).where(
                            target_column == target_id,
                            exclusion_model.month.in_(gap_months),
                        )
                    ).all()
                ) if gap_months else set()
                for gap_month in gap_months:
                    if gap_month not in existing_gap:
                        db.add(exclusion_model(**{target_column.key: target_id, "month": gap_month}))
                        changed = True
                target.ends_before_month = None
                changed = True
            result = db.execute(
                delete(exclusion_model).where(target_column == target_id, exclusion_model.month >= month)
            )
            changed = bool(result.rowcount) or changed
        else:  # all
            if target.archived_at is not None:
                target.archived_at = None
                changed = True
            if target.starts_month != STRUCTURE_EPOCH:
                target.starts_month = STRUCTURE_EPOCH
                changed = True
            if target.ends_before_month is not None:
                target.ends_before_month = None
                changed = True
            result = db.execute(delete(exclusion_model).where(target_column == target_id))
            changed = bool(result.rowcount) or changed
    else:
        if payload.scope == "month":
            if not lifetime_active(target, month):
                return False
            existing = db.scalar(
                select(exclusion_model.id).where(target_column == target_id, exclusion_model.month == month)
            )
            if existing is None:
                db.add(exclusion_model(**{target_column.key: target_id, "month": month}))
                changed = True
        elif payload.scope == "forward":
            # The exclusive boundary can equal starts_month, representing an item
            # retained for history but not visible in any current/future month.
            boundary = max(month, target.starts_month)
            if target.ends_before_month is None or boundary < target.ends_before_month:
                target.ends_before_month = boundary
                changed = True
            result = db.execute(
                delete(exclusion_model).where(target_column == target_id, exclusion_model.month >= month)
            )
            changed = bool(result.rowcount) or changed
        else:  # all
            if target.archived_at is None:
                target.archived_at = utcnow()
                changed = True

    return changed


@router.get("/budget")
def budget_state(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_db),
) -> dict:
    try:
        month_date = parse_month(month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ensure_month_records(db, auth.user.workspace_id, month_date)
    db.commit()
    return get_budget_state(db, auth.user.workspace_id, month_date)


@router.post("/sections")
def create_section(
    payload: SectionCreateRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    try:
        starts_month = structure_month(payload.starts_month or STRUCTURE_EPOCH)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    section = Section(
        workspace_id=auth.user.workspace_id,
        name=payload.name.strip(),
        icon=payload.icon,
        accent=payload.accent,
        sort_order=0,
        is_income=False,
        starts_month=starts_month,
    )
    db.add(section)
    db.flush()
    _reorder_sections(db, auth.user.workspace_id, section, payload.sort_order)
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="section.created",
        object_type="section",
        object_id=section.id,
        after=section_dict(section),
    )
    db.commit()
    return {"section": section_dict(section)}


@router.patch("/sections/{section_id}")
def update_section(
    section_id: uuid.UUID,
    payload: SectionUpdateRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    section = _section_for_user(db, section_id, auth.user.workspace_id, lock=True)
    if section.version != payload.version:
        raise HTTPException(
            status_code=409,
            detail={"message": "This section changed on another device.", "current": section_dict(section)},
        )
    before = section_dict(section)
    if payload.name is not None:
        section.name = payload.name.strip()
    if payload.icon is not None:
        section.icon = payload.icon
    if payload.accent is not None:
        section.accent = payload.accent
    if payload.sort_order is not None and not section.is_income:
        _reorder_sections(db, auth.user.workspace_id, section, payload.sort_order)
    section.version += 1
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="section.updated",
        object_type="section",
        object_id=section.id,
        before=before,
        after=section_dict(section),
    )
    db.commit()
    return {"section": section_dict(section)}


@router.put("/sections/{section_id}/visibility")
def set_section_visibility(
    section_id: uuid.UUID,
    payload: StructureVisibilityRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    section = _section_for_user(db, section_id, auth.user.workspace_id, lock=True)
    if section.version != payload.version:
        raise HTTPException(status_code=409, detail={"message": "Section conflict", "current": section_dict(section)})
    before = section_dict(section)
    changed = _change_visibility(
        db,
        target=section,
        payload=payload,
        exclusion_model=SectionMonthExclusion,
        target_column=SectionMonthExclusion.section_id,
    )
    if changed:
        section.version += 1
        write_audit(
            db,
            workspace_id=auth.user.workspace_id,
            actor_user_id=auth.user.id,
            action="section.visibility.updated",
            object_type="section",
            object_id=section.id,
            before=before,
            after=section_dict(section),
            detail={"month": payload.month.isoformat()[:7], "visible": payload.visible, "scope": payload.scope},
        )
    db.commit()
    return {"section": section_dict(section), "changed": changed}


@router.delete("/sections/{section_id}")
def archive_section(
    section_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    section = _section_for_user(db, section_id, auth.user.workspace_id, lock=True)
    if section.is_income:
        raise HTTPException(status_code=400, detail="The Income section is protected and cannot be removed")
    if section.version != version:
        raise HTTPException(status_code=409, detail={"message": "Section conflict", "current": section_dict(section)})
    before = section_dict(section)
    section.archived_at = utcnow()
    section.version += 1
    _reorder_sections(db, auth.user.workspace_id)
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="section.archived",
        object_type="section",
        object_id=section.id,
        before=before,
        after=section_dict(section),
    )
    db.commit()
    return {"ok": True}


@router.post("/categories")
def create_category(
    payload: CategoryCreateRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    section = _section_for_user(db, payload.section_id, auth.user.workspace_id)
    if section.archived_at:
        raise HTTPException(status_code=400, detail="Cannot add a category to an archived section")
    try:
        default_planned = parse_decimal(payload.default_planned)
        starts_month = structure_month(payload.starts_month or STRUCTURE_EPOCH)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if default_planned < 0:
        raise HTTPException(status_code=400, detail="Planned amounts cannot be negative")
    category = Category(
        section_id=section.id,
        name=payload.name.strip(),
        sort_order=0,
        rollover=payload.rollover and not section.is_income,
        default_planned=default_planned,
        note=payload.note,
        starts_month=starts_month,
    )
    db.add(category)
    db.flush()
    _reorder_categories(db, section.id, category, payload.sort_order)
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="category.created",
        object_type="category",
        object_id=category.id,
        after=category_dict(category),
    )
    db.commit()
    return {"category": category_dict(category)}


@router.patch("/categories/{category_id}")
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdateRequest,
    current_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    try:
        current_month_date = parse_month(current_month) if current_month else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    category = _category_for_user(db, category_id, auth.user.workspace_id, lock=True)
    if category.version != payload.version:
        raise HTTPException(
            status_code=409,
            detail={"message": "This category changed on another device.", "current": category_dict(category)},
        )
    before = category_dict(category)
    original_section_id = category.section_id
    target_section = category.section
    moving_sections = payload.section_id is not None and payload.section_id != category.section_id
    if moving_sections:
        target_section = _section_for_user(db, payload.section_id, auth.user.workspace_id)
        if target_section.archived_at:
            raise HTTPException(status_code=400, detail="Cannot move a category into an archived section")
        category.section_id = target_section.id
        _reorder_categories(db, original_section_id)
        _reorder_categories(db, target_section.id, category, payload.sort_order)
    elif payload.sort_order is not None:
        _reorder_categories(db, category.section_id, category, payload.sort_order)
    if payload.name is not None:
        category.name = payload.name.strip()
    if payload.rollover is not None:
        category.rollover = payload.rollover and not target_section.is_income
    if payload.default_planned is not None:
        try:
            amount = parse_decimal(payload.default_planned)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if amount < 0:
            raise HTTPException(status_code=400, detail="Planned amounts cannot be negative")
        default_changed = amount != category.default_planned
        category.default_planned = amount
        if default_changed and amount > 0 and current_month_date is not None:
            budget = db.scalar(
                select(CategoryBudget)
                .where(
                    CategoryBudget.workspace_id == auth.user.workspace_id,
                    CategoryBudget.month == current_month_date,
                    CategoryBudget.category_id == category.id,
                )
                .with_for_update()
            )
            if budget is not None and budget.planned == 0:
                budget_before = {"planned": money_str(budget.planned), "version": budget.version}
                budget.planned = amount
                budget.version += 1
                write_audit(
                    db,
                    workspace_id=auth.user.workspace_id,
                    actor_user_id=auth.user.id,
                    action="budget.amount.updated",
                    object_type="category_budget",
                    object_id=budget.id,
                    before=budget_before,
                    after={
                        "month": current_month,
                        "category_id": str(category.id),
                        "planned": money_str(budget.planned),
                        "version": budget.version,
                    },
                )
    if payload.note is not None:
        category.note = payload.note
    category.version += 1
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="category.updated",
        object_type="category",
        object_id=category.id,
        before=before,
        after=category_dict(category),
    )
    db.commit()
    return {"category": category_dict(category)}


@router.put("/categories/{category_id}/visibility")
def set_category_visibility(
    category_id: uuid.UUID,
    payload: StructureVisibilityRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    category = _category_for_user(db, category_id, auth.user.workspace_id, lock=True)
    if category.version != payload.version:
        raise HTTPException(status_code=409, detail={"message": "Category conflict", "current": category_dict(category)})
    before = category_dict(category)
    changed = _change_visibility(
        db,
        target=category,
        payload=payload,
        exclusion_model=CategoryMonthExclusion,
        target_column=CategoryMonthExclusion.category_id,
    )
    if changed:
        category.version += 1
        write_audit(
            db,
            workspace_id=auth.user.workspace_id,
            actor_user_id=auth.user.id,
            action="category.visibility.updated",
            object_type="category",
            object_id=category.id,
            before=before,
            after=category_dict(category),
            detail={"month": payload.month.isoformat()[:7], "visible": payload.visible, "scope": payload.scope},
        )
    db.commit()
    return {"category": category_dict(category), "changed": changed}


@router.delete("/categories/{category_id}")
def archive_category(
    category_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    category = _category_for_user(db, category_id, auth.user.workspace_id, lock=True)
    if category.version != version:
        raise HTTPException(status_code=409, detail={"message": "Category conflict", "current": category_dict(category)})
    before = category_dict(category)
    category.archived_at = utcnow()
    category.version += 1
    _reorder_categories(db, category.section_id)
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="category.archived",
        object_type="category",
        object_id=category.id,
        before=before,
        after=category_dict(category),
    )
    db.commit()
    return {"ok": True}


@router.put("/budget/{month}/categories/{category_id}")
def set_budget_amount(
    month: str,
    category_id: uuid.UUID,
    payload: BudgetAmountRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    try:
        month_date = parse_month(month)
        planned = parse_decimal(payload.planned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if planned < 0:
        raise HTTPException(status_code=400, detail="Planned amounts cannot be negative")
    category = _category_for_user(db, category_id, auth.user.workspace_id)
    if not category_visible_in_month(db, category, month_date):
        raise HTTPException(status_code=400, detail="This category is not available in the selected month")
    row = db.scalar(
        select(CategoryBudget)
        .where(
            CategoryBudget.workspace_id == auth.user.workspace_id,
            CategoryBudget.month == month_date,
            CategoryBudget.category_id == category.id,
        )
        .with_for_update()
    )
    if row is None:
        if payload.version != 0:
            raise HTTPException(status_code=409, detail={"message": "Budget line no longer exists", "current": None})
        row = CategoryBudget(
            workspace_id=auth.user.workspace_id,
            month=month_date,
            category_id=category.id,
            planned=planned,
        )
        db.add(row)
        db.flush()
        before = None
    else:
        if row.version != payload.version:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This budget amount changed on another device.",
                    "current": {"planned": money_str(row.planned), "version": row.version},
                },
            )
        before = {"planned": money_str(row.planned), "version": row.version}
        row.planned = planned
        row.version += 1
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="budget.amount.updated",
        object_type="category_budget",
        object_id=row.id,
        before=before,
        after={"month": month, "category_id": str(category.id), "planned": money_str(row.planned), "version": row.version},
    )
    db.commit()
    return {"planned": money_str(row.planned), "version": row.version}
