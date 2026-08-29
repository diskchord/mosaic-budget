from __future__ import annotations

import pytest

from app.services.transaction_labels import infer_simplefin_display_payee, transaction_display_payee


PHILO_DESCRIPTION = (
    "ACH Withdrawal PwP PHILO TV TYPE: Privacycom "
    "CO: PwP PHILO TV NAME: Alexander Peppe"
)


def test_privacy_ach_company_is_promoted_without_the_payment_wrapper() -> None:
    assert infer_simplefin_display_payee(PHILO_DESCRIPTION) == "PHILO TV"


@pytest.mark.parametrize(
    ("description", "extra", "expected"),
    [
        ("Uncle Frank's Bait Shop", {}, "Uncle Frank's Bait Shop"),
        ("ACH Debit TYPE: WEB CO: Café José NAME: Account Owner", {}, "Café José"),
        ("ACH Debit TYPE: CCD CO: PwP PHILO TV NAME: Account Owner", {}, "PwP PHILO TV"),
        ("ACH Withdrawal TYPE: WEB NAME: Account Owner", {}, "ACH Withdrawal TYPE: WEB NAME: Account Owner"),
        ("CARD PURCHASE LONG BANK TEXT", {"merchant_name": "Philo"}, "Philo"),
        ("CARD PURCHASE LONG BANK TEXT", {"name": "Account Owner"}, "CARD PURCHASE LONG BANK TEXT"),
        ("ACH Withdrawal 8675309 TYPE: WEB NAME: Account Owner", {}, "ACH Withdrawal 8675309 TYPE: WEB NAME: Account Owner"),
    ],
)
def test_display_payee_is_conservative(description: str, extra: dict, expected: str) -> None:
    assert infer_simplefin_display_payee(description, extra) == expected


def test_existing_effective_payees_take_precedence_over_inference() -> None:
    common = {
        "source_kind": "simplefin",
        "imported_description": PHILO_DESCRIPTION,
        "imported_extra": {},
    }
    assert transaction_display_payee(PHILO_DESCRIPTION, manual_payee_lock=False, **common) == "PHILO TV"
    assert transaction_display_payee("Philo Family", manual_payee_lock=False, **common) == "Philo Family"
    assert transaction_display_payee(PHILO_DESCRIPTION, manual_payee_lock=True, **common) == PHILO_DESCRIPTION
    assert transaction_display_payee(
        "Cash purchase",
        source_kind="manual",
        imported_description="",
        imported_extra={},
        manual_payee_lock=True,
    ) == "Cash purchase"
