from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Account, AuditEvent, BudgetTransaction, Section, SimpleFinConnection
from app.utils import utcnow


def _reset_with_duplicate_candidate() -> tuple[Account, BudgetTransaction, BudgetTransaction, BudgetTransaction]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()
    db = SessionLocal()
    try:
        workspace_id = db.scalar(select(Section.workspace_id).limit(1))
        connection = SimpleFinConnection(
            workspace_id=workspace_id,
            name="Duplicate test",
            access_url_fingerprint=hashlib.sha256(b"duplicate-account-api").hexdigest(),
            enabled=False,
            sync_interval_minutes=180,
            schedule_minute=17,
            next_sync_at=utcnow(),
        )
        db.add(connection)
        db.flush()
        account = Account(
            workspace_id=workspace_id,
            simplefin_connection_id=connection.id,
            source_type="simplefin",
            source_conn_id="institution-duplicate",
            source_account_id="account-duplicate",
            name="Checking duplicate",
            currency="USD",
            is_budget=True,
            is_active=True,
        )
        db.add(account)
        db.flush()
        visible = BudgetTransaction(
            workspace_id=workspace_id,
            account_id=account.id,
            source_kind="simplefin",
            effective_date=date(2026, 8, 20),
            amount=Decimal("-20.00"),
            payee="Visible duplicate",
        )
        independently_excluded = BudgetTransaction(
            workspace_id=workspace_id,
            account_id=account.id,
            source_kind="simplefin",
            effective_date=date(2026, 8, 21),
            amount=Decimal("-21.00"),
            payee="Already excluded",
            excluded=True,
        )
        deleted = BudgetTransaction(
            workspace_id=workspace_id,
            account_id=account.id,
            source_kind="simplefin",
            effective_date=date(2026, 8, 22),
            amount=Decimal("-22.00"),
            payee="Already deleted",
            deleted_at=utcnow(),
        )
        db.add_all([visible, independently_excluded, deleted])
        db.commit()
        for row in (account, visible, independently_excluded, deleted):
            db.refresh(row)
            db.expunge(row)
        return account, visible, independently_excluded, deleted
    finally:
        db.close()


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies["mosaic_csrf"]}


def test_duplicate_account_toggle_suppresses_and_restores_only_owned_exclusions() -> None:
    account, visible, independently_excluded, deleted = _reset_with_duplicate_candidate()

    with TestClient(app) as client:
        headers = _login(client)
        marked = client.patch(
            f"/api/connections/accounts/{account.id}",
            headers=headers,
            json={"version": account.version, "is_duplicate": True},
        )
        assert marked.status_code == 200
        marked_account = marked.json()["account"]
        assert marked_account["is_duplicate"] is True

        budget_accounts = client.get("/api/budget", params={"month": "2026-08"}).json()["accounts"]
        assert str(account.id) not in {item["id"] for item in budget_accounts}
        active_ids = {
            item["id"] for item in client.get("/api/transactions", params={"status": "active"}).json()["transactions"]
        }
        excluded_ids = {
            item["id"]
            for item in client.get("/api/transactions", params={"status": "excluded"}).json()["transactions"]
        }
        assert str(visible.id) not in active_ids | excluded_ids
        assert str(independently_excluded.id) not in excluded_ids

        db = SessionLocal()
        try:
            suppressed = db.get(BudgetTransaction, visible.id)
            untouched_excluded = db.get(BudgetTransaction, independently_excluded.id)
            untouched_deleted = db.get(BudgetTransaction, deleted.id)
            assert suppressed.excluded is True
            assert suppressed.suppressed_by_duplicate_account is True
            assert untouched_excluded.excluded is True
            assert untouched_excluded.suppressed_by_duplicate_account is False
            assert untouched_deleted.excluded is False
            assert untouched_deleted.suppressed_by_duplicate_account is False
            audit = db.scalar(
                select(AuditEvent)
                .where(AuditEvent.object_type == "account", AuditEvent.object_id == account.id)
                .order_by(AuditEvent.created_at.desc())
            )
            assert audit is not None
            assert audit.action == "account.updated"
            assert audit.detail["transactions_suppressed"] == 1
        finally:
            db.close()

        restored = client.patch(
            f"/api/connections/accounts/{account.id}",
            headers=headers,
            json={"version": marked_account["version"], "is_duplicate": False},
        )
        assert restored.status_code == 200
        assert restored.json()["account"]["is_duplicate"] is False
        restored_excluded_ids = {
            item["id"]
            for item in client.get("/api/transactions", params={"status": "excluded"}).json()["transactions"]
        }
        assert str(independently_excluded.id) in restored_excluded_ids

    db = SessionLocal()
    try:
        restored_visible = db.get(BudgetTransaction, visible.id)
        still_excluded = db.get(BudgetTransaction, independently_excluded.id)
        assert restored_visible.excluded is False
        assert restored_visible.suppressed_by_duplicate_account is False
        assert still_excluded.excluded is True
        assert still_excluded.suppressed_by_duplicate_account is False
    finally:
        db.close()


def test_manual_account_cannot_be_marked_duplicate() -> None:
    _reset_with_duplicate_candidate()

    with TestClient(app) as client:
        headers = _login(client)
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        cash = next(item for item in budget["accounts"] if item["source_type"] == "manual")
        response = client.patch(
            f"/api/connections/accounts/{cash['id']}",
            headers=headers,
            json={"version": cash["version"], "is_duplicate": True},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Only SimpleFIN accounts can be marked as duplicates"


def test_budget_account_catalog_includes_accounts_that_are_not_transaction_eligible() -> None:
    account, _visible, _independently_excluded, _deleted = _reset_with_duplicate_candidate()

    with TestClient(app) as client:
        headers = _login(client)
        response = client.patch(
            f"/api/connections/accounts/{account.id}",
            headers=headers,
            json={"version": account.version, "is_active": False, "is_duplicate": True},
        )
        assert response.status_code == 200

        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        assert str(account.id) not in {item["id"] for item in budget["accounts"]}
        catalog_account = next(item for item in budget["account_catalog"] if item["id"] == str(account.id))
        assert catalog_account["name"] == "Checking duplicate"
        assert catalog_account["is_active"] is False
        assert catalog_account["is_duplicate"] is True


def test_manual_account_name_is_trimmed_and_blank_names_are_rejected() -> None:
    _reset_with_duplicate_candidate()

    with TestClient(app) as client:
        headers = _login(client)
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        cash = next(item for item in budget["accounts"] if item["source_type"] == "manual")

        blank = client.patch(
            f"/api/connections/accounts/{cash['id']}",
            headers=headers,
            json={"version": cash["version"], "name": "   "},
        )
        assert blank.status_code == 400
        assert blank.json()["detail"] == "Account name cannot be blank"

        renamed = client.patch(
            f"/api/connections/accounts/{cash['id']}",
            headers=headers,
            json={"version": cash["version"], "name": "  Pocket Money  "},
        )
        assert renamed.status_code == 200
        renamed_account = renamed.json()["account"]
        assert renamed_account["name"] == "Pocket Money"
        assert renamed_account["version"] == cash["version"] + 1

        refreshed = client.get("/api/budget", params={"month": "2026-08"}).json()
        assert next(item for item in refreshed["accounts"] if item["id"] == cash["id"])["name"] == "Pocket Money"
        assert next(item for item in refreshed["account_catalog"] if item["id"] == cash["id"])["name"] == "Pocket Money"

    with SessionLocal() as db:
        audit = db.scalar(
            select(AuditEvent)
            .where(AuditEvent.object_type == "account", AuditEvent.object_id == uuid.UUID(cash["id"]))
            .order_by(AuditEvent.created_at.desc())
        )
        assert audit is not None
        assert audit.action == "account.updated"
        assert audit.before["name"] == "Cash Wallet"
        assert audit.after["name"] == "Pocket Money"
