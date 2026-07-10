from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook

from fin_ops_platform.services.app_settings_service import COST_STATISTICS_UNCATEGORIZED_TAG_CODE
from fin_ops_platform.services.cost_statistics_read_model_service import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
)
from fin_ops_platform.services.cost_statistics_service import (
    COST_STATISTICS_EXPORT_ROW_LIMIT,
    CostStatisticsExportLimitError,
)
from fin_ops_platform.services.read_model_query_gateway import (
    ReadModelQueryGateway,
    ReadModelRefreshQueueAdapter,
)


class CostStatisticsReadModelNotFreshError(RuntimeError):
    def __init__(self, payload: dict[str, Any], *, message: str) -> None:
        super().__init__(message)
        self.payload = {
            "error": "cost_statistics_read_model_not_fresh",
            "message": message,
            "read_model_status": payload.get("read_model_status") or "refreshing",
            "read_model_scope_key": payload.get("read_model_scope_key"),
            "read_model_stale_reasons": payload.get("read_model_stale_reasons") or [],
        }


class CostStatisticsQueryService:
    def __init__(
        self,
        *,
        runtime_service: Any,
        redis_helper: Any | None = None,
        sql_read_repository: Any | None = None,
        tag_selection_provider: Any | None = None,
    ) -> None:
        self._runtime_service = runtime_service
        self._sql_read_repository = sql_read_repository
        self._tag_selection_provider = tag_selection_provider
        self._read_model_query_gateway = ReadModelQueryGateway(
            queue_repository=ReadModelRefreshQueueAdapter(
                scope_type="cost_statistics",
                refresh_enqueuer=self._runtime_service.enqueue_read_model_refresh,
            ),
            redis_helper=redis_helper,
        )

    def get_month_statistics(self, month: str, project_scope: str) -> tuple[dict[str, Any], bool]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        sql_result = self.get_month_from_sql_read_model(month, normalized_project_scope)
        if sql_result is not None:
            return sql_result
        return self._refreshing_month_payload(
            month,
            normalized_project_scope,
            reason="api_sql_repository_unavailable",
        ), False

    def get_explorer(self, month: str, project_scope: str) -> tuple[dict[str, Any], bool]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        sql_result = self.get_explorer_from_sql_read_model(month, normalized_project_scope)
        if sql_result is not None:
            return sql_result
        return self._refreshing_explorer_payload(
            month,
            normalized_project_scope,
            reason="api_sql_repository_unavailable",
        ), False

    def get_project_statistics(
        self,
        month: str,
        project_name: str,
        *,
        project_scope: str,
    ) -> dict[str, Any]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        payload = self._require_fresh_explorer(month, normalized_project_scope)
        normalized_project_name = str(project_name or "").strip()
        entries = [
            entry
            for entry in self._entries_from_explorer_payload(payload)
            if entry["project_name"] == normalized_project_name
        ]
        rows = [
            {
                "transaction_id": entry["transaction_id"],
                "trade_time": entry["trade_time"],
                "direction": entry["direction"],
                "expense_type": entry["expense_type"],
                "expense_content": entry["expense_content"],
                "amount": _plain_money(entry["amount_decimal"]),
                "counterparty_name": entry["counterparty_name"],
                "payment_account_label": entry["payment_account_label"],
                "bank_tag_code": entry["bank_tag_code"],
                "bank_tag_label": entry["bank_tag_label"],
                "bank_tag_primary_label": entry["bank_tag_primary_label"],
                "bank_tag_sub_label": entry["bank_tag_sub_label"],
                "bank_tag_label_path": list(entry["bank_tag_label_path"]),
            }
            for entry in sorted(entries, key=lambda item: (item["trade_time"], item["transaction_id"]))
        ]
        return {
            "month": month,
            "project_name": project_name,
            "summary": self._summary_from_entries(entries, row_count=len(rows)),
            "rows": rows,
        }

    def get_transaction_detail(
        self,
        transaction_id: str,
        *,
        project_scope: str,
    ) -> dict[str, Any]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        payload = self._require_fresh_explorer("all", normalized_project_scope)
        normalized_transaction_id = str(transaction_id or "").strip()
        entries = self._entries_from_explorer_payload(payload)
        entry = next(
            (
                candidate
                for candidate in entries
                if candidate["transaction_id"] == normalized_transaction_id
            ),
            None,
        )
        if entry is None:
            raise KeyError(transaction_id)
        month = entry["month"] or (entry["trade_time"] or "")[:7] or "all"
        return {
            "month": month,
            "transaction": {
                "id": normalized_transaction_id,
                "project_name": entry["project_name"],
                "expense_type": entry["expense_type"],
                "expense_content": entry["expense_content"],
                "trade_time": entry["trade_time"],
                "direction": entry["direction"],
                "amount": _plain_money(entry["amount_decimal"]),
                "counterparty_name": entry["counterparty_name"],
                "payment_account_label": entry["payment_account_label"],
                "remark": entry["remark"],
                "oa_applicant": entry["oa_applicant"],
                "summary_fields": {},
                "detail_fields": {},
                "relation_status": "read_model",
                "relation_case_ids": [],
                "linked_oa_count": 0,
                "linked_invoice_count": 0,
                "bank_tag_code": entry["bank_tag_code"],
                "bank_tag_label": entry["bank_tag_label"],
                "bank_tag_primary_label": entry["bank_tag_primary_label"],
                "bank_tag_sub_label": entry["bank_tag_sub_label"],
                "bank_tag_label_path": list(entry["bank_tag_label_path"]),
            },
            "relation_context": {
                "row_id": normalized_transaction_id,
                "row_type": "bank_transaction",
                "relation_status": "read_model",
                "group_ids": [],
                "linked_oa": [],
                "linked_bank_transactions": [],
                "linked_input_invoices": [],
                "linked_output_invoices": [],
            },
        }

    def get_export_preview(self, **kwargs: Any) -> dict[str, Any]:
        kwargs["project_scope"] = self._normalize_project_scope(str(kwargs.get("project_scope") or "active"))
        return self._build_export_preview_from_read_model(**kwargs)

    def export_view(self, **kwargs: Any) -> tuple[str, bytes]:
        kwargs["project_scope"] = self._normalize_project_scope(str(kwargs.get("project_scope") or "active"))
        return self._export_view_from_read_model(**kwargs)

    def _require_fresh_explorer(
        self,
        month: str,
        project_scope: str,
        *,
        message: str = "成本统计数据正在刷新，请稍后重试。",
    ) -> dict[str, Any]:
        payload, _cache_hit = self.get_explorer(month, project_scope)
        status = str(payload.get("read_model_status") or "").strip().lower()
        if status and status != "fresh":
            raise CostStatisticsReadModelNotFreshError(payload, message=message)
        return payload

    def get_explorer_from_sql_read_model(
        self,
        month: str,
        project_scope: str,
    ) -> tuple[dict[str, Any], bool] | None:
        get_view = getattr(self._sql_read_repository, "get_cost_statistics_view", None)
        if not callable(get_view):
            return None
        scope_key = self._runtime_service.request_scope_key(month, project_scope)
        expected_source_versions = self._runtime_service.expected_source_versions(scope_key)
        tag_selection_payload = self._cost_tag_selection_payload()
        cache_key = self._runtime_service.redis_cache_key(
            scope_key,
            source_versions={
                **expected_source_versions,
                "cost_statistics_tag_selection": self._cost_tag_selection_cache_token(tag_selection_payload),
            },
        )
        result = self._read_model_query_gateway.load(
            scope_type="cost_statistics",
            scope_key=scope_key,
            expected_schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            expected_source_versions=expected_source_versions,
            load_view=lambda: get_view(scope_key=scope_key),
            empty_payload_factory=lambda: self.empty_explorer_payload(month),
            payload_validator=self._is_explorer_payload,
            cache_key=cache_key,
            cache_ttl_seconds=self._runtime_service.redis_ttl_seconds(),
            missing_reason="api_miss",
            stale_reason="api_stale",
            source_mismatch_reason="api_source_versions_stale",
            payload_invalid_reason="api_payload_shape_invalid",
        )
        payload = self._empty_non_fresh_payload(result.payload, lambda: self.empty_explorer_payload(month))
        if str(payload.get("read_model_status") or "").strip().lower() == "fresh":
            payload = self._apply_tag_selection_to_explorer_payload(payload, tag_selection_payload)
        return payload, result.cache_hit

    def get_month_from_sql_read_model(
        self,
        month: str,
        project_scope: str,
    ) -> tuple[dict[str, Any], bool] | None:
        get_view = getattr(self._sql_read_repository, "get_cost_statistics_view", None)
        if not callable(get_view):
            return None
        scope_key = self._runtime_service.request_scope_key(month, project_scope)
        expected_source_versions = self._runtime_service.expected_source_versions(scope_key)
        tag_selection_payload = self._cost_tag_selection_payload()
        cache_key = self._runtime_service.month_redis_cache_key(
            scope_key,
            source_versions={
                **expected_source_versions,
                "cost_statistics_tag_selection": self._cost_tag_selection_cache_token(tag_selection_payload),
            },
        )
        result = self._read_model_query_gateway.load(
            scope_type="cost_statistics",
            scope_key=scope_key,
            expected_schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            expected_source_versions=expected_source_versions,
            load_view=lambda: get_view(scope_key=scope_key),
            empty_payload_factory=lambda: self.empty_month_payload(month),
            payload_from_view=lambda view: self.month_payload_from_explorer_payload(
                month,
                self._apply_tag_selection_to_explorer_payload(
                    view.get("payload") if isinstance(view.get("payload"), dict) else {},
                    tag_selection_payload,
                ),
            ),
            cache_key=cache_key,
            cache_ttl_seconds=self._runtime_service.redis_ttl_seconds(),
            missing_reason="api_month_miss",
            stale_reason="api_month_stale",
            source_mismatch_reason="api_month_source_versions_stale",
        )
        return self._empty_non_fresh_payload(result.payload, lambda: self.empty_month_payload(month)), result.cache_hit

    @staticmethod
    def _empty_non_fresh_payload(payload: dict[str, Any], empty_payload_factory: Any) -> dict[str, Any]:
        if str(payload.get("read_model_status") or "").strip().lower() == "fresh":
            return payload
        replacement = dict(empty_payload_factory())
        for key in (
            "read_model_status",
            "read_model_scope_key",
            "read_model_generated_at",
            "read_model_schema_version",
            "read_model_stale_reasons",
            "source_versions",
            "refresh_enqueued",
            "refresh_reason",
        ):
            if key in payload:
                replacement[key] = payload[key]
        return replacement

    def _cost_tag_selection_payload(self) -> dict[str, Any] | None:
        provider = self._tag_selection_provider
        if provider is None:
            return None
        if callable(provider):
            payload = provider()
        else:
            get_payload = getattr(provider, "get_cost_statistics_tag_selection_payload", None)
            if not callable(get_payload):
                return None
            payload = get_payload(can_save=False)
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _cost_tag_selection_cache_token(payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return "unconfigured"
        selected = payload.get("effective_selected_tag_codes")
        if not isinstance(selected, list):
            selected = payload.get("selected_tag_codes")
        selected_codes = sorted({str(code).strip() for code in list(selected or []) if str(code).strip()})
        return (
            f"version:{int(payload.get('version') or 1)}"
            f"|bank:{int(payload.get('bank_auto_tag_rules_version') or 1)}"
            f"|selected:{','.join(selected_codes)}"
        )

    @staticmethod
    def _selected_bank_tag_codes(payload: dict[str, Any] | None) -> set[str] | None:
        if not isinstance(payload, dict):
            return None
        selected = payload.get("effective_selected_tag_codes")
        if not isinstance(selected, list):
            selected = payload.get("selected_tag_codes")
        if selected is None:
            return None
        return {str(code).strip() for code in list(selected or []) if str(code).strip()}

    def _apply_tag_selection_to_explorer_payload(
        self,
        payload: dict[str, Any],
        tag_selection_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        selected_codes = self._selected_bank_tag_codes(tag_selection_payload)
        if selected_codes is None:
            return dict(payload)
        filtered_time_rows = self._filter_rows_by_selected_tags(payload.get("time_rows"), selected_codes)
        filtered_bank_flow_rows = self._filter_rows_by_selected_tags(payload.get("bank_flow_time_rows"), selected_codes)
        next_payload = dict(payload)
        next_payload["time_rows"] = filtered_time_rows
        next_payload["summary"] = self._summary_from_time_rows(filtered_time_rows)
        next_payload["project_rows"] = self._project_rows_from_time_rows(filtered_time_rows)
        next_payload["expense_type_rows"] = self._expense_type_rows_from_time_rows(filtered_time_rows)
        next_payload["bank_flow_time_rows"] = filtered_bank_flow_rows
        next_payload["bank_flow_summary"] = self._summary_from_time_rows(filtered_bank_flow_rows)
        next_payload["cost_statistics_tag_selection_version"] = (
            int(tag_selection_payload.get("version") or 1) if isinstance(tag_selection_payload, dict) else 1
        )
        return next_payload

    @staticmethod
    def _filter_rows_by_selected_tags(rows: Any, selected_codes: set[str]) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            tag_code = str(row.get("bank_tag_code") or "").strip() or COST_STATISTICS_UNCATEGORIZED_TAG_CODE
            if tag_code in selected_codes:
                filtered.append(row)
        return filtered

    @staticmethod
    def _summary_from_time_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
        transaction_ids: set[str] = set()
        total_amount = Decimal("0.00")
        for row in rows:
            transaction_id = str(row.get("transaction_id") or "").strip()
            if transaction_id:
                transaction_ids.add(transaction_id)
            total_amount += _decimal_from_value(row.get("amount")) or Decimal("0.00")
        return {
            "row_count": len(rows),
            "transaction_count": len(transaction_ids) if transaction_ids else len(rows),
            "total_amount": _plain_money(total_amount),
        }

    @staticmethod
    def _project_rows_from_time_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            project_name = str(row.get("project_name") or "").strip()
            expense_type = str(row.get("expense_type") or "").strip()
            bucket = groups.setdefault(
                project_name,
                {
                    "project_name": project_name,
                    "total_amount": Decimal("0.00"),
                    "transaction_count": 0,
                    "expense_types": set(),
                },
            )
            bucket["total_amount"] += _decimal_from_value(row.get("amount")) or Decimal("0.00")
            bucket["transaction_count"] += 1
            bucket["expense_types"].add(expense_type)
        return [
            {
                "project_name": bucket["project_name"],
                "total_amount": _plain_money(bucket["total_amount"]),
                "transaction_count": bucket["transaction_count"],
                "expense_type_count": len(bucket["expense_types"]),
            }
            for bucket in sorted(groups.values(), key=lambda item: (-item["total_amount"], item["project_name"]))
        ]

    @staticmethod
    def _expense_type_rows_from_time_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            expense_type = str(row.get("expense_type") or "").strip()
            project_name = str(row.get("project_name") or "").strip()
            bucket = groups.setdefault(
                expense_type,
                {
                    "expense_type": expense_type,
                    "total_amount": Decimal("0.00"),
                    "transaction_count": 0,
                    "projects": set(),
                },
            )
            bucket["total_amount"] += _decimal_from_value(row.get("amount")) or Decimal("0.00")
            bucket["transaction_count"] += 1
            bucket["projects"].add(project_name)
        return [
            {
                "expense_type": bucket["expense_type"],
                "total_amount": _plain_money(bucket["total_amount"]),
                "transaction_count": bucket["transaction_count"],
                "project_count": len(bucket["projects"]),
            }
            for bucket in sorted(groups.values(), key=lambda item: (-item["total_amount"], item["expense_type"]))
        ]

    def _refreshing_explorer_payload(self, month: str, project_scope: str, *, reason: str) -> dict[str, Any]:
        scope_key = self._runtime_service.request_scope_key(month, project_scope)
        refresh_enqueued = self._runtime_service.enqueue_read_model_refresh(scope_key, reason=reason)
        payload = self.empty_explorer_payload(month)
        payload["error"] = "read_model_unavailable"
        payload["read_model_status"] = "refreshing"
        payload["read_model_scope_key"] = scope_key
        payload["refresh_reason"] = reason
        payload["refresh_enqueued"] = refresh_enqueued
        return payload

    def _refreshing_month_payload(self, month: str, project_scope: str, *, reason: str) -> dict[str, Any]:
        scope_key = self._runtime_service.request_scope_key(month, project_scope)
        refresh_enqueued = self._runtime_service.enqueue_read_model_refresh(scope_key, reason=reason)
        payload = self.empty_month_payload(month)
        payload["error"] = "read_model_unavailable"
        payload["read_model_status"] = "refreshing"
        payload["read_model_scope_key"] = scope_key
        payload["refresh_reason"] = reason
        payload["refresh_enqueued"] = refresh_enqueued
        return payload

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
            "bank_flow_summary": {
                "row_count": 0,
                "transaction_count": 0,
                "total_amount": "0.00",
            },
            "bank_flow_time_rows": [],
            "bank_accounts": [],
            "project_rows": [],
            "expense_type_rows": [],
        }

    @staticmethod
    def _is_explorer_payload(payload: dict[str, Any]) -> bool:
        summary = payload.get("summary")
        if not isinstance(summary, dict):
            return False
        bank_flow_summary = payload.get("bank_flow_summary")
        if bank_flow_summary is not None and not isinstance(bank_flow_summary, dict):
            return False
        return all(
            isinstance(payload.get(key), list)
            for key in ("time_rows", "bank_accounts", "project_rows", "expense_type_rows")
        ) and (
            "bank_flow_time_rows" not in payload or isinstance(payload.get("bank_flow_time_rows"), list)
        )

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

    def _build_export_preview_from_read_model(self, **kwargs: Any) -> dict[str, Any]:
        view = str(kwargs.get("view") or "").strip()
        month = str(kwargs.get("month") or "all")
        project_scope = str(kwargs.get("project_scope") or "active")
        project_names = self._normalize_text_set(
            kwargs.get("project_names") or ([kwargs.get("project_name")] if kwargs.get("project_name") else [])
        )
        expense_types = self._normalize_text_set(kwargs.get("expense_types"))
        aggregate_by = self._normalize_project_aggregate_by(kwargs.get("aggregate_by"))
        range_kwargs = self._range_kwargs(kwargs)
        if view == "time":
            entries = self._filtered_entries_from_read_model(
                month=month,
                project_scope=project_scope,
                rows_key="bank_flow_time_rows",
                **range_kwargs,
            )
            self._ensure_export_row_limit(view=view, total=len(entries))
            scope_label = self._build_scope_label(month=month, **range_kwargs)
            return self._preview_payload(
                view=view,
                file_name=self._build_filename(month=scope_label, view=view),
                scope_label=scope_label,
                sheet_names=["按时间统计"],
                columns=["时间", "项目名称", "费用类型", "金额", "费用内容", "资金方向", "对方户名", "支付账户"],
                rows=[
                    [
                        entry["trade_time"],
                        entry["project_name"],
                        entry["expense_type"],
                        _plain_money(entry["amount_decimal"]),
                        entry["expense_content"],
                        entry["direction"],
                        entry["counterparty_name"],
                        entry["payment_account_label"],
                    ]
                    for entry in entries
                ],
                total_amount=_plain_money(sum((entry["amount_decimal"] for entry in entries), start=Decimal("0.00"))),
            )
        if view == "project":
            if not project_names:
                raise ValueError("project_name is required for project export preview")
            if aggregate_by is not None or len(project_names) > 1:
                entries = self._filtered_entries_from_read_model(
                    month="all",
                    project_scope=project_scope,
                    project_names=project_names,
                    expense_types=expense_types,
                    **range_kwargs,
                )
                self._ensure_export_row_limit(view=view, total=len(entries))
                rows = self._project_aggregate_rows(entries, aggregate_by=aggregate_by or "month")
                scope_label = self._build_scope_label(month="all", **range_kwargs)
                return self._preview_payload(
                    view=view,
                    file_name=self._build_filename(
                        month=scope_label,
                        view=view,
                        project_names=sorted(project_names),
                        aggregate_by=aggregate_by or "month",
                    ),
                    scope_label=scope_label,
                    sheet_names=["按项目统计"],
                    columns=["统计周期", "项目名称", "费用类型", "金额", "费用内容", "支出笔数"],
                    rows=[
                        [
                            row["period_label"],
                            row["project_name"],
                            row["expense_type"],
                            row["amount"],
                            row["expense_content"],
                            str(row["transaction_count"]),
                        ]
                        for row in rows
                    ],
                    total_amount=_plain_money(sum((row["amount_decimal"] for row in rows), start=Decimal("0.00"))),
                )
            project_name = sorted(project_names)[0]
            entries = self._filtered_entries_from_read_model(
                month=month,
                project_scope=project_scope,
                project_names={project_name},
                expense_types=expense_types,
                **range_kwargs,
            )
            self._ensure_export_row_limit(view=view, total=len(entries))
            scope_label = self._build_scope_label(month=month, **range_kwargs)
            return self._preview_payload(
                view=view,
                file_name=self._build_filename(month=scope_label, view=view, project_name=project_name),
                scope_label=scope_label,
                sheet_names=self._project_sheet_names(
                    include_oa_details=True,
                    include_invoice_details=True,
                    include_exception_rows=True,
                    include_ignored_rows=True,
                    include_expense_content_summary=True,
                ),
                columns=["时间", "资金方向", "费用类型", "金额", "费用内容", "对方户名", "支付账户"],
                rows=[
                    [
                        entry["trade_time"],
                        entry["direction"],
                        entry["expense_type"],
                        _plain_money(entry["amount_decimal"]),
                        entry["expense_content"],
                        entry["counterparty_name"],
                        entry["payment_account_label"],
                    ]
                    for entry in entries
                ],
                total_amount=_plain_money(sum((entry["amount_decimal"] for entry in entries), start=Decimal("0.00"))),
            )
        if view == "expense_type":
            if not expense_types:
                raise ValueError("expense_type is required for expense_type export preview")
            entries = self._filtered_entries_from_read_model(
                month=month,
                project_scope=project_scope,
                expense_types=expense_types,
                **range_kwargs,
            )
            self._ensure_export_row_limit(view=view, total=len(entries))
            scope_label = self._build_scope_label(month=month, **range_kwargs)
            expense_label = self._build_expense_type_label(expense_types)
            return self._preview_payload(
                view=view,
                file_name=self._build_filename(month=scope_label, view=view, expense_type=expense_label),
                scope_label=scope_label,
                sheet_names=["按费用类型统计"],
                columns=["时间", "项目名称", "资金方向", "金额", "费用内容", "对方户名", "支付账户"],
                rows=[
                    [
                        entry["trade_time"],
                        entry["project_name"],
                        entry["direction"],
                        _plain_money(entry["amount_decimal"]),
                        entry["expense_content"],
                        entry["counterparty_name"],
                        entry["payment_account_label"],
                    ]
                    for entry in entries
                ],
                total_amount=_plain_money(sum((entry["amount_decimal"] for entry in entries), start=Decimal("0.00"))),
            )
        raise ValueError("view must be time, project, or expense_type.")

    def _export_view_from_read_model(self, **kwargs: Any) -> tuple[str, bytes]:
        view = str(kwargs.get("view") or "").strip()
        month = str(kwargs.get("month") or "all")
        project_scope = str(kwargs.get("project_scope") or "active")
        project_names = self._normalize_text_set(
            kwargs.get("project_names") or ([kwargs.get("project_name")] if kwargs.get("project_name") else [])
        )
        expense_types = self._normalize_text_set(kwargs.get("expense_types"))
        aggregate_by = self._normalize_project_aggregate_by(kwargs.get("aggregate_by"))
        range_kwargs = self._range_kwargs(kwargs)
        if view == "time":
            entries = self._filtered_entries_from_read_model(
                month=month,
                project_scope=project_scope,
                rows_key="bank_flow_time_rows",
                **range_kwargs,
            )
            self._ensure_export_row_limit(view=view, total=len(entries))
            rows = [self._time_row_from_entry(entry) for entry in entries]
            workbook = self._table_workbook(
                "按时间统计",
                ["时间", "项目名称", "费用类型", "金额", "费用内容", "资金方向", "对方户名", "支付账户"],
                rows,
            )
            return (
                self._build_filename(month=self._build_scope_label(month=month, **range_kwargs), view=view),
                self._serialize_workbook(workbook),
            )
        if view == "month":
            payload = self.month_payload_from_explorer_payload(
                month,
                self._require_fresh_explorer(month, project_scope, message="成本统计数据正在刷新，请稍后重试导出。"),
            )
            self._ensure_export_row_limit(view=view, total=int((payload.get("summary") or {}).get("row_count") or 0))
            rows = [
                [row["project_name"], row["expense_type"], row["amount"], row["expense_content"], row["transaction_count"]]
                for row in list(payload.get("rows") or [])
                if isinstance(row, dict)
            ]
            workbook = self._table_workbook("月份汇总", ["项目名称", "费用类型", "金额", "费用内容", "支出笔数"], rows)
            return self._build_filename(month=month, view=view), self._serialize_workbook(workbook)
        if view == "project":
            if not project_names:
                raise ValueError("project_name is required for project export")
            if aggregate_by is not None or len(project_names) > 1:
                entries = self._filtered_entries_from_read_model(
                    month="all",
                    project_scope=project_scope,
                    project_names=project_names,
                    expense_types=expense_types,
                    **range_kwargs,
                )
                self._ensure_export_row_limit(view=view, total=len(entries))
                rows = self._project_aggregate_rows(entries, aggregate_by=aggregate_by or "month")
                workbook = self._table_workbook(
                    "按项目统计",
                    ["统计周期", "项目名称", "费用类型", "金额", "费用内容", "支出笔数"],
                    [
                        [
                            row["period_label"],
                            row["project_name"],
                            row["expense_type"],
                            row["amount"],
                            row["expense_content"],
                            row["transaction_count"],
                        ]
                        for row in rows
                    ],
                )
                filename = self._build_filename(
                    month=self._build_scope_label(month="all", **range_kwargs),
                    view=view,
                    project_names=sorted(project_names),
                    aggregate_by=aggregate_by or "month",
                )
                return filename, self._serialize_workbook(workbook)
            project_name = sorted(project_names)[0]
            entries = self._filtered_entries_from_read_model(
                month=month,
                project_scope=project_scope,
                project_names={project_name},
                expense_types=expense_types,
                **range_kwargs,
            )
            self._ensure_export_row_limit(view=view, total=len(entries))
            workbook = self._project_detail_workbook(
                month=month,
                project_name=project_name,
                entries=entries,
                include_oa_details=bool(kwargs.get("include_oa_details", True)),
                include_invoice_details=bool(kwargs.get("include_invoice_details", True)),
                include_exception_rows=bool(kwargs.get("include_exception_rows", True)),
                include_ignored_rows=bool(kwargs.get("include_ignored_rows", True)),
                include_expense_content_summary=bool(kwargs.get("include_expense_content_summary", True)),
                scope_label=self._build_scope_label(month=month, **range_kwargs),
            )
            return (
                self._build_filename(
                    month=self._build_scope_label(month=month, **range_kwargs),
                    view=view,
                    project_name=project_name,
                ),
                self._serialize_workbook(workbook),
            )
        if view == "expense_type":
            if not expense_types:
                raise ValueError("expense_type is required for expense_type export")
            entries = self._filtered_entries_from_read_model(
                month=month,
                project_scope=project_scope,
                expense_types=expense_types,
                **range_kwargs,
            )
            self._ensure_export_row_limit(view=view, total=len(entries))
            rows = [
                [
                    entry["trade_time"],
                    entry["project_name"],
                    _plain_money(entry["amount_decimal"]),
                    entry["expense_content"],
                    entry["direction"],
                    entry["counterparty_name"],
                    entry["payment_account_label"],
                ]
                for entry in entries
            ]
            workbook = self._table_workbook(
                "按费用类型统计",
                ["时间", "项目名称", "金额", "费用内容", "资金方向", "对方户名", "支付账户"],
                rows,
            )
            filename = self._build_filename(
                month=self._build_scope_label(month=month, **range_kwargs),
                view=view,
                expense_type=self._build_expense_type_label(expense_types),
            )
            return filename, self._serialize_workbook(workbook)
        if view == "transaction":
            transaction_id = str(kwargs.get("transaction_id") or "").strip()
            if not transaction_id:
                raise ValueError("transaction_id is required for transaction export")
            payload = self.get_transaction_detail(transaction_id, project_scope=project_scope)
            workbook = self._transaction_workbook(payload)
            filename = self._build_filename(
                month=payload["month"],
                view=view,
                project_name=payload["transaction"]["project_name"],
                transaction_id=transaction_id,
            )
            return filename, self._serialize_workbook(workbook)
        raise ValueError(f"unsupported export view: {view}")

    def _filtered_entries_from_read_model(
        self,
        *,
        month: str,
        project_scope: str,
        start_month: str | None = None,
        end_month: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        project_names: set[str] | None = None,
        expense_types: set[str] | None = None,
        rows_key: str = "time_rows",
    ) -> list[dict[str, Any]]:
        payload = self._require_fresh_explorer(month, project_scope, message="成本统计数据正在刷新，请稍后重试导出。")
        entries = self._entries_from_explorer_payload(payload, rows_key=rows_key)
        if start_month and end_month and start_month > end_month:
            start_month, end_month = end_month, start_month
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date
        filtered: list[dict[str, Any]] = []
        for entry in entries:
            entry_month = entry["month"] or (entry["trade_time"] or "")[:7]
            trade_date = (entry["trade_time"] or "")[:10]
            if start_month and entry_month < start_month:
                continue
            if end_month and entry_month > end_month:
                continue
            if start_date and (not trade_date or trade_date < start_date):
                continue
            if end_date and (not trade_date or trade_date > end_date):
                continue
            if project_names and entry["project_name"] not in project_names:
                continue
            if expense_types and entry["expense_type"] not in expense_types:
                continue
            filtered.append(entry)
        return sorted(filtered, key=lambda item: (item["trade_time"], item["transaction_id"]), reverse=True)

    @staticmethod
    def _single_month_from_range(
        *,
        start_month: str | None,
        end_month: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> str | None:
        if not start_month and start_date:
            start_month = start_date[:7]
        if not end_month and end_date:
            end_month = end_date[:7]
        if start_month and end_month and start_month == end_month:
            return start_month
        return None

    @staticmethod
    def _entries_from_explorer_payload(payload: dict[str, Any], *, rows_key: str = "time_rows") -> list[dict[str, Any]]:
        rows = payload.get(rows_key)
        if not isinstance(rows, list):
            return []
        entries: list[dict[str, Any]] = []
        payload_month = str(payload.get("month") or "")
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            trade_time = str(raw_row.get("trade_time") or "")
            amount = _decimal_from_value(raw_row.get("amount")) or Decimal("0.00")
            label_path = [
                str(item).strip()
                for item in list(raw_row.get("bank_tag_label_path") or [])
                if str(item).strip()
            ]
            primary = str(raw_row.get("bank_tag_primary_label") or "").strip() or "未标记"
            sub = str(raw_row.get("bank_tag_sub_label") or raw_row.get("bank_tag_label") or "").strip() or primary
            if not label_path:
                label_path = [primary] if primary == sub else [primary, sub]
            entries.append(
                {
                    "transaction_id": str(raw_row.get("transaction_id") or "").strip(),
                    "month": str(raw_row.get("month") or "")[:7] or trade_time[:7] or payload_month,
                    "trade_time": trade_time,
                    "direction": str(raw_row.get("direction") or "支出"),
                    "project_name": str(raw_row.get("project_name") or "").strip(),
                    "expense_type": str(raw_row.get("expense_type") or "").strip(),
                    "expense_content": str(raw_row.get("expense_content") or "").strip(),
                    "amount_decimal": amount,
                    "counterparty_name": str(raw_row.get("counterparty_name") or "").strip(),
                    "payment_account_label": str(raw_row.get("payment_account_label") or "").strip(),
                    "remark": str(raw_row.get("remark") or "").strip(),
                    "oa_applicant": str(raw_row.get("oa_applicant") or "—").strip() or "—",
                    "bank_tag_code": str(raw_row.get("bank_tag_code") or "").strip(),
                    "bank_tag_label": str(raw_row.get("bank_tag_label") or sub).strip() or sub,
                    "bank_tag_primary_label": primary,
                    "bank_tag_sub_label": sub,
                    "bank_tag_label_path": label_path,
                }
            )
        return entries

    @staticmethod
    def _summary_from_entries(entries: list[dict[str, Any]], *, row_count: int | None = None) -> dict[str, Any]:
        return {
            "row_count": len(entries) if row_count is None else row_count,
            "transaction_count": len(entries),
            "total_amount": _plain_money(sum((entry["amount_decimal"] for entry in entries), start=Decimal("0.00"))),
        }

    @staticmethod
    def _range_kwargs(kwargs: dict[str, Any]) -> dict[str, str | None]:
        return {
            "start_month": str(kwargs.get("start_month") or "").strip() or None,
            "end_month": str(kwargs.get("end_month") or "").strip() or None,
            "start_date": str(kwargs.get("start_date") or "").strip() or None,
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
        return {str(value).strip() for value in iterable if str(value or "").strip()}

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
        total_amount: str,
    ) -> dict[str, Any]:
        return {
            "view": view,
            "file_name": file_name,
            "scope_label": scope_label,
            "summary": {
                "row_count": len(rows),
                "transaction_count": len(rows),
                "total_amount": total_amount,
                "sheet_count": len(sheet_names),
            },
            "sheet_names": sheet_names,
            "columns": columns,
            "rows": rows[:8],
        }

    @staticmethod
    def _time_row_from_entry(entry: dict[str, Any]) -> list[Any]:
        return [
            entry["trade_time"],
            entry["project_name"],
            entry["expense_type"],
            _plain_money(entry["amount_decimal"]),
            entry["expense_content"],
            entry["direction"],
            entry["counterparty_name"],
            entry["payment_account_label"],
        ]

    @staticmethod
    def _project_aggregate_rows(entries: list[dict[str, Any]], *, aggregate_by: str) -> list[dict[str, Any]]:
        buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for entry in entries:
            period_label = (entry["trade_time"] or "")[:7] if aggregate_by == "month" else (entry["trade_time"] or "")[:4]
            key = (period_label, entry["project_name"], entry["expense_type"], entry["expense_content"])
            bucket = buckets.setdefault(
                key,
                {
                    "period_label": period_label or "—",
                    "project_name": entry["project_name"],
                    "expense_type": entry["expense_type"],
                    "expense_content": entry["expense_content"],
                    "amount_decimal": Decimal("0.00"),
                    "transaction_count": 0,
                },
            )
            bucket["amount_decimal"] = bucket["amount_decimal"] + entry["amount_decimal"]
            bucket["transaction_count"] = int(bucket["transaction_count"]) + 1
        return [
            {**bucket, "amount": _plain_money(bucket["amount_decimal"])}
            for bucket in sorted(
                buckets.values(),
                key=lambda item: (item["period_label"], item["project_name"], item["expense_type"], item["expense_content"]),
            )
        ]

    @staticmethod
    def _build_expense_type_label(expense_types: set[str]) -> str:
        ordered = sorted(expense_types)
        if not ordered:
            return "未命名费用类型"
        if len(ordered) == 1:
            return ordered[0]
        return f"{ordered[0]}等{len(ordered)}类"

    @staticmethod
    def _project_sheet_names(
        *,
        include_oa_details: bool,
        include_invoice_details: bool,
        include_exception_rows: bool,
        include_ignored_rows: bool,
        include_expense_content_summary: bool,
    ) -> list[str]:
        sheet_names = ["导出说明", "项目汇总", "按费用类型汇总"]
        if include_expense_content_summary:
            sheet_names.append("按费用内容汇总")
        sheet_names.append("流水明细")
        if include_oa_details:
            sheet_names.append("OA关联明细")
        if include_invoice_details:
            sheet_names.append("发票关联明细")
        if include_exception_rows or include_ignored_rows:
            sheet_names.append("异常与未闭环")
        return sheet_names

    @staticmethod
    def _table_workbook(title: str, headers: list[str], rows: list[list[Any]]) -> Workbook:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = title
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        for index in range(1, len(headers) + 1):
            sheet.column_dimensions[chr(64 + index)].width = 18
        return workbook

    def _project_detail_workbook(
        self,
        *,
        month: str,
        project_name: str,
        entries: list[dict[str, Any]],
        include_oa_details: bool,
        include_invoice_details: bool,
        include_exception_rows: bool,
        include_ignored_rows: bool,
        include_expense_content_summary: bool,
        scope_label: str,
    ) -> Workbook:
        workbook = Workbook()
        intro_sheet = workbook.active
        intro_sheet.title = "导出说明"
        self._fill_key_value_sheet(
            intro_sheet,
            [
                ("项目名称", project_name),
                ("统计范围", scope_label),
                ("月份列表", month),
                ("数据口径", "成本统计 read model fresh payload"),
                ("导出结构", "项目汇总、费用类型汇总、流水明细"),
            ],
        )
        total_amount = sum((entry["amount_decimal"] for entry in entries), start=Decimal("0.00"))
        summary_sheet = workbook.create_sheet("项目汇总")
        self._fill_key_value_sheet(
            summary_sheet,
            [
                ("项目名称", project_name),
                ("统计期间", scope_label),
                ("总支出金额", _plain_money(total_amount)),
                ("支出流水笔数", len(entries)),
                ("费用类型数", len({entry["expense_type"] for entry in entries})),
                ("已关联OA笔数", 0),
                ("已关联发票笔数", 0),
                ("已处理异常笔数", 0),
                ("已忽略笔数", 0),
            ],
        )
        expense_type_rows, expense_content_rows = self._project_summary_rows(entries)
        self._append_table_sheet(
            workbook.create_sheet("按费用类型汇总"),
            ["费用类型", "金额", "占比", "笔数", "费用内容数"],
            [
                [row["expense_type"], row["total_amount"], row["percentage"], row["transaction_count"], row["expense_content_count"]]
                for row in expense_type_rows
            ],
        )
        if include_expense_content_summary:
            self._append_table_sheet(
                workbook.create_sheet("按费用内容汇总"),
                ["费用类型", "费用内容", "金额", "笔数"],
                [
                    [row["expense_type"], row["expense_content"], row["total_amount"], row["transaction_count"]]
                    for row in expense_content_rows
                ],
            )
        self._append_table_sheet(
            workbook.create_sheet("流水明细"),
            ["时间", "交易流水ID", "资金方向", "对方户名", "支付账户", "金额", "备注", "项目名称", "费用类型", "费用内容", "OA单号", "关联组ID"],
            [
                [
                    entry["trade_time"],
                    entry["transaction_id"],
                    entry["direction"],
                    entry["counterparty_name"],
                    entry["payment_account_label"],
                    _plain_money(entry["amount_decimal"]),
                    entry["remark"],
                    entry["project_name"],
                    entry["expense_type"],
                    entry["expense_content"],
                    "—",
                    "—",
                ]
                for entry in entries
            ],
        )
        if include_oa_details:
            self._append_table_sheet(workbook.create_sheet("OA关联明细"), ["OA单号", "申请人", "项目名称", "费用类型", "费用内容", "OA金额", "关联组ID"], [])
        if include_invoice_details:
            self._append_table_sheet(workbook.create_sheet("发票关联明细"), ["发票号码", "销方名称", "购方名称", "发票金额", "税额", "项目名称", "关联状态", "关联组ID"], [])
        if include_exception_rows or include_ignored_rows:
            self._append_table_sheet(workbook.create_sheet("异常与未闭环"), ["记录类型", "记录ID", "项目名称", "费用类型", "金额", "状态", "备注"], [])
        return workbook

    @staticmethod
    def _project_summary_rows(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        total_amount = sum((entry["amount_decimal"] for entry in entries), start=Decimal("0.00"))
        type_buckets: dict[str, dict[str, Any]] = {}
        content_buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in entries:
            type_bucket = type_buckets.setdefault(
                entry["expense_type"],
                {
                    "expense_type": entry["expense_type"],
                    "amount_decimal": Decimal("0.00"),
                    "transaction_count": 0,
                    "expense_contents": set(),
                },
            )
            type_bucket["amount_decimal"] = type_bucket["amount_decimal"] + entry["amount_decimal"]
            type_bucket["transaction_count"] = int(type_bucket["transaction_count"]) + 1
            type_bucket["expense_contents"].add(entry["expense_content"])
            content_key = (entry["expense_type"], entry["expense_content"])
            content_bucket = content_buckets.setdefault(
                content_key,
                {
                    "expense_type": entry["expense_type"],
                    "expense_content": entry["expense_content"],
                    "amount_decimal": Decimal("0.00"),
                    "transaction_count": 0,
                },
            )
            content_bucket["amount_decimal"] = content_bucket["amount_decimal"] + entry["amount_decimal"]
            content_bucket["transaction_count"] = int(content_bucket["transaction_count"]) + 1
        type_rows = [
            {
                "expense_type": bucket["expense_type"],
                "total_amount": _plain_money(bucket["amount_decimal"]),
                "percentage": _percentage(bucket["amount_decimal"], total_amount),
                "transaction_count": bucket["transaction_count"],
                "expense_content_count": len(bucket["expense_contents"]),
            }
            for bucket in sorted(type_buckets.values(), key=lambda item: (-item["amount_decimal"], item["expense_type"]))
        ]
        content_rows = [
            {
                "expense_type": bucket["expense_type"],
                "expense_content": bucket["expense_content"],
                "total_amount": _plain_money(bucket["amount_decimal"]),
                "transaction_count": bucket["transaction_count"],
            }
            for bucket in sorted(
                content_buckets.values(),
                key=lambda item: (-item["amount_decimal"], item["expense_type"], item["expense_content"]),
            )
        ]
        return type_rows, content_rows

    @staticmethod
    def _transaction_workbook(payload: dict[str, Any]) -> Workbook:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "流水详情"
        transaction = payload["transaction"]
        sheet.append(["字段", "值"])
        for key, value in [
            ("交易ID", transaction["id"]),
            ("月份", payload["month"]),
            ("项目名称", transaction["project_name"]),
            ("费用类型", transaction["expense_type"]),
            ("费用内容", transaction["expense_content"]),
            ("交易时间", transaction["trade_time"]),
            ("资金方向", transaction["direction"]),
            ("金额", transaction["amount"]),
            ("对方户名", transaction["counterparty_name"]),
            ("OA提交人", transaction["oa_applicant"]),
            ("支付账户", transaction["payment_account_label"]),
            ("备注", transaction["remark"]),
        ]:
            sheet.append([key, value])
        sheet.column_dimensions["A"].width = 22
        sheet.column_dimensions["B"].width = 52
        return workbook

    @staticmethod
    def _fill_key_value_sheet(sheet: Any, rows: list[tuple[str, Any]]) -> None:
        sheet.append(["字段", "值"])
        for key, value in rows:
            sheet.append([key, value])
        sheet.column_dimensions["A"].width = 18
        sheet.column_dimensions["B"].width = 52

    @staticmethod
    def _append_table_sheet(sheet: Any, headers: list[str], rows: list[list[Any]]) -> None:
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        for index in range(1, len(headers) + 1):
            sheet.column_dimensions[chr(64 + index)].width = 18

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
        expense_type: str | None = None,
        transaction_id: str | None = None,
    ) -> str:
        month_segment = "全部期间" if (month or "").strip().lower() == "all" else month
        if view == "time":
            return f"成本统计_{month_segment}_按时间统计.xlsx"
        if view == "month":
            return f"成本统计_{month_segment}_月份汇总.xlsx"
        if view == "project":
            if aggregate_by is not None:
                project_label = "、".join(project_names or ([project_name] if project_name else [])) or "未命名项目"
                return f"成本统计_{month_segment}_按项目统计_按{'月' if aggregate_by == 'month' else '年'}_{_sanitize_filename(project_label)}.xlsx"
            return f"成本统计_{month_segment}_项目明细_{_sanitize_filename(project_name or '未命名项目')}.xlsx"
        if view == "expense_type":
            return f"成本统计_{month_segment}_按费用类型统计_{_sanitize_filename(expense_type or '未命名费用类型')}.xlsx"
        return f"成本统计_{month_segment}_流水详情_{_sanitize_filename(project_name or '未命名项目')}_{_sanitize_filename(transaction_id or 'unknown')}.xlsx"


def _plain_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _decimal_from_value(value: object) -> Decimal | None:
    if value in (None, "", "--", "—"):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return None


def _percentage(value: Decimal, total: Decimal) -> str:
    if total == Decimal("0.00"):
        return "0.00%"
    return f"{(value / total * Decimal('100')).quantize(Decimal('0.01'))}%"


def _sanitize_filename(value: str) -> str:
    sanitized = str(value or "").strip().replace("/", "-").replace("\\", "-").replace(":", "：")
    return sanitized[:80] if len(sanitized) > 80 else sanitized
