from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class WorkbenchAmountCheckService:
    def summarize(self, rows_by_type: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        normalized_rows = {
            "oa": list(rows_by_type.get("oa") or []),
            "bank": list(rows_by_type.get("bank") or []),
            "invoice": list(rows_by_type.get("invoice") or []),
        }
        oa_total = self._sum_amounts(normalized_rows["oa"]) or ZERO
        bank_expense_rows: list[dict[str, Any]] = []
        bank_income_rows: list[dict[str, Any]] = []
        input_invoice_rows: list[dict[str, Any]] = []
        output_invoice_rows: list[dict[str, Any]] = []
        unknown_direction_row_ids: list[str] = []

        for row in normalized_rows["bank"]:
            direction = self._bank_direction(row)
            if direction == "expense":
                bank_expense_rows.append(row)
            elif direction == "income":
                bank_income_rows.append(row)
            else:
                unknown_direction_row_ids.append(self._row_id(row))

        for row in normalized_rows["invoice"]:
            direction = self._invoice_direction(row)
            if direction == "input":
                input_invoice_rows.append(row)
            elif direction == "output":
                output_invoice_rows.append(row)
            else:
                unknown_direction_row_ids.append(self._row_id(row))

        bank_expense_total = self._sum_amounts(bank_expense_rows) or ZERO
        bank_income_total = self._sum_amounts(bank_income_rows) or ZERO
        input_invoice_total = self._sum_amounts(input_invoice_rows) or ZERO
        output_invoice_total = self._sum_amounts(output_invoice_rows) or ZERO
        has_unknown_direction = bool(unknown_direction_row_ids)

        expense_relation = (
            "unknown_direction"
            if has_unknown_direction
            else self._expense_relation(
                has_oa=bool(normalized_rows["oa"]),
                has_bank=bool(bank_expense_rows),
                has_invoice=bool(input_invoice_rows),
                oa_total=oa_total,
                bank_total=bank_expense_total,
                invoice_total=input_invoice_total,
            )
        )
        income_relation = (
            "unknown_direction"
            if has_unknown_direction
            else self._income_relation(
                has_bank=bool(bank_income_rows),
                has_invoice=bool(output_invoice_rows),
                bank_total=bank_income_total,
                invoice_total=output_invoice_total,
            )
        )

        return {
            "oa_total": self._format_amount(oa_total),
            "bank_expense_total": self._format_amount(bank_expense_total),
            "bank_income_total": self._format_amount(bank_income_total),
            "input_invoice_total": self._format_amount(input_invoice_total),
            "output_invoice_total": self._format_amount(output_invoice_total),
            "expense_relation": expense_relation,
            "income_relation": income_relation,
            "has_unknown_direction": has_unknown_direction,
            "unknown_direction_row_ids": unknown_direction_row_ids,
        }

    def check(self, rows_by_type: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        normalized_rows = {
            "oa": list(rows_by_type.get("oa") or []),
            "bank": list(rows_by_type.get("bank") or []),
            "invoice": list(rows_by_type.get("invoice") or []),
        }
        totals = {
            "oa_total": self._sum_amounts(normalized_rows["oa"]),
            "bank_total": self._sum_amounts(normalized_rows["bank"]),
            "invoice_total": self._sum_amounts(normalized_rows["invoice"]),
        }
        directions = self._directions(normalized_rows)
        direction = next(iter(directions)) if len(directions) == 1 else "unknown"
        has_direction_gap = any(
            self._row_direction(row) is None
            for rows in normalized_rows.values()
            for row in rows
        )
        comparable = {key: value for key, value in totals.items() if value is not None}
        mismatch_fields: list[str] = []
        status = "matched"
        requires_note = False

        if direction == "unknown" and (has_direction_gap or not directions):
            status = "unknown"
            requires_note = True
        elif direction != "unknown" and len(comparable) >= 2:
            mismatch_fields = self._mismatch_fields_for_totals(comparable)
            if mismatch_fields:
                status = "mismatch"
                requires_note = True

        return {
            "status": status,
            "direction": direction,
            "oa_total": self._format_amount(totals["oa_total"]),
            "bank_total": self._format_amount(totals["bank_total"]),
            "invoice_total": self._format_amount(totals["invoice_total"]),
            "mismatch_fields": mismatch_fields,
            "requires_note": requires_note,
        }

    def _mismatch_fields_for_totals(self, comparable: dict[str, Decimal]) -> list[str]:
        if len(comparable) < 2:
            return []

        amount_groups: dict[Decimal, list[str]] = {}
        for key, value in comparable.items():
            amount_groups.setdefault(value, []).append(key)

        if len(amount_groups) == 1:
            return []

        if len(comparable) == 2:
            return list(comparable.keys())

        isolated_groups = [fields for fields in amount_groups.values() if len(fields) == 1]
        if len(isolated_groups) == 1:
            return isolated_groups[0]

        return list(comparable.keys())

    def _sum_amounts(self, rows: list[dict[str, Any]]) -> Decimal | None:
        amounts = [amount for amount in (self._amount(row) for row in rows) if amount is not None]
        if not amounts:
            return None
        return sum(amounts, ZERO).quantize(CENT)

    def _directions(self, rows_by_type: dict[str, list[dict[str, Any]]]) -> set[str]:
        return {
            direction
            for rows in rows_by_type.values()
            for direction in (self._row_direction(row) for row in rows)
            if direction is not None
        }

    def _row_direction(self, row: dict[str, Any]) -> str | None:
        row_type = str(row.get("type", ""))
        if row_type == "oa":
            apply_type = str(row.get("apply_type") or "")
            return "receipt" if ("收" in apply_type and "付" not in apply_type) else "payment"
        if row_type == "bank":
            debit_amount = self._decimal(row.get("debit_amount"))
            credit_amount = self._decimal(row.get("credit_amount"))
            if debit_amount is not None and debit_amount > ZERO:
                return "payment"
            if credit_amount is not None and credit_amount > ZERO:
                return "receipt"
            txn_direction = str(row.get("txn_direction") or "").lower()
            if txn_direction in {"outflow", "expense", "payment"}:
                return "payment"
            if txn_direction in {"inflow", "income", "receipt"}:
                return "receipt"
            return None
        if row_type == "invoice":
            invoice_type = str(row.get("invoice_type") or "")
            return "receipt" if "销" in invoice_type or invoice_type == "output" else "payment"
        return None

    def _bank_direction(self, row: dict[str, Any]) -> str | None:
        debit_amount = self._decimal(row.get("debit_amount"))
        credit_amount = self._decimal(row.get("credit_amount"))
        if debit_amount is not None and debit_amount > ZERO:
            return "expense"
        if credit_amount is not None and credit_amount > ZERO:
            return "income"
        txn_direction = str(row.get("txn_direction") or row.get("direction") or "").lower()
        if txn_direction in {"outflow", "expense", "payment", "pay", "支出", "付款"}:
            return "expense"
        if txn_direction in {"inflow", "income", "receipt", "receive", "收入", "收款"}:
            return "income"
        return None

    def _invoice_direction(self, row: dict[str, Any]) -> str | None:
        invoice_direction = str(row.get("invoice_direction") or "").lower()
        invoice_type = str(row.get("invoice_type") or "").lower()
        combined = f"{invoice_direction} {invoice_type}"
        if invoice_direction in {"input", "expense"} or "input" in invoice_type or "进项" in combined:
            return "input"
        if invoice_direction in {"output", "income"} or "output" in invoice_type or "销项" in combined:
            return "output"
        return None

    def _expense_relation(
        self,
        *,
        has_oa: bool,
        has_bank: bool,
        has_invoice: bool,
        oa_total: Decimal,
        bank_total: Decimal,
        invoice_total: Decimal,
    ) -> str:
        if has_oa and has_bank and has_invoice:
            if oa_total == bank_total == invoice_total:
                return "all_equal"
            if oa_total == bank_total:
                return (
                    "oa_equals_bank_greater_than_input_invoice"
                    if oa_total > invoice_total
                    else "oa_equals_bank_less_than_input_invoice"
                )
            if oa_total == invoice_total:
                return (
                    "oa_equals_input_invoice_greater_than_bank"
                    if oa_total > bank_total
                    else "oa_equals_input_invoice_less_than_bank"
                )
            if bank_total == invoice_total:
                return (
                    "bank_equals_input_invoice_greater_than_oa"
                    if bank_total > oa_total
                    else "bank_equals_input_invoice_less_than_oa"
                )
            return "all_different"
        if has_oa and has_bank:
            if oa_total == bank_total:
                return "oa_equals_bank_missing_input_invoice"
            return "oa_greater_than_bank_missing_input_invoice" if oa_total > bank_total else "oa_less_than_bank_missing_input_invoice"
        if has_oa and has_invoice:
            if oa_total == invoice_total:
                return "oa_equals_input_invoice_missing_bank"
            return "oa_greater_than_input_invoice_missing_bank" if oa_total > invoice_total else "oa_less_than_input_invoice_missing_bank"
        if has_bank and has_invoice:
            if bank_total == invoice_total:
                return "bank_equals_input_invoice_missing_oa"
            return "bank_greater_than_input_invoice_missing_oa" if bank_total > invoice_total else "bank_less_than_input_invoice_missing_oa"
        if has_oa:
            return "only_oa"
        if has_bank:
            return "only_bank_expense"
        if has_invoice:
            return "only_input_invoice"
        return "not_applicable"

    def _income_relation(
        self,
        *,
        has_bank: bool,
        has_invoice: bool,
        bank_total: Decimal,
        invoice_total: Decimal,
    ) -> str:
        if has_bank and has_invoice:
            if bank_total == invoice_total:
                return "income_equals_invoice"
            return "income_greater_than_invoice" if bank_total > invoice_total else "income_less_than_invoice"
        if has_bank:
            return "only_income_bank"
        if has_invoice:
            return "only_output_invoice"
        return "not_applicable"

    def _amount(self, row: dict[str, Any]) -> Decimal | None:
        row_type = str(row.get("type", ""))
        if row_type == "bank":
            debit_amount = self._decimal(row.get("debit_amount"))
            if debit_amount is not None and debit_amount > ZERO:
                return debit_amount
            return self._decimal(row.get("credit_amount") or row.get("amount"))
        if row_type == "invoice":
            return self._decimal(row.get("total_with_tax") or row.get("amount"))
        return self._decimal(
            row.get("amount")
            or row.get("reimbursement_amount")
            or row.get("payment_amount")
            or row.get("apply_amount")
        )

    @staticmethod
    def _format_amount(value: Decimal | None) -> str | None:
        if value is None:
            return None
        return f"{value.quantize(CENT):.2f}"

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("row_id") or "")

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value in (None, "", "--", "—"):
            return None
        try:
            return Decimal(str(value).replace(",", "")).quantize(CENT)
        except (InvalidOperation, ValueError):
            return None
