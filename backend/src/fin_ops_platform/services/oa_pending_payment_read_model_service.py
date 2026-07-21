from __future__ import annotations

from dataclasses import dataclass
import hashlib
from http import HTTPStatus
import json
from typing import Any, Callable

from fin_ops_platform.services.oa_pending_payment_read_model_details import (
    oa_pending_payment_bank_detail_from_row,
    oa_pending_payment_invoice_detail_from_row,
    oa_pending_payment_oa_detail_from_row,
    oa_pending_payment_relation_details_from_row,
)
from fin_ops_platform.services.oa_pending_payment_query_contract import (
    OaPendingPaymentError,
    filter_config,
    parse_filters,
    parse_positive_int,
    parse_sort,
    parse_view_mode,
)
from fin_ops_platform.services.oa_pending_payment_read_model_repository import OaPendingPaymentReadModelRepositoryPort
from fin_ops_platform.services.read_model_freshness import require_expected_source_versions
from fin_ops_platform.services.read_model_query_gateway import ReadModelQueryGateway
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway


SourceVersionsProvider = Callable[[], dict[str, Any]]
OA_PENDING_PAYMENT_ROWS_CONTRACT_REVISION = "oa-pending-payment-rows-v2"
OA_PENDING_PAYMENT_ROWS_CACHE_SCHEMA_VERSION = "oa-pending-payment-rows-cache-v1"
OA_PENDING_PAYMENT_ROWS_CACHE_TTL_SECONDS = 300


@dataclass(slots=True, frozen=True)
class OaPendingPaymentRowsRead:
    status: HTTPStatus
    payload: dict[str, Any]
    etag: str | None = None


class OaPendingPaymentReadModelService:
    def __init__(
        self,
        *,
        repository: Any | None,
        queue_repository: Any | None = None,
        redis_helper: Any | None = None,
        source_versions_provider: SourceVersionsProvider | None = None,
    ) -> None:
        if repository is None or isinstance(repository, OaPendingPaymentReadModelRepositoryPort):
            self._repository = repository
        else:
            self._repository = OaPendingPaymentReadModelRepositoryPort(repository)
        self._queue_repository = queue_repository
        self._read_model_query_gateway = ReadModelQueryGateway(
            queue_repository=queue_repository,
            redis_helper=redis_helper,
        )
        self._source_versions_provider = source_versions_provider

    def rows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self.conditional_rows(query, tenant_id="default", if_none_match=None).payload

    def conditional_rows(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str,
        if_none_match: str | None,
    ) -> OaPendingPaymentRowsRead:
        scope_key = self._scope_key_from_query(query)
        view_mode = parse_view_mode(query.get("view_mode", [None])[0])
        page = parse_positive_int(query.get("page", [1])[0], "page")
        page_size = parse_positive_int(query.get("page_size", [50])[0], "page_size", maximum=200)
        parsed_filters = parse_filters(query.get("filters", [None])[0])
        sort_field, sort_direction = parse_sort(
            query.get("sort_field", ["bank_trade_time"])[0],
            query.get("sort_direction", ["desc"])[0],
        )
        if self._repository is None:
            self._enqueue_refresh(scope_key, reason="api_sql_repository_unavailable")
            return OaPendingPaymentRowsRead(
                status=HTTPStatus.ACCEPTED,
                payload=self.refreshing_rows_payload(scope_key=scope_key, blocking_scope_keys=[scope_key]),
            )

        base_source_versions = self.expected_source_versions(scope_key=scope_key)
        state = self._repository.query_state(
            scope_key=scope_key,
            tenant_id=tenant_id,
            base_source_versions=base_source_versions,
        )
        if not isinstance(state, dict):
            self._enqueue_refresh(scope_key, reason="api_freshness_proof_unavailable")
            return OaPendingPaymentRowsRead(
                status=HTTPStatus.ACCEPTED,
                payload=self.refreshing_rows_payload(scope_key=scope_key, blocking_scope_keys=[scope_key]),
            )
        blocking_scope_keys = [str(value) for value in list(state.get("blocking_scope_keys") or []) if str(value)]
        stale_reasons = [str(value) for value in list(state.get("stale_reasons") or []) if str(value)]
        if str(state.get("status") or "refreshing") != "fresh":
            refresh_scope_keys = blocking_scope_keys or [scope_key]
            for blocking_scope_key in refresh_scope_keys:
                self._enqueue_refresh(blocking_scope_key, reason="api_freshness_gate_blocked")
            return OaPendingPaymentRowsRead(
                status=HTTPStatus.ACCEPTED,
                payload=self.refreshing_rows_payload(
                    scope_key=scope_key,
                    stale_reasons=stale_reasons,
                    blocking_scope_keys=refresh_scope_keys,
                ),
            )

        statistics_state = state
        statistics_base_source_versions = base_source_versions
        if scope_key != "all":
            statistics_base_source_versions = self.expected_source_versions(scope_key="all")
            statistics_state = self._repository.query_state(
                scope_key="all",
                tenant_id=tenant_id,
                base_source_versions=statistics_base_source_versions,
            ) or {}
        if str(statistics_state.get("status") or "refreshing") != "fresh":
            statistics_blocking_scope_keys = [
                str(value)
                for value in list(statistics_state.get("blocking_scope_keys") or [])
                if str(value).strip()
            ] or ["all"]
            for blocking_scope_key in statistics_blocking_scope_keys:
                self._enqueue_refresh(str(blocking_scope_key), reason="api_statistics_freshness_gate_blocked")

        etag = self._etag(
            tenant_id=tenant_id,
            normalized_query={
                "scopeKey": scope_key,
                "keyword": str(query.get("keyword", [""])[0] or "").strip(),
                "tradeDateFrom": query.get("trade_date_from", [None])[0],
                "tradeDateTo": query.get("trade_date_to", [None])[0],
                "filters": parsed_filters,
                "sortField": sort_field,
                "sortDirection": sort_direction,
                "page": page,
                "pageSize": page_size,
                "viewMode": view_mode,
            },
            version_token="|".join(
                (
                    str(state.get("version_token") or ""),
                    str(statistics_state.get("version_token") or ""),
                )
            ),
        )
        if _etag_matches(if_none_match, etag):
            return OaPendingPaymentRowsRead(status=HTTPStatus.NOT_MODIFIED, payload={}, etag=etag)

        snapshot_state: dict[str, Any] | None = None
        snapshot_statistics_state: dict[str, Any] | None = None

        def load_rows_view() -> dict[str, Any] | None:
            nonlocal snapshot_state, snapshot_statistics_state
            with self._repository.read_snapshot() as repository:
                snapshot_state = repository.query_state(
                    scope_key=scope_key,
                    tenant_id=tenant_id,
                    base_source_versions=base_source_versions,
                )
                if (
                    not isinstance(snapshot_state, dict)
                    or str(snapshot_state.get("status") or "refreshing") != "fresh"
                    or str(snapshot_state.get("version_token") or "") != str(state.get("version_token") or "")
                ):
                    return None
                snapshot_statistics_state = (
                    snapshot_state
                    if scope_key == "all"
                    else repository.query_state(
                        scope_key="all",
                        tenant_id=tenant_id,
                        base_source_versions=statistics_base_source_versions,
                    )
                )
                rows_payload = repository.list_oa_pending_payment_rows(
                    month=query.get("month", [None])[0],
                    keyword=query.get("keyword", [None])[0],
                    trade_date_from=query.get("trade_date_from", [None])[0],
                    trade_date_to=query.get("trade_date_to", [None])[0],
                    filters=query.get("filters", [None])[0],
                    sort_field=sort_field,
                    sort_direction=sort_direction,
                    page=page,
                    page_size=page_size,
                    view_mode=view_mode,
                )
                if not isinstance(rows_payload, dict):
                    return None
                if (
                    not isinstance(snapshot_statistics_state, dict)
                    or str(snapshot_statistics_state.get("status") or "refreshing") != "fresh"
                    or str(snapshot_statistics_state.get("version_token") or "")
                    != str(statistics_state.get("version_token") or "")
                ):
                    rows_payload["statistics"] = None
                return {
                    "payload": rows_payload,
                    "source_versions": dict(snapshot_state.get("source_versions") or {}),
                    "schema_version": OA_PENDING_PAYMENT_ROWS_CACHE_SCHEMA_VERSION,
                    "refresh_status": "fresh",
                }

        try:
            cached_read = self._read_model_query_gateway.load(
                scope_type="oa_pending_payment",
                scope_key=scope_key,
                expected_schema_version=OA_PENDING_PAYMENT_ROWS_CACHE_SCHEMA_VERSION,
                expected_source_versions=dict(state.get("source_versions") or {}),
                load_view=load_rows_view,
                empty_payload_factory=lambda: self.refreshing_rows_payload(
                    scope_key=scope_key,
                    blocking_scope_keys=[scope_key],
                ),
                payload_validator=self._is_rows_payload,
                cache_key=self._rows_cache_key(etag),
                cache_ttl_seconds=OA_PENDING_PAYMENT_ROWS_CACHE_TTL_SECONDS,
                missing_reason="api_read_model_payload_unavailable",
                stale_reason="api_read_model_payload_stale",
                source_mismatch_reason="api_read_model_payload_source_versions_stale",
                payload_invalid_reason="api_read_model_payload_invalid",
            )
        except OaPendingPaymentError:
            raise
        except ValueError as exc:
            raise OaPendingPaymentError("invalid_oa_pending_payment_query", str(exc)) from exc
        if cached_read.freshness_status != "fresh":
            failed_state = snapshot_state if isinstance(snapshot_state, dict) else {}
            refresh_scope_keys = [
                str(value) for value in list(failed_state.get("blocking_scope_keys") or []) if str(value)
            ] or [scope_key]
            for blocking_scope_key in refresh_scope_keys:
                self._enqueue_refresh(blocking_scope_key, reason="api_freshness_gate_changed_during_read")
            return OaPendingPaymentRowsRead(
                status=HTTPStatus.ACCEPTED,
                payload=self.refreshing_rows_payload(
                    scope_key=scope_key,
                    stale_reasons=[str(value) for value in list(failed_state.get("stale_reasons") or []) if str(value)],
                    blocking_scope_keys=refresh_scope_keys,
                ),
            )
        payload = cached_read.payload

        result = dict(payload)
        result.pop("read_model_schema_version", None)
        result.pop("refresh_enqueued", None)
        result["filterConfig"] = filter_config()
        result["appliedFilters"] = {"filters": parsed_filters}
        result["sort"] = {"field": sort_field, "direction": sort_direction}
        result["viewMode"] = view_mode
        result["sourceVersions"] = dict(state.get("source_versions") or {})
        result["source_versions"] = dict(state.get("source_versions") or {})
        result["read_model_status"] = "fresh"
        result["readModelStatus"] = "fresh"
        result["read_model_scope_key"] = scope_key
        return OaPendingPaymentRowsRead(status=HTTPStatus.OK, payload=result, etag=etag)

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        return self._detail(
            lookup_method_name="get_oa_pending_payment_row_by_oa_id",
            identifier=oa_id,
            builder=oa_pending_payment_oa_detail_from_row,
            not_found_code="oa_not_found",
            not_found_message=f"OA detail not found: {oa_id}",
            title="OA详情",
        )

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        return self._detail(
            lookup_method_name="get_oa_pending_payment_row_by_bank_transaction_id",
            identifier=bank_transaction_id,
            builder=lambda row: oa_pending_payment_bank_detail_from_row(row, bank_transaction_id),
            not_found_code="bank_transaction_not_found",
            not_found_message=f"Bank transaction detail not found: {bank_transaction_id}",
            title="支出流水详情",
        )

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        return self._detail(
            lookup_method_name="get_oa_pending_payment_row_by_invoice_id",
            identifier=invoice_id,
            builder=lambda row: oa_pending_payment_invoice_detail_from_row(row, invoice_id),
            not_found_code="invoice_not_found",
            not_found_message=f"Invoice detail not found: {invoice_id}",
            title="发票详情",
        )

    def relation_details(self, row_id: str, *, kind: str) -> dict[str, Any]:
        title = "支出流水关联明细" if kind == "bank" else "发票关联明细"
        return self._detail(
            lookup_method_name="get_oa_pending_payment_row_by_row_id",
            identifier=row_id,
            builder=lambda row: oa_pending_payment_relation_details_from_row(row, kind=kind),
            not_found_code="row_not_found",
            not_found_message=f"OA pending payment row not found: {row_id}",
            title=title,
        )

    def expected_source_versions(self, *, scope_key: str | None = None) -> dict[str, Any]:
        if not callable(self._source_versions_provider):
            return require_expected_source_versions({}, context="oa_pending_payment_read_model")
        return require_expected_source_versions(
            _source_versions_from_provider(self._source_versions_provider, scope_key=scope_key) or {},
            context="oa_pending_payment_read_model",
        )

    def refreshing_rows_payload(
        self,
        *,
        scope_key: str,
        stale_reasons: list[str] | None = None,
        blocking_scope_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_blocking_scope_keys = list(dict.fromkeys(blocking_scope_keys or [scope_key]))
        payload: dict[str, Any] = {
            "rows": [],
            "pagination": {"page": 1, "pageSize": 50, "total": 0},
            "summary": {"rowCount": 0, "viewCounts": {"completed": 0, "in_progress": 0}},
            "statistics": None,
            "filterConfig": filter_config(),
            "filterOptions": {},
            "read_model_status": "refreshing",
            "readModelStatus": "refreshing",
            "read_model_scope_key": scope_key,
            "operationBarrierTargets": [
                {"readModelKey": "oa_pending_payment", "scopeKey": blocking_scope_key}
                for blocking_scope_key in normalized_blocking_scope_keys
            ],
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        return payload

    def _detail(
        self,
        *,
        lookup_method_name: str,
        identifier: str,
        builder: Callable[[dict[str, Any]], dict[str, Any]],
        not_found_code: str,
        not_found_message: str,
        title: str,
    ) -> dict[str, Any]:
        if self._repository is None:
            self._enqueue_refresh("all", reason="api_detail_sql_repository_unavailable")
            return self._refreshing_detail_payload(title=title, scope_key="all")
        with self._repository.read_snapshot() as repository:
            lookup = getattr(repository, lookup_method_name, None)
            if not callable(lookup):
                self._enqueue_refresh("all", reason="api_detail_sql_repository_unavailable")
                return self._refreshing_detail_payload(title=title, scope_key="all")
            payload = lookup(identifier)
            if not isinstance(payload, dict):
                self._enqueue_refresh("all", reason="api_detail_miss")
                return self._refreshing_detail_payload(title=title, scope_key="all")
            scope_key = str(payload.get("read_model_scope_key") or "all")
            state = repository.query_state(
                scope_key=scope_key,
                tenant_id="default",
                base_source_versions=self.expected_source_versions(scope_key=scope_key),
            )
            if not isinstance(state, dict) or str(state.get("status") or "refreshing") != "fresh":
                blocking_scope_keys = [str(value) for value in list((state or {}).get("blocking_scope_keys") or [scope_key])]
                for blocking_scope_key in blocking_scope_keys:
                    self._enqueue_refresh(blocking_scope_key, reason="api_detail_freshness_gate_blocked")
                return self._refreshing_detail_payload(
                    title=title,
                    scope_key=scope_key,
                    stale_reasons=[str(value) for value in list((state or {}).get("stale_reasons") or [])],
                )
        row = payload.get("row")
        if not isinstance(row, dict):
            raise OaPendingPaymentError(not_found_code, not_found_message, status_code=HTTPStatus.NOT_FOUND)
        try:
            detail_payload = builder(row)
        except ValueError as exc:
            raise OaPendingPaymentError("invalid_relation_kind", str(exc)) from exc
        if not isinstance(detail_payload, dict):
            raise OaPendingPaymentError(not_found_code, not_found_message, status_code=HTTPStatus.NOT_FOUND)
        detail_payload["read_model_status"] = "fresh"
        detail_payload["readModelStatus"] = "fresh"
        detail_payload["read_model_scope_key"] = scope_key
        return detail_payload

    @staticmethod
    def _refreshing_detail_payload(
        *,
        title: str,
        scope_key: str,
        stale_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": title,
            "detailAvailable": False,
            "unavailableReason": "详情数据正在刷新，请稍后重试。",
            "sections": [],
            "read_model_status": "refreshing",
            "readModelStatus": "refreshing",
            "read_model_scope_key": scope_key,
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        return payload

    @staticmethod
    def _scope_key_from_query(query: dict[str, list[str]]) -> str:
        month = str(query.get("month", [""])[0] or "").strip()
        if len(month) >= 7 and month[4] == "-":
            return month[:7]
        return "all"

    def _enqueue_refresh(self, scope_key: str, *, reason: str) -> bool:
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            return False
        return bool(refresh_gateway.enqueue_one("oa_pending_payment", scope_key, reason=reason))

    @staticmethod
    def _is_rows_payload(payload: dict[str, Any]) -> bool:
        return (
            isinstance(payload.get("rows"), list)
            and isinstance(payload.get("pagination"), dict)
            and isinstance(payload.get("summary"), dict)
            and isinstance(payload.get("filterOptions"), dict)
        )

    @staticmethod
    def _rows_cache_key(etag: str) -> str:
        return "oa_pending_payment:rows:" + etag.strip('"')

    @staticmethod
    def _etag(*, tenant_id: str, normalized_query: dict[str, Any], version_token: str) -> str:
        material = {
            "tenantId": str(tenant_id or "default"),
            "query": normalized_query,
            "contractRevision": OA_PENDING_PAYMENT_ROWS_CONTRACT_REVISION,
            "readModelVersionToken": version_token,
        }
        digest = hashlib.sha256(
            json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f'"oa-pending-payment-{digest}"'


def _source_versions_from_provider(provider: SourceVersionsProvider, *, scope_key: str | None) -> dict[str, Any]:
    try:
        return dict(provider(scope_key=scope_key) or {})  # type: ignore[misc]
    except TypeError:
        return dict(provider() or {})


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    candidates = [candidate.strip() for candidate in str(if_none_match or "").split(",") if candidate.strip()]
    return "*" in candidates or etag in candidates or f"W/{etag}" in candidates
