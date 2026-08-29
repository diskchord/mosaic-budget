from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from starlette.requests import Request

from app.api.auth import login
from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.models import SessionRecord
from app.schemas import LoginRequest


def test_unknown_email_returns_invalid_credentials_without_creating_session() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()

    with SessionLocal() as db:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/auth/login",
                "headers": [],
                "client": ("testclient", 50000),
            }
        )
        with pytest.raises(HTTPException) as raised:
            login(
                LoginRequest(email="unknown@example.com", password="not-the-right-password"),
                request,
                db,
            )

        assert raised.value.status_code == 401
        assert raised.value.detail == "Email or password is incorrect"
        assert db.scalar(select(func.count(SessionRecord.id))) == 0
