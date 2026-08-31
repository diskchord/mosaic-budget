from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Account, Workspace
from ..schemas import ManualAccountCreateRequest
from ..services.audit import write_audit
from ..services.budgets import serialize_account
from ..utils import parse_decimal
from .deps import AuthContext, require_admin_write


router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.post("")
def create_manual_account(
    payload: ManualAccountCreateRequest,
    auth: AuthContext = Depends(require_admin_write),
    db: Session = Depends(get_db),
) -> dict:
    workspace = db.scalar(
        select(Workspace)
        .where(Workspace.id == auth.user.workspace_id)
        .with_for_update()
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        starting_balance = parse_decimal(payload.starting_balance)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    account = Account(
        workspace_id=workspace.id,
        source_type="manual",
        source_conn_id="manual",
        source_account_id=f"manual-{uuid.uuid4()}",
        name=payload.name,
        currency=workspace.currency,
        balance=starting_balance,
        available_balance=starting_balance,
        is_budget=payload.is_budget,
        is_active=True,
        is_duplicate=False,
    )
    db.add(account)
    db.flush()
    serialized = serialize_account(account)
    write_audit(
        db,
        workspace_id=workspace.id,
        actor_user_id=auth.user.id,
        action="account.created",
        object_type="account",
        object_id=account.id,
        after=serialized,
    )
    db.commit()
    return {"account": serialized}
