from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.api import transactions as transaction_api
from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.models import (
    Account,
    BalanceAlert,
    BudgetTransaction,
    NotificationIncident,
    NotificationOutbox,
    User,
)
from app.schemas import DeleteTransactionRequest, ManualTransactionRequest
from app.services import notifications


def _reset() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notifications.settings, "smtp_host", "mail.smtp2go.test")
    monkeypatch.setattr(notifications.settings, "smtp_from", "mosaic@example.test")
    monkeypatch.setattr(notifications.settings, "smtp_to", "owner@example.test")


def _manual_context(db):
    owner = db.scalar(select(User).where(User.is_admin.is_(True)))
    account = db.scalar(select(Account).where(Account.name == "Cash Wallet"))
    assert owner is not None
    assert account is not None
    return SimpleNamespace(user=owner), account


def test_manual_create_delete_and_restore_evaluate_balance_alerts_immediately(monkeypatch) -> None:
    _reset()
    _enable_smtp(monkeypatch)

    with SessionLocal() as db:
        auth, account = _manual_context(db)
        db.add(
            BalanceAlert(
                workspace_id=auth.user.workspace_id,
                account_id=account.id,
                account=account,
                name="Cash floor crossed",
                comparison="below",
                threshold=Decimal("-50"),
                channels=["smtp"],
                enabled=True,
                created_by_id=auth.user.id,
            )
        )
        db.commit()

        created = transaction_api.create_manual_transaction(
            ManualTransactionRequest(
                account_id=account.id,
                effective_date=date(2026, 8, 28),
                amount="-60",
                payee="Temporary cash outflow",
                allocations=[],
            ),
            auth,
            db,
        )["transaction"]

        assert Decimal(db.get(Account, account.id).balance) == Decimal("-60")
        incidents = db.scalars(select(NotificationIncident)).all()
        deliveries = db.scalars(select(NotificationOutbox)).all()
        assert len(incidents) == 1
        assert incidents[0].status == "open"
        assert len(deliveries) == 1
        assert "Cash Wallet balance is USD -60" in deliveries[0].payload["message"]
        assert "threshold of USD -50" in deliveries[0].payload["message"]

        deleted = transaction_api.delete_transaction(
            UUID(created["id"]),
            DeleteTransactionRequest(
                version=created["version"],
                confirm=True,
                confirm_amount=created["amount"],
            ),
            auth,
            db,
        )["transaction"]

        assert Decimal(db.get(Account, account.id).balance) == Decimal("0")
        deliveries = db.scalars(select(NotificationOutbox)).all()
        assert len(deliveries) == 2
        assert {delivery.payload["title"] for delivery in deliveries} == {
            "Cash floor crossed",
            "Resolved: Cash floor crossed",
        }

        transaction_api.restore_transaction(
            UUID(deleted["id"]),
            deleted["version"],
            auth,
            db,
        )

        assert Decimal(db.get(Account, account.id).balance) == Decimal("-60")
        incidents = db.scalars(select(NotificationIncident)).all()
        deliveries = db.scalars(select(NotificationOutbox)).all()
        assert sorted(incident.status for incident in incidents) == ["open", "resolved"]
        assert len(deliveries) == 3
        assert [delivery.payload["title"] for delivery in deliveries].count("Cash floor crossed") == 2


def test_manual_balance_mutation_rolls_back_when_alert_evaluation_fails(monkeypatch) -> None:
    _reset()

    def fail_evaluation(*_args, **_kwargs):
        raise RuntimeError("alert evaluation failed")

    monkeypatch.setattr(transaction_api, "evaluate_balance_alerts", fail_evaluation)

    with SessionLocal() as db:
        auth, account = _manual_context(db)
        with pytest.raises(RuntimeError, match="alert evaluation failed"):
            transaction_api.create_manual_transaction(
                ManualTransactionRequest(
                    account_id=account.id,
                    effective_date=date(2026, 8, 28),
                    amount="25",
                    payee="Rolled back cash deposit",
                    allocations=[],
                ),
                auth,
                db,
            )
        db.rollback()

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.name == "Cash Wallet"))
        assert account is not None
        assert Decimal(account.balance) == Decimal("0")
        assert db.scalar(select(func.count(BudgetTransaction.id))) == 0
