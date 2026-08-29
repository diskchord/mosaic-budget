from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Account, BudgetTransaction, SimpleFinConnection, SyncRun
from ..schemas import AccountBatchUpdateItem, AccountBatchUpdateRequest, SimpleFinClaimRequest
from ..security import encrypt_secret
from ..services.audit import write_audit
from ..services.balance_alerts import evaluate_balance_alerts
from ..services.budgets import serialize_account
from ..services.simplefin import SimpleFinError, claim_setup_token
from ..utils import utcnow
from .deps import AuthContext, current_auth, require_admin_write

router = APIRouter(prefix="/api/connections", tags=["connections"])
settings = get_settings()
SAFE_MINUTES = [7, 11, 17, 23, 29, 37, 41, 47, 53]


def _connection_for_user(
    db: Session,
    connection_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    lock: bool = False,
) -> SimpleFinConnection:
    query = select(SimpleFinConnection).where(
        SimpleFinConnection.id == connection_id,
        SimpleFinConnection.workspace_id == workspace_id,
    )
    if lock:
        query = query.with_for_update()
    connection = db.scalar(query)
    if not connection:
        raise HTTPException(status_code=404, detail="SimpleFIN connection not found")
    return connection


def connection_payload(connection: SimpleFinConnection) -> dict:
    return {
        "id": str(connection.id),
        "name": connection.name,
        "enabled": connection.enabled,
        "connected": bool(connection.encrypted_access_url),
        "sync_interval_minutes": connection.sync_interval_minutes,
        "last_attempt_at": connection.last_attempt_at.isoformat() if connection.last_attempt_at else None,
        "last_success_at": connection.last_success_at.isoformat() if connection.last_success_at else None,
        "next_sync_at": connection.next_sync_at.isoformat(),
        "consecutive_failures": connection.consecutive_failures,
        "last_error_code": connection.last_error_code,
        "last_error_message": connection.last_error_message,
        "disconnected_at": connection.disconnected_at.isoformat() if connection.disconnected_at else None,
        "version": connection.version,
    }


def _apply_account_values(
    db: Session,
    account: Account,
    *,
    name: str | None,
    is_budget: bool | None,
    is_active: bool | None,
    is_duplicate: bool | None,
) -> tuple[int, int]:
    suppressed_count = 0
    restored_count = 0
    if is_duplicate is not None and is_duplicate != account.is_duplicate:
        if is_duplicate:
            result = db.execute(
                update(BudgetTransaction)
                .where(
                    BudgetTransaction.account_id == account.id,
                    BudgetTransaction.deleted_at.is_(None),
                    BudgetTransaction.excluded.is_(False),
                )
                .values(
                    excluded=True,
                    suppressed_by_duplicate_account=True,
                    version=BudgetTransaction.version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            suppressed_count = int(result.rowcount or 0)
        else:
            result = db.execute(
                update(BudgetTransaction)
                .where(
                    BudgetTransaction.account_id == account.id,
                    BudgetTransaction.suppressed_by_duplicate_account.is_(True),
                )
                .values(
                    excluded=False,
                    suppressed_by_duplicate_account=False,
                    version=BudgetTransaction.version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            restored_count = int(result.rowcount or 0)
        account.is_duplicate = is_duplicate
    if name is not None:
        account.name = name
    if is_budget is not None:
        account.is_budget = is_budget
    if is_active is not None:
        account.is_active = is_active
    return suppressed_count, restored_count


def _write_account_update_audit(
    db: Session,
    *,
    account: Account,
    before: dict,
    auth: AuthContext,
    suppressed_count: int,
    restored_count: int,
) -> None:
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="account.updated",
        object_type="account",
        object_id=account.id,
        before=before,
        after=serialize_account(account),
        detail={
            "transactions_suppressed": suppressed_count,
            "transactions_restored": restored_count,
        },
    )


def _evaluate_account_alerts(db: Session, workspace_id: uuid.UUID, account_ids: set[uuid.UUID]) -> None:
    if not account_ids:
        return
    db.flush()
    evaluate_balance_alerts(db, workspace_id=workspace_id, account_ids=account_ids)


def _batch_accounts_for_connection(
    db: Session,
    account_inputs: list[AccountBatchUpdateItem],
    connection: SimpleFinConnection,
    workspace_id: uuid.UUID,
) -> list[Account]:
    requested_ids = [item.id for item in account_inputs]
    requested_versions = {item.id: item.version for item in account_inputs}
    rows = db.scalars(
        select(Account)
        .where(
            Account.id.in_(requested_ids),
            Account.workspace_id == workspace_id,
            Account.simplefin_connection_id == connection.id,
        )
        .order_by(Account.id)
        .with_for_update()
    ).all()
    by_id = {account.id: account for account in rows}
    if set(by_id) != set(requested_ids):
        raise HTTPException(status_code=404, detail="One or more accounts were not found in this connection")

    accounts = [by_id[account_id] for account_id in requested_ids]
    if any(account.source_type != "simplefin" for account in accounts):
        raise HTTPException(status_code=400, detail="Only SimpleFIN accounts can be updated through a connection")

    conflicts = [
        {
            "id": str(account.id),
            "expected_version": requested_versions[account.id],
            "current": serialize_account(account),
        }
        for account in accounts
        if account.version != requested_versions[account.id]
    ]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "One or more accounts changed on another device",
                "conflicts": conflicts,
            },
        )
    return accounts


@router.get("")
def list_connections(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(SimpleFinConnection)
        .where(SimpleFinConnection.workspace_id == auth.user.workspace_id)
        .order_by(SimpleFinConnection.created_at)
    ).all()
    return {"connections": [connection_payload(row) for row in rows]}


@router.post("/simplefin")
def connect_simplefin(
    payload: SimpleFinClaimRequest,
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    try:
        access_url, fingerprint = claim_setup_token(payload.setup_token)
    except SimpleFinError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)}) from exc
    if db.scalar(select(SimpleFinConnection.id).where(SimpleFinConnection.access_url_fingerprint == fingerprint)):
        raise HTTPException(status_code=409, detail="This SimpleFIN Access URL is already connected")
    connection = SimpleFinConnection(
        workspace_id=auth.user.workspace_id,
        name=payload.name.strip(),
        encrypted_access_url=encrypt_secret(access_url),
        access_url_fingerprint=fingerprint,
        enabled=True,
        sync_interval_minutes=settings.simplefin_sync_interval_minutes,
        schedule_minute=secrets.choice(SAFE_MINUTES),
        next_sync_at=utcnow(),
        created_by_id=auth.user.id,
    )
    db.add(connection)
    db.flush()
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="simplefin.connected",
        object_type="simplefin_connection",
        object_id=connection.id,
        after={"name": connection.name, "schedule_minute": connection.schedule_minute},
    )
    db.commit()
    return {
        "connection": connection_payload(connection),
        "message": "Connected. The background worker will begin the first import automatically.",
    }


@router.patch("/{connection_id}")
def update_connection(
    connection_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    name: str | None = Body(default=None, embed=True, max_length=160),
    enabled: bool | None = Body(default=None, embed=True),
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    connection = _connection_for_user(db, connection_id, auth.user.workspace_id, lock=True)
    if connection.version != version:
        raise HTTPException(status_code=409, detail={"message": "Connection conflict", "current": connection_payload(connection)})
    before = connection_payload(connection)
    if name is not None and name.strip():
        connection.name = name.strip()
    if enabled is not None:
        if enabled and not connection.encrypted_access_url:
            raise HTTPException(status_code=400, detail="This connection has been disconnected and has no credential")
        connection.enabled = enabled
        if enabled:
            connection.next_sync_at = utcnow()
    connection.version += 1
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="simplefin.updated",
        object_type="simplefin_connection",
        object_id=connection.id,
        before=before,
        after=connection_payload(connection),
    )
    if enabled is not None:
        account_ids = set(
            db.scalars(select(Account.id).where(Account.simplefin_connection_id == connection.id)).all()
        )
        _evaluate_account_alerts(db, auth.user.workspace_id, account_ids)
    db.commit()
    return {"connection": connection_payload(connection)}


@router.post("/{connection_id}/retry")
def retry_failed_connection(
    connection_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    connection = _connection_for_user(db, connection_id, auth.user.workspace_id, lock=True)
    if connection.version != version:
        raise HTTPException(status_code=409, detail={"message": "Connection conflict", "current": connection_payload(connection)})
    if not connection.enabled or not connection.encrypted_access_url:
        raise HTTPException(status_code=400, detail="The connection is disabled or disconnected")
    connection.next_sync_at = utcnow()
    connection.version += 1
    db.commit()
    return {"connection": connection_payload(connection)}


@router.delete("/{connection_id}")
def disconnect_simplefin(
    connection_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    confirm_name: str = Body(..., embed=True),
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    connection = _connection_for_user(db, connection_id, auth.user.workspace_id, lock=True)
    if connection.version != version:
        raise HTTPException(status_code=409, detail={"message": "Connection conflict", "current": connection_payload(connection)})
    if confirm_name.strip() != connection.name:
        raise HTTPException(status_code=400, detail="Type the connection name exactly to disconnect it")
    before = connection_payload(connection)
    connection.enabled = False
    connection.encrypted_access_url = None
    connection.disconnected_at = utcnow()
    connection.version += 1
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="simplefin.disconnected",
        object_type="simplefin_connection",
        object_id=connection.id,
        before=before,
        after=connection_payload(connection),
        detail={"imported_transactions_retained": True},
    )
    account_ids = set(
        db.scalars(select(Account.id).where(Account.simplefin_connection_id == connection.id)).all()
    )
    _evaluate_account_alerts(db, auth.user.workspace_id, account_ids)
    db.commit()
    return {"ok": True, "connection": connection_payload(connection)}


@router.get("/{connection_id}/accounts")
def list_connection_accounts(
    connection_id: uuid.UUID,
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_db),
) -> dict:
    connection = _connection_for_user(db, connection_id, auth.user.workspace_id)
    rows = db.scalars(
        select(Account).where(Account.simplefin_connection_id == connection.id).order_by(Account.name)
    ).all()
    return {"accounts": [serialize_account(account) for account in rows]}


@router.patch("/{connection_id}/accounts")
def update_connection_accounts(
    connection_id: uuid.UUID,
    payload: AccountBatchUpdateRequest,
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    connection = _connection_for_user(db, connection_id, auth.user.workspace_id)
    accounts = _batch_accounts_for_connection(
        db,
        payload.accounts,
        connection,
        auth.user.workspace_id,
    )

    updated_count = 0
    updated_account_ids: set[uuid.UUID] = set()
    for account, item in zip(accounts, payload.accounts, strict=True):
        changed = (
            account.name != item.name
            or account.is_budget != item.is_budget
            or account.is_active != item.is_active
            or account.is_duplicate != item.is_duplicate
        )
        if not changed:
            continue

        before = serialize_account(account)
        suppressed_count, restored_count = _apply_account_values(
            db,
            account,
            name=item.name,
            is_budget=item.is_budget,
            is_active=item.is_active,
            is_duplicate=item.is_duplicate,
        )
        account.version += 1
        _write_account_update_audit(
            db,
            account=account,
            before=before,
            auth=auth,
            suppressed_count=suppressed_count,
            restored_count=restored_count,
        )
        updated_count += 1
        updated_account_ids.add(account.id)

    _evaluate_account_alerts(db, auth.user.workspace_id, updated_account_ids)
    db.commit()
    return {
        "accounts": [serialize_account(account) for account in accounts],
        "updated_count": updated_count,
    }


@router.patch("/accounts/{account_id}")
def update_account(
    account_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    name: str | None = Body(default=None, embed=True, max_length=255),
    is_budget: bool | None = Body(default=None, embed=True),
    is_active: bool | None = Body(default=None, embed=True),
    is_duplicate: bool | None = Body(default=None, embed=True),
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    account = db.scalar(
        select(Account)
        .where(Account.id == account_id, Account.workspace_id == auth.user.workspace_id)
        .with_for_update()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.version != version:
        raise HTTPException(status_code=409, detail={"message": "Account conflict", "current": serialize_account(account)})
    if is_duplicate is not None and account.source_type != "simplefin":
        raise HTTPException(status_code=400, detail="Only SimpleFIN accounts can be marked as duplicates")
    clean_name = name.strip() if name is not None else None
    if name is not None and not clean_name:
        raise HTTPException(status_code=400, detail="Account name cannot be blank")

    before = serialize_account(account)
    suppressed_count, restored_count = _apply_account_values(
        db,
        account,
        name=clean_name,
        is_budget=is_budget,
        is_active=is_active,
        is_duplicate=is_duplicate,
    )
    account.version += 1
    _write_account_update_audit(
        db,
        account=account,
        before=before,
        auth=auth,
        suppressed_count=suppressed_count,
        restored_count=restored_count,
    )
    _evaluate_account_alerts(db, auth.user.workspace_id, {account.id})
    db.commit()
    return {"account": serialize_account(account)}


@router.get("/{connection_id}/runs")
def list_sync_runs(
    connection_id: uuid.UUID,
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_db),
) -> dict:
    connection = _connection_for_user(db, connection_id, auth.user.workspace_id)
    rows = db.scalars(
        select(SyncRun)
        .where(SyncRun.simplefin_connection_id == connection.id)
        .order_by(SyncRun.started_at.desc())
        .limit(50)
    ).all()
    return {
        "runs": [
            {
                "id": str(row.id),
                "started_at": row.started_at.isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "status": row.status,
                "mode": row.mode,
                "accounts_seen": row.accounts_seen,
                "transactions_seen": row.transactions_seen,
                "transactions_new": row.transactions_new,
                "transactions_changed": row.transactions_changed,
                "errors_seen": row.errors_seen,
                "error_code": row.error_code,
                "error_message": row.error_message,
            }
            for row in rows
        ]
    }
