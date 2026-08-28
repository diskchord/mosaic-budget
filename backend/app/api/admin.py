from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import (
    AuditEvent,
    BackupRecord,
    NotificationIncident,
    SessionRecord,
    User,
    WorkerHeartbeat,
)
from ..schemas import IncidentAcknowledgeRequest, UserCreateRequest, UserUpdateRequest
from ..security import hash_password
from ..services.audit import write_audit
from ..services.notifications import open_incident
from ..utils import ensure_utc, jsonable, utcnow
from .auth import user_payload
from .deps import AuthContext, require_admin, require_admin_write

router = APIRouter(prefix="/api/admin", tags=["administration"])
settings = get_settings()


def _user_for_workspace(db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID, *, lock: bool = False) -> User:
    query = select(User).where(User.id == user_id, User.workspace_id == workspace_id)
    if lock:
        query = query.with_for_update()
    user = db.scalar(query)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users")
def list_users(auth: AuthContext = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(User).where(User.workspace_id == auth.user.workspace_id).order_by(User.is_admin.desc(), User.display_name)
    ).all()
    return {"users": [user_payload(user) for user in rows]}


@router.post("/users")
def create_user(
    payload: UserCreateRequest,
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    if payload.is_admin:
        raise HTTPException(status_code=400, detail="There is one owner. Use Transfer ownership instead")
    email = str(payload.email).casefold()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    user = User(
        workspace_id=auth.user.workspace_id,
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        is_admin=False,
        is_active=True,
        theme="citrus",
        preferences={"density": "comfortable", "motion": "full", "show_cents": True},
    )
    db.add(user)
    db.flush()
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="user.created",
        object_type="user",
        object_id=user.id,
        after=user_payload(user),
    )
    db.commit()
    return {"user": user_payload(user)}


@router.patch("/users/{user_id}")
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    user = _user_for_workspace(db, user_id, auth.user.workspace_id, lock=True)
    if user.version != payload.version:
        raise HTTPException(status_code=409, detail={"message": "User conflict", "current": user_payload(user)})
    if payload.is_admin is not None and payload.is_admin != user.is_admin:
        raise HTTPException(status_code=400, detail="Use Transfer ownership to change the administrator")
    if user.is_admin and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Transfer ownership before disabling the administrator")
    before = user_payload(user)
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not user.is_active:
            db.execute(delete(SessionRecord).where(SessionRecord.user_id == user.id))
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        db.execute(delete(SessionRecord).where(SessionRecord.user_id == user.id))
    user.version += 1
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="user.updated",
        object_type="user",
        object_id=user.id,
        before=before,
        after=user_payload(user),
    )
    db.commit()
    return {"user": user_payload(user)}


@router.delete("/users/{user_id}")
def remove_user(
    user_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    user = _user_for_workspace(db, user_id, auth.user.workspace_id, lock=True)
    if user.is_admin:
        raise HTTPException(status_code=400, detail="The owner cannot be removed")
    if user.version != version:
        raise HTTPException(status_code=409, detail={"message": "User conflict", "current": user_payload(user)})
    before = user_payload(user)
    user.is_active = False
    user.version += 1
    db.execute(delete(SessionRecord).where(SessionRecord.user_id == user.id))
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="user.removed",
        object_type="user",
        object_id=user.id,
        before=before,
        after=user_payload(user),
    )
    db.commit()
    return {"ok": True}


@router.post("/transfer-ownership/{user_id}")
def transfer_ownership(
    user_id: uuid.UUID,
    target_version: int = Body(..., embed=True, ge=1),
    owner_version: int = Body(..., embed=True, ge=1),
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    owner = _user_for_workspace(db, auth.user.id, auth.user.workspace_id, lock=True)
    target = _user_for_workspace(db, user_id, auth.user.workspace_id, lock=True)
    if target.id == owner.id:
        return {"owner": user_payload(owner)}
    if not target.is_active:
        raise HTTPException(status_code=400, detail="Enable the target user before transferring ownership")
    if owner.version != owner_version or target.version != target_version:
        raise HTTPException(
            status_code=409,
            detail={"message": "Ownership changed while you were editing", "owner": user_payload(owner), "target": user_payload(target)},
        )
    owner.is_admin = False
    owner.version += 1
    # The database enforces at most one owner with a partial unique index.
    # Flush the demotion before promoting the target so the invariant also
    # holds during the statement sequence.
    db.flush()
    target.is_admin = True
    target.version += 1
    write_audit(
        db,
        workspace_id=owner.workspace_id,
        actor_user_id=owner.id,
        action="workspace.ownership.transferred",
        object_type="user",
        object_id=target.id,
        detail={"previous_owner_id": str(owner.id), "new_owner_id": str(target.id)},
    )
    db.commit()
    return {"owner": user_payload(target), "previous_owner": user_payload(owner)}


@router.get("/incidents")
def list_incidents(
    include_resolved: bool = False,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    query = select(NotificationIncident).where(NotificationIncident.workspace_id == auth.user.workspace_id)
    if not include_resolved:
        query = query.where(NotificationIncident.status == "open")
    rows = db.scalars(query.order_by(NotificationIncident.last_seen_at.desc()).limit(200)).all()
    return {
        "incidents": [
            {
                "id": str(row.id),
                "incident_key": row.incident_key,
                "severity": row.severity,
                "title": row.title,
                "message": row.message,
                "status": row.status,
                "occurrence_count": row.occurrence_count,
                "opened_at": row.opened_at.isoformat(),
                "last_seen_at": row.last_seen_at.isoformat(),
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
            }
            for row in rows
        ]
    }


@router.post("/incidents/{incident_id}/acknowledge")
def acknowledge_incident(
    incident_id: uuid.UUID,
    payload: IncidentAcknowledgeRequest,
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(
        select(NotificationIncident)
        .where(NotificationIncident.id == incident_id, NotificationIncident.workspace_id == auth.user.workspace_id)
        .with_for_update()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    row.acknowledged_at = utcnow() if payload.acknowledged else None
    row.acknowledged_by_id = auth.user.id if payload.acknowledged else None
    db.commit()
    return {"ok": True}


@router.post("/notifications/test")
def test_notifications(
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    channels = [name for name, enabled in (("smtp", settings.smtp_enabled), ("ntfy", settings.ntfy_enabled)) if enabled]
    if not channels:
        raise HTTPException(status_code=400, detail="Configure SMTP or ntfy before sending a test")
    key = f"notification-test:{auth.user.id}:{int(utcnow().timestamp())}"
    incident = open_incident(
        db,
        workspace_id=auth.user.workspace_id,
        incident_key=key,
        severity="info",
        title="Mosaic Budget notification test",
        message="The background notification pipeline is configured and able to queue this test.",
    )
    # The outbox rows remain durable, but a successful test request should not
    # leave a permanent open incident in the application's alert center.
    incident.status = "resolved"
    incident.resolved_at = utcnow()
    db.commit()
    return {"queued": True, "incident_id": str(incident.id), "channels": channels}


@router.get("/audit")
def audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.workspace_id == auth.user.workspace_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "events": [
            {
                "id": str(row.id),
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "action": row.action,
                "object_type": row.object_type,
                "object_id": str(row.object_id) if row.object_id else None,
                "detail": row.detail,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/operations")
def operations_status(auth: AuthContext = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    worker = db.get(WorkerHeartbeat, "main")
    backup = db.scalar(select(BackupRecord).order_by(BackupRecord.verified_at.desc()).limit(1))
    return {
        "worker": {
            "heartbeat_at": worker.heartbeat_at.isoformat() if worker else None,
            "healthy": bool(worker and ensure_utc(worker.heartbeat_at) > utcnow() - timedelta(minutes=3)),
            "detail": worker.detail if worker else {},
        },
        "backup": {
            "verified_at": backup.verified_at.isoformat() if backup else None,
            "byte_size": backup.byte_size if backup else None,
            "path": backup.path if backup else None,
        },
    }
