from __future__ import annotations

import regex
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Allocation, BudgetTransaction, Category, Rule, Section
from ..utils import MONEY_QUANT, normalize_description, parse_decimal
from .notifications import open_incident
from .structure import category_visible_in_month

PHASE_ORDER = {"cleanup": 0, "categorize": 1, "finish": 2}


class RuleError(ValueError):
    pass


def enabled_rules_for_workspace(db: Session, workspace_id: uuid.UUID) -> list[Rule]:
    phase_sort = case(
        (Rule.phase == "cleanup", 0),
        (Rule.phase == "categorize", 1),
        else_=2,
    )
    return db.scalars(
        select(Rule)
        .where(
            Rule.workspace_id == workspace_id,
            Rule.enabled.is_(True),
            Rule.archived_at.is_(None),
        )
        .order_by(phase_sort, Rule.priority, Rule.created_at)
    ).all()


def _field_value(transaction: BudgetTransaction, field: str) -> Any:
    amount = Decimal(transaction.amount)
    values: dict[str, Any] = {
        "original_description": transaction.imported_description or transaction.payee,
        "payee": transaction.payee,
        "account": str(transaction.account_id),
        "account_id": str(transaction.account_id),
        "connection": str(transaction.account.simplefin_connection_id)
        if transaction.account and transaction.account.simplefin_connection_id
        else "",
        "amount": amount,
        "outflow": -amount if amount < 0 else Decimal("0"),
        "inflow": amount if amount > 0 else Decimal("0"),
        "date": transaction.effective_date,
        "day_of_week": transaction.effective_date.strftime("%A").casefold(),
        "day_of_month": transaction.effective_date.day,
        "month": transaction.effective_date.month,
        "pending": transaction.pending,
        "cleared": transaction.cleared,
        "source": transaction.source_kind,
        "unassigned": len(transaction.allocations) == 0,
        "note": transaction.note,
        "tags": transaction.tags or [],
        "currency": transaction.account.currency if transaction.account else "",
        "needs_review": transaction.needs_review,
    }
    return values.get(field)


def _as_comparable(value: Any, target: Any) -> tuple[Any, Any]:
    if isinstance(value, Decimal):
        return value, parse_decimal(target)
    if isinstance(value, date):
        if isinstance(target, date):
            return value, target
        return value, date.fromisoformat(str(target))
    if isinstance(value, bool):
        if isinstance(target, bool):
            return value, target
        return value, str(target).casefold() in {"1", "true", "yes"}
    if isinstance(value, int):
        return value, int(target)
    return str(value or "").casefold(), str(target or "").casefold()


def evaluate_condition(transaction: BudgetTransaction, condition: dict[str, Any]) -> bool:
    field = str(condition.get("field", ""))
    operator = str(condition.get("operator", "is"))
    target = condition.get("value")
    value = _field_value(transaction, field)
    if value is None:
        return False

    if operator in {"is_true", "is_false"}:
        result = bool(value)
        return result if operator == "is_true" else not result
    if operator == "has_tag":
        return str(target).casefold() in {str(tag).casefold() for tag in value}
    if operator == "lacks_tag":
        return str(target).casefold() not in {str(tag).casefold() for tag in value}
    if operator in {"one_of", "not_one_of"}:
        targets = target if isinstance(target, list) else [target]
        normalized = {_as_comparable(value, item)[1] for item in targets}
        left, _ = _as_comparable(value, targets[0] if targets else "")
        result = left in normalized
        return not result if operator == "not_one_of" else result
    if operator == "between":
        if not isinstance(target, list) or len(target) != 2:
            return False
        left, low = _as_comparable(value, target[0])
        _, high = _as_comparable(value, target[1])
        return low <= left <= high

    left, right = _as_comparable(value, target)
    if operator == "is":
        return left == right
    if operator == "is_not":
        return left != right
    if operator == "contains":
        return str(right) in str(left)
    if operator == "not_contains":
        return str(right) not in str(left)
    if operator == "starts_with":
        return str(left).startswith(str(right))
    if operator == "ends_with":
        return str(left).endswith(str(right))
    if operator == "regex":
        pattern = str(target)
        if len(pattern) > 300:
            return False
        try:
            return regex.search(pattern, str(value), regex.IGNORECASE, timeout=0.05) is not None
        except (regex.error, TimeoutError):
            return False
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    if operator == "before":
        return left < right
    if operator == "after":
        return left > right
    return False


def matches_tree(transaction: BudgetTransaction, tree: dict[str, Any]) -> bool:
    children = tree.get("children")
    if isinstance(children, list):
        results = [matches_tree(transaction, child) for child in children if isinstance(child, dict)]
        combinator = str(tree.get("combinator", "all"))
        if combinator == "any":
            return any(results)
        if combinator == "none":
            return not any(results)
        return all(results)
    return evaluate_condition(transaction, tree)


def _signed_amount(parent: Decimal, magnitude: Decimal) -> Decimal:
    return magnitude.copy_abs() if parent >= 0 else -magnitude.copy_abs()


def _replace_allocations(
    db: Session,
    transaction: BudgetTransaction,
    allocations: list[tuple[uuid.UUID, Decimal, str]],
    *,
    rule_id: uuid.UUID,
) -> bool:
    total = sum((amount for _, amount, _ in allocations), Decimal("0"))
    if total.quantize(MONEY_QUANT) != Decimal(transaction.amount).quantize(MONEY_QUANT):
        raise RuleError(f"Rule allocation total {total} does not equal transaction amount {transaction.amount}")
    category_ids = {category_id for category_id, _, _ in allocations}
    if len(category_ids) != len(allocations):
        raise RuleError("A rule split cannot use the same category more than once")
    categories = db.scalars(
        select(Category)
        .join(Section, Section.id == Category.section_id)
        .where(
            Category.id.in_(category_ids),
            Category.archived_at.is_(None),
            Section.archived_at.is_(None),
            Section.workspace_id == transaction.workspace_id,
        )
        .options(selectinload(Category.section))
    ).all()
    if {category.id for category in categories} != category_ids:
        raise RuleError("Rule refers to a missing or archived category")
    unavailable = [
        category.name
        for category in categories
        if not category_visible_in_month(db, category, transaction.effective_date)
    ]
    if unavailable:
        raise RuleError(
            "Rule target is not available in the transaction month: " + ", ".join(sorted(unavailable)[:5])
        )

    old = [(item.category_id, Decimal(item.amount), item.memo) for item in transaction.allocations]
    new = [(category_id, amount, memo) for category_id, amount, memo in allocations]
    if old == new:
        return False
    transaction.allocations.clear()
    # Delete prior rows before inserting replacement sort positions. The allocation
    # sum trigger is deferred, while the (transaction_id, sort_order) uniqueness
    # constraint is immediate.
    db.flush()
    for index, (category_id, amount, memo) in enumerate(allocations):
        transaction.allocations.append(
            Allocation(
                category_id=category_id,
                amount=amount,
                memo=memo,
                sort_order=index,
                applied_by_rule_id=rule_id,
            )
        )
    return True


def _allocation_action(
    db: Session, transaction: BudgetTransaction, rule: Rule, action: dict[str, Any]
) -> bool:
    action_type = action.get("type")
    parent = Decimal(transaction.amount).quantize(MONEY_QUANT)
    if action_type == "assign_category":
        category_id = uuid.UUID(str(action["category_id"]))
        return _replace_allocations(db, transaction, [(category_id, parent, "")], rule_id=rule.id)

    if action_type == "split_fixed":
        parts: list[tuple[uuid.UUID, Decimal, str]] = []
        allocated = Decimal("0")
        for item in action.get("splits", []):
            magnitude = parse_decimal(item["amount"]).copy_abs()
            amount = _signed_amount(parent, magnitude)
            allocated += amount
            parts.append((uuid.UUID(str(item["category_id"])), amount, str(item.get("memo", ""))[:300]))
        if abs(allocated) > abs(parent):
            raise RuleError("Fixed split amounts exceed the transaction amount")
        remainder = (parent - allocated).quantize(MONEY_QUANT)
        remainder_category = action.get("remainder_category_id")
        if remainder:
            if not remainder_category:
                raise RuleError("Fixed split leaves a remainder without a remainder category")
            parts.append((uuid.UUID(str(remainder_category)), remainder, "Remainder"))
        return _replace_allocations(db, transaction, parts, rule_id=rule.id)

    if action_type == "split_percent":
        parts = []
        allocated = Decimal("0")
        percentages = action.get("splits", [])
        total_percent = sum((parse_decimal(item["percent"]) for item in percentages), Decimal("0"))
        if total_percent > Decimal("100"):
            raise RuleError("Split percentages exceed 100%")
        for item in percentages:
            percent = parse_decimal(item["percent"])
            if percent <= 0:
                raise RuleError("Split percentages must be greater than zero")
            amount = (parent * percent / Decimal("100")).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
            allocated += amount
            parts.append((uuid.UUID(str(item["category_id"])), amount, str(item.get("memo", ""))[:300]))
        remainder = (parent - allocated).quantize(MONEY_QUANT)
        remainder_category = action.get("remainder_category_id")
        if remainder:
            if not remainder_category:
                raise RuleError("Percentage split leaves a remainder without a remainder category")
            parts.append((uuid.UUID(str(remainder_category)), remainder, "Remainder"))
        return _replace_allocations(db, transaction, parts, rule_id=rule.id)

    return False


def apply_rules_to_transaction(
    db: Session,
    transaction: BudgetTransaction,
    *,
    rules: list[Rule] | None = None,
) -> list[Rule]:
    if rules is None:
        rules = enabled_rules_for_workspace(db, transaction.workspace_id)

    matched: list[Rule] = []
    changed = False
    stopped_phases: set[str] = set()
    for rule in rules:
        if rule.phase in stopped_phases or not matches_tree(transaction, rule.conditions):
            continue
        matched.append(rule)
        rule_changed = False
        for action in rule.actions:
            action_type = str(action.get("type", ""))
            try:
                if action_type == "set_payee":
                    if not transaction.manual_payee_lock or rule.apply_to_manual_overrides:
                        value = str(action.get("value", "")).strip()[:500]
                        if value and value != transaction.payee:
                            transaction.payee = value
                            rule_changed = True
                elif action_type in {"assign_category", "split_fixed", "split_percent"}:
                    if not transaction.manual_allocation_lock or rule.apply_to_manual_overrides:
                        rule_changed = _allocation_action(db, transaction, rule, action) or rule_changed
                elif action_type == "add_note":
                    value = str(action.get("value", "")).strip()
                    if value and value not in transaction.note:
                        transaction.note = (transaction.note + "\n" + value).strip()
                        rule_changed = True
                elif action_type == "add_tag":
                    value = str(action.get("value", "")).strip()
                    if value and value not in transaction.tags:
                        transaction.tags = [*transaction.tags, value]
                        rule_changed = True
                elif action_type == "mark_review" and not transaction.needs_review:
                    transaction.needs_review = True
                    rule_changed = True
                elif action_type == "exclude" and not transaction.excluded:
                    transaction.excluded = True
                    rule_changed = True
                elif action_type == "suggest_transfer":
                    if "transfer-suggested" not in transaction.tags:
                        transaction.tags = [*transaction.tags, "transfer-suggested"]
                        transaction.needs_review = True
                        rule_changed = True
                elif action_type == "alert":
                    open_incident(
                        db,
                        workspace_id=transaction.workspace_id,
                        incident_key=f"rule:{rule.id}:transaction:{transaction.id}",
                        severity=str(action.get("severity", "warning")),
                        title=str(action.get("title", f"Rule matched: {rule.name}")),
                        message="A budgeting rule requested review. Open the application for transaction details.",
                    )
            except (KeyError, ValueError, RuleError) as exc:
                if not transaction.needs_review:
                    transaction.needs_review = True
                    rule_changed = True
                open_incident(
                    db,
                    workspace_id=transaction.workspace_id,
                    incident_key=f"rule-error:{rule.id}",
                    severity="warning",
                    title=f"Rule needs attention: {rule.name}",
                    message=f"The rule could not be applied: {str(exc)[:300]}",
                )
        changed = changed or rule_changed
        if rule.stop_processing:
            stopped_phases.add(rule.phase)

    if changed:
        transaction.version += 1
    return matched


def rule_snapshot(rule: Rule) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "enabled": rule.enabled,
        "phase": rule.phase,
        "priority": rule.priority,
        "conditions": rule.conditions,
        "actions": rule.actions,
        "apply_to_manual_overrides": rule.apply_to_manual_overrides,
        "stop_processing": rule.stop_processing,
        "version": rule.version,
    }
