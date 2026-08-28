from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import Account, BudgetTransaction, Rule
from app.services.rules import _signed_amount, apply_rules_to_transaction, evaluate_condition, matches_tree


def transaction(*, amount: str = "-84.27", payee: str = "Hannaford #831") -> BudgetTransaction:
    workspace_id = uuid.uuid4()
    account = Account(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        source_type="simplefin",
        source_conn_id="bank",
        source_account_id="checking",
        name="Joint Checking",
        currency="USD",
        is_budget=True,
        is_active=True,
    )
    return BudgetTransaction(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        account_id=account.id,
        account=account,
        source_kind="simplefin",
        effective_date=date(2026, 8, 26),
        amount=Decimal(amount),
        payee=payee,
        imported_description="POS PURCHASE HANNAFORD #0831",
        imported_extra={},
        note="weekly shop",
        tags=["household"],
        pending=False,
        cleared=True,
        excluded=False,
        needs_review=False,
    )


def test_rule_matches_merchant_account_and_amount_range() -> None:
    item = transaction()
    tree = {
        "combinator": "all",
        "children": [
            {"field": "original_description", "operator": "contains", "value": "hannaford"},
            {"field": "account_id", "operator": "is", "value": str(item.account_id)},
            {"field": "outflow", "operator": "between", "value": ["1", "500"]},
        ],
    }
    assert matches_tree(item, tree)


def test_nested_any_and_none_groups_are_deterministic() -> None:
    item = transaction()
    assert matches_tree(
        item,
        {
            "combinator": "all",
            "children": [
                {
                    "combinator": "any",
                    "children": [
                        {"field": "payee", "operator": "starts_with", "value": "Hannaford"},
                        {"field": "payee", "operator": "is", "value": "Whole Foods"},
                    ],
                },
                {
                    "combinator": "none",
                    "children": [{"field": "pending", "operator": "is_true", "value": None}],
                },
            ],
        },
    )


def test_regex_timeout_or_invalid_pattern_fails_closed() -> None:
    item = transaction(payee="a" * 5000 + "!")
    assert not evaluate_condition(item, {"field": "payee", "operator": "regex", "value": "(a+)+$"})
    assert not evaluate_condition(item, {"field": "payee", "operator": "regex", "value": "["})


def test_signed_split_amount_follows_parent_direction() -> None:
    assert _signed_amount(Decimal("100"), Decimal("25")) == Decimal("25")
    assert _signed_amount(Decimal("-100"), Decimal("25")) == Decimal("-25")


def test_rule_action_error_marks_review_and_increments_version_once(monkeypatch) -> None:
    item = transaction()
    item.version = 7
    rule = Rule(
        id=uuid.uuid4(),
        workspace_id=item.workspace_id,
        name="Broken category rule",
        enabled=True,
        phase="categorize",
        priority=10,
        conditions={"field": "payee", "operator": "contains", "value": "Hannaford"},
        actions=[{"type": "assign_category", "category_id": "not-a-uuid"}],
        apply_to_manual_overrides=False,
        stop_processing=True,
    )
    incidents: list[dict] = []
    monkeypatch.setattr(
        "app.services.rules.open_incident",
        lambda _db, **kwargs: incidents.append(kwargs),
    )

    assert apply_rules_to_transaction(None, item, rules=[rule]) == [rule]
    assert item.needs_review is True
    assert item.version == 8
    assert len(incidents) == 1

    apply_rules_to_transaction(None, item, rules=[rule])
    assert item.version == 8
    assert len(incidents) == 2


class _Rows:
    def __init__(self, rows: list) -> None:
        self.rows = rows

    def all(self) -> list:
        return self.rows


def test_manual_rule_run_rejects_more_than_5000_candidates() -> None:
    from app.api.rules import MAX_MANUAL_RULE_TRANSACTIONS, run_rules
    from app.schemas import RuleRunRequest

    class CandidateDb:
        def scalars(self, _query) -> _Rows:
            return _Rows([uuid.uuid4()] * (MAX_MANUAL_RULE_TRANSACTIONS + 1))

    auth = SimpleNamespace(user=SimpleNamespace(workspace_id=uuid.uuid4(), id=uuid.uuid4()))
    with pytest.raises(HTTPException) as raised:
        run_rules(RuleRunRequest(month="2026-08"), auth, CandidateDb())
    assert raised.value.status_code == 400
    assert "5,000 unsorted transactions" in str(raised.value.detail)


def test_manual_rule_run_locks_and_rechecks_each_candidate() -> None:
    from app.api.rules import run_rules
    from app.schemas import RuleRunRequest

    class CandidateDb:
        def __init__(self) -> None:
            self.scalars_calls = 0
            self.locked_query = None
            self.committed = False

        def scalars(self, _query) -> _Rows:
            self.scalars_calls += 1
            return _Rows([uuid.uuid4()] if self.scalars_calls == 1 else [])

        def scalar(self, query):
            self.locked_query = query
            return None

        def add(self, _row) -> None:
            pass

        def flush(self) -> None:
            pass

        def commit(self) -> None:
            self.committed = True

    db = CandidateDb()
    workspace_id = uuid.uuid4()
    auth = SimpleNamespace(user=SimpleNamespace(workspace_id=workspace_id, id=uuid.uuid4()))
    result = run_rules(RuleRunRequest(month="2026-08"), auth, db)

    assert result["transactions_scanned"] == 0
    assert db.locked_query is not None
    assert db.locked_query._for_update_arg is not None
    sql = str(db.locked_query)
    assert "budget_transactions.workspace_id" in sql
    assert "budget_transactions.effective_date" in sql
    assert "budget_transactions.deleted_at IS NULL" in sql
    assert "budget_transactions.excluded IS false" in sql
    assert "budget_transactions.suppressed_by_duplicate_account IS false" in sql
    assert "accounts.is_duplicate IS false" in sql
    assert "allocations.transaction_id" in sql
    assert db.committed is True


def test_rule_split_validation_rejects_duplicate_categories() -> None:
    from fastapi import HTTPException
    from app.api.rules import _category_ids_from_actions

    category_id = str(uuid.uuid4())
    try:
        _category_ids_from_actions([
            {
                "type": "split_percent",
                "splits": [
                    {"category_id": category_id, "percent": "50"},
                    {"category_id": category_id, "percent": "50"},
                ],
            }
        ])
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "same category" in str(exc.detail)
    else:
        raise AssertionError("duplicate categories should be rejected")


def test_rule_split_validation_requires_positive_percentages_and_remainder() -> None:
    from fastapi import HTTPException
    from app.api.rules import _category_ids_from_actions

    for action in (
        {
            "type": "split_percent",
            "splits": [{"category_id": str(uuid.uuid4()), "percent": "0"}],
        },
        {
            "type": "split_percent",
            "splits": [{"category_id": str(uuid.uuid4()), "percent": "75"}],
        },
    ):
        try:
            _category_ids_from_actions([action])
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("unsafe percentage split should be rejected")
