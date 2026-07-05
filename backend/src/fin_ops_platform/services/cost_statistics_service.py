from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.services.cost_statistics_bank_tags import bank_tag_context_from_row
from fin_ops_platform.services.cost_statistics_relation_rules import is_cost_eligible_open_group
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.live_workbench_service import format_decimal

ZERO = Decimal("0.00")
EXCLUDED_COST_EXPENSE_TYPES = {"借款", "还款"}
OA_INVOICE_OFFSET_AUTO_MATCH_CODE = "oa_invoice_offset_auto_match"
OA_INVOICE_OFFSET_TAG = "冲"
CASH_PASS_THROUGH_MODE = "cash_pass_through"
CASH_TICKET_PURCHASE_MODE = "cash_ticket_purchase"
PROJECT_SCOPE_ACTIVE = "active"
PROJECT_SCOPE_ALL = "all"
COST_STATISTICS_EXPORT_ROW_LIMIT = 20000


class CostStatisticsExportLimitError(ValueError):
    def __init__(self, *, view: str, total: int, limit: int = COST_STATISTICS_EXPORT_ROW_LIMIT) -> None:
        super().__init__(f"当前筛选命中 {total} 行，超过 {limit} 行导出上限，请缩小筛选范围。")
        self.error_code = "cost_statistics_export_row_limit_exceeded"
        self.details = {"view": view, "total": total, "limit": limit}


class CostStatisticsService:
    def __init__(
        self,
        import_service: ImportNormalizationService,
        *,
        grouped_workbench_loader: Callable[[str], dict[str, Any]],
        project_active_checker: Callable[[str | None, str], bool] | None = None,
    ) -> None:
        self._import_service = import_service
        self._grouped_workbench_loader = grouped_workbench_loader
        self._project_active_checker = project_active_checker or (lambda project_id, project_name: True)

    def get_month_statistics(self, month: str, *, project_scope: str = PROJECT_SCOPE_ACTIVE) -> dict[str, Any]:
        entries = self._build_cost_entries(month, project_scope=project_scope)
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for entry in entries:
            key = (entry["project_name"], entry["expense_type"], entry["expense_content"])
            bucket = grouped.setdefault(
                key,
                {
                    "project_name": entry["project_name"],
                    "expense_type": entry["expense_type"],
                    "expense_content": entry["expense_content"],
                    "amount": ZERO,
                    "transaction_count": 0,
                    "sample_transaction_ids": [],
                },
            )
            bucket["amount"] += entry["amount_decimal"]
            bucket["transaction_count"] += 1
            if entry["transaction_id"] not in bucket["sample_transaction_ids"]:
                bucket["sample_transaction_ids"].append(entry["transaction_id"])

        rows = [
            {
                "project_name": bucket["project_name"],
                "expense_type": bucket["expense_type"],
                "expense_content": bucket["expense_content"],
                "amount": format_decimal(bucket["amount"]),
                "transaction_count": bucket["transaction_count"],
                "sample_transaction_ids": list(bucket["sample_transaction_ids"]),
            }
            for bucket in sorted(
                grouped.values(),
                key=lambda item: (item["project_name"], item["expense_type"], item["expense_content"]),
            )
        ]
        return {
            "month": month,
            "summary": {
                "row_count": len(rows),
                "transaction_count": len(entries),
                "total_amount": format_decimal(sum((entry["amount_decimal"] for entry in entries), start=ZERO)),
            },
            "rows": rows,
        }

    def get_explorer(self, month: str, *, project_scope: str = PROJECT_SCOPE_ACTIVE) -> dict[str, Any]:
        entries = self._build_cost_entries(month, project_scope=project_scope)
        sorted_entries = sorted(entries, key=lambda item: (item["trade_time"], item["transaction_id"]), reverse=True)

        project_groups: dict[str, dict[str, Any]] = {}
        expense_type_groups: dict[str, dict[str, Any]] = {}

        for entry in sorted_entries:
            project_bucket = project_groups.setdefault(
                entry["project_name"],
                {
                    "project_name": entry["project_name"],
                    "total_amount": ZERO,
                    "transaction_count": 0,
                    "expense_types": set(),
                },
            )
            project_bucket["total_amount"] += entry["amount_decimal"]
            project_bucket["transaction_count"] += 1
            project_bucket["expense_types"].add(entry["expense_type"])

            expense_bucket = expense_type_groups.setdefault(
                entry["expense_type"],
                {
                    "expense_type": entry["expense_type"],
                    "total_amount": ZERO,
                    "transaction_count": 0,
                    "projects": set(),
                },
            )
            expense_bucket["total_amount"] += entry["amount_decimal"]
            expense_bucket["transaction_count"] += 1
            expense_bucket["projects"].add(entry["project_name"])

        return {
            "month": month,
            "summary": self._summary_payload(sorted_entries),
            "time_rows": [self._serialize_cost_entry(entry) for entry in sorted_entries],
            "bank_accounts": [],
            "project_rows": [
                {
                    "project_name": bucket["project_name"],
                    "total_amount": format_decimal(bucket["total_amount"]),
                    "transaction_count": bucket["transaction_count"],
                    "expense_type_count": len(bucket["expense_types"]),
                }
                for bucket in sorted(
                    project_groups.values(),
                    key=lambda item: (-item["total_amount"], item["project_name"]),
                )
            ],
            "expense_type_rows": [
                {
                    "expense_type": bucket["expense_type"],
                    "total_amount": format_decimal(bucket["total_amount"]),
                    "transaction_count": bucket["transaction_count"],
                    "project_count": len(bucket["projects"]),
                }
                for bucket in sorted(
                    expense_type_groups.values(),
                    key=lambda item: (-item["total_amount"], item["expense_type"]),
                )
            ],
        }

    def get_expense_type_statistics(
        self,
        month: str,
        expense_type: str,
        *,
        project_scope: str = PROJECT_SCOPE_ACTIVE,
    ) -> dict[str, Any]:
        entries = [
            entry
            for entry in self._build_cost_entries(month, project_scope=project_scope)
            if entry["expense_type"] == expense_type
        ]
        rows = [
            {
                "transaction_id": entry["transaction_id"],
                "trade_time": entry["trade_time"],
                "direction": entry["direction"],
                "project_name": entry["project_name"],
                "expense_type": entry["expense_type"],
                "expense_content": entry["expense_content"],
                "amount": format_decimal(entry["amount_decimal"]),
                "counterparty_name": entry["counterparty_name"],
                "payment_account_label": entry["payment_account_label"],
                **bank_tag_context_from_row(entry),
            }
            for entry in sorted(entries, key=lambda item: (item["trade_time"], item["transaction_id"]), reverse=True)
        ]
        return {
            "month": month,
            "expense_type": expense_type,
            "summary": self._summary_payload(entries),
            "rows": rows,
        }

    def _build_cost_entries(self, month: str, *, project_scope: str = PROJECT_SCOPE_ACTIVE) -> list[dict[str, Any]]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        entries: list[dict[str, Any]] = []
        for scoped_month in self._resolve_target_months(month):
            payload = self._grouped_workbench_loader(scoped_month)
            groups = [
                *list(((payload.get("paired") or {}).get("groups") or [])),
                *[
                    group
                    for group in list(((payload.get("open") or {}).get("groups") or []))
                    if is_cost_eligible_open_group(group)
                ],
            ]
            for group in groups:
                oa_rows = list(group.get("oa_rows") or [])
                bank_rows = list(group.get("bank_rows") or [])
                if not oa_rows or not bank_rows:
                    continue
                special_metadata = self._group_special_metadata(group)
                special_policy = str(special_metadata.get("cost_policy") or "").strip()
                if special_policy == "exclude_all":
                    continue
                if special_policy == "include_ticket_cost_only":
                    ticket_entry = self._build_cash_ticket_cost_entry(group, oa_rows, bank_rows, special_metadata)
                    if ticket_entry is not None:
                        entries.append(ticket_entry)
                    continue
                context = self._resolve_group_cost_context(oa_rows)
                if context is None:
                    continue
                for bank_row in bank_rows:
                    amount = self._extract_outflow_amount(bank_row)
                    if amount is None:
                        continue
                    entries.append(
                        {
                            "group_id": str(group.get("group_id", "")),
                            "transaction_id": str(bank_row["id"]),
                            "trade_time": str(bank_row.get("trade_time") or bank_row.get("pay_receive_time") or ""),
                            "counterparty_name": str(bank_row.get("counterparty_name") or ""),
                            "payment_account_label": str(bank_row.get("payment_account_label") or ""),
                            "direction": str(bank_row.get("direction") or "支出"),
                            "remark": str(bank_row.get("remark") or ""),
                            "project_name": context["project_name"],
                            "project_id": context["project_id"],
                            "expense_type": context["expense_type"],
                            "expense_content": context["expense_content"],
                            "oa_applicant": context["oa_applicant"],
                            "amount_decimal": amount,
                            **bank_tag_context_from_row(bank_row),
                        }
                    )
        return self._filter_entries_by_project_scope(entries, normalized_project_scope)

    @staticmethod
    def _group_special_metadata(group: dict[str, Any]) -> dict[str, Any]:
        metadata = group.get("special_metadata")
        if isinstance(metadata, dict) and metadata:
            return dict(metadata)
        for row in [
            *list(group.get("oa_rows") or []),
            *list(group.get("bank_rows") or []),
            *list(group.get("invoice_rows") or []),
        ]:
            row_metadata = row.get("special_metadata")
            if isinstance(row_metadata, dict) and row_metadata:
                return dict(row_metadata)
        return {}

    def _build_cash_ticket_cost_entry(
        self,
        group: dict[str, Any],
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        special_metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        if str(special_metadata.get("special_type") or "").strip() != CASH_TICKET_PURCHASE_MODE:
            return None
        amount = self._parse_decimal(special_metadata.get("ticket_cost_amount"))
        if amount in (None, ZERO):
            return None
        bank_row = next((row for row in bank_rows if self._extract_outflow_amount(row) is not None), None)
        if bank_row is None:
            return None
        context = self._resolve_group_cost_context(oa_rows) or {}
        project_name = self._clean_text(special_metadata.get("project_name")) or str(context.get("project_name") or "")
        if not project_name:
            return None
        return {
            "group_id": str(group.get("group_id", "")),
            "transaction_id": str(bank_row["id"]),
            "trade_time": str(bank_row.get("trade_time") or bank_row.get("pay_receive_time") or ""),
            "counterparty_name": str(bank_row.get("counterparty_name") or ""),
            "payment_account_label": str(bank_row.get("payment_account_label") or ""),
            "direction": str(bank_row.get("direction") or "支出"),
            "remark": str(bank_row.get("remark") or ""),
            "project_name": project_name,
            "project_id": self._clean_text(special_metadata.get("project_id")) or str(context.get("project_id") or ""),
            "expense_type": self._clean_text(special_metadata.get("expense_type")) or str(context.get("expense_type") or "现金往来"),
            "expense_content": self._clean_text(special_metadata.get("expense_content")) or "买票成本",
            "oa_applicant": str(context.get("oa_applicant") or self._cash_special_applicant(oa_rows) or "—"),
            "amount_decimal": amount,
            **bank_tag_context_from_row(bank_row),
        }

    @classmethod
    def _cash_special_applicant(cls, oa_rows: list[dict[str, Any]]) -> str:
        for row in oa_rows:
            applicant = cls._clean_text(row.get("applicant"))
            if applicant:
                return applicant
            detail_fields = row.get("detail_fields")
            if isinstance(detail_fields, dict):
                applicant = cls._clean_text(detail_fields.get("申请人"))
                if applicant:
                    return applicant
        return ""

    def _filter_entries_by_project_scope(
        self,
        entries: list[dict[str, Any]],
        project_scope: str,
    ) -> list[dict[str, Any]]:
        normalized_scope = self._normalize_project_scope(project_scope)
        if normalized_scope == PROJECT_SCOPE_ALL:
            return entries
        return [
            entry
            for entry in entries
            if self._should_include_project(
                entry.get("project_id"),
                str(entry.get("project_name") or ""),
                normalized_scope,
            )
        ]

    def _should_include_project(
        self,
        project_id: object,
        project_name: str,
        project_scope: str,
    ) -> bool:
        normalized_scope = self._normalize_project_scope(project_scope)
        if normalized_scope == PROJECT_SCOPE_ALL:
            return True
        normalized_project_id = str(project_id or "").strip() or None
        return bool(self._project_active_checker(normalized_project_id, self._clean_text(project_name)))

    @staticmethod
    def _normalize_project_scope(project_scope: str | None) -> str:
        normalized_scope = str(project_scope or PROJECT_SCOPE_ACTIVE).strip().lower()
        if normalized_scope not in {PROJECT_SCOPE_ACTIVE, PROJECT_SCOPE_ALL}:
            raise ValueError("project_scope must be active or all")
        return normalized_scope

    def _resolve_target_months(
        self,
        month: str,
        *,
        start_month: str | None = None,
        end_month: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[str]:
        normalized = (month or "").strip()
        if not start_month and start_date:
            start_month = start_date[:7]
        if not end_month and end_date:
            end_month = end_date[:7]
        if start_month and end_month and start_month > end_month:
            start_month, end_month = end_month, start_month
        if normalized and normalized.lower() != "all":
            months = [normalized]
        else:
            months = sorted(
                {
                    (transaction.txn_date or "")[:7]
                    for transaction in self._import_service.list_transactions()
                    if (transaction.txn_date or "")[:7]
                },
                reverse=True,
            )
        if start_month:
            months = [item for item in months if item >= start_month]
        if end_month:
            months = [item for item in months if item <= end_month]
        return months

    def _resolve_group_cost_context(self, oa_rows: list[dict[str, Any]]) -> dict[str, str] | None:
        contexts: set[tuple[str, str, str, str, str]] = set()
        for row in oa_rows:
            if self._is_cost_excluded_oa_row(row):
                continue
            project_name = self._clean_text(row.get("project_name"))
            project_id = self._clean_text(row.get("project_id"))
            expense_type = self._clean_text(row.get("expense_type"))
            expense_content = self._clean_text(row.get("expense_content")) or self._clean_text(row.get("reason"))
            applicant = self._clean_text(row.get("applicant"))
            detail_fields = row.get("detail_fields")
            if isinstance(detail_fields, dict):
                if not expense_type:
                    expense_type = self._clean_text(detail_fields.get("费用类型"))
                if not expense_content:
                    expense_content = self._clean_text(detail_fields.get("费用内容"))
                if not applicant:
                    applicant = self._clean_text(detail_fields.get("申请人"))
            if expense_type in EXCLUDED_COST_EXPENSE_TYPES:
                continue
            if not (project_name and expense_type and expense_content):
                continue
            contexts.add((project_name, project_id, expense_type, expense_content, applicant))
        if len(contexts) != 1:
            return None
        project_name, project_id, expense_type, expense_content, applicant = next(iter(contexts))
        return {
            "project_name": project_name,
            "project_id": project_id,
            "expense_type": expense_type,
            "expense_content": expense_content,
            "oa_applicant": applicant or "—",
        }

    @staticmethod
    def _is_cost_excluded_oa_row(row: dict[str, Any]) -> bool:
        if bool(row.get("cost_excluded")):
            return True
        tags = {str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()}
        if OA_INVOICE_OFFSET_TAG in tags:
            return True
        relation = row.get("oa_bank_relation")
        if isinstance(relation, dict) and str(relation.get("code", "")) == OA_INVOICE_OFFSET_AUTO_MATCH_CODE:
            return True
        return False

    def _extract_outflow_amount(self, bank_row: dict[str, Any]) -> Decimal | None:
        transaction_id = str(bank_row.get("id", ""))
        try:
            transaction = self._import_service.get_transaction(transaction_id)
        except KeyError:
            transaction = None

        if transaction is not None:
            if transaction.txn_direction != TransactionDirection.OUTFLOW:
                return None
            return transaction.amount

        debit_amount = self._parse_decimal(bank_row.get("debit_amount"))
        credit_amount = self._parse_decimal(bank_row.get("credit_amount"))
        if credit_amount not in (None, ZERO):
            return None
        if debit_amount in (None, ZERO):
            return None
        return debit_amount

    @staticmethod
    def _parse_decimal(value: Any) -> Decimal | None:
        if value in (None, "", "—", "--"):
            return None
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text in {"-", "--", "—", "——"}:
            return ""
        return text

    def _summary_payload(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "row_count": len(entries),
            "transaction_count": len(entries),
            "total_amount": format_decimal(sum((entry["amount_decimal"] for entry in entries), start=ZERO)),
        }

    def _serialize_cost_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "transaction_id": entry["transaction_id"],
            "trade_time": entry["trade_time"],
            "direction": entry["direction"],
            "project_name": entry["project_name"],
            "expense_type": entry["expense_type"],
            "expense_content": entry["expense_content"],
            "amount": format_decimal(entry["amount_decimal"]),
            "counterparty_name": entry["counterparty_name"],
            "payment_account_label": entry["payment_account_label"],
            "remark": entry["remark"],
            "oa_applicant": entry["oa_applicant"],
            **bank_tag_context_from_row(entry),
        }
