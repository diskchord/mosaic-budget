from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, not_, select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    Account,
    Allocation,
    BudgetTransaction,
    Category,
    CategoryBudget,
    CategoryMonthExclusion,
    Section,
    SectionMonthExclusion,
    SimpleFinConnection,
)
from ..utils import money_str, next_month
from .balance_alerts import account_balance_unavailable_reason
from .structure import availability_dict, lifetime_active, month_exclusion_ids, visibility_reason
from .transaction_labels import transaction_display_payee


def ensure_month_records(db: Session, workspace_id: uuid.UUID, month: date) -> None:
    existing = set(
        db.scalars(
            select(CategoryBudget.category_id).where(
                CategoryBudget.workspace_id == workspace_id,
                CategoryBudget.month == month,
            )
        ).all()
    )
    sections = db.scalars(
        select(Section)
        .where(Section.workspace_id == workspace_id, Section.archived_at.is_(None))
        .options(selectinload(Section.categories))
    ).all()
    section_ids = {section.id for section in sections}
    category_ids = {
        category.id
        for section in sections
        for category in section.categories
        if category.archived_at is None
    }
    excluded_sections, excluded_categories = month_exclusion_ids(
        db,
        month,
        section_ids=section_ids,
        category_ids=category_ids,
    )
    for section in sections:
        if visibility_reason(section, month, excluded=section.id in excluded_sections):
            continue
        for category in section.categories:
            if category.archived_at is not None:
                continue
            if visibility_reason(category, month, excluded=category.id in excluded_categories):
                continue
            if category.id not in existing:
                db.add(
                    CategoryBudget(
                        workspace_id=workspace_id,
                        month=month,
                        category_id=category.id,
                        planned=category.default_planned,
                    )
                )


def serialize_account(account: Account) -> dict[str, Any]:
    balance_alert_unavailable_reason = account_balance_unavailable_reason(account)
    return {
        "id": str(account.id),
        "name": account.name,
        "source_type": account.source_type,
        "currency": account.currency,
        "balance": money_str(account.balance),
        "available_balance": money_str(account.available_balance),
        "balance_date": account.balance_date.isoformat() if account.balance_date else None,
        "is_budget": account.is_budget,
        "is_active": account.is_active,
        "is_duplicate": account.is_duplicate,
        "balance_alert_available": balance_alert_unavailable_reason is None,
        "balance_alert_unavailable_reason": balance_alert_unavailable_reason,
        "version": account.version,
    }


def serialize_transaction(transaction: BudgetTransaction, include_allocations: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(transaction.id),
        "account_id": str(transaction.account_id),
        "account_name": transaction.account.name if transaction.account else "",
        "source_kind": transaction.source_kind,
        "effective_date": transaction.effective_date.isoformat(),
        "amount": money_str(transaction.amount),
        "payee": transaction.payee,
        "display_payee": transaction_display_payee(
            transaction.payee,
            source_kind=transaction.source_kind,
            imported_description=transaction.imported_description,
            imported_extra=transaction.imported_extra,
            manual_payee_lock=transaction.manual_payee_lock,
        ),
        "imported_description": transaction.imported_description,
        "note": transaction.note,
        "tags": transaction.tags,
        "pending": transaction.pending,
        "cleared": transaction.cleared,
        "excluded": transaction.excluded,
        "suppressed_by_duplicate_account": transaction.suppressed_by_duplicate_account,
        "needs_review": transaction.needs_review,
        "deleted_at": transaction.deleted_at.isoformat() if transaction.deleted_at else None,
        "version": transaction.version,
        "manual_allocation_lock": transaction.manual_allocation_lock,
    }
    if include_allocations:
        data["allocations"] = [
            {
                "id": str(allocation.id),
                "category_id": str(allocation.category_id),
                "category_name": allocation.category.name if allocation.category else "",
                "section_name": allocation.category.section.name
                if allocation.category and allocation.category.section
                else "",
                "amount": money_str(allocation.amount),
                "memo": allocation.memo,
            }
            for allocation in transaction.allocations
        ]
    return data


def _rollover_planned_totals(
    db: Session,
    workspace_id: uuid.UUID,
    month_end: date,
) -> dict[uuid.UUID, Decimal]:
    rows = db.scalars(
        select(CategoryBudget)
        .join(Category, Category.id == CategoryBudget.category_id)
        .join(Section, Section.id == Category.section_id)
        .where(
            CategoryBudget.workspace_id == workspace_id,
            CategoryBudget.month < month_end,
            Category.rollover.is_(True),
        )
        .options(selectinload(CategoryBudget.category).selectinload(Category.section))
    ).all()
    if not rows:
        return {}

    months = {row.month for row in rows}
    category_ids = {row.category_id for row in rows}
    section_ids = {row.category.section_id for row in rows}
    section_exclusions = set(
        db.execute(
            select(SectionMonthExclusion.section_id, SectionMonthExclusion.month).where(
                SectionMonthExclusion.section_id.in_(section_ids),
                SectionMonthExclusion.month.in_(months),
            )
        ).all()
    )
    category_exclusions = set(
        db.execute(
            select(CategoryMonthExclusion.category_id, CategoryMonthExclusion.month).where(
                CategoryMonthExclusion.category_id.in_(category_ids),
                CategoryMonthExclusion.month.in_(months),
            )
        ).all()
    )

    totals: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        category = row.category
        section = category.section
        if not lifetime_active(section, row.month) or not lifetime_active(category, row.month):
            continue
        if (section.id, row.month) in section_exclusions or (category.id, row.month) in category_exclusions:
            continue
        totals[category.id] += Decimal(row.planned)
    return dict(totals)


def _hidden_reason_label(reason: str) -> str:
    return {
        "not_started": "Starts in a later month",
        "ended": "Ended before this month",
        "hidden_this_month": "Hidden only this month",
        "archived": "Archived in every month",
    }.get(reason, "Not available this month")


def get_budget_state(db: Session, workspace_id: uuid.UUID, month: date) -> dict[str, Any]:
    month_end = next_month(month)
    all_sections = db.scalars(
        select(Section)
        .where(Section.workspace_id == workspace_id)
        .options(selectinload(Section.categories))
        .order_by(Section.is_income.desc(), Section.sort_order, Section.name)
    ).all()
    live_sections = [section for section in all_sections if section.archived_at is None]
    live_categories = [
        category
        for section in live_sections
        for category in section.categories
        if category.archived_at is None
    ]
    section_ids = {section.id for section in live_sections}
    category_ids = {category.id for category in live_categories}
    excluded_sections, excluded_categories = month_exclusion_ids(
        db,
        month,
        section_ids=section_ids,
        category_ids=category_ids,
    )

    budget_rows = db.scalars(
        select(CategoryBudget).where(
            CategoryBudget.workspace_id == workspace_id,
            CategoryBudget.month == month,
        )
    ).all()
    budget_map = {row.category_id: row for row in budget_rows}

    current_activity = dict(
        db.execute(
            select(Allocation.category_id, func.coalesce(func.sum(Allocation.amount), 0))
            .join(BudgetTransaction, BudgetTransaction.id == Allocation.transaction_id)
            .where(
                BudgetTransaction.workspace_id == workspace_id,
                BudgetTransaction.effective_date >= month,
                BudgetTransaction.effective_date < month_end,
                BudgetTransaction.deleted_at.is_(None),
                BudgetTransaction.excluded.is_(False),
            )
            .group_by(Allocation.category_id)
        ).all()
    )

    cumulative_activity = dict(
        db.execute(
            select(Allocation.category_id, func.coalesce(func.sum(Allocation.amount), 0))
            .join(BudgetTransaction, BudgetTransaction.id == Allocation.transaction_id)
            .join(Category, Category.id == Allocation.category_id)
            .where(
                BudgetTransaction.workspace_id == workspace_id,
                BudgetTransaction.effective_date < month_end,
                BudgetTransaction.deleted_at.is_(None),
                BudgetTransaction.excluded.is_(False),
                Category.rollover.is_(True),
            )
            .group_by(Allocation.category_id)
        ).all()
    )
    cumulative_planned = _rollover_planned_totals(db, workspace_id, month_end)

    category_lookup = {
        category.id: (category, section)
        for section in all_sections
        for category in section.categories
    }
    actual_income = Decimal("0")
    actual_expenses = Decimal("0")
    for category_id, raw_activity in current_activity.items():
        category_pair = category_lookup.get(category_id)
        if not category_pair:
            continue
        _, section = category_pair
        activity = Decimal(raw_activity)
        if section.is_income:
            actual_income += activity
        else:
            actual_expenses += -activity

    planned_income = Decimal("0")
    planned_expenses = Decimal("0")
    serialized_sections: list[dict[str, Any]] = []
    hidden_sections: list[dict[str, Any]] = []
    hidden_categories: list[dict[str, Any]] = []
    category_catalog: list[dict[str, Any]] = []
    visible_category_ids: set[uuid.UUID] = set()

    for section in all_sections:
        section_reason = visibility_reason(section, month, excluded=section.id in excluded_sections)
        section_categories = sorted(
            section.categories,
            key=lambda category: (category.sort_order, category.name.casefold()),
        )
        if section_reason:
            if not section.is_income:
                hidden_sections.append(
                    {
                        "id": str(section.id),
                        "name": section.name,
                        "icon": section.icon,
                        "version": section.version,
                        **availability_dict(section),
                        "visibility_reason": section_reason,
                        "visibility_label": _hidden_reason_label(section_reason),
                        "category_count": len([category for category in section_categories if category.archived_at is None]),
                        "archived": section.archived_at is not None,
                    }
                )
            for category in section_categories:
                own_reason = visibility_reason(
                    category,
                    month,
                    excluded=category.id in excluded_categories,
                )
                category_catalog.append(
                    {
                        "id": str(category.id),
                        "section_id": str(section.id),
                        "section_name": section.name,
                        "section_is_income": section.is_income,
                        "name": category.name,
                        "version": category.version,
                        **availability_dict(category),
                        "archived": category.archived_at is not None,
                        "visible_this_month": False,
                        "visibility_reason": own_reason or f"section_{section_reason}",
                    }
                )
            continue

        category_items: list[dict[str, Any]] = []
        for category in section_categories:
            category_reason = visibility_reason(
                category,
                month,
                excluded=category.id in excluded_categories,
            )
            budget = budget_map.get(category.id)
            planned = Decimal(budget.planned if budget else category.default_planned)
            activity = Decimal(current_activity.get(category.id, 0))
            catalog_item = {
                "id": str(category.id),
                "section_id": str(section.id),
                "section_name": section.name,
                "section_is_income": section.is_income,
                "name": category.name,
                "version": category.version,
                **availability_dict(category),
                "archived": category.archived_at is not None,
                "visible_this_month": category_reason is None,
                "visibility_reason": category_reason,
            }
            category_catalog.append(catalog_item)
            if category_reason:
                hidden_categories.append(
                    {
                        **catalog_item,
                        "visibility_label": _hidden_reason_label(category_reason),
                        "planned": money_str(planned),
                        "activity": money_str(activity),
                    }
                )
                continue

            visible_category_ids.add(category.id)
            if section.is_income:
                remaining = activity - planned
                planned_income += planned
            else:
                remaining = (
                    Decimal(cumulative_planned.get(category.id, 0))
                    + Decimal(cumulative_activity.get(category.id, 0))
                    if category.rollover
                    else planned + activity
                )
                planned_expenses += planned
            category_items.append(
                {
                    "id": str(category.id),
                    "section_id": str(section.id),
                    "name": category.name,
                    "rollover": category.rollover,
                    "default_planned": money_str(category.default_planned),
                    "note": category.note,
                    "sort_order": category.sort_order,
                    "version": category.version,
                    **availability_dict(category),
                    "planned": money_str(planned),
                    "budget_version": budget.version if budget else 0,
                    "activity": money_str(activity),
                    "remaining": money_str(remaining),
                }
            )
        serialized_sections.append(
            {
                "id": str(section.id),
                "name": section.name,
                "icon": section.icon,
                "accent": section.accent,
                "sort_order": section.sort_order,
                "is_income": section.is_income,
                "version": section.version,
                **availability_dict(section),
                "categories": category_items,
            }
        )

    hidden_activity = Decimal("0")
    hidden_planned = Decimal("0")
    for category_id, (category, _section) in category_lookup.items():
        if category_id in visible_category_ids:
            continue
        hidden_activity += Decimal(current_activity.get(category_id, 0))
        budget = budget_map.get(category_id)
        if budget:
            hidden_planned += Decimal(budget.planned)

    unassigned = db.scalars(
        select(BudgetTransaction)
        .where(
            BudgetTransaction.workspace_id == workspace_id,
            BudgetTransaction.deleted_at.is_(None),
            BudgetTransaction.excluded.is_(False),
            BudgetTransaction.suppressed_by_duplicate_account.is_(False),
            BudgetTransaction.account.has(Account.is_duplicate.is_(False)),
            not_(BudgetTransaction.allocations.any()),
        )
        .options(selectinload(BudgetTransaction.account), selectinload(BudgetTransaction.allocations))
        .order_by(BudgetTransaction.effective_date.desc(), BudgetTransaction.created_at.desc())
        .limit(200)
    ).all()

    account_catalog = db.scalars(
        select(Account)
        .where(Account.workspace_id == workspace_id)
        .options(selectinload(Account.simplefin_connection))
        .order_by(Account.source_type, Account.name)
    ).all()
    accounts = [account for account in account_catalog if account.is_active and not account.is_duplicate]

    connections = db.scalars(
        select(SimpleFinConnection)
        .where(SimpleFinConnection.workspace_id == workspace_id)
        .order_by(SimpleFinConnection.created_at)
    ).all()

    return {
        "month": month.isoformat()[:7],
        "summary": {
            "planned_income": money_str(planned_income),
            "planned_expenses": money_str(planned_expenses),
            "left_to_assign": money_str(planned_income - planned_expenses),
            "actual_income": money_str(actual_income),
            "actual_expenses": money_str(actual_expenses),
            "actual_cash_flow": money_str(actual_income - actual_expenses),
            "hidden_activity": money_str(hidden_activity),
            "hidden_planned": money_str(hidden_planned),
        },
        "sections": serialized_sections,
        "hidden_structure": {
            "sections": hidden_sections,
            "categories": hidden_categories,
            "count": len(hidden_sections) + len(hidden_categories),
        },
        "category_catalog": category_catalog,
        "unassigned": [serialize_transaction(transaction) for transaction in unassigned],
        "accounts": [serialize_account(account) for account in accounts],
        "account_catalog": [serialize_account(account) for account in account_catalog],
        "connections": [
            {
                "id": str(connection.id),
                "name": connection.name,
                "enabled": connection.enabled,
                "last_attempt_at": connection.last_attempt_at.isoformat() if connection.last_attempt_at else None,
                "last_success_at": connection.last_success_at.isoformat() if connection.last_success_at else None,
                "next_sync_at": connection.next_sync_at.isoformat(),
                "consecutive_failures": connection.consecutive_failures,
                "last_error_code": connection.last_error_code,
                "last_error_message": connection.last_error_message,
                "version": connection.version,
            }
            for connection in connections
        ],
    }
