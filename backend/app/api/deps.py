from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SessionRecord, User
from ..security import SESSION_COOKIE, hash_secret, validate_csrf
from ..utils import ensure_utc, utcnow


@dataclass(slots=True)
class AuthContext:
    user: User
    session: SessionRecord


def current_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    record = db.scalar(
        select(SessionRecord)
        .where(SessionRecord.token_hash == hash_secret(raw_token), SessionRecord.expires_at > utcnow())
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = db.get(User, record.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is disabled")
    if ensure_utc(record.last_seen_at) < utcnow() - timedelta(hours=1):
        record.last_seen_at = utcnow()
        db.commit()
    return AuthContext(user=user, session=record)


def current_user(auth: AuthContext = Depends(current_auth)) -> User:
    return auth.user


def require_admin(auth: AuthContext = Depends(current_auth)) -> AuthContext:
    if not auth.user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return auth


def require_write(request: Request, auth: AuthContext = Depends(current_auth)) -> AuthContext:
    validate_csrf(request, auth.session)
    return auth


def require_admin_write(request: Request, auth: AuthContext = Depends(require_admin)) -> AuthContext:
    validate_csrf(request, auth.session)
    return auth
