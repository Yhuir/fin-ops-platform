from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from fin_ops_platform.domain.enums import TransactionDirection


class BankDetailsService:
    def __init__(self, import_service: Any) -> None:
        self._import_service = import_service

    def list_accounts(self, *, date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
        transactions = self._transactions()
        filtered_counts: dict[str, int] = {}
        accounts: dict[str, dict[str, Any]] = {}
        for transaction in transactions:
            row = self._transaction_payload(transaction)
            account = self._account_payload(row)
            accounts.setdefault(account["account_key"], account)
            if self._date_in_range(row.get("trade_time") or row.get("txn_date"), date_from=date_from, date_to=date_to):
                filtered_counts[account["account_key"]] = filtered_counts.get(account["account_key"], 0) + 1

        for account_key, account in accounts.items():
            account_transactions = [
                self._transaction_payload(transaction)
                for transaction in transactions
                if self._account_key(self._transaction_payload(transaction)) == account_key
            ]
            latest = self._latest_balance_transaction(account_transactions)
            if latest is None:
                account["latest_balance"] = None
                account["latest_balance_at"] = None
                account["has_balance"] = False
            else:
                account["latest_balance"] = self._format_decimal(latest.get("balance"))
                account["latest_balance_at"] = self._date_text(latest.get("trade_time") or latest.get("txn_date"))
                account["has_balance"] = True
            account["transaction_count"] = filtered_counts.get(account_key, 0)

        sorted_accounts = sorted(accounts.values(), key=lambda item: (item["bank_name"], item["account_last4"]))
        total_balance = sum(
            (Decimal(str(account["latest_balance"])) for account in sorted_accounts if account.get("has_balance")),
            Decimal("0.00"),
        )
        return {
            "accounts": sorted_accounts,
            "total_balance": self._format_decimal(total_balance) if any(account.get("has_balance") for account in sorted_accounts) else None,
            "balance_account_count": sum(1 for account in sorted_accounts if account.get("has_balance")),
            "missing_balance_account_count": sum(1 for account in sorted_accounts if not account.get("has_balance")),
        }

    def list_transactions(
        self,
        *,
        account_key: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 100), 1), 500)
        rows = []
        for transaction in self._transactions():
            payload = self._transaction_payload(transaction)
            if account_key and self._account_key(payload) != account_key:
                continue
            if not self._date_in_range(payload.get("trade_time") or payload.get("txn_date"), date_from=date_from, date_to=date_to):
                continue
            rows.append(self._row_payload(payload))
        rows.sort(key=lambda item: str(item.get("trade_time") or ""), reverse=True)
        total = len(rows)
        start = (normalized_page - 1) * normalized_page_size
        end = start + normalized_page_size
        return {
            "account_key": account_key,
            "date_from": date_from,
            "date_to": date_to,
            "rows": rows[start:end],
            "pagination": {
                "page": normalized_page,
                "page_size": normalized_page_size,
                "total": total,
            },
        }

    def _transactions(self) -> list[Any]:
        return list(self._import_service.list_transactions())

    def _transaction_payload(self, transaction: Any) -> dict[str, Any]:
        if is_dataclass(transaction):
            return asdict(transaction)
        return dict(transaction)

    def _account_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        bank_name = str(row.get("imported_bank_name") or row.get("bank_name") or "未知银行").strip() or "未知银行"
        account_last4 = str(row.get("imported_bank_last4") or row.get("account_last4") or "")[-4:] or str(row.get("account_no") or "")[-4:] or "unknown"
        account_key = self._account_key({**row, "imported_bank_name": bank_name, "imported_bank_last4": account_last4})
        return {
            "account_key": account_key,
            "bank_name": bank_name,
            "account_last4": account_last4,
            "display_name": f"{bank_name} {account_last4}",
            "latest_balance": None,
            "latest_balance_at": None,
            "has_balance": False,
            "transaction_count": 0,
        }

    def _account_key(self, row: dict[str, Any]) -> str:
        bank_name = str(row.get("imported_bank_name") or row.get("bank_name") or "未知银行").strip() or "未知银行"
        account_last4 = str(row.get("imported_bank_last4") or row.get("account_last4") or "")[-4:] or str(row.get("account_no") or "")[-4:] or "unknown"
        normalized_bank = bank_name.lower().replace(" ", "-")
        return f"{normalized_bank}:{account_last4}"

    def _latest_balance_transaction(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        with_balance = [row for row in rows if row.get("balance") not in (None, "", "—")]
        if not with_balance:
            return None
        return max(with_balance, key=lambda row: str(row.get("trade_time") or row.get("txn_date") or ""))

    def _row_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        direction = self._direction(row)
        account = self._account_payload(row)
        return {
            "id": str(row.get("id") or ""),
            "trade_time": self._date_text(row.get("trade_time") or row.get("txn_date")),
            "counterparty_name": str(row.get("counterparty_name_raw") or row.get("counterparty_name") or ""),
            "direction": direction,
            "direction_label": "收" if direction == "income" else "支",
            "amount": self._format_decimal(row.get("amount")),
            "balance": self._format_decimal(row.get("balance")) if row.get("balance") is not None else None,
            "summary": str(row.get("summary") or ""),
            "purpose": str(row.get("remark") or row.get("purpose") or ""),
            "bank_name": account["bank_name"],
            "account_last4": account["account_last4"],
        }

    @staticmethod
    def _direction(row: dict[str, Any]) -> str:
        direction = row.get("txn_direction")
        value = direction.value if isinstance(direction, TransactionDirection) else str(direction or "")
        return "income" if value == TransactionDirection.INFLOW.value else "expense"

    @staticmethod
    def _date_in_range(value: Any, *, date_from: str | None, date_to: str | None) -> bool:
        date_text = BankDetailsService._date_text(value)
        if date_from and date_text < date_from:
            return False
        if date_to and date_text > date_to:
            return False
        return True

    @staticmethod
    def _date_text(value: Any) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        text = str(value or "").strip()
        return text[:10]

    @staticmethod
    def _format_decimal(value: Any) -> str:
        return f"{Decimal(str(value)):.2f}"
