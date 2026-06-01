from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.read_model_freshness import source_version_mismatch_reasons


TURNOVER_LEDGER_SCOPE_TYPE = "turnover_ledger"
TURNOVER_LEDGER_REFRESH_EVENT_TYPE = "turnover_ledger.read_model.refresh"


class TurnoverLedgerQueryService:
    def __init__(
        self,
        *,
        read_repository: Any | None,
        refresh_queue_repository: Any | None,
        source_versions_provider: Callable[[], dict[str, Any]],
        legacy_payload_builder: Callable[..., dict[str, Any]],
        settings_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._read_repository = read_repository
        self._refresh_queue_repository = refresh_queue_repository
        self._source_versions_provider = source_versions_provider
        self._legacy_payload_builder = legacy_payload_builder
        self._settings_provider = settings_provider or (lambda: {})

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
            stale_reasons = source_version_mismatch_reasons(
                expected=expected_source_versions,
                actual=read_model_payload.get("source_versions") if isinstance(read_model_payload.get("source_versions"), dict) else {},
            )
            if not stale_reasons and str(read_model_payload.get("read_model_status") or "fresh") == "fresh":
                return read_model_payload
            refresh_enqueued = self._enqueue_refresh(reason="api_stale")
            return self._stale_payload(
                read_model_payload,
                stale_reasons=stale_reasons,
                refresh_reason="source_version_mismatch" if stale_reasons else "api_stale",
                refresh_enqueued=refresh_enqueued,
            )

        if self._postgres_required():
            refresh_enqueued = self._enqueue_refresh(reason="api_miss")
            return self._empty_refreshing_payload(
                family=family,
                direction=direction,
                status=status,
                page=page,
                page_size=page_size,
                source_versions=expected_source_versions,
                refresh_enqueued=refresh_enqueued,
            )

        payload = self._legacy_payload_builder(
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
        )
        result = dict(payload) if isinstance(payload, dict) else {}
        if "source_versions" not in result:
            result["source_versions"] = dict(expected_source_versions)
            result["rows"] = [
                {**row, "source_versions": dict(expected_source_versions)}
                if isinstance(row, dict) and "source_versions" not in row
                else row
                for row in list(result.get("rows") or [])
            ]
        return result

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

    def _postgres_required(self) -> bool:
        settings = self._settings_provider()
        return bool(settings.get("postgres_required")) if isinstance(settings, dict) else False

    def _enqueue_refresh(self, *, reason: str) -> bool:
        enqueue = getattr(self._refresh_queue_repository, "enqueue_read_model_refresh", None)
        if callable(enqueue):
            enqueue(scope_type=TURNOVER_LEDGER_SCOPE_TYPE, scope_key="all", reason=reason)
            return True
        return False

    @staticmethod
    def _stale_payload(
        payload: dict[str, Any],
        *,
        stale_reasons: list[str],
        refresh_reason: str,
        refresh_enqueued: bool,
    ) -> dict[str, Any]:
        result = dict(payload)
        result["read_model_status"] = "refreshing"
        result["refresh_enqueued"] = refresh_enqueued
        result["refresh_reason"] = refresh_reason
        if stale_reasons:
            result["read_model_stale_reasons"] = list(stale_reasons)
        return result

    @staticmethod
    def _empty_refreshing_payload(
        *,
        family: str,
        direction: str,
        status: str | None,
        page: int,
        page_size: int,
        source_versions: dict[str, Any],
        refresh_enqueued: bool,
    ) -> dict[str, Any]:
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 50), 1), 200)
        return {
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
            "read_model_status": "refreshing",
            "refresh_enqueued": refresh_enqueued,
            "refresh_reason": "api_miss",
        }
