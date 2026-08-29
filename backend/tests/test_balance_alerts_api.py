from __future__ import annotations

from email.header import decode_header, make_header
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Account, BalanceAlert, NotificationIncident, NotificationOutbox, SimpleFinConnection
from app.api.alerts import _account_for_workspace
from app.services import notifications
from app.services.balance_alerts import (
    balance_alert_unavailable_reason,
    close_balance_alert_episode,
    evaluate_balance_alert,
    evaluate_balance_alerts,
)
from app.utils import utcnow


def _reset() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies["mosaic_csrf"]}


def _enable_smtp(monkeypatch) -> None:
    monkeypatch.setattr(notifications.settings, "smtp_host", "mail.smtp2go.test")
    monkeypatch.setattr(notifications.settings, "smtp_from", "mosaic@example.test")
    monkeypatch.setattr(notifications.settings, "smtp_to", "owner@example.test")


def test_balance_alert_triggers_once_and_queues_recovery(monkeypatch) -> None:
    _reset()
    _enable_smtp(monkeypatch)

    with TestClient(app) as client:
        headers = _login(client)
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        account = next(item for item in budget["accounts"] if item["name"] == "Cash Wallet")
        created = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={
                "account_id": account["id"],
                "name": "Cash cushion is low",
                "comparison": "below",
                "threshold": "100",
                "channels": ["smtp"],
                "enabled": True,
            },
        )
        assert created.status_code == 200
        alert = created.json()["alert"]
        assert alert["triggered"] is True
        assert alert["current_balance"] == "0"

        listed = client.get("/api/alerts/balances").json()
        assert listed["available_channels"] == ["smtp"]
        assert listed["alerts"] == [alert]

    with SessionLocal() as db:
        assert db.scalar(select(func.count(NotificationOutbox.id))) == 1
        incident = db.scalar(select(NotificationIncident))
        assert incident.status == "open"
        assert "Cash Wallet balance is USD 0" in incident.message
        assert evaluate_balance_alerts(db) == {"evaluated": 1, "triggered": 1}
        assert db.scalar(select(func.count(NotificationOutbox.id))) == 1
        account_row = db.get(Account, UUID(alert["account_id"]))
        account_row.balance = Decimal("150")
        account_row.available_balance = Decimal("150")
        evaluate_balance_alerts(db)
        db.commit()

    with SessionLocal() as db:
        incident = db.scalar(select(NotificationIncident))
        assert incident.status == "resolved"
        assert "Cash Wallet balance is USD 150, no longer below" in incident.message
        deliveries = db.scalars(select(NotificationOutbox).order_by(NotificationOutbox.created_at)).all()
        assert len(deliveries) == 2
        assert [delivery.channel for delivery in deliveries] == ["smtp", "smtp"]
        assert deliveries[1].payload["title"] == "Resolved: Cash cushion is low"
        assert "Cash Wallet balance is USD 150, no longer below" in deliveries[1].payload["message"]


def test_balance_alert_validates_channels_and_preserves_manual_edits(monkeypatch) -> None:
    _reset()
    _enable_smtp(monkeypatch)

    with TestClient(app) as client:
        headers = _login(client)
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        account = next(item for item in budget["accounts"] if item["name"] == "Cash Wallet")
        unavailable = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={
                "account_id": account["id"],
                "name": "Unavailable channel",
                "comparison": "above",
                "threshold": "10",
                "channels": ["ntfy"],
                "enabled": True,
            },
        )
        assert unavailable.status_code == 400
        assert "Configure ntfy" in unavailable.json()["detail"]

        created = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={
                "account_id": account["id"],
                "name": "Savings milestone",
                "comparison": "above",
                "threshold": "500",
                "channels": ["smtp"],
                "enabled": True,
            },
        ).json()["alert"]
        updated_response = client.patch(
            f"/api/alerts/balances/{created['id']}",
            headers=headers,
            json={
                "version": created["version"],
                "account_id": account["id"],
                "name": "Emergency fund target",
                "comparison": "above",
                "threshold": "750.50",
                "channels": ["smtp"],
                "enabled": False,
            },
        )
        assert updated_response.status_code == 200
        updated = updated_response.json()["alert"]
        assert updated["name"] == "Emergency fund target"
        assert updated["threshold"] == "750.5"
        assert updated["enabled"] is False

        stale = client.request(
            "DELETE",
            f"/api/alerts/balances/{created['id']}",
            headers=headers,
            json={"version": created["version"]},
        )
        assert stale.status_code == 409
        deleted = client.request(
            "DELETE",
            f"/api/alerts/balances/{created['id']}",
            headers=headers,
            json={"version": updated["version"]},
        )
        assert deleted.status_code == 200

    with SessionLocal() as db:
        assert db.scalar(select(func.count(BalanceAlert.id))) == 0


def test_explicit_alert_channel_is_queued_while_temporarily_unconfigured(monkeypatch) -> None:
    _reset()
    monkeypatch.setattr(notifications.settings, "smtp_host", "")
    monkeypatch.setattr(notifications.settings, "smtp_from", "")
    monkeypatch.setattr(notifications.settings, "smtp_to", "")
    monkeypatch.setattr(notifications.settings, "ntfy_topic", "")

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.name == "Cash Wallet"))
        alert = BalanceAlert(
            workspace_id=account.workspace_id,
            account_id=account.id,
            account=account,
            name="Cash is low",
            comparison="below",
            threshold=Decimal("100"),
            channels=["smtp"],
            enabled=True,
        )
        db.add(alert)
        db.flush()
        assert evaluate_balance_alert(db, alert) is True
        notifications.open_incident(
            db,
            workspace_id=account.workspace_id,
            incident_key="operational-with-default-channels",
            severity="warning",
            title="Operational test",
            message="No configured channel should be queued.",
        )
        db.commit()

    with SessionLocal() as db:
        deliveries = db.scalars(select(NotificationOutbox)).all()
        assert [delivery.channel for delivery in deliveries] == ["smtp"]
        assert notifications.process_outbox(db) == 1
        db.commit()

    with SessionLocal() as db:
        delivery = db.scalar(select(NotificationOutbox))
        assert delivery.status == "retry"
        assert "not currently configured" in delivery.last_error
        delivery.next_attempt_at = utcnow()
        db.commit()

    sent: list[dict] = []
    _enable_smtp(monkeypatch)
    monkeypatch.setattr(notifications, "_send_smtp", lambda payload: sent.append(payload))
    with SessionLocal() as db:
        assert notifications.process_outbox(db) == 1
        db.commit()
    with SessionLocal() as db:
        delivery = db.scalar(select(NotificationOutbox))
        assert delivery.status == "sent"
        assert len(sent) == 1


def test_balance_alert_queues_each_selected_channel_once(monkeypatch) -> None:
    _reset()
    _enable_smtp(monkeypatch)
    monkeypatch.setattr(notifications.settings, "ntfy_topic", "private-budget-alerts")

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.name == "Cash Wallet"))
        alert = BalanceAlert(
            workspace_id=account.workspace_id,
            account_id=account.id,
            account=account,
            name="Cash is low",
            comparison="below",
            threshold=Decimal("100"),
            channels=["smtp", "ntfy"],
            enabled=True,
        )
        db.add(alert)
        db.flush()
        assert evaluate_balance_alert(db, alert) is True
        db.commit()

    with SessionLocal() as db:
        deliveries = db.scalars(select(NotificationOutbox).order_by(NotificationOutbox.channel)).all()
        assert [delivery.channel for delivery in deliveries] == ["ntfy", "smtp"]
        assert len({(delivery.incident_id, delivery.channel) for delivery in deliveries}) == 2


def test_paused_or_disconnected_simplefin_account_is_unavailable(monkeypatch) -> None:
    _reset()
    _enable_smtp(monkeypatch)

    with SessionLocal() as db:
        workspace_id = db.scalar(select(Account.workspace_id).limit(1))
        connection = SimpleFinConnection(
            workspace_id=workspace_id,
            name="Paused bridge",
            encrypted_access_url="encrypted-placeholder",
            access_url_fingerprint="f" * 64,
            enabled=True,
            sync_interval_minutes=180,
            schedule_minute=17,
            next_sync_at=utcnow(),
        )
        db.add(connection)
        db.flush()
        account = Account(
            workspace_id=workspace_id,
            simplefin_connection_id=connection.id,
            simplefin_connection=connection,
            source_type="simplefin",
            source_conn_id="institution",
            source_account_id="checking",
            name="Imported checking",
            currency="USD",
            balance=Decimal("0"),
            available_balance=Decimal("0"),
            is_active=True,
        )
        db.add(account)
        db.flush()
        alert = BalanceAlert(
            workspace_id=workspace_id,
            account_id=account.id,
            account=account,
            name="Checking is low",
            comparison="below",
            threshold=Decimal("100"),
            channels=["smtp"],
            enabled=True,
        )
        db.add(alert)
        db.flush()
        assert balance_alert_unavailable_reason(alert) is None
        assert evaluate_balance_alert(db, alert) is True

        connection.enabled = False
        assert balance_alert_unavailable_reason(alert) == "connection_unavailable"
        assert evaluate_balance_alert(db, alert) is False
        try:
            _account_for_workspace(db, account.id, workspace_id)
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "Reconnect or resume" in str(exc.detail)
        else:
            raise AssertionError("Paused SimpleFIN account was accepted for an enabled alert")

        connection.enabled = True
        connection.encrypted_access_url = None
        assert balance_alert_unavailable_reason(alert) == "connection_unavailable"
        assert evaluate_balance_alert(db, alert) is False
        db.commit()

    with SessionLocal() as db:
        incident = db.scalar(select(NotificationIncident))
        assert incident.status == "resolved"
        assert db.scalar(select(func.count(NotificationOutbox.id))) == 1


def test_material_reconfiguration_starts_new_episode_and_disable_is_silent(monkeypatch) -> None:
    _reset()
    _enable_smtp(monkeypatch)

    with TestClient(app) as client:
        headers = _login(client)
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        account = next(item for item in budget["accounts"] if item["name"] == "Cash Wallet")
        created = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={
                "account_id": account["id"],
                "name": "Cash is low",
                "comparison": "below",
                "threshold": "100",
                "channels": ["smtp"],
                "enabled": True,
            },
        ).json()["alert"]
        reconfigured = client.patch(
            f"/api/alerts/balances/{created['id']}",
            headers=headers,
            json={
                "version": created["version"],
                "account_id": account["id"],
                "name": "Cash is still low",
                "comparison": "below",
                "threshold": "200",
                "channels": ["smtp"],
                "enabled": True,
            },
        ).json()["alert"]
        disabled = client.patch(
            f"/api/alerts/balances/{created['id']}",
            headers=headers,
            json={
                "version": reconfigured["version"],
                "account_id": account["id"],
                "name": reconfigured["name"],
                "comparison": reconfigured["comparison"],
                "threshold": reconfigured["threshold"],
                "channels": reconfigured["channels"],
                "enabled": False,
            },
        ).json()["alert"]
        assert disabled["enabled"] is False

    with SessionLocal() as db:
        incidents = db.scalars(select(NotificationIncident).order_by(NotificationIncident.opened_at)).all()
        deliveries = db.scalars(select(NotificationOutbox).order_by(NotificationOutbox.created_at)).all()
        assert len(incidents) == 2
        assert [incident.status for incident in incidents] == ["resolved", "resolved"]
        assert len(deliveries) == 2
        assert all(not delivery.payload["title"].startswith("Resolved:") for delivery in deliveries)


def test_unmonitorable_accounts_are_rejected_and_existing_alert_becomes_unavailable(monkeypatch) -> None:
    _reset()
    _enable_smtp(monkeypatch)

    with TestClient(app) as client:
        headers = _login(client)
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        account = next(item for item in budget["accounts"] if item["name"] == "Cash Wallet")
        created = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={
                "account_id": account["id"],
                "name": "Cash is low",
                "comparison": "below",
                "threshold": "100",
                "channels": ["smtp"],
                "enabled": True,
            },
        ).json()["alert"]

        with SessionLocal() as db:
            account_row = db.get(Account, UUID(account["id"]))
            account_row.is_active = False
            evaluate_balance_alerts(db, account_ids={account_row.id})
            db.commit()

        listed = client.get("/api/alerts/balances").json()["alerts"]
        assert listed[0]["id"] == created["id"]
        assert listed[0]["available"] is False
        assert listed[0]["unavailable_reason"] == "inactive_account"
        assert listed[0]["triggered"] is False

        rejected = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={
                "account_id": account["id"],
                "name": "Another alert",
                "comparison": "above",
                "threshold": "1",
                "channels": ["smtp"],
                "enabled": True,
            },
        )
        assert rejected.status_code == 400
        assert "Activate this account" in rejected.json()["detail"]

        with SessionLocal() as db:
            account_row = db.get(Account, UUID(account["id"]))
            account_row.is_active = True
            account_row.balance = None
            db.commit()
        unknown_balance = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={
                "account_id": account["id"],
                "name": "Unknown balance",
                "comparison": "above",
                "threshold": "1",
                "channels": ["smtp"],
                "enabled": True,
            },
        )
        assert unknown_balance.status_code == 400
        assert "known balance" in unknown_balance.json()["detail"]

        with SessionLocal() as db:
            account_row = db.get(Account, UUID(account["id"]))
            account_row.balance = Decimal("0")
            account_row.is_duplicate = True
            db.commit()
        duplicate = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={
                "account_id": account["id"],
                "name": "Duplicate account",
                "comparison": "above",
                "threshold": "1",
                "channels": ["smtp"],
                "enabled": True,
            },
        )
        assert duplicate.status_code == 400
        assert "Duplicate accounts" in duplicate.json()["detail"]

    with SessionLocal() as db:
        assert db.scalar(select(func.count(NotificationOutbox.id))) == 1


def test_balance_alert_rejects_unsafe_names_and_unrepresentable_thresholds(monkeypatch) -> None:
    _reset()
    _enable_smtp(monkeypatch)

    with TestClient(app) as client:
        headers = _login(client)
        budget = client.get("/api/budget", params={"month": "2026-08"}).json()
        account = next(item for item in budget["accounts"] if item["name"] == "Cash Wallet")
        base = {
            "account_id": account["id"],
            "name": "Safe alert name",
            "comparison": "below",
            "threshold": "100",
            "channels": ["smtp"],
            "enabled": True,
        }

        unsafe_name = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={**base, "name": "Unsafe\r\nSubject"},
        )
        assert unsafe_name.status_code == 422

        extreme_exponent = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={**base, "threshold": "1e999999"},
        )
        assert extreme_exponent.status_code == 400

        numeric_overflow = client.post(
            "/api/alerts/balances",
            headers=headers,
            json={**base, "threshold": "10000000000000000"},
        )
        assert numeric_overflow.status_code == 400
        assert "outside the supported range" in numeric_overflow.json()["detail"]


def test_silent_alert_closure_cancels_unsent_trigger_delivery(monkeypatch) -> None:
    _reset()
    _enable_smtp(monkeypatch)

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.name == "Cash Wallet"))
        alert = BalanceAlert(
            workspace_id=account.workspace_id,
            account_id=account.id,
            account=account,
            name="Cash is low",
            comparison="below",
            threshold=Decimal("100"),
            channels=["smtp"],
            enabled=True,
        )
        db.add(alert)
        db.flush()
        assert evaluate_balance_alert(db, alert) is True
        assert close_balance_alert_episode(db, alert) is True
        db.commit()

    with SessionLocal() as db:
        delivery = db.scalar(select(NotificationOutbox))
        incident = db.scalar(select(NotificationIncident))
        assert incident.status == "resolved"
        assert delivery.status == "cancelled"
        assert notifications.process_outbox(db) == 0


def test_ntfy_encodes_unicode_alert_title_as_an_ascii_header(monkeypatch) -> None:
    monkeypatch.setattr(notifications.settings, "ntfy_url", "https://ntfy.example.test")
    monkeypatch.setattr(notifications.settings, "ntfy_topic", "private-budget-alerts")
    monkeypatch.setattr(notifications.settings, "ntfy_token", "")
    captured: dict = {}

    class Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

    def fake_post(url, *, content, headers, timeout):
        captured.update(url=url, content=content, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    notifications._send_ntfy(
        {
            "title": "Café checking is low",
            "message": "The current balance crossed its threshold.",
            "severity": "warning",
        }
    )

    encoded_title = captured["headers"]["Title"]
    assert encoded_title.isascii()
    assert str(make_header(decode_header(encoded_title))) == "Café checking is low"
