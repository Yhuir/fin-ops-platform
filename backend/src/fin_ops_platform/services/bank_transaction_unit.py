from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fin_ops_platform.domain.models import BankTransaction


@dataclass(slots=True)
class BankTransactionUnit(BankTransaction):
    """Purpose read projection; never used as an imported financial fact."""

    parent_transaction: BankTransaction | None = None
    bank_split_parts: list[dict[str, Any]] = field(default_factory=list)
    bank_split_version: int = 0
    turnover_role: str | None = None
    split_category_code: str | None = None
    is_split: bool = True


def bank_unit_matches_invoice(bank: BankTransaction) -> bool:
    return not isinstance(bank, BankTransactionUnit) or bank.turnover_role != "external_turnover"


def original_bank_transaction(bank: BankTransaction) -> BankTransaction:
    if isinstance(bank, BankTransactionUnit) and bank.parent_transaction is not None:
        return bank.parent_transaction
    return bank


def bank_unit_display(bank: BankTransaction) -> dict[str, Any]:
    if not isinstance(bank, BankTransactionUnit):
        return {}
    parent = original_bank_transaction(bank)
    return {"parent_row_id": parent.id, "parent_amount": f"{parent.amount:.2f}",
            "bank_split_parts": bank.bank_split_parts, "bank_split_version": bank.bank_split_version}


def original_bank_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if not summary.get("bank_split_parts"):
        return summary
    amount = summary["parent_amount"]
    return {**summary, "bankTransactionId": summary["parent_row_id"], "amount": amount,
            "debitAmount": amount if summary["direction"] == "outflow" else "0.00",
            "creditAmount": amount if summary["direction"] == "inflow" else "0.00"}


def original_bank_summaries(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        parent = original_bank_summary(summary)
        unique.setdefault(parent["bankTransactionId"], parent)
    return list(unique.values())
