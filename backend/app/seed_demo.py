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
HISTORY_MONTH_COUNT = 12
DEMO_ACCOUNT_BALANCE = Decimal("12548.72")

# Bootstrap remains intentionally unchanged for real installations. The optional
# demo path gives those starter categories neutral public-facing labels before
# creating screenshot-safe sample activity.
# role: (starter section, starter position, public demo label)
DEMO_CATEGORY_LAYOUT = {
    "primary_income": ("Income", 0, "Primary Income"),
    "side_income": ("Income", 1, "Side Income"),
    "other_income": ("Income", 2, "Other Income"),
    "housing": ("Housing", 0, "Housing Payment"),
    "utilities": ("Housing", 1, "Utilities"),
    "heating_cooling": ("Housing", 2, "Heating & Cooling"),
    "home_maintenance": ("Housing", 3, "Home Maintenance"),
    "groceries": ("Food", 0, "Groceries"),
    "dining": ("Food", 1, "Dining Out"),
    "fuel_transit": ("Transportation", 0, "Fuel & Transit"),
    "vehicle_maintenance": ("Transportation", 1, "Vehicle Maintenance"),
    "registration_fees": ("Transportation", 2, "Registration & Fees"),
    "internet": ("Subscriptions", 0, "Internet"),
    "software": ("Subscriptions", 1, "Software"),
    "entertainment": ("Subscriptions", 2, "Entertainment"),
    "health": ("Personal", 0, "Health"),
    "clothing": ("Personal", 1, "Clothing"),
    "gifts": ("Personal", 2, "Gifts"),
    "rainy_day": ("Savings", 0, "Rainy Day Fund"),
    "taxes": ("Savings", 1, "Taxes"),
    "future_purchases": ("Savings", 2, "Future Purchases"),
}

DEMO_PLANS = {
    "primary_income": "6500",
    "side_income": "1700",
    "housing": "1450",
    "utilities": "250",
    "heating_cooling": "100",
    "home_maintenance": "200",
    "groceries": "500",
    "dining": "150",
    "fuel_transit": "300",
    "vehicle_maintenance": "150",
    "registration_fees": "50",
    "internet": "75",
    "software": "30",
    "entertainment": "50",
    "health": "125",
    "clothing": "60",
    "gifts": "75",
    "rainy_day": "800",
    "taxes": "450",
    "future_purchases": "500",
}

# Eleven completed months plus the current month fill Analytics' default range.
# The names are invented and deliberately avoid real banks, merchants, and places.
HISTORICAL_AMOUNTS = [
    {
        "primary": "6040.00",
        "side": "1510.00",
        "utilities": "164.88",
        "groceries_one": "78.34",
        "groceries_two": "82.17",
        "dining": "64.20",
        "fuel": "53.81",
    },
    {
        "primary": "6175.00",
        "side": "1560.00",
        "utilities": "179.42",
        "groceries_one": "84.29",
        "groceries_two": "75.63",
        "dining": "70.15",
        "fuel": "58.94",
    },
    {
        "primary": "6260.00",
        "side": "1495.00",
        "utilities": "196.73",
        "groceries_one": "92.48",
        "groceries_two": "88.16",
        "dining": "86.35",
        "fuel": "60.22",
    },
    {
        "primary": "6450.00",
        "side": "1625.00",
        "utilities": "211.09",
        "groceries_one": "96.57",
        "groceries_two": "90.24",
        "dining": "93.18",
        "fuel": "55.76",
    },
    {
        "primary": "6085.00",
        "side": "1680.00",
        "utilities": "224.56",
        "groceries_one": "87.43",
        "groceries_two": "78.91",
        "dining": "69.75",
        "fuel": "62.38",
    },
    {
        "primary": "6315.00",
        "side": "1545.00",
        "utilities": "217.14",
        "groceries_one": "80.65",
        "groceries_two": "85.37",
        "dining": "72.80",
        "fuel": "56.49",
    },
    {
        "primary": "6120.00",
        "side": "1585.00",
        "utilities": "172.48",
        "groceries_one": "91.34",
        "groceries_two": "76.22",
        "dining": "68.40",
        "fuel": "57.18",
    },
    {
        "primary": "6380.00",
        "side": "1640.00",
        "utilities": "188.15",
        "groceries_one": "83.76",
        "groceries_two": "79.58",
        "dining": "74.25",
        "fuel": "61.09",
    },
    {
        "primary": "6210.00",
        "side": "1725.00",
        "utilities": "203.66",
        "groceries_one": "88.12",
        "groceries_two": "81.47",
        "dining": "82.10",
        "fuel": "54.87",
    },
    {
        "primary": "6490.00",
        "side": "1690.00",
        "utilities": "176.92",
        "groceries_one": "94.08",
        "groceries_two": "73.39",
        "dining": "77.65",
        "fuel": "65.44",
    },
    {
        "primary": "6330.00",
        "side": "1775.00",
        "utilities": "191.37",
        "groceries_one": "86.51",
        "groceries_two": "84.63",
        "dining": "71.90",
        "fuel": "59.72",
    },
]


def _shift_month(month: date, offset: int) -> date:
    absolute = month.year * 12 + month.month - 1 + offset
    return date(absolute // 12, absolute % 12 + 1, 1)


def seed() -> None:
    db = SessionLocal()
    try:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at).limit(1))
        if workspace is None:
            raise RuntimeError("Run migrations and app.bootstrap before seeding demo data")
        if db.scalar(
            select(Rule.id).where(
                Rule.workspace_id == workspace.id,
                Rule.name == "Meadowcart Market → Groceries",
            )
        ):
            logger.info("Demo data already exists; nothing changed")
            return
        owner = db.scalar(select(User).where(User.workspace_id == workspace.id, User.is_admin.is_(True)))
        account = db.scalar(
            select(Account).where(
                Account.workspace_id == workspace.id,
                Account.source_type == "manual",
                Account.name == "Cash Wallet",
            )
        )
        if not owner or not account:
            raise RuntimeError("Run migrations and app.bootstrap before seeding demo data")

        categories = db.scalars(
            select(Category)
            .join(Section)
            .where(Section.workspace_id == workspace.id)
            .options(selectinload(Category.section))
        ).all()
        by_slot = {(category.section.name, category.sort_order): category for category in categories}
        by_role = {
            role: by_slot.get((section_name, sort_order))
            for role, (section_name, sort_order, _demo_name) in DEMO_CATEGORY_LAYOUT.items()
        }
        missing = {role for role, category in by_role.items() if category is None}
        if missing:
            raise RuntimeError(f"Starter category positions are missing: {', '.join(sorted(missing))}")

        workspace.name = "Demo Household"
        workspace.version += 1
        owner.display_name = "Jordan Lee"
        owner.version += 1
        account.name = "Everyday Account"
        secondary_account = db.scalar(
            select(Account).where(
                Account.workspace_id == workspace.id,
                Account.source_type == "manual",
                Account.name == "Untracked Cash",
            )
        )
        if secondary_account:
            secondary_account.name = "Cash & Other"
            secondary_account.balance = Decimal("185.00")
            secondary_account.available_balance = secondary_account.balance
            secondary_account.version += 1

        today = utcnow().astimezone(ZoneInfo(settings.app_timezone)).date()
        month = month_floor(today)
        demo_months = [_shift_month(month, offset) for offset in range(-(HISTORY_MONTH_COUNT - 1), 1)]
        for budget_month in demo_months:
            for role, amount in DEMO_PLANS.items():
                category = by_role[role]
                assert category is not None
                row = db.scalar(
                    select(CategoryBudget).where(
                        CategoryBudget.workspace_id == workspace.id,
                        CategoryBudget.month == budget_month,
                        CategoryBudget.category_id == category.id,
                    )
                )
                if row is None:
                    db.add(
                        CategoryBudget(
                            workspace_id=workspace.id,
                            month=budget_month,
                            category_id=category.id,
                            planned=Decimal(amount),
                        )
                    )
                else:
                    row.planned = Decimal(amount)
                    row.version += 1

        def add_transaction(
            *,
            target_month: date,
            day: int,
            payee: str,
            amount: str,
            category_role: str | None,
            description: str | None = None,
        ) -> None:
            parsed_amount = Decimal(amount)
            transaction = BudgetTransaction(
                workspace_id=workspace.id,
                account_id=account.id,
                source_kind="manual",
                effective_date=date(target_month.year, target_month.month, day),
                amount=parsed_amount,
                payee=payee,
                imported_description=description or payee.upper(),
                imported_extra={"demo_dataset": DEMO_MARKER},
                note="",
                pending=False,
                cleared=True,
                manual_payee_lock=category_role is not None,
                manual_date_lock=category_role is not None,
                manual_allocation_lock=category_role is not None,
                created_by_id=owner.id,
            )
            if category_role is not None:
                category = by_role[category_role]
                assert category is not None
                transaction.allocations.append(
                    Allocation(category_id=category.id, amount=parsed_amount, memo="Demo")
                )
            db.add(transaction)

        for history_month, amounts in zip(demo_months[:-1], HISTORICAL_AMOUNTS, strict=True):
            historical_entries = [
                (4, "Project Payment", amounts["primary"], "primary_income"),
                (7, "Workshop Payment", amounts["side"], "side_income"),
                (2, "Hearthway Housing", "-1450.00", "housing"),
                (9, "Sunwire Utilities", f'-{amounts["utilities"]}', "utilities"),
                (11, "Meadowcart Market", f'-{amounts["groceries_one"]}', "groceries"),
                (22, "Meadowcart Market", f'-{amounts["groceries_two"]}', "groceries"),
                (18, "Juniper Table", f'-{amounts["dining"]}', "dining"),
                (12, "Cloudnest Internet", "-75.00", "internet"),
                (13, "Storybox Media", "-31.48", "entertainment"),
                (20, "Roadleaf Fuel", f'-{amounts["fuel"]}', "fuel_transit"),
                (6, "Rainy Day Transfer", "-800.00", "rainy_day"),
            ]
            for day, payee, amount, category_role in historical_entries:
                add_transaction(
                    target_month=history_month,
                    day=day,
                    payee=payee,
                    amount=amount,
                    category_role=category_role,
                )

        current_entries = [
            (4, "Project Payment", "5940.00", "primary_income"),
            (7, "Workshop Payment", "1820.00", "side_income"),
            (2, "Hearthway Housing", "-1450.00", "housing"),
            (9, "Sunwire Utilities", "-184.26", "utilities"),
            (11, "Meadowcart Market", "-84.27", "groceries"),
            (18, "Meadowcart Market", "-72.14", "groceries"),
            (25, "Meadowcart Market", "-70.63", "groceries"),
            (20, "Juniper Table", "-94.18", "dining"),
            (12, "Cloudnest Internet", "-75.00", "internet"),
            (13, "Storybox Media", "-31.48", "entertainment"),
            (22, "Roadleaf Fuel", "-63.19", "fuel_transit"),
            (6, "Rainy Day Transfer", "-800.00", "rainy_day"),
        ]
        for day, payee, amount, category_role in current_entries:
            add_transaction(
                target_month=month,
                day=day,
                payee=payee,
                amount=amount,
                category_role=category_role,
            )

        unsorted_entries = [
            (26, "Meadowcart Market", "-46.72", "CARD PURCHASE MEADOWCART MARKET 1042"),
            (24, "Bluebird Pharmacy", "-28.41", "CARD PURCHASE BLUEBIRD PHARMACY"),
            (23, "Civic Corner Books", "-19.95", "CARD PURCHASE CIVIC CORNER BOOKS"),
            (21, "Oakline Hardware", "-86.33", "CARD PURCHASE OAKLINE HARDWARE"),
            (19, "Daybreak Bakery", "-14.80", "CARD PURCHASE DAYBREAK BAKERY"),
            (17, "Northloop Transit", "-32.00", "CARD PURCHASE NORTHLOOP TRANSIT"),
            (15, "Willow & Thread", "-54.25", "CARD PURCHASE WILLOW AND THREAD"),
        ]
        for day, payee, amount, description in unsorted_entries:
            add_transaction(
                target_month=month,
                day=day,
                payee=payee,
                amount=amount,
                category_role=None,
                description=description,
            )
        account.balance = DEMO_ACCOUNT_BALANCE
        account.available_balance = account.balance
        account.version += 1

        def add_rule(
            *,
            name: str,
            enabled: bool,
            phase: str,
            priority: int,
            conditions: dict,
            actions: list[dict],
            stop_processing: bool = True,
        ) -> None:
            if db.scalar(select(Rule.id).where(Rule.workspace_id == workspace.id, Rule.name == name)):
                return
            rule = Rule(
                workspace_id=workspace.id,
                name=name,
                enabled=enabled,
                phase=phase,
                priority=priority,
                conditions=conditions,
                actions=actions,
                apply_to_manual_overrides=False,
                stop_processing=stop_processing,
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

        add_rule(
            name="Meadowcart Market → Groceries",
            enabled=False,
            phase="categorize",
            priority=100,
            conditions={
                "combinator": "all",
                "children": [
                    {"field": "original_description", "operator": "contains", "value": "MEADOWCART"},
                    {"field": "account_id", "operator": "is", "value": str(account.id)},
                    {"field": "outflow", "operator": "between", "value": ["1", "500"]},
                ],
            },
            actions=[{"type": "assign_category", "category_id": str(by_role["groceries"].id)}],
        )
        add_rule(
            name="Cloudnest → Internet",
            enabled=True,
            phase="categorize",
            priority=110,
            conditions={"field": "original_description", "operator": "contains", "value": "CLOUDNEST"},
            actions=[{"type": "assign_category", "category_id": str(by_role["internet"].id)}],
        )
        add_rule(
            name="Storybox → Entertainment",
            enabled=True,
            phase="categorize",
            priority=120,
            conditions={"field": "original_description", "operator": "contains", "value": "STORYBOX"},
            actions=[{"type": "assign_category", "category_id": str(by_role["entertainment"].id)}],
        )
        add_rule(
            name="Flag large purchases",
            enabled=True,
            phase="finish",
            priority=200,
            conditions={"field": "outflow", "operator": "gt", "value": "500"},
            actions=[{"type": "mark_review"}, {"type": "add_tag", "value": "large-purchase"}],
            stop_processing=False,
        )

        for role, (_section_name, _sort_order, demo_name) in DEMO_CATEGORY_LAYOUT.items():
            category = by_role[role]
            assert category is not None
            category.name = demo_name
            category.version += 1

        db.commit()
        logger.info("Demo budget created for %s through %s", demo_months[0].isoformat()[:7], month.isoformat()[:7])
        logger.info("The Meadowcart rule is disabled so the inbox keeps draggable transactions")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
