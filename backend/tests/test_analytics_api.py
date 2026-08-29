from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.analytics import analytics
from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.models import Account, Allocation, BudgetTransaction, Category, Section, Workspace
from app.utils import utcnow


def _transaction(
    db,
    *,
    workspace_id,
    account_id,
    effective_date: date,
    amount: str,
    payee: str,
    category_amounts: list[tuple[Category, str]] | None = None,
    excluded: bool = False,
    suppressed: bool = False,
    deleted: bool = False,
) -> BudgetTransaction:
    transaction = BudgetTransaction(
        workspace_id=workspace_id,
        account_id=account_id,
        source_kind="manual",
        effective_date=effective_date,
        amount=Decimal(amount),
        payee=payee,
        excluded=excluded,
        suppressed_by_duplicate_account=suppressed,
        deleted_at=utcnow() if deleted else None,
    )
    db.add(transaction)
    db.flush()
    for index, (category, allocation_amount) in enumerate(category_amounts or []):
        db.add(
            Allocation(
                transaction_id=transaction.id,
                category_id=category.id,
                amount=Decimal(allocation_amount),
                sort_order=index,
            )
        )
    return transaction


def _seed_analytics() -> tuple[object, dict[str, str]]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()

    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).limit(1))
        assert workspace is not None
        account = db.scalar(
            select(Account).where(
                Account.workspace_id == workspace.id,
                Account.source_type == "manual",
            )
        )
        income = db.scalar(
            select(Category)
            .join(Section)
            .where(Section.workspace_id == workspace.id, Section.is_income.is_(True))
            .order_by(Category.sort_order)
        )
        groceries = db.scalar(select(Category).where(Category.name == "Groceries"))
        streaming = db.scalar(select(Category).where(Category.name == "Streaming"))
        assert account is not None and income is not None and groceries is not None and streaming is not None

        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=account.id,
            effective_date=date(2026, 7, 2),
            amount="1000",
            payee="July income",
            category_amounts=[(income, "1000")],
        )
        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=account.id,
            effective_date=date(2026, 7, 3),
            amount="-300",
            payee="July groceries",
            category_amounts=[(groceries, "-300")],
        )
        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=account.id,
            effective_date=date(2026, 7, 4),
            amount="-20",
            payee="Not sorted yet",
        )

        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=account.id,
            effective_date=date(2026, 8, 2),
            amount="1200",
            payee="August income",
            category_amounts=[(income, "1200")],
        )
        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=account.id,
            effective_date=date(2026, 8, 3),
            amount="-250",
            payee="August split",
            category_amounts=[(groceries, "-200"), (streaming, "-50")],
        )
        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=account.id,
            effective_date=date(2026, 8, 4),
            amount="25",
            payee="Grocery refund",
            category_amounts=[(groceries, "25")],
        )

        # Each exclusion path is intentionally independent so a missing filter
        # would produce an unmistakably large analytics result.
        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=account.id,
            effective_date=date(2026, 8, 10),
            amount="9000",
            payee="Excluded",
            category_amounts=[(income, "9000")],
            excluded=True,
        )
        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=account.id,
            effective_date=date(2026, 8, 11),
            amount="-9000",
            payee="Deleted",
            category_amounts=[(groceries, "-9000")],
            deleted=True,
        )
        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=account.id,
            effective_date=date(2026, 8, 12),
            amount="7000",
            payee="Duplicate-suppressed",
            category_amounts=[(income, "7000")],
            suppressed=True,
        )

        duplicate_account = Account(
            workspace_id=workspace.id,
            source_type="simplefin",
            source_conn_id="analytics-test",
            source_account_id="duplicate",
            name="Duplicate account",
            currency="USD",
            is_duplicate=True,
        )
        db.add(duplicate_account)
        db.flush()
        _transaction(
            db,
            workspace_id=workspace.id,
            account_id=duplicate_account.id,
            effective_date=date(2026, 8, 13),
            amount="6000",
            payee="Duplicate account transaction",
            category_amounts=[(income, "6000")],
        )
        workspace_id = workspace.id
        ids = {
            "income_id": str(income.id),
            "groceries_id": str(groceries.id),
            "streaming_id": str(streaming.id),
        }
        db.commit()

    return workspace_id, ids


def test_analytics_compares_months_and_preserves_transaction_visibility_semantics() -> None:
    workspace_id, ids = _seed_analytics()

    with SessionLocal() as db:
        payload = analytics(
            start_month="2026-07",
            end_month="2026-08",
            auth=SimpleNamespace(user=SimpleNamespace(workspace_id=workspace_id)),
            db=db,
        )

    assert payload["currency"] == "USD"
    assert payload["start_month"] == "2026-07"
    assert payload["end_month"] == "2026-08"
    assert payload["months"] == [
        {
            "month": "2026-07",
            "income": "1000",
            "spending": "300",
            "net": "700",
            "transaction_count": 3,
            "categorized_transaction_count": 2,
            "uncategorized_transaction_count": 1,
            "uncategorized_net": "-20",
        },
        {
            "month": "2026-08",
            "income": "1200",
            "spending": "225",
            "net": "975",
            "transaction_count": 3,
            "categorized_transaction_count": 3,
            "uncategorized_transaction_count": 0,
            "uncategorized_net": "0",
        },
    ]
    assert payload["totals"] == {
        "income": "2200",
        "spending": "525",
        "net": "1675",
        "average_income": "1100",
        "average_spending": "262.5",
        "average_net": "837.5",
        "transaction_count": 6,
        "categorized_transaction_count": 5,
        "uncategorized_transaction_count": 1,
        "uncategorized_net": "-20",
    }

    categories = {item["id"]: item for item in payload["categories"]}
    assert categories[ids["income_id"]]["months"] == [
        {"month": "2026-07", "amount": "1000"},
        {"month": "2026-08", "amount": "1200"},
    ]
    assert categories[ids["groceries_id"]]["total"] == "475"
    assert categories[ids["groceries_id"]]["months"] == [
        {"month": "2026-07", "amount": "300"},
        {"month": "2026-08", "amount": "175"},
    ]
    assert categories[ids["streaming_id"]]["months"] == [
        {"month": "2026-07", "amount": "0"},
        {"month": "2026-08", "amount": "50"},
    ]


def test_analytics_emits_empty_months_and_validates_range() -> None:
    workspace_id, _ids = _seed_analytics()

    with SessionLocal() as db:
        auth = SimpleNamespace(user=SimpleNamespace(workspace_id=workspace_id))
        empty = analytics(
            start_month="2026-06",
            end_month="2026-06",
            auth=auth,
            db=db,
        )
        with pytest.raises(HTTPException) as reversed_error:
            analytics(
                start_month="2026-09",
                end_month="2026-08",
                auth=auth,
                db=db,
            )
        with pytest.raises(HTTPException) as too_long_error:
            analytics(
                start_month="2016-08",
                end_month="2026-08",
                auth=auth,
                db=db,
            )
        with pytest.raises(HTTPException) as malformed_error:
            analytics(
                start_month="August 2026",
                end_month="2026-08",
                auth=auth,
                db=db,
            )
        with pytest.raises(HTTPException) as maximum_calendar_error:
            analytics(
                start_month="9999-12",
                end_month="9999-12",
                auth=auth,
                db=db,
            )
        with pytest.raises(HTTPException) as minimum_default_error:
            analytics(
                start_month=None,
                end_month="0001-01",
                auth=auth,
                db=db,
            )

    assert empty["months"] == [
        {
            "month": "2026-06",
            "income": "0",
            "spending": "0",
            "net": "0",
            "transaction_count": 0,
            "categorized_transaction_count": 0,
            "uncategorized_transaction_count": 0,
            "uncategorized_net": "0",
        }
    ]
    assert reversed_error.value.status_code == 400
    assert reversed_error.value.detail == "Start month must not be after end month"
    assert too_long_error.value.status_code == 400
    assert too_long_error.value.detail == "Analytics ranges are limited to 120 months"
    assert malformed_error.value.status_code == 400
    assert malformed_error.value.detail == "Month must be formatted YYYY-MM"
    assert maximum_calendar_error.value.status_code == 400
    assert maximum_calendar_error.value.detail == "End month must be before December 9999"
    assert minimum_default_error.value.status_code == 400
    assert "outside the supported calendar" in minimum_default_error.value.detail
