from __future__ import annotations

import copy
import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.bootstrap import bootstrap
from app.db import Base, SessionLocal, engine
from app.main import app
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
from app.services.budgets import serialize_transaction
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


def test_noisy_ach_description_gets_a_non_destructive_display_payee(monkeypatch) -> None:
    connection = _reset_with_connection()
    raw_description = (
        "ACH Withdrawal PwP PHILO TV TYPE: Privacycom "
        "CO: PwP PHILO TV NAME: Alexander Peppe"
    )
    item = _transaction("philo-source", pending=False)
    item["description"] = raw_description
    item["extra"] = {"memo": "provider detail"}
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: _payload([copy.deepcopy(item)]))

    assert sync_service.perform_sync(connection.id)["status"] == "success"

    with SessionLocal() as db:
        transaction = db.scalar(select(BudgetTransaction))
        source_version = db.scalar(select(SourceTransactionVersion))
        serialized = serialize_transaction(transaction)
        assert serialized["display_payee"] == "PHILO TV"
        assert serialized["payee"] == raw_description
        assert serialized["imported_description"] == raw_description
        assert transaction.imported_extra == {"memo": "provider detail"}
        assert source_version.description == raw_description
        assert source_version.extra == {"memo": "provider detail"}


def test_unchanged_payee_patch_does_not_freeze_the_imported_description(monkeypatch) -> None:
    connection = _reset_with_connection()
    raw_description = (
        "ACH Withdrawal PwP PHILO TV TYPE: Privacycom "
        "CO: PwP PHILO TV NAME: Alexander Peppe"
    )
    item = _transaction("philo-patch", pending=False)
    item["description"] = raw_description
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: _payload([copy.deepcopy(item)]))
    assert sync_service.perform_sync(connection.id)["status"] == "success"

    with SessionLocal() as db:
        transaction = db.scalar(select(BudgetTransaction))
        transaction_id = transaction.id
        version = transaction.version
        assert transaction.manual_payee_lock is False

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
        )
        assert login.status_code == 200
        headers = {"X-CSRF-Token": client.cookies["mosaic_csrf"]}
        unchanged = client.patch(
            f"/api/transactions/{transaction_id}",
            headers=headers,
            json={"version": version, "payee": raw_description, "note": "Reviewed"},
        )
        assert unchanged.status_code == 200
        assert unchanged.json()["transaction"]["display_payee"] == "PHILO TV"
        with SessionLocal() as db:
            assert db.get(BudgetTransaction, transaction_id).manual_payee_lock is False

        customized = client.patch(
            f"/api/transactions/{transaction_id}",
            headers=headers,
            json={
                "version": unchanged.json()["transaction"]["version"],
                "payee": "Philo Family",
            },
        )
        assert customized.status_code == 200
        assert customized.json()["transaction"]["display_payee"] == "Philo Family"

    with SessionLocal() as db:
        transaction = db.get(BudgetTransaction, transaction_id)
        assert transaction.manual_payee_lock is True
        assert transaction.payee == "Philo Family"
        assert transaction.imported_description == raw_description


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


def test_posted_replacement_reconciles_after_pending_transaction_moves_cross_month(monkeypatch) -> None:
    connection = _reset_with_connection()
    responses = [
        _payload([_transaction("pending-moved", pending=True)]),
        _payload([_transaction("posted-moved", pending=False, posted_offset_days=1)]),
    ]
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: copy.deepcopy(responses.pop(0)))

    assert sync_service.perform_sync(connection.id)["status"] == "success"

    with SessionLocal() as db:
        transaction = db.scalar(select(BudgetTransaction))
        groceries = db.scalar(select(Category).join(Section).where(Category.name == "Groceries"))
        transaction.effective_date = date(2026, 9, 26)
        transaction.manual_date_lock = True
        transaction.allocations.append(
            Allocation(category_id=groceries.id, amount=Decimal("-84.27"), memo="Manual choice", sort_order=0)
        )
        transaction.manual_allocation_lock = True
        transaction.version += 1
        original_id = transaction.id
        groceries_id = groceries.id
        db.commit()

    assert sync_service.perform_sync(connection.id)["status"] == "success"

    with SessionLocal() as db:
        transactions = db.scalars(select(BudgetTransaction)).all()
        assert len(transactions) == 1
        transaction = transactions[0]
        assert transaction.id == original_id
        assert transaction.pending is False
        assert transaction.effective_date == date(2026, 9, 26)
        assert transaction.manual_date_lock is True
        assert transaction.manual_allocation_lock is True
        allocation = db.scalar(select(Allocation))
        assert allocation.category_id == groceries_id
        assert Decimal(allocation.amount) == Decimal("-84.2700")
        sources = db.scalars(select(SourceTransaction).order_by(SourceTransaction.created_at)).all()
        assert len(sources) == 2
        pending_source = next(row for row in sources if row.source_transaction_id == "pending-moved")
        posted_source = next(row for row in sources if row.source_transaction_id == "posted-moved")
        assert pending_source.superseded_by_id == posted_source.id


def test_pending_reconciliation_prefers_the_source_current_version_when_observation_times_tie(
    monkeypatch,
) -> None:
    connection = _reset_with_connection()
    older = _transaction("pending-tied", pending=True)
    older["transacted_at"] = int(datetime(2026, 7, 26, 16, 0, tzinfo=UTC).timestamp())
    current = _transaction("pending-tied", pending=True)
    posted = _transaction("posted-tied", pending=False)
    responses = [_payload([older]), _payload([current]), _payload([posted])]
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: copy.deepcopy(responses.pop(0)))

    assert sync_service.perform_sync(connection.id)["status"] == "success"
    assert sync_service.perform_sync(connection.id)["status"] == "success"

    with SessionLocal() as db:
        transaction = db.scalar(select(BudgetTransaction))
        source = db.scalar(select(SourceTransaction))
        versions = db.scalars(
            select(SourceTransactionVersion).where(SourceTransactionVersion.source_transaction_id == source.id)
        ).all()
        assert len(versions) == 2
        current_version = next(
            version for version in versions if version.import_batch_id == source.last_seen_batch_id
        )
        older_version = next(version for version in versions if version.id != current_version.id)
        tied_at = datetime(2026, 8, 27, 13, 0, tzinfo=UTC)
        older_version.observed_at = tied_at
        current_version.observed_at = tied_at
        # Make UUID chronology point at the older provider date. Reconciliation
        # must still use the version from SourceTransaction.last_seen_batch_id.
        older_version.id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        current_version.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        groceries = db.scalar(select(Category).join(Section).where(Category.name == "Groceries"))
        transaction.effective_date = date(2026, 9, 26)
        transaction.manual_date_lock = True
        transaction.allocations.append(
            Allocation(category_id=groceries.id, amount=Decimal("-84.27"), memo="Manual choice", sort_order=0)
        )
        transaction.manual_allocation_lock = True
        transaction.version += 1
        original_id = transaction.id
        db.commit()

    assert sync_service.perform_sync(connection.id)["status"] == "success"

    with SessionLocal() as db:
        transactions = db.scalars(select(BudgetTransaction)).all()
        assert len(transactions) == 1
        transaction = transactions[0]
        assert transaction.id == original_id
        assert transaction.pending is False
        assert transaction.effective_date == date(2026, 9, 26)
        assert transaction.manual_date_lock is True
        assert transaction.manual_allocation_lock is True


def test_sync_row_lock_refreshes_manual_date_state_before_source_updates(monkeypatch) -> None:
    connection = _reset_with_connection()
    payload = _payload([_transaction("stale-lock", pending=True)])
    monkeypatch.setattr(sync_service, "fetch_account_set", lambda *args, **kwargs: copy.deepcopy(payload))
    assert sync_service.perform_sync(connection.id)["status"] == "success"

    with SessionLocal() as db:
        stale = db.scalar(select(BudgetTransaction))
        assert stale.manual_date_lock is False
        original_version = stale.version
        db.execute(
            update(BudgetTransaction)
            .where(BudgetTransaction.id == stale.id)
            .values(
                effective_date=date(2026, 9, 26),
                manual_date_lock=True,
                version=original_version + 1,
            ),
            execution_options={"synchronize_session": False},
        )
        db.commit()
        assert stale.manual_date_lock is False

        refreshed = sync_service._locked_budget_transaction(db, stale.id)
        assert refreshed is stale
        assert refreshed.effective_date == date(2026, 9, 26)
        assert refreshed.manual_date_lock is True
        assert refreshed.version == original_version + 1


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
