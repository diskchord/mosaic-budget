from __future__ import annotations

import regex
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import not_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Account, Allocation, BudgetTransaction, Category, Rule, RuleRevision, Section, Workspace
from ..schemas import RuleOrderRequest, RuleRequest, RuleRunRequest, RuleUpdateRequest
from ..services.audit import write_audit
from ..services.budgets import serialize_transaction
from ..services.rules import (
    apply_rules_to_transaction,
    enabled_rules_for_workspace,
    matches_tree,
    rule_order_columns,
    rule_snapshot,
)
from ..utils import next_month, parse_decimal, parse_month, utcnow
from .deps import AuthContext, current_auth, require_write

router = APIRouter(prefix="/api/rules", tags=["rules"])

MAX_MANUAL_RULE_TRANSACTIONS = 5000
ALLOCATION_ACTIONS = {"assign_category", "split_fixed", "split_percent"}

ALLOWED_FIELDS = {
    "original_description",
    "payee",
    "account",
    "account_id",
    "connection",
    "amount",
    "outflow",
    "inflow",
    "date",
    "day_of_week",
    "day_of_month",
    "month",
    "pending",
    "cleared",
    "source",
    "unassigned",
    "note",
    "tags",
    "currency",
    "needs_review",
}
ALLOWED_OPERATORS = {
    "is",
    "is_not",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "regex",
    "one_of",
    "not_one_of",
    "between",
    "gt",
    "gte",
    "lt",
    "lte",
    "before",
    "after",
    "has_tag",
    "lacks_tag",
    "is_true",
    "is_false",
}
ALLOWED_ACTIONS = {
    "set_payee",
    "assign_category",
    "split_fixed",
    "split_percent",
    "add_note",
    "add_tag",
    "mark_review",
    "exclude",
    "suggest_transfer",
    "alert",
}


def _validate_conditions(tree: dict[str, Any], *, depth: int = 0) -> None:
    if depth > 6:
        raise HTTPException(status_code=400, detail="Rule condition nesting is too deep")
    children = tree.get("children")
    if children is not None:
        if tree.get("combinator", "all") not in {"all", "any", "none"}:
            raise HTTPException(status_code=400, detail="Invalid condition group")
        if not isinstance(children, list) or not children or len(children) > 50:
            raise HTTPException(status_code=400, detail="Condition groups require 1 to 50 conditions")
        for child in children:
            if not isinstance(child, dict):
                raise HTTPException(status_code=400, detail="Invalid rule condition")
            _validate_conditions(child, depth=depth + 1)
        return
    field = tree.get("field")
    operator = tree.get("operator")
    if field not in ALLOWED_FIELDS or operator not in ALLOWED_OPERATORS:
        raise HTTPException(status_code=400, detail="Unsupported rule field or operator")
    if operator == "regex":
        pattern = str(tree.get("value", ""))
        if len(pattern) > 300:
            raise HTTPException(status_code=400, detail="Regular expressions are limited to 300 characters")
        try:
            regex.compile(pattern)
        except regex.error as exc:
            raise HTTPException(status_code=400, detail=f"Invalid regular expression: {exc}") from exc
    if field in {"amount", "outflow", "inflow"}:
        values = tree.get("value") if isinstance(tree.get("value"), list) else [tree.get("value")]
        try:
            for value in values:
                parse_decimal(value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Amount conditions must contain valid numbers") from exc


def _category_ids_from_actions(actions: list[dict[str, Any]]) -> set[uuid.UUID]:
    result: set[uuid.UUID] = set()
    for action in actions:
        action_type = action.get("type")
        if action_type not in ALLOWED_ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported rule action: {action_type}")
        try:
            if action_type == "assign_category":
                result.add(uuid.UUID(str(action["category_id"])))
            elif action_type in {"split_fixed", "split_percent"}:
                splits = action.get("splits", [])
                if not isinstance(splits, list) or not splits or len(splits) > 100:
                    raise HTTPException(status_code=400, detail="Split actions require 1 to 100 parts")
                action_ids: list[uuid.UUID] = []
                total_percent = 0
                for part in splits:
                    category_id = uuid.UUID(str(part["category_id"]))
                    action_ids.append(category_id)
                    if action_type == "split_fixed":
                        if parse_decimal(part["amount"]) <= 0:
                            raise HTTPException(status_code=400, detail="Fixed split amounts must be greater than zero")
                    else:
                        percent = parse_decimal(part["percent"])
                        if percent <= 0:
                            raise HTTPException(status_code=400, detail="Split percentages must be greater than zero")
                        total_percent += percent
                remainder = action.get("remainder_category_id")
                if remainder:
                    action_ids.append(uuid.UUID(str(remainder)))
                if len(set(action_ids)) != len(action_ids):
                    raise HTTPException(status_code=400, detail="A split cannot use the same category more than once")
                if action_type == "split_percent":
                    if total_percent > 100:
                        raise HTTPException(status_code=400, detail="Split percentages cannot exceed 100%")
                    if total_percent < 100 and not remainder:
                        raise HTTPException(status_code=400, detail="Percentage splits below 100% need a remainder category")
                result.update(action_ids)
        except HTTPException:
            raise
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid {action_type} action") from exc
    return result


def _validate_rule(db: Session, workspace_id: uuid.UUID, payload: RuleRequest | RuleUpdateRequest) -> None:
    _validate_conditions(payload.conditions)
    category_ids = _category_ids_from_actions(payload.actions)
    if category_ids:
        found = set(
            db.scalars(
                select(Category.id)
                .join(Section, Section.id == Category.section_id)
                .where(
                    Category.id.in_(category_ids),
                    Section.workspace_id == workspace_id,
                    Category.archived_at.is_(None),
                    Category.deleted_from_month.is_(None),
                    Section.archived_at.is_(None),
                    Section.deleted_from_month.is_(None),
                )
            ).all()
        )
        if found != category_ids:
            raise HTTPException(status_code=400, detail="A rule action refers to a missing or archived category")


def _rule_for_user(db: Session, rule_id: uuid.UUID, workspace_id: uuid.UUID, *, lock: bool = False) -> Rule:
    query = select(Rule).where(Rule.id == rule_id, Rule.workspace_id == workspace_id)
    if lock:
        query = query.with_for_update()
    rule = db.scalar(query)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


def _lock_rule_set(db: Session, workspace_id: uuid.UUID) -> None:
    # A stable parent-row lock serializes creates, archives, phase changes, and
    # reorders. Row-locking only the current lane would not prevent a concurrent
    # insert from appearing immediately after its complete-list version check.
    db.scalar(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())


def _save_revision(db: Session, rule: Rule, user_id: uuid.UUID | None) -> None:
    db.add(
        RuleRevision(
            rule_id=rule.id,
            version=rule.version,
            snapshot=rule_snapshot(rule),
            changed_by_id=user_id,
        )
    )


def _candidate_query(workspace_id: uuid.UUID):
    return (
        select(BudgetTransaction)
        .where(
            BudgetTransaction.workspace_id == workspace_id,
            BudgetTransaction.deleted_at.is_(None),
            BudgetTransaction.account.has(Account.is_duplicate.is_(False)),
        )
        .options(
            selectinload(BudgetTransaction.account),
            selectinload(BudgetTransaction.allocations)
            .selectinload(Allocation.category)
            .selectinload(Category.section),
        )
        .order_by(BudgetTransaction.effective_date.desc())
    )


def _run_candidate_filters(
    workspace_id: uuid.UUID,
    month_start: date,
    month_end: date,
) -> tuple[Any, ...]:
    return (
        BudgetTransaction.workspace_id == workspace_id,
        BudgetTransaction.effective_date >= month_start,
        BudgetTransaction.effective_date < month_end,
        BudgetTransaction.deleted_at.is_(None),
        BudgetTransaction.excluded.is_(False),
        BudgetTransaction.suppressed_by_duplicate_account.is_(False),
        BudgetTransaction.account.has(Account.is_duplicate.is_(False)),
        not_(BudgetTransaction.allocations.any()),
    )


def _rule_has_allocation_action(rule: Rule) -> bool:
    return any(action.get("type") in ALLOCATION_ACTIONS for action in rule.actions)


def _empty_apply_result() -> dict[str, int]:
    return {
        "transactions_changed": 0,
        "transactions_sorted": 0,
        "transactions_still_unsorted": 0,
    }


def _apply_existing(db: Session, rule: Rule, scope: str) -> dict[str, int]:
    query = _candidate_query(rule.workspace_id)
    if scope == "unassigned":
        query = query.where(not_(BudgetTransaction.allocations.any()))
    rows = db.scalars(query.limit(5000)).unique().all()
    result = _empty_apply_result()
    has_allocation_action = _rule_has_allocation_action(rule)
    for transaction in rows:
        if scope != "eligible" and scope != "unassigned":
            continue
        initially_unassigned = not transaction.allocations
        before_version = transaction.version
        matched = apply_rules_to_transaction(db, transaction, rules=[rule])
        if transaction.version != before_version:
            result["transactions_changed"] += 1
        if initially_unassigned and transaction.allocations:
            result["transactions_sorted"] += 1
        elif initially_unassigned and matched and has_allocation_action:
            result["transactions_still_unsorted"] += 1
    return result


@router.get("")
def list_rules(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(Rule)
        .where(Rule.workspace_id == auth.user.workspace_id, Rule.archived_at.is_(None))
        .order_by(*rule_order_columns())
    ).all()
    return {"rules": [rule_snapshot(rule) for rule in rows]}


@router.get("/options")
def rule_options(auth: AuthContext = Depends(current_auth)) -> dict:
    return {
        "fields": sorted(ALLOWED_FIELDS),
        "operators": sorted(ALLOWED_OPERATORS),
        "actions": sorted(ALLOWED_ACTIONS),
        "phases": ["cleanup", "categorize", "finish"],
    }


@router.post("/preview")
def preview_rule(
    payload: RuleRequest,
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_db),
) -> dict:
    _validate_rule(db, auth.user.workspace_id, payload)
    rows = db.scalars(_candidate_query(auth.user.workspace_id).limit(1000)).unique().all()
    matches = [transaction for transaction in rows if matches_tree(transaction, payload.conditions)]
    return {
        "match_count_in_sample": len(matches),
        "sample_size": len(rows),
        "transactions": [serialize_transaction(transaction) for transaction in matches[:50]],
    }


@router.post("/run")
def run_rules(
    payload: RuleRunRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    try:
        month_start = parse_month(payload.month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _lock_rule_set(db, auth.user.workspace_id)
    month_end = next_month(month_start)
    filters = _run_candidate_filters(auth.user.workspace_id, month_start, month_end)
    candidate_ids = db.scalars(
        select(BudgetTransaction.id)
        .where(*filters)
        .order_by(BudgetTransaction.effective_date.desc(), BudgetTransaction.id)
        .limit(MAX_MANUAL_RULE_TRANSACTIONS + 1)
    ).all()
    if len(candidate_ids) > MAX_MANUAL_RULE_TRANSACTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Manual rule runs are limited to {MAX_MANUAL_RULE_TRANSACTIONS:,} unsorted "
                "transactions per month. Sort some transactions and try again."
            ),
        )
    rules = enabled_rules_for_workspace(db, auth.user.workspace_id)
    scanned = 0
    changed = 0
    sorted_count = 0
    still_unsorted_count = 0
    for transaction_id in candidate_ids:
        transaction = db.scalar(
            select(BudgetTransaction)
            .where(BudgetTransaction.id == transaction_id, *filters)
            .options(
                selectinload(BudgetTransaction.account),
                selectinload(BudgetTransaction.allocations)
                .selectinload(Allocation.category)
                .selectinload(Category.section),
            )
            .with_for_update()
        )
        if transaction is None:
            continue
        scanned += 1
        before_version = transaction.version
        matched = apply_rules_to_transaction(db, transaction, rules=rules)
        if transaction.version != before_version:
            changed += 1
        if transaction.allocations:
            sorted_count += 1
        elif any(_rule_has_allocation_action(rule) for rule in matched):
            still_unsorted_count += 1

    result = {
        "month": month_start.isoformat()[:7],
        "transactions_scanned": scanned,
        "transactions_changed": changed,
        "transactions_sorted": sorted_count,
        "transactions_still_unsorted": still_unsorted_count,
    }
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="rules.applied",
        object_type="rule_set",
        detail={"scope": "unassigned", **result},
    )
    db.commit()
    return result


@router.post("")
def create_rule(
    payload: RuleRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    _lock_rule_set(db, auth.user.workspace_id)
    _validate_rule(db, auth.user.workspace_id, payload)
    rule = Rule(
        workspace_id=auth.user.workspace_id,
        name=payload.name.strip(),
        enabled=payload.enabled,
        phase=payload.phase,
        priority=payload.priority,
        conditions=payload.conditions,
        actions=payload.actions,
        apply_to_manual_overrides=payload.apply_to_manual_overrides,
        stop_processing=payload.stop_processing,
        created_by_id=auth.user.id,
    )
    db.add(rule)
    db.flush()
    _save_revision(db, rule, auth.user.id)
    applied = _apply_existing(db, rule, payload.apply_now) if payload.apply_now != "none" else _empty_apply_result()
    historical = {
        "historical_transactions_changed": applied["transactions_changed"],
        "historical_transactions_sorted": applied["transactions_sorted"],
        "historical_transactions_still_unsorted": applied["transactions_still_unsorted"],
    }
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="rule.created",
        object_type="rule",
        object_id=rule.id,
        after=rule_snapshot(rule),
        detail=historical,
    )
    db.commit()
    return {"rule": rule_snapshot(rule), **historical}


@router.put("/order")
def reorder_rules(
    payload: RuleOrderRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    _lock_rule_set(db, auth.user.workspace_id)
    rows = db.scalars(
        select(Rule)
        .where(
            Rule.workspace_id == auth.user.workspace_id,
            Rule.phase == payload.phase,
            Rule.archived_at.is_(None),
        )
        .order_by(Rule.id)
        .with_for_update()
    ).all()
    current = sorted(rows, key=lambda rule: (rule.priority, rule.created_at, str(rule.id)))
    current_by_id = {rule.id: rule for rule in current}
    requested_ids = [item.id for item in payload.rules]
    versions_match = all(
        current_by_id.get(item.id) is not None and current_by_id[item.id].version == item.version
        for item in payload.rules
    )
    if set(requested_ids) != set(current_by_id) or not versions_match:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "These rules changed on another device. The latest order has been restored.",
                "current": [rule_snapshot(rule) for rule in current],
            },
        )

    if requested_ids == [rule.id for rule in current]:
        return {"rules": [rule_snapshot(rule) for rule in current]}

    ordered = [current_by_id[rule_id] for rule_id in requested_ids]
    priority_slots = sorted(rule.priority for rule in current)
    if len(priority_slots) != len(set(priority_slots)):
        priority_slots = list(range(len(ordered)))
    before = {
        "phase": payload.phase,
        "rules": [
            {"id": str(rule.id), "priority": rule.priority, "version": rule.version}
            for rule in current
        ],
    }
    for rule, priority in zip(ordered, priority_slots, strict=True):
        if rule.priority == priority:
            continue
        rule.priority = priority
        rule.version += 1
        _save_revision(db, rule, auth.user.id)
    after = {
        "phase": payload.phase,
        "rules": [
            {"id": str(rule.id), "priority": rule.priority, "version": rule.version}
            for rule in ordered
        ],
    }
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="rules.reordered",
        object_type="rule_set",
        before=before,
        after=after,
        detail={"phase": payload.phase, "rule_ids": [str(rule.id) for rule in ordered]},
    )
    db.commit()
    return {"rules": [rule_snapshot(rule) for rule in ordered]}


@router.patch("/{rule_id}")
def update_rule(
    rule_id: uuid.UUID,
    payload: RuleUpdateRequest,
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    _lock_rule_set(db, auth.user.workspace_id)
    _validate_rule(db, auth.user.workspace_id, payload)
    rule = _rule_for_user(db, rule_id, auth.user.workspace_id, lock=True)
    if rule.version != payload.version:
        raise HTTPException(status_code=409, detail={"message": "Rule conflict", "current": rule_snapshot(rule)})
    before = rule_snapshot(rule)
    rule.name = payload.name.strip()
    rule.enabled = payload.enabled
    rule.phase = payload.phase
    rule.priority = payload.priority
    rule.conditions = payload.conditions
    rule.actions = payload.actions
    rule.apply_to_manual_overrides = payload.apply_to_manual_overrides
    rule.stop_processing = payload.stop_processing
    rule.version += 1
    _save_revision(db, rule, auth.user.id)
    applied = _apply_existing(db, rule, payload.apply_now) if payload.apply_now != "none" else _empty_apply_result()
    historical = {
        "historical_transactions_changed": applied["transactions_changed"],
        "historical_transactions_sorted": applied["transactions_sorted"],
        "historical_transactions_still_unsorted": applied["transactions_still_unsorted"],
    }
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="rule.updated",
        object_type="rule",
        object_id=rule.id,
        before=before,
        after=rule_snapshot(rule),
        detail=historical,
    )
    db.commit()
    return {"rule": rule_snapshot(rule), **historical}


@router.post("/{rule_id}/apply")
def apply_rule_now(
    rule_id: uuid.UUID,
    scope: str = Body(default="unassigned", embed=True),
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    if scope not in {"unassigned", "eligible"}:
        raise HTTPException(status_code=400, detail="Scope must be unassigned or eligible")
    _lock_rule_set(db, auth.user.workspace_id)
    rule = _rule_for_user(db, rule_id, auth.user.workspace_id)
    applied = _apply_existing(db, rule, scope)
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="rule.applied",
        object_type="rule",
        object_id=rule.id,
        detail={"scope": scope, **applied},
    )
    db.commit()
    return applied


@router.delete("/{rule_id}")
def archive_rule(
    rule_id: uuid.UUID,
    version: int = Body(..., embed=True, ge=1),
    auth: AuthContext = Depends(require_write),
    db: Session = Depends(get_db),
) -> dict:
    _lock_rule_set(db, auth.user.workspace_id)
    rule = _rule_for_user(db, rule_id, auth.user.workspace_id, lock=True)
    if rule.version != version:
        raise HTTPException(status_code=409, detail={"message": "Rule conflict", "current": rule_snapshot(rule)})
    before = rule_snapshot(rule)
    rule.enabled = False
    rule.archived_at = utcnow()
    rule.version += 1
    _save_revision(db, rule, auth.user.id)
    write_audit(
        db,
        workspace_id=auth.user.workspace_id,
        actor_user_id=auth.user.id,
        action="rule.archived",
        object_type="rule",
        object_id=rule.id,
        before=before,
        after=rule_snapshot(rule),
    )
    db.commit()
    return {"ok": True}
