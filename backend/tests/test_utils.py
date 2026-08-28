from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.utils import exponential_backoff, normalize_description, parse_decimal, stable_hash


def test_decimal_amounts_are_exact_to_four_places() -> None:
    assert parse_decimal("12.34567") == Decimal("12.3457")
    assert parse_decimal("-0.005") == Decimal("-0.0050")
    assert parse_decimal(10) == Decimal("10.0000")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "not money", None])
def test_decimal_rejects_invalid_or_nonfinite_values(value: object) -> None:
    with pytest.raises(ValueError):
        parse_decimal(value)


def test_stable_hash_ignores_dictionary_order() -> None:
    assert stable_hash({"a": 1, "b": [2, 3]}) == stable_hash({"b": [2, 3], "a": 1})


def test_description_normalization_removes_card_noise() -> None:
    assert normalize_description("PENDING Visa Purchase: HANNAFORD #0831") == "hannaford 0831"


def test_notification_backoff_is_bounded() -> None:
    assert exponential_backoff(1) == timedelta(seconds=30)
    assert exponential_backoff(3) == timedelta(minutes=2)
    assert exponential_backoff(99) == timedelta(hours=6)
