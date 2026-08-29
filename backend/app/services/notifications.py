from __future__ import annotations

import smtplib
import ssl
import uuid
from email.header import Header
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import NotificationIncident, NotificationOutbox
from ..utils import exponential_backoff, sanitize_message, utcnow

settings = get_settings()


def _normalize_incident_key(value: str) -> str:
    return str(value)[:255]


def configured_channels() -> list[str]:
    channels: list[str] = []
    if settings.smtp_enabled:
        channels.append("smtp")
    if settings.ntfy_enabled:
        channels.append("ntfy")
    return channels


def _queue_delivery(
    db: Session,
    incident: NotificationIncident,
    *,
    recovery: bool = False,
    channels: list[str] | None = None,
) -> None:
    title = f"Resolved: {incident.title}" if recovery else incident.title
    message = (
        f"The incident has recovered.\n\n{incident.message}"
        if recovery
        else incident.message
    )
    # Operational incidents without an explicit channel selection follow the
    # channels currently configured by the deployment. Explicit selections,
    # such as balance-alert channels, are durable user intent: queue them even
    # while the deployment is temporarily missing that channel's credentials.
    selected_channels = configured_channels() if channels is None else channels
    for channel in dict.fromkeys(selected_channels):
        db.add(
            NotificationOutbox(
                incident_id=incident.id,
                channel=channel,
                payload={
                    "title": sanitize_message(title, 200),
                    "message": sanitize_message(message, 2000),
                    "severity": "info" if recovery else incident.severity,
                    "incident_key": incident.incident_key,
                },
                next_attempt_at=utcnow(),
            )
        )


def open_incident(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    incident_key: str,
    severity: str,
    title: str,
    message: str,
    channels: list[str] | None = None,
) -> NotificationIncident:
    incident_key = _normalize_incident_key(incident_key)
    incident = db.scalar(
        select(NotificationIncident).where(
            NotificationIncident.workspace_id == workspace_id,
            NotificationIncident.incident_key == incident_key,
            NotificationIncident.status == "open",
        )
    )
    now = utcnow()
    if incident:
        incident.last_seen_at = now
        incident.occurrence_count += 1
        incident.severity = severity
        incident.title = sanitize_message(title, 200)
        incident.message = sanitize_message(message, 2000)
        return incident

    created = False
    try:
        # The partial unique index permits one open incident per key. A savepoint
        # makes concurrent detectors collapse into that same incident without
        # aborting the surrounding sync transaction.
        with db.begin_nested():
            incident = NotificationIncident(
                workspace_id=workspace_id,
                incident_key=incident_key,
                severity=severity,
                title=sanitize_message(title, 200),
                message=sanitize_message(message, 2000),
                status="open",
                opened_at=now,
                last_seen_at=now,
            )
            db.add(incident)
            db.flush()
            created = True
    except IntegrityError:
        incident = db.scalar(
            select(NotificationIncident).where(
                NotificationIncident.workspace_id == workspace_id,
                NotificationIncident.incident_key == incident_key,
                NotificationIncident.status == "open",
            )
        )
        if incident is None:
            raise
        incident.last_seen_at = now
        incident.occurrence_count += 1
        incident.severity = severity
        incident.title = sanitize_message(title, 200)
        incident.message = sanitize_message(message, 2000)
    if created:
        _queue_delivery(db, incident, channels=channels)
    return incident


def resolve_incident(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    incident_key: str,
    channels: list[str] | None = None,
    notify_recovery: bool = True,
    cancel_pending: bool = False,
    title: str | None = None,
    message: str | None = None,
) -> bool:
    incident_key = _normalize_incident_key(incident_key)
    incident = db.scalar(
        select(NotificationIncident).where(
            NotificationIncident.workspace_id == workspace_id,
            NotificationIncident.incident_key == incident_key,
            NotificationIncident.status == "open",
        ).with_for_update()
    )
    if not incident:
        return False
    if title is not None:
        incident.title = sanitize_message(title, 200)
    if message is not None:
        incident.message = sanitize_message(message, 2000)
    incident.status = "resolved"
    incident.resolved_at = utcnow()
    incident.last_seen_at = incident.resolved_at
    if cancel_pending:
        # A trigger can be opened and administratively closed in the same
        # transaction. Flush its newly queued outbox rows before cancelling
        # them so none are inserted afterward with a stale pending status.
        db.flush()
        db.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.incident_id == incident.id,
                NotificationOutbox.status.in_(["pending", "retry"]),
            )
            .values(
                status="cancelled",
                last_error="Cancelled because the incident was closed administratively.",
            )
            .execution_options(synchronize_session=False)
        )
    if notify_recovery:
        _queue_delivery(db, incident, recovery=True, channels=channels)
    return True


def _send_smtp(payload: dict[str, Any]) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = settings.smtp_to
    subject = " ".join(f"[{settings.app_name}] {payload['title']}".splitlines())
    message["Subject"] = sanitize_message(subject, 300)
    message.set_content(payload["message"])

    if settings.smtp_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=30,
            context=ssl.create_default_context(),
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
    try:
        client.ehlo()
        if settings.smtp_starttls and not settings.smtp_ssl:
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
    finally:
        try:
            client.quit()
        except Exception:
            client.close()


def _send_ntfy(payload: dict[str, Any]) -> None:
    url = f"{settings.ntfy_url.rstrip('/')}/{settings.ntfy_topic}"
    title = sanitize_message(" ".join(str(payload["title"]).splitlines()), 200)
    # httpx requires header values to be ASCII. ntfy supports RFC 2047 for
    # Unicode titles, so preserve user-written alert names without turning a
    # valid notification into a permanently retrying delivery.
    if not title.isascii():
        title = Header(title, "utf-8", maxlinelen=0).encode(linesep="")
    headers = {
        "Title": title,
        "Priority": {"critical": "5", "warning": "4", "info": "3"}.get(payload.get("severity"), "3"),
        "Tags": "warning" if payload.get("severity") in {"critical", "warning"} else "white_check_mark",
    }
    if settings.ntfy_token:
        headers["Authorization"] = f"Bearer {settings.ntfy_token}"
    response = httpx.post(url, content=payload["message"].encode(), headers=headers, timeout=30)
    response.raise_for_status()


def process_outbox(db: Session, limit: int = 20) -> int:
    rows = db.scalars(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.status.in_(["pending", "retry"]),
            NotificationOutbox.next_attempt_at <= utcnow(),
        )
        .order_by(NotificationOutbox.created_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
    ).all()
    processed = 0
    for row in rows:
        try:
            if row.channel not in configured_channels():
                raise RuntimeError(f"Notification channel is not currently configured: {row.channel}")
            if row.channel == "smtp":
                _send_smtp(row.payload)
            elif row.channel == "ntfy":
                _send_ntfy(row.payload)
            else:
                raise RuntimeError(f"Unknown notification channel: {row.channel}")
            row.status = "sent"
            row.sent_at = utcnow()
            row.last_error = ""
        except Exception as exc:  # delivery errors are persisted and retried
            row.attempts += 1
            row.status = "retry"
            row.last_error = sanitize_message(type(exc).__name__ + ": " + str(exc), 1000)
            row.next_attempt_at = utcnow() + exponential_backoff(row.attempts)
        processed += 1
    return processed
