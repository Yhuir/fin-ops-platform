from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.read_model_query_gateway import ReadModelQueryGateway
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway


TURNOVER_LEDGER_SCOPE_TYPE = "turnover_ledger"
TURNOVER_LEDGER_REFRESH_EVENT_TYPE = "turnover_ledger.read_model.refresh"


class TurnoverLedgerQueryService:
    def __init__(
        self,
        *,
        read_repository: Any | None,
        refresh_queue_repository: Any | None,
        source_versions_provider: Callable[[], dict[str, Any]],
    ) -> None:
        self._read_repository = read_repository
        self._refresh_queue_repository = refresh_queue_repository
        self._source_versions_provider = source_versions_provider

    def list_ledger(
        self,
        *,
        family: str = "all",
        direction: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
        view: str | None = None,
    ) -> dict[str, Any]:
        _ = view
        expected_source_versions = dict(self._source_versions_provider())
        expected_source_version_contract = require_expected_source_versions(
            expected_source_versions,
            context="turnover_ledger:list_ledger",
        )
        freshness_view = self._freshness_view()
        if not isinstance(freshness_view, dict):
            return self._non_fresh_payload(
                family=family,
                direction=direction,
                status=status,
                page=page,
                page_size=page_size,
                source_versions=expected_source_versions,
                refresh_reason="api_miss",
                refresh_scope_keys=["all"],
                refresh_enqueued=self._enqueue_refresh(
                    scope_key="all",
                    reason="api_miss",
                ),
            )
        actual_source_versions = (
            dict(freshness_view.get("source_versions"))
            if isinstance(freshness_view.get("source_versions"), dict)
            else {}
        )
        refresh_status = str(freshness_view.get("refresh_status") or "fresh").strip().lower()
        stale_reasons = source_version_mismatch_reasons(
            expected=expected_source_version_contract,
            actual=actual_source_versions,
        )
        if refresh_status != "fresh":
            return self._non_fresh_payload(
                family=family,
                direction=direction,
                status=status,
                page=page,
                page_size=page_size,
                source_versions=actual_source_versions,
                refresh_reason="api_stale",
                refresh_scope_keys=[],
                refresh_enqueued=False,
                stale_reasons=[f"dirty_scope_{refresh_status}", *stale_reasons],
            )
        if stale_reasons:
            exact_refreshes = self._relation_delta_refreshes(
                expected_source_versions=expected_source_versions,
                actual_source_versions=actual_source_versions,
                stale_reasons=stale_reasons,
            )
            if exact_refreshes:
                refresh_enqueued = False
                for scope_key, metadata in exact_refreshes.items():
                    refresh_enqueued = bool(
                        self._refresh_gateway().enqueue_many_events(
                            TURNOVER_LEDGER_SCOPE_TYPE,
                            [scope_key],
                            reason="api_relation_delta",
                            metadata=metadata,
                        )
                    ) or refresh_enqueued
                return self._non_fresh_payload(
                    family=family,
                    direction=direction,
                    status=status,
                    page=page,
                    page_size=page_size,
                    source_versions=actual_source_versions,
                    refresh_reason="api_relation_delta",
                    refresh_scope_keys=list(exact_refreshes),
                    refresh_enqueued=refresh_enqueued,
                    stale_reasons=stale_reasons,
                )
            return self._non_fresh_payload(
                family=family,
                direction=direction,
                status=status,
                page=page,
                page_size=page_size,
                source_versions=actual_source_versions,
                refresh_reason="source_version_mismatch",
                refresh_scope_keys=["all"],
                refresh_enqueued=self._enqueue_refresh(
                    scope_key="all",
                    reason="api_stale",
                ),
                stale_reasons=stale_reasons,
            )
        read_model_payload = self._read_from_repository(
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
        )

        result = ReadModelQueryGateway(queue_repository=self._refresh_queue_repository).load(
            scope_type=TURNOVER_LEDGER_SCOPE_TYPE,
            scope_key="all",
            expected_source_versions=expected_source_versions,
            load_view=lambda: read_model_payload,
            payload_from_view=lambda view: view,
            empty_payload_factory=lambda: self._empty_refreshing_payload(
                family=family,
                direction=direction,
                status=status,
                page=page,
                page_size=page_size,
                source_versions=expected_source_versions,
            ),
            missing_reason="api_miss",
            stale_reason="api_stale",
            source_mismatch_reason="api_stale",
        )
        payload = dict(result.payload)
        payload.pop("generation", None)
        if payload.get("read_model_status") != "fresh":
            payload["statistics"] = None
            payload["statistics_status"] = "refreshing"
        return payload

    def _freshness_view(self) -> dict[str, Any] | None:
        load_freshness = getattr(
            self._read_repository,
            "get_turnover_ledger_freshness_view",
            None,
        )
        if not callable(load_freshness):
            return None
        payload = load_freshness()
        return dict(payload) if isinstance(payload, dict) else None

    def _relation_delta_refreshes(
        self,
        *,
        expected_source_versions: dict[str, Any],
        actual_source_versions: dict[str, Any],
        stale_reasons: list[str],
    ) -> dict[str, dict[str, object]]:
        closure_key = "turnover_manual_closure_source_version"
        if stale_reasons != [f"{closure_key}_mismatch"]:
            return {}
        actual_closure = actual_source_versions.get(closure_key)
        expected_closure = expected_source_versions.get(closure_key)
        if not isinstance(actual_closure, dict) or not isinstance(expected_closure, dict):
            return {}
        updated_after = str(actual_closure.get("relation_updated_at") or "").strip()
        load_changes = getattr(
            self._read_repository,
            "list_turnover_manual_closure_changes",
            None,
        )
        if not updated_after or not callable(load_changes):
            return {}
        changes = load_changes(updated_after=updated_after)
        if not isinstance(changes, list) or not changes:
            return {}
        refreshes: dict[str, dict[str, object]] = {}
        for item in changes:
            if not isinstance(item, dict):
                return {}
            case_id = str(item.get("case_id") or "").strip()
            relation_status = str(item.get("status") or "").strip()
            row_ids = list(
                dict.fromkeys(
                    str(row_id).strip()
                    for row_id in list(item.get("row_ids") or [])
                    if str(row_id).strip()
                )
            )
            affected_months = list(
                dict.fromkeys(
                    str(month).strip()
                    for month in list(item.get("affected_months") or [])
                    if str(month).strip() and str(month).strip() != "all"
                )
            )
            if not case_id or not relation_status or not row_ids or not affected_months:
                return {}
            delta = {
                "status": relation_status,
                "row_ids": row_ids,
                "updated_at": str(item.get("updated_at") or "").strip(),
            }
            for scope_key in affected_months:
                metadata = refreshes.setdefault(
                    scope_key,
                    {"row_ids": [], "case_ids": [], "relation_deltas": {}},
                )
                metadata["row_ids"] = list(
                    dict.fromkeys([*list(metadata["row_ids"]), *row_ids])
                )
                metadata["case_ids"] = list(
                    dict.fromkeys([*list(metadata["case_ids"]), case_id])
                )
                relation_deltas = metadata["relation_deltas"]
                assert isinstance(relation_deltas, dict)
                relation_deltas[case_id] = delta
        return refreshes

    def _refresh_gateway(self) -> ReadModelRefreshGateway:
        return ReadModelRefreshGateway(
            queue_repository=self._refresh_queue_repository,
        )

    def _enqueue_refresh(self, *, scope_key: str, reason: str) -> bool:
        return bool(
            self._refresh_gateway().enqueue_many_events(
                TURNOVER_LEDGER_SCOPE_TYPE,
                [scope_key],
                reason=reason,
            )
        )

    def _non_fresh_payload(
        self,
        *,
        family: str,
        direction: str,
        status: str | None,
        page: int,
        page_size: int,
        source_versions: dict[str, Any],
        refresh_reason: str,
        refresh_scope_keys: list[str],
        refresh_enqueued: bool,
        stale_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = self._empty_refreshing_payload(
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
            source_versions=source_versions,
        )
        payload.update(
            {
                "read_model_status": "refreshing",
                "read_model_scope_key": "all",
                "refresh_reason": refresh_reason,
                "refresh_scope_keys": list(refresh_scope_keys),
                "refresh_enqueued": refresh_enqueued,
            }
        )
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        return payload

    def _read_from_repository(
        self,
        *,
        family: str,
        direction: str,
        status: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any] | None:
        read_turnover_ledger = getattr(self._read_repository, "list_turnover_ledger_view", None)
        if not callable(read_turnover_ledger):
            return None
        return read_turnover_ledger(
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
            scope_key="all",
        )

    @staticmethod
    def _empty_refreshing_payload(
        *,
        family: str,
        direction: str,
        status: str | None,
        page: int,
        page_size: int,
        source_versions: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 50), 1), 200)
        return {
            "statistics": None,
            "statistics_status": "refreshing",
            "summary": {
                "pending_repayment_amount": "0.00",
                "repaid_amount": "0.00",
                "pending_collection_amount": "0.00",
                "collected_amount": "0.00",
                "closed_amount": "0.00",
                "suggested_count": 0,
                "conflict_count": 0,
                "row_count": 0,
            },
            "family_summaries": [],
            "rows": [],
            "pagination": {"page": normalized_page, "page_size": normalized_page_size, "total": 0},
            "filters": {"family": family or "all", "direction": direction or "all", "status": status},
            "source_versions": dict(source_versions),
        }
