from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Account, AuditEvent, BudgetTransaction, Workspace


def _signed_in_client() -> tuple[TestClient, dict[str, str]]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    return client, {"X-CSRF-Token": client.cookies["mosaic_csrf"]}


def _budget(client: TestClient, month: str = "2026-08") -> dict:
    response = client.get("/api/budget", params={"month": month})
    assert response.status_code == 200
    return response.json()


def _category(budget: dict, name: str) -> dict:
    return next(
        category
        for section in budget["sections"]
        for category in section["categories"]
        if category["name"] == name
    )


def _cash_account(budget: dict) -> dict:
    return next(account for account in budget["accounts"] if account["name"] == "Cash Wallet")


def _create_transaction(
    client: TestClient,
    headers: dict[str, str],
    account_id: str,
    *,
    payee: str,
    amount: str = "-10",
    effective_date: str = "2026-08-15",
    allocations: list[dict] | None = None,
) -> dict:
    response = client.post(
        "/api/transactions",
        headers=headers,
        json={
            "account_id": account_id,
            "effective_date": effective_date,
            "amount": amount,
            "payee": payee,
            "note": "",
            "allocations": allocations or [],
        },
    )
    assert response.status_code == 200
    return response.json()["transaction"]


def _get_transaction(client: TestClient, transaction_id: str) -> dict:
    response = client.get(f"/api/transactions/{transaction_id}")
    assert response.status_code == 200
    return response.json()["transaction"]


def _refs(*transactions: dict) -> list[dict]:
    return [
        {"id": transaction["id"], "version": transaction["version"]}
        for transaction in transactions
    ]


def _batch_update_audits() -> list[AuditEvent]:
    with SessionLocal() as db:
        return [
            event
            for event in db.scalars(
                select(AuditEvent)
                .where(AuditEvent.action == "transaction.updated")
                .order_by(AuditEvent.created_at, AuditEvent.id)
            ).all()
            if event.detail.get("batch") is True
        ]


def test_batch_update_validates_csrf_changes_and_transaction_refs() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        transaction = _create_transaction(
            client,
            headers,
            _cash_account(budget)["id"],
            payee="Validation",
        )
        valid_body = {"transactions": _refs(transaction), "needs_review": True}

        forbidden = client.patch("/api/transactions/batch", json=valid_body)
        assert forbidden.status_code == 403

        no_changes = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(transaction)},
        )
        assert no_changes.status_code == 422
        assert "Provide at least one transaction change" in no_changes.text

        null_boolean = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(transaction), "excluded": None},
        )
        assert null_boolean.status_code == 422
        assert "excluded must be true or false" in null_boolean.text

        empty = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": [], "needs_review": True},
        )
        assert empty.status_code == 422

        duplicate = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(transaction, transaction), "needs_review": True},
        )
        assert duplicate.status_code == 422
        assert "Include each transaction only once" in duplicate.text

        oversized = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={
                "transactions": [
                    {"id": str(uuid.uuid4()), "version": 1}
                    for _ in range(201)
                ],
                "needs_review": True,
            },
        )
        assert oversized.status_code == 422
        assert _get_transaction(client, transaction["id"])["needs_review"] is False
        assert _batch_update_audits() == []


def test_batch_update_combines_category_review_and_exclusion_in_request_order() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        groceries = _category(budget, "Groceries")
        eating_out = _category(budget, "Eating Out")
        cash = _cash_account(budget)
        unassigned = _create_transaction(
            client,
            headers,
            cash["id"],
            payee="Unassigned",
            amount="-12.25",
        )
        assigned = _create_transaction(
            client,
            headers,
            cash["id"],
            payee="Assigned",
            amount="-7.75",
            allocations=[
                {
                    "category_id": groceries["id"],
                    "amount": "-7.75",
                    "memo": "preserve this memo",
                }
            ],
        )
        reviewed_response = client.patch(
            f"/api/transactions/{assigned['id']}",
            headers=headers,
            json={"version": assigned["version"], "needs_review": True},
        )
        assert reviewed_response.status_code == 200
        assigned = reviewed_response.json()["transaction"]

        response = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={
                "transactions": _refs(assigned, unassigned),
                "category_id": eating_out["id"],
                "needs_review": True,
                "excluded": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["updated_count"] == 2
        updated = payload["transactions"]
        assert [transaction["id"] for transaction in updated] == [assigned["id"], unassigned["id"]]
        assert [transaction["version"] for transaction in updated] == [
            assigned["version"] + 1,
            unassigned["version"] + 1,
        ]
        assert all(transaction["needs_review"] is True for transaction in updated)
        assert all(transaction["excluded"] is True for transaction in updated)
        assert all(transaction["manual_allocation_lock"] is True for transaction in updated)
        assert [transaction["allocations"][0]["amount"] for transaction in updated] == ["-7.75", "-12.25"]
        assert all(
            transaction["allocations"][0]["category_id"] == eating_out["id"]
            for transaction in updated
        )
        assert updated[0]["allocations"][0]["memo"] == "preserve this memo"
        assert updated[1]["allocations"][0]["memo"] == ""

        latest_budget = _budget(client)
        assert _category(latest_budget, "Groceries")["activity"] == "0"
        assert _category(latest_budget, "Eating Out")["activity"] == "0"
        excluded = client.get(
            "/api/transactions",
            params={"month": "2026-08", "status": "excluded"},
        )
        assert excluded.status_code == 200
        assert {transaction["id"] for transaction in excluded.json()["transactions"]} >= {
            assigned["id"],
            unassigned["id"],
        }

        audits = _batch_update_audits()
        assert {str(event.object_id) for event in audits} == {assigned["id"], unassigned["id"]}
        assert all(
            event.detail
            == {
                "batch": True,
                "batch_size": 2,
                "fields": ["category_id", "needs_review", "excluded"],
            }
            for event in audits
        )


def test_batch_category_clears_review_when_omitted_and_exact_noops_do_not_bump() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        groceries = _category(budget, "Groceries")
        eating_out = _category(budget, "Eating Out")
        transaction = _create_transaction(
            client,
            headers,
            _cash_account(budget)["id"],
            payee="Review then move",
            allocations=[
                {"category_id": groceries["id"], "amount": "-10", "memo": "keep"}
            ],
        )
        reviewed_response = client.patch(
            f"/api/transactions/{transaction['id']}",
            headers=headers,
            json={"version": transaction["version"], "needs_review": True},
        )
        assert reviewed_response.status_code == 200
        reviewed = reviewed_response.json()["transaction"]

        moved_response = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(reviewed), "category_id": eating_out["id"]},
        )
        assert moved_response.status_code == 200
        moved = moved_response.json()["transactions"][0]
        assert moved_response.json()["updated_count"] == 1
        assert moved["needs_review"] is False
        assert moved["allocations"][0]["category_id"] == eating_out["id"]
        assert moved["allocations"][0]["memo"] == "keep"

        no_op_response = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={
                "transactions": _refs(moved),
                "category_id": eating_out["id"],
                "needs_review": False,
                "excluded": False,
            },
        )
        assert no_op_response.status_code == 200
        assert no_op_response.json()["updated_count"] == 0
        no_op = no_op_response.json()["transactions"][0]
        assert no_op["version"] == moved["version"]
        assert len(_batch_update_audits()) == 1

        cleared_response = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(no_op), "category_id": None},
        )
        assert cleared_response.status_code == 200
        cleared = cleared_response.json()["transactions"][0]
        assert cleared_response.json()["updated_count"] == 1
        assert cleared["allocations"] == []

        clear_no_op = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(cleared), "category_id": None},
        )
        assert clear_no_op.status_code == 200
        assert clear_no_op.json()["updated_count"] == 0
        assert clear_no_op.json()["transactions"][0]["version"] == cleared["version"]
        assert len(_batch_update_audits()) == 2


def test_batch_category_rejects_splits_without_changing_valid_peers() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        groceries = _category(budget, "Groceries")
        eating_out = _category(budget, "Eating Out")
        cash = _cash_account(budget)
        peer = _create_transaction(client, headers, cash["id"], payee="Peer")
        split = _create_transaction(
            client,
            headers,
            cash["id"],
            payee="Split",
            allocations=[
                {"category_id": groceries["id"], "amount": "-4", "memo": "first"},
                {"category_id": eating_out["id"], "amount": "-6", "memo": "second"},
            ],
        )

        response = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(peer, split), "category_id": groceries["id"]},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Split transactions must be edited individually"
        assert _get_transaction(client, peer["id"])["version"] == peer["version"]
        current_split = _get_transaction(client, split["id"])
        assert current_split["version"] == split["version"]
        assert current_split["allocations"] == split["allocations"]
        assert _batch_update_audits() == []


def test_batch_category_requires_visibility_in_every_selected_transaction_month() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        eating_out = _category(budget, "Eating Out")
        hidden_response = client.put(
            f"/api/categories/{eating_out['id']}/visibility",
            headers=headers,
            json={
                "version": eating_out["version"],
                "month": "2026-09-01",
                "visible": False,
                "scope": "month",
            },
        )
        assert hidden_response.status_code == 200
        cash = _cash_account(_budget(client))
        august = _create_transaction(
            client,
            headers,
            cash["id"],
            payee="August",
            effective_date="2026-08-15",
        )
        september = _create_transaction(
            client,
            headers,
            cash["id"],
            payee="September",
            effective_date="2026-09-15",
        )

        response = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(august, september), "category_id": eating_out["id"]},
        )
        assert response.status_code == 400
        assert "not available" in response.json()["detail"]
        for transaction in (august, september):
            current = _get_transaction(client, transaction["id"])
            assert current["version"] == transaction["version"]
            assert current["allocations"] == []
        assert _batch_update_audits() == []


def test_batch_update_stale_missing_and_foreign_rows_are_atomic() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        cash = _cash_account(budget)
        first = _create_transaction(client, headers, cash["id"], payee="Current")
        second = _create_transaction(client, headers, cash["id"], payee="Stale")
        changed_response = client.patch(
            f"/api/transactions/{second['id']}",
            headers=headers,
            json={"version": second["version"], "note": "changed elsewhere"},
        )
        assert changed_response.status_code == 200
        changed = changed_response.json()["transaction"]

        stale = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(first, second), "needs_review": True},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["conflicts"] == [
            {
                "id": second["id"],
                "expected_version": second["version"],
                "current": changed,
            }
        ]
        assert _get_transaction(client, first["id"])["version"] == first["version"]

        missing = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={
                "transactions": [
                    *_refs(first),
                    {"id": str(uuid.uuid4()), "version": 1},
                ],
                "excluded": True,
            },
        )
        assert missing.status_code == 404
        assert _get_transaction(client, first["id"])["version"] == first["version"]

        with SessionLocal() as db:
            other_workspace = Workspace(name="Other household", currency="USD")
            db.add(other_workspace)
            db.flush()
            other_account = Account(
                workspace_id=other_workspace.id,
                source_type="manual",
                source_conn_id="manual",
                source_account_id="other-manual",
                name="Other cash",
                currency="USD",
                balance=Decimal("0"),
                available_balance=Decimal("0"),
            )
            db.add(other_account)
            db.flush()
            other_transaction = BudgetTransaction(
                workspace_id=other_workspace.id,
                account_id=other_account.id,
                source_kind="manual",
                effective_date=date(2026, 8, 15),
                amount=Decimal("-5"),
                payee="Other workspace",
            )
            db.add(other_transaction)
            db.commit()
            other_id = other_transaction.id
            other_version = other_transaction.version

        foreign = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={
                "transactions": [
                    *_refs(first),
                    {"id": str(other_id), "version": other_version},
                ],
                "needs_review": True,
            },
        )
        assert foreign.status_code == 404
        assert _get_transaction(client, first["id"])["version"] == first["version"]
        with SessionLocal() as db:
            other = db.get(BudgetTransaction, other_id)
            assert other is not None
            assert other.version == other_version
            assert other.needs_review is False
        assert _batch_update_audits() == []


def test_batch_update_rejects_deleted_rows_before_mutating_peers() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        cash = _cash_account(budget)
        peer = _create_transaction(client, headers, cash["id"], payee="Peer")
        deleted = _create_transaction(client, headers, cash["id"], payee="Deleted")
        deleted_response = client.request(
            "DELETE",
            f"/api/transactions/{deleted['id']}",
            headers=headers,
            json={
                "version": deleted["version"],
                "confirm": True,
                "confirm_amount": deleted["amount"],
            },
        )
        assert deleted_response.status_code == 200
        deleted = deleted_response.json()["transaction"]

        response = client.patch(
            "/api/transactions/batch",
            headers=headers,
            json={"transactions": _refs(peer, deleted), "excluded": True},
        )
        assert response.status_code == 400
        assert "Restore deleted transactions" in response.json()["detail"]
        current_peer = _get_transaction(client, peer["id"])
        assert current_peer["version"] == peer["version"]
        assert current_peer["excluded"] is False
        assert _batch_update_audits() == []
