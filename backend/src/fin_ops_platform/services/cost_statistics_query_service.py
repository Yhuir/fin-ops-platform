from __future__ import annotations

import base64
from decimal import Decimal
import hashlib
from io import BytesIO
import json
import re
from typing import Any, Callable

from openpyxl import Workbook

from fin_ops_platform.services.app_settings_service import COST_STATISTICS_UNCATEGORIZED_TAG_CODE
from fin_ops_platform.services.cost_statistics_source_versions import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
    cost_statistics_bank_flow_source_versions,
    cost_statistics_semantic_source_versions,
    cost_statistics_source_versions,
    cost_statistics_workbench_dependency_source_versions,
)
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    resolve_read_model_freshness,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.read_model_query_gateway import (
    ReadModelQueryGateway,
    ReadModelRefreshQueueAdapter,
)

COST_STATISTICS_EXPORT_ROW_LIMIT = 20000
COST_STATISTICS_EXPORT_BATCH_SIZE = 1000
COST_STATISTICS_EXPORT_PREVIEW_SIZE = 8


class CostStatisticsExportLimitError(ValueError):
    def __init__(self, *, view: str, total: int, limit: int = COST_STATISTICS_EXPORT_ROW_LIMIT) -> None:
        super().__init__(f"当前筛选命中 {total} 行，超过 {limit} 行导出上限，请缩小筛选范围。")
        self.error_code = "cost_statistics_export_row_limit_exceeded"
        self.details = {"view": view, "total": total, "limit": limit}


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
        tag_selection_mapper: Callable[[dict[str, Any]], dict[str, Any]],
        workbench_dependency_versions_provider: Callable[
            [str], tuple[dict[str, Any], dict[str, Any]]
        ],
        workbench_dependency_versions_by_scope_provider: Callable[
            [], tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]
        ],
        workbench_refresh_enqueuer: Callable[..., bool],
        bank_detail_refresh_enqueuer: Callable[..., bool] | None = None,
    ) -> None:
        self._runtime_service = runtime_service
        self._sql_read_repository = sql_read_repository
        self._tag_selection_mapper = tag_selection_mapper
        self._workbench_dependency_versions_provider = workbench_dependency_versions_provider
        self._workbench_dependency_versions_by_scope_provider = (
            workbench_dependency_versions_by_scope_provider
        )
        self._workbench_refresh_enqueuer = workbench_refresh_enqueuer
        self._bank_detail_refresh_enqueuer = bank_detail_refresh_enqueuer
        self._read_model_query_gateway = ReadModelQueryGateway(
            queue_repository=ReadModelRefreshQueueAdapter(
                scope_type="cost_statistics",
                refresh_enqueuer=self._runtime_service.enqueue_read_model_refresh,
            ),
            redis_helper=redis_helper,
        )

    def get_explorer_page(
        self,
        *,
        scope: str,
        view: str,
        project_scope: str,
        filters: dict[str, str | None],
        cursor: str | None,
        page_size: int,
        if_none_match: str | None = None,
    ) -> tuple[dict[str, Any], bool, str, bool]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        scope_kind, scope_value, normalized_scope = self._normalize_page_scope(scope)
        normalized_view, normalized_filters = self._normalize_page_query(view, filters)
        normalized_page_size = self._normalize_page_size(page_size)
        gate_scope_month = scope_value if scope_kind == "month" else "all"
        gate_scope_key = self._runtime_service.request_scope_key(gate_scope_month, normalized_project_scope)
        get_page = getattr(self._sql_read_repository, "get_cost_statistics_page", None)
        get_freshness_gate = getattr(self._sql_read_repository, "get_cost_statistics_freshness_gate", None)
        empty_payload = lambda: self.empty_explorer_page_payload(normalized_scope, normalized_view)
        if not callable(get_page) or not callable(get_freshness_gate):
            payload = self._cost_statistics_non_fresh_gate_payload(
                scope_key=gate_scope_key,
                empty_payload_factory=empty_payload,
                refresh_reason="api_page_sql_repository_unavailable",
                stale_reasons=(),
            )
            return payload, False, "", False

        gate, expected_source_versions, non_fresh_payload = self._cost_statistics_freshness_gate(
            scope_key=gate_scope_key,
            get_freshness_gate=get_freshness_gate,
            empty_payload_factory=empty_payload,
            missing_reason="api_page_miss",
            stale_reason="api_page_stale",
            source_mismatch_reason="api_page_source_versions_stale",
            dependency_profile=(
                "bank_flow"
                if normalized_view in {"time", "bank_tag"}
                else "workbench"
            ),
        )
        if non_fresh_payload is not None:
            return non_fresh_payload, False, "", False
        if gate is None or expected_source_versions is None:
            return empty_payload(), False, "", False

        tag_selection_payload = self._cost_tag_selection_payload_from_gate(gate)
        selected_codes = self._selected_bank_tag_codes(tag_selection_payload)
        statistics_status = str(gate.get("statistics_status") or "stale").strip().lower()
        statistics = gate.get("statistics") if statistics_status == "fresh" else None
        statistics_refresh_enqueued = False
        if statistics_status != "fresh":
            statistics_workbench_scope_keys = self._normalized_refresh_scope_keys(
                gate.get("statistics_workbench_refresh_scope_keys")
            )
            statistics_child_scope_keys = self._normalized_refresh_scope_keys(
                gate.get("statistics_child_refresh_scope_keys")
            )
            if statistics_workbench_scope_keys:
                statistics_refresh_results = [
                    bool(
                        self._workbench_refresh_enqueuer(
                            workbench_scope_key,
                            reason="cost_statistics_workbench_dependency_stale",
                        )
                    )
                    for workbench_scope_key in statistics_workbench_scope_keys
                ]
                statistics_refresh_enqueued = any(statistics_refresh_results)
            elif statistics_child_scope_keys:
                statistics_refresh_results = [
                    bool(
                        self._runtime_service.enqueue_read_model_refresh(
                            child_scope_key,
                            reason=f"api_statistics_{statistics_status}",
                        )
                    )
                    for child_scope_key in statistics_child_scope_keys
                ]
                statistics_refresh_enqueued = any(statistics_refresh_results)
            else:
                statistics_refresh_enqueued = self._runtime_service.enqueue_read_model_refresh(
                    str(gate.get("statistics_scope_key") or f"{normalized_project_scope}:all"),
                    reason=f"api_statistics_{statistics_status}",
                )
        statistics_published_source_version = gate.get("statistics_published_source_version")
        query_binding = self._page_query_binding(
            scope=normalized_scope,
            view=normalized_view,
            filters=normalized_filters,
            page_size=normalized_page_size,
        )
        cursor_values = self._decode_page_cursor(
            cursor,
            query_binding=query_binding,
            published_source_version=int(gate["published_source_version"]),
        )
        query_fingerprint = self._page_query_fingerprint(query_binding, cursor)
        tag_token = self._cost_tag_selection_cache_token(tag_selection_payload)
        etag = self._page_etag(
            scope_key=gate_scope_key,
            published_source_version=int(gate["published_source_version"]),
            statistics_published_source_version=(
                int(statistics_published_source_version)
                if statistics_published_source_version is not None
                else None
            ),
            statistics_status=statistics_status,
            query_fingerprint=query_fingerprint,
            tag_token=tag_token,
        )
        if self._etag_matches(if_none_match, etag):
            return {}, False, etag, True

        def load_page_view() -> dict[str, Any] | None:
            raw_page = get_page(
                project_scope=normalized_project_scope,
                scope_kind=scope_kind,
                scope_value=scope_value,
                view=normalized_view,
                filters=normalized_filters,
                selected_tag_codes=sorted(selected_codes) if selected_codes is not None else None,
                cursor_values=cursor_values,
                page_size=normalized_page_size,
            )
            if not isinstance(raw_page, dict):
                return None
            payload = self._normalize_explorer_page_payload(
                raw_page,
                scope=normalized_scope,
                view=normalized_view,
                query_binding=query_binding,
                published_source_version=int(gate["published_source_version"]),
                bank_accounts=list(gate.get("bank_accounts") or []),
                statistics=dict(statistics) if isinstance(statistics, dict) else None,
                statistics_status=statistics_status,
                statistics_refresh_enqueued=statistics_refresh_enqueued,
            )
            payload["cost_statistics_tag_selection_version"] = (
                int(tag_selection_payload.get("version") or 1)
                if isinstance(tag_selection_payload, dict)
                else 1
            )
            return {
                "payload": payload,
                "source_versions": expected_source_versions,
                "schema_version": gate.get("schema_version"),
                "generated_at": gate.get("generated_at"),
                "refresh_status": "fresh",
            }

        cache_key = self._runtime_service.page_redis_cache_key(
            gate_scope_key,
            query_fingerprint,
            source_versions={
                **expected_source_versions,
                "cost_statistics_published_source_version": gate["published_source_version"],
                "cost_statistics_statistics_published_source_version": (
                    statistics_published_source_version
                    if statistics_published_source_version is not None
                    else f"{statistics_status}:missing"
                ),
                "cost_statistics_statistics_status": statistics_status,
                "cost_statistics_tag_selection": tag_token,
            },
        )
        result = self._read_model_query_gateway.load(
            scope_type="cost_statistics",
            scope_key=gate_scope_key,
            expected_schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            expected_source_versions=expected_source_versions,
            load_view=load_page_view,
            load_freshness_view=lambda: {
                "payload": {},
                "source_versions": expected_source_versions,
                "schema_version": gate.get("schema_version"),
                "generated_at": gate.get("generated_at"),
                "refresh_status": "fresh",
            },
            empty_payload_factory=empty_payload,
            payload_validator=self._is_explorer_page_payload,
            cache_key=cache_key,
            cache_ttl_seconds=self._runtime_service.redis_ttl_seconds(),
            missing_reason="api_page_miss",
            stale_reason="api_page_stale",
            source_mismatch_reason="api_page_source_versions_stale",
            payload_invalid_reason="api_page_payload_shape_invalid",
        )
        payload = self._empty_non_fresh_payload(result.payload, empty_payload)
        return payload, result.cache_hit, etag, False

    def get_transaction_detail(
        self,
        transaction_id: str,
        *,
        project_scope: str,
        view: str,
        scope: str,
    ) -> dict[str, Any]:
        normalized_project_scope = self._normalize_project_scope(project_scope)
        scope_kind, scope_value, _normalized_scope = self._normalize_page_scope(scope)
        normalized_view, _filters = self._normalize_page_query(view, {})
        dependency_profile = (
            "bank_flow"
            if normalized_view in {"time", "bank_tag"}
            else "workbench"
        )
        normalized_transaction_id = str(transaction_id or "").strip()
        get_transaction = getattr(self._sql_read_repository, "get_cost_statistics_transaction", None)
        get_freshness_gate = getattr(self._sql_read_repository, "get_cost_statistics_freshness_gate", None)
        gate_scope_month = scope_value if scope_kind == "month" else "all"
        scope_key = self._runtime_service.request_scope_key(
            gate_scope_month,
            normalized_project_scope,
        )
        if not callable(get_transaction) or not callable(get_freshness_gate):
            payload = self._cost_statistics_non_fresh_gate_payload(
                scope_key=scope_key,
                empty_payload_factory=lambda: self.empty_explorer_payload("all"),
                refresh_reason="api_detail_sql_repository_unavailable",
                stale_reasons=(),
            )
            raise CostStatisticsReadModelNotFreshError(
                payload,
                message="成本统计数据正在刷新，请稍后重试。",
            )
        gate, _expected_source_versions, non_fresh_payload = self._cost_statistics_freshness_gate(
            scope_key=scope_key,
            get_freshness_gate=get_freshness_gate,
            empty_payload_factory=lambda: self.empty_explorer_payload("all"),
            missing_reason="api_detail_miss",
            stale_reason="api_detail_stale",
            source_mismatch_reason="api_detail_source_versions_stale",
            dependency_profile=dependency_profile,
        )
        if non_fresh_payload is not None:
            raise CostStatisticsReadModelNotFreshError(
                non_fresh_payload,
                message="成本统计数据正在刷新，请稍后重试。",
            )
        if gate is None:
            raise CostStatisticsReadModelNotFreshError(
                self._cost_statistics_non_fresh_gate_payload(
                    scope_key=scope_key,
                    empty_payload_factory=lambda: self.empty_explorer_payload("all"),
                    refresh_reason="api_detail_miss",
                    stale_reasons=(),
                ),
                message="成本统计数据正在刷新，请稍后重试。",
            )
        row = get_transaction(
            project_scope=normalized_project_scope,
            transaction_id=normalized_transaction_id,
            dependency_profile=dependency_profile,
            scope_kind=scope_kind,
            scope_value=scope_value,
        )
        if not isinstance(row, dict):
            raise KeyError(transaction_id)
        selected_codes = self._selected_bank_tag_codes(self._cost_tag_selection_payload_from_gate(gate))
        bank_tag_code = str(row.get("bank_tag_code") or "").strip() or COST_STATISTICS_UNCATEGORIZED_TAG_CODE
        if selected_codes is not None and bank_tag_code not in selected_codes:
            raise KeyError(transaction_id)
        trade_time = str(row.get("trade_time") or "").strip()
        stored_month = str(row.get("month") or "").strip()
        month = stored_month[:7] or trade_time[:7] or "all"
        label_path = row.get("bank_tag_label_path")
        cost_allocations = [
            {
                "row_key": str(item.get("row_key") or ""),
                "project_name": str(item.get("project_name") or "未归集项目"),
                "project_id": str(item.get("project_id") or ""),
                "expense_type": str(item.get("expense_type") or "未分类"),
                "expense_content": str(item.get("expense_content") or ""),
                "oa_applicant": str(item.get("oa_applicant") or "—"),
                "amount": _plain_money(_decimal_from_value(item.get("amount")) or Decimal("0.00")),
            }
            for item in list(row.get("cost_allocations") or [])
            if isinstance(item, dict)
        ]
        project_names = {item["project_name"] for item in cost_allocations}
        expense_types = {item["expense_type"] for item in cost_allocations}
        allocation_amount = sum(
            (_decimal_from_value(item["amount"]) or Decimal("0.00") for item in cost_allocations),
            start=Decimal("0.00"),
        )
        return {
            "month": month,
            "transaction": {
                "id": normalized_transaction_id,
                "project_name": (
                    next(iter(project_names))
                    if len(project_names) == 1
                    else "多项目"
                    if project_names
                    else str(row.get("project_name") or "")
                ),
                "expense_type": (
                    next(iter(expense_types))
                    if len(expense_types) == 1
                    else "多费用类型"
                    if expense_types
                    else str(row.get("expense_type") or "")
                ),
                "expense_content": (
                    "、".join(sorted({item["expense_content"] for item in cost_allocations if item["expense_content"]}))
                    or str(row.get("expense_content") or "")
                ),
                "trade_time": trade_time,
                "direction": str(row.get("direction") or ""),
                "amount": _plain_money(
                    allocation_amount
                    if cost_allocations
                    else _decimal_from_value(row.get("amount")) or Decimal("0.00")
                ),
                "counterparty_name": str(row.get("counterparty_name") or ""),
                "payment_account_label": str(row.get("payment_account_label") or ""),
                "remark": str(row.get("remark") or ""),
                "oa_applicant": (
                    "、".join(sorted({item["oa_applicant"] for item in cost_allocations if item["oa_applicant"]}))
                    or str(row.get("oa_applicant") or "")
                ),
                "cost_allocations": cost_allocations,
                "summary_fields": {},
                "detail_fields": {},
                "relation_status": "read_model",
                "relation_case_ids": [],
                "linked_oa_count": 0,
                "linked_invoice_count": 0,
                "bank_tag_code": str(row.get("bank_tag_code") or ""),
                "bank_tag_label": str(row.get("bank_tag_label") or ""),
                "bank_tag_primary_label": str(row.get("bank_tag_primary_label") or ""),
                "bank_tag_sub_label": str(row.get("bank_tag_sub_label") or ""),
                "bank_tag_label_path": list(label_path) if isinstance(label_path, list) else [],
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

    def _cost_statistics_freshness_gate(
        self,
        *,
        scope_key: str,
        get_freshness_gate: Any,
        empty_payload_factory: Any,
        missing_reason: str,
        stale_reason: str,
        source_mismatch_reason: str,
        dependency_profile: str = "workbench",
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        scope_month = str(scope_key).split(":", 1)[1] if ":" in str(scope_key) else ""
        bank_flow_profile = dependency_profile == "bank_flow"
        gate = get_freshness_gate(
            scope_key=scope_key,
            dependency_profile=dependency_profile,
        )
        if not isinstance(gate, dict):
            return None, None, self._cost_statistics_non_fresh_gate_payload(
                scope_key=scope_key,
                empty_payload_factory=empty_payload_factory,
                refresh_reason=missing_reason,
                stale_reasons=(),
            )

        gate_status = str(
            (
                gate.get("bank_flow_refresh_status")
                if bank_flow_profile
                else gate.get("refresh_status")
            )
            or "stale"
        ).strip().lower()
        gate_reasons = tuple(
            str(reason).strip()
            for reason in list(
                (
                    gate.get("bank_flow_stale_reasons")
                    if bank_flow_profile
                    else gate.get("stale_reasons")
                )
                or []
            )
            if str(reason).strip()
        )
        workbench_refresh_scope_keys = self._normalized_refresh_scope_keys(
            gate.get("workbench_refresh_scope_keys")
        )
        if not bank_flow_profile and workbench_refresh_scope_keys:
            return gate, None, self._workbench_dependency_non_fresh_payload(
                scope_key=scope_key,
                workbench_scope_keys=workbench_refresh_scope_keys,
                empty_payload_factory=empty_payload_factory,
                stale_reasons=gate_reasons or ("workbench_dependency_not_fresh",),
            )
        bank_detail_refresh_scope_keys = self._normalized_refresh_scope_keys(
            gate.get(
                "bank_flow_bank_detail_refresh_scope_keys"
                if bank_flow_profile
                else "bank_detail_refresh_scope_keys"
            )
        )
        if bank_detail_refresh_scope_keys:
            return gate, None, self._bank_detail_dependency_non_fresh_payload(
                scope_key=scope_key,
                bank_detail_scope_keys=bank_detail_refresh_scope_keys,
                empty_payload_factory=empty_payload_factory,
                stale_reasons=gate_reasons or ("bank_detail_dependency_not_fresh",),
            )
        child_refresh_scope_keys = self._normalized_refresh_scope_keys(
            gate.get(
                "bank_flow_child_refresh_scope_keys"
                if bank_flow_profile
                else "child_refresh_scope_keys"
            )
        )
        if gate_status != "fresh":
            return gate, None, self._cost_statistics_non_fresh_gate_payload(
                scope_key=scope_key,
                empty_payload_factory=empty_payload_factory,
                refresh_reason=stale_reason,
                stale_reasons=gate_reasons,
                refresh_scope_keys=child_refresh_scope_keys,
            )

        if not bank_flow_profile and scope_month and scope_month != "all":
            expected_workbench_versions, active_workbench_versions = (
                self._workbench_dependency_versions_provider(scope_month)
            )
            expected_workbench_versions = require_expected_source_versions(
                cost_statistics_workbench_dependency_source_versions(
                    expected_workbench_versions
                ),
                context="cost_statistics_workbench_dependency",
            )
            workbench_stale_reasons = source_version_mismatch_reasons(
                expected=expected_workbench_versions,
                actual=cost_statistics_workbench_dependency_source_versions(
                    active_workbench_versions
                ),
            )
            if workbench_stale_reasons:
                return gate, None, self._workbench_dependency_non_fresh_payload(
                    scope_key=scope_key,
                    workbench_scope_keys=(scope_month,),
                    empty_payload_factory=empty_payload_factory,
                    stale_reasons=tuple(
                        f"workbench_dependency_{reason}" for reason in workbench_stale_reasons
                    ),
                )
        elif not bank_flow_profile and scope_month == "all":
            expected_by_scope, active_by_scope = (
                self._workbench_dependency_versions_by_scope_provider()
            )
            workbench_stale_reasons: list[str] = []
            workbench_stale_scope_keys: list[str] = []
            for workbench_scope_key in sorted(expected_by_scope):
                expected_workbench_versions = require_expected_source_versions(
                    cost_statistics_workbench_dependency_source_versions(
                        expected_by_scope.get(workbench_scope_key)
                    ),
                    context=f"cost_statistics_workbench_dependency:{workbench_scope_key}",
                )
                scope_stale_reasons = source_version_mismatch_reasons(
                    expected=expected_workbench_versions,
                    actual=cost_statistics_workbench_dependency_source_versions(
                        active_by_scope.get(workbench_scope_key)
                    ),
                )
                if not scope_stale_reasons:
                    continue
                workbench_stale_scope_keys.append(workbench_scope_key)
                workbench_stale_reasons.extend(
                    f"workbench_dependency_{workbench_scope_key}_{reason}"
                    for reason in scope_stale_reasons
                )
            if workbench_stale_scope_keys:
                return gate, None, self._workbench_dependency_non_fresh_payload(
                    scope_key=scope_key,
                    workbench_scope_keys=tuple(workbench_stale_scope_keys),
                    empty_payload_factory=empty_payload_factory,
                    stale_reasons=tuple(workbench_stale_reasons),
                )

        expected_source_versions = cost_statistics_source_versions(
            month=scope_month,
            settings_payload=(
                gate.get("source_settings")
                if isinstance(gate.get("source_settings"), dict)
                else {}
            ),
            workbench_source_versions=(
                gate.get("workbench_source_versions")
                if isinstance(gate.get("workbench_source_versions"), dict)
                else None
            ),
            bank_detail_source_versions=(
                gate.get("bank_detail_source_versions")
                if isinstance(gate.get("bank_detail_source_versions"), dict)
                and gate.get("bank_detail_source_versions")
                else None
            ),
        )
        source_version_filter = (
            cost_statistics_bank_flow_source_versions
            if bank_flow_profile
            else cost_statistics_semantic_source_versions
        )
        freshness = resolve_read_model_freshness(
            expected_schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            actual_schema_version=gate.get("schema_version"),
            expected_source_versions=source_version_filter(expected_source_versions),
            actual_source_versions=source_version_filter(
                gate.get("source_versions")
                if isinstance(gate.get("source_versions"), dict)
                else {}
            ),
        )
        if freshness.status == "fresh":
            return gate, source_version_filter(expected_source_versions), None
        refresh_reason = (
            source_mismatch_reason
            if any(reason.endswith("_missing") or reason.endswith("_mismatch") for reason in freshness.stale_reasons)
            else stale_reason
        )
        return gate, expected_source_versions, self._cost_statistics_non_fresh_gate_payload(
            scope_key=scope_key,
            empty_payload_factory=empty_payload_factory,
            refresh_reason=refresh_reason,
            stale_reasons=freshness.stale_reasons,
        )

    def _bank_detail_dependency_non_fresh_payload(
        self,
        *,
        scope_key: str,
        bank_detail_scope_keys: tuple[str, ...],
        empty_payload_factory: Any,
        stale_reasons: tuple[str, ...],
    ) -> dict[str, Any]:
        payload = dict(empty_payload_factory())
        payload["read_model_status"] = "refreshing"
        payload["read_model_scope_key"] = scope_key
        payload["read_model_stale_reasons"] = list(stale_reasons)
        payload["refresh_reason"] = "cost_statistics_bank_detail_dependency_stale"
        payload["refresh_dependency"] = "bank_detail"
        payload["refresh_scope_keys"] = list(bank_detail_scope_keys)
        payload["refresh_enqueued"] = bool(
            callable(self._bank_detail_refresh_enqueuer)
            and self._bank_detail_refresh_enqueuer(
                list(bank_detail_scope_keys),
                reason="cost_statistics_bank_detail_dependency_stale",
            )
        )
        return payload

    def _workbench_dependency_non_fresh_payload(
        self,
        *,
        scope_key: str,
        workbench_scope_keys: tuple[str, ...],
        empty_payload_factory: Any,
        stale_reasons: tuple[str, ...],
    ) -> dict[str, Any]:
        refresh_reason = "cost_statistics_workbench_dependency_stale"
        payload = dict(empty_payload_factory())
        payload["read_model_status"] = "refreshing"
        payload["read_model_scope_key"] = scope_key
        payload["read_model_stale_reasons"] = list(stale_reasons)
        payload["refresh_reason"] = refresh_reason
        payload["refresh_dependency"] = "workbench"
        payload["refresh_scope_keys"] = list(workbench_scope_keys)
        refresh_results = [
            bool(
                self._workbench_refresh_enqueuer(
                    workbench_scope_key,
                    reason=refresh_reason,
                )
            )
            for workbench_scope_key in workbench_scope_keys
        ]
        project_scope = str(scope_key or "").split(":", 1)[0]
        dependency_months = sorted(
            month
            for month in self._runtime_service.months_from_workbench_scope_keys(
                list(workbench_scope_keys)
            )
            if month != "all"
        )
        cost_scope_keys = [
            self._runtime_service.request_scope_key(month, project_scope)
            for month in dependency_months
        ]
        cost_refresh_scope_keys = (
            self._runtime_service.enqueue_read_model_refreshes(
                cost_scope_keys,
                reason=refresh_reason,
            )
            if cost_scope_keys
            else []
        )
        payload["refresh_enqueued"] = bool(cost_refresh_scope_keys) or any(refresh_results)
        return payload

    def _cost_statistics_non_fresh_gate_payload(
        self,
        *,
        scope_key: str,
        empty_payload_factory: Any,
        refresh_reason: str,
        stale_reasons: tuple[str, ...],
        refresh_scope_keys: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        payload = dict(empty_payload_factory())
        payload["read_model_status"] = "refreshing"
        payload["read_model_scope_key"] = scope_key
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        payload["refresh_reason"] = refresh_reason
        target_scope_keys = refresh_scope_keys or (scope_key,)
        payload["refresh_scope_keys"] = list(target_scope_keys)
        refresh_results = [
            bool(
                self._runtime_service.enqueue_read_model_refresh(
                    target_scope_key,
                    reason=refresh_reason,
                )
            )
            for target_scope_key in target_scope_keys
        ]
        payload["refresh_enqueued"] = any(refresh_results)
        return payload

    @staticmethod
    def _normalized_refresh_scope_keys(value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(
            dict.fromkeys(
                normalized
                for item in value
                for normalized in [str(item or "").strip()]
                if normalized
            )
        )

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

    def _cost_tag_selection_payload_from_gate(self, gate: dict[str, Any]) -> dict[str, Any]:
        settings_payload = gate.get("source_settings") if isinstance(gate.get("source_settings"), dict) else {}
        payload = self._tag_selection_mapper(settings_payload)
        if not isinstance(payload, dict):
            raise RuntimeError("cost statistics tag selection mapper must return a mapping")
        return payload

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

    @staticmethod
    def _normalize_page_scope(scope: str) -> tuple[str, str | None, str]:
        normalized = str(scope or "").strip().lower()
        if normalized == "all":
            return "all", None, "all"
        year_match = re.fullmatch(r"year:(\d{4})", normalized)
        if year_match:
            return "year", year_match.group(1), f"year:{year_match.group(1)}"
        month_match = re.fullmatch(r"(\d{4})-(\d{2})", normalized)
        if month_match and 1 <= int(month_match.group(2)) <= 12:
            return "month", normalized, normalized
        raise ValueError("cost statistics scope must be YYYY-MM, year:YYYY, or all")

    @staticmethod
    def _normalize_page_size(page_size: int) -> int:
        try:
            normalized = int(page_size)
        except (TypeError, ValueError) as error:
            raise ValueError("cost statistics page_size must be an integer") from error
        if not 1 <= normalized <= 100:
            raise ValueError("cost statistics page_size must be between 1 and 100")
        return normalized

    @staticmethod
    def _normalize_page_query(
        view: str,
        filters: dict[str, str | None],
    ) -> tuple[str, dict[str, str]]:
        normalized_view = str(view or "").strip().lower()
        allowed_filters = {
            "time": set(),
            "project": {"project_name", "expense_type"},
            "bank": {"payment_account_label", "project_name"},
            "expense_type": {"expense_type"},
            "bank_tag": {"bank_tag_primary_label", "bank_tag_sub_label"},
        }
        if normalized_view not in allowed_filters:
            raise ValueError("unsupported cost statistics view")
        normalized_filters = {
            key: str(value or "").strip()
            for key, value in filters.items()
            if str(value or "").strip()
        }
        unexpected = set(normalized_filters) - allowed_filters[normalized_view]
        if unexpected:
            raise ValueError(f"unsupported filters for {normalized_view}: {', '.join(sorted(unexpected))}")
        if normalized_view == "project" and normalized_filters.get("expense_type") and not normalized_filters.get("project_name"):
            raise ValueError("project_name is required when expense_type is selected")
        if normalized_view == "bank" and normalized_filters.get("project_name") and not normalized_filters.get("payment_account_label"):
            raise ValueError("payment_account_label is required when project_name is selected")
        if normalized_view == "bank_tag" and normalized_filters.get("bank_tag_sub_label") and not normalized_filters.get("bank_tag_primary_label"):
            raise ValueError("bank_tag_primary_label is required when bank_tag_sub_label is selected")
        return normalized_view, normalized_filters

    @staticmethod
    def _page_query_binding(
        *,
        scope: str,
        view: str,
        filters: dict[str, str],
        page_size: int,
    ) -> str:
        return json.dumps(
            {
                "scope": scope,
                "view": view,
                "filters": filters,
                "page_size": page_size,
                "schema": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _page_query_fingerprint(query_binding: str, cursor: str | None) -> str:
        return hashlib.sha256(f"{query_binding}|cursor:{str(cursor or '')}".encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _encode_page_cursor(
        values: tuple[str, str, str, str],
        *,
        query_binding: str,
        published_source_version: int,
    ) -> str:
        cursor_payload = {
            "v": 1,
            "q": hashlib.sha256(query_binding.encode("utf-8")).hexdigest(),
            "p": published_source_version,
            "s": list(values),
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(cursor_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        return encoded.rstrip("=")

    @staticmethod
    def _decode_page_cursor(
        cursor: str | None,
        *,
        query_binding: str,
        published_source_version: int,
    ) -> tuple[str, str, str, str] | None:
        normalized = str(cursor or "").strip()
        if not normalized:
            return None
        try:
            padding = "=" * (-len(normalized) % 4)
            payload = json.loads(base64.urlsafe_b64decode(f"{normalized}{padding}").decode("utf-8"))
        except Exception as error:
            raise ValueError("cost_statistics_cursor_invalid") from error
        expected_query = hashlib.sha256(query_binding.encode("utf-8")).hexdigest()
        sort_values = payload.get("s") if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or payload.get("v") != 1
            or payload.get("q") != expected_query
            or payload.get("p") != published_source_version
            or not isinstance(sort_values, list)
            or len(sort_values) != 4
            or any(not isinstance(value, str) for value in sort_values)
        ):
            raise ValueError("cost_statistics_cursor_stale_or_mismatched")
        return tuple(sort_values)  # type: ignore[return-value]

    @staticmethod
    def _page_etag(
        *,
        scope_key: str,
        published_source_version: int,
        statistics_published_source_version: int | None,
        statistics_status: str,
        query_fingerprint: str,
        tag_token: str,
    ) -> str:
        digest = hashlib.sha256(
            (
                f"{scope_key}|{published_source_version}|statistics:"
                f"{statistics_published_source_version}:{statistics_status}|"
                f"{query_fingerprint}|{tag_token}"
            ).encode("utf-8")
        ).hexdigest()[:32]
        return f'"cost-statistics-{digest}"'

    @staticmethod
    def _etag_matches(if_none_match: str | None, etag: str) -> bool:
        candidates = {item.strip() for item in str(if_none_match or "").split(",") if item.strip()}
        return "*" in candidates or etag in candidates or f"W/{etag}" in candidates

    @classmethod
    def _normalize_explorer_page_payload(
        cls,
        payload: dict[str, Any],
        *,
        scope: str,
        view: str,
        query_binding: str,
        published_source_version: int,
        bank_accounts: list[Any],
        statistics: dict[str, Any] | None,
        statistics_status: str,
        statistics_refresh_enqueued: bool,
    ) -> dict[str, Any]:
        primary = [dict(item) for item in list(payload.get("primary_facets") or []) if isinstance(item, dict)]
        secondary = [dict(item) for item in list(payload.get("secondary_facets") or []) if isinstance(item, dict)]
        facets = {
            "projects": [],
            "expense_types": [],
            "bank_accounts": [],
            "bank_tag_primary": [],
            "bank_tag_sub": [],
        }
        if view == "project":
            facets["projects"] = primary
            facets["expense_types"] = secondary
        elif view == "bank":
            facets["bank_accounts"] = cls._merge_bank_account_facets(primary, bank_accounts)
            facets["projects"] = secondary
        elif view == "expense_type":
            facets["expense_types"] = primary
        elif view == "bank_tag":
            facets["bank_tag_primary"] = primary
            facets["bank_tag_sub"] = secondary
        next_values = payload.get("next_cursor_values")
        next_cursor = None
        if isinstance(next_values, (list, tuple)) and len(next_values) == 4:
            next_cursor = cls._encode_page_cursor(
                tuple(str(value or "") for value in next_values),  # type: ignore[arg-type]
                query_binding=query_binding,
                published_source_version=published_source_version,
            )
        normalized_statistics = dict(statistics) if isinstance(statistics, dict) else None
        cost_transaction_count = payload.get("cost_transaction_count")
        if (
            normalized_statistics is not None
            and not isinstance(cost_transaction_count, bool)
            and isinstance(cost_transaction_count, int)
            and cost_transaction_count >= 0
        ):
            normalized_statistics["cost_transaction_count"] = cost_transaction_count
        return {
            "scope": scope,
            "view": view,
            "statistics": normalized_statistics,
            "statistics_status": statistics_status,
            **({"statistics_refresh_enqueued": True} if statistics_refresh_enqueued else {}),
            "summary": dict(payload.get("summary") or {}),
            "available_years": [str(value) for value in list(payload.get("available_years") or []) if str(value)],
            "facets": facets,
            "rows": [dict(item) for item in list(payload.get("rows") or []) if isinstance(item, dict)],
            "row_count": int(payload.get("row_count") or 0),
            "next_cursor": next_cursor,
        }

    @staticmethod
    def _merge_bank_account_facets(observed: list[dict[str, Any]], configured: list[Any]) -> list[dict[str, Any]]:
        rows = [dict(item) for item in observed]
        seen = {str(item.get("payment_account_label") or "").strip() for item in rows}
        for raw_account in configured:
            if not isinstance(raw_account, dict):
                continue
            label = str(raw_account.get("payment_account_label") or "").strip()
            if not label or label in seen:
                continue
            seen.add(label)
            rows.append(
                {
                    "payment_account_label": label,
                    "total_amount": "0.00",
                    "transaction_count": 0,
                    "project_count": 0,
                    "percentage_label": "0.0%",
                }
            )
        return rows

    @staticmethod
    def empty_explorer_page_payload(scope: str, view: str) -> dict[str, Any]:
        return {
            "scope": scope,
            "view": view,
            "statistics": None,
            "statistics_status": "refreshing",
            "summary": {
                "row_count": 0,
                "transaction_count": 0,
                "total_amount": "0.00",
                "expense_amount": "0.00",
                "income_amount": "0.00",
                "expense_transaction_count": 0,
                "income_transaction_count": 0,
            },
            "available_years": [],
            "facets": {
                "projects": [],
                "expense_types": [],
                "bank_accounts": [],
                "bank_tag_primary": [],
                "bank_tag_sub": [],
            },
            "rows": [],
            "row_count": 0,
            "next_cursor": None,
        }

    @staticmethod
    def _is_explorer_page_payload(payload: dict[str, Any]) -> bool:
        return (
            isinstance(payload.get("summary"), dict)
            and isinstance(payload.get("available_years"), list)
            and isinstance(payload.get("facets"), dict)
            and isinstance(payload.get("rows"), list)
            and payload.get("view") in {"time", "project", "bank", "expense_type", "bank_tag"}
        )

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
            "bank_accounts": [],
            "project_rows": [],
            "expense_type_rows": [],
        }

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
        project_scope = self._normalize_project_scope(str(kwargs.get("project_scope") or "active"))
        project_names = self._normalize_text_set(
            kwargs.get("project_names") or ([kwargs.get("project_name")] if kwargs.get("project_name") else [])
        )
        expense_types = self._normalize_text_set(kwargs.get("expense_types"))
        aggregate_by = self._normalize_project_aggregate_by(kwargs.get("aggregate_by"))
        range_kwargs = self._range_kwargs(kwargs)
        if view == "time":
            gate_scope_key, gate, first_page, query = self._load_export_first_page(
                view=view,
                month=month,
                project_scope=project_scope,
                project_names=set(),
                expense_types=set(),
                row_shape="raw_bank",
                page_size=COST_STATISTICS_EXPORT_PREVIEW_SIZE,
                **range_kwargs,
            )
            del gate_scope_key, gate, query
            summary = self._export_page_summary(first_page)
            self._ensure_export_row_limit(view=view, total=int(summary["source_row_count"]))
            entries = [self._export_entry_from_row(row) for row in list(first_page.get("rows") or [])]
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
                total_count=int(summary["source_row_count"]),
                total_amount=_plain_money(_decimal_from_value(summary.get("total_amount")) or Decimal("0.00")),
                summary_extra=self._directional_summary_from_export_summary(summary),
            )
        if view == "bank_tag":
            _scope_key, _gate, first_page, _query = self._load_export_first_page(
                view=view,
                month=month,
                project_scope=project_scope,
                project_names=set(),
                expense_types=set(),
                row_shape="raw_bank",
                page_size=COST_STATISTICS_EXPORT_PREVIEW_SIZE,
                **range_kwargs,
            )
            summary = self._export_page_summary(first_page)
            self._ensure_export_row_limit(view=view, total=int(summary["source_row_count"]))
            entries = [self._export_entry_from_row(row) for row in list(first_page.get("rows") or [])]
            scope_label = self._build_scope_label(month=month, **range_kwargs)
            return self._preview_payload(
                view=view,
                file_name=self._build_filename(month=scope_label, view=view),
                scope_label=scope_label,
                sheet_names=["按标签统计"],
                columns=["时间", "主标签", "子标签", "资金方向", "金额", "费用内容", "对方户名", "支付账户"],
                rows=[self._bank_tag_row_from_entry(entry) for entry in entries],
                total_count=int(summary["source_row_count"]),
                total_amount=_plain_money(_decimal_from_value(summary.get("total_amount")) or Decimal("0.00")),
                summary_extra=self._directional_summary_from_export_summary(summary),
            )
        if view == "project":
            if not project_names:
                raise ValueError("project_name is required for project export preview")
            if aggregate_by is not None or len(project_names) > 1:
                _scope_key, _gate, first_page, _query = self._load_export_first_page(
                    view=view,
                    month="all",
                    project_scope=project_scope,
                    project_names=project_names,
                    expense_types=expense_types,
                    row_shape="project_month" if (aggregate_by or "month") == "month" else "project_year",
                    page_size=COST_STATISTICS_EXPORT_PREVIEW_SIZE,
                    **range_kwargs,
                )
                summary = self._export_page_summary(first_page)
                self._ensure_export_row_limit(view=view, total=int(summary["source_row_count"]))
                rows = [self._export_entry_from_row(row) for row in list(first_page.get("rows") or [])]
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
                    total_count=int(summary["source_row_count"]),
                    total_amount=_plain_money(_decimal_from_value(summary.get("total_amount")) or Decimal("0.00")),
                )
            project_name = sorted(project_names)[0]
            _scope_key, _gate, first_page, _query = self._load_export_first_page(
                view=view,
                month=month,
                project_scope=project_scope,
                project_names={project_name},
                expense_types=expense_types,
                row_shape="raw_cost",
                page_size=COST_STATISTICS_EXPORT_PREVIEW_SIZE,
                **range_kwargs,
            )
            summary = self._export_page_summary(first_page)
            self._ensure_export_row_limit(view=view, total=int(summary["source_row_count"]))
            entries = [self._export_entry_from_row(row) for row in list(first_page.get("rows") or [])]
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
                total_count=int(summary["source_row_count"]),
                total_amount=_plain_money(_decimal_from_value(summary.get("total_amount")) or Decimal("0.00")),
            )
        if view == "expense_type":
            if not expense_types:
                raise ValueError("expense_type is required for expense_type export preview")
            _scope_key, _gate, first_page, _query = self._load_export_first_page(
                view=view,
                month=month,
                project_scope=project_scope,
                project_names=set(),
                expense_types=expense_types,
                row_shape="raw_cost",
                page_size=COST_STATISTICS_EXPORT_PREVIEW_SIZE,
                **range_kwargs,
            )
            summary = self._export_page_summary(first_page)
            self._ensure_export_row_limit(view=view, total=int(summary["source_row_count"]))
            entries = [self._export_entry_from_row(row) for row in list(first_page.get("rows") or [])]
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
                total_count=int(summary["source_row_count"]),
                total_amount=_plain_money(_decimal_from_value(summary.get("total_amount")) or Decimal("0.00")),
            )
        raise ValueError("view must be time, bank_tag, project, or expense_type.")

    def _export_view_from_read_model(self, **kwargs: Any) -> tuple[str, bytes]:
        view = str(kwargs.get("view") or "").strip()
        month = str(kwargs.get("month") or "all")
        project_scope = self._normalize_project_scope(str(kwargs.get("project_scope") or "active"))
        project_names = self._normalize_text_set(
            kwargs.get("project_names") or ([kwargs.get("project_name")] if kwargs.get("project_name") else [])
        )
        expense_types = self._normalize_text_set(kwargs.get("expense_types"))
        aggregate_by = self._normalize_project_aggregate_by(kwargs.get("aggregate_by"))
        range_kwargs = self._range_kwargs(kwargs)
        if view == "transaction":
            transaction_id = str(kwargs.get("transaction_id") or "").strip()
            if not transaction_id:
                raise ValueError("transaction_id is required for transaction export")
            payload = self.get_transaction_detail(
                transaction_id,
                project_scope=project_scope,
                view="project",
                scope=month,
            )
            workbook = self._transaction_workbook(payload)
            filename = self._build_filename(
                month=payload["month"],
                view=view,
                project_name=payload["transaction"]["project_name"],
                transaction_id=transaction_id,
            )
            return filename, self._serialize_workbook(workbook)

        export_month = month
        row_shape = "raw_cost"
        if view in {"time", "bank_tag"}:
            row_shape = "raw_bank"
        elif view == "month":
            row_shape = "month_summary"
        elif view == "project":
            if not project_names:
                raise ValueError("project_name is required for project export")
            if aggregate_by is not None or len(project_names) > 1:
                export_month = "all"
                row_shape = "project_month" if (aggregate_by or "month") == "month" else "project_year"
        elif view == "expense_type":
            if not expense_types:
                raise ValueError("expense_type is required for expense_type export")
        else:
            raise ValueError(f"unsupported export view: {view}")

        gate_scope_key, gate, first_page, query = self._load_export_first_page(
            view=view,
            month=export_month,
            project_scope=project_scope,
            project_names=project_names if view == "project" else set(),
            expense_types=expense_types,
            row_shape=row_shape,
            page_size=COST_STATISTICS_EXPORT_BATCH_SIZE,
            **range_kwargs,
        )
        summary = self._export_page_summary(first_page)
        limit_total = int(summary["row_count"] if view == "month" else summary["source_row_count"])
        self._ensure_export_row_limit(view=view, total=limit_total)

        if view == "time":
            workbook = self._table_workbook(
                "按时间统计",
                ["时间", "项目名称", "费用类型", "金额", "费用内容", "资金方向", "对方户名", "支付账户"],
                (self._time_row_from_entry(entry) for entry in self._iter_export_entries(first_page, query)),
            )
            filename = self._build_filename(month=self._build_scope_label(month=month, **range_kwargs), view=view)
        elif view == "bank_tag":
            workbook = self._table_workbook(
                "按标签统计",
                ["时间", "主标签", "子标签", "资金方向", "金额", "费用内容", "对方户名", "支付账户"],
                (self._bank_tag_row_from_entry(entry) for entry in self._iter_export_entries(first_page, query)),
            )
            filename = self._build_filename(month=self._build_scope_label(month=month, **range_kwargs), view=view)
        elif view == "month":
            workbook = self._table_workbook(
                "月份汇总",
                ["项目名称", "费用类型", "金额", "费用内容", "支出笔数"],
                (
                    [entry["project_name"], entry["expense_type"], entry["amount"], entry["expense_content"], entry["transaction_count"]]
                    for entry in self._iter_export_entries(first_page, query)
                ),
            )
            filename = self._build_filename(month=month, view=view)
        elif view == "project":
            if aggregate_by is not None or len(project_names) > 1:
                workbook = self._table_workbook(
                    "按项目统计",
                    ["统计周期", "项目名称", "费用类型", "金额", "费用内容", "支出笔数"],
                    (
                        [
                            row["period_label"],
                            row["project_name"],
                            row["expense_type"],
                            row["amount"],
                            row["expense_content"],
                            row["transaction_count"],
                        ]
                        for row in self._iter_export_entries(first_page, query)
                    ),
                )
                filename = self._build_filename(
                    month=self._build_scope_label(month="all", **range_kwargs),
                    view=view,
                    project_names=sorted(project_names),
                    aggregate_by=aggregate_by or "month",
                )
            else:
                project_name = sorted(project_names)[0]
                workbook = self._project_detail_workbook_from_export_pages(
                    month=month,
                    project_name=project_name,
                    entries=self._iter_export_entries(first_page, query),
                    include_oa_details=bool(kwargs.get("include_oa_details", True)),
                    include_invoice_details=bool(kwargs.get("include_invoice_details", True)),
                    include_exception_rows=bool(kwargs.get("include_exception_rows", True)),
                    include_ignored_rows=bool(kwargs.get("include_ignored_rows", True)),
                    include_expense_content_summary=bool(kwargs.get("include_expense_content_summary", True)),
                    scope_label=self._build_scope_label(month=month, **range_kwargs),
                )
                filename = self._build_filename(
                    month=self._build_scope_label(month=month, **range_kwargs),
                    view=view,
                    project_name=project_name,
                )
        elif view == "expense_type":
            workbook = self._table_workbook(
                "按费用类型统计",
                ["时间", "项目名称", "金额", "费用内容", "资金方向", "对方户名", "支付账户"],
                (
                    [
                        entry["trade_time"],
                        entry["project_name"],
                        _plain_money(entry["amount_decimal"]),
                        entry["expense_content"],
                        entry["direction"],
                        entry["counterparty_name"],
                        entry["payment_account_label"],
                    ]
                    for entry in self._iter_export_entries(first_page, query)
                ),
            )
            filename = self._build_filename(
                month=self._build_scope_label(month=month, **range_kwargs),
                view=view,
                expense_type=self._build_expense_type_label(expense_types),
            )

        content = self._serialize_workbook(workbook)
        self._assert_export_gate_unchanged(
            scope_key=gate_scope_key,
            initial_gate=gate,
            dependency_profile=str(query["dependency_profile"]),
        )
        return filename, content

    def _load_export_first_page(
        self,
        *,
        view: str,
        month: str,
        project_scope: str,
        row_shape: str,
        page_size: int,
        start_month: str | None = None,
        end_month: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        project_names: set[str] | None = None,
        expense_types: set[str] | None = None,
    ) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]:
        get_export_page = getattr(self._sql_read_repository, "get_cost_statistics_export_page", None)
        get_freshness_gate = getattr(self._sql_read_repository, "get_cost_statistics_freshness_gate", None)
        gate_month = month if re.fullmatch(r"\d{4}-\d{2}", month) else "all"
        scope_key = self._runtime_service.request_scope_key(gate_month, project_scope)
        dependency_profile = "bank_flow" if row_shape == "raw_bank" else "workbench"
        if not callable(get_export_page) or not callable(get_freshness_gate):
            payload = self._cost_statistics_non_fresh_gate_payload(
                scope_key=scope_key,
                empty_payload_factory=lambda: self.empty_explorer_payload(gate_month),
                refresh_reason="api_export_sql_repository_unavailable",
                stale_reasons=(),
            )
            raise CostStatisticsReadModelNotFreshError(payload, message="成本统计数据正在刷新，请稍后重试导出。")
        gate, _expected_source_versions, non_fresh_payload = self._cost_statistics_freshness_gate(
            scope_key=scope_key,
            get_freshness_gate=get_freshness_gate,
            empty_payload_factory=lambda: self.empty_explorer_payload(gate_month),
            missing_reason="api_export_miss",
            stale_reason="api_export_stale",
            source_mismatch_reason="api_export_source_versions_stale",
            dependency_profile=dependency_profile,
        )
        if non_fresh_payload is not None or gate is None:
            raise CostStatisticsReadModelNotFreshError(
                non_fresh_payload or self.empty_explorer_payload(gate_month),
                message="成本统计数据正在刷新，请稍后重试导出。",
            )
        selected_codes = self._selected_bank_tag_codes(self._cost_tag_selection_payload_from_gate(gate))
        query = {
            "project_scope": project_scope,
            "month": month,
            "start_month": start_month,
            "end_month": end_month,
            "start_date": start_date,
            "end_date": end_date,
            "project_names": sorted(project_names or set()),
            "expense_types": sorted(expense_types or set()),
            "selected_tag_codes": sorted(selected_codes) if selected_codes is not None else None,
            "row_shape": row_shape,
            "page_size": page_size,
            "get_export_page": get_export_page,
            "view": view,
            "scope_key": scope_key,
            "dependency_profile": dependency_profile,
        }
        first_page = get_export_page(
            **{
                key: value
                for key, value in query.items()
                if key not in {"get_export_page", "view", "scope_key", "dependency_profile"}
            },
            offset=0,
            include_summary=True,
        )
        if not isinstance(first_page, dict) or not isinstance(first_page.get("summary"), dict):
            raise CostStatisticsReadModelNotFreshError(
                {
                    "read_model_status": "unavailable",
                    "read_model_scope_key": scope_key,
                    "read_model_stale_reasons": ["export_query_unavailable"],
                },
                message="成本统计数据正在刷新，请稍后重试导出。",
            )
        return scope_key, gate, first_page, query

    def _iter_export_entries(self, first_page: dict[str, Any], query: dict[str, Any]) -> Any:
        page = first_page
        while True:
            for row in list(page.get("rows") or []):
                if isinstance(row, dict):
                    yield self._export_entry_from_row(row)
            next_offset = page.get("next_offset")
            if next_offset is None:
                return
            get_export_page = query["get_export_page"]
            page = get_export_page(
                **{
                    key: value
                    for key, value in query.items()
                    if key not in {"get_export_page", "view", "scope_key", "dependency_profile"}
                },
                offset=int(next_offset),
                include_summary=False,
            )
            if not isinstance(page, dict):
                raise CostStatisticsReadModelNotFreshError(
                    {
                        "read_model_status": "unavailable",
                        "read_model_scope_key": query["scope_key"],
                        "read_model_stale_reasons": ["export_page_unavailable"],
                    },
                    message="成本统计数据正在刷新，请稍后重试导出。",
                )

    def _assert_export_gate_unchanged(
        self,
        *,
        scope_key: str,
        initial_gate: dict[str, Any],
        dependency_profile: str,
    ) -> None:
        get_freshness_gate = getattr(self._sql_read_repository, "get_cost_statistics_freshness_gate", None)
        if not callable(get_freshness_gate):
            raise CostStatisticsReadModelNotFreshError(
                {"read_model_status": "unavailable", "read_model_scope_key": scope_key},
                message="成本统计数据正在刷新，请稍后重试导出。",
            )
        gate, _expected_source_versions, non_fresh_payload = self._cost_statistics_freshness_gate(
            scope_key=scope_key,
            get_freshness_gate=get_freshness_gate,
            empty_payload_factory=lambda: self.empty_explorer_payload(scope_key.split(":", 1)[-1]),
            missing_reason="api_export_final_miss",
            stale_reason="api_export_final_stale",
            source_mismatch_reason="api_export_final_source_versions_stale",
            dependency_profile=dependency_profile,
        )
        initial_proof = (
            initial_gate.get("schema_version"),
            initial_gate.get("published_source_version"),
            initial_gate.get("source_versions"),
        )
        final_proof = (
            gate.get("schema_version") if isinstance(gate, dict) else None,
            gate.get("published_source_version") if isinstance(gate, dict) else None,
            gate.get("source_versions") if isinstance(gate, dict) else None,
        )
        if non_fresh_payload is not None or gate is None or final_proof != initial_proof:
            raise CostStatisticsReadModelNotFreshError(
                non_fresh_payload
                or {
                    "read_model_status": "stale",
                    "read_model_scope_key": scope_key,
                    "read_model_stale_reasons": ["export_snapshot_changed"],
                },
                message="成本统计数据已更新，请重新导出。",
            )

    @staticmethod
    def _export_page_summary(page: dict[str, Any]) -> dict[str, Any]:
        summary = page.get("summary")
        if not isinstance(summary, dict):
            return {
                "source_row_count": 0,
                "row_count": 0,
                "transaction_count": 0,
                "total_amount": "0.00",
            }
        return summary

    @staticmethod
    def _export_entry_from_row(raw_row: dict[str, Any]) -> dict[str, Any]:
        trade_time = str(raw_row.get("trade_time") or raw_row.get("trade_time_text") or "")
        amount = _decimal_from_value(raw_row.get("amount")) or Decimal("0.00")
        primary = str(raw_row.get("bank_tag_primary_label") or raw_row.get("bank_tag_label") or "").strip() or "未标记"
        sub = str(raw_row.get("bank_tag_sub_label") or raw_row.get("bank_tag_label") or "").strip() or primary
        label_path = [str(item).strip() for item in list(raw_row.get("bank_tag_label_path") or []) if str(item).strip()]
        if not label_path:
            label_path = [primary] if primary == sub else [primary, sub]
        return {
            "transaction_id": str(raw_row.get("transaction_id") or "").strip(),
            "month": str(raw_row.get("month") or raw_row.get("scope_month") or "")[:7] or trade_time[:7],
            "trade_time": trade_time,
            "direction": str(raw_row.get("direction") or "支出"),
            "project_name": str(raw_row.get("project_name") or "").strip(),
            "expense_type": str(raw_row.get("expense_type") or "").strip(),
            "expense_content": str(raw_row.get("expense_content") or "").strip(),
            "amount_decimal": amount,
            "amount": _plain_money(amount),
            "counterparty_name": str(raw_row.get("counterparty_name") or "").strip(),
            "payment_account_label": str(raw_row.get("payment_account_label") or "").strip(),
            "remark": str(raw_row.get("remark") or "").strip(),
            "oa_applicant": str(raw_row.get("oa_applicant") or "—").strip() or "—",
            "bank_tag_code": str(raw_row.get("bank_tag_code") or "").strip(),
            "bank_tag_label": str(raw_row.get("bank_tag_label") or sub).strip() or sub,
            "bank_tag_primary_label": primary,
            "bank_tag_sub_label": sub,
            "bank_tag_label_path": label_path,
            "period_label": str(raw_row.get("period_label") or "—"),
            "transaction_count": int(raw_row.get("transaction_count") or 0),
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
    def _bank_tag_row_from_entry(entry: dict[str, Any]) -> list[Any]:
        return [
            entry["trade_time"],
            entry["bank_tag_primary_label"],
            entry["bank_tag_sub_label"],
            entry["direction"],
            _plain_money(entry["amount_decimal"]),
            entry["expense_content"],
            entry["counterparty_name"],
            entry["payment_account_label"],
        ]

    @staticmethod
    def _directional_summary_from_export_summary(summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "expense_amount": _plain_money(_decimal_from_value(summary.get("expense_amount")) or Decimal("0.00")),
            "income_amount": _plain_money(_decimal_from_value(summary.get("income_amount")) or Decimal("0.00")),
            "expense_transaction_count": int(summary.get("expense_transaction_count") or 0),
            "income_transaction_count": int(summary.get("income_transaction_count") or 0),
        }

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
    def _table_workbook(title: str, headers: list[str], rows: Any) -> Workbook:
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet(title)
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        for index in range(1, len(headers) + 1):
            sheet.column_dimensions[chr(64 + index)].width = 18
        return workbook

    def _project_detail_workbook_from_export_pages(
        self,
        *,
        month: str,
        project_name: str,
        entries: Any,
        include_oa_details: bool,
        include_invoice_details: bool,
        include_exception_rows: bool,
        include_ignored_rows: bool,
        include_expense_content_summary: bool,
        scope_label: str,
    ) -> Workbook:
        workbook = Workbook(write_only=True)
        intro_sheet = workbook.create_sheet("导出说明")
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
        summary_sheet = workbook.create_sheet("项目汇总")
        expense_type_sheet = workbook.create_sheet("按费用类型汇总")
        expense_content_sheet = workbook.create_sheet("按费用内容汇总") if include_expense_content_summary else None
        detail_sheet = workbook.create_sheet("流水明细")
        detail_headers = ["时间", "交易流水ID", "资金方向", "对方户名", "支付账户", "金额", "备注", "项目名称", "费用类型", "费用内容", "OA单号", "关联组ID"]
        detail_sheet.append(detail_headers)
        for index in range(1, len(detail_headers) + 1):
            detail_sheet.column_dimensions[chr(64 + index)].width = 18
        if include_oa_details:
            self._append_table_sheet(workbook.create_sheet("OA关联明细"), ["OA单号", "申请人", "项目名称", "费用类型", "费用内容", "OA金额", "关联组ID"], [])
        if include_invoice_details:
            self._append_table_sheet(workbook.create_sheet("发票关联明细"), ["发票号码", "销方名称", "购方名称", "发票金额", "税额", "项目名称", "关联状态", "关联组ID"], [])
        if include_exception_rows or include_ignored_rows:
            self._append_table_sheet(workbook.create_sheet("异常与未闭环"), ["记录类型", "记录ID", "项目名称", "费用类型", "金额", "状态", "备注"], [])

        total_amount = Decimal("0.00")
        transaction_count = 0
        type_buckets: dict[str, dict[str, Any]] = {}
        content_buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in entries:
            total_amount += entry["amount_decimal"]
            transaction_count += 1
            type_bucket = type_buckets.setdefault(
                entry["expense_type"],
                {"amount_decimal": Decimal("0.00"), "transaction_count": 0, "expense_contents": set()},
            )
            type_bucket["amount_decimal"] += entry["amount_decimal"]
            type_bucket["transaction_count"] += 1
            type_bucket["expense_contents"].add(entry["expense_content"])
            content_key = (entry["expense_type"], entry["expense_content"])
            content_bucket = content_buckets.setdefault(
                content_key,
                {"amount_decimal": Decimal("0.00"), "transaction_count": 0},
            )
            content_bucket["amount_decimal"] += entry["amount_decimal"]
            content_bucket["transaction_count"] += 1
            detail_sheet.append(
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
            )

        self._fill_key_value_sheet(
            summary_sheet,
            [
                ("项目名称", project_name),
                ("统计期间", scope_label),
                ("总支出金额", _plain_money(total_amount)),
                ("支出流水笔数", transaction_count),
                ("费用类型数", len(type_buckets)),
                ("已关联OA笔数", 0),
                ("已关联发票笔数", 0),
                ("已处理异常笔数", 0),
                ("已忽略笔数", 0),
            ],
        )
        self._append_table_sheet(
            expense_type_sheet,
            ["费用类型", "金额", "占比", "笔数", "费用内容数"],
            (
                [
                    expense_type,
                    _plain_money(bucket["amount_decimal"]),
                    _percentage(bucket["amount_decimal"], total_amount),
                    bucket["transaction_count"],
                    len(bucket["expense_contents"]),
                ]
                for expense_type, bucket in sorted(
                    type_buckets.items(),
                    key=lambda item: (-item[1]["amount_decimal"], item[0]),
                )
            ),
        )
        if include_expense_content_summary:
            assert expense_content_sheet is not None
            self._append_table_sheet(
                expense_content_sheet,
                ["费用类型", "费用内容", "金额", "笔数"],
                [
                    [expense_type, expense_content, _plain_money(bucket["amount_decimal"]), bucket["transaction_count"]]
                    for (expense_type, expense_content), bucket in sorted(
                        content_buckets.items(),
                        key=lambda item: (-item[1]["amount_decimal"], item[0][0], item[0][1]),
                    )
                ],
            )
        return workbook

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
    def _append_table_sheet(sheet: Any, headers: list[str], rows: Any) -> None:
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
        if view == "bank_tag":
            return f"成本统计_{month_segment}_按标签统计.xlsx"
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
