from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.services import assignment_undo


def test_assignment_undo_token_expires_at_five_minute_boundary(monkeypatch) -> None:
    issued_at = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    category_id = uuid.uuid4()
    transaction_id = uuid.uuid4()
    monkeypatch.setattr(assignment_undo, "utcnow", lambda: issued_at)
    token = assignment_undo.create_assignment_undo_token(
        workspace_id,
        user_id,
        session_id,
        category_id,
        "2026-08",
        {
            transaction_id: assignment_undo.AssignmentUndoState(
                effective_date=date(2026, 7, 31),
                manual_date_lock=False,
                manual_allocation_lock=False,
                needs_review=True,
                assigned_version=2,
            )
        },
    )

    monkeypatch.setattr(assignment_undo, "utcnow", lambda: issued_at + timedelta(seconds=299))
    claims = assignment_undo.read_assignment_undo_token(
        token,
        workspace_id,
        user_id,
        session_id,
    )
    assert claims.category_id == category_id
    assert claims.states[transaction_id].effective_date == date(2026, 7, 31)

    monkeypatch.setattr(assignment_undo, "utcnow", lambda: issued_at + timedelta(seconds=300))
    with pytest.raises(assignment_undo.AssignmentUndoTokenError):
        assignment_undo.read_assignment_undo_token(
            token,
            workspace_id,
            user_id,
            session_id,
        )
