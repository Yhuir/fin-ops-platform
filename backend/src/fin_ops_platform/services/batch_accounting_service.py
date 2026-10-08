from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import Any, Callable

from fin_ops_platform.services.workbench_row_identity import canonical_workbench_row_type


class BatchAccountingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BatchAccountingService:
    def __init__(self, *, query_repository: Any | None = None) -> None:
        self._query_repository = query_repository

    def build_payload(
        self,
        *,
        bank_year: str = "all",
        page: int | str = 1,
        page_size: int | str = 50,
        timing_observer: Callable[[str, float], None] | None = None,
    ) -> dict[str, Any]:
        if bank_year != "all" and not re.fullmatch(r"20\d{2}", bank_year):
            raise BatchAccountingError("invalid_batch_accounting_year", "流水年份必须为四位年份或 all。")
        year = None if bank_year == "all" else bank_year
        page_number = self._positive_int(page, "page")
        size = self._positive_int(page_size, "page_size", maximum=200)
        started = perf_counter()
        snapshot = self._repository().list_snapshot(bank_year=year, page=page_number, page_size=size)
        if not isinstance(snapshot, dict):
            raise BatchAccountingError("batch_accounting_canonical_query_unavailable", "批量账务历史查询不可用。")
        if timing_observer:
            timing_observer("canonical_snapshot", (perf_counter() - started) * 1000)
        rows = []
        for source in snapshot["rows"]:
            rows.append(
                {
                    **source,
                    "bank_amount": self._money(source["bank_amount"]),
                    **{field: source[field] or [] for field in ("bank_accounts", "counterparty_names")},
                }
            )
        return {
            "summary": {
                "relation_count": snapshot["relation_count"],
                "transaction_count": snapshot["transaction_count"],
                "bank_year": year,
            },
            "rows": rows,
            "pagination": {"page": page_number, "page_size": size, "total": snapshot["relation_count"]},
            "available_years": snapshot["available_years"],
        }

    def detail(self, relation_id: str) -> dict[str, Any]:
        if not relation_id or len(relation_id) > 200:
            raise BatchAccountingError("invalid_batch_accounting_relation_id", "关联记录标识无效。")
        snapshot = self._repository().detail_snapshot(relation_id)
        if snapshot is None:
            raise BatchAccountingError("batch_accounting_relation_not_found", "批量账务历史记录不存在。")
        relation = snapshot["relation"]
        members = {(row["member_type"], row["id"]): row["payload"] for row in snapshot["member_rows"]}
        result: dict[str, Any] = {
            "relation_id": relation["case_id"],
            "note": relation["note"],
            "bank_rows": [],
            "oa_rows": [],
            "invoice_rows": [],
            "missing_member_ids": [],
        }
        missing_types: set[str] = set()
        seen: set[tuple[str, str]] = set()
        if len(relation["row_ids"]) != len(relation["row_types"]):
            raise BatchAccountingError("batch_accounting_invalid_history", "历史关联成员类型不完整。")
        for row_id, row_type in zip(relation["row_ids"], relation["row_types"], strict=True):
            kind = canonical_workbench_row_type(row_type)
            if kind not in {"bank", "oa", "invoice"}:
                raise BatchAccountingError("batch_accounting_invalid_history", "历史关联成员类型无效。")
            key = (kind, row_id)
            if key in seen:
                continue
            seen.add(key)
            row = members.get(key)
            if row is None:
                result["missing_member_ids"].append(row_id)
                missing_types.add(kind)
                continue
            normalized = {
                **row,
                **{
                    field: self._money(row[field])
                    for field in ("amount", "signed_amount", "total_with_tax")
                    if field in row
                },
            }
            if "etc_invoice_detail_rows" in row:
                normalized["etc_invoice_detail_rows"] = [
                    {
                        **invoice,
                        "amount": self._money(invoice["amount"]),
                        "total_with_tax": self._money(invoice["total_with_tax"]),
                    }
                    for invoice in row["etc_invoice_detail_rows"]
                ]
            result[f"{kind}_rows"].append(normalized)
        for kind in ("bank", "oa"):
            result[f"{kind}_amount"] = None if kind in missing_types else self._total(result[f"{kind}_rows"])
        result["amount_delta"] = (
            self._money(Decimal(result["bank_amount"]) - Decimal(result["oa_amount"]))
            if result["bank_amount"] is not None and result["oa_amount"] is not None
            else None
        )
        return result

    def _repository(self) -> Any:
        if self._query_repository is None:
            raise BatchAccountingError("batch_accounting_canonical_query_unavailable", "批量账务历史查询不可用。")
        return self._query_repository

    @staticmethod
    def _positive_int(value: int | str, field: str, *, maximum: int | None = None) -> int:
        if isinstance(value, bool) or not re.fullmatch(r"[1-9]\d*", str(value)):
            raise BatchAccountingError("invalid_paging", f"{field} 必须为正整数。")
        number = int(value)
        if maximum is not None and number > maximum:
            raise BatchAccountingError("invalid_paging", f"{field} 不能超过 {maximum}。")
        return number

    @staticmethod
    def _money(value: Any) -> str | None:
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
            if not amount.is_finite():
                raise InvalidOperation
            return f"{amount:.2f}"
        except (InvalidOperation, ValueError) as exc:
            raise BatchAccountingError("batch_accounting_invalid_amount", "历史记录金额无效。") from exc

    @classmethod
    def _total(cls, rows: list[dict[str, Any]]) -> str | None:
        if not rows or any(row["amount"] is None for row in rows):
            return None
        return cls._money(sum((Decimal(row["amount"]) for row in rows), Decimal(0)))
