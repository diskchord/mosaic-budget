from __future__ import annotations

from sqlalchemy import select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.models import Account, BudgetTransaction, Category, Rule, User, Workspace
from app.seed_demo import DEMO_ACCOUNT_BALANCE, DEMO_MARKER, HISTORY_MONTH_COUNT, seed
from app.services.analytics import get_analytics


def test_demo_seed_is_public_safe_useful_and_idempotent() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()

    seed()
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).limit(1))
        owner = db.scalar(select(User).where(User.is_admin.is_(True)))
        category_names = set(db.scalars(select(Category.name)).all())
        account_names = set(db.scalars(select(Account.name)).all())
        rules = db.scalars(select(Rule).order_by(Rule.priority)).all()
        transactions = [
            transaction
            for transaction in db.scalars(select(BudgetTransaction)).all()
            if transaction.imported_extra.get("demo_dataset") == DEMO_MARKER
        ]
        transaction_count = len(transactions)
        months = {transaction.effective_date.replace(day=1) for transaction in transactions}
        unsorted_count = sum(not transaction.allocations for transaction in transactions)

        assert workspace is not None and workspace.name == "Demo Household"
        assert owner is not None and owner.display_name == "Jordan Lee"
        assert {"Everyday Account", "Cash & Other"} <= account_names
        primary_account = db.scalar(select(Account).where(Account.name == "Everyday Account"))
        assert primary_account is not None and primary_account.balance == DEMO_ACCOUNT_BALANCE
        assert {"Primary Income", "Side Income", "Housing Payment", "Heating & Cooling"} <= category_names
        assert len(months) == HISTORY_MONTH_COUNT
        assert transaction_count == (HISTORY_MONTH_COUNT - 1) * 11 + 12 + 7
        assert unsorted_count == 7
        analytics = get_analytics(db, workspace.id, min(months), max(months))
        assert len(analytics["months"]) == HISTORY_MONTH_COUNT
        assert all(month_summary["income"] != "0" for month_summary in analytics["months"])
        assert all(month_summary["spending"] != "0" for month_summary in analytics["months"])
        assert [rule.name for rule in rules] == [
            "Meadowcart Market → Groceries",
            "Cloudnest → Internet",
            "Storybox → Entertainment",
            "Flag large purchases",
        ]
        assert rules[0].enabled is False
        assert all(transaction.note == "" for transaction in transactions)
        public_text = " ".join(
            [
                *(transaction.payee for transaction in transactions),
                *category_names,
                *account_names,
                *(rule.name for rule in rules),
                owner.display_name,
                owner.email,
            ]
        ).casefold()
        assert all(
            banned not in public_text
            for banned in ("hannaford", "maine", "central maine power", "piano", "canine", "mortgage")
        )

    seed()
    with SessionLocal() as db:
        assert sum(
            transaction.imported_extra.get("demo_dataset") == DEMO_MARKER
            for transaction in db.scalars(select(BudgetTransaction)).all()
        ) == transaction_count
