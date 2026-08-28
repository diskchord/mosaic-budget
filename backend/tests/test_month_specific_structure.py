from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import CategoryBudget


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
