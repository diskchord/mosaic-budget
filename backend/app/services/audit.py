from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEvent
from ..utils import jsonable


def write_audit(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    action: str,
    object_type: str,
    object_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before=jsonable(before) if before is not None else None,
        after=jsonable(after) if after is not None else None,
        detail=jsonable(detail or {}),
    )
    db.add(event)
    db.flush()
    return event
