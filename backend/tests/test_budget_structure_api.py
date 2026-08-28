from __future__ import annotations

from fastapi.testclient import TestClient

from app.bootstrap import bootstrap
from app.db import Base, engine
from app.main import app


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
