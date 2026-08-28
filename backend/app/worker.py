from __future__ import annotations

import logging
import time
from datetime import timedelta

import httpx
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import BackupRecord, SimpleFinConnection, WorkerHeartbeat, Workspace
from .security import purge_expired_sessions
from .services.notifications import open_incident, process_outbox, resolve_incident
from .services.sync import perform_sync
from .utils import ensure_utc, utcnow

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def heartbeat(db, detail: dict | None = None) -> None:
    row = db.get(WorkerHeartbeat, "main")
    if row is None:
        row = WorkerHeartbeat(worker_name="main", heartbeat_at=utcnow(), detail=detail or {})
        db.add(row)
    else:
        row.heartbeat_at = utcnow()
        row.detail = detail or {}


def monitor_health(db) -> None:
    now = utcnow()
    for connection in db.scalars(select(SimpleFinConnection).where(SimpleFinConnection.enabled.is_(True))).all():
        stale_after = timedelta(minutes=connection.sync_interval_minutes * 3)
        baseline = ensure_utc(connection.last_success_at or connection.created_at)
        key = f"simplefin-stale:{connection.id}"
        if baseline < now - stale_after:
            open_incident(
                db,
                workspace_id=connection.workspace_id,
                incident_key=key,
                severity="warning",
                title="SimpleFIN has not synchronized recently",
                message="No successful automatic synchronization has completed within three expected cycles.",
            )
        else:
            resolve_incident(db, workspace_id=connection.workspace_id, incident_key=key)

    latest_backup = db.scalar(select(BackupRecord).order_by(BackupRecord.verified_at.desc()).limit(1))
    for workspace in db.scalars(select(Workspace)).all():
        key = f"backup-stale:{workspace.id}"
        if ensure_utc(workspace.created_at) < now - timedelta(hours=settings.backup_stale_hours) and (
            latest_backup is None
            or ensure_utc(latest_backup.verified_at) < now - timedelta(hours=settings.backup_stale_hours)
        ):
            open_incident(
                db,
                workspace_id=workspace.id,
                incident_key=key,
                severity="critical",
                title="Verified database backups are stale",
                message="The application has not recorded a successful backup and restore verification recently.",
            )
        else:
            resolve_incident(db, workspace_id=workspace.id, incident_key=key)


def ping_external_heartbeat() -> None:
    if not settings.external_heartbeat_url:
        return
    try:
        response = httpx.get(settings.external_heartbeat_url, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("External heartbeat failed: %s", type(exc).__name__)


def run() -> None:
    last_monitor = 0.0
    last_external_ping = 0.0
    logger.info("Mosaic background worker started")
    while True:
        cycle_started = time.monotonic()
        try:
            db = SessionLocal()
            try:
                due_ids = db.scalars(
                    select(SimpleFinConnection.id)
                    .where(
                        SimpleFinConnection.enabled.is_(True),
                        SimpleFinConnection.next_sync_at <= utcnow(),
                    )
                    .order_by(SimpleFinConnection.next_sync_at)
                    .limit(4)
                ).all()
                heartbeat(db, {"due_connections": len(due_ids)})
                db.commit()
            finally:
                db.close()

            for connection_id in due_ids:
                result = perform_sync(connection_id)
                logger.info("SimpleFIN sync %s: %s", connection_id, result.get("status"))

            db = SessionLocal()
            try:
                processed = process_outbox(db)
                purge_expired_sessions(db)
                if time.monotonic() - last_monitor > 300:
                    monitor_health(db)
                    last_monitor = time.monotonic()
                heartbeat(db, {"notifications_processed": processed, "last_cycle_seconds": round(time.monotonic() - cycle_started, 3)})
                db.commit()
            finally:
                db.close()

            if time.monotonic() - last_external_ping > 300:
                ping_external_heartbeat()
                last_external_ping = time.monotonic()
        except Exception:
            logger.exception("Worker cycle failed")
        time.sleep(20)


if __name__ == "__main__":
    run()
