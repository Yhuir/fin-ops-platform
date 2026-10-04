"""Pure normalization and version helpers for canonical bank settings."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from fin_ops_platform.services.bank_account_resolver import BankAccountResolver


def bank_short_names_from_mappings(mappings: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    """Use only an unambiguous configured name for the exact bank and account suffix."""
    names: dict[tuple[str, str], set[str]] = {}
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        bank_name = str(mapping.get("bank_name") or "").strip()
        last4 = mapping.get("last4")
        if not bank_name or not isinstance(last4, str) or len(last4) != 4 or not last4.isdigit():
            continue
        names.setdefault((bank_name, last4), set()).add(str(mapping.get("short_name") or "").strip())
    return {key: next(iter(values)) for key, values in names.items() if len(values) == 1}


def bank_summary_with_short_names(
    bank: dict[str, Any], names: dict[tuple[str, str], str],
) -> dict[str, Any]:
    """Add display names without changing source names, suffixes, or account labels."""
    result = {
        **bank,
        "bankShortName": names.get((str(bank.get("bankName") or "").strip(), bank.get("accountLast4")), ""),
    }
    if "summaries" in bank:
        result["summaries"] = [bank_summary_with_short_names(item, names) for item in bank["summaries"]]
    return result


def bank_account_display_labels_from_settings(settings: dict[str, Any]) -> dict[str, str]:
    """Map the existing account-label formats to explicitly configured short names."""
    names = bank_short_names_from_mappings(settings.get("bank_account_mappings") or [])
    labels: dict[str, str] = {}
    resolver = BankAccountResolver()
    for (bank_name, last4), short_name in names.items():
        if not short_name:
            continue
        display_label = f"{short_name} {last4}"
        labels[f"{bank_name} {last4}"] = display_label
        for account_name in (None, "基本", "一般", "专户"):
            label = resolver.resolve_label(
                None, account_name, preferred_bank_name=bank_name, preferred_last4=last4,
            )
            labels[label] = display_label
    return labels


def bank_accounts_from_settings_payload(settings_payload: dict[str, Any]) -> list[dict[str, str]]:
    accounts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    mappings = settings_payload.get("bank_account_mappings") if isinstance(settings_payload, dict) else []
    for item in list(mappings or []):
        if not isinstance(item, dict):
            continue
        bank_name = str(item.get("bank_name") or item.get("bankName") or "").strip()
        last4 = str(item.get("last4") or "").strip()
        if not bank_name or len(last4) != 4 or not last4.isdigit():
            continue
        key = (bank_name, last4)
        if key in seen:
            continue
        seen.add(key)
        accounts.append(
            {
                "bank_name": bank_name,
                "account_last4": last4,
                "payment_account_label": f"{bank_name} 账户 {last4}",
                "source": "settings",
            }
        )
    return sorted(accounts, key=lambda item: (item["bank_name"], item["account_last4"]))


def bank_account_mappings_fingerprint_from_settings_payload(settings_payload: dict[str, Any]) -> str:
    return bank_account_mappings_fingerprint(bank_accounts_from_settings_payload(settings_payload))


def bank_auto_tag_rules_version_from_settings_payload(settings_payload: dict[str, Any]) -> int:
    rules_payload = settings_payload.get("bank_transaction_tags") if isinstance(settings_payload, dict) else {}
    if not isinstance(rules_payload, dict):
        return 1
    try:
        return int(rules_payload.get("version") or 1)
    except (TypeError, ValueError):
        return 1


def bank_account_mappings_fingerprint(accounts: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "bank_name": str(account.get("bank_name") or "").strip(),
            "account_last4": str(account.get("account_last4") or "").strip(),
            "payment_account_label": str(account.get("payment_account_label") or "").strip(),
        }
        for account in list(accounts or [])
        if str(account.get("bank_name") or "").strip() and str(account.get("account_last4") or "").strip()
    ]
    normalized.sort(key=lambda item: (item["bank_name"], item["account_last4"], item["payment_account_label"]))
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]
