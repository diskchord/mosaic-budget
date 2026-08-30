from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Account, BudgetTransaction


def _add_unsorted_transactions(count: int, *, offset: int = 0) -> None:
    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.name == "Cash Wallet"))
        assert account is not None
        db.add_all(
            [
                BudgetTransaction(
                    workspace_id=account.workspace_id,
                    account_id=account.id,
                    source_kind="manual",
                    effective_date=date(2026, 8, 15),
                    amount=Decimal("-1"),
                    payee=f"Unsorted {offset + index}",
                )
                for index in range(count)
            ]
        )
        db.commit()


def test_budget_marks_an_unassigned_preview_overflow_after_200_transactions() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()
    _add_unsorted_transactions(200)

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
        )
        assert login.status_code == 200

        exact = client.get("/api/budget", params={"month": "2026-08"})
        assert exact.status_code == 200
        assert len(exact.json()["unassigned"]) == 200
        assert exact.json()["unassigned_has_more"] is False

        _add_unsorted_transactions(1, offset=200)

        overflow = client.get("/api/budget", params={"month": "2026-08"})
        assert overflow.status_code == 200
        assert len(overflow.json()["unassigned"]) == 200
        assert overflow.json()["unassigned_has_more"] is True
