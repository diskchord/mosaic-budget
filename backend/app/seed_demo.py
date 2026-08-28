from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import get_settings
from .db import SessionLocal
from .models import (
    Account,
    Allocation,
    BudgetTransaction,
    Category,
    CategoryBudget,
    Rule,
    RuleRevision,
    Section,
    User,
    Workspace,
)
from .services.rules import rule_snapshot
from .utils import month_floor, utcnow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()
DEMO_MARKER = "mosaic-demo-v1"


def seed() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(BudgetTransaction.id).where(BudgetTransaction.note == DEMO_MARKER).limit(1)):
            logger.info("Demo data already exists; nothing changed")
            return

        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at).limit(1))
        owner = db.scalar(select(User).where(User.workspace_id == workspace.id, User.is_admin.is_(True)))
        account = db.scalar(
            select(Account).where(
                Account.workspace_id == workspace.id,
                Account.source_type == "manual",
                Account.name == "Cash Wallet",
            )
        )
        if not workspace or not owner or not account:
            raise RuntimeError("Run migrations and app.bootstrap before seeding demo data")

        categories = db.scalars(
            select(Category)
            .join(Section)
            .where(Section.workspace_id == workspace.id)
            .options(selectinload(Category.section))
        ).all()
        by_name = {category.name: category for category in categories}
        required = {
            "Alex's Piano Service",
            "Diamond Canine",
            "Land Mortgage",
            "Electricity",
            "Groceries",
            "Eating Out",
            "Internet",
            "Streaming",
            "Fuel",
            "Emergency Fund",
        }
        missing = required - by_name.keys()
        if missing:
            raise RuntimeError(f"Starter categories are missing: {', '.join(sorted(missing))}")

        today = utcnow().astimezone(ZoneInfo(settings.app_timezone)).date()
        month = month_floor(today)
        plans = {
            "Alex's Piano Service": "6500",
            "Diamond Canine": "1700",
            "Land Mortgage": "1450",
            "Electricity": "250",
            "Groceries": "500",
            "Eating Out": "150",
            "Internet": "75",
            "Streaming": "50",
            "Fuel": "300",
            "Emergency Fund": "800",
        }
        for name, amount in plans.items():
            category = by_name[name]
            row = db.scalar(
                select(CategoryBudget).where(
                    CategoryBudget.workspace_id == workspace.id,
                    CategoryBudget.month == month,
                    CategoryBudget.category_id == category.id,
                )
            )
            if row is None:
                db.add(
                    CategoryBudget(
                        workspace_id=workspace.id,
                        month=month,
                        category_id=category.id,
                        planned=Decimal(amount),
                    )
                )
            else:
                row.planned = Decimal(amount)
                row.version += 1

        def day(number: int) -> date:
            # All selected values are valid in every month.
            return date(month.year, month.month, number)

        entries = [
            ("Alex's Piano Service", "5940.00", "Alex's Piano Service", day(4)),
            ("Diamond Canine", "1820.00", "Diamond Canine", day(7)),
            ("Land Mortgage", "-1450.00", "Land Mortgage", day(2)),
            ("Central Maine Power", "-184.26", "Electricity", day(9)),
            ("Hannaford", "-84.27", "Groceries", day(11)),
            ("Hannaford", "-72.14", "Groceries", day(18)),
            ("Hannaford", "-70.63", "Groceries", day(25)),
            ("Local Restaurant", "-94.18", "Eating Out", day(20)),
            ("Internet Provider", "-75.00", "Internet", day(12)),
            ("Streaming Services", "-31.48", "Streaming", day(13)),
            ("Fuel Station", "-63.19", "Fuel", day(22)),
            ("Emergency transfer", "-800.00", "Emergency Fund", day(6)),
        ]
        net = Decimal("0")
        for payee, raw_amount, category_name, effective_date in entries:
            amount = Decimal(raw_amount)
            transaction = BudgetTransaction(
                workspace_id=workspace.id,
                account_id=account.id,
                source_kind="manual",
                effective_date=effective_date,
                amount=amount,
                payee=payee,
                imported_description="",
                imported_extra={},
                note=DEMO_MARKER,
                pending=False,
                cleared=True,
                manual_payee_lock=True,
                manual_date_lock=True,
                manual_allocation_lock=True,
                created_by_id=owner.id,
            )
            transaction.allocations.append(
                Allocation(category_id=by_name[category_name].id, amount=amount, memo="Demo")
            )
            db.add(transaction)
            net += amount

        unassigned = BudgetTransaction(
            workspace_id=workspace.id,
            account_id=account.id,
            source_kind="manual",
            effective_date=day(26),
            amount=Decimal("-46.72"),
            payee="Hannaford",
            imported_description="POS PURCHASE HANNAFORD 0831",
            imported_extra={},
            note=DEMO_MARKER,
            pending=False,
            cleared=True,
            manual_payee_lock=False,
            manual_date_lock=False,
            manual_allocation_lock=False,
            created_by_id=owner.id,
        )
        db.add(unassigned)
        net += Decimal("-46.72")
        account.balance = Decimal(account.balance or 0) + net
        account.available_balance = account.balance
        account.version += 1

        if not db.scalar(select(Rule.id).where(Rule.workspace_id == workspace.id, Rule.name == "Hannaford → Groceries")):
            rule = Rule(
                workspace_id=workspace.id,
                name="Hannaford → Groceries",
                enabled=False,
                phase="categorize",
                priority=100,
                conditions={
                    "combinator": "all",
                    "children": [
                        {"field": "original_description", "operator": "contains", "value": "Hannaford"},
                        {"field": "account_id", "operator": "is", "value": str(account.id)},
                        {"field": "outflow", "operator": "between", "value": ["1", "500"]},
                    ],
                },
                actions=[{"type": "assign_category", "category_id": str(by_name["Groceries"].id)}],
                apply_to_manual_overrides=False,
                stop_processing=True,
                created_by_id=owner.id,
            )
            db.add(rule)
            db.flush()
            db.add(
                RuleRevision(
                    rule_id=rule.id,
                    version=rule.version,
                    snapshot=rule_snapshot(rule),
                    changed_by_id=owner.id,
                )
            )

        db.commit()
        logger.info("Demo budget created for %s", month.isoformat()[:7])
        logger.info("The demo Hannaford rule is disabled so the inbox has a draggable transaction")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
