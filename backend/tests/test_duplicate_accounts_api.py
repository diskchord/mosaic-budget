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


def _add_duplicate_peer(account: Account) -> tuple[Account, BudgetTransaction]:
    with SessionLocal() as db:
        original = db.get(Account, account.id)
        assert original is not None
        peer = Account(
            workspace_id=original.workspace_id,
            simplefin_connection_id=original.simplefin_connection_id,
            source_type="simplefin",
            source_conn_id="institution-duplicate",
            source_account_id="account-restorable",
            name="Savings duplicate",
            currency="USD",
            is_budget=True,
            is_active=True,
            is_duplicate=True,
        )
        db.add(peer)
        db.flush()
        transaction = BudgetTransaction(
            workspace_id=original.workspace_id,
            account_id=peer.id,
            source_kind="simplefin",
            effective_date=date(2026, 8, 23),
            amount=Decimal("-23.00"),
            payee="Suppressed peer transaction",
            excluded=True,
            suppressed_by_duplicate_account=True,
        )
        db.add(transaction)
        db.commit()
        for row in (peer, transaction):
            db.refresh(row)
            db.expunge(row)
        return peer, transaction


def _batch_account_item(account: Account, **changes: object) -> dict:
    item = {
        "id": str(account.id),
        "version": account.version,
        "name": account.name,
        "is_budget": account.is_budget,
        "is_active": account.is_active,
        "is_duplicate": account.is_duplicate,
    }
    item.update(changes)
    return item


def _serialized_batch_account_item(account: dict) -> dict:
    return {
        key: account[key]
        for key in ("id", "version", "name", "is_budget", "is_active", "is_duplicate")
    }


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
        inactive_response = client.patch(
            f"/api/connections/accounts/{account.id}",
            headers=headers,
            json={"version": account.version, "is_active": False},
        )
        assert inactive_response.status_code == 200

        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        assert str(account.id) not in {item["id"] for item in budget["accounts"]}
        catalog_account = next(item for item in budget["account_catalog"] if item["id"] == str(account.id))
        assert catalog_account["name"] == "Checking duplicate"
        assert catalog_account["is_active"] is False
        assert catalog_account["is_duplicate"] is False

        duplicate_response = client.patch(
            f"/api/connections/accounts/{account.id}",
            headers=headers,
            json={
                "version": inactive_response.json()["account"]["version"],
                "is_active": True,
                "is_duplicate": True,
            },
        )
        assert duplicate_response.status_code == 200

        duplicate_budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        assert str(account.id) not in {item["id"] for item in duplicate_budget["accounts"]}
        catalog_account = next(
            item for item in duplicate_budget["account_catalog"] if item["id"] == str(account.id)
        )
        assert catalog_account["is_active"] is True
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


def test_batch_account_update_saves_two_accounts_in_request_order_and_is_idempotent() -> None:
    account, visible, independently_excluded, _deleted = _reset_with_duplicate_candidate()
    peer, peer_transaction = _add_duplicate_peer(account)

    with TestClient(app) as client:
        headers = _login(client)
        response = client.patch(
            f"/api/connections/{account.simplefin_connection_id}/accounts",
            headers=headers,
            json={
                "accounts": [
                    _batch_account_item(
                        peer,
                        name="  Everyday Savings  ",
                        is_budget=False,
                        is_active=False,
                        is_duplicate=False,
                    ),
                    _batch_account_item(account, name="  Primary Checking  ", is_duplicate=True),
                ]
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["updated_count"] == 2
        assert [item["id"] for item in result["accounts"]] == [str(peer.id), str(account.id)]

        updated_peer, updated_account = result["accounts"]
        assert updated_peer["name"] == "Everyday Savings"
        assert updated_peer["version"] == peer.version + 1
        assert updated_peer["is_budget"] is False
        assert updated_peer["is_active"] is False
        assert updated_peer["is_duplicate"] is False
        assert updated_account["name"] == "Primary Checking"
        assert updated_account["version"] == account.version + 1
        assert updated_account["is_duplicate"] is True

        unchanged = client.patch(
            f"/api/connections/{account.simplefin_connection_id}/accounts",
            headers=headers,
            json={"accounts": [_serialized_batch_account_item(item) for item in result["accounts"]]},
        )
        assert unchanged.status_code == 200
        assert unchanged.json() == {"accounts": result["accounts"], "updated_count": 0}

    with SessionLocal() as db:
        suppressed = db.get(BudgetTransaction, visible.id)
        untouched_excluded = db.get(BudgetTransaction, independently_excluded.id)
        restored = db.get(BudgetTransaction, peer_transaction.id)
        assert suppressed is not None
        assert suppressed.excluded is True
        assert suppressed.suppressed_by_duplicate_account is True
        assert untouched_excluded is not None
        assert untouched_excluded.excluded is True
        assert untouched_excluded.suppressed_by_duplicate_account is False
        assert restored is not None
        assert restored.excluded is False
        assert restored.suppressed_by_duplicate_account is False

        audits = db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == "account.updated")
            .order_by(AuditEvent.object_id)
        ).all()
        assert len(audits) == 2
        audits_by_account = {audit.object_id: audit for audit in audits}
        assert audits_by_account[account.id].detail == {
            "transactions_suppressed": 1,
            "transactions_restored": 0,
        }
        assert audits_by_account[peer.id].detail == {
            "transactions_suppressed": 0,
            "transactions_restored": 1,
        }


def test_batch_account_update_reports_all_stale_rows_without_partial_changes() -> None:
    account, visible, _independently_excluded, _deleted = _reset_with_duplicate_candidate()
    peer, _peer_transaction = _add_duplicate_peer(account)

    with SessionLocal() as db:
        current_peer_row = db.get(Account, peer.id)
        assert current_peer_row is not None
        current_peer_row.name = "Changed elsewhere"
        current_peer_row.version += 1
        db.commit()
        db.refresh(current_peer_row)
        current_peer_version = current_peer_row.version

    with TestClient(app) as client:
        headers = _login(client)
        current_peer = next(
            item
            for item in client.get(
                f"/api/connections/{account.simplefin_connection_id}/accounts"
            ).json()["accounts"]
            if item["id"] == str(peer.id)
        )
        response = client.patch(
            f"/api/connections/{account.simplefin_connection_id}/accounts",
            headers=headers,
            json={
                "accounts": [
                    _batch_account_item(account, name="Must not save", is_duplicate=True),
                    _batch_account_item(peer, name="Also must not save", is_duplicate=False),
                ]
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "message": "One or more accounts changed on another device",
            "conflicts": [
                {
                    "id": str(peer.id),
                    "expected_version": peer.version,
                    "current": current_peer,
                }
            ],
        }
        assert current_peer["name"] == "Changed elsewhere"
        assert current_peer["version"] == current_peer_version

    with SessionLocal() as db:
        current_account = db.get(Account, account.id)
        current_transaction = db.get(BudgetTransaction, visible.id)
        assert current_account is not None
        assert current_account.name == account.name
        assert current_account.version == account.version
        assert current_account.is_duplicate is False
        assert current_transaction is not None
        assert current_transaction.excluded is False
        assert current_transaction.suppressed_by_duplicate_account is False
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "account.updated")) is None


def test_batch_account_update_rejects_invalid_requests_without_partial_changes() -> None:
    account, visible, _independently_excluded, _deleted = _reset_with_duplicate_candidate()
    peer, _peer_transaction = _add_duplicate_peer(account)

    with TestClient(app) as client:
        headers = _login(client)
        blank = client.patch(
            f"/api/connections/{account.simplefin_connection_id}/accounts",
            headers=headers,
            json={
                "accounts": [
                    _batch_account_item(account, name="Must not save", is_duplicate=True),
                    _batch_account_item(peer, name="   ", is_duplicate=False),
                ]
            },
        )
        assert blank.status_code == 422

        duplicate = client.patch(
            f"/api/connections/{account.simplefin_connection_id}/accounts",
            headers=headers,
            json={
                "accounts": [
                    _batch_account_item(account, name="Must not save", is_duplicate=True),
                    _batch_account_item(account, name="Still must not save", is_duplicate=True),
                ]
            },
        )
        assert duplicate.status_code == 422

        missing = client.patch(
            f"/api/connections/{account.simplefin_connection_id}/accounts",
            headers=headers,
            json={
                "accounts": [
                    _batch_account_item(account, name="Must not save", is_duplicate=True),
                    {
                        "id": str(uuid.uuid4()),
                        "version": 1,
                        "name": "Missing account",
                        "is_budget": True,
                        "is_active": True,
                        "is_duplicate": False,
                    },
                ]
            },
        )
        assert missing.status_code == 404

        with SessionLocal() as db:
            invalid_peer = db.get(Account, peer.id)
            assert invalid_peer is not None
            invalid_peer.source_type = "manual"
            db.commit()

        invalid_source = client.patch(
            f"/api/connections/{account.simplefin_connection_id}/accounts",
            headers=headers,
            json={
                "accounts": [
                    _batch_account_item(account, name="Must not save", is_duplicate=True),
                    _batch_account_item(peer, name="Invalid source", is_duplicate=False),
                ]
            },
        )
        assert invalid_source.status_code == 400
        assert invalid_source.json()["detail"] == "Only SimpleFIN accounts can be updated through a connection"

    with SessionLocal() as db:
        current_account = db.get(Account, account.id)
        current_transaction = db.get(BudgetTransaction, visible.id)
        assert current_account is not None
        assert current_account.name == account.name
        assert current_account.version == account.version
        assert current_account.is_duplicate is False
        assert current_transaction is not None
        assert current_transaction.excluded is False
        assert current_transaction.suppressed_by_duplicate_account is False
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "account.updated")) is None


def test_batch_account_update_requires_the_workspace_owner() -> None:
    account, _visible, _independently_excluded, _deleted = _reset_with_duplicate_candidate()

    with TestClient(app) as owner_client:
        owner_headers = _login(owner_client)
        created = owner_client.post(
            "/api/admin/users",
            headers=owner_headers,
            json={
                "email": "member@example.com",
                "display_name": "Household member",
                "password": "member-password-1234",
                "is_admin": False,
            },
        )
        assert created.status_code == 200

    with TestClient(app) as member_client:
        login = member_client.post(
            "/api/auth/login",
            json={"email": "member@example.com", "password": "member-password-1234"},
        )
        assert login.status_code == 200
        response = member_client.patch(
            f"/api/connections/{account.simplefin_connection_id}/accounts",
            headers={"X-CSRF-Token": member_client.cookies["mosaic_csrf"]},
            json={"accounts": [_batch_account_item(account, name="Must not save")]},
        )
        assert response.status_code == 403

    with SessionLocal() as db:
        current_account = db.get(Account, account.id)
        assert current_account is not None
        assert current_account.name == account.name
        assert current_account.version == account.version
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "account.updated")) is None
