from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import AuditEvent


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


def _create_transaction(
    client: TestClient,
    headers: dict[str, str],
    *,
    account_id: str,
    effective_date: str,
    payee: str,
    category_id: str | None = None,
) -> dict:
    amount = "-10"
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


def _transaction(client: TestClient, transaction_id: str) -> dict:
    response = client.get(f"/api/transactions/{transaction_id}")
    assert response.status_code == 200
    return response.json()["transaction"]


def test_run_rules_scopes_to_unsorted_active_transactions_in_selected_month() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        account = next(item for item in budget["accounts"] if item["name"] == "Cash Wallet")
        groceries = next(
            category
            for section in budget["sections"]
            for category in section["categories"]
            if category["name"] == "Groceries"
        )
        eating_out = next(
            category
            for section in budget["sections"]
            for category in section["categories"]
            if category["name"] == "Eating Out"
        )

        candidate = _create_transaction(
            client,
            headers,
            account_id=account["id"],
            effective_date="2026-08-01",
            payee="Scope candidate",
        )
        assigned = _create_transaction(
            client,
            headers,
            account_id=account["id"],
            effective_date="2026-08-15",
            payee="Scope assigned",
            category_id=eating_out["id"],
        )
        excluded = _create_transaction(
            client,
            headers,
            account_id=account["id"],
            effective_date="2026-08-20",
            payee="Scope excluded",
        )
        excluded_response = client.patch(
            f"/api/transactions/{excluded['id']}",
            headers=headers,
            json={"version": excluded["version"], "excluded": True},
        )
        assert excluded_response.status_code == 200
        excluded = excluded_response.json()["transaction"]

        deleted = _create_transaction(
            client,
            headers,
            account_id=account["id"],
            effective_date="2026-08-22",
            payee="Scope deleted",
        )
        deleted_response = client.request(
            "DELETE",
            f"/api/transactions/{deleted['id']}",
            headers=headers,
            json={"version": deleted["version"], "confirm": True, "confirm_amount": "-10"},
        )
        assert deleted_response.status_code == 200
        deleted = deleted_response.json()["transaction"]

        other_month = _create_transaction(
            client,
            headers,
            account_id=account["id"],
            effective_date="2026-09-01",
            payee="Scope September",
        )

        disabled_response = client.post(
            "/api/rules",
            headers=headers,
            json={
                "name": "Disabled cleanup",
                "enabled": False,
                "phase": "cleanup",
                "priority": 1,
                "conditions": {
                    "combinator": "all",
                    "children": [{"field": "payee", "operator": "contains", "value": "Scope"}],
                },
                "actions": [{"type": "set_payee", "value": "Disabled rule ran"}],
                "apply_to_manual_overrides": True,
                "stop_processing": True,
                "apply_now": "none",
            },
        )
        assert disabled_response.status_code == 200

        enabled_response = client.post(
            "/api/rules",
            headers=headers,
            json={
                "name": "Scope categorizer",
                "enabled": True,
                "phase": "categorize",
                "priority": 10,
                "conditions": {
                    "combinator": "all",
                    "children": [{"field": "payee", "operator": "contains", "value": "Scope"}],
                },
                "actions": [{"type": "assign_category", "category_id": groceries["id"]}],
                "apply_to_manual_overrides": True,
                "stop_processing": True,
                "apply_now": "none",
            },
        )
        assert enabled_response.status_code == 200

        forbidden = client.post("/api/rules/run", json={"month": "2026-08"})
        assert forbidden.status_code == 403

        response = client.post("/api/rules/run", headers=headers, json={"month": "2026-08"})
        assert response.status_code == 200
        assert response.json() == {
            "month": "2026-08",
            "transactions_scanned": 1,
            "transactions_changed": 1,
            "transactions_sorted": 1,
        }

        updated_candidate = _transaction(client, candidate["id"])
        assert updated_candidate["payee"] == "Scope candidate"
        assert updated_candidate["version"] == candidate["version"] + 1
        assert [item["category_id"] for item in updated_candidate["allocations"]] == [groceries["id"]]

        unchanged_assigned = _transaction(client, assigned["id"])
        assert unchanged_assigned["version"] == assigned["version"]
        assert [item["category_id"] for item in unchanged_assigned["allocations"]] == [eating_out["id"]]

        for unchanged in (excluded, deleted, other_month):
            latest = _transaction(client, unchanged["id"])
            assert latest["version"] == unchanged["version"]
            assert latest["allocations"] == []

        with SessionLocal() as db:
            audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "rules.applied"))
            assert audit is not None
            assert audit.object_type == "rule_set"
            assert audit.detail == {
                "scope": "unassigned",
                "month": "2026-08",
                "transactions_scanned": 1,
                "transactions_changed": 1,
                "transactions_sorted": 1,
            }
