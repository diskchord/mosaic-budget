from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import func, select

from .config import get_settings
from .db import SessionLocal
from .models import Account, Category, Section, User, Workspace
from .security import hash_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

DEFAULT_STRUCTURE = [
    (
        "Income",
        True,
        "sparkles",
        "income",
        ["Alex's Piano Service", "Diamond Canine", "Other Income"],
    ),
    ("Housing", False, "home", "housing", ["Land Mortgage", "Electricity", "Heating Oil", "Home Repairs"]),
    ("Food", False, "basket", "food", ["Groceries", "Eating Out"]),
    ("Transportation", False, "car", "transport", ["Fuel", "Vehicle Repairs", "Registration"]),
    ("Subscriptions", False, "repeat", "subscriptions", ["Internet", "Software", "Streaming"]),
    ("Personal", False, "person", "personal", ["Medical", "Clothing", "Gifts"]),
    ("Savings", False, "vault", "savings", ["Emergency Fund", "Taxes", "Major Purchases"]),
]


def bootstrap() -> None:
    db = SessionLocal()
    try:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at).limit(1))
        if workspace is None:
            workspace = Workspace(name="Household Budget", currency="USD")
            db.add(workspace)
            db.flush()
            logger.info("Created the initial workspace")

        owner = db.scalar(select(User).where(User.is_admin.is_(True)).limit(1))
        if owner is None:
            owner = User(
                workspace_id=workspace.id,
                email=str(settings.bootstrap_admin_email).casefold(),
                display_name=settings.bootstrap_admin_name,
                password_hash=hash_password(settings.bootstrap_admin_password),
                is_admin=True,
                is_active=True,
                theme="citrus",
                preferences={"density": "comfortable", "motion": "full", "show_cents": True},
            )
            db.add(owner)
            logger.info("Created administrator %s", owner.email)

        section_count = db.scalar(select(func.count(Section.id)).where(Section.workspace_id == workspace.id)) or 0
        if section_count == 0:
            for section_index, (name, income, icon, accent, category_names) in enumerate(DEFAULT_STRUCTURE):
                section = Section(
                    workspace_id=workspace.id,
                    name=name,
                    is_income=income,
                    icon=icon,
                    accent=accent,
                    sort_order=section_index,
                )
                db.add(section)
                db.flush()
                for category_index, category_name in enumerate(category_names):
                    db.add(
                        Category(
                            section_id=section.id,
                            name=category_name,
                            sort_order=category_index,
                            rollover=category_name in {
                                "Heating Oil",
                                "Home Repairs",
                                "Vehicle Repairs",
                                "Registration",
                                "Taxes",
                                "Emergency Fund",
                                "Major Purchases",
                            },
                            default_planned=Decimal("0"),
                        )
                    )
            logger.info("Created the starter budget structure")

        manual_accounts = db.scalars(
            select(Account).where(Account.workspace_id == workspace.id, Account.source_type == "manual")
        ).all()
        existing_names = {account.name for account in manual_accounts}
        for index, name in enumerate(["Cash Wallet", "Untracked Cash"]):
            if name not in existing_names:
                db.add(
                    Account(
                        workspace_id=workspace.id,
                        source_type="manual",
                        source_conn_id="manual",
                        source_account_id=f"manual-{index}",
                        name=name,
                        currency=workspace.currency,
                        balance=Decimal("0"),
                        available_balance=Decimal("0"),
                        is_budget=True,
                        is_active=True,
                    )
                )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap()
