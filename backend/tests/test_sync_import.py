from __future__ import annotations

import copy
import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.models import (
    Account,
    Allocation,
    BudgetTransaction,
    Category,
    ImportBatch,
    NotificationIncident,
    Section,
    SimpleFinConnection,
    SourceTransaction,
    SourceTransactionVersion,
)
from app.security import encrypt_secret
from app.services import sync as sync_service
from app.utils import utcnow


def _reset_with_connection() -> SimpleFinConnection:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()
    db = SessionLocal()
    try:
        workspace_id = db.scalar(select(Section.workspace_id).limit(1))
        connection = SimpleFinConnection(
            workspace_id=workspace_id,
            name="Test Bridge",
            encrypted_access_url=encrypt_secret("https://user:password@example.test/simplefin"),
            access_url_fingerprint=hashlib.sha256(b"test-access-url").hexdigest(),
            enabled=True,
            sync_interval_minutes=180,
            schedule_minute=17,
            next_sync_at=utcnow(),
        )
        db.add(connection)
        db.commit()
        db.refresh(connection)
        db.expunge(connection)
        return connection
    finally:
        db.close()


def _payload(transactions: list[dict]) -> dict:
    observed = int(datetime(2026, 8, 27, 12, 0, tzinfo=UTC).timestamp())
    return {
        "connections": [
            {
                "conn_id": "institution-1",
                "name": "Example Credit Union",
                "org_id": "example",
                "org_url": "https://example.test",
                "sfin_url": "https://example.test/simplefin",
            }
        ],
        "accounts": [
            {
                "id": "checking-1",
                "conn_id": "institution-1",
                "name": "Joint Checking",
                "currency": "USD",
                "balance": "1234.56",
                "available-balance": "1200.00",
                "balance-date": observed,
                "transactions": transactions,
                "extra": {},
            }
        ],
        "errlist": [],
    }


def _transaction(source_id: str, *, pending: bool, posted_offset_days: int = 0) -> dict:
    base = int(datetime(2026, 8, 26, 16, 0, tzinfo=UTC).timestamp())
    return {
        "id": source_id,
        "posted": 0 if pending else base + posted_offset_days * 86400,
        "transacted_at": base,
        "pending": pending,
        "amount": "-84.27",
        "description": "HANNAFORD",
        "extra": {"memo": "test"},
    }


def test_identical_payload_is_idempotent_and_tombstone_survives(monkeypatch) -> None:
    connection = _reset_with_connection()
    payload = _payload([_transaction("source-1", pending=False)])
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: copy.deepcopy(payload))

    first = sync_service.perform_sync(connection.id)
    assert first["status"] == "success"
    assert first["new"] == 1

    db = SessionLocal()
    try:
        transaction = db.scalar(select(BudgetTransaction))
        transaction.deleted_at = utcnow()
        transaction.version += 1
        db.commit()
    finally:
        db.close()

    second = sync_service.perform_sync(connection.id)
    assert second["status"] == "success"
    assert second["new"] == 0
    assert second["changed"] == 0

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(BudgetTransaction.id))) == 1
        assert db.scalar(select(func.count(SourceTransaction.id))) == 1
        assert db.scalar(select(func.count(SourceTransactionVersion.id))) == 1
        assert db.scalar(select(func.count(ImportBatch.id))) == 2
        assert db.scalar(select(BudgetTransaction.deleted_at)) is not None
    finally:
        db.close()


def test_sync_preserves_custom_account_name_and_tracks_latest_provider_name(monkeypatch) -> None:
    connection = _reset_with_connection()
    payload = _payload([])
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: copy.deepcopy(payload))

    assert sync_service.perform_sync(connection.id)["status"] == "success"

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.simplefin_connection_id == connection.id))
        assert account is not None
        account.name = "Household Spending"
        account.version += 1
        db.commit()

    payload["accounts"][0]["name"] = "Provider Renamed Checking"
    assert sync_service.perform_sync(connection.id)["status"] == "success"

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.simplefin_connection_id == connection.id))
        assert account is not None
        assert account.name == "Household Spending"
        assert account.extra["_simplefin_name"] == "Provider Renamed Checking"


def test_posted_replacement_reuses_pending_budget_transaction_and_manual_split(monkeypatch) -> None:
    connection = _reset_with_connection()
    responses = [
        _payload([_transaction("pending-1", pending=True)]),
        _payload([_transaction("posted-1", pending=False, posted_offset_days=1)]),
    ]
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: copy.deepcopy(responses.pop(0)))

    assert sync_service.perform_sync(connection.id)["status"] == "success"

    db = SessionLocal()
    try:
        transaction = db.scalar(select(BudgetTransaction))
        groceries = db.scalar(select(Category).join(Section).where(Category.name == "Groceries"))
        transaction.allocations.append(
            Allocation(category_id=groceries.id, amount=Decimal("-84.27"), memo="Manual choice", sort_order=0)
        )
        transaction.manual_allocation_lock = True
        transaction.version += 1
        original_id = transaction.id
        db.commit()
    finally:
        db.close()

    assert sync_service.perform_sync(connection.id)["status"] == "success"

    db = SessionLocal()
    try:
        transactions = db.scalars(select(BudgetTransaction)).all()
        assert len(transactions) == 1
        assert transactions[0].id == original_id
        assert transactions[0].pending is False
        assert transactions[0].manual_allocation_lock is True
        allocation = db.scalar(select(Allocation))
        assert allocation.category_id == groceries.id
        assert Decimal(allocation.amount) == Decimal("-84.2700")
        sources = db.scalars(select(SourceTransaction).order_by(SourceTransaction.created_at)).all()
        assert len(sources) == 2
        pending_source = next(row for row in sources if row.source_transaction_id == "pending-1")
        posted_source = next(row for row in sources if row.source_transaction_id == "posted-1")
        assert pending_source.superseded_by_id == posted_source.id
    finally:
        db.close()


def test_ambiguous_pending_match_preserves_every_record_and_flags_review(monkeypatch) -> None:
    connection = _reset_with_connection()
    responses = [
        _payload([
            _transaction("pending-a", pending=True),
            _transaction("pending-b", pending=True),
        ]),
        _payload([_transaction("posted-new", pending=False, posted_offset_days=1)]),
    ]
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: copy.deepcopy(responses.pop(0)))

    assert sync_service.perform_sync(connection.id)["status"] == "success"
    assert sync_service.perform_sync(connection.id)["status"] == "success"

    db = SessionLocal()
    try:
        transactions = db.scalars(select(BudgetTransaction).order_by(BudgetTransaction.created_at)).all()
        assert len(transactions) == 3
        assert all(row.needs_review for row in transactions)
        assert sum(1 for row in transactions if row.pending) == 2
        assert db.scalar(select(func.count(SourceTransaction.id))) == 3
        incident = db.scalar(
            select(NotificationIncident).where(NotificationIncident.incident_key.like("pending-ambiguous:%"))
        )
        assert incident is not None
        assert incident.status == "open"
    finally:
        db.close()


def test_duplicate_account_imports_source_history_without_visible_counts_or_rules(monkeypatch) -> None:
    connection = _reset_with_connection()
    original = _transaction("duplicate-source", pending=False)
    changed = copy.deepcopy(original)
    changed["description"] = "HANNAFORD UPDATED"
    later = _transaction("normal-source", pending=False, posted_offset_days=1)
    responses = [
        _payload([]),
        _payload([original]),
        _payload([changed]),
        _payload([changed, later]),
    ]
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: copy.deepcopy(responses.pop(0)))
    rule_calls: list[str] = []
    monkeypatch.setattr(
        sync_service,
        "apply_rules_to_transaction",
        lambda _db, transaction: rule_calls.append(transaction.payee),
    )

    assert sync_service.perform_sync(connection.id)["status"] == "success"

    db = SessionLocal()
    try:
        account = db.scalar(select(Account).where(Account.simplefin_connection_id == connection.id))
        assert account is not None
        account.is_duplicate = True
        account.version += 1
        db.commit()
    finally:
        db.close()

    imported = sync_service.perform_sync(connection.id)
    updated = sync_service.perform_sync(connection.id)
    assert imported == {"status": "success", "new": 0, "changed": 0, "seen": 1}
    assert updated == {"status": "success", "new": 0, "changed": 0, "seen": 1}
    assert rule_calls == []

    db = SessionLocal()
    try:
        transaction = db.scalar(select(BudgetTransaction))
        assert transaction is not None
        assert transaction.payee == "HANNAFORD UPDATED"
        assert transaction.excluded is True
        assert transaction.suppressed_by_duplicate_account is True
        assert db.scalar(select(func.count(SourceTransaction.id))) == 1
        assert db.scalar(select(func.count(SourceTransactionVersion.id))) == 2
        assert db.scalar(select(func.count(ImportBatch.id))) == 3

        account = db.get(Account, transaction.account_id)
        account.is_duplicate = False
        account.version += 1
        transaction.excluded = False
        transaction.suppressed_by_duplicate_account = False
        transaction.version += 1
        db.commit()
    finally:
        db.close()

    resumed = sync_service.perform_sync(connection.id)
    assert resumed == {"status": "success", "new": 1, "changed": 0, "seen": 2}
    assert rule_calls == ["HANNAFORD"]

    db = SessionLocal()
    try:
        rows = db.scalars(select(BudgetTransaction).order_by(BudgetTransaction.created_at)).all()
        assert len(rows) == 2
        assert rows[1].excluded is False
        assert rows[1].suppressed_by_duplicate_account is False
        assert db.scalar(select(func.count(SourceTransaction.id))) == 2
    finally:
        db.close()
