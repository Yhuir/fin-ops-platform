from __future__ import annotations

import base64
from decimal import Decimal
from io import BytesIO
import json
import re
from typing import Any

from openpyxl import Workbook

from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy
from fin_ops_platform.services.search_query import normalize_money_search_query


COST_STATISTICS_EXPORT_ROW_LIMIT = 20000
COST_STATISTICS_EXPORT_PREVIEW_SIZE = 8


class CostStatisticsExportLimitError(ValueError):
    def __init__(
        self,
        *,
        view: str,
        total: int,
        limit: int = COST_STATISTICS_EXPORT_ROW_LIMIT,
    ) -> None:
        super().__init__(
            f"当前筛选命中 {total} 行，超过 {limit} 行导出上限，请缩小筛选范围。"
        )
        self.error_code = "cost_statistics_export_row_limit_exceeded"
        self.details = {"view": view, "total": total, "limit": limit}


class CostStatisticsQueryService:
    """Serve Cost pages from one canonical snapshot per API request."""

    def __init__(self, *, canonical_repository: Any) -> None:
        if not callable(
            getattr(canonical_repository, "load_snapshot", None)
        ) or not callable(
            getattr(canonical_repository, "load_no_oa_tag_candidate_snapshot", None)
        ):
            raise ValueError(
                "Cost statistics query service requires a canonical snapshot repository."
            )
        self._canonical_repository = canonical_repository

    def get_explorer_page(
        self,
        *,
        scope: str,
        view: str,
        filters: dict[str, str | None],
        cursor: str | None,
        page_size: int,
        include_statistics: bool = True,
    ) -> dict[str, Any]:
        scope_kind, scope_value, normalized_scope = self._normalize_page_scope(
            scope
        )
        normalized_view, normalized_filters = self._normalize_page_query(
            view,
            filters,
        )
        normalized_page_size = self._normalize_page_size(page_size)
        policy = CostStatisticsPolicy(
            self._canonical_repository.load_snapshot(
                scope_kind=scope_kind,
                scope_value=scope_value,
                view=normalized_view,
                include_statistics=include_statistics,
            ),
        )
        query_binding = self._page_query_binding(
            scope=normalized_scope,
            view=normalized_view,
            filters=normalized_filters,
            page_size=normalized_page_size,
            scope_version=(policy.project_cost_scope["version"] if normalized_view in {"project", "cost_tag", "bank_account"} else None),
        )
        cursor_values = self._decode_page_cursor(
            cursor,
            query_binding=query_binding,
        )
        raw_page = policy.explorer_page(
            scope_kind=scope_kind,
            scope_value=scope_value,
            view=normalized_view,
            filters=normalized_filters,
            cursor_values=cursor_values,
            page_size=normalized_page_size,
            include_statistics=include_statistics,
        )
        facets = {
            "projects": [],
            "bank_accounts": [],
            "bank_tag_primary": [],
            "bank_tag_sub": [],
            "cost_tag_primary": [],
            "cost_tag_sub": [],
        }
        primary = list(raw_page.get("primary_facets") or [])
        secondary = list(raw_page.get("secondary_facets") or [])
        if normalized_view == "project":
            facets["projects"] = primary
            facets["cost_tag_primary"] = secondary
            facets["cost_tag_sub"] = list(raw_page["tertiary_facets"])
        elif normalized_view == "bank_account":
            facets["bank_accounts"] = primary
            facets["projects"] = secondary
            facets["cost_tag_primary"] = list(raw_page["tertiary_facets"])
            facets["cost_tag_sub"] = list(raw_page["quaternary_facets"])
        elif normalized_view == "cost_tag":
            facets["cost_tag_primary"] = primary
            facets["cost_tag_sub"] = secondary
        elif normalized_view == "bank_tag":
            facets["bank_tag_primary"] = primary
            facets["bank_tag_sub"] = secondary
        next_cursor_values = raw_page.get("next_cursor_values")
        payload = {
            "scope": normalized_scope,
            "view": normalized_view,
            "summary": dict(raw_page.get("summary") or {}),
            "statistics": (
                dict(raw_page["statistics"])
                if isinstance(raw_page.get("statistics"), dict)
                else None
            ),
            "available_years": list(raw_page.get("available_years") or []),
            "facets": facets,
            "rows": [
                dict(row)
                for row in list(raw_page.get("rows") or [])
                if isinstance(row, dict)
            ],
            "row_count": int(raw_page.get("row_count") or 0),
            "next_cursor": (
                self._encode_page_cursor(
                    tuple(str(value) for value in next_cursor_values),
                    query_binding=query_binding,
                )
                if isinstance(next_cursor_values, (list, tuple))
                and len(next_cursor_values) == 4
                else None
            ),
            "allocation_quality": (
                dict(raw_page["allocation_quality"])
                if isinstance(raw_page.get("allocation_quality"), dict)
                else None
            ),
        }
        if normalized_view in {"project", "cost_tag", "bank_account"}:
            payload["project_cost_scope_version"] = policy.project_cost_scope["version"]
        return payload

    def get_bank_transaction_detail(
        self,
        transaction_id: str,
        *,
        view: str,
        scope: str,
    ) -> dict[str, Any]:
        scope_kind, scope_value, _normalized_scope = self._normalize_page_scope(
            scope
        )
        normalized_view, _filters = self._normalize_page_query(view, {})
        normalized_transaction_id = str(transaction_id or "").strip()
        if not normalized_transaction_id:
            raise KeyError(transaction_id)
        row = CostStatisticsPolicy(
            self._canonical_repository.load_snapshot(
                scope_kind=scope_kind,
                scope_value=scope_value,
                view=normalized_view,
                include_statistics=False,
            ),
        ).bank_transaction(
            transaction_id=normalized_transaction_id,
            scope_kind=scope_kind,
            scope_value=scope_value,
        )
        if not isinstance(row, dict):
            raise KeyError(transaction_id)
        label_path = row.get("bank_tag_label_path")
        month = str(row.get("month") or row.get("trade_time") or "")[:7] or "all"
        return {
            "month": month,
            "kind": "bank_transaction",
            "bank_transaction": {
                "id": normalized_transaction_id,
                "expense_content": str(row.get("expense_content") or ""),
                "trade_time": str(row.get("trade_time") or ""),
                "direction": str(row.get("direction") or ""),
                "amount": _plain_money(
                    _decimal_from_value(row.get("amount"))
                    or Decimal("0.00")
                ),
                "counterparty_name": str(
                    row.get("counterparty_name") or ""
                ),
                "payment_account_label": str(
                    row.get("payment_account_label") or ""
                ),
                "remark": str(row.get("remark") or ""),
                "bank_tag_code": str(row.get("bank_tag_code") or ""),
                "bank_tag_label": str(row.get("bank_tag_label") or ""),
                "bank_tag_primary_label": str(
                    row.get("bank_tag_primary_label") or ""
                ),
                "bank_tag_sub_label": str(
                    row.get("bank_tag_sub_label") or ""
                ),
                "bank_tag_label_path": (
                    list(label_path) if isinstance(label_path, list) else []
                ),
                "project_name": str(row.get("project_name") or ""),
                "expense_type": str(row.get("expense_type") or ""),
            },
        }

    def get_allocation_detail(
        self,
        allocation_id: str,
        *,
        view: str,
        scope: str,
    ) -> dict[str, Any]:
        scope_kind, scope_value, _normalized_scope = self._normalize_page_scope(scope)
        normalized_view, _filters = self._normalize_page_query(view, {})
        if normalized_view not in {"project", "bank_account", "cost_tag"}:
            raise ValueError(
                "allocation detail requires project, bank_account, or cost_tag view"
            )
        normalized_allocation_id = str(allocation_id or "").strip()
        relation_prefix, separator, _unit_source = normalized_allocation_id.partition(":unit:")
        if not separator or not relation_prefix.startswith("relation:"):
            raise KeyError(allocation_id)
        row = CostStatisticsPolicy(
            self._canonical_repository.load_relation_snapshot(relation_prefix.removeprefix("relation:")),
        ).allocation(
            allocation_id=normalized_allocation_id,
            scope_kind=scope_kind,
            scope_value=scope_value,
        )
        if not isinstance(row, dict):
            raise KeyError(allocation_id)
        return {
            "month": str(row.get("month") or "")[:7] or "all",
            "kind": "oa_allocation",
            "allocation": {
                key: row.get(key)
                for key in (
                    "allocation_id",
                    "oa_id",
                    "oa_apply_type",
                    "expense_item_id",
                    "oa_completed_at",
                    "project_name",
                    "project_id",
                    "expense_type",
                    "expense_content",
                    "amount",
                    "counterparty_name",
                    "payment_account_label",
                    "bank_account_label",
                    "oa_applicant",
                    "oa_original_amount",
                    "oa_allocation_weight",
                    "bank_event_amount", "transaction_id", "occurred_at", "allocation_state",
                    "bank_tag_code", "bank_tag_primary_label", "bank_tag_sub_label", "bank_tag_label_path",
                )
            },
            "payment_evidence": [
                dict(item)
                for item in list(row.get("payment_evidence") or [])
                if isinstance(item, dict)
            ],
            "reconciliation": dict(row.get("reconciliation") or {}),
        }

    def get_no_oa_tag_candidates(self) -> list[dict[str, Any]]:
        policy = CostStatisticsPolicy(
            self._canonical_repository.load_no_oa_tag_candidate_snapshot(),
        )
        return policy.no_oa_tag_candidates()

    def get_export_preview(self, **kwargs: Any) -> dict[str, Any]:
        view = str(kwargs.get("view") or "").strip()
        month = str(kwargs.get("month") or "all").strip() or "all"
        project_names = self._normalize_text_set(
            kwargs.get("project_names")
            or (
                [kwargs.get("project_name")]
                if kwargs.get("project_name")
                else []
            )
        )
        bank_tag_primary_keys = self._normalize_text_set(kwargs.get("bank_tag_primary_keys"))
        bank_account_labels = self._normalize_text_set(
            kwargs.get("bank_account_labels")
        )
        range_kwargs = self._range_kwargs(kwargs)
        if view not in {
            "time",
            "bank_tag",
            "bank_account",
            "project",
            "cost_tag",
        }:
            raise ValueError(
                "view must be time, bank_tag, bank_account, project, or cost_tag."
            )
        if view == "project" and not project_names:
            raise ValueError("project_name is required for project export preview")
        if view == "cost_tag" and not bank_tag_primary_keys:
            raise ValueError(
                "bank_tag_primary_key is required for cost_tag export preview"
            )
        if view == "bank_account" and not bank_account_labels:
            raise ValueError(
                "bank_account_label is required for bank_account export preview"
            )
        aggregate_by = self._normalize_project_aggregate_by(kwargs.get("aggregate_by"))
        row_shape = "raw_bank" if view in {"time", "bank_tag"} else "raw_cost"
        if view == "project" and aggregate_by is not None:
            row_shape = "project_month" if aggregate_by == "month" else "project_year"
        policy = self._policy(view=view)
        page = policy.export_page(
            month=month,
            project_names=sorted(project_names),
            bank_tag_primary_keys=sorted(bank_tag_primary_keys),
            row_shape=row_shape,
            offset=0,
            page_size=COST_STATISTICS_EXPORT_ROW_LIMIT + 1,
            include_summary=True,
            bank_account_labels=sorted(bank_account_labels),
            **range_kwargs,
        )
        summary = self._export_page_summary(page)
        total = int(summary.get("source_row_count") or 0)
        self._ensure_export_row_limit(view=view, total=total)
        entries = [
            self._export_entry_from_row(row)
            for row in list(page.get("rows") or [])[:COST_STATISTICS_EXPORT_PREVIEW_SIZE]
        ]
        scope_label = self._build_scope_label(month=month, **range_kwargs)
        if view == "time":
            columns = [
                "交易时间",
                "资金方向",
                "金额",
                "主标签",
                "子标签",
                "对方户名",
                "摘要/备注",
                "银行账户",
            ]
            rows = [self._time_row_from_entry(entry) for entry in entries]
            sheet_names = ["按时间统计"]
            file_name = self._build_filename(month=scope_label, view=view)
            extra = self._directional_summary_from_export_summary(summary)
        elif view == "bank_tag":
            columns = [
                "交易时间",
                "主标签",
                "子标签",
                "资金方向",
                "金额",
                "对方户名",
                "摘要/备注",
                "银行账户",
            ]
            rows = [self._bank_tag_row_from_entry(entry) for entry in entries]
            sheet_names = ["按标签统计"]
            file_name = self._build_filename(month=scope_label, view=view)
            extra = self._directional_summary_from_export_summary(summary)
        else:
            if row_shape in {"project_month", "project_year"}:
                columns = ["统计周期", "项目名称", "银行主标签", "银行子标签", "金额", "费用内容", "成本明细数"]
                rows = [[entry["period_label"], entry["project_name"], entry["bank_tag_primary_label"], entry["bank_tag_sub_label"], entry["amount"], entry["expense_content"], entry["transaction_count"]] for entry in entries]
            else:
                columns = self._cost_export_headers()
                rows = [self._cost_export_row(entry) for entry in entries]
            sheet_names = ["按项目汇总", "成本明细"] if row_shape in {"project_month", "project_year"} else ["成本明细"]
            file_name = self._build_filename(month=scope_label, view=view, project_name="、".join(sorted(project_names)), project_names=sorted(project_names), aggregate_by=aggregate_by)
            extra = {}
        if view not in {"time", "bank_tag"}:
            allocation_quality = self._manual_allocation_quality_from_export_summary(
                summary
            )
            extra.update(allocation_quality)
            if allocation_quality["manual_allocation_pending_count"] > 0:
                sheet_names.append("待分配说明")
        return self._preview_payload(
            view=view,
            file_name=file_name,
            scope_label=scope_label,
            sheet_names=sheet_names,
            columns=columns,
            rows=rows,
            total_count=total,
            total_amount=_plain_money(
                _decimal_from_value(summary.get("total_amount"))
                or Decimal("0.00")
            ),
            summary_extra=extra,
        )

    def export_view(self, **kwargs: Any) -> tuple[str, bytes]:
        view = str(kwargs.get("view") or "").strip()
        month = str(kwargs.get("month") or "all").strip() or "all"
        project_names = self._normalize_text_set(
            kwargs.get("project_names")
            or (
                [kwargs.get("project_name")]
                if kwargs.get("project_name")
                else []
            )
        )
        bank_tag_primary_keys = self._normalize_text_set(kwargs.get("bank_tag_primary_keys"))
        bank_account_labels = self._normalize_text_set(
            kwargs.get("bank_account_labels")
        )
        aggregate_by = self._normalize_project_aggregate_by(
            kwargs.get("aggregate_by")
        )
        range_kwargs = self._range_kwargs(kwargs)
        if view not in {
            "time",
            "bank_tag",
            "bank_account",
            "project",
            "cost_tag",
        }:
            raise ValueError(f"unsupported export view: {view}")
        if view == "project" and not project_names:
            raise ValueError("project_name is required for project export")
        if view == "cost_tag" and not bank_tag_primary_keys:
            raise ValueError(
                "bank_tag_primary_key is required for cost_tag export"
            )
        if view == "bank_account" and not bank_account_labels:
            raise ValueError("bank_account_label is required for bank_account export")
        row_shape = "raw_cost"
        export_month = month
        if view in {"time", "bank_tag"}:
            row_shape = "raw_bank"
        elif view == "project" and aggregate_by is not None:
            row_shape = (
                "project_month"
                if (aggregate_by or "month") == "month"
                else "project_year"
            )
        policy = self._policy(view=view)
        page = policy.export_page(
            month=export_month,
            project_names=sorted(project_names),
            bank_tag_primary_keys=sorted(bank_tag_primary_keys),
            row_shape=row_shape,
            offset=0,
            page_size=COST_STATISTICS_EXPORT_ROW_LIMIT + 1,
            include_summary=True,
            bank_account_labels=sorted(bank_account_labels),
            **range_kwargs,
        )
        summary = self._export_page_summary(page)
        total = int(
            summary.get("source_row_count")
            or 0
        )
        self._ensure_export_row_limit(view=view, total=total)
        entries = [
            self._export_entry_from_row(row)
            for row in list(page.get("rows") or [])
        ]
        scope_label = self._build_scope_label(month=month, **range_kwargs)
        if view == "time":
            workbook = self._table_workbook(
                "按时间统计",
                [
                    "交易时间",
                    "资金方向",
                    "金额",
                    "主标签",
                    "子标签",
                    "对方户名",
                    "摘要/备注",
                    "银行账户",
                ],
                (self._time_row_from_entry(entry) for entry in entries),
            )
            filename = self._build_filename(month=scope_label, view=view)
        elif view == "bank_tag":
            workbook = self._table_workbook(
                "按标签统计",
                [
                    "交易时间",
                    "主标签",
                    "子标签",
                    "资金方向",
                    "金额",
                    "对方户名",
                    "摘要/备注",
                    "银行账户",
                ],
                (self._bank_tag_row_from_entry(entry) for entry in entries),
            )
            filename = self._build_filename(month=scope_label, view=view)
        else:
            if row_shape in {"project_month", "project_year"}:
                headers = ["统计周期", "项目名称", "银行主标签", "银行子标签", "金额", "费用内容", "成本明细数"]
                values = ([entry["period_label"], entry["project_name"], entry["bank_tag_primary_label"], entry["bank_tag_sub_label"], entry["amount"], entry["expense_content"], entry["transaction_count"]] for entry in entries)
            else:
                headers = self._cost_export_headers()
                values = (self._cost_export_row(entry) for entry in entries)
            aggregated = row_shape in {"project_month", "project_year"}
            workbook = self._table_workbook("按项目汇总" if aggregated else "成本明细", headers, values)
            if aggregated:
                detail_page = policy.export_page(
                    month=export_month, project_names=sorted(project_names),
                    bank_tag_primary_keys=sorted(bank_tag_primary_keys), row_shape="raw_cost",
                    offset=0, page_size=COST_STATISTICS_EXPORT_ROW_LIMIT + 1,
                    include_summary=False, bank_account_labels=sorted(bank_account_labels), **range_kwargs,
                )
                detail_sheet = workbook.create_sheet("成本明细")
                detail_sheet.append(self._cost_export_headers())
                for row in detail_page["rows"]:
                    detail_sheet.append(self._cost_export_row(self._export_entry_from_row(row)))
            filename = self._build_filename(month=scope_label, view=view, project_name="、".join(sorted(project_names)), project_names=sorted(project_names), aggregate_by=aggregate_by)
        if view not in {"time", "bank_tag"}:
            self._append_manual_allocation_notice(workbook, summary=summary)
        return filename, self._serialize_workbook(workbook)

    def _policy(self, *, view: str) -> CostStatisticsPolicy:
        snapshot_view = view
        if snapshot_view == "cost_tag":
            snapshot_view = "project"
        return CostStatisticsPolicy(
            self._canonical_repository.load_snapshot(
                view=snapshot_view,
            )
        )

    @staticmethod
    def _normalize_page_scope(
        scope: str,
    ) -> tuple[str, str | None, str]:
        normalized = str(scope or "").strip().lower()
        if normalized == "all":
            return "all", None, "all"
        if re.fullmatch(r"year:\d{4}", normalized):
            return "year", normalized.split(":", 1)[1], normalized
        if re.fullmatch(r"\d{4}-\d{2}", normalized):
            return "month", normalized, normalized
        raise ValueError("scope must be all, year:YYYY, or YYYY-MM")

    @staticmethod
    def _normalize_page_size(page_size: int) -> int:
        normalized = int(page_size)
        if normalized < 1 or normalized > 200:
            raise ValueError("page_size must be between 1 and 200")
        return normalized

    @staticmethod
    def _normalize_page_query(
        view: str,
        filters: dict[str, str | None],
    ) -> tuple[str, dict[str, str]]:
        normalized_view = str(view or "project").strip().lower() or "project"
        if normalized_view not in {
            "time",
            "project",
            "cost_tag",
            "bank_account",
            "bank_tag",
        }:
            raise ValueError(
                "view must be time, project, cost_tag, bank_account, or bank_tag"
            )
        query = normalize_money_search_query(
            " ".join(str(filters.get("query") or "").split())
        )
        if len(query) > 200:
            raise ValueError("query must be at most 200 characters")
        if filters.get("expense_type"):
            raise ValueError("OA expense_type is no longer a cost statistics filter")
        keys = {"query"}
        if normalized_view in {"project", "bank_account"}:
            keys.add("project_name")
        if normalized_view == "bank_account":
            keys.add("bank_account_label")
        if normalized_view in {"project", "bank_account", "cost_tag"}:
            keys.update({"bank_tag_primary_key", "bank_tag_sub_key"})
        elif normalized_view == "bank_tag":
            keys.update({"bank_tag_primary_label", "bank_tag_sub_label"})
        normalized_filters = {key: str(filters.get(key) or "").strip() for key in sorted(keys)}
        normalized_filters["query"] = query
        return normalized_view, normalized_filters

    @staticmethod
    def _page_query_binding(
        *,
        scope: str,
        view: str,
        filters: dict[str, str],
        page_size: int,
        scope_version: int | None = None,
    ) -> str:
        return json.dumps(
            {
                "scope": scope,
                "view": view,
                "filters": filters,
                "page_size": page_size,
                **({"cost_cursor_version": 2, "project_cost_scope_version": scope_version} if view in {"project", "cost_tag", "bank_account"} else {}),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _encode_page_cursor(
        values: tuple[str, ...],
        *,
        query_binding: str,
    ) -> str:
        encoded = json.dumps(
            {"query": query_binding, "values": list(values)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_page_cursor(
        cursor: str | None,
        *,
        query_binding: str,
    ) -> tuple[str, str, str, str] | None:
        if not cursor:
            return None
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(
                base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
            )
            values = payload.get("values")
        except Exception as error:
            raise ValueError("invalid cost statistics cursor") from error
        if (
            not isinstance(payload, dict)
            or payload.get("query") != query_binding
            or not isinstance(values, list)
            or len(values) != 4
        ):
            raise ValueError("cost statistics cursor does not match query")
        return tuple(str(value) for value in values)  # type: ignore[return-value]

    @staticmethod
    def empty_explorer_page_payload(
        scope: str,
        view: str,
    ) -> dict[str, Any]:
        return {
            "scope": scope,
            "view": view,
            "summary": {
                "row_count": 0,
                "transaction_count": 0,
                "total_amount": "0.00",
                "expense_amount": "0.00",
                "income_amount": "0.00",
                "expense_transaction_count": 0,
                "income_transaction_count": 0,
            },
            "statistics": {},
            "available_years": [],
            "facets": {
                "projects": [],
                    "bank_accounts": [],
                "bank_tag_primary": [],
                "bank_tag_sub": [],
            "cost_tag_primary": [],
            "cost_tag_sub": [],
            },
            "rows": [],
            "row_count": 0,
            "next_cursor": None,
        }

    @staticmethod
    def explorer_entry_count(payload: dict[str, Any]) -> int:
        return int(payload.get("row_count") or 0)

    @staticmethod
    def _export_page_summary(page: dict[str, Any]) -> dict[str, Any]:
        summary = page.get("summary")
        return dict(summary) if isinstance(summary, dict) else {}

    @staticmethod
    def _manual_allocation_quality_from_export_summary(
        summary: dict[str, Any],
    ) -> dict[str, int]:
        pending = int(summary.get("pending_manual_allocation_count") or 0)
        stale = int(summary.get("stale_manual_allocation_count") or 0)
        return {
            "manual_allocation_pending_count": pending + stale,
            "pending_manual_allocation_count": pending,
            "stale_manual_allocation_count": stale,
        }

    @staticmethod
    def _export_entry_from_row(
        raw_row: dict[str, Any],
    ) -> dict[str, Any]:
        trade_time = str(
            raw_row.get("occurred_at")
            or raw_row.get("trade_time")
            or raw_row.get("trade_time_text")
            or ""
        )
        amount = _decimal_from_value(raw_row.get("amount")) or Decimal(
            "0.00"
        )
        primary = str(raw_row.get("bank_tag_primary_label") or "")
        sub = str(raw_row.get("bank_tag_sub_label") or "")
        label_path = list(raw_row.get("bank_tag_label_path") or [])
        return {
            "entry_id": str(
                raw_row.get("entry_id")
                or raw_row.get("allocation_id")
                or raw_row.get("transaction_id")
                or ""
            ).strip(),
            "allocation_id": str(raw_row.get("allocation_id") or "").strip(),
            "transaction_id": raw_row.get("transaction_id"),
            "allocation_state": raw_row.get("allocation_state", "source_resolved"),
            "oa_id": str(raw_row.get("oa_id") or "").strip(),
            "oa_apply_type": str(raw_row.get("oa_apply_type") or "").strip(),
            "relation_case_id": str(
                raw_row.get("relation_case_id") or raw_row.get("group_id") or ""
            ).strip(),
            "month": str(
                raw_row.get("month") or raw_row.get("scope_month") or ""
            )[:7]
            or trade_time[:7],
            "trade_time": trade_time,
            "direction": str(raw_row.get("direction") or "支出"),
            "project_name": str(
                raw_row.get("project_name") or ""
            ).strip(),
            "expense_type": str(
                raw_row.get("expense_type") or ""
            ).strip(),
            "expense_content": str(
                raw_row.get("expense_content") or ""
            ).strip(),
            "amount_decimal": amount,
            "amount": _plain_money(amount),
            "counterparty_name": str(
                raw_row.get("counterparty_name") or ""
            ).strip(),
            "payment_account_label": str(
                raw_row.get("payment_account_label") or ""
            ).strip(),
            "bank_account_label": str(
                raw_row.get("bank_account_label") or ""
            ).strip(),
            "remark": str(raw_row.get("remark") or "").strip(),
            "oa_applicant": str(
                raw_row.get("oa_applicant") or ""
            ).strip(),
            "bank_tag_code": str(raw_row.get("bank_tag_code") or "").strip(),
            "bank_tag_label": str(raw_row.get("bank_tag_label") or sub).strip(),
            "bank_tag_primary_label": primary,
            "bank_tag_sub_label": sub,
            "bank_tag_label_path": label_path,
            "period_label": str(raw_row.get("period_label") or "—"),
            "transaction_count": int(
                raw_row.get("transaction_count") or 0
            ),
        }

    @staticmethod
    def _range_kwargs(
        kwargs: dict[str, Any],
    ) -> dict[str, str | None]:
        return {
            "start_month": str(kwargs.get("start_month") or "").strip()
            or None,
            "end_month": str(kwargs.get("end_month") or "").strip()
            or None,
            "start_date": str(kwargs.get("start_date") or "").strip()
            or None,
            "end_date": str(kwargs.get("end_date") or "").strip() or None,
        }

    @staticmethod
    def _normalize_text_set(values: object) -> set[str]:
        if values is None:
            return set()
        if isinstance(values, str):
            iterable: list[object] = [values]
        else:
            try:
                iterable = list(values)  # type: ignore[arg-type]
            except TypeError:
                iterable = [values]
        return {
            str(value).strip()
            for value in iterable
            if str(value or "").strip()
        }

    @staticmethod
    def _normalize_project_aggregate_by(value: object) -> str | None:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return None
        if normalized not in {"month", "year"}:
            raise ValueError("aggregate_by must be month or year")
        return normalized

    @staticmethod
    def _build_scope_label(
        *,
        month: str,
        start_month: str | None = None,
        end_month: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        if start_date and end_date:
            return f"{start_date}至{end_date}"
        if start_month and end_month:
            return f"{start_month}至{end_month}"
        if str(month or "").strip().lower() == "all":
            return "全部期间"
        return month or "—"

    @staticmethod
    def _ensure_export_row_limit(*, view: str, total: int) -> None:
        if total > COST_STATISTICS_EXPORT_ROW_LIMIT:
            raise CostStatisticsExportLimitError(view=view, total=total)

    @staticmethod
    def _preview_payload(
        *,
        view: str,
        file_name: str,
        scope_label: str,
        sheet_names: list[str],
        columns: list[str],
        rows: list[list[Any]],
        total_count: int,
        total_amount: str,
        summary_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "view": view,
            "file_name": file_name,
            "scope_label": scope_label,
            "summary": {
                "row_count": total_count,
                "transaction_count": total_count,
                "total_amount": total_amount,
                "sheet_count": len(sheet_names),
                **dict(summary_extra or {}),
            },
            "sheet_names": sheet_names,
            "columns": columns,
            "rows": rows[:COST_STATISTICS_EXPORT_PREVIEW_SIZE],
        }

    @staticmethod
    def _time_row_from_entry(entry: dict[str, Any]) -> list[Any]:
        return [
            entry["trade_time"],
            entry["direction"],
            _plain_money(entry["amount_decimal"]),
            entry["bank_tag_primary_label"],
            entry["bank_tag_sub_label"],
            entry["counterparty_name"],
            entry["expense_content"],
            entry["payment_account_label"],
        ]

    @staticmethod
    def _bank_tag_row_from_entry(entry: dict[str, Any]) -> list[Any]:
        return [
            entry["trade_time"],
            entry["bank_tag_primary_label"],
            entry["bank_tag_sub_label"],
            entry["direction"],
            _plain_money(entry["amount_decimal"]),
            entry["counterparty_name"],
            entry["expense_content"],
            entry["payment_account_label"],
        ]

    @staticmethod
    def _directional_summary_from_export_summary(
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "expense_amount": _plain_money(
                _decimal_from_value(summary.get("expense_amount")) or Decimal("0.00")
            ),
            "income_amount": _plain_money(
                _decimal_from_value(summary.get("income_amount")) or Decimal("0.00")
            ),
            "expense_transaction_count": int(
                summary.get("expense_transaction_count") or 0
            ),
            "income_transaction_count": int(
                summary.get("income_transaction_count") or 0
            ),
        }

    @staticmethod
    def _cost_export_headers() -> list[str]:
        return ["付款日期", "项目名称", "银行账户", "银行主标签", "银行子标签", "银行完整标签", "成本金额", "费用内容", "申请/报销人", "来源流水ID", "成本明细ID", "OA单号", "原OA费用类型", "分配状态"]

    @staticmethod
    def _cost_export_row(entry: dict[str, Any]) -> list[Any]:
        return [entry["trade_time"] or "日期待完善", entry["project_name"], entry["bank_account_label"],
                entry["bank_tag_primary_label"], entry["bank_tag_sub_label"], " / ".join(entry["bank_tag_label_path"]),
                entry["amount"], entry["expense_content"], entry["oa_applicant"], entry["transaction_id"],
                entry["entry_id"], entry["oa_id"], entry["expense_type"],
                "来源已确定"]

    @staticmethod
    def _table_workbook(
        title: str,
        headers: list[str],
        rows: Any,
    ) -> Workbook:
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet(title)
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        for index in range(1, len(headers) + 1):
            sheet.column_dimensions[chr(64 + index)].width = 18
        return workbook

    @classmethod
    def _append_manual_allocation_notice(
        cls,
        workbook: Workbook,
        *,
        summary: dict[str, Any],
    ) -> None:
        quality = cls._manual_allocation_quality_from_export_summary(summary)
        if quality["manual_allocation_pending_count"] == 0:
            return
        sheet = workbook.create_sheet("待分配说明")
        sheet.append(["说明", "数量"])
        sheet.append(
            [
                "待分配或完善银行资料的关联",
                quality["manual_allocation_pending_count"],
            ]
        )
        sheet.append(["待首次分配", quality["pending_manual_allocation_count"]])
        sheet.append(["来源变化待重新分配", quality["stale_manual_allocation_count"]])

    @staticmethod
    def _serialize_workbook(workbook: Workbook) -> bytes:
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _build_filename(
        *,
        month: str,
        view: str,
        project_name: str | None = None,
        project_names: list[str] | None = None,
        aggregate_by: str | None = None,
    ) -> str:
        month_segment = (
            "全部期间"
            if (month or "").strip().lower() == "all"
            else month
        )
        if view == "time":
            return f"成本统计_{month_segment}_按时间统计.xlsx"
        if view == "bank_tag":
            return f"成本统计_{month_segment}_按标签统计.xlsx"
        if view == "bank_account":
            return f"成本统计_{month_segment}_按银行账户统计.xlsx"
        if view == "project":
            if aggregate_by is not None:
                project_label = (
                    "、".join(
                        project_names
                        or ([project_name] if project_name else [])
                    )
                    or "未命名项目"
                )
                period = "月" if aggregate_by == "month" else "年"
                return (
                    f"成本统计_{month_segment}_按项目统计_按{period}_"
                    f"{_sanitize_filename(project_label)}.xlsx"
                )
            return (
                f"成本统计_{month_segment}_项目明细_"
                f"{_sanitize_filename(project_name or '未命名项目')}.xlsx"
            )
        if view == "cost_tag":
            return f"成本统计_{month_segment}_按流水标签统计.xlsx"
        raise ValueError(f"unsupported export view: {view}")


def _plain_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _decimal_from_value(value: object) -> Decimal | None:
    if value in (None, "", "--", "—"):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return None


def _sanitize_filename(value: str) -> str:
    sanitized = (
        str(value or "")
        .strip()
        .replace("/", "-")
        .replace("\\", "-")
        .replace(":", "：")
    )
    return sanitized[:80] if len(sanitized) > 80 else sanitized
