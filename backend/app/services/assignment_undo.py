from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping

from ..config import get_settings
from ..utils import utcnow

UNDO_TOKEN_TTL = timedelta(minutes=5)
_TOKEN_VERSION = 1
_MAX_TRANSACTIONS = 200
_SIGNING_CONTEXT = b"mosaic-budget\0batch-assignment-undo\0v1\0"


class AssignmentUndoTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AssignmentUndoState:
    effective_date: date
    manual_date_lock: bool
    manual_allocation_lock: bool
    needs_review: bool
    assigned_version: int


@dataclass(frozen=True, slots=True)
class AssignmentUndo:
    category_id: uuid.UUID
    target_month: str | None
    states: dict[uuid.UUID, AssignmentUndoState]


def _encode_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_payload(value: str) -> dict:
    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssignmentUndoTokenError("Invalid assignment Undo token") from exc
    if not isinstance(payload, dict):
        raise AssignmentUndoTokenError("Invalid assignment Undo token")
    return payload


def create_assignment_undo_token(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    category_id: uuid.UUID,
    target_month: str | None,
    states: Mapping[uuid.UUID, AssignmentUndoState],
) -> str:
    now = utcnow()
    payload = {
        "v": _TOKEN_VERSION,
        "purpose": "batch-assignment-undo",
        "issued_at": int(now.timestamp()),
        "expires_at": int((now + UNDO_TOKEN_TTL).timestamp()),
        "workspace_id": str(workspace_id),
        "user_id": str(user_id),
        "session_id": str(session_id),
        "category_id": str(category_id),
        "target_month": target_month,
        "transactions": [
            {
                "id": str(transaction_id),
                "assigned_version": state.assigned_version,
                "effective_date": state.effective_date.isoformat(),
                "manual_date_lock": state.manual_date_lock,
                "manual_allocation_lock": state.manual_allocation_lock,
                "needs_review": state.needs_review,
            }
            for transaction_id, state in sorted(states.items(), key=lambda item: str(item[0]))
        ],
    }
    encoded = _encode_payload(payload)
    signature = hmac.new(
        get_settings().app_secret_key.encode(),
        _SIGNING_CONTEXT + encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"v1.{encoded}.{signature}"


def read_assignment_undo_token(
    token: str,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> AssignmentUndo:
    try:
        version, encoded, signature = token.split(".")
    except ValueError as exc:
        raise AssignmentUndoTokenError("Invalid assignment Undo token") from exc
    if version != "v1" or not encoded or len(signature) != hashlib.sha256().digest_size * 2:
        raise AssignmentUndoTokenError("Invalid assignment Undo token")
    try:
        encoded_bytes = encoded.encode("ascii")
        signature.encode("ascii")
    except UnicodeEncodeError as exc:
        raise AssignmentUndoTokenError("Invalid assignment Undo token") from exc
    expected_signature = hmac.new(
        get_settings().app_secret_key.encode(),
        _SIGNING_CONTEXT + encoded_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise AssignmentUndoTokenError("Invalid assignment Undo token")

    payload = _decode_payload(encoded)
    if (
        payload.get("v") != _TOKEN_VERSION
        or payload.get("purpose") != "batch-assignment-undo"
        or payload.get("workspace_id") != str(workspace_id)
        or payload.get("user_id") != str(user_id)
        or payload.get("session_id") != str(session_id)
    ):
        raise AssignmentUndoTokenError("Invalid assignment Undo token")
    issued_at = payload.get("issued_at")
    expires_at = payload.get("expires_at")
    now = int(utcnow().timestamp())
    if (
        type(issued_at) is not int
        or type(expires_at) is not int
        or issued_at > now + 30
        or expires_at - issued_at != int(UNDO_TOKEN_TTL.total_seconds())
        or expires_at <= now
    ):
        raise AssignmentUndoTokenError("Expired assignment Undo token")
    try:
        category_id = uuid.UUID(payload["category_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AssignmentUndoTokenError("Invalid assignment Undo token") from exc
    target_month = payload.get("target_month")
    if target_month is not None and (
        not isinstance(target_month, str)
        or len(target_month) != 7
        or target_month[4] != "-"
    ):
        raise AssignmentUndoTokenError("Invalid assignment Undo token")
    raw_transactions = payload.get("transactions")
    if not isinstance(raw_transactions, list) or not 1 <= len(raw_transactions) <= _MAX_TRANSACTIONS:
        raise AssignmentUndoTokenError("Invalid assignment Undo token")

    states: dict[uuid.UUID, AssignmentUndoState] = {}
    try:
        for raw in raw_transactions:
            if not isinstance(raw, dict):
                raise ValueError
            transaction_id = uuid.UUID(raw["id"])
            assigned_version = raw["assigned_version"]
            effective_date = date.fromisoformat(raw["effective_date"])
            boolean_values = (
                raw["manual_date_lock"],
                raw["manual_allocation_lock"],
                raw["needs_review"],
            )
            if type(assigned_version) is not int or assigned_version < 1:
                raise ValueError
            if any(type(value) is not bool for value in boolean_values):
                raise ValueError
            if transaction_id in states:
                raise ValueError
            states[transaction_id] = AssignmentUndoState(
                effective_date=effective_date,
                manual_date_lock=boolean_values[0],
                manual_allocation_lock=boolean_values[1],
                needs_review=boolean_values[2],
                assigned_version=assigned_version,
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise AssignmentUndoTokenError("Invalid assignment Undo token") from exc
    return AssignmentUndo(category_id=category_id, target_month=target_month, states=states)
