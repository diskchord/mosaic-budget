from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_EXTRA_PAYEE_KEYS = (
    "merchant_name",
    "merchant",
    "payee_name",
    "payee",
    "counterparty_name",
    "counterparty",
    "recipient_name",
    "recipient",
)
_ACH_PREFIX = re.compile(r"^\s*ACH\s+(?:WITHDRAWAL|DEBIT|DEPOSIT|CREDIT)\b", re.IGNORECASE)
_ACH_LABEL = re.compile(
    r"(?<!\w)(?P<label>"
    r"ORIG(?:INATING)?\s+CO(?:MPANY)?(?:\s+NAME)?"
    r"|COMPANY\s+ID|CO\s+ID"
    r"|COMPANY(?:\s+NAME)?|CO(?:\s+NAME)?"
    r"|MERCHANT|PAYEE|RECIPIENT"
    r"|ENTRY(?:\s+DESCRIPTION)?|DES(?:CRIPTION)?"
    r"|IND(?:IVIDUAL)?(?:\s+NAME)?|NAME"
    r"|TRACE(?:\s+NUMBER)?|TYPE|SEC|ID"
    r")\s*:\s*",
    re.IGNORECASE,
)
_COMPANY_LABELS = {
    "ORIGCONAME",
    "ORIGCOMPANYNAME",
    "ORIGINATINGCONAME",
    "ORIGINATINGCOMPANYNAME",
    "COMPANYNAME",
    "COMPANY",
    "CONAME",
    "CO",
    "MERCHANT",
    "PAYEE",
    "RECIPIENT",
}
_GENERIC_CANDIDATE = re.compile(
    r"^(?:(?:ONLINE|EXTERNAL|INTERNAL)\s+)?(?:TRANSFER|PAYMENT|WITHDRAWAL|DEPOSIT|DEBIT|CREDIT)\b",
    re.IGNORECASE,
)


def _canonical_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def _label_key(value: str) -> str:
    return re.sub(r"[^A-Z]+", "", value.upper())


def _candidate(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", value).strip(" \t\r\n-–—:;,|")
    if not text or len(text) > 160 or not any(character.isalpha() for character in text):
        return None
    if _GENERIC_CANDIDATE.match(text):
        return None
    return text


def _extra_payee(extra: Mapping[str, Any] | None) -> str | None:
    if not extra:
        return None
    values = {_canonical_key(key): value for key, value in extra.items()}
    for key in _EXTRA_PAYEE_KEYS:
        found = _candidate(values.get(key))
        if found:
            return found
    return None


def _ach_fields(description: str) -> list[tuple[str, str]]:
    matches = list(_ACH_LABEL.finditer(description))
    fields: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(description)
        fields.append((_label_key(match.group("label")), description[match.end() : end]))
    return fields


def _first_field_candidate(fields: list[tuple[str, str]], labels: set[str]) -> str | None:
    for key, value in fields:
        if key in labels and (found := _candidate(value)):
            return found
    return None


def infer_simplefin_display_payee(description: str, extra: Mapping[str, Any] | None = None) -> str:
    """Return a conservative human-facing name while retaining the raw description elsewhere."""

    raw = description.strip()
    if not raw:
        return "Transaction"

    structured = _extra_payee(extra)
    if structured:
        return structured

    prefix = _ACH_PREFIX.match(raw)
    if not prefix:
        return raw

    fields = _ach_fields(raw)
    company: str | None = None
    for preferred in ("MERCHANT", "PAYEE", "RECIPIENT"):
        company = _first_field_candidate(fields, {preferred})
        if company:
            break
    if not company:
        company = _first_field_candidate(fields, _COMPANY_LABELS)

    # Some banks put the company immediately after "ACH Withdrawal" and before
    # the first labeled field. Use it only when it looks like a real name.
    if not company:
        first_label = _ACH_LABEL.search(raw, prefix.end())
        preamble_end = first_label.start() if first_label else len(raw)
        company = _candidate(raw[prefix.end() : preamble_end])

    if not company:
        return raw

    transaction_type = _first_field_candidate(fields, {"TYPE"})
    if transaction_type and re.sub(r"[^a-z0-9]+", "", transaction_type.casefold()) == "privacycom":
        without_wrapper = re.sub(r"^PWP(?:\s+|\s*[-:|]\s*)", "", company, count=1, flags=re.IGNORECASE)
        company = _candidate(without_wrapper) or company

    return company


def transaction_display_payee(
    payee: str,
    *,
    source_kind: str,
    imported_description: str,
    imported_extra: Mapping[str, Any] | None,
    manual_payee_lock: bool,
) -> str:
    """Choose the UI title without changing stored or rule-facing transaction values."""

    current = payee.strip()
    raw = imported_description.strip()
    if source_kind != "simplefin" or manual_payee_lock or not raw or current != raw:
        return current or raw or "Transaction"
    return infer_simplefin_display_payee(raw, imported_extra)
