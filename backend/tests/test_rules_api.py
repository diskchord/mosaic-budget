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


def _listed_transaction_ids(client: TestClient, status: str) -> set[str]:
    response = client.get("/api/transactions", params={"status": status})
    assert response.status_code == 200
    return {transaction["id"] for transaction in response.json()["transactions"]}


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
            "transactions_still_unsorted": 0,
        }

        updated_candidate = _transaction(client, candidate["id"])
        assert updated_candidate["payee"] == "Scope candidate"
        assert updated_candidate["version"] == candidate["version"] + 1
        assert [item["category_id"] for item in updated_candidate["allocations"]] == [groceries["id"]]

        refreshed_budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        assert candidate["id"] not in {item["id"] for item in refreshed_budget["unassigned"]}
        assert candidate["id"] not in _listed_transaction_ids(client, "unassigned")
        assert candidate["id"] in _listed_transaction_ids(client, "assigned")

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
                "transactions_still_unsorted": 0,
            }


def test_historical_rule_reports_assignment_failure_as_still_unsorted() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        account = next(item for item in budget["accounts"] if item["name"] == "Cash Wallet")
        food = next(section for section in budget["sections"] if section["name"] == "Food")

        future_category_response = client.post(
            "/api/categories",
            headers=headers,
            json={
                "section_id": food["id"],
                "name": "September only",
                "rollover": False,
                "default_planned": "0",
                "note": "",
                "starts_month": "2026-09-01",
            },
        )
        assert future_category_response.status_code == 200
        future_category = future_category_response.json()["category"]

        transaction = _create_transaction(
            client,
            headers,
            account_id=account["id"],
            effective_date="2026-08-12",
            payee="Unavailable category candidate",
        )
        rule_payload = {
            "name": "Unavailable historical category",
            "enabled": True,
            "phase": "categorize",
            "priority": 10,
            "conditions": {
                "combinator": "all",
                "children": [
                    {
                        "field": "payee",
                        "operator": "is",
                        "value": "Unavailable category candidate",
                    }
                ],
            },
            "actions": [
                {"type": "assign_category", "category_id": future_category["id"]}
            ],
            "apply_to_manual_overrides": True,
            "stop_processing": True,
            "apply_now": "unassigned",
        }
        rule_response = client.post(
            "/api/rules",
            headers=headers,
            json=rule_payload,
        )
        assert rule_response.status_code == 200
        result = rule_response.json()
        assert result["historical_transactions_changed"] == 1
        assert result["historical_transactions_sorted"] == 0
        assert result["historical_transactions_still_unsorted"] == 1

        current = _transaction(client, transaction["id"])
        assert current["allocations"] == []
        assert current["needs_review"] is True
        refreshed_budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        assert transaction["id"] in {item["id"] for item in refreshed_budget["unassigned"]}
        assert transaction["id"] in _listed_transaction_ids(client, "unassigned")
        assert transaction["id"] not in _listed_transaction_ids(client, "assigned")

        update_response = client.patch(
            f"/api/rules/{result['rule']['id']}",
            headers=headers,
            json={**rule_payload, "version": result["rule"]["version"]},
        )
        assert update_response.status_code == 200
        updated_result = update_response.json()
        assert updated_result["historical_transactions_changed"] == 0
        assert updated_result["historical_transactions_sorted"] == 0
        assert updated_result["historical_transactions_still_unsorted"] == 1

        apply_response = client.post(
            f"/api/rules/{result['rule']['id']}/apply",
            headers=headers,
            json={"scope": "unassigned"},
        )
        assert apply_response.status_code == 200
        assert apply_response.json() == {
            "transactions_changed": 0,
            "transactions_sorted": 0,
            "transactions_still_unsorted": 1,
        }

        with SessionLocal() as db:
            audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "rule.created"))
            assert audit is not None
            assert audit.detail == {
                "historical_transactions_changed": 1,
                "historical_transactions_sorted": 0,
                "historical_transactions_still_unsorted": 1,
            }
            updated_audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "rule.updated"))
            assert updated_audit is not None
            assert updated_audit.detail == {
                "historical_transactions_changed": 0,
                "historical_transactions_sorted": 0,
                "historical_transactions_still_unsorted": 1,
            }
            applied_audit = db.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "rule.applied",
                    AuditEvent.object_type == "rule",
                )
            )
            assert applied_audit is not None
            assert applied_audit.detail == {
                "scope": "unassigned",
                "transactions_changed": 0,
                "transactions_sorted": 0,
                "transactions_still_unsorted": 1,
            }
