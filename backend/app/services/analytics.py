from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, not_, select
from sqlalchemy.orm import Session

from ..models import Account, Allocation, BudgetTransaction, Category, Section, Workspace
from ..utils import money_str, next_month


def month_range(start_month: date, end_month: date) -> list[date]:
    """Return every first-of-month date in an inclusive range."""
    months: list[date] = []
    cursor = start_month
    while cursor <= end_month:
        months.append(cursor)
        cursor = next_month(cursor)
    return months


def _eligible_transaction_filters(workspace_id: uuid.UUID) -> tuple[Any, ...]:
    return (
        BudgetTransaction.workspace_id == workspace_id,
        BudgetTransaction.deleted_at.is_(None),
        BudgetTransaction.excluded.is_(False),
        BudgetTransaction.suppressed_by_duplicate_account.is_(False),
        BudgetTransaction.transfer_group_id.is_(None),
        Account.is_duplicate.is_(False),
    )


def _empty_month(month: date) -> dict[str, Any]:
    return {
        "month": month.isoformat()[:7],
        "income": Decimal("0"),
        "spending": Decimal("0"),
        "net": Decimal("0"),
        "transaction_ids": set(),
        "categorized_transaction_ids": set(),
        "uncategorized_transaction_ids": set(),
        "uncategorized_net": Decimal("0"),
    }


def _serialize_month(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "month": item["month"],
        "income": money_str(item["income"]),
        "spending": money_str(item["spending"]),
        "net": money_str(item["net"]),
        "transaction_count": len(item["transaction_ids"]),
        "categorized_transaction_count": len(item["categorized_transaction_ids"]),
        "uncategorized_transaction_count": len(item["uncategorized_transaction_ids"]),
        "uncategorized_net": money_str(item["uncategorized_net"]),
    }


def get_analytics(
    db: Session,
    workspace_id: uuid.UUID,
    start_month: date,
    end_month: date,
) -> dict[str, Any]:
    """Build inclusive month-by-month actuals for a workspace.

    Income and spending follow budget activity semantics: allocations in an
    income section add to income, while allocations in every other section are
    negated into spending. Transactions that have not been categorized are
    disclosed separately and do not distort either total.
    """
    months = month_range(start_month, end_month)
    month_items = {month.isoformat()[:7]: _empty_month(month) for month in months}
    range_end = next_month(end_month)

    allocation_rows = db.execute(
        select(
            BudgetTransaction.effective_date,
            BudgetTransaction.id,
            Category.id,
            Category.name,
            Category.sort_order,
            Section.id,
            Section.name,
            Section.sort_order,
            Section.is_income,
            func.coalesce(func.sum(Allocation.amount), 0),
        )
        .select_from(Allocation)
        .join(BudgetTransaction, BudgetTransaction.id == Allocation.transaction_id)
        .join(Account, Account.id == BudgetTransaction.account_id)
        .join(Category, Category.id == Allocation.category_id)
        .join(Section, Section.id == Category.section_id)
        .where(
            *_eligible_transaction_filters(workspace_id),
            BudgetTransaction.effective_date >= start_month,
            BudgetTransaction.effective_date < range_end,
        )
        .group_by(
            BudgetTransaction.effective_date,
            BudgetTransaction.id,
            Category.id,
            Category.name,
            Category.sort_order,
            Section.id,
            Section.name,
            Section.sort_order,
            Section.is_income,
        )
    ).all()

    category_items: dict[uuid.UUID, dict[str, Any]] = {}
    category_month_amounts: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    for (
        effective_date,
        transaction_id,
        category_id,
        category_name,
        category_sort_order,
        section_id,
        section_name,
        section_sort_order,
        is_income,
        raw_amount,
    ) in allocation_rows:
        key = effective_date.isoformat()[:7]
        item = month_items[key]
        amount = Decimal(raw_amount)
        display_amount = amount if is_income else -amount

        if is_income:
            item["income"] += display_amount
        else:
            item["spending"] += display_amount
        item["categorized_transaction_ids"].add(transaction_id)
        item["transaction_ids"].add(transaction_id)
        category_month_amounts[category_id][key] += display_amount
        category_items[category_id] = {
            "id": str(category_id),
            "name": category_name,
            "section_id": str(section_id),
            "section_name": section_name,
            "is_income": is_income,
            "section_sort_order": section_sort_order,
            "category_sort_order": category_sort_order,
        }

    uncategorized_rows = db.execute(
        select(
            BudgetTransaction.effective_date,
            BudgetTransaction.id,
            BudgetTransaction.amount,
        )
        .join(Account, Account.id == BudgetTransaction.account_id)
        .where(
            *_eligible_transaction_filters(workspace_id),
            BudgetTransaction.effective_date >= start_month,
            BudgetTransaction.effective_date < range_end,
            not_(BudgetTransaction.allocations.any()),
        )
    ).all()
    for effective_date, transaction_id, raw_amount in uncategorized_rows:
        item = month_items[effective_date.isoformat()[:7]]
        item["transaction_ids"].add(transaction_id)
        item["uncategorized_transaction_ids"].add(transaction_id)
        item["uncategorized_net"] += Decimal(raw_amount)

    for item in month_items.values():
        item["net"] = item["income"] - item["spending"]

    serialized_months = [_serialize_month(month_items[month.isoformat()[:7]]) for month in months]
    month_count = Decimal(len(months))
    total_income = sum((item["income"] for item in month_items.values()), Decimal("0"))
    total_spending = sum((item["spending"] for item in month_items.values()), Decimal("0"))
    total_net = total_income - total_spending
    total_uncategorized_net = sum(
        (item["uncategorized_net"] for item in month_items.values()),
        Decimal("0"),
    )

    serialized_categories: list[dict[str, Any]] = []
    for category in sorted(
        category_items.values(),
        key=lambda item: (
            not item["is_income"],
            item["section_sort_order"],
            item["category_sort_order"],
            item["name"].casefold(),
        ),
    ):
        category_id = uuid.UUID(category["id"])
        amounts = category_month_amounts[category_id]
        total = sum(amounts.values(), Decimal("0"))
        serialized_categories.append(
            {
                "id": category["id"],
                "name": category["name"],
                "section_id": category["section_id"],
                "section_name": category["section_name"],
                "is_income": category["is_income"],
                "total": money_str(total),
                "average": money_str(total / month_count),
                "months": [
                    {
                        "month": month.isoformat()[:7],
                        "amount": money_str(amounts.get(month.isoformat()[:7], Decimal("0"))),
                    }
                    for month in months
                ],
            }
        )

    workspace = db.get(Workspace, workspace_id)
    return {
        "currency": workspace.currency if workspace else "USD",
        "start_month": start_month.isoformat()[:7],
        "end_month": end_month.isoformat()[:7],
        "months": serialized_months,
        "totals": {
            "income": money_str(total_income),
            "spending": money_str(total_spending),
            "net": money_str(total_net),
            "average_income": money_str(total_income / month_count),
            "average_spending": money_str(total_spending / month_count),
            "average_net": money_str(total_net / month_count),
            "transaction_count": sum(item["transaction_count"] for item in serialized_months),
            "categorized_transaction_count": sum(
                item["categorized_transaction_count"] for item in serialized_months
            ),
            "uncategorized_transaction_count": sum(
                item["uncategorized_transaction_count"] for item in serialized_months
            ),
            "uncategorized_net": money_str(total_uncategorized_net),
        },
        "categories": serialized_categories,
    }
