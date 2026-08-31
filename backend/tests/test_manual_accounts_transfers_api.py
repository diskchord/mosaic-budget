from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Account, BudgetTransaction, Workspace


def _reset() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()


def _login(
    client: TestClient,
    *,
    email: str = "owner@example.com",
    password: str = "correct-horse-battery-staple",
) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies["mosaic_csrf"]}


def _budget(client: TestClient) -> dict:
    response = client.get("/api/budget", params={"month": "2026-08"})
    assert response.status_code == 200
    return response.json()


def _account_named(client: TestClient, name: str) -> dict:
    return next(account for account in _budget(client)["account_catalog"] if account["name"] == name)


def _create_manual_account(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    *,
    starting_balance: str = "0",
    is_budget: bool = True,
) -> dict:
    response = client.post(
        "/api/accounts",
        headers=headers,
        json={
            "name": name,
            "starting_balance": starting_balance,
            "is_budget": is_budget,
        },
    )
    assert response.status_code == 200
    return response.json()["account"]


def _set_balance(account_id: str, amount: str) -> None:
    with SessionLocal() as db:
        account = db.get(Account, uuid.UUID(account_id))
        assert account is not None
        account.balance = Decimal(amount)
        account.available_balance = Decimal(amount)
        db.commit()


def _create_imported_account(
    *,
    name: str = "Imported Checking",
    balance: str = "25",
    active: bool = True,
) -> Account:
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).limit(1))
        assert workspace is not None
        account = Account(
            workspace_id=workspace.id,
            source_type="simplefin",
            source_conn_id=f"test-{uuid.uuid4()}",
            source_account_id=f"account-{uuid.uuid4()}",
            name=name,
            currency=workspace.currency,
            balance=Decimal(balance),
            available_balance=Decimal(balance),
            is_budget=True,
            is_active=active,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        db.expunge(account)
        return account


def _create_transfer(
    client: TestClient,
    headers: dict[str, str],
    source_id: str,
    destination_id: str,
    *,
    amount: str = "40",
) -> dict:
    response = client.post(
        "/api/transactions/transfers",
        headers=headers,
        json={
            "from_account_id": source_id,
            "to_account_id": destination_id,
            "effective_date": "2026-08-30",
            "amount": amount,
            "note": "Move to the safe",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_owner_creates_trimmed_manual_account_with_safe_defaults_and_member_cannot() -> None:
    _reset()

    with TestClient(app) as owner_client:
        headers = _login(owner_client)

        no_csrf = owner_client.post("/api/accounts", json={"name": "Cash Safe"})
        assert no_csrf.status_code == 403

        blank = owner_client.post("/api/accounts", headers=headers, json={"name": "   "})
        assert blank.status_code == 422

        invalid_balance = owner_client.post(
            "/api/accounts",
            headers=headers,
            json={"name": "Invalid reserve", "starting_balance": "NaN"},
        )
        assert invalid_balance.status_code == 400
        assert invalid_balance.json()["detail"] == "Amount must be finite"

        created = owner_client.post(
            "/api/accounts",
            headers=headers,
            json={"name": "  Cash Safe  "},
        )
        assert created.status_code == 200
        account = created.json()["account"]
        assert account["name"] == "Cash Safe"
        assert account["source_type"] == "manual"
        assert account["currency"] == "USD"
        assert account["balance"] == "0"
        assert account["available_balance"] == "0"
        assert account["is_budget"] is True
        assert account["is_active"] is True
        assert account["is_duplicate"] is False
        assert account["version"] == 1

        budget = _budget(owner_client)
        assert [item["id"] for item in budget["accounts"]].count(account["id"]) == 1
        assert [item["id"] for item in budget["account_catalog"]].count(account["id"]) == 1

        custom = _create_manual_account(
            owner_client,
            headers,
            "Off-budget reserve",
            starting_balance="123.45678",
            is_budget=False,
        )
        assert custom["balance"] == "123.4568"
        assert custom["available_balance"] == "123.4568"
        assert custom["is_budget"] is False

        member_password = "member-password-1234"
        member = owner_client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "email": "member@example.com",
                "display_name": "Member",
                "password": member_password,
                "is_admin": False,
            },
        )
        assert member.status_code == 200

    with TestClient(app) as member_client:
        member_headers = _login(
            member_client,
            email="member@example.com",
            password="member-password-1234",
        )
        forbidden = member_client.post(
            "/api/accounts",
            headers=member_headers,
            json={"name": "Member safe"},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"] == "Administrator access required"

    with SessionLocal() as db:
        stored = db.get(Account, uuid.UUID(account["id"]))
        assert stored is not None
        assert stored.name == "Cash Safe"
        assert stored.source_type == "manual"
        assert stored.source_conn_id == "manual"
        assert stored.source_account_id
        assert Decimal(stored.balance) == Decimal("0")


def test_manual_transaction_defaults_omitted_null_or_blank_payee() -> None:
    _reset()
    imported = _create_imported_account()
    with SessionLocal() as db:
        imported_source = BudgetTransaction(
            workspace_id=imported.workspace_id,
            account_id=imported.id,
            source_kind="simplefin",
            effective_date=date(2026, 8, 12),
            amount=Decimal("-2"),
            payee="Imported merchant",
            imported_description="Imported merchant detail",
        )
        db.add(imported_source)
        db.commit()
        db.refresh(imported_source)
        db.expunge(imported_source)

    with TestClient(app) as client:
        headers = _login(client)
        wallet = _account_named(client, "Cash Wallet")
        payee_variants = [
            {},
            {"payee": None},
            {"payee": ""},
            {"payee": "   "},
        ]
        for offset, payee_payload in enumerate(payee_variants, start=1):
            response = client.post(
                "/api/transactions",
                headers=headers,
                json={
                    "account_id": wallet["id"],
                    "effective_date": f"2026-08-{offset:02d}",
                    "amount": str(offset),
                    "note": "",
                    "allocations": [],
                    **payee_payload,
                },
            )
            assert response.status_code == 200
            transaction = response.json()["transaction"]
            assert transaction["payee"] == "Cash transaction"
            assert transaction["display_payee"] == "Cash transaction"

        named = client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": wallet["id"],
                "effective_date": "2026-08-10",
                "amount": "5",
                "payee": "  Named cash source  ",
                "allocations": [],
            },
        )
        assert named.status_code == 200
        named_transaction = named.json()["transaction"]
        assert named_transaction["payee"] == "Named cash source"

        reset_to_default = client.patch(
            f"/api/transactions/{named_transaction['id']}",
            headers=headers,
            json={"version": named_transaction["version"], "payee": "   "},
        )
        assert reset_to_default.status_code == 200
        assert reset_to_default.json()["transaction"]["payee"] == "Cash transaction"

        imported_default = client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": str(imported.id),
                "effective_date": "2026-08-11",
                "amount": "1",
                "allocations": [],
            },
        )
        assert imported_default.status_code == 200
        assert imported_default.json()["transaction"]["payee"] == "Manual transaction"

        imported_blank = client.patch(
            f"/api/transactions/{imported_source.id}",
            headers=headers,
            json={"version": imported_source.version, "payee": "   "},
        )
        assert imported_blank.status_code == 400
        assert imported_blank.json()["detail"] == "Payee cannot be blank"
        unchanged_imported = client.get(
            f"/api/transactions/{imported_source.id}"
        ).json()["transaction"]
        assert unchanged_imported["payee"] == "Imported merchant"

        refreshed_wallet = _account_named(client, "Cash Wallet")
        assert refreshed_wallet["balance"] == "15"
        assert _account_named(client, "Imported Checking")["balance"] == "25"


def test_transfer_creates_a_budget_neutral_inverse_pair_and_updates_both_balances() -> None:
    _reset()

    with TestClient(app) as client:
        headers = _login(client)
        wallet = _account_named(client, "Cash Wallet")
        safe = _create_manual_account(client, headers, "Cash Safe", starting_balance="20")
        _set_balance(wallet["id"], "150")

        before_unassigned = {item["id"] for item in _budget(client)["unassigned"]}
        result = _create_transfer(
            client,
            headers,
            wallet["id"],
            safe["id"],
            amount="35.75",
        )

        transfer_group_id = result["transfer_group_id"]
        uuid.UUID(transfer_group_id)
        source_leg, destination_leg = result["transactions"]
        assert source_leg["account_id"] == wallet["id"]
        assert destination_leg["account_id"] == safe["id"]
        assert source_leg["amount"] == "-35.75"
        assert destination_leg["amount"] == "35.75"
        assert source_leg["payee"] == "Transfer to Cash Safe"
        assert destination_leg["payee"] == "Transfer from Cash Wallet"
        assert source_leg["display_payee"] == "Transfer to Cash Safe"
        assert destination_leg["display_payee"] == "Transfer from Cash Wallet"
        assert source_leg["effective_date"] == destination_leg["effective_date"] == "2026-08-30"
        assert source_leg["note"] == destination_leg["note"] == "Move to the safe"
        assert source_leg["transfer_group_id"] == transfer_group_id
        assert destination_leg["transfer_group_id"] == transfer_group_id
        assert source_leg["allocations"] == destination_leg["allocations"] == []
        assert source_leg["excluded"] is False
        assert destination_leg["excluded"] is False

        refreshed_budget = _budget(client)
        accounts = {item["id"]: item for item in refreshed_budget["accounts"]}
        assert accounts[wallet["id"]]["balance"] == "114.25"
        assert accounts[safe["id"]]["balance"] == "55.75"
        assert {item["id"] for item in refreshed_budget["unassigned"]} == before_unassigned

        listed = client.get("/api/transactions", params={"month": "2026-08"})
        assert listed.status_code == 200
        listed_ids = {item["id"] for item in listed.json()["transactions"]}
        assert {source_leg["id"], destination_leg["id"]} <= listed_ids

        unassigned = client.get(
            "/api/transactions",
            params={"month": "2026-08", "status": "unassigned"},
        )
        assert unassigned.status_code == 200
        unassigned_ids = {item["id"] for item in unassigned.json()["transactions"]}
        assert {source_leg["id"], destination_leg["id"]}.isdisjoint(unassigned_ids)

        analytics = client.get(
            "/api/analytics",
            params={"start_month": "2026-08", "end_month": "2026-08"},
        )
        assert analytics.status_code == 200
        analytics_payload = analytics.json()
        assert analytics_payload["months"][0]["transaction_count"] == 0
        assert analytics_payload["months"][0]["uncategorized_transaction_count"] == 0
        assert analytics_payload["totals"]["transaction_count"] == 0
        assert analytics_payload["totals"]["uncategorized_transaction_count"] == 0

        rules = client.post(
            "/api/rules/run",
            headers=headers,
            json={"month": "2026-08"},
        )
        assert rules.status_code == 200
        assert rules.json()["transactions_scanned"] == 0

    with SessionLocal() as db:
        rows = db.scalars(
            select(BudgetTransaction).where(
                BudgetTransaction.transfer_group_id == uuid.UUID(transfer_group_id)
            )
        ).all()
        assert len(rows) == 2
        assert sum((Decimal(row.amount) for row in rows), Decimal("0")) == Decimal("0")


def test_transfer_rejects_invalid_amounts_and_accounts_without_partial_changes() -> None:
    _reset()
    imported = _create_imported_account()

    with TestClient(app) as client:
        headers = _login(client)
        wallet = _account_named(client, "Cash Wallet")
        safe = _create_manual_account(client, headers, "Cash Safe", starting_balance="10")
        inactive = _create_manual_account(client, headers, "Inactive safe", starting_balance="3")
        deactivated = client.patch(
            f"/api/connections/accounts/{inactive['id']}",
            headers=headers,
            json={"version": inactive["version"], "is_active": False},
        )
        assert deactivated.status_code == 200

        with SessionLocal() as db:
            workspace = db.scalar(select(Workspace).limit(1))
            assert workspace is not None
            other_currency = Account(
                workspace_id=workspace.id,
                source_type="manual",
                source_conn_id="manual",
                source_account_id=f"manual-{uuid.uuid4()}",
                name="Euro cash",
                currency="EUR",
                balance=Decimal("5"),
                available_balance=Decimal("5"),
                is_budget=True,
                is_active=True,
            )
            db.add(other_currency)
            db.commit()
            other_currency_id = str(other_currency.id)

        no_csrf = client.post(
            "/api/transactions/transfers",
            json={
                "from_account_id": wallet["id"],
                "to_account_id": safe["id"],
                "effective_date": "2026-08-30",
                "amount": "1",
            },
        )
        assert no_csrf.status_code == 403

        attempts = [
            (wallet["id"], wallet["id"], "1", 400, "Transfer accounts must be different"),
            (wallet["id"], safe["id"], "0", 400, "Transfer amount must be greater than zero"),
            (wallet["id"], safe["id"], "-1", 400, "Transfer amount must be greater than zero"),
            (
                str(imported.id),
                safe["id"],
                "1",
                404,
                "One or more transfer accounts were not found",
            ),
            (
                wallet["id"],
                inactive["id"],
                "1",
                404,
                "One or more transfer accounts were not found",
            ),
            (
                wallet["id"],
                other_currency_id,
                "1",
                400,
                "Transfer accounts must use the same currency",
            ),
        ]
        for source_id, destination_id, amount, status, detail in attempts:
            response = client.post(
                "/api/transactions/transfers",
                headers=headers,
                json={
                    "from_account_id": source_id,
                    "to_account_id": destination_id,
                    "effective_date": "2026-08-30",
                    "amount": amount,
                },
            )
            assert response.status_code == status
            assert response.json()["detail"] == detail

    with SessionLocal() as db:
        assert db.scalar(select(func.count(BudgetTransaction.id))) == 0
        balances = {
            account.name: Decimal(account.balance)
            for account in db.scalars(select(Account)).all()
            if account.balance is not None
        }
        assert balances["Cash Wallet"] == Decimal("0")
        assert balances["Cash Safe"] == Decimal("10")
        assert balances["Inactive safe"] == Decimal("3")
        assert balances["Imported Checking"] == Decimal("25")
        assert balances["Euro cash"] == Decimal("5")


def test_deleting_or_restoring_either_transfer_leg_updates_the_complete_pair_atomically() -> None:
    _reset()

    with TestClient(app) as client:
        headers = _login(client)
        wallet = _account_named(client, "Cash Wallet")
        safe = _create_manual_account(client, headers, "Cash Safe")
        _set_balance(wallet["id"], "100")
        result = _create_transfer(client, headers, wallet["id"], safe["id"])
        source_leg, destination_leg = result["transactions"]

        individual_edit = client.patch(
            f"/api/transactions/{source_leg['id']}",
            headers=headers,
            json={"version": source_leg["version"], "note": "Break the pair"},
        )
        assert individual_edit.status_code == 400
        assert individual_edit.json()["detail"] == "Transfer transactions cannot be edited individually"

        individual_allocation = client.put(
            f"/api/transactions/{destination_leg['id']}/allocations",
            headers=headers,
            json={"version": destination_leg["version"], "allocations": []},
        )
        assert individual_allocation.status_code == 400
        assert individual_allocation.json()["detail"] == (
            "Transfer transactions cannot be edited individually"
        )

        deleted = client.request(
            "DELETE",
            f"/api/transactions/{source_leg['id']}",
            headers=headers,
            json={
                "version": source_leg["version"],
                "confirm": True,
                "confirm_amount": source_leg["amount"],
            },
        )
        assert deleted.status_code == 200

        deleted_source = client.get(f"/api/transactions/{source_leg['id']}").json()["transaction"]
        deleted_destination = client.get(
            f"/api/transactions/{destination_leg['id']}"
        ).json()["transaction"]
        assert deleted_source["deleted_at"] is not None
        assert deleted_destination["deleted_at"] is not None
        assert deleted_source["version"] == source_leg["version"] + 1
        assert deleted_destination["version"] == destination_leg["version"] + 1
        assert _account_named(client, "Cash Wallet")["balance"] == "100"
        assert _account_named(client, "Cash Safe")["balance"] == "0"

        stale_restore = client.post(
            f"/api/transactions/{destination_leg['id']}/restore",
            headers=headers,
            json={"version": destination_leg["version"]},
        )
        assert stale_restore.status_code == 409
        assert client.get(f"/api/transactions/{source_leg['id']}").json()["transaction"][
            "deleted_at"
        ] is not None
        assert client.get(
            f"/api/transactions/{destination_leg['id']}"
        ).json()["transaction"]["deleted_at"] is not None
        assert _account_named(client, "Cash Wallet")["balance"] == "100"
        assert _account_named(client, "Cash Safe")["balance"] == "0"

        restored = client.post(
            f"/api/transactions/{destination_leg['id']}/restore",
            headers=headers,
            json={"version": deleted_destination["version"]},
        )
        assert restored.status_code == 200

        restored_source = client.get(f"/api/transactions/{source_leg['id']}").json()["transaction"]
        restored_destination = client.get(
            f"/api/transactions/{destination_leg['id']}"
        ).json()["transaction"]
        assert restored_source["deleted_at"] is None
        assert restored_destination["deleted_at"] is None
        assert restored_source["version"] == deleted_source["version"] + 1
        assert restored_destination["version"] == deleted_destination["version"] + 1
        assert _account_named(client, "Cash Wallet")["balance"] == "60"
        assert _account_named(client, "Cash Safe")["balance"] == "40"
