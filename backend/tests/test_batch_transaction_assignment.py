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


def _category(budget: dict, name: str = "Groceries") -> dict:
    return next(
        category
        for section in budget["sections"]
        for category in section["categories"]
        if category["name"] == name
    )


def _create_transaction(
    client: TestClient,
    headers: dict[str, str],
    account_id: str,
    *,
    payee: str,
    amount: str = "-10",
    effective_date: str = "2026-08-15",
    category_id: str | None = None,
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
            "allocations": (
                [{"category_id": category_id, "amount": amount, "memo": ""}]
                if category_id
                else []
            ),
        },
    )
    assert response.status_code == 200
    return response.json()["transaction"]


def _batch_body(category_id: str | None, *transactions: dict) -> dict:
    return {
        "category_id": category_id,
        "transactions": [
            {"id": transaction["id"], "version": transaction["version"]}
            for transaction in transactions
        ],
    }


def _get_transaction(client: TestClient, transaction_id: str) -> dict:
    response = client.get(f"/api/transactions/{transaction_id}")
    assert response.status_code == 200
    return response.json()["transaction"]


def _batch_audits() -> list[AuditEvent]:
    with SessionLocal() as db:
        return [
            event
            for event in db.scalars(
                select(AuditEvent)
                .where(AuditEvent.action == "transaction.allocations.updated")
                .order_by(AuditEvent.created_at, AuditEvent.id)
            ).all()
            if event.detail.get("batch") is True
        ]


def test_batch_assignment_and_undo_update_every_transaction_and_budget_atomically() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        groceries = _category(budget)
        cash = next(account for account in budget["accounts"] if account["name"] == "Cash Wallet")
        first = _create_transaction(client, headers, cash["id"], payee="First", amount="-12.25")
        second = _create_transaction(client, headers, cash["id"], payee="Second", amount="-7.75")

        response = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(groceries["id"], second, first),
        )
        assert response.status_code == 200
        assigned = response.json()["transactions"]
        assert [transaction["id"] for transaction in assigned] == [second["id"], first["id"]]
        assert [transaction["version"] for transaction in assigned] == [
            second["version"] + 1,
            first["version"] + 1,
        ]
        assert [transaction["allocations"][0]["amount"] for transaction in assigned] == ["-7.75", "-12.25"]
        assert all(transaction["allocations"][0]["category_id"] == groceries["id"] for transaction in assigned)
        assert all(transaction["manual_allocation_lock"] is True for transaction in assigned)
        assert all(transaction["needs_review"] is False for transaction in assigned)

        updated_budget = _budget(client)
        updated_groceries = _category(updated_budget)
        assert updated_groceries["activity"] == "-20"
        assert {transaction["id"] for transaction in updated_budget["unassigned"]}.isdisjoint(
            {first["id"], second["id"]}
        )
        audits = _batch_audits()
        assert {str(event.object_id) for event in audits} == {first["id"], second["id"]}
        assert all(event.detail == {"batch": True, "batch_size": 2} for event in audits)
        assert all(event.before["allocations"] == [] for event in audits)
        assert all(len(event.after["allocations"]) == 1 for event in audits)

        undo = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(None, *assigned),
        )
        assert undo.status_code == 200
        restored = undo.json()["transactions"]
        assert all(transaction["allocations"] == [] for transaction in restored)
        assert [transaction["version"] for transaction in restored] == [
            assigned[0]["version"] + 1,
            assigned[1]["version"] + 1,
        ]
        assert _category(_budget(client))["activity"] == "0"
        assert len(_batch_audits()) == 4


def test_batch_payload_rejects_missing_csrf_empty_duplicate_and_oversized_lists() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        category_id = _category(budget)["id"]
        cash = next(account for account in budget["accounts"] if account["name"] == "Cash Wallet")
        transaction = _create_transaction(client, headers, cash["id"], payee="Validation")

        forbidden = client.put(
            "/api/transactions/batch",
            json=_batch_body(category_id, transaction),
        )
        assert forbidden.status_code == 403

        empty = client.put(
            "/api/transactions/batch",
            headers=headers,
            json={"category_id": category_id, "transactions": []},
        )
        assert empty.status_code == 422

        duplicate = client.put(
            "/api/transactions/batch",
            headers=headers,
            json={
                "category_id": category_id,
                "transactions": [
                    {"id": transaction["id"], "version": transaction["version"]},
                    {"id": transaction["id"], "version": transaction["version"]},
                ],
            },
        )
        assert duplicate.status_code == 422
        assert "Include each transaction only once" in duplicate.text

        oversized = client.put(
            "/api/transactions/batch",
            headers=headers,
            json={
                "category_id": category_id,
                "transactions": [
                    {"id": str(uuid.uuid4()), "version": 1}
                    for _ in range(201)
                ],
            },
        )
        assert oversized.status_code == 422
        assert _get_transaction(client, transaction["id"])["allocations"] == []


def test_batch_assignment_rejects_stale_versions_without_partial_changes() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        groceries = _category(budget)
        cash = next(account for account in budget["accounts"] if account["name"] == "Cash Wallet")
        first = _create_transaction(client, headers, cash["id"], payee="Current")
        second = _create_transaction(client, headers, cash["id"], payee="Stale")
        changed_response = client.patch(
            f"/api/transactions/{second['id']}",
            headers=headers,
            json={"version": second["version"], "note": "changed elsewhere"},
        )
        assert changed_response.status_code == 200
        changed = changed_response.json()["transaction"]

        response = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(groceries["id"], first, second),
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["message"] == "One or more transactions changed on another device"
        assert detail["conflicts"] == [
            {
                "id": second["id"],
                "expected_version": second["version"],
                "current": changed,
            }
        ]
        assert _get_transaction(client, first["id"])["allocations"] == []
        assert _get_transaction(client, first["id"])["version"] == first["version"]
        assert _get_transaction(client, second["id"])["allocations"] == []
        assert len(_batch_audits()) == 0


def test_batch_undo_rejects_stale_versions_without_clearing_current_peers() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        groceries = _category(budget)
        cash = next(account for account in budget["accounts"] if account["name"] == "Cash Wallet")
        first = _create_transaction(client, headers, cash["id"], payee="Undo current")
        second = _create_transaction(client, headers, cash["id"], payee="Undo stale")
        assigned_response = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(groceries["id"], first, second),
        )
        assert assigned_response.status_code == 200
        assigned = assigned_response.json()["transactions"]

        changed_response = client.patch(
            f"/api/transactions/{second['id']}",
            headers=headers,
            json={"version": assigned[1]["version"], "note": "changed after assignment"},
        )
        assert changed_response.status_code == 200
        changed = changed_response.json()["transaction"]

        undo = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(None, *assigned),
        )
        assert undo.status_code == 409
        detail = undo.json()["detail"]
        assert detail["conflicts"] == [
            {
                "id": second["id"],
                "expected_version": assigned[1]["version"],
                "current": changed,
            }
        ]

        current_first = _get_transaction(client, first["id"])
        current_second = _get_transaction(client, second["id"])
        assert current_first["version"] == assigned[0]["version"]
        assert current_first["allocations"] == assigned[0]["allocations"]
        assert current_second["version"] == changed["version"]
        assert current_second["allocations"] == changed["allocations"]
        assert len(_batch_audits()) == 2


def test_batch_assignment_rejects_invalid_transaction_states_without_changing_peers() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        groceries = _category(budget)
        cash = next(account for account in budget["accounts"] if account["name"] == "Cash Wallet")
        peer = _create_transaction(client, headers, cash["id"], payee="Peer")

        missing = client.put(
            "/api/transactions/batch",
            headers=headers,
            json={
                "category_id": groceries["id"],
                "transactions": [
                    {"id": peer["id"], "version": peer["version"]},
                    {"id": str(uuid.uuid4()), "version": 1},
                ],
            },
        )
        assert missing.status_code == 404

        deleted = _create_transaction(client, headers, cash["id"], payee="Deleted")
        deleted_response = client.request(
            "DELETE",
            f"/api/transactions/{deleted['id']}",
            headers=headers,
            json={"version": deleted["version"], "confirm": True, "confirm_amount": deleted["amount"]},
        )
        assert deleted_response.status_code == 200
        deleted = deleted_response.json()["transaction"]
        rejected_deleted = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(groceries["id"], peer, deleted),
        )
        assert rejected_deleted.status_code == 400
        assert "Restore deleted" in rejected_deleted.json()["detail"]

        excluded = _create_transaction(client, headers, cash["id"], payee="Excluded")
        excluded_response = client.patch(
            f"/api/transactions/{excluded['id']}",
            headers=headers,
            json={"version": excluded["version"], "excluded": True},
        )
        assert excluded_response.status_code == 200
        excluded = excluded_response.json()["transaction"]
        rejected_excluded = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(groceries["id"], peer, excluded),
        )
        assert rejected_excluded.status_code == 400
        assert "Excluded transactions" in rejected_excluded.json()["detail"]

        suppressed = _create_transaction(client, headers, cash["id"], payee="Suppressed")
        with SessionLocal() as db:
            row = db.get(BudgetTransaction, uuid.UUID(suppressed["id"]))
            assert row is not None
            row.suppressed_by_duplicate_account = True
            db.commit()
        rejected_suppressed = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(groceries["id"], peer, suppressed),
        )
        assert rejected_suppressed.status_code == 404

        assigned = _create_transaction(
            client,
            headers,
            cash["id"],
            payee="Already assigned",
            category_id=groceries["id"],
        )
        rejected_assigned = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(groceries["id"], peer, assigned),
        )
        assert rejected_assigned.status_code == 400
        assert rejected_assigned.json()["detail"] == "Group assignment accepts only unassigned transactions"

        missing_category = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(str(uuid.uuid4()), peer),
        )
        assert missing_category.status_code == 400
        assert _get_transaction(client, peer["id"])["allocations"] == []
        assert _get_transaction(client, peer["id"])["version"] == peer["version"]
        assert len(_batch_audits()) == 0


def test_batch_assignment_requires_category_availability_for_every_transaction_month() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        groceries = _category(budget)
        cash = next(account for account in budget["accounts"] if account["name"] == "Cash Wallet")
        hidden_response = client.put(
            f"/api/categories/{groceries['id']}/visibility",
            headers=headers,
            json={
                "version": groceries["version"],
                "month": "2026-09-01",
                "visible": False,
                "scope": "month",
            },
        )
        assert hidden_response.status_code == 200
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

        response = client.put(
            "/api/transactions/batch",
            headers=headers,
            json=_batch_body(groceries["id"], august, september),
        )
        assert response.status_code == 400
        assert "not available" in response.json()["detail"]
        assert _get_transaction(client, august["id"])["allocations"] == []
        assert _get_transaction(client, september["id"])["allocations"] == []
        assert len(_batch_audits()) == 0


def test_batch_assignment_does_not_cross_workspaces_or_partially_update_owned_rows() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = _budget(client)
        groceries = _category(budget)
        cash = next(account for account in budget["accounts"] if account["name"] == "Cash Wallet")
        owned = _create_transaction(client, headers, cash["id"], payee="Owned")

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

        response = client.put(
            "/api/transactions/batch",
            headers=headers,
            json={
                "category_id": groceries["id"],
                "transactions": [
                    {"id": owned["id"], "version": owned["version"]},
                    {"id": str(other_id), "version": other_version},
                ],
            },
        )
        assert response.status_code == 404
        assert _get_transaction(client, owned["id"])["allocations"] == []
        with SessionLocal() as db:
            other = db.get(BudgetTransaction, other_id)
            assert other is not None
            assert other.allocations == []
            assert other.version == other_version
        assert len(_batch_audits()) == 0
