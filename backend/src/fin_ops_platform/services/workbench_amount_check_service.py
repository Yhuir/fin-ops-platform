from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class WorkbenchAmountCheckService:
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
            "oa_total": totals["oa_total"],
            "bank_total": totals["bank_total"],
            "invoice_total": totals["invoice_total"],
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
    def _decimal(value: Any) -> Decimal | None:
        if value in (None, "", "--", "—"):
            return None
        try:
            return Decimal(str(value).replace(",", "")).quantize(CENT)
        except (InvalidOperation, ValueError):
            return None
