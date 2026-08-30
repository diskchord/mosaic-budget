from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import LoginThrottle, SessionRecord, User, Workspace
from ..schemas import LoginRequest, PreferenceRequest
from ..security import (
    SESSION_COOKIE,
    clear_session_cookies,
    create_session,
    hash_password,
    password_needs_rehash,
    revoke_session,
    set_session_cookies,
    verify_password,
)
from ..services.audit import write_audit
from ..utils import ensure_utc, utcnow
from .deps import AuthContext, current_auth, require_write

router = APIRouter(prefix="/api/auth", tags=["authentication"])
settings = get_settings()
THEMES = ["citrus", "ocean", "berry", "meadow", "sunrise", "high-contrast", "system"]
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_BLOCK = timedelta(minutes=15)
LOGIN_FAILURE_LIMIT = 5
# A real Argon2 hash keeps nonexistent-account attempts on the same expensive path.
DUMMY_PASSWORD_HASH = hash_password("mosaic-dummy-password-never-used")


def _throttle_key(email: str, request: Request) -> str:
    address = request.client.host if request.client else "unknown"
    material = f"{email}|{address}|{settings.app_secret_key}"
    return hashlib.sha256(material.encode()).hexdigest()


def _check_login_throttle(db: Session, key_hash: str) -> LoginThrottle | None:
    row = db.scalar(select(LoginThrottle).where(LoginThrottle.key_hash == key_hash).with_for_update())
    now = utcnow()
    if row and row.blocked_until and ensure_utc(row.blocked_until) > now:
        retry = max(1, int((ensure_utc(row.blocked_until) - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many sign-in attempts. Try again in {retry // 60 + 1} minutes.",
            headers={"Retry-After": str(retry)},
        )
    return row


def _record_login_failure(db: Session, row: LoginThrottle | None, key_hash: str) -> None:
    now = utcnow()
    if row is None:
        row = LoginThrottle(key_hash=key_hash, failures=0, window_started_at=now)
        db.add(row)
    elif ensure_utc(row.window_started_at) < now - LOGIN_WINDOW:
        row.failures = 0
        row.window_started_at = now
        row.blocked_until = None
    row.failures += 1
    if row.failures >= LOGIN_FAILURE_LIMIT:
        row.blocked_until = now + LOGIN_BLOCK



def user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "theme": user.theme,
        "preferences": user.preferences,
        "version": user.version,
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Response:
    email = str(payload.email).casefold()
    throttle_key = _throttle_key(email, request)
    throttle = _check_login_throttle(db, throttle_key)
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or not user.is_active or not valid:
        _record_login_failure(db, throttle, throttle_key)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect")
    if throttle:
        db.delete(throttle)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.last_login_at = utcnow()
    tokens = create_session(db, user, request)
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_user_id=user.id,
        action="auth.login",
        object_type="user",
        object_id=user.id,
    )
    db.commit()
    response = JSONResponse({"user": user_payload(user), "app_name": settings.app_name})
    set_session_cookies(response, tokens)
    return response


@router.post("/logout")
def logout(request: Request, auth: AuthContext = Depends(require_write), db: Session = Depends(get_db)) -> Response:
    revoke_session(db, request.cookies.get(SESSION_COOKIE))
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="auth.logout",
        object_type="user",
        object_id=auth.user.id,
    )
    db.commit()
    response = JSONResponse({"ok": True})
    clear_session_cookies(response)
    return response


@router.get("/me")
def me(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    workspace = db.get(Workspace, auth.user.workspace_id)
    return {
        "app_name": settings.app_name,
        "user": user_payload(auth.user),
        "workspace": {"id": str(workspace.id), "name": workspace.name, "currency": workspace.currency},
        "themes": THEMES,
        "notification_channels": {
            "smtp": settings.smtp_enabled,
            "ntfy": settings.ntfy_enabled,
            "external_heartbeat": bool(settings.external_heartbeat_url),
        },
    }


@router.patch("/preferences")
def update_preferences(
    payload: PreferenceRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    user = db.scalar(select(User).where(User.id == auth.user.id).with_for_update())
    if user.version != payload.version:
        raise HTTPException(
            status_code=409,
            detail={"message": "Your preferences changed on another device.", "current": user_payload(user)},
        )
    before = user_payload(user)
    if payload.theme is not None:
        if payload.theme not in THEMES:
            raise HTTPException(status_code=400, detail="Unknown theme")
        user.theme = payload.theme
    if payload.preferences is not None:
        allowed = {"density", "motion", "show_cents", "collapsed_sections", "default_month"}
        user.preferences = {key: value for key, value in payload.preferences.items() if key in allowed}
    user.version += 1
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_user_id=user.id,
        action="user.preferences.updated",
        object_type="user",
        object_id=user.id,
        before=before,
        after=user_payload(user),
    )
    db.commit()
    return {"user": user_payload(user)}


@router.get("/sessions")
def list_sessions(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(SessionRecord)
        .where(SessionRecord.user_id == auth.user.id)
        .order_by(SessionRecord.last_seen_at.desc())
    ).all()
    return {
        "sessions": [
            {
                "id": str(row.id),
                "created_at": row.created_at.isoformat(),
                "last_seen_at": row.last_seen_at.isoformat(),
                "expires_at": row.expires_at.isoformat(),
                "user_agent": row.user_agent,
                "ip_address": row.ip_address,
                "current": row.id == auth.session.id,
            }
            for row in rows
        ]
    }


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: uuid.UUID,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> Response:
    record = db.get(SessionRecord, session_id)
    if not record or record.user_id != auth.user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    is_current = record.id == auth.session.id
    db.delete(record)
    db.commit()
    response = JSONResponse({"ok": True, "signed_out": is_current})
    if is_current:
        clear_session_cookies(response)
    return response
