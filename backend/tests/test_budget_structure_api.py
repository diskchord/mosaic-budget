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


def _category(budget: dict, name: str) -> dict:
    return next(
        category
        for section in budget["sections"]
        for category in section["categories"]
        if category["name"] == name
    )


def _budget_amount_audits() -> list[AuditEvent]:
    with SessionLocal() as db:
        return db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == "budget.amount.updated")
            .order_by(AuditEvent.created_at, AuditEvent.id)
        ).all()


def test_create_move_reorder_and_archive_budget_structure() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        housing = next(section for section in budget["sections"] if section["name"] == "Housing")
        food = next(section for section in budget["sections"] if section["name"] == "Food")

        created_section_response = client.post(
            "/api/sections",
            headers=headers,
            json={"name": "Giving", "icon": "sparkles", "accent": "accent", "sort_order": 0},
        )
        assert created_section_response.status_code == 200
        created_section = created_section_response.json()["section"]

        latest = client.get("/api/budget", params={"month": "2026-08"}).json()
        assert latest["sections"][0]["name"] == "Income"
        assert latest["sections"][1]["name"] == "Giving"

        created_category_response = client.post(
            "/api/categories",
            headers=headers,
            json={
                "section_id": food["id"],
                "name": "Coffee",
                "sort_order": 0,
                "rollover": False,
                "default_planned": "25",
                "note": "",
            },
        )
        assert created_category_response.status_code == 200
        category = created_category_response.json()["category"]

        latest = client.get("/api/budget", params={"month": "2026-08"}).json()
        latest_food = next(section for section in latest["sections"] if section["id"] == food["id"])
        assert latest_food["categories"][0]["name"] == "Coffee"
        assert latest_food["categories"][0]["planned"] == "25"

        moved_response = client.patch(
            f"/api/categories/{category['id']}",
            headers=headers,
            json={
                "version": category["version"],
                "section_id": housing["id"],
                "sort_order": 1,
                "name": "Coffee",
                "rollover": False,
                "default_planned": "25",
                "note": "",
            },
        )
        assert moved_response.status_code == 200
        moved = moved_response.json()["category"]

        latest = client.get("/api/budget", params={"month": "2026-08"}).json()
        latest_housing = next(section for section in latest["sections"] if section["id"] == housing["id"])
        assert [item["name"] for item in latest_housing["categories"]][1] == "Coffee"

        archived_category = client.request(
            "DELETE",
            f"/api/categories/{moved['id']}",
            headers=headers,
            json={"version": moved["version"]},
        )
        assert archived_category.status_code == 200

        archived_section = client.request(
            "DELETE",
            f"/api/sections/{created_section['id']}",
            headers=headers,
            json={"version": created_section["version"]},
        )
        assert archived_section.status_code == 200

        latest = client.get("/api/budget", params={"month": "2026-08"}).json()
        assert all(section["name"] != "Giving" for section in latest["sections"])
        assert all(
            category["name"] != "Coffee"
            for section in latest["sections"]
            for category in section["categories"]
        )


def test_existing_sections_and_categories_reorder_with_conflict_protection() -> None:
    client, headers = _signed_in_client()
    with client:
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        expenses = [section for section in budget["sections"] if not section["is_income"]]
        moving_section = expenses[-1]

        section_response = client.patch(
            f"/api/sections/{moving_section['id']}",
            headers=headers,
            json={"version": moving_section["version"], "sort_order": 0},
        )
        assert section_response.status_code == 200
        reordered_section = section_response.json()["section"]
        latest = client.get("/api/budget", params={"month": "2026-08"}).json()
        assert latest["sections"][0]["is_income"] is True
        assert latest["sections"][1]["id"] == moving_section["id"]
        assert [section["sort_order"] for section in latest["sections"] if not section["is_income"]] == list(
            range(1, len(expenses) + 1)
        )

        stale_section = client.patch(
            f"/api/sections/{moving_section['id']}",
            headers=headers,
            json={"version": moving_section["version"], "sort_order": len(expenses) - 1},
        )
        assert stale_section.status_code == 409
        assert stale_section.json()["detail"]["current"]["version"] == reordered_section["version"]

        food = next(section for section in latest["sections"] if section["name"] == "Food")
        moving_category = food["categories"][-1]
        category_response = client.patch(
            f"/api/categories/{moving_category['id']}",
            params={"current_month": "2026-08"},
            headers=headers,
            json={
                "version": moving_category["version"],
                "section_id": food["id"],
                "sort_order": 0,
            },
        )
        assert category_response.status_code == 200
        reordered_category = category_response.json()["category"]
        latest = client.get("/api/budget", params={"month": "2026-08"}).json()
        latest_food = next(section for section in latest["sections"] if section["id"] == food["id"])
        assert latest_food["categories"][0]["id"] == moving_category["id"]
        assert [category["sort_order"] for category in latest_food["categories"]] == list(
            range(len(latest_food["categories"]))
        )

        stale_category = client.patch(
            f"/api/categories/{moving_category['id']}",
            params={"current_month": "2026-08"},
            headers=headers,
            json={"version": moving_category["version"], "sort_order": 1},
        )
        assert stale_category.status_code == 409
        assert stale_category.json()["detail"]["current"]["version"] == reordered_category["version"]


def test_changed_category_default_seeds_only_requested_zero_month_and_audits() -> None:
    client, headers = _signed_in_client()
    with client:
        august = client.get("/api/budget", params={"month": "2026-08"}).json()
        september = client.get("/api/budget", params={"month": "2026-09"}).json()
        august_groceries = _category(august, "Groceries")
        september_groceries = _category(september, "Groceries")
        assert august_groceries["planned"] == "0"
        assert september_groceries["planned"] == "0"

        response = client.patch(
            f"/api/categories/{august_groceries['id']}",
            params={"current_month": "2026-08"},
            headers=headers,
            json={"version": august_groceries["version"], "default_planned": "75"},
        )
        assert response.status_code == 200
        assert response.json()["category"]["default_planned"] == "75"

        updated_august = _category(client.get("/api/budget", params={"month": "2026-08"}).json(), "Groceries")
        unchanged_september = _category(
            client.get("/api/budget", params={"month": "2026-09"}).json(),
            "Groceries",
        )
        assert updated_august["planned"] == "75"
        assert updated_august["budget_version"] == august_groceries["budget_version"] + 1
        assert unchanged_september["planned"] == "0"
        assert unchanged_september["budget_version"] == september_groceries["budget_version"]

        audits = _budget_amount_audits()
        assert len(audits) == 1
        assert audits[0].object_type == "category_budget"
        assert audits[0].before == {
            "planned": "0",
            "version": august_groceries["budget_version"],
        }
        assert audits[0].after == {
            "month": "2026-08",
            "category_id": august_groceries["id"],
            "planned": "75",
            "version": august_groceries["budget_version"] + 1,
        }


def test_category_default_preserves_nonzero_plan_and_unchanged_default_does_not_seed() -> None:
    client, headers = _signed_in_client()
    with client:
        august = client.get("/api/budget", params={"month": "2026-08"}).json()
        september = client.get("/api/budget", params={"month": "2026-09"}).json()
        august_groceries = _category(august, "Groceries")
        september_groceries = _category(september, "Groceries")

        planned_response = client.put(
            f"/api/budget/2026-08/categories/{august_groceries['id']}",
            headers=headers,
            json={"version": august_groceries["budget_version"], "planned": "35"},
        )
        assert planned_response.status_code == 200

        changed_response = client.patch(
            f"/api/categories/{august_groceries['id']}",
            params={"current_month": "2026-08"},
            headers=headers,
            json={"version": august_groceries["version"], "default_planned": "75"},
        )
        assert changed_response.status_code == 200
        changed_category = changed_response.json()["category"]
        assert _category(client.get("/api/budget", params={"month": "2026-08"}).json(), "Groceries")["planned"] == "35"
        assert _category(client.get("/api/budget", params={"month": "2026-09"}).json(), "Groceries")["planned"] == "0"
        assert len(_budget_amount_audits()) == 1

        unchanged_response = client.patch(
            f"/api/categories/{august_groceries['id']}",
            params={"current_month": "2026-09"},
            headers=headers,
            json={"version": changed_category["version"], "default_planned": "75"},
        )
        assert unchanged_response.status_code == 200
        unchanged_september = _category(
            client.get("/api/budget", params={"month": "2026-09"}).json(),
            "Groceries",
        )
        assert unchanged_september["planned"] == "0"
        assert unchanged_september["budget_version"] == september_groceries["budget_version"]
        assert len(_budget_amount_audits()) == 1
