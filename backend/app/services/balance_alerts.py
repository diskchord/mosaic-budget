from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Account, BalanceAlert
from ..utils import money_str
from .notifications import open_incident, resolve_incident


def balance_alert_key(alert_id: uuid.UUID) -> str:
    return f"balance-alert:{alert_id}"


def account_balance_unavailable_reason(account: Account) -> str | None:
    if account.is_duplicate:
        return "duplicate_account"
    if not account.is_active:
        return "inactive_account"
    if account.source_type == "simplefin":
        connection = account.simplefin_connection
        if connection is None or not connection.enabled or not connection.encrypted_access_url:
            return "connection_unavailable"
    if account.balance is None:
        return "balance_unavailable"
    return None


def balance_alert_unavailable_reason(alert: BalanceAlert) -> str | None:
    return account_balance_unavailable_reason(alert.account)


def balance_alert_is_triggered(alert: BalanceAlert) -> bool:
    if balance_alert_unavailable_reason(alert) is not None:
        return False
    balance = Decimal(alert.account.balance)
    threshold = Decimal(alert.threshold)
    return balance < threshold if alert.comparison == "below" else balance > threshold


def _balance_alert_message(alert: BalanceAlert, *, recovered: bool = False) -> str:
    balance = money_str(Decimal(alert.account.balance))
    threshold = money_str(Decimal(alert.threshold))
    direction = "below" if alert.comparison == "below" else "above"
    qualifier = f"no longer {direction}" if recovered else direction
    currency = alert.account.currency or "USD"
    return (
        f"{alert.account.name} balance is {currency} {balance}, {qualifier} "
        f"the configured threshold of {currency} {threshold}."
    )


def close_balance_alert_episode(db: Session, alert: BalanceAlert) -> bool:
    return resolve_incident(
        db,
        workspace_id=alert.workspace_id,
        incident_key=balance_alert_key(alert.id),
        channels=list(alert.channels or []),
        notify_recovery=False,
        cancel_pending=True,
    )


def evaluate_balance_alert(db: Session, alert: BalanceAlert) -> bool:
    key = balance_alert_key(alert.id)
    channels = list(alert.channels or [])
    if not alert.enabled or balance_alert_unavailable_reason(alert) is not None:
        close_balance_alert_episode(db, alert)
        return False

    triggered = balance_alert_is_triggered(alert)
    if not triggered:
        resolve_incident(
            db,
            workspace_id=alert.workspace_id,
            incident_key=key,
            channels=channels,
            title=alert.name,
            message=_balance_alert_message(alert, recovered=True),
        )
        return False

    open_incident(
        db,
        workspace_id=alert.workspace_id,
        incident_key=key,
        severity="warning",
        title=alert.name,
        message=_balance_alert_message(alert),
        channels=channels,
    )
    return True


def evaluate_balance_alerts(
    db: Session,
    *,
    workspace_id: uuid.UUID | None = None,
    account_ids: set[uuid.UUID] | None = None,
) -> dict[str, int]:
    query = (
        select(BalanceAlert)
        .options(selectinload(BalanceAlert.account).selectinload(Account.simplefin_connection))
        .where(BalanceAlert.enabled.is_(True))
        .with_for_update(skip_locked=True)
    )
    if workspace_id is not None:
        query = query.where(BalanceAlert.workspace_id == workspace_id)
    if account_ids is not None:
        if not account_ids:
            return {"evaluated": 0, "triggered": 0}
        query = query.where(BalanceAlert.account_id.in_(account_ids))
    alerts = db.scalars(query.order_by(BalanceAlert.created_at, BalanceAlert.id)).all()
    triggered = sum(1 for alert in alerts if evaluate_balance_alert(db, alert))
    return {"evaluated": len(alerts), "triggered": triggered}
