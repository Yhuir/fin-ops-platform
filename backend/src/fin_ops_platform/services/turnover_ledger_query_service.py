from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.read_model_query_gateway import ReadModelQueryGateway


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
        expected_source_versions = self._source_versions_provider()
        read_model_payload = self._read_from_repository(
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
        )
        if isinstance(read_model_payload, dict):
            read_model_payload = self._normalize_all_scope_source_versions(
                read_model_payload,
                expected_source_versions=expected_source_versions,
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
        return result.payload

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
    def _normalize_all_scope_source_versions(
        payload: dict[str, Any],
        *,
        expected_source_versions: dict[str, Any],
    ) -> dict[str, Any]:
        refresh_status = str(payload.get("refresh_status") or "").strip().lower()
        if payload.get("source_versions_mixed") is True and refresh_status == "fresh":
            return {**payload, "source_versions": dict(expected_source_versions)}
        return payload

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
