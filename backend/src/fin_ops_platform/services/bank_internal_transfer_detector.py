from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.import_file_service import is_company_identity


INTERNAL_TRANSFER_MATCH_WINDOW = timedelta(hours=48)
INTERNAL_TRANSFER_RULE_CODE = "internal_transfer_pair"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class BankInternalTransferDetector:
    def detect(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        candidates = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
        by_amount: dict[str, list[dict[str, Any]]] = {}
        for row in candidates:
            if not self._row_id(row) or not self._is_company_bank_row(row):
                continue
            amount = self._amount(row)
            if amount is None or amount <= ZERO:
                continue
            direction = self._direction(row)
            row_time = self._row_time(row)
            account_key = self._account_key(row)
            if direction not in {"inflow", "outflow"} or row_time is None or not account_key:
                continue
            by_amount.setdefault(self._format_amount(amount), []).append(row)

        suggestions: dict[str, dict[str, Any]] = {}
        for amount_text, group_rows in by_amount.items():
            suggestions.update(self._detect_amount_group(amount_text, group_rows))
        return suggestions

    def _detect_amount_group(self, amount_text: str, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        outflows = [row for row in rows if self._direction(row) == "outflow"]
        inflows = [row for row in rows if self._direction(row) == "inflow"]
        if not outflows or not inflows:
            return {}

        candidates: list[tuple[str, str, int, dict[str, Any], dict[str, Any]]] = []
        degrees: dict[str, int] = {}
        for outflow in outflows:
            outflow_id = self._row_id(outflow)
            outflow_time = self._row_time(outflow)
            if outflow_time is None:
                continue
            for inflow in inflows:
                inflow_id = self._row_id(inflow)
                if not self._accounts_are_distinct(outflow, inflow):
                    continue
                inflow_time = self._row_time(inflow)
                if inflow_time is None:
                    continue
                delta = abs(inflow_time - outflow_time)
                if delta > INTERNAL_TRANSFER_MATCH_WINDOW:
                    continue
                degrees[outflow_id] = degrees.get(outflow_id, 0) + 1
                degrees[inflow_id] = degrees.get(inflow_id, 0) + 1
                candidates.append((outflow_id, inflow_id, int(delta.total_seconds()), outflow, inflow))

        if not candidates:
            return {}
        if any(count > 1 for count in degrees.values()):
            return {}

        suggestions: dict[str, dict[str, Any]] = {}
        for outflow_id, inflow_id, delta_seconds, outflow, inflow in candidates:
            suggestions[outflow_id] = self._suggestion(
                transaction_id=outflow_id,
                counterpart_id=inflow_id,
                amount_text=amount_text,
                delta_seconds=delta_seconds,
                account_key=self._account_key(outflow),
                counterpart_account_key=self._account_key(inflow),
            )
            suggestions[inflow_id] = self._suggestion(
                transaction_id=inflow_id,
                counterpart_id=outflow_id,
                amount_text=amount_text,
                delta_seconds=delta_seconds,
                account_key=self._account_key(inflow),
                counterpart_account_key=self._account_key(outflow),
            )
        return suggestions

    @staticmethod
    def _suggestion(
        *,
        transaction_id: str,
        counterpart_id: str,
        amount_text: str,
        delta_seconds: int,
        account_key: str,
        counterpart_account_key: str,
    ) -> dict[str, Any]:
        return {
            "transaction_id": transaction_id,
            "category_code": "internal_transfer",
            "category_label": "内部往来款",
            "category_path": ["自动识别", "内部往来款"],
            "source": "auto",
            "rule_code": INTERNAL_TRANSFER_RULE_CODE,
            "reason": (
                f"内部往来配对：金额 {amount_text}，对方流水 {counterpart_id}，"
                f"账户 {account_key} -> {counterpart_account_key}，时间差 {delta_seconds} 秒"
            ),
            "confidence": "high",
            "rule_version": "2026-05-bank-auto-category-internal-transfer-v1",
        }

    @classmethod
    def _is_company_bank_row(cls, row: dict[str, Any]) -> bool:
        return bool(cls._account_key(row)) and is_company_identity(None, str(row.get("counterparty_name") or ""))

    @classmethod
    def _accounts_are_distinct(cls, left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_key = cls._account_key(left)
        right_key = cls._account_key(right)
        return bool(left_key and right_key and left_key != right_key)

    @classmethod
    def _account_key(cls, row: dict[str, Any]) -> str:
        for field_name in ("account_no", "account_number"):
            value = row.get(field_name)
            if value not in (None, "", "--", "—"):
                normalized = cls._clean_account_no(value)
                if len(normalized) > 4:
                    return normalized
        bank_name = row.get("imported_bank_name") or row.get("bank_name")
        last4 = row.get("imported_bank_last4") or row.get("account_last4")
        if bank_name not in (None, "", "--", "—") and last4 not in (None, "", "--", "—"):
            return f"{str(bank_name).strip()}:{str(last4).strip()[-4:]}"
        account_key = row.get("account_key")
        if account_key not in (None, "", "--", "—"):
            return str(account_key).strip()
        return ""

    @staticmethod
    def _clean_account_no(value: Any) -> str:
        return "".join(char for char in str(value or "").strip() if char.isalnum())

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()

    @classmethod
    def _direction(cls, row: dict[str, Any]) -> str:
        raw = str(row.get("txn_direction") or row.get("direction") or "").strip().lower()
        if raw in {"income", "credit", "inflow", "收入", "收"}:
            return "inflow"
        if raw in {"expense", "debit", "outflow", "支出", "支"}:
            return "outflow"
        debit = cls._decimal(row.get("debit_amount"))
        if debit is not None and debit > ZERO:
            return "outflow"
        credit = cls._decimal(row.get("credit_amount"))
        if credit is not None and credit > ZERO:
            return "inflow"
        signed = cls._decimal(row.get("signed_amount"))
        if signed is not None:
            return "inflow" if signed > ZERO else "outflow"
        return ""

    @classmethod
    def _amount(cls, row: dict[str, Any]) -> Decimal | None:
        debit = cls._decimal(row.get("debit_amount"))
        if debit is not None and debit > ZERO:
            return debit
        credit = cls._decimal(row.get("credit_amount"))
        if credit is not None and credit > ZERO:
            return credit
        amount = cls._decimal(row.get("amount"))
        if amount is not None:
            return abs(amount)
        signed = cls._decimal(row.get("signed_amount"))
        return abs(signed) if signed is not None else None

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value in (None, "", "--", "—"):
            return None
        try:
            return Decimal(str(value).replace(",", "")).quantize(CENT)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _format_amount(value: Decimal) -> str:
        return f"{value.quantize(CENT):.2f}"

    @staticmethod
    def _row_time(row: dict[str, Any]) -> datetime | None:
        for field_name in ("pay_receive_time", "trade_time", "transaction_at", "txn_date", "posted_at"):
            value = row.get(field_name)
            if value in (None, "", "--", "—"):
                continue
            text = str(value).strip().replace("/", "-")
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                pass
            for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text[:19] if "%S" in pattern else text[:16 if "%H" in pattern else 10], pattern)
                except ValueError:
                    continue
        return None
