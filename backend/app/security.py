from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import SessionRecord, User
from .utils import utcnow

settings = get_settings()
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
fernet = Fernet(settings.app_encryption_key.encode())
SESSION_COOKIE = "mosaic_session"
CSRF_COOKIE = "mosaic_csrf"


@dataclass(slots=True)
class SessionTokens:
    session_token: str
    csrf_token: str
    record: SessionRecord


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def encrypt_secret(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt stored credential; verify APP_ENCRYPTION_KEY") from exc


def create_session(db: Session, user: User, request: Request) -> SessionTokens:
    raw_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    now = utcnow()
    record = SessionRecord(
        user_id=user.id,
        token_hash=hash_secret(raw_token),
        csrf_hash=hash_secret(csrf_token),
        expires_at=now + timedelta(days=settings.session_days),
        last_seen_at=now,
        user_agent=(request.headers.get("user-agent") or "")[:500],
        ip_address=(request.client.host if request.client else "")[:80],
    )
    db.add(record)
    db.flush()
    return SessionTokens(raw_token, csrf_token, record)


def set_session_cookies(response: Response, tokens: SessionTokens) -> None:
    max_age = settings.session_days * 86400
    response.set_cookie(
        SESSION_COOKIE,
        tokens.session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def revoke_session(db: Session, raw_token: str | None) -> None:
    if raw_token:
        db.execute(delete(SessionRecord).where(SessionRecord.token_hash == hash_secret(raw_token)))


def validate_csrf(request: Request, session: SessionRecord) -> None:
    sent = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not sent or not cookie or not hmac.compare_digest(sent, cookie):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing or invalid CSRF token")
    if not hmac.compare_digest(hash_secret(sent), session.csrf_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF session mismatch")


def purge_expired_sessions(db: Session) -> int:
    result = db.execute(delete(SessionRecord).where(SessionRecord.expires_at <= utcnow()))
    return result.rowcount or 0
