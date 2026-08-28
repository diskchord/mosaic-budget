from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from ..db import SessionLocal
from ..models import AuditEvent
from ..utils import utcnow
from .deps import AuthContext, current_auth

router = APIRouter(tags=["events"])


@router.get("/api/events")
async def events(request: Request, auth: AuthContext = Depends(current_auth)) -> StreamingResponse:
    workspace_id = auth.user.workspace_id

    async def stream():
        last_seen = utcnow()
        tick = 0
        yield "retry: 3000\nevent: ready\ndata: {}\n\n"
        while not await request.is_disconnected():
            await asyncio.sleep(2)
            tick += 1
            db = SessionLocal()
            try:
                newest = db.scalar(
                    select(func.max(AuditEvent.created_at)).where(
                        AuditEvent.workspace_id == workspace_id,
                        AuditEvent.created_at > last_seen,
                    )
                )
            finally:
                db.close()
            if newest:
                last_seen = newest
                payload = json.dumps({"changed_at": newest.isoformat()})
                yield f"id: {newest.isoformat()}\nevent: change\ndata: {payload}\n\n"
            elif tick % 15 == 0:
                yield "event: tick\ndata: {}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
