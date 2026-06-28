from __future__ import annotations

from decimal import Decimal
from typing import Any


class CostStatisticsQueryService:
    def __init__(
        self,
        *,
        cost_statistics_service: Any,
        runtime_service: Any,
    ) -> None:
        self._cost_statistics_service = cost_statistics_service
        self._runtime_service = runtime_service

    def get_month_statistics(self, month: str, project_scope: str) -> tuple[dict[str, Any], bool]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        payload = self._cost_statistics_service.get_month_statistics(
            month,
            project_scope=normalized_project_scope,
        )
        return payload, False

    def get_explorer(self, month: str, project_scope: str) -> tuple[dict[str, Any], bool]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        payload = self._cost_statistics_service.get_explorer(
            month,
            project_scope=normalized_project_scope,
        )
        return payload, False

    @staticmethod
    def month_payload_from_explorer_payload(
        month: str,
        explorer_payload: dict[str, Any],
    ) -> dict[str, Any]:
        time_rows = explorer_payload.get("time_rows")
        if not isinstance(time_rows, list):
            time_rows = []
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        transaction_ids: set[str] = set()
        total_amount = Decimal("0.00")
        for raw_row in time_rows:
            if not isinstance(raw_row, dict):
                continue
            amount = _decimal_from_value(raw_row.get("amount")) or Decimal("0.00")
            transaction_id = str(raw_row.get("transaction_id") or "").strip()
            if transaction_id:
                transaction_ids.add(transaction_id)
            total_amount += amount
            key = (
                str(raw_row.get("project_name") or "").strip(),
                str(raw_row.get("expense_type") or "").strip(),
                str(raw_row.get("expense_content") or "").strip(),
            )
            bucket = grouped.setdefault(
                key,
                {
                    "project_name": key[0],
                    "expense_type": key[1],
                    "expense_content": key[2],
                    "amount_decimal": Decimal("0.00"),
                    "transaction_count": 0,
                    "sample_transaction_ids": [],
                },
            )
            bucket["amount_decimal"] = bucket["amount_decimal"] + amount
            bucket["transaction_count"] = int(bucket["transaction_count"]) + 1
            samples = bucket["sample_transaction_ids"]
            if transaction_id and isinstance(samples, list) and transaction_id not in samples:
                samples.append(transaction_id)

        rows = []
        for bucket in sorted(grouped.values(), key=lambda item: (item["project_name"], item["expense_type"], item["expense_content"])):
            rows.append(
                {
                    "project_name": bucket["project_name"],
                    "expense_type": bucket["expense_type"],
                    "expense_content": bucket["expense_content"],
                    "amount": _plain_money(bucket["amount_decimal"]),
                    "transaction_count": bucket["transaction_count"],
                    "sample_transaction_ids": list(bucket["sample_transaction_ids"]),
                }
            )
        return {
            "month": month,
            "summary": {
                "row_count": len(rows),
                "transaction_count": len(transaction_ids) if transaction_ids else len(time_rows),
                "total_amount": _plain_money(total_amount),
            },
            "rows": rows,
        }

    @staticmethod
    def empty_explorer_payload(month: str) -> dict[str, Any]:
        return {
            "month": month,
            "summary": {
                "row_count": 0,
                "transaction_count": 0,
                "total_amount": "0.00",
            },
            "time_rows": [],
            "project_rows": [],
            "expense_type_rows": [],
        }

    @staticmethod
    def _is_explorer_payload(payload: dict[str, Any]) -> bool:
        summary = payload.get("summary")
        if not isinstance(summary, dict):
            return False
        return all(isinstance(payload.get(key), list) for key in ("time_rows", "project_rows", "expense_type_rows"))

    @staticmethod
    def empty_month_payload(month: str) -> dict[str, Any]:
        return {
            "month": month,
            "summary": {
                "row_count": 0,
                "transaction_count": 0,
                "total_amount": "0.00",
            },
            "rows": [],
        }

    @staticmethod
    def explorer_entry_count(payload: dict[str, Any]) -> int:
        time_rows = payload.get("time_rows")
        if isinstance(time_rows, list):
            return len(time_rows)
        summary = payload.get("summary")
        if isinstance(summary, dict):
            raw_count = summary.get("transaction_count", summary.get("row_count", 0))
            try:
                return int(raw_count)
            except (TypeError, ValueError):
                return 0
        return 0

    @staticmethod
    def _normalize_project_scope(project_scope: str) -> str:
        normalized_project_scope = str(project_scope or "active").strip().lower()
        if normalized_project_scope not in {"active", "all"}:
            raise ValueError("project_scope must be active or all")
        return normalized_project_scope


def _plain_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _decimal_from_value(value: object) -> Decimal | None:
    if value in (None, "", "--", "—"):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return None
