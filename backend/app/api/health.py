from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import BackupRecord, SimpleFinConnection, WorkerHeartbeat
from ..utils import ensure_utc, utcnow
from .deps import AuthContext, current_auth

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


def _health_snapshot(db: Session) -> tuple[bool, dict]:
    now = utcnow()
    worker = db.get(WorkerHeartbeat, "main")
    worker_ok = bool(worker and ensure_utc(worker.heartbeat_at) > now - timedelta(minutes=3))
    stale_connections: list[str] = []
    for connection in db.scalars(select(SimpleFinConnection).where(SimpleFinConnection.enabled.is_(True))).all():
        baseline = ensure_utc(connection.last_success_at or connection.created_at)
        if baseline < now - timedelta(minutes=connection.sync_interval_minutes * 3):
            stale_connections.append(str(connection.id))
    backup = db.scalar(select(BackupRecord).order_by(BackupRecord.verified_at.desc()).limit(1))
    backup_ok = bool(backup and ensure_utc(backup.verified_at) > now - timedelta(hours=settings.backup_stale_hours))
    payload = {
        "worker": "ok" if worker_ok else "stale",
        "synchronization": "ok" if not stale_connections else "stale",
        "backup": "ok" if backup_ok else "stale",
        "stale_connection_count": len(stale_connections),
    }
    return worker_ok and not stale_connections and backup_ok, payload


@router.get("/health/sync")
def sync_health(db: Session = Depends(get_db)) -> dict:
    healthy, payload = _health_snapshot(db)
    if not healthy:
        raise HTTPException(status_code=503, detail=payload)
    return {"status": "ok", **payload}


@router.get("/api/system/status")
def system_status(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    healthy, payload = _health_snapshot(db)
    return {"healthy": healthy, **payload}
