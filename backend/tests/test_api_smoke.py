from __future__ import annotations

from fastapi.testclient import TestClient

from app.bootstrap import bootstrap
from app.db import Base, engine
from app.main import app


def test_login_budget_manual_transaction_assignment_and_conflict() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
        )
        assert response.status_code == 200
        csrf = client.cookies["mosaic_csrf"]
        headers = {"X-CSRF-Token": csrf}

        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        groceries = next(
            category
            for section in budget["sections"]
            for category in section["categories"]
            if category["name"] == "Groceries"
        )
        cash = next(account for account in budget["accounts"] if account["name"] == "Cash Wallet")

        created = client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": cash["id"],
                "effective_date": "2026-08-27",
                "amount": "-84.27",
                "payee": "Hannaford",
                "note": "smoke test",
                "allocations": [],
            },
        )
        assert created.status_code == 200
        transaction = created.json()["transaction"]

        assigned = client.put(
            f"/api/transactions/{transaction['id']}/allocations",
            headers=headers,
            json={
                "version": transaction["version"],
                "allocations": [{"category_id": groceries["id"], "amount": "-84.27", "memo": ""}],
            },
        )
        assert assigned.status_code == 200
        assert assigned.json()["transaction"]["allocations"][0]["category_name"] == "Groceries"

        stale = client.patch(
            f"/api/transactions/{transaction['id']}",
            headers=headers,
            json={"version": transaction["version"], "note": "stale edit"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current"]["version"] > transaction["version"]

        latest_budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        latest_groceries = next(
            category
            for section in latest_budget["sections"]
            for category in section["categories"]
            if category["name"] == "Groceries"
        )
        assert latest_groceries["activity"] == "-84.27"
        assert all(item["id"] != transaction["id"] for item in latest_budget["unassigned"])
