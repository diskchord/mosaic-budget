from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, not_, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Account, Allocation, BudgetTransaction, Category, Section
from ..schemas import (
    AllocationInput,
    AllocationRequest,
    BatchAllocationTransactionInput,
    BatchAllocationRequest,
    BatchTransactionUpdateRequest,
    DeleteTransactionRequest,
    ManualTransactionRequest,
    TransactionUpdateRequest,
)
from ..services.audit import write_audit
from ..services.assignment_undo import (
    AssignmentUndoState,
    AssignmentUndoTokenError,
    create_assignment_undo_token,
    read_assignment_undo_token,
)
from ..services.balance_alerts import evaluate_balance_alerts
from ..services.budgets import serialize_transaction
from ..services.structure import category_visible_in_month
from ..utils import money_str, next_month, parse_decimal, parse_month, utcnow
from .deps import AuthContext, current_auth, require_write

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _load_options():
    return (
        selectinload(BudgetTransaction.account),
        selectinload(BudgetTransaction.allocations)
        .selectinload(Allocation.category)
        .selectinload(Category.section),
        selectinload(BudgetTransaction.source_records),
    )


def _transaction_for_user(
    db: Session,
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    lock: bool = False,
) -> BudgetTransaction:
    query = (
        select(BudgetTransaction)
        .where(
            BudgetTransaction.id == transaction_id,
            BudgetTransaction.workspace_id == workspace_id,
            BudgetTransaction.suppressed_by_duplicate_account.is_(False),
            BudgetTransaction.account.has(Account.is_duplicate.is_(False)),
        )
        .options(*_load_options())
    )
    if lock:
        query = query.with_for_update()
    transaction = db.scalar(query)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


def _lock_account_before_manual_transaction(
    db: Session,
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Account | None:
    """Lock a manual transaction's account before locking the transaction.

    Manual creates and account-management changes already lock accounts first.
    Keeping that order here serializes balance deltas from different
    transactions without introducing an account/transaction deadlock.
    """
    transaction_identity = db.execute(
        select(BudgetTransaction.account_id, BudgetTransaction.source_kind).where(
            BudgetTransaction.id == transaction_id,
            BudgetTransaction.workspace_id == workspace_id,
            BudgetTransaction.suppressed_by_duplicate_account.is_(False),
            BudgetTransaction.account.has(Account.is_duplicate.is_(False)),
        )
    ).one_or_none()
    if transaction_identity is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if transaction_identity.source_kind != "manual":
        return None
    account = db.scalar(
        select(Account)
        .where(
            Account.id == transaction_identity.account_id,
            Account.workspace_id == workspace_id,
            Account.is_duplicate.is_(False),
        )
        .with_for_update()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return account


def _conflict(transaction: BudgetTransaction, message: str = "This transaction changed on another device") -> None:
    raise HTTPException(status_code=409, detail={"message": message, "current": serialize_transaction(transaction)})


def _move_date_to_month(value: date, month: date) -> date:
    return date(month.year, month.month, min(value.day, monthrange(month.year, month.month)[1]))


def _batch_transactions_for_user(
    db: Session,
    transaction_inputs: list[BatchAllocationTransactionInput],
    workspace_id: uuid.UUID,
) -> list[BudgetTransaction]:
    requested_ids = [item.id for item in transaction_inputs]
    requested_versions = {item.id: item.version for item in transaction_inputs}
    rows = db.scalars(
        select(BudgetTransaction)
        .where(
            BudgetTransaction.workspace_id == workspace_id,
            BudgetTransaction.id.in_(requested_ids),
        )
        .options(*_load_options())
        .order_by(BudgetTransaction.id)
        .with_for_update()
    ).unique().all()
    by_id = {transaction.id: transaction for transaction in rows}
    if set(by_id) != set(requested_ids):
        raise HTTPException(status_code=404, detail="One or more transactions were not found")

    transactions = [by_id[transaction_id] for transaction_id in requested_ids]
    if any(
        transaction.suppressed_by_duplicate_account or transaction.account.is_duplicate
        for transaction in transactions
    ):
        raise HTTPException(status_code=404, detail="One or more transactions were not found")

    conflicts = [
        {
            "id": str(transaction.id),
            "expected_version": requested_versions[transaction.id],
            "current": serialize_transaction(transaction),
        }
        for transaction in transactions
        if transaction.version != requested_versions[transaction.id]
    ]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "One or more transactions changed on another device",
                "conflicts": conflicts,
            },
        )
    return transactions


def _validate_categories(
    db: Session,
    workspace_id: uuid.UUID,
    category_ids: set[uuid.UUID],
    effective_date: date,
    *,
    allow_existing: set[uuid.UUID] | None = None,
) -> None:
    if not category_ids:
        return
    allow_existing = allow_existing or set()
    rows = db.scalars(
        select(Category)
        .join(Section, Section.id == Category.section_id)
        .where(Category.id.in_(category_ids), Section.workspace_id == workspace_id)
        .options(selectinload(Category.section))
    ).all()
    by_id = {row.id: row for row in rows}
    if set(by_id) != category_ids:
        raise HTTPException(status_code=400, detail="One or more categories are missing")
    unavailable = [
        category.name
        for category in rows
        if category.id not in allow_existing and not category_visible_in_month(db, category, effective_date)
    ]
    if unavailable:
        names = ", ".join(sorted(unavailable)[:5])
        raise HTTPException(
            status_code=400,
            detail=f"The following categories are not available in this transaction's month: {names}",
        )


def _replace_allocations(
    db: Session,
    transaction: BudgetTransaction,
    allocations_payload,
    *,
    manual_lock: bool,
    allow_unavailable_existing: bool = True,
) -> None:
    parsed = [
        (item.category_id, parse_decimal(item.amount), item.memo.strip()) for item in allocations_payload
    ]
    category_ids = {category_id for category_id, _, _ in parsed}
    if len(category_ids) != len(parsed):
        raise HTTPException(status_code=400, detail="Use each category only once in a split")
    existing_category_ids = (
        {allocation.category_id for allocation in transaction.allocations}
        if allow_unavailable_existing
        else set()
    )
    _validate_categories(
        db,
        transaction.workspace_id,
        category_ids,
        transaction.effective_date,
        allow_existing=existing_category_ids,
    )
    if parsed:
        total = sum((amount for _, amount, _ in parsed), Decimal("0"))
        if total != Decimal(transaction.amount):
            raise HTTPException(
                status_code=400,
                detail=f"Split allocations total {money_str(total)}, but the transaction is {money_str(transaction.amount)}",
            )
    transaction.allocations.clear()
    # Delete prior rows before inserting replacement sort positions. The allocation
    # sum trigger is deferred, while the (transaction_id, sort_order) uniqueness
    # constraint is immediate.
    db.flush()
    for index, (category_id, amount, memo) in enumerate(parsed):
        transaction.allocations.append(
            Allocation(category_id=category_id, amount=amount, memo=memo[:300], sort_order=index)
        )
    transaction.manual_allocation_lock = manual_lock


@router.get("")
def list_transactions(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    status_filter: str = Query(default="active", alias="status"),
    search: str = Query(default="", max_length=200),
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_db),
) -> dict:
    query = select(BudgetTransaction).where(
        BudgetTransaction.workspace_id == auth.user.workspace_id,
        BudgetTransaction.suppressed_by_duplicate_account.is_(False),
        BudgetTransaction.account.has(Account.is_duplicate.is_(False)),
    )
    if status_filter == "trash":
        query = query.where(BudgetTransaction.deleted_at.is_not(None))
    else:
        query = query.where(BudgetTransaction.deleted_at.is_(None))
        if status_filter == "unassigned":
            query = query.where(not_(BudgetTransaction.allocations.any()))
        elif status_filter == "assigned":
            query = query.where(BudgetTransaction.allocations.any())
        elif status_filter == "review":
            query = query.where(BudgetTransaction.needs_review.is_(True))
        elif status_filter == "pending":
            query = query.where(BudgetTransaction.pending.is_(True))
        elif status_filter == "excluded":
            query = query.where(BudgetTransaction.excluded.is_(True))
        else:
            query = query.where(BudgetTransaction.excluded.is_(False))
    if month:
        try:
            start = parse_month(month)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        query = query.where(BudgetTransaction.effective_date >= start, BudgetTransaction.effective_date < next_month(start))
    if account_id:
        query = query.where(BudgetTransaction.account_id == account_id)
    if category_id:
        query = query.where(BudgetTransaction.allocations.any(Allocation.category_id == category_id))
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                BudgetTransaction.payee.ilike(pattern),
                BudgetTransaction.imported_description.ilike(pattern),
                BudgetTransaction.note.ilike(pattern),
            )
        )
    query = (
        query.options(*_load_options())
        .order_by(BudgetTransaction.effective_date.desc(), BudgetTransaction.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = db.scalars(query).unique().all()
    return {"transactions": [serialize_transaction(row) for row in rows], "offset": offset, "limit": limit}


@router.get("/{transaction_id}")
def get_transaction(
    transaction_id: uuid.UUID,
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_db),
) -> dict:
    return {"transaction": serialize_transaction(_transaction_for_user(db, transaction_id, auth.user.workspace_id))}


@router.post("")
def create_manual_transaction(
    payload: ManualTransactionRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    account = db.scalar(
        select(Account)
        .where(
            Account.id == payload.account_id,
            Account.workspace_id == auth.user.workspace_id,
            Account.is_active.is_(True),
            Account.is_duplicate.is_(False),
        )
        .with_for_update()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        amount = parse_decimal(payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if amount == 0:
        raise HTTPException(status_code=400, detail="Transaction amount cannot be zero")
    transaction = BudgetTransaction(
        workspace_id=auth.user.workspace_id,
        account_id=account.id,
        source_kind="manual",
        effective_date=payload.effective_date,
        amount=amount,
        payee=payload.payee.strip(),
        imported_description="",
        imported_extra={},
        note=payload.note,
        pending=False,
        cleared=True,
        manual_payee_lock=True,
        manual_date_lock=True,
        manual_allocation_lock=True,
        created_by_id=auth.user.id,
    )
    db.add(transaction)
    db.flush()
    try:
        _replace_allocations(db, transaction, payload.allocations, manual_lock=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if account.source_type == "manual":
        account.balance = Decimal(account.balance or 0) + amount
        account.available_balance = account.balance
        account.version += 1
    db.flush()
    if account.source_type == "manual":
        evaluate_balance_alerts(
            db,
            workspace_id=auth.user.workspace_id,
            account_ids={account.id},
        )
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="transaction.manual.created",
        object_type="transaction",
        object_id=transaction.id,
        after=serialize_transaction(transaction),
    )
    db.commit()
    return {"transaction": serialize_transaction(transaction)}


@router.put("/{transaction_id}/allocations")
def set_allocations(
    transaction_id: uuid.UUID,
    payload: AllocationRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    transaction = _transaction_for_user(db, transaction_id, auth.user.workspace_id, lock=True)
    if transaction.deleted_at:
        raise HTTPException(status_code=400, detail="Restore the transaction before categorizing it")
    if transaction.version != payload.version:
        _conflict(transaction)
    before = serialize_transaction(transaction)
    try:
        _replace_allocations(db, transaction, payload.allocations, manual_lock=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    transaction.needs_review = False
    transaction.version += 1
    db.flush()
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="transaction.allocations.updated",
        object_type="transaction",
        object_id=transaction.id,
        before=before,
        after=serialize_transaction(transaction),
    )
    db.commit()
    return {"transaction": serialize_transaction(transaction)}


@router.put("/batch")
def set_batch_allocations(
    payload: BatchAllocationRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    if "restore_state" in payload.model_fields_set:
        raise HTTPException(
            status_code=409,
            detail="Mosaic was updated. Reload the page before undoing this assignment.",
        )
    if payload.category_id is not None and payload.target_month is None:
        raise HTTPException(
            status_code=409,
            detail="Mosaic was updated. Reload the page before assigning transactions.",
        )
    transactions = _batch_transactions_for_user(db, payload.transactions, auth.user.workspace_id)
    if any(transaction.deleted_at is not None for transaction in transactions):
        raise HTTPException(status_code=400, detail="Restore deleted transactions before categorizing them")
    if any(transaction.excluded for transaction in transactions):
        raise HTTPException(status_code=400, detail="Excluded transactions cannot be categorized")

    clearing = payload.category_id is None
    target_month = None
    if payload.target_month is not None:
        try:
            target_month = parse_month(payload.target_month)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if target_month > date(9999, 11, 1):
            raise HTTPException(status_code=400, detail="Target month must be before December 9999")
    undo_states: dict[uuid.UUID, AssignmentUndoState] = {}
    undo_category_id: uuid.UUID | None = None
    if payload.undo_token is not None:
        try:
            undo = read_assignment_undo_token(
                payload.undo_token,
                auth.user.workspace_id,
                auth.user.id,
                auth.session.id,
            )
        except AssignmentUndoTokenError as exc:
            raise HTTPException(status_code=400, detail="This assignment can no longer be undone") from exc
        undo_states = undo.states
        undo_category_id = undo.category_id
        if set(undo_states) != {transaction.id for transaction in transactions}:
            raise HTTPException(status_code=400, detail="This Undo does not match the selected transactions")
        if any(
            undo_states[transaction.id].assigned_version != transaction.version
            for transaction in transactions
        ):
            raise HTTPException(
                status_code=409,
                detail="One or more transactions changed after this assignment",
            )
    desired_dates = {
        transaction.id: (
            _move_date_to_month(transaction.effective_date, target_month)
            if target_month is not None
            else undo_states[transaction.id].effective_date
            if transaction.id in undo_states
            else transaction.effective_date
        )
        for transaction in transactions
    }
    if clearing:
        if any(not transaction.allocations for transaction in transactions):
            raise HTTPException(status_code=400, detail="One or more transactions are already unassigned")
        if undo_category_id is not None and any(
            len(transaction.allocations) != 1
            or transaction.allocations[0].category_id != undo_category_id
            for transaction in transactions
        ):
            raise HTTPException(
                status_code=409,
                detail="One or more transactions changed after this assignment",
            )
    else:
        if any(transaction.allocations for transaction in transactions):
            raise HTTPException(status_code=400, detail="Group assignment accepts only unassigned transactions")
        for effective_date in set(desired_dates.values()):
            _validate_categories(
                db,
                auth.user.workspace_id,
                {payload.category_id},
                effective_date,
                allow_existing=set(),
            )

    before_by_id = {transaction.id: serialize_transaction(transaction) for transaction in transactions}
    original_states = {
        transaction.id: AssignmentUndoState(
            effective_date=transaction.effective_date,
            manual_date_lock=transaction.manual_date_lock,
            manual_allocation_lock=transaction.manual_allocation_lock,
            needs_review=transaction.needs_review,
            assigned_version=transaction.version + 1,
        )
        for transaction in transactions
    }
    for transaction in transactions:
        desired_date = desired_dates[transaction.id]
        if target_month is not None:
            transaction.effective_date = desired_date
            transaction.manual_date_lock = True
        elif transaction.id in undo_states:
            transaction.effective_date = desired_date
            transaction.manual_date_lock = undo_states[transaction.id].manual_date_lock
        allocations = (
            []
            if clearing
            else [
                AllocationInput(
                    category_id=payload.category_id,
                    amount=money_str(transaction.amount),
                    memo="",
                )
            ]
        )
        _replace_allocations(db, transaction, allocations, manual_lock=True)
        if transaction.id in undo_states:
            original = undo_states[transaction.id]
            transaction.manual_allocation_lock = original.manual_allocation_lock
            transaction.needs_review = original.needs_review
        else:
            transaction.needs_review = False
        transaction.version += 1

    db.flush()
    for transaction in transactions:
        detail = {"batch": True, "batch_size": len(transactions)}
        if target_month is not None:
            detail["target_month"] = payload.target_month
        elif undo_states:
            detail["assignment_undone"] = True
        write_audit(
            db,
            workspace_id=auth.user.workspace_id,
            actor_user_id=auth.user.id,
            action="transaction.allocations.updated",
            object_type="transaction",
            object_id=transaction.id,
            before=before_by_id[transaction.id],
            after=serialize_transaction(transaction),
            detail=detail,
        )
    undo_token = (
        create_assignment_undo_token(
            auth.user.workspace_id,
            auth.user.id,
            auth.session.id,
            payload.category_id,
            payload.target_month,
            original_states,
        )
        if not clearing
        else None
    )
    db.commit()
    return {
        "transactions": [serialize_transaction(transaction) for transaction in transactions],
        "undo_token": undo_token,
    }


@router.patch("/batch")
def update_batch_transactions(
    payload: BatchTransactionUpdateRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    transactions = _batch_transactions_for_user(db, payload.transactions, auth.user.workspace_id)
    if any(transaction.deleted_at is not None for transaction in transactions):
        raise HTTPException(status_code=400, detail="Restore deleted transactions before modifying them")

    requested_fields = [
        field
        for field in ("category_id", "needs_review", "excluded")
        if field in payload.model_fields_set
    ]
    category_supplied = "category_id" in payload.model_fields_set
    review_supplied = "needs_review" in payload.model_fields_set
    excluded_supplied = "excluded" in payload.model_fields_set

    if category_supplied:
        if any(len(transaction.allocations) > 1 for transaction in transactions):
            raise HTTPException(status_code=400, detail="Split transactions must be edited individually")
        if payload.category_id is not None:
            for effective_date in sorted({transaction.effective_date for transaction in transactions}):
                _validate_categories(
                    db,
                    auth.user.workspace_id,
                    {payload.category_id},
                    effective_date,
                    allow_existing=set(),
                )

    changed: list[tuple[BudgetTransaction, dict]] = []
    for transaction in transactions:
        existing_allocation = transaction.allocations[0] if transaction.allocations else None
        allocation_changed = category_supplied and (
            (payload.category_id is None and existing_allocation is not None)
            or (
                payload.category_id is not None
                and (existing_allocation is None or existing_allocation.category_id != payload.category_id)
            )
        )
        desired_review = (
            payload.needs_review
            if review_supplied
            else False
            if category_supplied
            else transaction.needs_review
        )
        desired_excluded = payload.excluded if excluded_supplied else transaction.excluded
        if not (
            allocation_changed
            or desired_review != transaction.needs_review
            or desired_excluded != transaction.excluded
        ):
            continue

        before = serialize_transaction(transaction)
        if allocation_changed:
            allocations = (
                []
                if payload.category_id is None
                else [
                    AllocationInput(
                        category_id=payload.category_id,
                        amount=money_str(transaction.amount),
                        memo=existing_allocation.memo if existing_allocation else "",
                    )
                ]
            )
            _replace_allocations(db, transaction, allocations, manual_lock=True)
        transaction.needs_review = desired_review
        transaction.excluded = desired_excluded
        transaction.version += 1
        changed.append((transaction, before))

    db.flush()
    for transaction, before in changed:
        write_audit(
            db,
            workspace_id=auth.user.workspace_id,
            actor_user_id=auth.user.id,
            action="transaction.updated",
            object_type="transaction",
            object_id=transaction.id,
            before=before,
            after=serialize_transaction(transaction),
            detail={
                "batch": True,
                "batch_size": len(transactions),
                "fields": requested_fields,
            },
        )
    db.commit()
    return {
        "transactions": [serialize_transaction(transaction) for transaction in transactions],
        "updated_count": len(changed),
    }


@router.patch("/{transaction_id}")
def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdateRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    transaction = _transaction_for_user(db, transaction_id, auth.user.workspace_id, lock=True)
    if transaction.version != payload.version:
        _conflict(transaction)
    before = serialize_transaction(transaction)
    if payload.payee is not None and payload.payee.strip() != transaction.payee:
        transaction.payee = payload.payee.strip()
        transaction.manual_payee_lock = True
    date_changed = payload.effective_date is not None and payload.effective_date != transaction.effective_date
    if payload.effective_date is not None:
        if payload.allocations is None:
            existing_category_ids = {allocation.category_id for allocation in transaction.allocations}
            _validate_categories(
                db,
                transaction.workspace_id,
                existing_category_ids,
                payload.effective_date,
            )
        transaction.effective_date = payload.effective_date
        transaction.manual_date_lock = True
    if payload.allocations is not None:
        try:
            _replace_allocations(
                db,
                transaction,
                payload.allocations,
                manual_lock=True,
                allow_unavailable_existing=not date_changed,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.note is not None:
        transaction.note = payload.note
    if payload.tags is not None:
        transaction.tags = list(dict.fromkeys(tag.strip()[:80] for tag in payload.tags if tag.strip()))[:50]
    if payload.cleared is not None:
        transaction.cleared = payload.cleared
    if payload.excluded is not None:
        transaction.excluded = payload.excluded
    if payload.needs_review is not None:
        transaction.needs_review = payload.needs_review
    transaction.version += 1
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="transaction.updated",
        object_type="transaction",
        object_id=transaction.id,
        before=before,
        after=serialize_transaction(transaction),
    )
    db.commit()
    return {"transaction": serialize_transaction(transaction)}


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: uuid.UUID,
    payload: DeleteTransactionRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    locked_account = _lock_account_before_manual_transaction(db, transaction_id, auth.user.workspace_id)
    transaction = _transaction_for_user(db, transaction_id, auth.user.workspace_id, lock=True)
    if transaction.version != payload.version:
        _conflict(transaction)
    try:
        confirmed_amount = parse_decimal(payload.confirm_amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if confirmed_amount != Decimal(transaction.amount):
        raise HTTPException(status_code=400, detail="The confirmation amount does not match the transaction")
    if transaction.deleted_at:
        return {"ok": True, "transaction": serialize_transaction(transaction)}
    before = serialize_transaction(transaction)
    transaction.deleted_at = utcnow()
    transaction.deleted_by_id = auth.user.id
    transaction.version += 1
    if locked_account is not None and locked_account.source_type == "manual":
        locked_account.balance = Decimal(locked_account.balance or 0) - Decimal(transaction.amount)
        locked_account.available_balance = locked_account.balance
        locked_account.version += 1
        db.flush()
        evaluate_balance_alerts(
            db,
            workspace_id=auth.user.workspace_id,
            account_ids={transaction.account_id},
        )
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="transaction.deleted",
        object_type="transaction",
        object_id=transaction.id,
        before=before,
        after=serialize_transaction(transaction),
    )
    db.commit()
    return {"ok": True, "transaction": serialize_transaction(transaction)}


@router.post("/{transaction_id}/restore")
def restore_transaction(
    transaction_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    locked_account = _lock_account_before_manual_transaction(db, transaction_id, auth.user.workspace_id)
    transaction = _transaction_for_user(db, transaction_id, auth.user.workspace_id, lock=True)
    if transaction.version != version:
        _conflict(transaction)
    if not transaction.deleted_at:
        return {"transaction": serialize_transaction(transaction)}
    before = serialize_transaction(transaction)
    transaction.deleted_at = None
    transaction.deleted_by_id = None
    transaction.version += 1
    if locked_account is not None and locked_account.source_type == "manual":
        locked_account.balance = Decimal(locked_account.balance or 0) + Decimal(transaction.amount)
        locked_account.available_balance = locked_account.balance
        locked_account.version += 1
        db.flush()
        evaluate_balance_alerts(
            db,
            workspace_id=auth.user.workspace_id,
            account_ids={transaction.account_id},
        )
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="transaction.restored",
        object_type="transaction",
        object_id=transaction.id,
        before=before,
        after=serialize_transaction(transaction),
    )
    db.commit()
    return {"transaction": serialize_transaction(transaction)}
