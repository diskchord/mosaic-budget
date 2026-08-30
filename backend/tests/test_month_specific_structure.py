from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import AuditEvent, Category, CategoryBudget, Rule


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


def _budget(client: TestClient, month: str) -> dict:
    response = client.get("/api/budget", params={"month": month})
    assert response.status_code == 200
    return response.json()


def _category_in_budget(budget: dict, category_id: str) -> bool:
    return any(category["id"] == category_id for section in budget["sections"] for category in section["categories"])


def _section_in_budget(budget: dict, section_id: str) -> bool:
    return any(section["id"] == section_id for section in budget["sections"])


def _create_transaction(
    client: TestClient,
    headers: dict[str, str],
    *,
    account_id: str,
    effective_date: str,
    amount: str,
    payee: str,
    allocations: list[dict],
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
            "allocations": allocations,
        },
    )
    assert response.status_code == 200
    return response.json()["transaction"]


def _transaction(client: TestClient, transaction_id: str) -> dict:
    response = client.get(f"/api/transactions/{transaction_id}")
    assert response.status_code == 200
    return response.json()["transaction"]


def _category_rule_payload(name: str, category_id: str) -> dict:
    return {
        "name": name,
        "enabled": True,
        "phase": "categorize",
        "priority": 100,
        "conditions": {"field": "payee", "operator": "contains", "value": name},
        "actions": [{"type": "assign_category", "category_id": category_id}],
        "apply_to_manual_overrides": False,
        "stop_processing": True,
        "apply_now": "none",
    }


def test_category_lifetime_carries_forward_and_can_have_a_finite_gap() -> None:
    client, headers = _signed_in_client()
    with client:
        august = _budget(client, "2026-08")
        food = next(section for section in august["sections"] if section["name"] == "Food")
        created_response = client.post(
            "/api/categories",
            headers=headers,
            json={
                "section_id": food["id"],
                "name": "School Lunch",
                "sort_order": 2,
                "rollover": False,
                "default_planned": "80",
                "note": "",
                "starts_month": "2026-09-01",
            },
        )
        assert created_response.status_code == 200
        category = created_response.json()["category"]

        august = _budget(client, "2026-08")
        assert not _category_in_budget(august, category["id"])
        hidden = next(item for item in august["hidden_structure"]["categories"] if item["id"] == category["id"])
        assert hidden["visibility_reason"] == "not_started"
        assert _category_in_budget(_budget(client, "2026-09"), category["id"])
        assert _category_in_budget(_budget(client, "2026-10"), category["id"])

        hidden_once_response = client.put(
            f"/api/categories/{category['id']}/visibility",
            headers=headers,
            json={"version": category["version"], "month": "2026-09-01", "visible": False, "scope": "month"},
        )
        assert hidden_once_response.status_code == 200
        category = hidden_once_response.json()["category"]
        assert not _category_in_budget(_budget(client, "2026-09"), category["id"])
        assert _category_in_budget(_budget(client, "2026-10"), category["id"])

        restored_response = client.put(
            f"/api/categories/{category['id']}/visibility",
            headers=headers,
            json={"version": category["version"], "month": "2026-09-01", "visible": True, "scope": "month"},
        )
        assert restored_response.status_code == 200
        category = restored_response.json()["category"]
        assert _category_in_budget(_budget(client, "2026-09"), category["id"])

        ended_response = client.put(
            f"/api/categories/{category['id']}/visibility",
            headers=headers,
            json={"version": category["version"], "month": "2026-10-01", "visible": False, "scope": "forward"},
        )
        assert ended_response.status_code == 200
        category = ended_response.json()["category"]
        assert _category_in_budget(_budget(client, "2026-09"), category["id"])
        assert not _category_in_budget(_budget(client, "2026-10"), category["id"])
        assert not _category_in_budget(_budget(client, "2026-11"), category["id"])

        resumed_response = client.put(
            f"/api/categories/{category['id']}/visibility",
            headers=headers,
            json={"version": category["version"], "month": "2026-12-01", "visible": True, "scope": "forward"},
        )
        assert resumed_response.status_code == 200
        assert _category_in_budget(_budget(client, "2026-09"), category["id"])
        assert not _category_in_budget(_budget(client, "2026-10"), category["id"])
        assert not _category_in_budget(_budget(client, "2026-11"), category["id"])
        assert _category_in_budget(_budget(client, "2026-12"), category["id"])
        assert _category_in_budget(_budget(client, "2027-01"), category["id"])


def test_section_visibility_controls_its_categories_without_destroying_them() -> None:
    client, headers = _signed_in_client()
    with client:
        created_response = client.post(
            "/api/sections",
            headers=headers,
            json={
                "name": "Education",
                "icon": "sparkles",
                "accent": "accent",
                "sort_order": 2,
                "starts_month": "2026-11-01",
            },
        )
        assert created_response.status_code == 200
        section = created_response.json()["section"]
        category_response = client.post(
            "/api/categories",
            headers=headers,
            json={
                "section_id": section["id"],
                "name": "Tuition",
                "sort_order": 0,
                "rollover": False,
                "default_planned": "500",
                "note": "",
                "starts_month": "2026-11-01",
            },
        )
        assert category_response.status_code == 200

        assert not _section_in_budget(_budget(client, "2026-10"), section["id"])
        assert _section_in_budget(_budget(client, "2026-11"), section["id"])

        hidden_response = client.put(
            f"/api/sections/{section['id']}/visibility",
            headers=headers,
            json={"version": section["version"], "month": "2026-12-01", "visible": False, "scope": "month"},
        )
        assert hidden_response.status_code == 200
        assert not _section_in_budget(_budget(client, "2026-12"), section["id"])
        january = _budget(client, "2027-01")
        assert _section_in_budget(january, section["id"])
        restored_section = next(item for item in january["sections"] if item["id"] == section["id"])
        assert [category["name"] for category in restored_section["categories"]] == ["Tuition"]


def test_budget_rows_are_created_only_for_visible_months() -> None:
    client, headers = _signed_in_client()
    with client:
        food = next(section for section in _budget(client, "2026-08")["sections"] if section["name"] == "Food")
        response = client.post(
            "/api/categories",
            headers=headers,
            json={
                "section_id": food["id"],
                "name": "Seasonal Produce",
                "sort_order": 2,
                "rollover": False,
                "default_planned": "42",
                "note": "",
                "starts_month": "2026-09-01",
            },
        )
        category_id = response.json()["category"]["id"]
        _budget(client, "2026-08")
        with SessionLocal() as db:
            assert db.scalar(
                select(CategoryBudget).where(
                    CategoryBudget.category_id == uuid.UUID(category_id),
                    CategoryBudget.month == date(2026, 8, 1),
                )
            ) is None
        september = _budget(client, "2026-09")
        category = next(
            item for section in september["sections"] for item in section["categories"] if item["id"] == category_id
        )
        assert category["planned"] == "42"


def test_new_allocations_reject_categories_hidden_for_transaction_month() -> None:
    client, headers = _signed_in_client()
    with client:
        september = _budget(client, "2026-09")
        food = next(section for section in september["sections"] if section["name"] == "Food")
        account = september["accounts"][0]
        response = client.post(
            "/api/categories",
            headers=headers,
            json={
                "section_id": food["id"],
                "name": "September Only",
                "sort_order": 2,
                "rollover": False,
                "default_planned": "0",
                "note": "",
                "starts_month": "2026-09-01",
            },
        )
        category = response.json()["category"]
        hidden_response = client.put(
            f"/api/categories/{category['id']}/visibility",
            headers=headers,
            json={"version": category["version"], "month": "2026-09-01", "visible": False, "scope": "month"},
        )
        assert hidden_response.status_code == 200

        transaction_response = client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": account["id"],
                "effective_date": "2026-09-15",
                "amount": "-12.50",
                "payee": "Test",
                "note": "",
                "allocations": [{"category_id": category["id"], "amount": "-12.50", "memo": ""}],
            },
        )
        assert transaction_response.status_code == 400
        assert "not available" in transaction_response.json()["detail"]


def test_hiding_a_category_preserves_its_plan_activity_and_history() -> None:
    client, headers = _signed_in_client()
    with client:
        august = _budget(client, "2026-08")
        groceries = next(
            category
            for section in august["sections"]
            for category in section["categories"]
            if category["name"] == "Groceries"
        )
        cash = next(account for account in august["accounts"] if account["name"] == "Cash Wallet")

        planned_response = client.put(
            f"/api/budget/2026-08/categories/{groceries['id']}",
            headers=headers,
            json={"version": groceries["budget_version"], "planned": "300"},
        )
        assert planned_response.status_code == 200
        transaction_response = client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": cash["id"],
                "effective_date": "2026-08-20",
                "amount": "-25",
                "payee": "Hannaford",
                "note": "",
                "allocations": [{"category_id": groceries["id"], "amount": "-25", "memo": ""}],
            },
        )
        assert transaction_response.status_code == 200

        hidden_response = client.put(
            f"/api/categories/{groceries['id']}/visibility",
            headers=headers,
            json={"version": groceries["version"], "month": "2026-08-01", "visible": False, "scope": "month"},
        )
        assert hidden_response.status_code == 200
        category = hidden_response.json()["category"]

        hidden_budget = _budget(client, "2026-08")
        assert not _category_in_budget(hidden_budget, groceries["id"])
        assert hidden_budget["summary"]["actual_expenses"] == "25"
        assert hidden_budget["summary"]["actual_cash_flow"] == "-25"
        assert hidden_budget["summary"]["hidden_activity"] == "-25"
        assert hidden_budget["summary"]["hidden_planned"] == "300"
        hidden_item = next(
            item for item in hidden_budget["hidden_structure"]["categories"] if item["id"] == groceries["id"]
        )
        assert hidden_item["planned"] == "300"
        assert hidden_item["activity"] == "-25"

        restored_response = client.put(
            f"/api/categories/{groceries['id']}/visibility",
            headers=headers,
            json={"version": category["version"], "month": "2026-08-01", "visible": True, "scope": "month"},
        )
        assert restored_response.status_code == 200
        restored_budget = _budget(client, "2026-08")
        restored = next(
            item
            for section in restored_budget["sections"]
            for item in section["categories"]
            if item["id"] == groceries["id"]
        )
        assert restored["planned"] == "300"
        assert restored["activity"] == "-25"
        assert restored["remaining"] == "275"


def test_category_can_be_archived_everywhere_and_restored_everywhere() -> None:
    client, headers = _signed_in_client()
    with client:
        august = _budget(client, "2026-08")
        streaming = next(
            category
            for section in august["sections"]
            for category in section["categories"]
            if category["name"] == "Streaming"
        )
        archived_response = client.put(
            f"/api/categories/{streaming['id']}/visibility",
            headers=headers,
            json={"version": streaming["version"], "month": "2026-08-01", "visible": False, "scope": "all"},
        )
        assert archived_response.status_code == 200
        archived = archived_response.json()["category"]
        for month in ("2026-07", "2026-08", "2027-01"):
            budget = _budget(client, month)
            assert not _category_in_budget(budget, streaming["id"])
            hidden = next(item for item in budget["hidden_structure"]["categories"] if item["id"] == streaming["id"])
            assert hidden["visibility_reason"] == "archived"

        restored_response = client.put(
            f"/api/categories/{streaming['id']}/visibility",
            headers=headers,
            json={"version": archived["version"], "month": "2026-08-01", "visible": True, "scope": "all"},
        )
        assert restored_response.status_code == 200
        for month in ("2026-07", "2026-08", "2027-01"):
            assert _category_in_budget(_budget(client, month), streaming["id"])


def test_income_section_cannot_be_hidden_in_any_scope() -> None:
    client, headers = _signed_in_client()
    with client:
        income = next(section for section in _budget(client, "2026-08")["sections"] if section["is_income"])
        for scope in ("month", "forward", "all"):
            response = client.put(
                f"/api/sections/{income['id']}/visibility",
                headers=headers,
                json={"version": income["version"], "month": "2026-08-01", "visible": False, "scope": scope},
            )
            assert response.status_code == 400
            assert "protected" in response.json()["detail"]


def test_hiding_a_section_rejects_new_allocations_to_its_categories() -> None:
    client, headers = _signed_in_client()
    with client:
        september = _budget(client, "2026-09")
        food = next(section for section in september["sections"] if section["name"] == "Food")
        groceries = next(category for category in food["categories"] if category["name"] == "Groceries")
        cash = next(account for account in september["accounts"] if account["name"] == "Cash Wallet")

        hidden_response = client.put(
            f"/api/sections/{food['id']}/visibility",
            headers=headers,
            json={"version": food["version"], "month": "2026-09-01", "visible": False, "scope": "month"},
        )
        assert hidden_response.status_code == 200
        response = client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": cash["id"],
                "effective_date": "2026-09-20",
                "amount": "-10",
                "payee": "Test",
                "note": "",
                "allocations": [{"category_id": groceries["id"], "amount": "-10", "memo": ""}],
            },
        )
        assert response.status_code == 400
        assert "not available" in response.json()["detail"]


def test_transaction_month_and_category_can_change_atomically() -> None:
    client, headers = _signed_in_client()
    with client:
        august = _budget(client, "2026-08")
        food = next(section for section in august["sections"] if section["name"] == "Food")
        groceries = next(category for category in food["categories"] if category["name"] == "Groceries")
        cash = next(account for account in august["accounts"] if account["name"] == "Cash Wallet")
        future_response = client.post(
            "/api/categories",
            headers=headers,
            json={
                "section_id": food["id"],
                "name": "September Food",
                "sort_order": 2,
                "rollover": False,
                "default_planned": "0",
                "note": "",
                "starts_month": "2026-09-01",
            },
        )
        assert future_response.status_code == 200
        future = future_response.json()["category"]
        hidden_response = client.put(
            f"/api/categories/{groceries['id']}/visibility",
            headers=headers,
            json={"version": groceries["version"], "month": "2026-09-01", "visible": False, "scope": "month"},
        )
        assert hidden_response.status_code == 200

        created_response = client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": cash["id"],
                "effective_date": "2026-08-31",
                "amount": "-18",
                "payee": "Market",
                "note": "",
                "allocations": [{"category_id": groceries["id"], "amount": "-18", "memo": ""}],
            },
        )
        assert created_response.status_code == 200
        transaction = created_response.json()["transaction"]

        date_only = client.patch(
            f"/api/transactions/{transaction['id']}",
            headers=headers,
            json={"version": transaction["version"], "effective_date": "2026-09-01"},
        )
        assert date_only.status_code == 400
        assert "not available" in date_only.json()["detail"]

        combined = client.patch(
            f"/api/transactions/{transaction['id']}",
            headers=headers,
            json={
                "version": transaction["version"],
                "effective_date": "2026-09-01",
                "allocations": [{"category_id": future["id"], "amount": "-18", "memo": ""}],
            },
        )
        assert combined.status_code == 200
        updated = combined.json()["transaction"]
        assert updated["effective_date"] == "2026-09-01"
        assert updated["allocations"][0]["category_id"] == future["id"]


def test_permanent_category_delete_preserves_earlier_structure_and_decategorizes_every_split() -> None:
    client, headers = _signed_in_client()
    with client:
        july = _budget(client, "2026-07")
        august = _budget(client, "2026-08")
        food = next(section for section in august["sections"] if section["name"] == "Food")
        groceries = next(category for category in food["categories"] if category["name"] == "Groceries")
        dining = next(category for category in food["categories"] if category["name"] == "Eating Out")
        cash = next(account for account in august["accounts"] if account["name"] == "Cash Wallet")
        assert _category_in_budget(july, groceries["id"])

        past = _create_transaction(
            client,
            headers,
            account_id=cash["id"],
            effective_date="2026-07-10",
            amount="-15",
            payee="Past groceries",
            allocations=[{"category_id": groceries["id"], "amount": "-15", "memo": ""}],
        )
        split = _create_transaction(
            client,
            headers,
            account_id=cash["id"],
            effective_date="2026-08-10",
            amount="-30",
            payee="Split purchase",
            allocations=[
                {"category_id": groceries["id"], "amount": "-10", "memo": ""},
                {"category_id": dining["id"], "amount": "-20", "memo": ""},
            ],
        )
        reviewed_response = client.patch(
            f"/api/transactions/{split['id']}",
            headers=headers,
            json={"version": split["version"], "needs_review": True},
        )
        assert reviewed_response.status_code == 200
        split = reviewed_response.json()["transaction"]
        unrelated = _create_transaction(
            client,
            headers,
            account_id=cash["id"],
            effective_date="2026-08-11",
            amount="-12",
            payee="Dinner",
            allocations=[{"category_id": dining["id"], "amount": "-12", "memo": ""}],
        )
        rule_response = client.post(
            "/api/rules",
            headers=headers,
            json=_category_rule_payload("Grocery rule", groceries["id"]),
        )
        assert rule_response.status_code == 200
        rule = rule_response.json()["rule"]

        deleted_response = client.request(
            "DELETE",
            f"/api/categories/{groceries['id']}",
            headers=headers,
            json={"version": groceries["version"], "month": "2026-08-01"},
        )
        assert deleted_response.status_code == 200
        result = deleted_response.json()
        assert result["transactions_decategorized"] == 2
        assert result["rules_disabled"] == 1

        for original in (past, split):
            updated = _transaction(client, original["id"])
            assert updated["allocations"] == []
            assert updated["version"] == original["version"] + 1
            assert updated["manual_allocation_lock"] is True
            assert updated["needs_review"] is False
        assert _transaction(client, unrelated["id"])["allocations"][0]["category_id"] == dining["id"]

        earlier = _budget(client, "2026-07")
        earlier_category = next(
            category
            for section in earlier["sections"]
            for category in section["categories"]
            if category["id"] == groceries["id"]
        )
        assert earlier_category["deleted_from_month"] == "2026-08"
        for month in ("2026-08", "2026-09"):
            budget = _budget(client, month)
            assert not _category_in_budget(budget, groceries["id"])
            assert all(item["id"] != groceries["id"] for item in budget["category_catalog"])
            assert all(item["id"] != groceries["id"] for item in budget["hidden_structure"]["categories"])

        with SessionLocal() as db:
            category = db.scalar(select(Category).where(Category.id == uuid.UUID(groceries["id"])))
            assert category is not None
            assert category.deleted_from_month == date(2026, 8, 1)
            months = db.scalars(
                select(CategoryBudget.month).where(CategoryBudget.category_id == category.id)
            ).all()
            assert months and all(month < date(2026, 8, 1) for month in months)
            disabled_rule = db.scalar(select(Rule).where(Rule.id == uuid.UUID(rule["id"])))
            assert disabled_rule is not None
            assert disabled_rule.enabled is False
            assert disabled_rule.version == rule["version"] + 1
            structure_audit = db.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "category.deleted",
                    AuditEvent.object_id == category.id,
                )
            )
            assert structure_audit is not None
            assert structure_audit.detail["transactions_decategorized"] == 2
            allocation_audits = db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "transaction.allocations.updated",
                    AuditEvent.object_id.in_([uuid.UUID(past["id"]), uuid.UUID(split["id"])]),
                )
            ).all()
            assert {event.object_id for event in allocation_audits} == {
                uuid.UUID(past["id"]),
                uuid.UUID(split["id"]),
            }

        restore = client.put(
            f"/api/categories/{groceries['id']}/visibility",
            headers=headers,
            json={
                "version": groceries["version"] + 1,
                "month": "2026-08-01",
                "visible": True,
                "scope": "all",
            },
        )
        assert restore.status_code == 400
        assert "permanently deleted" in restore.json()["detail"]
        invalid_rule = client.post(
            "/api/rules",
            headers=headers,
            json=_category_rule_payload("Deleted target", groceries["id"]),
        )
        assert invalid_rule.status_code == 400


def test_permanent_section_delete_tombstones_every_child_and_protects_income() -> None:
    client, headers = _signed_in_client()
    with client:
        august = _budget(client, "2026-08")
        income = next(section for section in august["sections"] if section["is_income"])
        protected = client.request(
            "DELETE",
            f"/api/sections/{income['id']}",
            headers=headers,
            json={"version": income["version"], "month": "2026-08-01"},
        )
        assert protected.status_code == 400

        section_response = client.post(
            "/api/sections",
            headers=headers,
            json={
                "name": "Projects",
                "icon": "sparkles",
                "accent": "accent",
                "sort_order": 2,
                "starts_month": "2026-07-01",
            },
        )
        assert section_response.status_code == 200
        section = section_response.json()["section"]
        children = []
        for index, name in enumerate(("Workshop", "Garden")):
            response = client.post(
                "/api/categories",
                headers=headers,
                json={
                    "section_id": section["id"],
                    "name": name,
                    "sort_order": index,
                    "rollover": False,
                    "default_planned": "20",
                    "note": "",
                    "starts_month": "2026-07-01",
                },
            )
            assert response.status_code == 200
            children.append(response.json()["category"])

        august = _budget(client, "2026-08")
        food = next(item for item in august["sections"] if item["name"] == "Food")
        groceries = next(category for category in food["categories"] if category["name"] == "Groceries")
        cash = next(account for account in august["accounts"] if account["name"] == "Cash Wallet")
        transaction = _create_transaction(
            client,
            headers,
            account_id=cash["id"],
            effective_date="2026-08-14",
            amount="-40",
            payee="Project split",
            allocations=[
                {"category_id": children[0]["id"], "amount": "-15", "memo": ""},
                {"category_id": groceries["id"], "amount": "-25", "memo": ""},
            ],
        )
        hidden_child = client.put(
            f"/api/categories/{children[1]['id']}/visibility",
            headers=headers,
            json={
                "version": children[1]["version"],
                "month": "2026-08-01",
                "visible": False,
                "scope": "month",
            },
        )
        assert hidden_child.status_code == 200

        deleted = client.request(
            "DELETE",
            f"/api/sections/{section['id']}",
            headers=headers,
            json={"version": section["version"], "month": "2026-08-01"},
        )
        assert deleted.status_code == 200
        assert deleted.json()["transactions_decategorized"] == 1
        updated = _transaction(client, transaction["id"])
        assert updated["allocations"] == []
        assert updated["version"] == transaction["version"] + 1

        assert _section_in_budget(_budget(client, "2026-07"), section["id"])
        for month in ("2026-08", "2026-10"):
            budget = _budget(client, month)
            assert not _section_in_budget(budget, section["id"])
            assert all(item["id"] != section["id"] for item in budget["hidden_structure"]["sections"])
            child_ids = {child["id"] for child in children}
            assert child_ids.isdisjoint(item["id"] for item in budget["category_catalog"])

        with SessionLocal() as db:
            rows = db.scalars(
                select(Category).where(Category.id.in_([uuid.UUID(child["id"]) for child in children]))
            ).all()
            assert len(rows) == 2
            assert all(category.deleted_from_month == date(2026, 8, 1) for category in rows)


def test_permanent_structure_delete_conflict_leaves_allocations_untouched() -> None:
    client, headers = _signed_in_client()
    with client:
        august = _budget(client, "2026-08")
        food = next(section for section in august["sections"] if section["name"] == "Food")
        groceries = next(category for category in food["categories"] if category["name"] == "Groceries")
        cash = next(account for account in august["accounts"] if account["name"] == "Cash Wallet")
        transaction = _create_transaction(
            client,
            headers,
            account_id=cash["id"],
            effective_date="2026-08-20",
            amount="-9",
            payee="Conflict",
            allocations=[{"category_id": groceries["id"], "amount": "-9", "memo": ""}],
        )
        renamed = client.patch(
            f"/api/categories/{groceries['id']}",
            headers=headers,
            json={"version": groceries["version"], "name": "Groceries updated"},
        )
        assert renamed.status_code == 200
        stale = client.request(
            "DELETE",
            f"/api/categories/{groceries['id']}",
            headers=headers,
            json={"version": groceries["version"], "month": "2026-08-01"},
        )
        assert stale.status_code == 409
        assert _transaction(client, transaction["id"])["allocations"][0]["category_id"] == groceries["id"]
        assert _category_in_budget(_budget(client, "2026-08"), groceries["id"])


def test_permanent_delete_removes_a_not_started_category_from_the_selected_month() -> None:
    client, headers = _signed_in_client()
    with client:
        august = _budget(client, "2026-08")
        food = next(section for section in august["sections"] if section["name"] == "Food")
        created = client.post(
            "/api/categories",
            headers=headers,
            json={
                "section_id": food["id"],
                "name": "Autumn market",
                "sort_order": 2,
                "rollover": False,
                "default_planned": "40",
                "note": "",
                "starts_month": "2026-09-01",
            },
        )
        assert created.status_code == 200
        category = created.json()["category"]
        assert any(
            item["id"] == category["id"] and item["visibility_reason"] == "not_started"
            for item in _budget(client, "2026-08")["hidden_structure"]["categories"]
        )

        deleted = client.request(
            "DELETE",
            f"/api/categories/{category['id']}",
            headers=headers,
            json={"version": category["version"], "month": "2026-08-01"},
        )
        assert deleted.status_code == 200

        for month in ("2026-08", "2026-09", "2026-10"):
            budget = _budget(client, month)
            assert not _category_in_budget(budget, category["id"])
            assert all(item["id"] != category["id"] for item in budget["category_catalog"])
            assert all(item["id"] != category["id"] for item in budget["hidden_structure"]["categories"])
        july_hidden = next(
            item
            for item in _budget(client, "2026-07")["hidden_structure"]["categories"]
            if item["id"] == category["id"]
        )
        assert july_hidden["deleted_from_month"] == "2026-08"

        rejected_budget = client.put(
            f"/api/budget/2026-09/categories/{category['id']}",
            headers=headers,
            json={"planned": "25", "version": 0},
        )
        assert rejected_budget.status_code == 400
        with SessionLocal() as db:
            stored = db.scalar(select(Category).where(Category.id == uuid.UUID(category["id"])))
            assert stored is not None
            assert stored.deleted_from_month == date(2026, 8, 1)
            assert stored.ends_before_month == date(2026, 9, 1)


def test_deleted_section_rejects_new_and_moved_categories() -> None:
    client, headers = _signed_in_client()
    with client:
        august = _budget(client, "2026-08")
        food = next(section for section in august["sections"] if section["name"] == "Food")
        groceries = next(category for category in food["categories"] if category["name"] == "Groceries")
        created = client.post(
            "/api/sections",
            headers=headers,
            json={
                "name": "Future projects",
                "icon": "sparkles",
                "accent": "accent",
                "sort_order": 3,
                "starts_month": "2026-09-01",
            },
        )
        assert created.status_code == 200
        section = created.json()["section"]
        deleted = client.request(
            "DELETE",
            f"/api/sections/{section['id']}",
            headers=headers,
            json={"version": section["version"], "month": "2026-08-01"},
        )
        assert deleted.status_code == 200
        for month in ("2026-08", "2026-09"):
            budget = _budget(client, month)
            assert not _section_in_budget(budget, section["id"])
            assert all(item["id"] != section["id"] for item in budget["hidden_structure"]["sections"])

        added = client.post(
            "/api/categories",
            headers=headers,
            json={"section_id": section["id"], "name": "Should not exist"},
        )
        assert added.status_code == 400
        assert "deleted section" in added.json()["detail"]
        moved = client.patch(
            f"/api/categories/{groceries['id']}",
            headers=headers,
            json={"version": groceries["version"], "section_id": section["id"]},
        )
        assert moved.status_code == 400
        assert "deleted section" in moved.json()["detail"]
        assert _category_in_budget(_budget(client, "2026-08"), groceries["id"])


def test_permanently_deleted_categories_do_not_consume_reorder_positions() -> None:
    client, headers = _signed_in_client()
    with client:
        august = _budget(client, "2026-08")
        food = next(section for section in august["sections"] if section["name"] == "Food")
        created = client.post(
            "/api/categories",
            headers=headers,
            json={
                "section_id": food["id"],
                "name": "Dessert",
                "sort_order": 2,
                "rollover": False,
                "default_planned": "0",
                "note": "",
                "starts_month": "2026-08-01",
            },
        )
        assert created.status_code == 200
        food = next(section for section in _budget(client, "2026-08")["sections"] if section["name"] == "Food")
        groceries = next(category for category in food["categories"] if category["name"] == "Groceries")
        eating_out = next(category for category in food["categories"] if category["name"] == "Eating Out")

        deleted = client.request(
            "DELETE",
            f"/api/categories/{groceries['id']}",
            headers=headers,
            json={"version": groceries["version"], "month": "2026-08-01"},
        )
        assert deleted.status_code == 200
        reordered = client.patch(
            f"/api/categories/{eating_out['id']}",
            headers=headers,
            json={"version": eating_out["version"], "sort_order": 1},
        )
        assert reordered.status_code == 200
        food = next(section for section in _budget(client, "2026-08")["sections"] if section["name"] == "Food")
        assert [category["name"] for category in food["categories"]] == ["Dessert", "Eating Out"]
