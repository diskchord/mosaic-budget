from __future__ import annotations

import uuid
from decimal import Decimal, DecimalException

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Account, BalanceAlert
from ..schemas import BalanceAlertRequest, BalanceAlertUpdateRequest
from ..services.audit import write_audit
from ..services.balance_alerts import (
    account_balance_unavailable_reason,
    balance_alert_is_triggered,
    balance_alert_unavailable_reason,
    close_balance_alert_episode,
    evaluate_balance_alert,
)
from ..services.notifications import configured_channels
from ..utils import money_str, parse_decimal
from .deps import AuthContext, require_admin, require_admin_write

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
MAX_MONEY = Decimal("9999999999999999.9999")


def _serialize_alert(alert: BalanceAlert) -> dict:
    unavailable_reason = balance_alert_unavailable_reason(alert)
    current_balance = Decimal(alert.account.balance) if alert.account.balance is not None else None
    return {
        "id": str(alert.id),
        "account_id": str(alert.account_id),
        "account_name": alert.account.name,
        "account_currency": alert.account.currency,
        "current_balance": money_str(current_balance),
        "name": alert.name,
        "comparison": alert.comparison,
        "threshold": money_str(Decimal(alert.threshold)),
        "channels": list(alert.channels or []),
        "enabled": alert.enabled,
        "available": unavailable_reason is None,
        "unavailable_reason": unavailable_reason,
        "triggered": bool(alert.enabled and unavailable_reason is None and balance_alert_is_triggered(alert)),
        "version": alert.version,
        "created_at": alert.created_at.isoformat(),
        "updated_at": alert.updated_at.isoformat(),
    }


def _alert_for_workspace(
    db: Session,
    alert_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    lock: bool = False,
) -> BalanceAlert:
    query = (
        select(BalanceAlert)
        .where(BalanceAlert.id == alert_id, BalanceAlert.workspace_id == workspace_id)
        .options(selectinload(BalanceAlert.account).selectinload(Account.simplefin_connection))
    )
    if lock:
        query = query.with_for_update()
    alert = db.scalar(query)
    if not alert:
        raise HTTPException(status_code=404, detail="Balance alert not found")
    return alert


def _account_for_workspace(
    db: Session,
    account_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    require_monitorable: bool = True,
) -> Account:
    account = db.scalar(
        select(Account)
        .where(
            Account.id == account_id,
            Account.workspace_id == workspace_id,
        )
        .options(selectinload(Account.simplefin_connection))
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    unavailable_reason = account_balance_unavailable_reason(account)
    if require_monitorable and unavailable_reason is not None:
        messages = {
            "duplicate_account": "Duplicate accounts cannot be monitored",
            "inactive_account": "Activate this account before adding a balance alert",
            "balance_unavailable": "This account does not have a known balance yet",
            "connection_unavailable": "Reconnect or resume this account before adding a balance alert",
        }
        raise HTTPException(status_code=400, detail=messages[unavailable_reason])
    return account


def _validated_channels(channels: list[str], *, require_configured: bool = True) -> list[str]:
    channels = list(dict.fromkeys(channels))
    if not require_configured:
        return channels
    available = set(configured_channels())
    unavailable = [channel for channel in channels if channel not in available]
    if unavailable:
        labels = {"smtp": "SMTP2GO/email", "ntfy": "ntfy"}
        missing = ", ".join(labels[channel] for channel in unavailable)
        raise HTTPException(status_code=400, detail=f"Configure {missing} before using that alert channel")
    return channels


def _threshold(value: str) -> Decimal:
    try:
        threshold = parse_decimal(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DecimalException as exc:
        raise HTTPException(status_code=400, detail="Invalid decimal amount") from exc
    if abs(threshold) > MAX_MONEY:
        raise HTTPException(status_code=400, detail="Amount is outside the supported range")
    return threshold


@router.get("/balances")
def list_balance_alerts(
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(BalanceAlert)
        .where(BalanceAlert.workspace_id == auth.user.workspace_id)
        .options(selectinload(BalanceAlert.account).selectinload(Account.simplefin_connection))
        .order_by(BalanceAlert.name, BalanceAlert.created_at)
    ).all()
    return {"alerts": [_serialize_alert(alert) for alert in rows], "available_channels": configured_channels()}


@router.post("/balances")
def create_balance_alert(
    payload: BalanceAlertRequest,
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    account = _account_for_workspace(db, payload.account_id, auth.user.workspace_id)
    alert = BalanceAlert(
        workspace_id=auth.user.workspace_id,
        account_id=account.id,
        account=account,
        name=payload.name.strip(),
        comparison=payload.comparison,
        threshold=_threshold(payload.threshold),
        channels=_validated_channels(list(payload.channels)),
        enabled=payload.enabled,
        created_by_id=auth.user.id,
    )
    db.add(alert)
    db.flush()
    evaluate_balance_alert(db, alert)
    after = _serialize_alert(alert)
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="balance_alert.created",
        object_type="balance_alert",
        object_id=alert.id,
        after=after,
    )
    db.commit()
    return {"alert": after}


@router.patch("/balances/{alert_id}")
def update_balance_alert(
    alert_id: uuid.UUID,
    payload: BalanceAlertUpdateRequest,
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    alert = _alert_for_workspace(db, alert_id, auth.user.workspace_id, lock=True)
    if alert.version != payload.version:
        raise HTTPException(
            status_code=409,
            detail={"message": "Balance alert conflict", "current": _serialize_alert(alert)},
        )
    account = _account_for_workspace(
        db,
        payload.account_id,
        auth.user.workspace_id,
        require_monitorable=payload.enabled,
    )
    threshold = _threshold(payload.threshold)
    channels = _validated_channels(list(payload.channels), require_configured=payload.enabled)
    before = _serialize_alert(alert)
    materially_reconfigured = (
        alert.account_id != account.id
        or alert.comparison != payload.comparison
        or Decimal(alert.threshold) != threshold
        or set(alert.channels or []) != set(channels)
    )
    if materially_reconfigured or alert.enabled != payload.enabled:
        close_balance_alert_episode(db, alert)
    alert.account_id = account.id
    alert.account = account
    alert.name = payload.name.strip()
    alert.comparison = payload.comparison
    alert.threshold = threshold
    alert.channels = channels
    alert.enabled = payload.enabled
    alert.version += 1
    db.flush()
    evaluate_balance_alert(db, alert)
    after = _serialize_alert(alert)
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="balance_alert.updated",
        object_type="balance_alert",
        object_id=alert.id,
        before=before,
        after=after,
    )
    db.commit()
    return {"alert": after}


@router.delete("/balances/{alert_id}")
def delete_balance_alert(
    alert_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    alert = _alert_for_workspace(db, alert_id, auth.user.workspace_id, lock=True)
    if alert.version != version:
        raise HTTPException(
            status_code=409,
            detail={"message": "Balance alert conflict", "current": _serialize_alert(alert)},
        )
    before = _serialize_alert(alert)
    close_balance_alert_episode(db, alert)
    db.delete(alert)
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="balance_alert.deleted",
        object_type="balance_alert",
        object_id=alert.id,
        before=before,
    )
    db.commit()
    return {"ok": True}
