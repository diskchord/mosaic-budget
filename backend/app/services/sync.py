from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import SessionLocal
from ..models import (
    Account,
    Allocation,
    BudgetTransaction,
    ImportBatch,
    InstitutionConnection,
    NotificationIncident,
    SimpleFinConnection,
    SimpleFinRequestLog,
    SourceTransaction,
    SourceTransactionVersion,
    SyncRun,
    Workspace,
)
from ..security import decrypt_secret
from ..utils import ensure_utc, normalize_description, parse_decimal, sanitize_message, stable_hash, utcnow
from .audit import write_audit
from .balance_alerts import evaluate_balance_alerts
from .notifications import open_incident, resolve_incident
from .rules import apply_rules_to_transaction
from .simplefin import SimpleFinError, fetch_account_set

logger = logging.getLogger(__name__)
settings = get_settings()
local_zone = ZoneInfo(settings.app_timezone)
PENDING_CANDIDATE_LIMIT = 200


def next_scheduled_at(now: datetime, interval_minutes: int, minute_offset: int) -> datetime:
    now = now.astimezone(UTC)
    midnight = datetime.combine(now.date(), time(0, minute_offset % 60), tzinfo=UTC)
    interval = timedelta(minutes=interval_minutes)
    candidate = midnight
    while candidate <= now:
        candidate += interval
    return candidate


def _epoch_to_datetime(value: object) -> datetime | None:
    try:
        epoch = int(value or 0)
    except (TypeError, ValueError):
        return None
    if epoch <= 0:
        return None
    try:
        return datetime.fromtimestamp(epoch, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _effective_date(posted: datetime | None, transacted: datetime | None) -> date:
    chosen = transacted or posted or utcnow()
    return chosen.astimezone(local_zone).date()


def _adjust_allocations_for_amount_change(transaction: BudgetTransaction, old_amount: Decimal) -> None:
    if not transaction.allocations:
        return
    delta = Decimal(transaction.amount) - old_amount
    if len(transaction.allocations) == 1:
        transaction.allocations[0].amount = transaction.amount
        return
    transaction.allocations[-1].amount = Decimal(transaction.allocations[-1].amount) + delta
    transaction.needs_review = True


def _source_version_timestamp(version: SourceTransactionVersion) -> datetime | None:
    return ensure_utc(version.transacted_at) or ensure_utc(version.posted_at)


def _selected_source_versions(
    db: Session,
    transactions: list[BudgetTransaction],
) -> dict[uuid.UUID, list[SourceTransactionVersion]]:
    sources = [source for transaction in transactions for source in transaction.source_records]
    source_ids = {source.id for source in sources}
    if not source_ids:
        return {}

    selected: dict[uuid.UUID, list[SourceTransactionVersion]] = {}
    current_versions = db.scalars(
        select(SourceTransactionVersion)
        .join(SourceTransaction)
        .where(
            SourceTransaction.id.in_(source_ids),
            SourceTransactionVersion.import_batch_id == SourceTransaction.last_seen_batch_id,
        )
    ).all()
    for version in current_versions:
        selected.setdefault(version.source_transaction_id, []).append(version)

    fallback_source_ids = source_ids - set(selected)
    if fallback_source_ids:
        latest_observed = (
            select(
                SourceTransactionVersion.source_transaction_id.label("source_transaction_id"),
                func.max(SourceTransactionVersion.observed_at).label("latest_observed_at"),
            )
            .where(SourceTransactionVersion.source_transaction_id.in_(fallback_source_ids))
            .group_by(SourceTransactionVersion.source_transaction_id)
            .subquery()
        )
        fallback_versions = db.scalars(
            select(SourceTransactionVersion).join(
                latest_observed,
                and_(
                    SourceTransactionVersion.source_transaction_id
                    == latest_observed.c.source_transaction_id,
                    SourceTransactionVersion.observed_at == latest_observed.c.latest_observed_at,
                ),
            )
        ).all()
        for version in fallback_versions:
            selected.setdefault(version.source_transaction_id, []).append(version)
    return selected


def _pending_source_date(
    transaction: BudgetTransaction,
    selected_versions: dict[uuid.UUID, list[SourceTransactionVersion]],
) -> tuple[date | None, bool]:
    """Return the current immutable source date and whether source chronology is decisive.

    A version observed in the source's last-seen batch is the provider state that
    produced that source observation. If an identical payload was observed later,
    there is no version for the last-seen batch, so fall back to the uniquely latest
    observed version. Timestamp ties with different source dates are deliberately
    ambiguous instead of treating random UUID order as chronology.
    """

    source_dates: list[date] = []
    decisive = False
    for source in transaction.source_records:
        versions = selected_versions.get(source.id, [])
        timestamps = [_source_version_timestamp(version) for version in versions]
        dated = {timestamp.astimezone(local_zone).date() for timestamp in timestamps if timestamp is not None}
        if len(dated) > 1 or (dated and len(dated) != len(versions)):
            return None, True
        if dated:
            decisive = True
            source_dates.append(next(iter(dated)))

    if len(set(source_dates)) > 1:
        return None, True
    return (source_dates[0] if source_dates else None), decisive


def _locked_budget_transaction(
    db: Session,
    transaction_id: uuid.UUID,
    *,
    include_source_records: bool = False,
) -> BudgetTransaction | None:
    options = [
        selectinload(BudgetTransaction.allocations),
        selectinload(BudgetTransaction.account),
    ]
    if include_source_records:
        options.append(selectinload(BudgetTransaction.source_records))
    return db.scalar(
        select(BudgetTransaction)
        .where(BudgetTransaction.id == transaction_id)
        .options(*options)
        .execution_options(populate_existing=True)
        .with_for_update()
    )


def _matches_pending_replacement(
    transaction: BudgetTransaction,
    *,
    account_id: uuid.UUID,
    amount: Decimal,
    start: date,
    end: date,
    normalized_description: str,
    selected_versions: dict[uuid.UUID, list[SourceTransactionVersion]],
) -> bool:
    if (
        transaction.account_id != account_id
        or not transaction.pending
        or Decimal(transaction.amount) != amount
        or transaction.deleted_at is not None
        or normalize_description(transaction.imported_description or transaction.payee)
        != normalized_description
        or any(source.superseded_by_id for source in transaction.source_records)
    ):
        return False
    source_date, decisive = _pending_source_date(transaction, selected_versions)
    candidate_date = source_date if decisive else transaction.effective_date
    return candidate_date is not None and start <= candidate_date <= end


def _pending_candidates(
    db: Session,
    *,
    account: Account,
    amount: Decimal,
    effective_date: date,
    description: str,
) -> list[BudgetTransaction]:
    start = effective_date - timedelta(days=7)
    end = effective_date + timedelta(days=7)
    utc_start = datetime.combine(start, time.min, tzinfo=local_zone).astimezone(UTC)
    utc_end = datetime.combine(end + timedelta(days=1), time.min, tzinfo=local_zone).astimezone(UTC)
    source_date_in_window = or_(
        and_(
            SourceTransactionVersion.transacted_at.is_not(None),
            SourceTransactionVersion.transacted_at >= utc_start,
            SourceTransactionVersion.transacted_at < utc_end,
        ),
        and_(
            SourceTransactionVersion.transacted_at.is_(None),
            SourceTransactionVersion.posted_at.is_not(None),
            SourceTransactionVersion.posted_at >= utc_start,
            SourceTransactionVersion.posted_at < utc_end,
        ),
    )
    source_candidate_ids = (
        select(SourceTransaction.budget_transaction_id)
        .join(SourceTransactionVersion)
        .where(
            SourceTransaction.account_id == account.id,
            SourceTransaction.superseded_by_id.is_(None),
            source_date_in_window,
        )
    )
    rows = db.scalars(
        select(BudgetTransaction)
        .where(
            BudgetTransaction.account_id == account.id,
            BudgetTransaction.pending.is_(True),
            BudgetTransaction.amount == amount,
            BudgetTransaction.deleted_at.is_(None),
            or_(
                BudgetTransaction.id.in_(source_candidate_ids),
                and_(
                    BudgetTransaction.effective_date >= start,
                    BudgetTransaction.effective_date <= end,
                ),
            ),
        )
        .options(selectinload(BudgetTransaction.source_records))
        .order_by(BudgetTransaction.created_at.desc(), BudgetTransaction.id)
        .limit(PENDING_CANDIDATE_LIMIT + 1)
    ).all()
    if len(rows) > PENDING_CANDIDATE_LIMIT:
        logger.warning(
            "Pending reconciliation candidate limit reached for account %s; preserving records for review",
            account.id,
        )
        return []

    normalized = normalize_description(description)
    selected_versions = _selected_source_versions(db, rows)
    candidate_ids: list[uuid.UUID] = []
    for row in rows:
        if _matches_pending_replacement(
            row,
            account_id=account.id,
            amount=amount,
            start=start,
            end=end,
            normalized_description=normalized,
            selected_versions=selected_versions,
        ):
            candidate_ids.append(row.id)

    locked_rows: list[BudgetTransaction] = []
    for transaction_id in sorted(candidate_ids, key=str):
        row = _locked_budget_transaction(db, transaction_id, include_source_records=True)
        if row is not None:
            locked_rows.append(row)
    locked_versions = _selected_source_versions(db, locked_rows)
    return [
        row
        for row in locked_rows
        if _matches_pending_replacement(
            row,
            account_id=account.id,
            amount=amount,
            start=start,
            end=end,
            normalized_description=normalized,
            selected_versions=locked_versions,
        )
    ]


def _update_budget_transaction_from_source(
    transaction: BudgetTransaction,
    *,
    amount: Decimal,
    description: str,
    extra: dict,
    effective_date: date,
    pending: bool,
) -> bool:
    changed = False
    old_amount = Decimal(transaction.amount)
    if old_amount != amount:
        transaction.amount = amount
        _adjust_allocations_for_amount_change(transaction, old_amount)
        changed = True
    if transaction.imported_description != description:
        transaction.imported_description = description
        changed = True
    if transaction.imported_extra != extra:
        transaction.imported_extra = extra
        changed = True
    if not transaction.manual_payee_lock and transaction.payee != description:
        transaction.payee = description
        changed = True
    if not transaction.manual_date_lock and transaction.effective_date != effective_date:
        transaction.effective_date = effective_date
        changed = True
    if transaction.pending != pending:
        transaction.pending = pending
        changed = True
    if not pending and not transaction.cleared:
        transaction.cleared = True
        changed = True
    if changed:
        transaction.version += 1
    return changed


def _upsert_provider_connections(db: Session, connection: SimpleFinConnection, payload: dict) -> None:
    for item in payload.get("connections", []):
        source_id = str(item.get("conn_id", "")).strip()
        if not source_id:
            continue
        row = db.scalar(
            select(InstitutionConnection).where(
                InstitutionConnection.simplefin_connection_id == connection.id,
                InstitutionConnection.source_conn_id == source_id,
            )
        )
        values = {
            "name": sanitize_message(item.get("name", "Financial institution"), 255),
            "org_id": sanitize_message(item.get("org_id", ""), 255),
            "org_url": sanitize_message(item.get("org_url", ""), 1000),
            "sfin_url": sanitize_message(item.get("sfin_url", ""), 1000),
        }
        if row:
            for key, value in values.items():
                setattr(row, key, value)
        else:
            db.add(
                InstitutionConnection(
                    simplefin_connection_id=connection.id,
                    source_conn_id=source_id,
                    **values,
                )
            )


def _upsert_account(db: Session, connection: SimpleFinConnection, item: dict) -> Account:
    source_account_id = str(item.get("id", "")).strip()
    source_conn_id = str(item.get("conn_id", "")).strip()
    if not source_account_id or not source_conn_id:
        raise ValueError("SimpleFIN account lacks id or conn_id")
    account = db.scalar(
        select(Account).where(
            Account.simplefin_connection_id == connection.id,
            Account.source_conn_id == source_conn_id,
            Account.source_account_id == source_account_id,
        ).with_for_update()
    )
    balance = parse_decimal(item.get("balance", "0"))
    available = parse_decimal(item.get("available-balance", item.get("balance", "0")))
    balance_date = _epoch_to_datetime(item.get("balance-date"))
    imported_name = sanitize_message(item.get("name", "Account"), 255)
    imported_extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    # Keep the latest provider name for diagnostics without overwriting a name a
    # user may have deliberately customized in Mosaic.
    imported_extra = {**imported_extra, "_simplefin_name": imported_name}
    values = {
        "currency": sanitize_message(item.get("currency", "USD"), 255),
        "balance": balance,
        "available_balance": available,
        "balance_date": balance_date,
        "extra": imported_extra,
    }
    if account:
        changed = False
        for key, value in values.items():
            if getattr(account, key) != value:
                setattr(account, key, value)
                changed = True
        if changed:
            account.version += 1
        return account
    account = Account(
        workspace_id=connection.workspace_id,
        simplefin_connection_id=connection.id,
        source_type="simplefin",
        source_conn_id=source_conn_id,
        source_account_id=source_account_id,
        name=imported_name,
        is_active=True,
        **values,
    )
    db.add(account)
    db.flush()
    return account


def _import_transaction(
    db: Session,
    *,
    account: Account,
    batch: ImportBatch,
    raw: dict,
) -> tuple[bool, bool]:
    source_id = str(raw.get("id", "")).strip()
    description = sanitize_message(raw.get("description", "Transaction"), 10000)
    if not source_id:
        raise ValueError("SimpleFIN transaction is missing an id")
    amount = parse_decimal(raw.get("amount"))
    pending = bool(raw.get("pending", False))
    posted = _epoch_to_datetime(raw.get("posted"))
    transacted = _epoch_to_datetime(raw.get("transacted_at"))
    effective = _effective_date(posted, transacted)
    extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
    version_payload = {
        "posted": int(raw.get("posted") or 0),
        "transacted_at": int(raw.get("transacted_at") or 0),
        "pending": pending,
        "amount": str(raw.get("amount")),
        "description": description,
        "extra": extra,
    }
    content_hash = stable_hash(version_payload)

    source = db.scalar(
        select(SourceTransaction)
        .where(SourceTransaction.account_id == account.id, SourceTransaction.source_transaction_id == source_id)
        .options(selectinload(SourceTransaction.versions))
    )
    if source:
        source.last_seen_batch_id = batch.id
        if any(version.content_hash == content_hash for version in source.versions):
            return False, False
        transaction = _locked_budget_transaction(db, source.budget_transaction_id)
        if transaction is None:
            raise ValueError("SimpleFIN source refers to a missing budget transaction")
        changed = _update_budget_transaction_from_source(
            transaction,
            amount=amount,
            description=description,
            extra=extra,
            effective_date=effective,
            pending=pending,
        )
        version = SourceTransactionVersion(
            source_transaction_id=source.id,
            import_batch_id=batch.id,
            content_hash=content_hash,
            posted_at=posted,
            transacted_at=transacted,
            pending=pending,
            amount=amount,
            description=description,
            extra=extra,
        )
        db.add(version)
        if changed and not account.is_duplicate and not transaction.manual_allocation_lock:
            apply_rules_to_transaction(db, transaction)
        return False, True

    transaction: BudgetTransaction | None = None
    ambiguous_pending = False
    if not pending:
        candidates = _pending_candidates(
            db,
            account=account,
            amount=amount,
            effective_date=effective,
            description=description,
        )
        if len(candidates) == 1:
            transaction = candidates[0]
        elif len(candidates) > 1:
            ambiguous_pending = True
            for candidate in candidates:
                if not candidate.needs_review:
                    candidate.needs_review = True
                    candidate.version += 1
            if not account.is_duplicate:
                open_incident(
                    db,
                    workspace_id=account.workspace_id,
                    incident_key=f"pending-ambiguous:{account.id}:{source_id}",
                    severity="warning",
                    title="A pending transaction could not be reconciled automatically",
                    message="More than one pending transaction matched a newly posted transaction. Open the review queue.",
                )

    if transaction is None:
        transaction = BudgetTransaction(
            workspace_id=account.workspace_id,
            account_id=account.id,
            source_kind="simplefin",
            effective_date=effective,
            amount=amount,
            payee=description,
            imported_description=description,
            imported_extra=extra,
            pending=pending,
            cleared=not pending,
            excluded=account.is_duplicate,
            suppressed_by_duplicate_account=account.is_duplicate,
            needs_review=ambiguous_pending,
        )
        db.add(transaction)
        db.flush()
    else:
        _update_budget_transaction_from_source(
            transaction,
            amount=amount,
            description=description,
            extra=extra,
            effective_date=effective,
            pending=False,
        )

    prior_sources = list(transaction.source_records) if not pending else []
    source = SourceTransaction(
        account_id=account.id,
        source_transaction_id=source_id,
        budget_transaction_id=transaction.id,
        first_seen_batch_id=batch.id,
        last_seen_batch_id=batch.id,
    )
    db.add(source)
    db.flush()
    if not pending:
        for old_source in prior_sources:
            if old_source.id != source.id and old_source.superseded_by_id is None:
                old_source.superseded_by_id = source.id

    db.add(
        SourceTransactionVersion(
            source_transaction_id=source.id,
            import_batch_id=batch.id,
            content_hash=content_hash,
            posted_at=posted,
            transacted_at=transacted,
            pending=pending,
            amount=amount,
            description=description,
            extra=extra,
        )
    )
    if not account.is_duplicate and not transaction.manual_allocation_lock:
        apply_rules_to_transaction(db, transaction)
    return True, False


def _handle_structured_errors(db: Session, connection: SimpleFinConnection, errors: list[dict]) -> int:
    active_keys: set[str] = set()
    for error in errors:
        code = sanitize_message(error.get("code", "gen."), 80) or "gen."
        entity = sanitize_message(error.get("account_id") or error.get("conn_id") or "general", 255)
        key = f"simplefin-structured:{connection.id}:{code}:{entity}"
        active_keys.add(key)
        open_incident(
            db,
            workspace_id=connection.workspace_id,
            incident_key=key,
            severity="warning" if code not in {"gen.auth", "con.auth"} else "critical",
            title="SimpleFIN reported an account problem",
            message=sanitize_message(error.get("msg", "SimpleFIN reported an unspecified error."), 1000),
        )

    open_rows = db.scalars(
        select(NotificationIncident).where(
            NotificationIncident.workspace_id == connection.workspace_id,
            NotificationIncident.status == "open",
            NotificationIncident.incident_key.like(f"simplefin-structured:{connection.id}:%"),
        )
    ).all()
    for row in open_rows:
        if row.incident_key not in active_keys:
            resolve_incident(db, workspace_id=connection.workspace_id, incident_key=row.incident_key)
    return len(errors)


def _quota_remaining(db: Session, connection_id: uuid.UUID) -> int:
    count = db.scalar(
        select(func.count(SimpleFinRequestLog.id)).where(
            SimpleFinRequestLog.simplefin_connection_id == connection_id,
            SimpleFinRequestLog.requested_at >= utcnow() - timedelta(hours=24),
        )
    ) or 0
    return max(0, settings.simplefin_max_requests_24h - int(count))


def perform_sync(connection_id: uuid.UUID) -> dict[str, int | str]:
    db = SessionLocal()
    locked = False
    run_id: uuid.UUID | None = None
    try:
        if db.bind and db.bind.dialect.name == "postgresql":
            locked = bool(
                db.scalar(text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": f"simplefin:{connection_id}"})
            )
            if not locked:
                return {"status": "already-running", "new": 0, "changed": 0}
        connection = db.get(SimpleFinConnection, connection_id)
        if not connection or not connection.enabled:
            return {"status": "disabled", "new": 0, "changed": 0}

        now = utcnow()
        if _quota_remaining(db, connection.id) <= 0:
            connection.next_sync_at = now + timedelta(hours=2)
            connection.last_error_code = "sync.local_quota"
            connection.last_error_message = "Local safety quota reached; synchronization was deferred."
            db.commit()
            return {"status": "deferred-quota", "new": 0, "changed": 0}

        deep = connection.last_deep_sync_at is None or ensure_utc(connection.last_deep_sync_at) < now - timedelta(hours=24)
        days = settings.simplefin_deep_days if deep else settings.simplefin_routine_days
        window_start = now - timedelta(days=days)
        window_end = now + timedelta(days=1)
        run = SyncRun(
            simplefin_connection_id=connection.id,
            mode="deep" if deep else "routine",
            window_start=window_start,
            window_end=window_end,
            status="running",
        )
        db.add(run)
        connection.last_attempt_at = now
        db.flush()
        run_id = run.id
        db.commit()

        if not connection.encrypted_access_url:
            raise SimpleFinError("The SimpleFIN credential has been removed.", code="sync.disconnected")
        access_url = decrypt_secret(connection.encrypted_access_url)
        request_log = SimpleFinRequestLog(simplefin_connection_id=connection.id, endpoint="accounts")
        db.add(request_log)
        db.commit()
        try:
            payload = fetch_account_set(
                access_url,
                start_epoch=int(window_start.timestamp()),
                end_epoch=int(window_end.timestamp()),
            )
            request_log = db.get(SimpleFinRequestLog, request_log.id)
            request_log.status_code = 200
            db.commit()
        except SimpleFinError as exc:
            request_log = db.get(SimpleFinRequestLog, request_log.id)
            request_log.status_code = exc.status_code
            db.commit()
            raise

        run = db.get(SyncRun, run_id)
        connection = db.get(SimpleFinConnection, connection_id)
        db.scalar(
            select(Workspace.id)
            .where(Workspace.id == connection.workspace_id)
            .with_for_update()
        )
        batch = ImportBatch(
            simplefin_connection_id=connection.id,
            sync_run_id=run.id,
            payload_hash=stable_hash(payload),
            payload=payload,
        )
        db.add(batch)
        db.flush()
        _upsert_provider_connections(db, connection, payload)

        new_count = 0
        changed_count = 0
        seen_count = 0
        synced_account_ids: set[uuid.UUID] = set()
        for account_data in payload.get("accounts", []):
            if not isinstance(account_data, dict):
                continue
            account = _upsert_account(db, connection, account_data)
            synced_account_ids.add(account.id)
            for raw_transaction in account_data.get("transactions", []) or []:
                if not isinstance(raw_transaction, dict):
                    continue
                seen_count += 1
                is_new, is_changed = _import_transaction(
                    db,
                    account=account,
                    batch=batch,
                    raw=raw_transaction,
                )
                if not account.is_duplicate:
                    new_count += int(is_new)
                    changed_count += int(is_changed)

        structured_errors = [item for item in payload.get("errlist", []) if isinstance(item, dict)]
        error_count = _handle_structured_errors(db, connection, structured_errors)
        run.accounts_seen = len(payload.get("accounts", []))
        run.transactions_seen = seen_count
        run.transactions_new = new_count
        run.transactions_changed = changed_count
        run.errors_seen = error_count
        run.status = "partial" if error_count else "success"
        run.finished_at = utcnow()
        connection.last_success_at = run.finished_at
        if deep:
            connection.last_deep_sync_at = run.finished_at
        connection.consecutive_failures = 0
        connection.last_error_code = ""
        connection.last_error_message = ""
        connection.next_sync_at = next_scheduled_at(
            run.finished_at,
            connection.sync_interval_minutes,
            connection.schedule_minute,
        )
        connection.version += 1
        evaluate_balance_alerts(
            db,
            workspace_id=connection.workspace_id,
            account_ids=synced_account_ids,
        )
        resolve_incident(db, workspace_id=connection.workspace_id, incident_key=f"simplefin-sync:{connection.id}")
        write_audit(
            db,
            workspace_id=connection.workspace_id,
            action="sync.completed",
            object_type="simplefin_connection",
            object_id=connection.id,
            detail={
                "accounts": run.accounts_seen,
                "transactions_seen": seen_count,
                "new": new_count,
                "changed": changed_count,
                "structured_errors": error_count,
            },
        )
        db.commit()
        return {
            "status": run.status,
            "new": new_count,
            "changed": changed_count,
            "seen": seen_count,
        }
    except Exception as exc:
        db.rollback()
        connection = db.get(SimpleFinConnection, connection_id)
        run = db.get(SyncRun, run_id) if run_id else None
        code = exc.code if isinstance(exc, SimpleFinError) else "sync.internal"
        message = sanitize_message(str(exc) or type(exc).__name__, 1000)
        if connection:
            connection.last_attempt_at = utcnow()
            connection.consecutive_failures += 1
            connection.last_error_code = code
            connection.last_error_message = message
            retry_minutes = min(15 * (2 ** max(0, connection.consecutive_failures - 1)), 360)
            connection.next_sync_at = utcnow() + timedelta(minutes=retry_minutes)
            connection.version += 1
            immediate = code in {"sync.authorization", "sync.payment_required"}
            if immediate or connection.consecutive_failures >= 2:
                open_incident(
                    db,
                    workspace_id=connection.workspace_id,
                    incident_key=f"simplefin-sync:{connection.id}",
                    severity="critical" if immediate else "warning",
                    title="SimpleFIN synchronization is failing",
                    message=f"Automatic synchronization failed: {message}",
                )
        if run:
            run.status = "failed"
            run.finished_at = utcnow()
            run.error_code = code
            run.error_message = message
        db.commit()
        logger.exception("SimpleFIN sync failed for connection %s: %s", connection_id, code)
        return {"status": "failed", "new": 0, "changed": 0, "error": code}
    finally:
        if locked:
            try:
                db.execute(text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": f"simplefin:{connection_id}"})
            except Exception:
                pass
        db.close()
