from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.workbench_invoice_direction import invoice_flow_direction_from_row, normalize_invoice_kind_from_row


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
        direction, has_direction_conflict = self._check_direction(normalized_rows)
        totals = {
            "oa_total": self._sum_amounts(normalized_rows["oa"]),
            "bank_total": self._pane_total_for_direction(normalized_rows["bank"], direction),
            "invoice_total": self._pane_total_for_direction(normalized_rows["invoice"], direction),
        }
        directions = self._directions(normalized_rows)
        has_direction_gap = any(
            self._row_direction(row) is None
            for rows in normalized_rows.values()
            for row in rows
        )
        comparable = {key: value for key, value in totals.items() if value is not None}
        mismatch_fields: list[str] = []
        status = "matched"
        requires_note = False

        if has_direction_gap or has_direction_conflict or (direction == "unknown" and not directions):
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
            "oa_amount": self._format_amount(totals["oa_total"]),
            "bank_amount": self._format_amount(totals["bank_total"]),
            "amount_delta": self._format_amount(self._amount_delta(comparable)),
            "mismatch_fields": mismatch_fields,
            "requires_note": requires_note,
        }

    def _check_direction(self, rows_by_type: dict[str, list[dict[str, Any]]]) -> tuple[str, bool]:
        non_bank_directions = {
            direction
            for row_type in ("oa", "invoice")
            for row in rows_by_type.get(row_type, [])
            for direction in (self._row_direction(row),)
            if direction is not None
        }
        if len(non_bank_directions) == 1:
            return next(iter(non_bank_directions)), False
        if len(non_bank_directions) > 1:
            return "unknown", True

        directions = self._directions(rows_by_type)
        if len(directions) == 1:
            return next(iter(directions)), False
        return "unknown", False

    def _pane_total_for_direction(self, rows: list[dict[str, Any]], direction: str) -> Decimal | None:
        if direction not in {"payment", "receipt"}:
            return self._sum_amounts(rows)
        matching_rows = [row for row in rows if self._row_direction(row) == direction]
        if matching_rows:
            return self._sum_amounts(matching_rows)
        known_direction_rows = [row for row in rows if self._row_direction(row) is not None]
        if known_direction_rows:
            return ZERO
        return self._sum_amounts(rows)

    def _amount_delta(self, comparable: dict[str, Decimal]) -> Decimal | None:
        if len(comparable) < 2:
            return None
        values = list(comparable.values())
        return (max(values) - min(values)).quantize(CENT)

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
            direction = invoice_flow_direction_from_row(row)
            if direction == "inflow":
                return "receipt"
            if direction == "outflow":
                return "payment"
            return None
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
        invoice_kind = normalize_invoice_kind_from_row(row)
        if invoice_direction in {"input", "expense"} or invoice_kind == "input":
            return "input"
        if invoice_direction in {"output", "income"} or invoice_kind == "output":
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
        if row_type == "oa":
            reconciliation_amount = self._oa_reconciliation_amount(row)
            if reconciliation_amount is not None:
                return reconciliation_amount
        return self._decimal(
            row.get("amount")
            or row.get("reimbursement_amount")
            or row.get("payment_amount")
            or row.get("apply_amount")
        )

    def _oa_reconciliation_amount(self, row: dict[str, Any]) -> Decimal | None:
        explicit_amount = self._decimal(row.get("reconciliation_amount"))
        if explicit_amount is not None:
            return explicit_amount

        detail_fields = row.get("detail_fields") or row.get("_detail_fields")
        if not isinstance(detail_fields, dict):
            return None
        amount_source = str(row.get("amount_source") or detail_fields.get("金额来源") or "").strip()
        if amount_source not in {"header", "主表总金额"}:
            return None
        if "金额差异" not in detail_fields and not isinstance(row.get("amount_mismatch"), dict):
            return None
        detail_sum = self._decimal(detail_fields.get("明细金额合计"))
        if detail_sum is None:
            return None
        return detail_sum

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
