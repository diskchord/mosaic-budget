from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

MONEY_QUANT = Decimal("0.0001")
DISPLAY_QUANT = Decimal("0.01")


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Return an aware UTC datetime, including for SQLite's naive round trips."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def month_floor(value: date | datetime) -> date:
    if isinstance(value, datetime):
        value = value.date()
    return date(value.year, value.month, 1)


def next_month(value: date) -> date:
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def parse_month(value: str) -> date:
    try:
        parsed = date.fromisoformat(f"{value}-01" if len(value) == 7 else value)
    except ValueError as exc:
        raise ValueError("Month must be formatted YYYY-MM") from exc
    return month_floor(parsed)


def parse_decimal(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid decimal amount") from exc
    if not number.is_finite():
        raise ValueError("Amount must be finite")
    return number.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def money_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.quantize(MONEY_QUANT)
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return money_str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "hex") and value.__class__.__name__ == "UUID":
        return str(value)
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    return value


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def normalize_description(value: str) -> str:
    text = value.casefold().strip()
    text = re.sub(r"\b(pos|debit|purchase|card|visa|mastercard|checkcard|pending)\b", " ", text)
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sanitize_message(value: str, limit: int = 500) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value))
    return text.strip()[:limit]


def exponential_backoff(attempts: int, maximum: timedelta = timedelta(hours=6)) -> timedelta:
    seconds = min(30 * (2 ** max(0, attempts - 1)), int(maximum.total_seconds()))
    return timedelta(seconds=seconds)
