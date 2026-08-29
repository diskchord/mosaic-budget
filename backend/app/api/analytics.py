from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.analytics import get_analytics
from ..utils import month_floor, parse_month
from .deps import AuthContext, current_auth

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

DEFAULT_MONTH_COUNT = 12
MAX_MONTH_COUNT = 120
LAST_SUPPORTED_END_MONTH = date(9999, 11, 1)


def _shift_month(month: date, offset: int) -> date:
    absolute_month = month.year * 12 + month.month - 1 + offset
    return date(absolute_month // 12, absolute_month % 12 + 1, 1)


def _parse_optional_month(value: str | None, fallback: date) -> date:
    if value is None:
        return fallback
    try:
        return parse_month(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def analytics(
    start_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    end_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_db),
) -> dict:
    default_end = month_floor(date.today())
    parsed_end = _parse_optional_month(end_month, default_end)
    if parsed_end > LAST_SUPPORTED_END_MONTH:
        raise HTTPException(status_code=400, detail="End month must be before December 9999")
    try:
        default_start = _shift_month(parsed_end, -(DEFAULT_MONTH_COUNT - 1))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="The default Analytics range falls outside the supported calendar",
        ) from exc
    parsed_start = _parse_optional_month(start_month, default_start)
    if parsed_start > parsed_end:
        raise HTTPException(status_code=400, detail="Start month must not be after end month")
    month_count = (parsed_end.year - parsed_start.year) * 12 + parsed_end.month - parsed_start.month + 1
    if month_count > MAX_MONTH_COUNT:
        raise HTTPException(status_code=400, detail=f"Analytics ranges are limited to {MAX_MONTH_COUNT} months")

    return get_analytics(
        db,
        auth.user.workspace_id,
        parsed_start,
        parsed_end,
    )
