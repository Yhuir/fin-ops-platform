from __future__ import annotations

from contextlib import contextmanager
import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.pending_invoice_read_model_repository import PendingInvoiceReadModelRepositoryPort
from fin_ops_platform.services.postgres_repositories import read_models as read_models_module
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.pending_invoice_read_model_service import (
    PendingInvoiceReadModelService,
    PendingInvoiceSourceVersionsProvider,
    pending_invoice_source_versions,
)
from fin_ops_platform.services.pending_invoice_service import (
    PENDING_INVOICE_EXPORT_ROW_LIMIT,
    PendingInvoiceError,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
    BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.search_read_model_repository import SearchReadModelRepositoryPort
from fin_ops_platform.services.search_query_freshness_service import (
    SearchIndexSourceVersionsProvider,
    SearchQueryFreshnessService,
)
from fin_ops_platform.services.search_read_model_refresh_producer import SearchReadModelRefreshProducer
from fin_ops_platform.services.search_pending_read_model_refresh import SearchPendingReadModelRefreshService
from fin_ops_platform.services.search_pending_sql_projection import SearchPendingSqlProjectionBuilder


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> None:
        self.completed.append((tenant_id, scope_type, scope_key))


class AtomicBatchQueueRecorder(QueueRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.refresh_batches: list[dict[str, object]] = []

    def enqueue_read_model_refreshes_if_inactive(
        self,
        **kwargs: object,
    ) -> list[RuntimeQueueEvent]:
        self.refresh_batches.append(dict(kwargs))
        return []


class _PendingInvoiceRowsTestResponse:
    def __init__(self, *, status_code: HTTPStatus, payload: dict[str, object]) -> None:
        self.status_code = int(status_code)
        self.body = json.dumps(payload)


def _pending_invoice_rows_response(app: Application, query: dict[str, list[str]]) -> _PendingInvoiceRowsTestResponse:
    status_code, payload = app._pending_invoice_routes().rows(query)
    return _PendingInvoiceRowsTestResponse(status_code=status_code, payload=payload)


class SearchRefreshGatewayRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def can_enqueue(self) -> bool:
        return True

    def enqueue_many(
        self,
        scope_type: str,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> list[str]:
        self.refreshes.extend((scope_type, scope_key, reason) for scope_key in scope_keys)
        return list(scope_keys)


class FakeSearchRefreshProducer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def enqueue_scope_keys(self, scope_keys: list[str], *, reason: str, **_kwargs: object) -> list[str]:
        self.calls.append((list(scope_keys), reason))
        return list(scope_keys)


class UnderlyingPendingInvoiceReadModelRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_pending_invoice_rows(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_pending_invoice_rows", dict(kwargs)))
        return {"rows": [{"id": "pending-1"}], "read_model_status": "fresh"}

    def list_pending_invoice_filter_options(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_pending_invoice_filter_options", dict(kwargs)))
        return {"options": [{"field": "status_code", "value": "paid_pending_invoice"}]}

    def pending_invoice_source_summary(self, **kwargs: object) -> dict[str, int]:
        self.calls.append(("pending_invoice_source_summary", dict(kwargs)))
        return {"bank_transaction_rows": 1}

    def pending_invoice_bank_detail_source_versions(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("pending_invoice_bank_detail_source_versions", dict(kwargs)))
        return {"bank_detail_schema_version": 2}

    def pending_invoice_workbench_relation_source_versions(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("pending_invoice_workbench_relation_source_versions", dict(kwargs)))
        return {"workbench_relation_schema_version": "v1"}

    def save_pending_invoice_rows(self, **kwargs: object) -> None:
        self.calls.append(("save_pending_invoice_rows", dict(kwargs)))

    def mark_pending_invoice_scope(self, **kwargs: object) -> None:
        self.calls.append(("mark_pending_invoice_scope", dict(kwargs)))


class UnderlyingSearchReadModelRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def search_index(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("search_index", dict(kwargs)))
        return {
            "query": kwargs.get("q"),
            "summary": {"total": 0, "oa": 0, "bank": 0, "invoice": 0},
            "refresh_status": "fresh",
        }

    def save_search_index_rows(self, **kwargs: object) -> None:
        self.calls.append(("save_search_index_rows", dict(kwargs)))

    def search_index_scope_summary(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("search_index_scope_summary", dict(kwargs)))
        return {
            "read_model_status": "fresh",
            "row_count": 1,
            "source_versions": {"search": "v1"},
        }


def _pending_invoice_expected_source_versions() -> dict[str, object]:
    return {
        "pending_invoice_read_model_schema_version": "2026-06-pending-invoice-oa-identity-v2",
        "invoice_lifecycle_policy_schema_version": 1,
        "pending_invoice_tag_groups_version": 1,
        "pending_output_invoice_tag_groups_version": 1,
        "bank_auto_tag_rules_version": 1,
        "oa_attachment_invoice_parser_version": "2026-05-28-attachment-status-v1:2026-05-11-evidence-v1",
        "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
        "bank_detail_source_versions": {},
        "workbench_relation_source_versions": {},
    }


def _pending_invoice_statistics_contract(
    *,
    expense_versions: dict[str, object] | None = None,
    income_versions: dict[str, object] | None = None,
) -> dict[str, object]:
    statistics = {
        "bank_transaction_count": 0,
        "expense_transaction_count": 0,
        "income_transaction_count": 0,
        "found_invoice_transaction_count": 0,
        "pending_invoice_transaction_count": 0,
        "no_invoice_required_transaction_count": 0,
        "cash_income_transaction_count": 0,
        "linked_oa_transaction_count": 0,
        "linked_input_invoice_transaction_count": 0,
        "linked_output_invoice_transaction_count": 0,
    }
    return {
        "statistics": statistics,
        "statistics_status": "fresh",
        "statistics_source_versions_by_scope": {
            "expense:all": expense_versions or _pending_invoice_expected_source_versions(),
            "income:all": income_versions or _pending_invoice_expected_source_versions(),
        },
    }


def _search_expected_source_versions() -> dict[str, object]:
    return SearchIndexSourceVersionsProvider(
        bank_auto_tag_rules_version_provider=lambda: 1,
        oa_attachment_invoice_parser_version_provider=lambda: "parser-v1",
        oa_projection_sync_version_provider=lambda: OA_PROJECTION_SYNC_VERSION,
    ).expected_source_versions()


class PendingInvoiceReadModelRepositoryPortTests(unittest.TestCase):
    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        underlying = UnderlyingPendingInvoiceReadModelRepository()
        port = PendingInvoiceReadModelRepositoryPort(underlying)

        self.assertEqual(
            port.list_pending_invoice_rows(
                direction="expense",
                filter="all",
                date_from=None,
                date_to=None,
                keyword=None,
                filters=None,
                page=1,
                page_size=50,
            )["rows"][0]["id"],
            "pending-1",
        )
        self.assertEqual(
            port.list_pending_invoice_filter_options(
                direction="expense",
                filter="all",
                date_from=None,
                date_to=None,
                keyword=None,
                filters=None,
            )["options"][0]["value"],
            "paid_pending_invoice",
        )
        self.assertEqual(
            port.pending_invoice_source_summary(direction="expense", date_from=None, date_to=None)[
                "bank_transaction_rows"
            ],
            1,
        )
        self.assertEqual(
            port.pending_invoice_bank_detail_source_versions(
                direction="expense",
                filter="all",
                date_from=None,
                date_to=None,
                keyword=None,
                filters=None,
            )["bank_detail_schema_version"],
            2,
        )
        self.assertEqual(
            port.pending_invoice_workbench_relation_source_versions(
                direction="expense",
                filter="all",
                date_from=None,
                date_to=None,
                keyword=None,
                filters=None,
            )["workbench_relation_schema_version"],
            "v1",
        )
        port.save_pending_invoice_rows(
            scope_key="expense:all:2026-05",
            rows=[{"id": "pending-1"}],
            source_versions={"schema": "v1"},
        )
        port.mark_pending_invoice_scope(
            scope_key="expense:all:2026-06",
            row_count=0,
            source_versions={"schema": "v2"},
        )

        self.assertFalse(hasattr(port, "search_index"))
        self.assertFalse(hasattr(port, "save_search_index_rows"))
        self.assertFalse(hasattr(port, "list_bank_detail_transactions"))
        self.assertFalse(hasattr(port, "list_workbench_relation_rows"))
        self.assertEqual(
            [name for name, _payload in underlying.calls],
            [
                "list_pending_invoice_rows",
                "list_pending_invoice_filter_options",
                "pending_invoice_source_summary",
                "pending_invoice_bank_detail_source_versions",
                "pending_invoice_workbench_relation_source_versions",
                "save_pending_invoice_rows",
                "mark_pending_invoice_scope",
            ],
        )


class SearchReadModelRepositoryPortTests(unittest.TestCase):
    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        underlying = UnderlyingSearchReadModelRepository()
        port = SearchReadModelRepositoryPort(underlying)

        payload = port.search_index(
            q="昆明",
            scope="all",
            month="2026-05",
            project_name=None,
            status=None,
            limit=20,
        )
        port.save_search_index_rows(
            scope_key="2026-05",
            rows=[{"row_id": "txn-1"}],
            source_versions={"search": "v1"},
        )
        summary = port.search_index_scope_summary(month="2026-05")

        self.assertEqual(payload["refresh_status"], "fresh")
        self.assertEqual(summary["row_count"], 1)
        self.assertFalse(hasattr(port, "list_pending_invoice_rows"))
        self.assertFalse(hasattr(port, "save_pending_invoice_rows"))
        self.assertFalse(hasattr(port, "list_bank_detail_transactions"))
        self.assertFalse(hasattr(port, "list_no_oa_bank_batch_rows"))
        self.assertFalse(hasattr(port, "list_workbench_relation_rows"))
        self.assertEqual(
            [name for name, _payload in underlying.calls],
            ["search_index", "save_search_index_rows", "search_index_scope_summary"],
        )


class SearchQueryFreshnessServiceTests(unittest.TestCase):
    def test_missing_sql_payload_enqueues_refresh_without_live_scan(self) -> None:
        queue = QueueRecorder()
        service = SearchQueryFreshnessService(
            read_repository=type("SearchRepo", (), {"search_index": lambda *_args, **_kwargs: None})(),
            source_versions_provider=_search_expected_source_versions,
            enqueue_refresh=lambda scope_key, *, reason, metadata=None: queue.enqueue_read_model_refresh(
                scope_type="search",
                scope_key=scope_key,
                reason=reason,
            ),
        )

        payload = service.get_payload(
            q="昆明",
            scope="all",
            month="2026-05",
            project_name=None,
            status=None,
            limit=20,
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(queue.refreshes, [("search", "2026-05", "api_miss")])

    def test_fresh_sql_payload_preserves_rows_and_does_not_enqueue(self) -> None:
        queue = QueueRecorder()
        source_versions = _search_expected_source_versions()
        service = SearchQueryFreshnessService(
            read_repository=type(
                "SearchRepo",
                (),
                {
                    "search_index": lambda *_args, **_kwargs: {
                        "query": "昆明",
                        "filters": {
                            "scope": "all",
                            "month": "2026-05",
                            "project_name": None,
                            "status": None,
                            "limit": 20,
                        },
                        "summary": {"total": 1, "oa": 0, "bank": 1, "invoice": 0},
                        "oa_results": [],
                        "bank_results": [{"row_id": "txn-1"}],
                        "invoice_results": [],
                        "refresh_status": "fresh",
                        "source_versions": source_versions,
                    }
                },
            )(),
            source_versions_provider=lambda: source_versions,
            enqueue_refresh=lambda scope_key, *, reason, metadata=None: queue.enqueue_read_model_refresh(
                scope_type="search",
                scope_key=scope_key,
                reason=reason,
            ),
        )

        payload = service.get_payload(
            q="昆明",
            scope="all",
            month="2026-05",
            project_name=None,
            status=None,
            limit=20,
        )

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["bank_results"], [{"row_id": "txn-1"}])
        self.assertEqual(queue.refreshes, [])

    def test_source_version_mismatch_marks_stale_and_enqueues_refresh(self) -> None:
        queue = QueueRecorder()
        source_versions = _search_expected_source_versions()
        stale_versions = dict(source_versions)
        stale_versions["bank_auto_tag_rules_version"] = "old"
        service = SearchQueryFreshnessService(
            read_repository=type(
                "SearchRepo",
                (),
                {
                    "search_index": lambda *_args, **_kwargs: {
                        "query": "昆明",
                        "filters": {
                            "scope": "all",
                            "month": "2026-05",
                            "project_name": None,
                            "status": None,
                            "limit": 20,
                        },
                        "summary": {"total": 1, "oa": 0, "bank": 1, "invoice": 0},
                        "oa_results": [],
                        "bank_results": [{"row_id": "txn-1"}],
                        "invoice_results": [],
                        "refresh_status": "fresh",
                        "source_versions": stale_versions,
                    }
                },
            )(),
            source_versions_provider=lambda: source_versions,
            enqueue_refresh=lambda scope_key, *, reason, metadata=None: queue.enqueue_read_model_refresh(
                scope_type="search",
                scope_key=scope_key,
                reason=reason,
            ),
        )

        payload = service.get_payload(
            q="昆明",
            scope="all",
            month="2026-05",
            project_name=None,
            status=None,
            limit=20,
        )

        self.assertEqual(payload["read_model_status"], "stale")
        self.assertIn("bank_auto_tag_rules_version_mismatch", payload["read_model_stale_reasons"])
        self.assertEqual(queue.refreshes, [("search", "2026-05", "api_source_versions_stale")])


class SearchReadModelRefreshProducerTests(unittest.TestCase):
    def test_enqueue_uses_gateway_and_normalizes_search_scopes(self) -> None:
        gateway = SearchRefreshGatewayRecorder()
        producer = SearchReadModelRefreshProducer(refresh_gateway_provider=lambda: gateway)

        enqueued = producer.enqueue(
            ["", "2026-05", "bad", "all", "2026-05"],
            reason="workbench_scope_invalidated",
            metadata={"action_name": "confirm_link"},
        )

        self.assertTrue(enqueued)
        self.assertEqual(
            gateway.refreshes,
            [
                ("search", "2026-05", "workbench_scope_invalidated"),
                ("search", "all", "workbench_scope_invalidated"),
            ],
        )

    def test_invalidate_maps_month_scope_inputs_or_all_fallback(self) -> None:
        gateway = SearchRefreshGatewayRecorder()
        producer = SearchReadModelRefreshProducer(refresh_gateway_provider=lambda: gateway)

        producer.invalidate(["2026-05", "2026-06", "ignored"], reason="import_state_changed")
        producer.invalidate(["project-only"], reason="settings_update")

        self.assertEqual(
            gateway.refreshes,
            [
                ("search", "2026-05", "import_state_changed"),
                ("search", "2026-06", "import_state_changed"),
                ("search", "all", "settings_update"),
            ],
        )

    def test_enqueue_returns_false_when_gateway_unavailable(self) -> None:
        gateway = type("Gateway", (), {"can_enqueue": lambda self: False})()
        producer = SearchReadModelRefreshProducer(refresh_gateway_provider=lambda: gateway)

        self.assertFalse(producer.enqueue(["2026-05"], reason="api_miss"))
        self.assertEqual(producer.enqueue_scope_keys(["2026-05"], reason="api_miss"), [])


class SearchPendingConnection:
    def __init__(
        self,
        *,
        search_rows: list[dict] | None = None,
        pending_rows: list[dict] | None = None,
        workbench_rows: list[dict] | None = None,
        pending_source_counts: dict[str, int] | None = None,
        pending_statistics: dict[str, int] | None = None,
        pending_statistics_scope_rows: list[dict[str, object]] | None = None,
        pending_filter_option_rows: list[dict] | None = None,
        dirty: bool = False,
        pending_scope_exists: bool = True,
        bank_detail_scope_exists: bool = False,
        bank_detail_direction_exists: bool = False,
    ) -> None:
        self.search_rows = list(search_rows or [])
        self.pending_rows = list(pending_rows or [])
        self.workbench_rows = list(workbench_rows or [])
        self.pending_source_counts = dict(pending_source_counts or {"expense": len(self.pending_rows)})
        self.pending_statistics = dict(pending_statistics or {})
        self.pending_statistics_scope_rows = pending_statistics_scope_rows
        self.pending_filter_option_rows = list(pending_filter_option_rows or [])
        self.dirty = dirty
        self.pending_scope_exists = pending_scope_exists
        self.bank_detail_scope_exists = bank_detail_scope_exists
        self.bank_detail_direction_exists = bank_detail_direction_exists
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from ranked_options" in normalized:
            return self.pending_filter_option_rows
        if "from read_model.search_index_rows" in normalized:
            return self.search_rows
        if "from read_model.workbench_rows" in normalized:
            return self.workbench_rows
        if "from read_model.pending_invoice_scopes" in normalized and "filter_group = 'all'" in normalized:
            if not self.pending_scope_exists:
                return []
            if self.pending_statistics_scope_rows is not None:
                return list(self.pending_statistics_scope_rows)
            statistics = self.pending_statistics or {
                "bank_transaction_count": len(self.pending_rows),
                "expense_transaction_count": len(self.pending_rows),
                "income_transaction_count": 0,
                "found_invoice_transaction_count": 0,
                "pending_invoice_transaction_count": 0,
                "no_invoice_required_transaction_count": 0,
                "cash_income_transaction_count": 0,
                "linked_oa_transaction_count": 0,
                "linked_input_invoice_transaction_count": 0,
                "linked_output_invoice_transaction_count": 0,
            }
            expense_count = int(statistics.get("expense_transaction_count") or 0)
            income_count = int(statistics.get("income_transaction_count") or 0)
            expense_statistics = {
                **{key: 0 for key in statistics},
                "bank_transaction_count": expense_count,
                "expense_transaction_count": expense_count,
                "found_invoice_transaction_count": int(statistics.get("linked_input_invoice_transaction_count") or 0),
                "linked_input_invoice_transaction_count": int(
                    statistics.get("linked_input_invoice_transaction_count") or 0
                ),
                "pending_invoice_transaction_count": int(statistics.get("pending_invoice_transaction_count") or 0),
                "no_invoice_required_transaction_count": int(
                    statistics.get("no_invoice_required_transaction_count") or 0
                ),
                "cash_income_transaction_count": int(statistics.get("cash_income_transaction_count") or 0),
                "linked_oa_transaction_count": int(statistics.get("linked_oa_transaction_count") or 0),
            }
            income_statistics = {
                **{key: 0 for key in statistics},
                "bank_transaction_count": income_count,
                "income_transaction_count": income_count,
                "found_invoice_transaction_count": int(statistics.get("linked_output_invoice_transaction_count") or 0),
                "linked_output_invoice_transaction_count": int(
                    statistics.get("linked_output_invoice_transaction_count") or 0
                ),
            }
            return [
                {
                    "scope_key": "expense:all:2026-05",
                    "direction": "expense",
                    "row_count": expense_count,
                    "cache_status": "fresh",
                    "source_versions": _pending_invoice_expected_source_versions(),
                    "raw_payload": {"statistics_metadata": {"statistics": expense_statistics}},
                },
                {
                    "scope_key": "income:all:2026-05",
                    "direction": "income",
                    "row_count": income_count,
                    "cache_status": "fresh",
                    "source_versions": _pending_invoice_expected_source_versions(),
                    "raw_payload": {"statistics_metadata": {"statistics": income_statistics}},
                },
            ]
        if "from read_model.pending_invoice_scopes" in normalized:
            return [
                {
                    "scope_key": params[0],
                    "source_versions": _pending_invoice_expected_source_versions(),
                }
            ] if self.pending_scope_exists else []
        if "/* bank_detail_canonical_source_summaries */" in normalized:
            return [
                {
                    "scope_key": scope_key,
                    "row_count": 0,
                    "context_row_count": 0,
                    "bank_transactions_updated_at": "",
                }
                for scope_key in list(params[0] if params else [])
            ]
        if "from read_model.bank_detail_scopes" in normalized:
            requested_scope = params[1][0] if len(params) > 1 else "2026-05"
            return [
                {
                    "scope_key": requested_scope,
                    "scope_type": "bank_detail",
                    "schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                    "status": "fresh",
                    "row_count": 0,
                    "source_version": 7,
                    "source_versions": {
                        "bank_detail_signature": "empty-v1",
                        "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                        "bank_transactions_context_row_count": 0,
                        "bank_transactions_updated_at": "",
                        "workbench_relation_source_versions": {
                            "source": "workbench_pair_relations",
                            "scope_key": requested_scope,
                            "relation_count": 0,
                            "relation_updated_at": "",
                        },
                    },
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "last_error": None,
                }
            ] if self.bank_detail_scope_exists else []
        if "from read_model.pending_invoice_rows" in normalized and "group by direction" in normalized:
            return [
                {"direction": direction, "count": count}
                for direction, count in sorted(self.pending_source_counts.items())
            ]
        if "from read_model.pending_invoice_rows" in normalized:
            return self.pending_rows
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-21T09:00:00+00:00"} if self.dirty else None
        if "from read_model.bank_detail_rows" in normalized:
            return {"transaction_id": "txn-bank-1"} if self.bank_detail_direction_exists else None
        if "transaction_flags as" in normalized and "from read_model.pending_invoice_rows" in normalized:
            return self.pending_statistics
        if "count(*)" in normalized and "from read_model.search_index_rows" in normalized:
            versions = [
                dict(row.get("source_versions"))
                for row in self.search_rows
                if isinstance(row.get("source_versions"), dict)
            ]
            version_texts = [json.dumps(version, ensure_ascii=False, sort_keys=True) for version in versions]
            return {
                "row_count": len(self.search_rows),
                "min_source_versions": min(version_texts) if version_texts else None,
                "max_source_versions": max(version_texts) if version_texts else None,
                "source_versions": versions[0] if versions else {},
            }
        if "count(*)" in normalized and "from read_model.pending_invoice_rows" in normalized:
            return {"count": len(self.pending_rows)}
        return None


class SearchIndexBulkWriteConnection:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple]] = []
        self.execute_many_values_calls: list[tuple[str, list[tuple]]] = []
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.execute_calls.append((" ".join(sql.lower().split()), params))
        return 1

    def execute_many_values(self, sql: str, params_seq: list[tuple], *, chunk_size: int = 200) -> int:
        self.execute_many_values_calls.append((" ".join(sql.lower().split()), list(params_seq)))
        return len(params_seq)


class PendingProjectionConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "transaction_id": "txn-1",
                    "counterparty_name_raw": "云南供应商",
                    "trade_time": "2026-05-20 10:00:00",
                    "txn_date": "2026-05-20",
                    "amount": "118.00",
                    "balance": "1000.00",
                    "currency": "CNY",
                    "summary": "转账",
                    "remark": "服务费",
                    "bank_serial_no": "SERIAL-1",
                    "account_name": "工商银行",
                    "account_no": "622200001234",
                    "category_payload": {"category_code": "service_fee", "category_label": "服务费"},
                    "invoices": [],
                    "paid_total": "0.00",
                    "oa_applicant": "",
                    "oa_project_name": "",
                    "relation_case_ids": [],
                }
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "requires_invoice": {"tag_codes": ["service_fee"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    }
                }
            }
        return None


class PendingProjectionFacadeConnection(PendingProjectionConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 5,
                        "definitions": [
                            {"code": "service_fee", "label": "服务费", "status": "active"},
                            {
                                "code": "equipment_purchase",
                                "label": "设备采购",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["设备采购"]},
                            },
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "version": 5,
                        "groups": {
                            "requires_invoice": {"tag_codes": ["service_fee"]},
                            "bank_statement_as_invoice": {"tag_codes": ["equipment_purchase"]},
                            "no_invoice_required": {"tag_codes": []},
                        },
                    }
                }
            }
        return None


class CapturePendingInvoiceReadRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []

    def save_pending_invoice_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
        statistics_metadata: dict[str, object] | None = None,
    ) -> None:
        self.saved.append(
            {
                "scope_key": scope_key,
                "rows": list(rows),
                "source_versions": dict(source_versions or {}),
                "statistics_metadata": dict(statistics_metadata or {}),
            }
        )


class FakeBankTransactionTagFacade:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def list_by_month(
        self,
        month: str,
        *,
        direction: str | None = None,
        category_codes: list[str] | None = None,
        require_fresh: bool = True,
        reason: str = "downstream_bank_tag_read",
    ) -> dict[str, object]:
        self.calls.append(
            {
                "month": month,
                "direction": direction,
                "category_codes": list(category_codes or []),
                "require_fresh": require_fresh,
                "reason": reason,
            }
        )
        return self.payload


class FakeWorkbenchRelationReadFacade:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def get_by_row_ids(
        self,
        row_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_read",
        month_hint: str | None = None,
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "row_ids": list(row_ids),
                "require_fresh": require_fresh,
                "reason": reason,
                "month_hint": month_hint,
                "scope_keys_hint": list(scope_keys_hint or []),
            }
        )
        return self.payload


class PendingProjectionOaBankConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "transaction_id": "txn-oa-bank",
                    "counterparty_name_raw": "云南供应商",
                    "trade_time": "2026-05-20 10:00:00",
                    "txn_date": "2026-05-20",
                    "amount": "118.00",
                    "balance": "1000.00",
                    "currency": "CNY",
                    "summary": "转账",
                    "remark": "服务费",
                    "bank_serial_no": "SERIAL-1",
                    "account_name": "云南溯源科技有限公司",
                    "account_no": "622200001234",
                    "bank_name": "招商银行",
                    "bank_short_name": "招行",
                    "counterparty_account_no": "622200009999",
                    "counterparty_bank_name": "招商银行昆明分行",
                    "category_payload": {"category_code": "service_fee", "category_label": "服务费"},
                    "invoices": [],
                    "paid_total": "0.00",
                    "oa_summaries": [
                        {
                            "id": "oa-pay-2048",
                            "applicant": "杨丽萍",
                            "application_type": "支付申请",
                            "project_name": "大理项目",
                            "status": "已完成",
                            "form_no": "2048",
                            "detail_available": True,
                            "relation_case_id": "case-oa-bank",
                        }
                    ],
                    "oa_applicant": "杨丽萍",
                    "oa_project_name": "大理项目",
                    "relation_case_ids": ["case-oa-bank"],
                }
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "requires_invoice": {"tag_codes": ["service_fee"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    }
                }
            }
        return None


class PendingProjectionCandidateOaConnection(PendingProjectionOaBankConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "transaction_id": "txn-oa-bank",
                    "counterparty_name_raw": "云南供应商",
                    "trade_time": "2026-05-20 10:00:00",
                    "txn_date": "2026-05-20",
                    "amount": "118.00",
                    "balance": "1000.00",
                    "currency": "CNY",
                    "summary": "转账",
                    "remark": "服务费",
                    "bank_serial_no": "SERIAL-1",
                    "account_name": "云南溯源科技有限公司",
                    "account_no": "622200001234",
                    "bank_name": "招商银行",
                    "bank_short_name": "招行",
                    "counterparty_account_no": "622200009999",
                    "counterparty_bank_name": "招商银行昆明分行",
                    "category_payload": {"category_code": "service_fee", "category_label": "服务费"},
                    "invoices": [],
                    "paid_total": "0.00",
                    "oa_summaries": [
                        {
                            "id": "candidate:wrong-oa-id",
                            "applicant": "杨丽萍",
                            "application_type": "支付申请",
                            "project_name": "大理项目",
                            "status": "已完成",
                            "form_no": "2048",
                            "detail_available": False,
                            "relation_case_id": "candidate:oa-bank",
                        }
                    ],
                    "oa_applicant": "杨丽萍",
                    "oa_project_name": "大理项目",
                    "relation_case_ids": ["candidate:oa-bank"],
                }
            ]
        return []


class PendingComplementProjectionConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                self._row("txn-fee", "fee", "手续费"),
                self._row("txn-salary", "salary", "工资"),
                self._row("txn-custom-meal", "custom_meal", "餐饮"),
                self._row("txn-no-category", "", ""),
                self._row("txn-archived", "custom_archived", "归档"),
                self._row("txn-unknown", "unknown_external_code", "未知"),
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 7,
                        "definitions": [
                            {"code": "fee", "label": "手续费", "status": "active"},
                            {"code": "salary", "label": "工资", "status": "active"},
                            {
                                "code": "custom_meal",
                                "label": "餐饮",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["餐饮"]},
                            },
                            {"code": "custom_archived", "label": "归档", "status": "archived"},
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "requires_invoice": {"tag_codes": ["legacy_requires_should_be_ignored"]},
                            "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                            "no_invoice_required": {"tag_codes": ["salary"]},
                        }
                    },
                }
            }
        return None

    @staticmethod
    def _row(transaction_id: str, category_code: str, category_label: str) -> dict:
        return {
            "transaction_id": transaction_id,
            "counterparty_name_raw": transaction_id,
            "trade_time": "2026-05-20 10:00:00",
            "txn_date": "2026-05-20",
            "amount": "118.00",
            "balance": "1000.00",
            "currency": "CNY",
            "summary": "转账",
            "remark": "",
            "bank_serial_no": transaction_id,
            "account_name": "工商银行",
            "account_no": "622200001234",
            "category_payload": (
                {"category_code": category_code, "category_label": category_label}
                if category_code
                else {}
            ),
            "invoices": [],
            "paid_total": "0.00",
            "oa_applicant": "",
            "oa_project_name": "",
            "relation_case_ids": [],
        }


class PendingRuleClosureProjectionConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                self._row("txn-fee", "fee", "手续费"),
                self._row("txn-internal-transfer", "internal_transfer", "内部转账"),
                self._row("txn-salary", "salary", "工资"),
                self._row("txn-no-category", "", ""),
                self._row("txn-unknown", "unknown_external_code", "未知"),
                self._row("txn-archived", "archived_training", "历史培训"),
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 11,
                        "definitions": [
                            {
                                "code": "fee",
                                "label": "手续费",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["手续费"]},
                            },
                            {
                                "code": "internal_transfer",
                                "label": "内部转账",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["内部转账"]},
                            },
                            {
                                "code": "salary",
                                "label": "工资",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["工资"]},
                            },
                            {
                                "code": "archived_training",
                                "label": "历史培训",
                                "status": "archived",
                                "rules": {"match_fields": ["all_text"], "contains": ["培训"]},
                            },
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "requires_invoice": {"tag_codes": ["legacy_requires_should_be_ignored"]},
                            "bank_statement_as_invoice": {"tag_codes": ["internal_transfer"]},
                            "no_invoice_required": {"tag_codes": ["salary"]},
                        }
                    },
                }
            }
        return None

    @staticmethod
    def _row(transaction_id: str, category_code: str, category_label: str) -> dict:
        return {
            "transaction_id": transaction_id,
            "counterparty_name_raw": transaction_id,
            "trade_time": "2026-05-20 10:00:00",
            "txn_date": "2026-05-20",
            "amount": "118.00",
            "balance": "1000.00",
            "currency": "CNY",
            "summary": "转账",
            "remark": "",
            "bank_serial_no": transaction_id,
            "account_name": "工商银行",
            "account_no": "622200001234",
            "category_payload": (
                {"category_code": category_code, "category_label": category_label}
                if category_code
                else {}
            ),
            "invoices": [],
            "paid_total": "0.00",
            "oa_applicant": "",
            "oa_project_name": "",
            "relation_case_ids": [],
        }


class PendingEffectiveCategoryProjectionConnection:
    def __init__(self, *, direction: str = "expense") -> None:
        self.direction = direction

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            if self.direction == "income":
                return [
                    self._row("txn-income-service", "service_income", "服务收入", ["收入", "服务收入"]),
                    self._row("txn-income-cash", "cash_sale", "现金销售", ["收入", "现金销售"]),
                    self._row("txn-income-unknown", "unknown_income", "未知收入", ["收入", "未知收入"]),
                ]
            return [
                self._row("txn-equipment", "equipment_purchase", "设备采购", ["货款", "设备采购"]),
                self._row("txn-expense-unknown", "unknown_expense", "未知支出", ["货款", "未知支出"]),
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 12,
                        "definitions": [
                            {"code": "equipment_purchase", "label": "设备采购", "status": "active", "direction": "expense", "rules": {"match_fields": ["all_text"], "contains": ["设备采购"]}},
                            {"code": "service_income", "label": "服务收入", "status": "active", "direction": "income", "rules": {"match_fields": ["all_text"], "contains": ["服务收入"]}},
                            {"code": "cash_sale", "label": "现金销售", "status": "active", "direction": "income", "rules": {"match_fields": ["all_text"], "contains": ["现金销售"]}},
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "bank_statement_as_invoice": {"tag_codes": ["equipment_purchase"]},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    },
                    "pending_output_invoice_tag_groups": {
                        "groups": {
                            "no_invoice_required": {"tag_codes": []},
                            "cash_income": {"tag_codes": ["cash_sale"]},
                        }
                    },
                }
            }
        return None

    @staticmethod
    def _row(transaction_id: str, category_code: str, category_label: str, label_path: list[str]) -> dict:
        return {
            "transaction_id": transaction_id,
            "counterparty_name_raw": transaction_id,
            "trade_time": "2026-05-20 10:00:00",
            "txn_date": "2026-05-20",
            "amount": "118.00",
            "balance": "1000.00",
            "currency": "CNY",
            "summary": "转账",
            "remark": "",
            "bank_serial_no": transaction_id,
            "account_name": "工商银行",
            "account_no": "622200001234",
            "category_payload": {
                "effective_category_code": category_code,
                "effective_category_label": category_label,
                "effective_category_primary_label": label_path[0] if label_path else "",
                "effective_category_sub_label": label_path[1] if len(label_path) > 1 else category_label,
                "effective_category_label_path": label_path,
            },
            "invoices": [],
            "paid_total": "0.00",
            "oa_applicant": "",
            "oa_project_name": "",
            "income_status_override": None,
            "relation_case_ids": [],
        }


class PendingIncomeProjectionConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                self._row("txn-output", "service_income", "服务收入", invoices=[{"id": "out-1", "total_with_tax": "118.00"}]),
                self._row("txn-no-invoice", "internal_transfer", "内部转账"),
                self._row("txn-cash", "cash_sale", "现金销售"),
                self._row("txn-manual", "other_income", "其他收入", status_override={"status_code": "cash_income"}),
                self._row("txn-pending", "other_income", "其他收入"),
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 9,
                        "definitions": [
                            {
                                "code": "service_income",
                                "label": "服务收入",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["服务"]},
                            },
                            {
                                "code": "internal_transfer",
                                "label": "内部转账",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["内部"]},
                            },
                            {
                                "code": "cash_sale",
                                "label": "现金销售",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["现金"]},
                            },
                            {
                                "code": "other_income",
                                "label": "其他收入",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["其他"]},
                            },
                        ],
                    },
                    "pending_output_invoice_tag_groups": {
                        "version": 3,
                        "groups": {
                            "no_invoice_required": {"tag_codes": ["internal_transfer"]},
                            "cash_income": {"tag_codes": ["cash_sale"]},
                        },
                    },
                }
            }
        return None

    @staticmethod
    def _row(
        transaction_id: str,
        category_code: str,
        category_label: str,
        *,
        invoices: list[dict] | None = None,
        status_override: dict | None = None,
    ) -> dict:
        return {
            "transaction_id": transaction_id,
            "counterparty_name_raw": transaction_id,
            "trade_time": "2026-05-20 10:00:00",
            "txn_date": "2026-05-20",
            "amount": "118.00",
            "balance": "1000.00",
            "currency": "CNY",
            "summary": "收款",
            "remark": "",
            "bank_serial_no": transaction_id,
            "account_name": "工商银行",
            "account_no": "622200001234",
            "category_payload": {
                "category_code": category_code,
                "category_label": category_label,
                "category_primary_label": "收入",
                "category_sub_label": category_label,
                "category_label_path": ["收入", category_label],
            },
            "invoices": list(invoices or []),
            "paid_total": "0.00",
            "oa_applicant": "",
            "oa_project_name": "",
            "income_status_override": dict(status_override) if status_override else None,
            "relation_case_ids": [],
        }


class SearchPendingSqlRuntimeTests(unittest.TestCase):
    def test_pending_invoice_all_direction_merges_expense_and_income_source_versions(self) -> None:
        merged = read_models_module._merge_pending_invoice_direction_scope_rows(
            "all:all",
            [
                {
                    "scope_key": "expense:all",
                    "row_count": 2,
                    "source_versions": {
                        "pending_invoice_read_model_schema_version": "schema-v1",
                        "workbench_relation_source_versions": {
                            "2026-01": {"source_version": "expense-jan"},
                        },
                    },
                },
                {
                    "scope_key": "income:all",
                    "row_count": 1,
                    "source_versions": {
                        "pending_invoice_read_model_schema_version": "schema-v1",
                        "workbench_relation_source_versions": {
                            "2026-01": {"source_version": "income-jan"},
                        },
                    },
                },
            ],
        )

        self.assertEqual(merged["scope_key"], "all:all")
        self.assertEqual(
            merged["source_versions"]["workbench_relation_source_versions"],
            {
                "expense": {"2026-01": {"source_version": "expense-jan"}},
                "income": {"2026-01": {"source_version": "income-jan"}},
            },
        )

    def test_pending_invoice_all_direction_source_provider_uses_child_scopes(self) -> None:
        class PendingSourceVersionRepository:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, object]]] = []

            def pending_invoice_bank_detail_source_versions(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("bank", dict(kwargs)))
                return {"2026-01": {"source": f"bank-{kwargs['direction']}"}}

            def pending_invoice_workbench_relation_source_versions(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("relation", dict(kwargs)))
                return {"2026-01": {"source": f"relation-{kwargs['direction']}"}}

        repository = PendingSourceVersionRepository()
        provider = PendingInvoiceSourceVersionsProvider(
            settings_provider=lambda: {},
            attachment_invoice_parser_version_provider=lambda: "parser-v1",
            oa_projection_sync_version_provider=lambda: "oa-sync-v1",
            repository=repository,
        )

        source_versions = provider(
            query={
                "direction": ["all"],
                "filter": ["all"],
                "date_from": ["2026-01-01"],
                "keyword": ["ignored-view-filter"],
                "filters": ["[]"],
            },
            payload={},
        )

        self.assertEqual(
            source_versions["bank_detail_source_versions"],
            {
                "expense": {"2026-01": {"source": "bank-expense"}},
                "income": {"2026-01": {"source": "bank-income"}},
            },
        )
        self.assertEqual(
            source_versions["workbench_relation_source_versions"],
            {
                "expense": {"2026-01": {"source": "relation-expense"}},
                "income": {"2026-01": {"source": "relation-income"}},
            },
        )
        self.assertEqual(
            repository.calls,
            [
                ("bank", {"direction": "expense", "filter": "all"}),
                ("bank", {"direction": "income", "filter": "all"}),
                ("relation", {"direction": "expense", "filter": "all"}),
                ("relation", {"direction": "income", "filter": "all"}),
            ],
        )

    def test_pending_invoice_source_provider_reuses_request_settings_payload(self) -> None:
        provider = PendingInvoiceSourceVersionsProvider(
            settings_provider=lambda: (_ for _ in ()).throw(
                AssertionError("request-scoped settings must prevent a second settings load")
            ),
            attachment_invoice_parser_version_provider=lambda: "parser-v1",
            oa_projection_sync_version_provider=lambda: "oa-sync-v1",
            repository=None,
        )
        settings_payload = {
            "bank_transaction_tags": {"version": 7},
            "pending_invoice_tag_groups": {"version": 8},
        }

        source_versions = provider(
            query={"direction": ["expense"]},
            settings_payload=settings_payload,
        )

        self.assertEqual(source_versions["bank_auto_tag_rules_version"], 7)
        self.assertEqual(source_versions["pending_invoice_tag_groups_version"], 8)

    def test_pending_invoice_filtered_source_provider_uses_direction_wide_dependencies(self) -> None:
        class PendingSourceVersionRepository:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, object]]] = []

            def pending_invoice_bank_detail_source_versions(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("bank", dict(kwargs)))
                return {"2026-01": {"source": "bank"}}

            def pending_invoice_workbench_relation_source_versions(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("relation", dict(kwargs)))
                return {"2026-01": {"source": "relation"}}

        repository = PendingSourceVersionRepository()
        provider = PendingInvoiceSourceVersionsProvider(
            settings_provider=lambda: {},
            attachment_invoice_parser_version_provider=lambda: "parser-v1",
            oa_projection_sync_version_provider=lambda: "oa-sync-v1",
            repository=repository,
        )

        provider(
            query={"direction": ["income"], "filter": ["cash_income"]},
            payload={},
        )

        self.assertEqual(
            repository.calls,
            [
                ("bank", {"direction": "income", "filter": "all"}),
                ("relation", {"direction": "income", "filter": "all"}),
            ],
        )

    def test_pending_invoice_writer_and_api_source_version_contracts_match(self) -> None:
        connection = SearchPendingConnection()
        builder = SearchPendingSqlProjectionBuilder(connection=connection)

        writer_versions = builder._pending_invoice_source_versions()
        api_versions = pending_invoice_source_versions(
            {
                "pending_invoice_tag_groups": {"version": 1},
                "pending_output_invoice_tag_groups": {"version": 1},
                "bank_transaction_tags": {"version": 1},
            },
            attachment_invoice_parser_version=str(writer_versions["oa_attachment_invoice_parser_version"]),
            oa_projection_sync_version=str(writer_versions["oa_projection_sync_version"]),
            bank_detail_source_versions={},
            workbench_relation_source_versions={},
        )

        self.assertEqual(writer_versions, api_versions)

    def test_pending_invoice_writer_and_api_versions_are_direction_exact(self) -> None:
        connection = SearchPendingConnection()
        builder = SearchPendingSqlProjectionBuilder(connection=connection)
        settings = {
            "pending_invoice_tag_groups": {"version": 1},
            "pending_output_invoice_tag_groups": {"version": 1},
            "bank_transaction_tags": {"version": 1},
        }

        for direction, included_key, excluded_key in (
            ("expense", "pending_invoice_tag_groups_version", "pending_output_invoice_tag_groups_version"),
            ("income", "pending_output_invoice_tag_groups_version", "pending_invoice_tag_groups_version"),
        ):
            writer_versions = builder._pending_invoice_source_versions(direction)
            api_versions = pending_invoice_source_versions(
                settings,
                direction=direction,
                attachment_invoice_parser_version=str(writer_versions["oa_attachment_invoice_parser_version"]),
                oa_projection_sync_version=str(writer_versions["oa_projection_sync_version"]),
                bank_detail_source_versions={},
                workbench_relation_source_versions={},
            )
            self.assertEqual(writer_versions, api_versions)
            self.assertIn(included_key, writer_versions)
            self.assertNotIn(excluded_key, writer_versions)

    def test_search_projection_reads_unique_workbench_rows_before_python_build(self) -> None:
        connection = SearchPendingConnection(
            workbench_rows=[
                {
                    "row_id": "txn-1",
                    "source_kind": "bank",
                    "status": "paired",
                    "scope_month": "2026-05-01",
                    "project_name": "项目A",
                    "counterparty_name": "昆明供应商",
                    "amount": "10.00",
                    "generated_at": "2026-05-21T10:00:00+00:00",
                    "group_zone": "paired",
                    "group_id": "case:SEARCH-REL-001",
                    "payload": {"id": "txn-1", "counterparty_name": "昆明供应商"},
                }
            ]
        )
        builder = SearchPendingSqlProjectionBuilder(connection=connection)

        rows = builder._search_rows_for_month("2026-05")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["row_id"], "txn-1")
        self.assertEqual(rows[0]["payload"]["zone_hint"], "paired")
        self.assertEqual(rows[0]["payload"]["group_id"], "case:SEARCH-REL-001")
        self.assertEqual(rows[0]["payload"]["jump_target"]["group_id"], "case:SEARCH-REL-001")
        sql, params = connection.fetch_all_calls[0]
        self.assertIn("row_number() over", sql)
        self.assertIn("partition by row_id", sql)
        self.assertIn("read_model.workbench_group_rows", sql)
        self.assertIn("where row_rank = 1", sql)
        self.assertEqual(params, ("2026-05-01", "2026-05"))

    def test_search_index_scope_summary_reads_versions_without_loading_rows(self) -> None:
        connection = SearchPendingConnection(
            search_rows=[
                {
                    "row_id": "txn-1",
                    "source_versions": {"search_index_schema_version": "v1"},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        summary = repository.search_index_scope_summary(month="2026-05")

        self.assertEqual(summary["read_model_status"], "fresh")
        self.assertEqual(summary["row_count"], 1)
        self.assertEqual(summary["source_versions"], {"search_index_schema_version": "v1"})
        self.assertTrue(any("from read_model.search_index_rows" in sql for sql, _params in connection.fetch_one_calls))
        self.assertFalse(any("from read_model.search_index_rows" in sql for sql, _params in connection.fetch_all_calls))

    def test_search_projection_skips_unchanged_scope_without_workbench_scan(self) -> None:
        class SummaryRepository:
            def __init__(self) -> None:
                self.source_versions: dict[str, object] = {}
                self.summary_months: list[str] = []

            def search_index_scope_summary(self, *, month: str) -> dict[str, object]:
                self.summary_months.append(month)
                return {
                    "read_model_status": "fresh",
                    "row_count": 210,
                    "source_versions": dict(self.source_versions),
                }

            def save_search_index_rows(self, **_kwargs: object) -> None:
                raise AssertionError("unchanged search scope must not save rows")

        class NoWorkbenchScanConnection(SearchPendingConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.workbench_rows" in normalized:
                    raise AssertionError("unchanged search scope must not scan workbench rows")
                return super().fetch_all(sql, params)

        connection = NoWorkbenchScanConnection()
        repository = SummaryRepository()
        builder = SearchPendingSqlProjectionBuilder(connection=connection, read_model_repository=repository)
        repository.source_versions = builder._search_source_versions()

        result = builder.rebuild_search_index_scope("2026-05")

        self.assertEqual(result["scope_key"], "2026-05")
        self.assertEqual(result["row_count"], 210)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["skip_reason"], "source_versions_unchanged")
        self.assertEqual(repository.summary_months, ["2026-05"])
        self.assertFalse(any("from read_model.workbench_rows" in sql for sql, _params in connection.fetch_all_calls))

    def test_search_index_rows_are_saved_with_bulk_values(self) -> None:
        connection = SearchIndexBulkWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_search_index_rows(
            scope_key="2026-05",
            source_versions={"search": "v1"},
            rows=[
                {
                    "row_id": "txn-1",
                    "source_kind": "bank",
                    "status": "unpaired",
                    "title": "昆明供应商",
                    "subtitle": "工行",
                    "searchable_text": "昆明 10.00",
                    "project_name": "项目A",
                    "counterparty_name": "昆明供应商",
                    "amount": "10.00",
                    "payload": {"row_id": "txn-1", "record_type": "bank", "month": "2026-05"},
                },
                {
                    "row_id": "inv-1",
                    "source_kind": "invoice",
                    "status": "unpaired",
                    "title": "发票",
                    "searchable_text": "发票 10.00",
                    "payload": {"row_id": "inv-1", "record_type": "invoice", "month": "2026-05"},
                },
            ],
        )

        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(len(connection.execute_calls), 1)
        delete_sql, delete_params = connection.execute_calls[0]
        self.assertIn("delete from read_model.search_index_rows", delete_sql)
        self.assertIn("not (row_id = any", delete_sql)
        self.assertEqual(delete_params[1], ["txn-1", "inv-1"])
        self.assertEqual(len(connection.execute_many_values_calls), 1)
        sql, params_seq = connection.execute_many_values_calls[0]
        self.assertIn("insert into read_model.search_index_rows", sql)
        self.assertIn("is distinct from", sql)
        self.assertEqual(len(params_seq), 2)
        self.assertEqual(params_seq[0][0], "txn-1")
        self.assertEqual(params_seq[1][0], "inv-1")

    def test_search_index_bulk_save_dedupes_duplicate_row_ids(self) -> None:
        connection = SearchIndexBulkWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_search_index_rows(
            scope_key="2026-05",
            rows=[
                {
                    "row_id": "txn-1",
                    "source_kind": "bank",
                    "title": "旧标题",
                    "searchable_text": "旧",
                    "payload": {"row_id": "txn-1", "record_type": "bank", "month": "2026-05", "title": "旧标题"},
                },
                {
                    "row_id": "txn-1",
                    "source_kind": "bank",
                    "title": "新标题",
                    "searchable_text": "新",
                    "payload": {"row_id": "txn-1", "record_type": "bank", "month": "2026-05", "title": "新标题"},
                },
            ],
        )

        _sql, params_seq = connection.execute_many_values_calls[0]
        self.assertEqual(len(params_seq), 1)
        self.assertEqual(params_seq[0][0], "txn-1")
        self.assertEqual(params_seq[0][4], "新标题")

    def test_search_index_bulk_save_deletes_scope_when_result_is_empty(self) -> None:
        connection = SearchIndexBulkWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_search_index_rows(scope_key="2026-05", rows=[])

        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(connection.execute_many_values_calls, [])
        self.assertEqual(len(connection.execute_calls), 1)
        self.assertIn("delete from read_model.search_index_rows", connection.execute_calls[0][0])
        self.assertNotIn("row_id = any", connection.execute_calls[0][0])

    def test_search_repository_reads_index_rows_without_state_fallback(self) -> None:
        connection = SearchPendingConnection(
            search_rows=[
                {
                    "source_kind": "bank",
                    "payload": {
                        "row_id": "txn-1",
                        "record_type": "bank",
                        "month": "2026-05",
                        "zone_hint": "unpaired",
                        "matched_field": "对方户名",
                        "title": "昆明供应商",
                        "primary_meta": "2026-05-02 / 10.00 / 支出",
                        "secondary_meta": "工行 / 项目A",
                        "status_label": "未配对",
                        "jump_target": {"month": "2026-05", "row_id": "txn-1", "record_type": "bank", "zone_hint": "unpaired"},
                    },
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.search_index(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit=20)

        self.assertEqual(payload["summary"], {"total": 1, "oa": 0, "bank": 1, "invoice": 0})
        self.assertEqual(payload["bank_results"][0]["row_id"], "txn-1")
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_all_calls))

    def test_search_api_miss_enqueues_refresh_without_sync_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._search_sql_read_repository = type("SearchRepo", (), {"search_index": lambda *_args, **_kwargs: None})()
        app._search_service = type(
            "SearchService",
            (),
            {"search": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search API miss must not scan in-memory state"))},
        )()

        response = app._handle_api_search(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit="20")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("search", "2026-05", "api_miss")])

    def test_search_api_requires_sql_repository_in_production_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._search_sql_read_repository = None
        app._search_service = type(
            "SearchService",
            (),
            {
                "search": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("production search API must not scan in-memory state without SQL repository")
                )
            },
        )()

        response = app._handle_api_search(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit="20")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.SERVICE_UNAVAILABLE))
        self.assertEqual(payload["error"], "read_model_unavailable")
        self.assertEqual(payload["read_model_status"], "unavailable")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(queue.refreshes, [("search", "2026-05", "api_sql_repository_unavailable")])

    def test_search_api_reads_sql_index(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._search_sql_read_repository = type(
            "SearchRepo",
            (),
            {
                "search_index": lambda *_args, **_kwargs: {
                    "query": "昆明",
                    "filters": {"scope": "all", "month": "2026-05", "project_name": None, "status": None, "limit": 20},
                    "summary": {"total": 1, "oa": 0, "bank": 1, "invoice": 0},
                    "oa_results": [],
                    "bank_results": [
                        {
                            "row_id": "txn-1",
                            "group_id": "case:SEARCH-REL-001",
                            "jump_target": {
                                "month": "2026-05",
                                "row_id": "txn-1",
                                "record_type": "bank",
                                "zone_hint": "paired",
                                "group_id": "case:SEARCH-REL-001",
                            },
                        }
                    ],
                    "invoice_results": [],
                    "refresh_status": "fresh",
                    "source_versions": app._search_query_freshness_service().expected_source_versions(),
                }
            },
        )()
        app._search_service = type(
            "SearchService",
            (),
            {"search": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search SQL hit must not scan in-memory state"))},
        )()

        response = app._handle_api_search(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit="20")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["bank_results"][0]["row_id"], "txn-1")
        self.assertEqual(payload["bank_results"][0]["group_id"], "case:SEARCH-REL-001")
        self.assertEqual(payload["bank_results"][0]["jump_target"]["group_id"], "case:SEARCH-REL-001")
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_pending_invoice_repository_reads_rows_page_and_summary(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-1",
                        "bank_transaction": {"id": "txn-1", "counterparty_name": "昆明供应商"},
                        "invoices": [],
                        "can_create_invoice": True,
                    },
                    "missing_invoice": True,
                    "can_create_invoice": True,
                }
            ],
            pending_source_counts={"expense": 356, "income": 75},
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(direction="expense", filter="all", date_from=None, date_to=None, keyword=None, page=1, page_size=50)

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["summary"]["missing_invoice_rows"], 1)
        self.assertEqual(payload["rows"][0]["id"], "txn-1")
        self.assertEqual(connection.transaction_count, 1)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("case when payload = '{}'::jsonb then raw_payload else null::jsonb end as raw_payload", executed_sql)
        self.assertNotIn("select payload, raw_payload", executed_sql)
        self.assertEqual(
            payload["summary"]["source_summary"],
            {
                "bank_transaction_rows": 431,
                "expense_rows": 356,
                "income_rows": 75,
                "current_direction_rows": 356,
                "excluded_direction_rows": 75,
            },
        )

    def test_pending_invoice_repository_returns_unfiltered_projection_statistics(self) -> None:
        statistics = {
            "bank_transaction_count": 900,
            "expense_transaction_count": 500,
            "income_transaction_count": 400,
            "found_invoice_transaction_count": 620,
            "pending_invoice_transaction_count": 210,
            "no_invoice_required_transaction_count": 55,
            "cash_income_transaction_count": 15,
            "linked_oa_transaction_count": 580,
            "linked_input_invoice_transaction_count": 360,
            "linked_output_invoice_transaction_count": 260,
        }
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-visible",
                        "bank_transaction": {"id": "txn-visible"},
                        "invoice_acquisition_status": {"code": "paid_invoiced"},
                    },
                    "missing_invoice": False,
                    "can_create_invoice": False,
                }
            ],
            pending_statistics=statistics,
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="requires_invoice",
            date_from="2026-05-01",
            date_to="2026-05-31",
            keyword="visible",
            page=1,
            page_size=1,
        )

        self.assertEqual(payload["statistics"], statistics)
        self.assertEqual(payload["statistics_status"], "fresh")
        self.assertFalse(any("transaction_flags as" in sql for sql, _params in connection.fetch_one_calls))
        statistics_sql = next(
            sql
            for sql, _params in connection.fetch_all_calls
            if "from read_model.pending_invoice_scopes" in sql and "filter_group = 'all'" in sql
        )
        self.assertNotIn("from read_model.pending_invoice_rows", statistics_sql)
        self.assertNotIn("trade_date >=", statistics_sql)
        self.assertNotIn("searchable_text ilike", statistics_sql)
        statistics_gate_sql = " ".join(sql for sql, _params in connection.fetch_one_calls)
        self.assertEqual(
            statistics_gate_sql.count("'^(expense|income):all(?::[0-9]{4}-[0-9]{2})?$'"),
            2,
        )
        self.assertIn("coalesce(scope_key, payload->>'scope_key', '')", statistics_gate_sql)

    def test_pending_invoice_statistics_ignore_historical_zero_row_scope_metadata(self) -> None:
        keys = tuple(_pending_invoice_statistics_contract()["statistics"])
        expense_statistics = {
            **{key: 0 for key in keys},
            "bank_transaction_count": 2,
            "expense_transaction_count": 2,
            "found_invoice_transaction_count": 1,
            "pending_invoice_transaction_count": 1,
            "linked_input_invoice_transaction_count": 1,
        }
        income_statistics = {
            **{key: 0 for key in keys},
            "bank_transaction_count": 1,
            "income_transaction_count": 1,
            "found_invoice_transaction_count": 1,
            "linked_output_invoice_transaction_count": 1,
        }
        connection = SearchPendingConnection(
            pending_statistics_scope_rows=[
                {
                    "scope_key": "expense:all:2023-05",
                    "direction": "expense",
                    "row_count": 0,
                    "cache_status": "fresh",
                    "source_versions": {
                        **_pending_invoice_expected_source_versions(),
                        "bank_detail_source_versions": {"source_version": 1},
                    },
                    "raw_payload": {},
                },
                {
                    "scope_key": "expense:all:2026-05",
                    "direction": "expense",
                    "row_count": 2,
                    "cache_status": "fresh",
                    "source_versions": {
                        **_pending_invoice_expected_source_versions(),
                        "bank_detail_source_versions": {"source_version": 7},
                    },
                    "raw_payload": {"statistics_metadata": {"statistics": expense_statistics}},
                },
                {
                    "scope_key": "income:all:2026-05",
                    "direction": "income",
                    "row_count": 1,
                    "cache_status": "fresh",
                    "source_versions": {
                        **_pending_invoice_expected_source_versions(),
                        "bank_detail_source_versions": {"source_version": 8},
                    },
                    "raw_payload": {"statistics_metadata": {"statistics": income_statistics}},
                },
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["statistics_status"], "fresh")
        self.assertEqual(payload["statistics"]["bank_transaction_count"], 3)
        self.assertEqual(payload["statistics"]["expense_transaction_count"], 2)
        self.assertEqual(payload["statistics"]["income_transaction_count"], 1)
        self.assertEqual(payload["statistics"]["found_invoice_transaction_count"], 2)
        self.assertEqual(
            payload["statistics_source_versions_by_scope"]["expense:all"]["bank_detail_source_versions"],
            {"source_version": 7},
        )

    def test_pending_invoice_statistics_keep_source_proof_while_refresh_is_in_flight(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-1",
                        "bank_transaction": {"id": "txn-1"},
                    },
                    "missing_invoice": True,
                    "can_create_invoice": True,
                }
            ],
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        state = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        self.assertEqual(state["statistics_status"], "refreshing")
        self.assertIsNone(state["statistics"])
        self.assertEqual(
            state["statistics_source_versions_by_scope"],
            {
                "expense:all": _pending_invoice_expected_source_versions(),
                "income:all": _pending_invoice_expected_source_versions(),
            },
        )

    def test_invoice_lifecycle_reads_exact_pending_invoice_month_shard(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-1",
                        "bank_transaction": {"id": "txn-1", "trade_time": "2026-05-20"},
                        "invoice_acquisition_status": {"code": "missing_invoice"},
                    },
                    "raw_payload": None,
                }
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_lifecycle_source_rows(
            month="2026-05",
            direction="expense",
        )

        self.assertEqual(payload["scope_key"], "expense:all:2026-05")
        self.assertEqual(payload["refresh_status"], "fresh")
        self.assertEqual([row["id"] for row in payload["rows"]], ["txn-1"])
        self.assertEqual(connection.transaction_count, 1)
        rows_query = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "from read_model.pending_invoice_rows" in sql
        )
        self.assertIn("scope_month = %s::date", rows_query[0])
        self.assertEqual(rows_query[1], ("expense", "2026-05-01"))
        dirty_query = next(
            (sql, params)
            for sql, params in connection.fetch_one_calls
            if "from job.read_model_dirty_scopes" in sql
        )
        self.assertEqual(dirty_query[1], ("pending_invoice", "expense:all:2026-05"))

    def test_invoice_lifecycle_does_not_read_stale_pending_invoice_rows(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[{"payload": {"id": "stale-txn"}}],
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_lifecycle_source_rows(
            month="2026-05",
            direction="expense",
        )

        self.assertEqual(payload["refresh_status"], "refreshing")
        self.assertEqual(payload["rows"], [])
        self.assertFalse(
            any("from read_model.pending_invoice_rows" in sql for sql, _params in connection.fetch_all_calls)
        )

    def test_invoice_lifecycle_accepts_missing_pending_scope_only_for_proven_empty_bank_direction(self) -> None:
        connection = SearchPendingConnection(
            pending_scope_exists=False,
            bank_detail_scope_exists=True,
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_lifecycle_source_rows(
            month="2026-05",
            direction="income",
        )

        self.assertEqual(payload["scope_key"], "income:all:2026-05")
        self.assertEqual(payload["refresh_status"], "fresh")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(
            payload["source_versions"]["pending_invoice_empty_month_direction"]["bank_detail_source_versions"],
            {
                "bank_detail_signature": "empty-v1",
                "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                "bank_transactions_context_row_count": 0,
                "bank_transactions_updated_at": "",
                "workbench_relation_source_versions": {
                    "source": "workbench_pair_relations",
                    "scope_key": "2026-05",
                    "relation_count": 0,
                    "relation_updated_at": "",
                },
            },
        )

    def test_invoice_lifecycle_rejects_missing_pending_scope_when_bank_direction_has_rows(self) -> None:
        connection = SearchPendingConnection(
            pending_scope_exists=False,
            bank_detail_scope_exists=True,
            bank_detail_direction_exists=True,
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_lifecycle_source_rows(
            month="2026-05",
            direction="income",
        )

        self.assertIsNone(payload)

    def test_pending_invoice_repository_writes_canonical_payload_without_raw_payload_duplication(self) -> None:
        connection = SearchIndexBulkWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_pending_invoice_rows(
            scope_key="expense:all:2026-05",
            rows=[
                {
                    "payload": {
                        "id": "txn-raw-1",
                        "bank_transaction": {
                            "id": "txn-raw-1",
                            "trade_time": "2026-05-20",
                            "amount": "128.00",
                        },
                        "filter_group": "all",
                        "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                        "input_invoices": {"primary": None, "payment_summary": {}},
                        "oa": {"primary": None},
                        "invoices": [],
                        "can_create_invoice": True,
                    }
                }
            ],
            source_versions={"schema": "v1"},
        )

        insert_calls = [
            (sql, params)
            for sql, params in connection.execute_calls
            if "insert into read_model.pending_invoice_rows" in sql
        ]
        self.assertEqual(len(insert_calls), 1)
        _sql, params = insert_calls[0]
        payload_param = params[-2]
        raw_payload_param = params[-1]
        self.assertEqual(payload_param.obj["id"], "txn-raw-1")
        self.assertEqual(raw_payload_param.obj, {})

    def test_pending_invoice_repository_all_scope_marks_filter_scopes_from_same_write(self) -> None:
        connection = SearchIndexBulkWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_pending_invoice_rows(
            scope_key="expense:all:2026-05",
            rows=[
                {
                    "payload": {
                        "id": "txn-requires",
                        "bank_transaction": {
                            "id": "txn-requires",
                            "trade_time": "2026-05-20",
                            "amount": "128.00",
                        },
                        "filter_group": "requires_invoice",
                        "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                        "input_invoices": {"primary": None, "payment_summary": {}},
                        "oa": {"primary": None},
                        "invoices": [],
                        "can_create_invoice": True,
                    }
                },
                {
                    "payload": {
                        "id": "txn-bank-statement",
                        "bank_transaction": {
                            "id": "txn-bank-statement",
                            "trade_time": "2026-05-21",
                            "amount": "88.00",
                        },
                        "filter_group": "bank_statement_as_invoice",
                        "invoice_acquisition_status": {"code": "bank_statement_as_invoice"},
                        "input_invoices": {"primary": None, "payment_summary": {}},
                        "oa": {"primary": None},
                        "invoices": [],
                        "can_create_invoice": False,
                    }
                },
                {
                    "payload": {
                        "id": "txn-requires-from-status",
                        "bank_transaction": {
                            "id": "txn-requires-from-status",
                            "trade_time": "2026-05-22",
                            "amount": "188.00",
                        },
                        "filter_group": "all",
                        "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                        "input_invoices": {"primary": None, "payment_summary": {}},
                        "oa": {"primary": None},
                        "invoices": [],
                        "can_create_invoice": True,
                    }
                },
            ],
            source_versions={"schema": "v1"},
        )

        scope_upserts = [
            params
            for sql, params in connection.execute_calls
            if "insert into read_model.pending_invoice_scopes" in sql
        ]
        self.assertEqual(
            [(params[0], params[3]) for params in scope_upserts],
            [
                ("expense:all:2026-05", 3),
                ("expense:requires_invoice:2026-05", 2),
                ("expense:bank_statement_as_invoice:2026-05", 1),
                ("expense:no_invoice_required:2026-05", 0),
            ],
        )

    def test_pending_invoice_repository_all_direction_combines_direction_summaries(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {"id": "txn-expense", "bank_transaction": {"id": "txn-expense"}, "can_create_invoice": True},
                    "missing_invoice": True,
                    "can_create_invoice": True,
                },
                {
                    "payload": {"id": "txn-income", "bank_transaction": {"id": "txn-income"}, "can_create_invoice": False},
                    "missing_invoice": True,
                    "can_create_invoice": False,
                },
            ],
            pending_source_counts={"expense": 356, "income": 75},
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(direction="all", filter="all", date_from=None, date_to=None, keyword=None, page=1, page_size=50)

        self.assertEqual(payload["pagination"]["total"], 2)
        self.assertEqual(payload["summary"]["source_summary"]["current_direction_rows"], 431)
        self.assertEqual(payload["summary"]["source_summary"]["excluded_direction_rows"], 0)

    def test_pending_invoice_repository_returns_fresh_empty_scope_without_api_miss(self) -> None:
        connection = SearchPendingConnection(pending_rows=[], dirty=False)
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 50, "total": 0})
        self.assertEqual(payload["refresh_status"], "fresh")

    def test_pending_invoice_repository_returns_none_when_scope_was_never_built(self) -> None:
        connection = SearchPendingConnection(pending_rows=[], dirty=False, pending_scope_exists=False)
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        self.assertIsNone(payload)

    def test_pending_invoice_repository_accepts_filter_json_and_native_sort_fields(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-1",
                        "bank_transaction": {"id": "txn-1", "counterparty_name": "昆明供应商"},
                        "input_invoices": {"primary": {"seller_name": "昆明供应商"}},
                    },
                    "missing_invoice": False,
                    "can_create_invoice": False,
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            filters='[{"field":"status_code","operator":"in","values":["paid_invoiced"]}]',
            sort_field="seller_name",
            sort_direction="asc",
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("status_code", executed_sql)
        self.assertIn("seller_name asc", executed_sql)

    def test_pending_invoice_repository_filters_status_groups_by_visible_status(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-statement-paid",
                        "bank_transaction": {"id": "txn-statement-paid"},
                        "invoice_acquisition_status": {"code": "paid_invoiced"},
                        "filter_group": "bank_statement_as_invoice",
                    },
                    "missing_invoice": False,
                    "can_create_invoice": False,
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        repository.list_pending_invoice_rows(
            direction="expense",
            filter="bank_statement_as_invoice",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("status_code", executed_sql)
        self.assertNotIn("filter_group = %s", executed_sql)

    def test_pending_invoice_repository_requires_invoice_filter_uses_status_bucket(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-paid-pending",
                        "bank_transaction": {"id": "txn-paid-pending"},
                        "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                        "filter_group": "all",
                    },
                    "missing_invoice": True,
                    "can_create_invoice": True,
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        repository.list_pending_invoice_rows(
            direction="expense",
            filter="requires_invoice",
            date_from=None,
            date_to=None,
            keyword=None,
            filters=json.dumps([{"field": "status_code", "operator": "in", "values": ["paid_pending_invoice"]}]),
            page=1,
            page_size=50,
        )

        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("status_code = any", executed_sql)
        self.assertNotIn("filter_group = %s", executed_sql)

    def test_pending_invoice_repository_supports_new_column_filter_fields_as_and_clauses(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-filtered",
                        "bank_transaction": {
                            "id": "txn-filtered",
                            "bank_short_name": "光大",
                            "account_last4": "8826",
                            "effective_tag_label_path": ["项目开销", "员工报销"],
                        },
                        "oa": {"primary": {"application_type": "支付申请"}},
                    },
                    "missing_invoice": True,
                    "can_create_invoice": True,
                }
            ],
        )
        repository = PostgresReadModelRepository(connection)

        repository.list_pending_invoice_rows(
            direction="all",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            filters=json.dumps(
                [
                    {"field": "bank_account", "operator": "in", "values": ["光大 8826"]},
                    {"field": "transaction_tag", "operator": "in", "values": ["项目开销 / 员工报销"]},
                    {"field": "direction", "operator": "in", "values": ["expense"]},
                    {"field": "oa_application_type", "operator": "in", "values": ["支付申请"]},
                ],
                ensure_ascii=False,
            ),
            page=1,
            page_size=50,
        )

        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("bank_short_name", executed_sql)
        self.assertIn("effective_tag_label_path", executed_sql)
        self.assertIn("direction", executed_sql)
        self.assertIn("application_type", executed_sql)
        self.assertIn(" and ", executed_sql)

    def test_pending_invoice_repository_builds_filter_options_in_sql(self) -> None:
        connection = SearchPendingConnection(
            pending_filter_option_rows=[
                {"field": "bank_account", "value": "光大 8826", "option_count": 3},
                {"field": "status_code", "value": "paid_pending_invoice", "option_count": 2},
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_filter_options(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            filters=json.dumps([{"field": "status_code", "operator": "in", "values": ["paid_pending_invoice"]}]),
        )

        self.assertEqual(payload["direction"], "expense")
        self.assertEqual(payload["filter"], "all")
        self.assertEqual(payload["options"]["bank_account"], [{"value": "光大 8826", "label": "光大 8826", "count": 3}])
        self.assertEqual(
            payload["options"]["status_code"],
            [{"value": "paid_pending_invoice", "label": "paid_pending_invoice", "count": 2}],
        )
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("ranked_options", executed_sql)
        self.assertIn("status_code", executed_sql)
        self.assertNotIn("limit %s offset %s", executed_sql)

    def test_pending_invoice_api_miss_enqueues_refresh_without_sync_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {"list_pending_invoice_rows": lambda *_args, **_kwargs: None},
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pending invoice API miss must not scan in-memory state"))},
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_miss")])

    def test_pending_invoice_api_reads_sql_page(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-1",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": _pending_invoice_expected_source_versions(),
                }
            },
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pending invoice SQL hit must not scan in-memory state"))},
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-1")
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_pending_invoice_api_treats_legacy_sql_payload_shape_as_refreshing(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [{"id": "txn-legacy", "bank_transaction": {"id": "txn-legacy"}, "invoices": []}],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": {
                        key: value
                        for key, value in _pending_invoice_expected_source_versions().items()
                        if key != "workbench_relation_source_versions"
                    },
                }
            },
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy SQL shape must not scan in-memory state"))},
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_schema_stale")])

    def test_pending_invoice_api_source_version_stale_serves_existing_rows_and_enqueues_refresh(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-stale-version",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    **_pending_invoice_statistics_contract(),
                    "source_versions": {
                        "pending_invoice_read_model_schema_version": "2026-05-pending-invoice-v1",
                        "pending_invoice_tag_groups_version": 999,
                    },
                }
            },
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("source-version stale pending invoice API must not scan in-memory state"))},
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-stale-version")
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("pending_invoice_tag_groups_version_mismatch", payload["read_model_stale_reasons"])
        self.assertEqual(
            queue.refreshes,
            [("pending_invoice", "expense:all", "api_source_versions_stale")],
        )

    def test_pending_invoice_api_bank_detail_source_version_stale_enqueues_refresh(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()

        class PendingRepo:
            def __init__(self) -> None:
                self.version_queries: list[dict[str, object]] = []

            def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-bank-tag-stale",
                            "bank_transaction": {
                                "id": "txn-bank-tag-stale",
                                "trade_time": "2026-04-23 11:18:17",
                                "effective_tag_label_path": [],
                            },
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    **_pending_invoice_statistics_contract(
                        expense_versions={
                            **_pending_invoice_expected_source_versions(),
                            "bank_detail_source_versions": {
                                "bank_detail_schema_version": 12,
                                "bank_auto_tag_rules_version": 7,
                            },
                        },
                        income_versions={
                            **_pending_invoice_expected_source_versions(),
                            "bank_detail_source_versions": {
                                "bank_detail_schema_version": 12,
                                "bank_auto_tag_rules_version": 7,
                            },
                        },
                    ),
                    "source_versions": {
                        key: value
                        for key, value in _pending_invoice_expected_source_versions().items()
                        if key != "bank_detail_source_versions"
                    },
                }

            def pending_invoice_bank_detail_source_versions(self, **kwargs: object) -> dict[str, object]:
                self.version_queries.append(dict(kwargs))
                return {"bank_detail_schema_version": 12, "bank_auto_tag_rules_version": 7}

        pending_repo = PendingRepo()
        app._pending_invoice_sql_read_repository = pending_repo
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("bank-detail stale pending invoice API must not scan in-memory state"))},
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-bank-tag-stale")
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("bank_detail_source_versions_missing", payload["read_model_stale_reasons"])
        self.assertEqual(
            queue.refreshes,
            [("pending_invoice", "expense:all:2026-04", "api_source_versions_stale")],
        )
        self.assertEqual(pending_repo.version_queries[0]["direction"], "expense")
        self.assertEqual(pending_repo.version_queries[0]["filter"], "all")

    def test_pending_invoice_api_workbench_relation_source_version_stale_enqueues_refresh(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()

        class PendingRepo:
            def __init__(self) -> None:
                self.version_queries: list[dict[str, object]] = []

            def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-relation-stale",
                            "bank_transaction": {
                                "id": "txn-relation-stale",
                                "trade_time": "2026-04-23 11:18:17",
                                "effective_tag_label_path": [],
                            },
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    **_pending_invoice_statistics_contract(
                        expense_versions={
                            **_pending_invoice_expected_source_versions(),
                            "workbench_relation_source_versions": {
                                "workbench_relation_schema_version": "2026-06-relation-v1",
                                "source_version": 42,
                            },
                        },
                        income_versions={
                            **_pending_invoice_expected_source_versions(),
                            "workbench_relation_source_versions": {
                                "workbench_relation_schema_version": "2026-06-relation-v1",
                                "source_version": 42,
                            },
                        },
                    ),
                    "source_versions": {
                        key: value
                        for key, value in _pending_invoice_expected_source_versions().items()
                        if key != "workbench_relation_source_versions"
                    },
                }

            def pending_invoice_workbench_relation_source_versions(self, **kwargs: object) -> dict[str, object]:
                self.version_queries.append(dict(kwargs))
                return {"workbench_relation_schema_version": "2026-06-relation-v1", "source_version": 42}

        pending_repo = PendingRepo()
        app._pending_invoice_sql_read_repository = pending_repo
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {
                "list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("relation stale pending invoice API must not scan in-memory state")
                )
            },
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-relation-stale")
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("workbench_relation_source_versions_missing", payload["read_model_stale_reasons"])
        self.assertEqual(
            queue.refreshes,
            [("pending_invoice", "expense:all:2026-04", "api_source_versions_stale")],
        )
        self.assertEqual(pending_repo.version_queries[0]["direction"], "expense")
        self.assertEqual(pending_repo.version_queries[0]["filter"], "all")

    def test_pending_invoice_api_workbench_relation_source_version_mismatch_enqueues_refresh(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()

        class PendingRepo:
            def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-relation-old",
                            "bank_transaction": {
                                "id": "txn-relation-old",
                                "trade_time": "2026-04-23 11:18:17",
                                "effective_tag_label_path": [],
                            },
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    **_pending_invoice_statistics_contract(
                        expense_versions={
                            **_pending_invoice_expected_source_versions(),
                            "workbench_relation_source_versions": {
                                "workbench_relation_schema_version": "2026-06-relation-v1",
                                "source_version": 42,
                            },
                        },
                        income_versions={
                            **_pending_invoice_expected_source_versions(),
                            "workbench_relation_source_versions": {
                                "workbench_relation_schema_version": "2026-06-relation-v1",
                                "source_version": 42,
                            },
                        },
                    ),
                    "source_versions": {
                        **_pending_invoice_expected_source_versions(),
                        "workbench_relation_source_versions": {
                            "workbench_relation_schema_version": "2026-06-relation-v1",
                            "source_version": 41,
                        },
                    },
                }

            def pending_invoice_workbench_relation_source_versions(self, **_kwargs: object) -> dict[str, object]:
                return {"workbench_relation_schema_version": "2026-06-relation-v1", "source_version": 42}

        app._pending_invoice_sql_read_repository = PendingRepo()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {
                "list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("relation mismatch pending invoice API must not scan in-memory state")
                )
            },
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("workbench_relation_source_versions_mismatch", payload["read_model_stale_reasons"])
        self.assertEqual(
            queue.refreshes,
            [("pending_invoice", "expense:all:2026-04", "api_source_versions_stale")],
        )

    def test_pending_invoice_all_direction_miss_enqueues_expense_and_income_refresh_without_sync_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {"list_pending_invoice_rows": lambda *_args, **_kwargs: None},
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("all-direction pending invoice API miss must not scan in-memory state"))},
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["all"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(
            queue.refreshes,
            [
                ("pending_invoice", "expense:all", "api_miss"),
                ("pending_invoice", "income:all", "api_miss"),
            ],
        )

    def test_pending_invoice_all_direction_nested_child_source_versions_are_fresh(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()

        bank_versions = {
            "expense": {"2026-01": {"source": "bank-expense"}},
            "income": {"2026-01": {"source": "bank-income"}},
        }
        relation_versions = {
            "expense": {"2026-01": {"source": "relation-expense"}},
            "income": {"2026-01": {"source": "relation-income"}},
        }

        class PendingRepo:
            def __init__(self) -> None:
                self.version_calls: list[tuple[str, dict[str, object]]] = []

            def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "direction": "all",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-all-fresh",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {
                        "total_rows": 1,
                        "missing_invoice_rows": 1,
                        "create_invoice_available_rows": 1,
                        "source_summary": {
                            "bank_transaction_rows": 1,
                            "expense_rows": 1,
                            "income_rows": 0,
                            "current_direction_rows": 1,
                            "excluded_direction_rows": 0,
                        },
                    },
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    **_pending_invoice_statistics_contract(
                        expense_versions={
                            **_pending_invoice_expected_source_versions(),
                            "bank_detail_source_versions": bank_versions["expense"],
                            "workbench_relation_source_versions": relation_versions["expense"],
                        },
                        income_versions={
                            **_pending_invoice_expected_source_versions(),
                            "bank_detail_source_versions": bank_versions["income"],
                            "workbench_relation_source_versions": relation_versions["income"],
                        },
                    ),
                    "source_versions": {
                        **_pending_invoice_expected_source_versions(),
                        "bank_detail_source_versions": bank_versions,
                        "workbench_relation_source_versions": relation_versions,
                    },
                }

            def pending_invoice_bank_detail_source_versions(self, **kwargs: object) -> dict[str, object]:
                self.version_calls.append(("bank", dict(kwargs)))
                return bank_versions.get(str(kwargs.get("direction") or ""), {})

            def pending_invoice_workbench_relation_source_versions(self, **kwargs: object) -> dict[str, object]:
                self.version_calls.append(("relation", dict(kwargs)))
                return relation_versions.get(str(kwargs.get("direction") or ""), {})

        pending_repo = PendingRepo()
        app._pending_invoice_sql_read_repository = pending_repo
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fresh all-direction API must not scan in-memory state"))},
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["all"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertNotIn("read_model_stale_reasons", payload)
        self.assertEqual(queue.refreshes, [])
        for kind in ("bank", "relation"):
            for direction in ("expense", "income"):
                self.assertEqual(
                    pending_repo.version_calls.count((kind, {"direction": direction, "filter": "all"})),
                    2,
                )

    def test_pending_invoice_api_serves_existing_rows_while_scope_refreshes(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-stale",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "refreshing",
                },
                "pending_invoice_source_summary": lambda *_args, **_kwargs: {
                    "bank_transaction_rows": 431,
                    "expense_rows": 356,
                    "income_rows": 75,
                    "current_direction_rows": 356,
                    "excluded_direction_rows": 75,
                },
            },
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-stale")
        self.assertEqual(payload["summary"]["source_summary"]["bank_transaction_rows"], 431)
        self.assertEqual(payload["summary"]["source_summary"]["income_rows"], 75)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(
            queue.refreshes,
            [
                ("pending_invoice", "expense:all", "api_statistics_source_versions_stale"),
                ("pending_invoice", "income:all", "api_statistics_source_versions_stale"),
            ],
        )

    def test_pending_invoice_read_model_service_rejects_unconfigured_repository_without_sync_scan(self) -> None:
        service = PendingInvoiceReadModelService(
            repository=None,
            queue_repository=QueueRecorder(),
            row_normalizer=lambda rows, **_kwargs: rows,
            settings_provider=lambda: {},
            source_versions_provider=lambda: {"pending_invoice_read_model_schema_version": "2026-06-pending-invoice-oa-identity-v2"},
        )

        with self.assertRaisesRegex(Exception, "Pending invoice SQL read repository is not configured"):
            service.rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})

    def test_pending_invoice_read_model_service_all_rows_returns_refreshing_payload_without_fallback(self) -> None:
        queue = QueueRecorder()
        service = PendingInvoiceReadModelService(
            repository=type("PendingRepo", (), {"list_pending_invoice_rows": lambda *_args, **_kwargs: None})(),
            queue_repository=queue,
            row_normalizer=lambda rows, **_kwargs: rows,
            settings_provider=lambda: {},
            source_versions_provider=lambda: {"pending_invoice_read_model_schema_version": "2026-06-pending-invoice-oa-identity-v2"},
        )

        payload = service.all_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_miss")])

    def test_pending_invoice_dependency_mismatch_enqueues_only_changed_month_shard(self) -> None:
        current_versions = {
            **_pending_invoice_expected_source_versions(),
            "workbench_relation_source_versions": {
                "2026-02": {"relation_count": 2, "relation_updated_at": "new"},
                "2026-03": {"relation_count": 1, "relation_updated_at": "same"},
            },
        }
        persisted_versions = {
            **current_versions,
            "workbench_relation_source_versions": {
                "2026-02": {"relation_count": 1, "relation_updated_at": "old"},
                "2026-03": {"relation_count": 1, "relation_updated_at": "same"},
            },
        }
        queue = QueueRecorder()
        service = PendingInvoiceReadModelService(
            repository=type(
                "PendingRepo",
                (),
                {
                    "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                        "direction": "expense",
                        "filter": "all",
                        "rows": [
                            {
                                "id": "txn-2026-02",
                                "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                                "input_invoices": {"primary": None, "summaries": []},
                                "oa": {"primary": None, "summaries": []},
                            }
                        ],
                        "pagination": {"page": 1, "page_size": 50, "total": 1},
                        "summary": {"total_rows": 1},
                        "refresh_status": "fresh",
                        "source_versions": persisted_versions,
                    },
                },
            )(),
            queue_repository=queue,
            source_versions_provider=lambda: current_versions,
        )

        payload = service.rows({"direction": ["expense"], "filter": ["all"]}, include_statistics=False)

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(
            queue.refreshes,
            [("pending_invoice", "expense:all:2026-02", "api_source_versions_stale")],
        )

    def test_pending_invoice_rows_loads_settings_once_for_all_request_consumers(self) -> None:
        settings_payload = {
            "bank_transaction_tags": {"version": 9, "items": [{"code": "A1"}]},
            "pending_invoice_tag_groups": {"version": 3},
            "pending_output_invoice_tag_groups": {"version": 4},
            "bank_account_mappings": [],
        }
        settings_calls = 0
        source_settings: list[dict[str, object] | None] = []
        normalized_settings: list[dict[str, object]] = []
        expected_versions = _pending_invoice_expected_source_versions()

        def settings_provider() -> dict[str, object]:
            nonlocal settings_calls
            settings_calls += 1
            return settings_payload

        def source_versions_provider(
            **kwargs: object,
        ) -> dict[str, object]:
            source_settings.append(kwargs.get("settings_payload"))  # type: ignore[arg-type]
            return expected_versions

        def normalize_rows(
            rows: list[dict[str, object]],
            *,
            settings_payload: dict[str, object],
        ) -> list[dict[str, object]]:
            normalized_settings.append(settings_payload)
            return rows

        service = PendingInvoiceReadModelService(
            repository=type(
                "PendingRepo",
                (),
                {
                    "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                        "direction": "expense",
                        "filter": "all",
                        "rows": [
                            {
                                "id": "txn-1",
                                "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                                "input_invoices": {"primary": None, "summaries": []},
                                "oa": {"primary": None, "summaries": []},
                            }
                        ],
                        "pagination": {"page": 1, "page_size": 50, "total": 1},
                        "summary": {"total_rows": 1},
                        "refresh_status": "fresh",
                        **_pending_invoice_statistics_contract(
                            expense_versions=expected_versions,
                            income_versions=expected_versions,
                        ),
                        "source_versions": expected_versions,
                    },
                },
            )(),
            queue_repository=QueueRecorder(),
            row_normalizer=normalize_rows,
            settings_provider=settings_provider,
            source_versions_provider=source_versions_provider,
        )

        payload = service.rows({"direction": ["expense"], "filter": ["all"]})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(settings_calls, 1)
        self.assertGreaterEqual(len(source_settings), 3)
        self.assertTrue(all(item is settings_payload for item in source_settings))
        self.assertEqual(normalized_settings, [settings_payload])

    def test_pending_invoice_statistics_and_rows_mismatch_enqueue_one_atomic_scope_batch(self) -> None:
        current_versions = {
            **_pending_invoice_expected_source_versions(),
            "workbench_relation_source_versions": {
                "2026-02": {"relation_count": 2, "relation_updated_at": "new"},
                "2026-03": {"relation_count": 2, "relation_updated_at": "new"},
            },
        }
        stale_statistics_versions = {
            **current_versions,
            "workbench_relation_source_versions": {
                "2026-02": {"relation_count": 1, "relation_updated_at": "old"},
                "2026-03": {"relation_count": 2, "relation_updated_at": "new"},
            },
        }
        stale_row_versions = {
            **current_versions,
            "workbench_relation_source_versions": {
                "2026-02": {"relation_count": 2, "relation_updated_at": "new"},
                "2026-03": {"relation_count": 1, "relation_updated_at": "old"},
            },
        }
        queue = AtomicBatchQueueRecorder()
        service = PendingInvoiceReadModelService(
            repository=type(
                "PendingRepo",
                (),
                {
                    "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                        "direction": "expense",
                        "filter": "all",
                        "rows": [
                            {
                                "id": "txn-2026-02",
                                "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                                "input_invoices": {"primary": None, "summaries": []},
                                "oa": {"primary": None, "summaries": []},
                            }
                        ],
                        "pagination": {"page": 1, "page_size": 50, "total": 1},
                        "summary": {"total_rows": 1},
                        "refresh_status": "fresh",
                        **_pending_invoice_statistics_contract(
                            expense_versions=stale_statistics_versions,
                            income_versions=current_versions,
                        ),
                        "source_versions": stale_row_versions,
                    },
                },
            )(),
            queue_repository=queue,
            source_versions_provider=lambda: current_versions,
        )

        payload = service.rows({"direction": ["expense"], "filter": ["all"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["statistics_status"], "refreshing")
        self.assertIsNone(payload["statistics"])
        self.assertEqual(
            queue.refresh_batches,
            [
                {
                    "scope_type": "pending_invoice",
                    "scope_keys": [
                        "expense:all:2026-02",
                        "expense:all:2026-03",
                    ],
                    "reason": "api_source_versions_stale",
                    "tenant_id": "default",
                    "priority": "normal",
                    "trace_id": None,
                    "metadata": None,
                }
            ],
        )
        self.assertEqual(queue.refreshes, [])

    def test_pending_invoice_in_flight_statistics_with_current_proof_do_not_enqueue_parent_scopes(self) -> None:
        current_versions = _pending_invoice_expected_source_versions()
        queue = QueueRecorder()
        service = PendingInvoiceReadModelService(
            repository=type(
                "PendingRepo",
                (),
                {
                    "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                        "direction": "expense",
                        "filter": "all",
                        "rows": [
                            {
                                "id": "txn-2026-02",
                                "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                                "input_invoices": {"primary": None, "summaries": []},
                                "oa": {"primary": None, "summaries": []},
                            }
                        ],
                        "pagination": {"page": 1, "page_size": 50, "total": 1},
                        "summary": {"total_rows": 1},
                        "refresh_status": "fresh",
                        "statistics": None,
                        "statistics_status": "refreshing",
                        "statistics_source_versions_by_scope": {
                            "expense:all": current_versions,
                            "income:all": current_versions,
                        },
                        "source_versions": current_versions,
                    },
                },
            )(),
            queue_repository=queue,
            source_versions_provider=lambda: current_versions,
        )

        payload = service.rows({"direction": ["expense"], "filter": ["all"]})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["statistics_status"], "refreshing")
        self.assertIsNone(payload["statistics"])
        self.assertEqual(queue.refreshes, [])

    def test_pending_invoice_read_model_service_all_rows_rejects_export_row_limit_before_scanning_more_pages(self) -> None:
        class PendingRepo:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_pending_invoice_rows(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(dict(kwargs))
                return {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-large-export",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {
                        "page": 1,
                        "page_size": 200,
                        "total": PENDING_INVOICE_EXPORT_ROW_LIMIT + 1,
                    },
                    "summary": {"total_rows": PENDING_INVOICE_EXPORT_ROW_LIMIT + 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": _pending_invoice_expected_source_versions(),
                }

        repository = PendingRepo()
        service = PendingInvoiceReadModelService(
            repository=repository,
            queue_repository=QueueRecorder(),
            row_normalizer=lambda rows, **_kwargs: rows,
            settings_provider=lambda: {},
            source_versions_provider=_pending_invoice_expected_source_versions,
        )

        with self.assertRaises(PendingInvoiceError) as context:
            service.all_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})

        self.assertEqual(context.exception.error_code, "pending_invoice_export_row_limit_exceeded")
        self.assertEqual(context.exception.details, {"total": PENDING_INVOICE_EXPORT_ROW_LIMIT + 1, "limit": PENDING_INVOICE_EXPORT_ROW_LIMIT})
        self.assertEqual(len(repository.calls), 1)
        self.assertEqual(repository.calls[0]["page"], "1")
        self.assertEqual(repository.calls[0]["page_size"], "200")

    def test_pending_invoice_all_rows_skips_title_statistics_on_every_page(self) -> None:
        expected_versions = _pending_invoice_expected_source_versions()

        class PendingRepo:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_pending_invoice_rows(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(dict(kwargs))
                page = int(kwargs.get("page") or 1)
                count = 200 if page == 1 else 1
                return {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": f"txn-{page}-{index}",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                        for index in range(count)
                    ],
                    "pagination": {"page": page, "page_size": 200, "total": 201},
                    "summary": {"total_rows": 201},
                    "statistics": {"bank_transaction_count": 201},
                    "statistics_status": "fresh",
                    "statistics_source_versions_by_scope": {
                        "expense:all": expected_versions,
                        "income:all": expected_versions,
                    },
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": expected_versions,
                }

        repository = PendingRepo()
        service = PendingInvoiceReadModelService(
            repository=repository,
            queue_repository=QueueRecorder(),
            row_normalizer=lambda rows, **_kwargs: rows,
            settings_provider=lambda: {},
            source_versions_provider=lambda: expected_versions,
        )

        payload = service.all_rows({"direction": ["expense"]})

        self.assertEqual(len(payload["rows"]), 201)
        self.assertEqual([call["include_statistics"] for call in repository.calls], [False, False])
        self.assertNotIn("statistics", payload)
        self.assertNotIn("statistics_status", payload)

    def test_pending_invoice_sql_page_preserves_bank_tag_settings(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._app_settings_service = type(
            "SettingsService",
            (),
            {"get_settings_payload": lambda *_args: {"bank_transaction_tags": {"version": 7, "items": [{"code": "A1"}]}}},
        )()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-1",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": _pending_invoice_expected_source_versions(),
                }
            },
        )()

        response = _pending_invoice_rows_response(app, {"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["bank_transaction_tags"], {"version": 7, "items": [{"code": "A1"}]})
        self.assertEqual(payload["bank_transaction_tags_version"], 7)

    def test_pending_invoice_repository_aggregates_bank_detail_source_versions_across_month_shards(self) -> None:
        class PendingScopeConnection:
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.pending_invoice_scopes" in normalized:
                    return [
                        {
                            "scope_key": "expense:all:2026-04",
                            "row_count": 3,
                            "source_versions": {
                                **_pending_invoice_expected_source_versions(),
                                "bank_detail_source_versions": {"bank_detail_schema_version": 12, "rules": 7},
                                "workbench_relation_source_versions": {
                                    "workbench_relation_schema_version": "relation-v1",
                                    "source_version": 41,
                                },
                            },
                        },
                        {
                            "scope_key": "expense:all:2026-05",
                            "row_count": 4,
                            "source_versions": {
                                **_pending_invoice_expected_source_versions(),
                                "bank_detail_source_versions": {"bank_detail_schema_version": 12, "rules": 8},
                                "workbench_relation_source_versions": {
                                    "workbench_relation_schema_version": "relation-v1",
                                    "source_version": 42,
                                },
                            },
                        },
                    ]
                return []

            def transaction(self):
                connection = self

                class Transaction:
                    def __enter__(self) -> PendingScopeConnection:
                        return connection

                    def __exit__(self, exc_type, exc, traceback) -> bool:
                        return False

                return Transaction()

        repository = PostgresReadModelRepository(PendingScopeConnection())

        scope_row = repository._pending_invoice_scope_row("expense:all")

        self.assertIsNotNone(scope_row)
        source_versions = scope_row["source_versions"]
        self.assertEqual(
            source_versions["bank_detail_source_versions"],
            {
                "2026-04": {"bank_detail_schema_version": 12, "rules": 7},
                "2026-05": {"bank_detail_schema_version": 12, "rules": 8},
            },
        )
        self.assertEqual(
            source_versions["workbench_relation_source_versions"],
            {
                "2026-04": {"workbench_relation_schema_version": "relation-v1", "source_version": 41},
                "2026-05": {"workbench_relation_schema_version": "relation-v1", "source_version": 42},
            },
        )

    def test_pending_invoice_repository_ignores_zero_row_historical_shards_for_aggregate_source_versions(self) -> None:
        class PendingScopeConnection:
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.pending_invoice_scopes" in normalized:
                    return [
                        {
                            "scope_key": "expense:all:2023-05",
                            "row_count": 0,
                            "source_versions": {
                                **_pending_invoice_expected_source_versions(),
                                "pending_invoice_read_model_schema_version": "stale-schema",
                                "bank_auto_tag_rules_version": 1,
                                "bank_detail_source_versions": {"legacy": "stale"},
                            },
                        },
                        {
                            "scope_key": "expense:all:2026-05",
                            "row_count": 2,
                            "source_versions": {
                                **_pending_invoice_expected_source_versions(),
                                "bank_auto_tag_rules_version": 7,
                                "bank_detail_source_versions": {"bank_detail_schema_version": 12, "rules": 8},
                            },
                        },
                    ]
                return []

            def transaction(self):
                connection = self

                class Transaction:
                    def __enter__(self) -> PendingScopeConnection:
                        return connection

                    def __exit__(self, exc_type, exc, traceback) -> bool:
                        return False

                return Transaction()

        repository = PostgresReadModelRepository(PendingScopeConnection())

        scope_row = repository._pending_invoice_scope_row("expense:all")

        self.assertIsNotNone(scope_row)
        source_versions = scope_row["source_versions"]
        self.assertEqual(source_versions["pending_invoice_read_model_schema_version"], "2026-06-pending-invoice-oa-identity-v2")
        self.assertEqual(source_versions["bank_auto_tag_rules_version"], 7)
        self.assertEqual(
            source_versions["bank_detail_source_versions"],
            {"2026-05": {"bank_detail_schema_version": 12, "rules": 8}},
        )

    def test_pending_invoice_filtered_scope_keeps_zero_row_month_dependency_proofs(self) -> None:
        class PendingScopeConnection:
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.pending_invoice_rows" in normalized:
                    return [{"scope_key": "2026-04"}, {"scope_key": "2026-05"}]
                if "from read_model.pending_invoice_scopes" not in normalized:
                    return []
                return [
                    {
                        "scope_key": "income:cash_income",
                        "row_count": 0,
                        "source_versions": {
                            **_pending_invoice_expected_source_versions(),
                            "bank_auto_tag_rules_version": 1,
                            "bank_detail_source_versions": {"legacy": "parent"},
                            "workbench_relation_source_versions": {"legacy": "parent"},
                        },
                    },
                    {
                        "scope_key": "income:cash_income:2023-05",
                        "row_count": 0,
                        "source_versions": {
                            **_pending_invoice_expected_source_versions(),
                            "bank_auto_tag_rules_version": 1,
                            "bank_detail_source_versions": {"legacy": "historical"},
                            "workbench_relation_source_versions": {"legacy": "historical"},
                        },
                    },
                    {
                        "scope_key": "income:cash_income:2026-04",
                        "row_count": 0,
                        "source_versions": {
                            **_pending_invoice_expected_source_versions(),
                            "bank_detail_source_versions": {"source_version": 7},
                            "workbench_relation_source_versions": {"source_version": 41},
                        },
                    },
                    {
                        "scope_key": "income:cash_income:2026-05",
                        "row_count": 0,
                        "source_versions": {
                            **_pending_invoice_expected_source_versions(),
                            "bank_detail_source_versions": {"source_version": 8},
                            "workbench_relation_source_versions": {"source_version": 42},
                        },
                    },
                ]

        repository = PostgresReadModelRepository(PendingScopeConnection())

        scope_row = repository._pending_invoice_scope_row("income:cash_income")

        self.assertEqual(
            scope_row["source_versions"]["bank_detail_source_versions"],
            {
                "2026-04": {"source_version": 7},
                "2026-05": {"source_version": 8},
            },
        )
        self.assertEqual(
            scope_row["source_versions"]["workbench_relation_source_versions"],
            {
                "2026-04": {"source_version": 41},
                "2026-05": {"source_version": 42},
            },
        )

    def test_pending_invoice_repository_loads_workbench_relation_source_versions_for_matching_months(self) -> None:
        class PendingRelationScopeConnection:
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
                normalized = " ".join(sql.lower().split())
                if "pending_invoice_relation_source_versions_bulk" in normalized:
                    self.relation_source_summary_params = getattr(self, "relation_source_summary_params", [])
                    self.relation_source_summary_params.append(params)
                    return [
                        {
                            "scope_key": "2026-04",
                            "relation_count": 1,
                            "relation_updated_at": "2026-04-01 10:00:00",
                        },
                        {
                            "scope_key": "2026-05",
                            "relation_count": 2,
                            "relation_updated_at": "2026-05-01 10:00:00",
                        },
                    ]
                return []

            def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
                raise AssertionError(f"unexpected per-scope source-version query: {sql} {params}")

            def transaction(self):
                connection = self

                class Transaction:
                    def __enter__(self) -> PendingRelationScopeConnection:
                        return connection

                    def __exit__(self, exc_type, exc, traceback) -> bool:
                        return False

                return Transaction()

        connection = PendingRelationScopeConnection()
        repository = PostgresReadModelRepository(connection)

        source_versions = repository.pending_invoice_workbench_relation_source_versions(
            direction="expense",
            filter="all",
        )

        self.assertEqual(
            connection.relation_source_summary_params,
            [("expense", "turnover_manual_closure")],
        )
        self.assertEqual(
            source_versions,
            {
                "2026-04": {
                    "source": "workbench_pair_relations",
                    "scope_key": "2026-04",
                    "relation_count": 1,
                    "relation_updated_at": "2026-04-01 10:00:00",
                },
                "2026-05": {
                    "source": "workbench_pair_relations",
                    "scope_key": "2026-05",
                    "relation_count": 2,
                    "relation_updated_at": "2026-05-01 10:00:00",
                },
            },
        )

    def test_pending_invoice_sql_projection_emits_upgraded_four_zone_payload(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingProjectionConnection())

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["id"], "txn-1")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "paid_pending_invoice")
        self.assertEqual(payload["invoice_acquisition_status"]["label"], "已支付待开票")
        self.assertIn("input_invoices", payload)
        self.assertIn("oa", payload)
        self.assertEqual(payload["bank_transaction"]["account_last4"], "1234")

    def test_pending_invoice_sql_projection_consumes_workbench_relation_distribution(self) -> None:
        relation_facade = FakeWorkbenchRelationReadFacade(
            {
                "status": "fresh",
                "rows": [
                    {
                        "row_id": "txn-1",
                        "row_type": "bank_transaction",
                        "relation_status": "linked",
                        "group_ids": ["case-tian-196"],
                        "linked_oa": [
                            {
                                "id": "64e31b1fabc9012345678901",
                                "applicant": "田孟维",
                                "application_type": "日常报销",
                                "project_name": "云南溯源科技; 大理卷烟厂余...",
                                "detail_available": True,
                                "relation_case_id": "case-tian-196",
                            }
                        ],
                        "linked_bank_transactions": [{"id": "txn-1", "amount": "196.00"}],
                        "linked_input_invoices": [
                            {
                                "id": "oa-att-inv-70",
                                "invoice_no": "9132019MA1XM5TX71",
                                "digital_invoice_no": "",
                                "issue_date": "2026-01-20",
                                "seller_name": "中科视拓（南京）科技有限公司",
                                "seller_tax_no": "9132019MA1XM5TX71",
                                "buyer_name": "云南溯源科技有限公司",
                                "total_with_tax": "70.00",
                                "invoice_type": "input",
                                "source_kind": "oa_attachment_invoice",
                            },
                            {
                                "id": "oa-att-inv-126",
                                "invoice_no": "92532324MAC296HG5K",
                                "digital_invoice_no": "",
                                "issue_date": "2026-01-20",
                                "seller_name": "南华县沙桥镇润华清真饭店",
                                "seller_tax_no": "92532324MAC296HG5K",
                                "buyer_name": "云南溯源科技有限公司",
                                "total_with_tax": "126.00",
                                "invoice_type": "input",
                                "source_kind": "oa_attachment_invoice",
                            },
                        ],
                        "linked_output_invoices": [],
                    }
                ],
                "groups": [{"group_id": "case-tian-196", "relation_kind": "oa_bank_input_invoice"}],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-05"],
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingProjectionConnection(),
            workbench_relation_read_facade=relation_facade,
        )

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["input_invoices"]["relation_count"], 2)
        self.assertEqual(
            [invoice["id"] for invoice in payload["input_invoices"]["summaries"]],
            ["oa-att-inv-70", "oa-att-inv-126"],
        )
        self.assertEqual(payload["input_invoices"]["payment_summary"]["invoice_total"], "196.00")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "paid_invoiced")
        self.assertEqual(payload["oa"]["primary"]["id"], "64e31b1fabc9012345678901")
        self.assertEqual(payload["oa"]["relation_count"], 1)
        self.assertEqual(payload["relation_case_ids"], ["case-tian-196"])
        self.assertEqual(relation_facade.calls[0]["reason"], "pending_invoice_sql_projection")

    def test_pending_invoice_source_fast_path_does_not_wait_for_relation_read_model(self) -> None:
        class SourceRelationConnection(PendingProjectionConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.workbench_pair_relations" in normalized:
                    return [
                        {
                            "case_id": "case-source-pending",
                            "status": "active",
                            "row_ids": ["txn-1", "oa-source-pending", "inv-source-pending"],
                            "row_types": ["bank", "oa", "invoice"],
                        }
                    ]
                if "from app.bank_transactions" in normalized and "as row_id" in normalized:
                    return [
                        {
                            "row_id": "txn-1",
                            "counterparty_name_raw": "云南供应商",
                            "trade_time": "2026-05-20 10:00:00",
                            "txn_date": "2026-05-20",
                            "amount": "118.00",
                            "txn_direction": "outflow",
                            "summary": "转账",
                            "remark": "服务费",
                            "bank_serial_no": "SERIAL-1",
                            "account_name": "工商银行",
                            "account_no": "622200001234",
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return [
                        {
                            "row_id": "oa-source-pending",
                            "form_id": "OA-SOURCE-001",
                            "form_type": "支付申请",
                            "status": "已完成",
                            "applicant": "陈佳玉",
                            "project_name": "云南配电监控系统建设",
                            "amount": "118.00",
                        }
                    ]
                if "from app.invoices" in normalized:
                    return [
                        {
                            "row_id": "inv-source-pending",
                            "invoice_type": "input",
                            "invoice_code": "530001",
                            "invoice_no": "INV-SOURCE-001",
                            "digital_invoice_no": "",
                            "invoice_date": "2026-05-18",
                            "seller_name": "云南供应商",
                            "seller_tax_no": "91530000SOURCE",
                            "buyer_name": "云南溯源科技有限公司",
                            "buyer_tax_no": "91530000BUYER",
                            "amount": "118.00",
                            "total_with_tax": "118.00",
                        }
                    ]
                return super().fetch_all(sql, params)

            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                if "from app.workbench_pair_relations" in normalized:
                    return {"relation_count": 1, "relation_updated_at": "2026-05-20 10:00:00"}
                return super().fetch_one(sql, params)

        class FailingRelationFacade:
            def get_by_row_ids(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("source fast path must not read relation read model")

        builder = SearchPendingSqlProjectionBuilder(
            connection=SourceRelationConnection(),
            workbench_relation_read_facade=FailingRelationFacade(),
            relation_rows_from_source=True,
        )

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["relation_case_ids"], ["case-source-pending"])
        self.assertEqual(payload["oa"]["relation_count"], 1)
        self.assertEqual(payload["oa"]["primary"]["applicant"], "陈佳玉")
        self.assertEqual(payload["oa"]["primary"]["project_name"], "云南配电监控系统建设")
        self.assertEqual(payload["input_invoices"]["relation_count"], 1)
        self.assertEqual(payload["input_invoices"]["primary"]["invoice_no"], "INV-SOURCE-001")
        self.assertEqual(payload["input_invoices"]["primary"]["seller_name"], "云南供应商")
        self.assertEqual(payload["input_invoices"]["payment_summary"]["invoice_total"], "118.00")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "paid_invoiced")
        self.assertEqual(
            builder._pending_invoice_relation_source_versions["source"],
            "workbench_pair_relations",
        )

    def test_pending_invoice_sql_projection_collapses_multi_bank_relation_members(self) -> None:
        class MultiBankConnection(PendingProjectionConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.bank_transactions" in normalized:
                    return [
                        {
                            "transaction_id": transaction_id,
                            "counterparty_name_raw": "云南供应商",
                            "trade_time": f"2026-05-20 10:0{index}:00",
                            "txn_date": "2026-05-20",
                            "amount": amount,
                            "balance": "1000.00",
                            "currency": "CNY",
                            "summary": "转账",
                            "remark": "服务费",
                            "bank_serial_no": transaction_id,
                            "account_name": "工商银行",
                            "account_no": "622200001234",
                            "category_payload": {"category_code": "service_fee", "category_label": "服务费"},
                            "invoices": [],
                            "paid_total": "0.00",
                            "oa_applicant": "",
                            "oa_project_name": "",
                            "relation_case_ids": [],
                        }
                        for index, (transaction_id, amount) in enumerate(
                            [("txn-group-1", "120.00"), ("txn-group-2", "80.00"), ("txn-group-3", "50.00")],
                            start=1,
                        )
                    ]
                return super().fetch_all(sql, params)

        relation_rows = [
            {
                "row_id": transaction_id,
                "row_type": "bank_transaction",
                "relation_status": "linked",
                "group_ids": ["case-sql-multi"],
                "linked_oa": [
                    {"id": "oa-sql-1", "applicant": "张三", "application_type": "支付申请", "project_name": "项目一", "relation_case_id": "case-sql-multi"},
                    {"id": "oa-sql-2", "applicant": "李四", "application_type": "日常报销", "project_name": "项目二", "relation_case_id": "case-sql-multi"},
                ],
                "linked_bank_transactions": [
                    {"id": "txn-group-1", "amount": "120.00", "trade_time": "2026-05-20 10:01:00", "counterparty_name": "云南供应商", "relation_case_id": "case-sql-multi"},
                    {"id": "txn-group-2", "amount": "80.00", "trade_time": "2026-05-20 10:02:00", "counterparty_name": "云南供应商", "relation_case_id": "case-sql-multi"},
                    {"id": "txn-group-3", "amount": "50.00", "trade_time": "2026-05-20 10:03:00", "counterparty_name": "云南供应商", "relation_case_id": "case-sql-multi"},
                    {"id": "txn-other-direction", "amount": "25.00", "trade_time": "2026-05-20 10:04:00", "counterparty_name": "云南供应商", "relation_case_id": "case-sql-multi"},
                ],
                "linked_input_invoices": [
                    {"id": "inv-sql-1", "invoice_no": "IN-SQL-001", "seller_name": "云南供应商", "total_with_tax": "100.00", "relation_case_id": "case-sql-multi"},
                    {"id": "inv-sql-2", "invoice_no": "IN-SQL-002", "seller_name": "云南供应商", "total_with_tax": "150.00", "relation_case_id": "case-sql-multi"},
                ],
                "linked_output_invoices": [],
            }
            for transaction_id in ("txn-group-1", "txn-group-2", "txn-group-3")
        ]
        relation_facade = FakeWorkbenchRelationReadFacade(
            {
                "status": "fresh",
                "rows": relation_rows,
                "groups": [{"group_id": "case-sql-multi", "relation_status": "linked"}],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-05"],
            }
        )
        read_repository = CapturePendingInvoiceReadRepository()
        builder = SearchPendingSqlProjectionBuilder(
            connection=MultiBankConnection(),
            pending_invoice_read_model_repository=read_repository,
            workbench_relation_read_facade=relation_facade,
        )

        builder.rebuild_pending_invoice_read_model_scope("expense:all:2026-05")

        rows = read_repository.saved[0]["rows"]
        self.assertEqual(len(rows), 1)
        payload = rows[0]["payload"]
        self.assertEqual(payload["id"], "txn-group-1")
        self.assertEqual(payload["relation_case_ids"], ["case-sql-multi"])
        self.assertEqual(payload["bank_transactions"]["relation_count"], 4)
        self.assertEqual(payload["bank_transactions"]["linked_relation_count"], 4)
        self.assertEqual(
            [transaction["id"] for transaction in payload["bank_transactions"]["summaries"]],
            ["txn-group-1", "txn-group-2", "txn-group-3", "txn-other-direction"],
        )
        self.assertEqual(payload["bank_transactions"]["payment_summary"]["paid_total"], "275.00")
        self.assertEqual(payload["input_invoices"]["relation_count"], 2)
        self.assertEqual(payload["oa"]["relation_count"], 2)
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "paid_invoiced")
        self.assertEqual(
            read_repository.saved[0]["statistics_metadata"],
            {
                "statistics": {
                    "bank_transaction_count": 3,
                    "expense_transaction_count": 3,
                    "income_transaction_count": 0,
                    "found_invoice_transaction_count": 3,
                    "pending_invoice_transaction_count": 0,
                    "no_invoice_required_transaction_count": 0,
                    "cash_income_transaction_count": 0,
                    "linked_oa_transaction_count": 3,
                    "linked_input_invoice_transaction_count": 3,
                    "linked_output_invoice_transaction_count": 0,
                }
            },
        )

    def test_pending_invoice_sql_projection_preserves_candidate_without_closing_status(self) -> None:
        relation_facade = FakeWorkbenchRelationReadFacade(
            {
                "status": "fresh",
                "rows": [
                    {
                        "row_id": "txn-1",
                        "row_type": "bank_transaction",
                        "relation_status": "candidate",
                        "group_ids": ["candidate-sql-pending"],
                        "linked_oa": [
                            {
                                "id": "oa-candidate",
                                "applicant": "候选申请人",
                                "application_type": "支付申请",
                                "project_name": "候选项目",
                                "detail_available": True,
                                "relation_case_id": "candidate-sql-pending",
                                "relation_status": "candidate",
                            }
                        ],
                        "linked_bank_transactions": [
                            {
                                "id": "txn-1",
                                "amount": "118.00",
                                "relation_case_id": "candidate-sql-pending",
                                "relation_status": "candidate",
                            }
                        ],
                        "linked_input_invoices": [
                            {
                                "id": "inv-candidate",
                                "invoice_no": "IN-CANDIDATE",
                                "issue_date": "2026-05-20",
                                "seller_name": "云南供应商",
                                "total_with_tax": "118.00",
                                "invoice_type": "input",
                                "relation_case_id": "candidate-sql-pending",
                                "relation_status": "candidate",
                            }
                        ],
                        "linked_output_invoices": [],
                    }
                ],
                "groups": [{"group_id": "candidate-sql-pending", "relation_status": "candidate"}],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-05"],
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingProjectionConnection(),
            workbench_relation_read_facade=relation_facade,
        )

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["input_invoices"]["relation_count"], 1)
        self.assertEqual(payload["input_invoices"]["linked_relation_count"], 0)
        self.assertEqual(payload["input_invoices"]["summaries"][0]["relation_status"], "candidate")
        self.assertEqual(payload["oa"]["summaries"][0]["relation_status"], "candidate")
        self.assertEqual(payload["input_invoices"]["payment_summary"]["paid_total"], "0.00")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "paid_pending_invoice")
        self.assertTrue(payload["can_create_invoice"])

    def test_pending_invoice_sql_projection_uses_fresh_bank_tag_facade_category(self) -> None:
        facade = FakeBankTransactionTagFacade(
            {
                "status": "fresh",
                "rows": [
                    {
                        "transaction_id": "txn-1",
                        "effective_category_code": "equipment_purchase",
                        "effective_category_label": "设备采购",
                        "effective_category_primary_label": "货款",
                        "effective_category_sub_label": "设备采购",
                        "effective_category_third_label": None,
                        "effective_category_label_path": ["货款", "设备采购"],
                        "effective_category_source": "auto_confirmation",
                    }
                ],
                "source_versions": {"bank_detail": {"source_version": 9}},
                "scope_keys": ["2026-05"],
                "refresh_enqueued": False,
                "stale_reasons": [],
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingProjectionFacadeConnection(),
            bank_transaction_tag_read_facade=facade,
        )

        rows = builder._pending_invoice_rows(
            direction="expense",
            filter_name="bank_statement_as_invoice",
            month="2026-05",
        )

        self.assertEqual(facade.calls[0]["require_fresh"], True)
        self.assertEqual(facade.calls[0]["direction"], "expense")
        payload = rows[0]["payload"]
        self.assertEqual(payload["filter_group"], "bank_statement_as_invoice")
        self.assertEqual(payload["bank_transaction"]["effective_tag_code"], "equipment_purchase")
        self.assertEqual(payload["bank_transaction"]["effective_tag_label_path"], ["货款", "设备采购"])
        self.assertEqual(payload["invoice_acquisition_status"]["matched_rule"]["tag_code"], "equipment_purchase")

    def test_pending_invoice_sql_projection_refuses_to_publish_when_bank_tags_are_not_fresh(self) -> None:
        read_repository = CapturePendingInvoiceReadRepository()
        facade = FakeBankTransactionTagFacade(
            {
                "status": "stale",
                "rows": [],
                "source_versions": {"bank_detail": {"source_version": 8}},
                "scope_keys": ["2026-05"],
                "refresh_enqueued": True,
                "stale_reasons": ["read_model_not_fresh"],
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingProjectionFacadeConnection(),
            read_model_repository=read_repository,
            bank_transaction_tag_read_facade=facade,
        )

        with self.assertRaisesRegex(RuntimeError, "bank_detail_read_model_not_fresh"):
            builder.rebuild_pending_invoice_read_model_scope("expense:all:2026-05")

        self.assertEqual(read_repository.saved, [])

    def test_pending_invoice_sql_projection_preserves_real_bank_and_oa_identity(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingProjectionOaBankConnection())

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["bank_transaction"]["bank_name"], "招商银行")
        self.assertEqual(payload["bank_transaction"]["account_name"], "云南溯源科技有限公司")
        self.assertEqual(payload["bank_transaction"]["counterparty_account_no"], "622200009999")
        self.assertEqual(payload["oa"]["primary"]["id"], "oa-pay-2048")
        self.assertEqual(payload["oa"]["primary"]["relation_case_id"], "case-oa-bank")
        self.assertTrue(payload["oa"]["detail_available"])
        self.assertTrue(payload["oa"]["primary"]["detail_available"])

    def test_pending_invoice_sql_projection_does_not_expose_candidate_as_oa_id(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingProjectionCandidateOaConnection())

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["relation_case_ids"], ["candidate:oa-bank"])
        self.assertIsNone(payload["oa"]["primary"])
        self.assertFalse(payload["oa"]["detail_available"])

    def test_pending_invoice_sql_projection_uses_active_complement_for_requires_invoice_filter(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingComplementProjectionConnection())

        rows = builder._pending_invoice_rows(direction="expense", filter_name="requires_invoice", month="2026-05")

        self.assertEqual(
            [row["payload"]["id"] for row in rows],
            ["txn-custom-meal", "txn-no-category", "txn-archived", "txn-unknown"],
        )
        self.assertEqual(rows[0]["payload"]["filter_group"], "requires_invoice")
        self.assertEqual(rows[1]["payload"]["filter_group"], "all")
        self.assertEqual(
            rows[0]["payload"]["invoice_acquisition_status"]["matched_rule"]["group"],
            "requires_invoice",
        )

    def test_pending_invoice_sql_projection_closes_active_rule_tag_filter_groups(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingRuleClosureProjectionConnection())

        all_rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")
        requires_rows = builder._pending_invoice_rows(direction="expense", filter_name="requires_invoice", month="2026-05")
        statement_rows = builder._pending_invoice_rows(direction="expense", filter_name="bank_statement_as_invoice", month="2026-05")
        no_invoice_rows = builder._pending_invoice_rows(direction="expense", filter_name="no_invoice_required", month="2026-05")

        groups_by_id = {row["payload"]["id"]: row["payload"]["filter_group"] for row in all_rows}
        self.assertEqual(groups_by_id["txn-fee"], "requires_invoice")
        self.assertEqual(groups_by_id["txn-internal-transfer"], "bank_statement_as_invoice")
        self.assertEqual(groups_by_id["txn-salary"], "no_invoice_required")
        self.assertEqual(groups_by_id["txn-no-category"], "all")
        self.assertEqual(groups_by_id["txn-unknown"], "all")
        self.assertEqual(groups_by_id["txn-archived"], "all")
        self.assertEqual(
            [row["payload"]["id"] for row in requires_rows],
            ["txn-fee", "txn-no-category", "txn-unknown", "txn-archived"],
        )
        self.assertEqual([row["payload"]["id"] for row in statement_rows], ["txn-internal-transfer"])
        self.assertEqual([row["payload"]["id"] for row in no_invoice_rows], ["txn-salary"])

    def test_pending_invoice_sql_projection_uses_effective_category_fields_for_expense_rules(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingEffectiveCategoryProjectionConnection())

        statement_rows = builder._pending_invoice_rows(direction="expense", filter_name="bank_statement_as_invoice", month="2026-05")
        requires_rows = builder._pending_invoice_rows(direction="expense", filter_name="requires_invoice", month="2026-05")

        self.assertEqual([row["payload"]["id"] for row in statement_rows], ["txn-equipment"])
        payload = statement_rows[0]["payload"]
        self.assertEqual(payload["filter_group"], "bank_statement_as_invoice")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "bank_statement_as_invoice")
        self.assertEqual(payload["invoice_acquisition_status"]["matched_rule"]["tag_code"], "equipment_purchase")
        self.assertEqual(payload["invoice_acquisition_status"]["matched_rule"]["tag_label_path"], ["货款", "设备采购"])
        self.assertEqual(payload["bank_transaction"]["effective_tag_label_path"], ["货款", "设备采购"])
        self.assertEqual([row["payload"]["id"] for row in requires_rows], ["txn-expense-unknown"])
        self.assertEqual(requires_rows[0]["payload"]["filter_group"], "all")

    def test_pending_invoice_sql_projection_excludes_already_invoiced_rows_from_statement_filter(self) -> None:
        relation_facade = FakeWorkbenchRelationReadFacade(
            {
                "status": "fresh",
                "rows": [
                    {
                        "row_id": "txn-equipment",
                        "row_type": "bank_transaction",
                        "relation_status": "linked",
                        "group_ids": ["case-equipment-paid"],
                        "linked_oa": [],
                        "linked_bank_transactions": [{"id": "txn-equipment", "amount": "118.00", "direction": "outflow"}],
                        "linked_input_invoices": [
                            {
                                "id": "inv-equipment",
                                "invoice_no": "INV-EQUIPMENT",
                                "seller_name": "设备供应商",
                                "total_with_tax": "118.00",
                                "relation_case_id": "case-equipment-paid",
                            }
                        ],
                        "linked_output_invoices": [],
                    }
                ],
                "source_versions": {"workbench_relation_schema_version": 1},
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingEffectiveCategoryProjectionConnection(),
            workbench_relation_read_facade=relation_facade,
        )

        statement_rows = builder._pending_invoice_rows(direction="expense", filter_name="bank_statement_as_invoice", month="2026-05")
        all_rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        self.assertEqual(statement_rows, [])
        statuses = {row["payload"]["id"]: row["payload"]["invoice_acquisition_status"]["code"] for row in all_rows}
        self.assertEqual(statuses["txn-equipment"], "paid_invoiced")

    def test_pending_invoice_sql_projection_emits_income_output_statuses(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingIncomeProjectionConnection())

        rows = builder._pending_invoice_rows(direction="income", filter_name="all", month="2026-05")
        by_id = {row["payload"]["id"]: row["payload"] for row in rows}

        self.assertEqual(by_id["txn-output"]["invoice_acquisition_status"]["code"], "income_invoiced")
        self.assertEqual(by_id["txn-no-invoice"]["invoice_acquisition_status"]["code"], "income_no_invoice_required")
        self.assertEqual(by_id["txn-cash"]["invoice_acquisition_status"]["code"], "cash_income")
        self.assertEqual(by_id["txn-manual"]["invoice_acquisition_status"]["code"], "cash_income")
        self.assertEqual(by_id["txn-pending"]["invoice_acquisition_status"]["code"], "income_pending_invoice")
        self.assertEqual(by_id["txn-pending"]["invoice_acquisition_status"]["primary_action"], "mark_income_status")
        self.assertFalse(any(payload["can_create_invoice"] for payload in by_id.values()))
        self.assertEqual(by_id["txn-cash"]["bank_transaction"]["effective_tag_label_path"], ["收入", "现金销售"])

    def test_pending_invoice_sql_projection_filters_income_rule_groups(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingIncomeProjectionConnection())

        requires_rows = builder._pending_invoice_rows(direction="income", filter_name="requires_invoice", month="2026-05")
        no_invoice_rows = builder._pending_invoice_rows(direction="income", filter_name="no_invoice_required", month="2026-05")
        cash_rows = builder._pending_invoice_rows(direction="income", filter_name="cash_income", month="2026-05")

        self.assertEqual([row["payload"]["id"] for row in requires_rows], ["txn-output", "txn-pending"])
        self.assertEqual(requires_rows[0]["payload"]["invoice_acquisition_status"]["code"], "income_invoiced")
        self.assertEqual([row["payload"]["id"] for row in no_invoice_rows], ["txn-no-invoice"])
        self.assertEqual([row["payload"]["id"] for row in cash_rows], ["txn-cash", "txn-manual"])

    def test_pending_invoice_sql_projection_uses_effective_category_fields_for_income_rules(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingEffectiveCategoryProjectionConnection(direction="income"))

        requires_rows = builder._pending_invoice_rows(direction="income", filter_name="requires_invoice", month="2026-05")
        cash_rows = builder._pending_invoice_rows(direction="income", filter_name="cash_income", month="2026-05")

        self.assertEqual([row["payload"]["id"] for row in requires_rows], ["txn-income-service", "txn-income-unknown"])
        self.assertEqual([row["payload"]["id"] for row in cash_rows], ["txn-income-cash"])
        self.assertEqual(requires_rows[0]["payload"]["invoice_acquisition_status"]["matched_rule"]["tag_label_path"], ["收入", "服务收入"])
        self.assertEqual(cash_rows[0]["payload"]["bank_transaction"]["effective_tag_code"], "cash_sale")

    def test_application_pending_invoice_invalidation_scopes_cover_income_filters(self) -> None:
        self.assertEqual(
            Application._pending_invoice_read_model_scope_keys(),
            [
                "expense:all",
                "expense:requires_invoice",
                "expense:bank_statement_as_invoice",
                "expense:no_invoice_required",
                "income:all",
                "income:requires_invoice",
                "income:no_invoice_required",
                "income:cash_income",
            ],
        )

    def test_refresh_handler_rebuilds_search_and_pending_scopes(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.search_rebuilt: list[str] = []
                self.pending_rebuilt: list[str] = []

            def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
                self.search_rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 1}

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.pending_rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 2}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        search_event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="search.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="search",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05"},
            attempts=1,
            status="processing",
        )
        pending_event = RuntimeQueueEvent(
            event_id="event-2",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:all",
            scope_type="pending_invoice",
            scope_key="expense:all",
            dedupe_key=None,
            payload={"scope_key": "expense:all"},
            attempts=1,
            status="processing",
        )

        self.assertEqual(service.handle_runtime_event(search_event)["row_count"], 1)
        self.assertEqual(service.handle_runtime_event(pending_event)["row_count"], 2)

        self.assertEqual(builder.search_rebuilt, ["2026-05"])
        self.assertEqual(builder.pending_rebuilt, ["expense:all"])
        self.assertEqual(
            queue.completed,
            [("tenant-a", "search", "2026-05"), ("tenant-a", "pending_invoice", "expense:all")],
        )

    def test_refresh_handler_skips_stale_search_source_version(self) -> None:
        class FakeBuilder:
            def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(f"stale event should not rebuild {scope_key}")

        class FakeQueue:
            def __init__(self) -> None:
                self.current_checks: list[tuple[str, str, str, object]] = []

            def read_model_refresh_is_current(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object,
            ) -> bool:
                self.current_checks.append((tenant_id, scope_type, scope_key, source_version))
                return False

        queue = FakeQueue()
        service = SearchPendingReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-stale",
            tenant_id="tenant-a",
            event_type="search.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="search",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 3},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(queue.current_checks, [("tenant-a", "search", "2026-05", 3)])
        self.assertEqual(
            result,
            {
                "scope_key": "2026-05",
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": 3,
            },
        )

    def test_refresh_handler_rejects_application_fallback_dependency(self) -> None:
        with self.assertRaisesRegex(ValueError, "projection_builder is required"):
            SearchPendingReadModelRefreshService(application=object(), queue_repository=QueueRecorder())

    def test_refresh_handler_expands_search_all_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def list_search_scope_shards(self, scope_key: str) -> list[str]:
                self.rebuilt.append(f"list:{scope_key}")
                return ["2026-05", "2026-04"]

            def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
                self.rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 1}

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="search.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="search",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05", "2026-04"], "row_count": 0})
        self.assertEqual(builder.rebuilt, ["list:all"])
        self.assertEqual(
            queue.refreshes,
            [("search", "2026-05", "search_all_shard"), ("search", "2026-04", "search_all_shard")],
        )
        self.assertEqual(queue.completed, [("tenant-a", "search", "all")])

    def test_refresh_handler_expands_search_all_through_search_producer_boundary(self) -> None:
        class FakeBuilder:
            def list_search_scope_shards(self, scope_key: str) -> list[str]:
                return ["2026-05", "2026-04"]

            def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        producer = FakeSearchRefreshProducer()
        service = SearchPendingReadModelRefreshService(
            projection_builder=FakeBuilder(),
            queue_repository=queue,
            search_read_model_refresh_producer=producer,
        )
        event = RuntimeQueueEvent(
            event_id="event-all-producer",
            tenant_id="tenant-a",
            event_type="search.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="search",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05", "2026-04"], "row_count": 0})
        self.assertEqual(producer.calls, [(["2026-05", "2026-04"], "search_all_shard")])
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(queue.completed, [("tenant-a", "search", "all")])

    def test_refresh_handler_expands_legacy_pending_scope_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def list_pending_invoice_scope_shards(self, scope_key: str) -> list[str]:
                self.rebuilt.append(f"list:{scope_key}")
                return ["expense:all:2026-05", "expense:all:2026-04"]

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-pending-all",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:all",
            scope_type="pending_invoice",
            scope_key="expense:all",
            dedupe_key=None,
            payload={"scope_key": "expense:all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "expense:all", "enqueued_scope_keys": ["expense:all:2026-05", "expense:all:2026-04"], "row_count": 0})
        self.assertEqual(builder.rebuilt, ["list:expense:all"])
        self.assertEqual(
            queue.refreshes,
            [
                ("pending_invoice", "expense:all:2026-05", "pending_invoice_month_shard"),
                ("pending_invoice", "expense:all:2026-04", "pending_invoice_month_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "pending_invoice", "expense:all")])

    def test_refresh_handler_expands_pending_filter_scope_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def list_pending_invoice_scope_shards(self, scope_key: str) -> list[str]:
                self.calls.append(f"list:{scope_key}")
                return ["expense:requires_invoice:2026-05", "expense:requires_invoice:2026-04"]

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.calls.append(f"rebuild:{scope_key}")
                return {"scope_key": scope_key, "row_count": 1}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-pending-requires",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:requires_invoice",
            scope_type="pending_invoice",
            scope_key="expense:requires_invoice",
            dedupe_key=None,
            payload={"scope_key": "expense:requires_invoice"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(
            result,
            {
                "scope_key": "expense:requires_invoice",
                "enqueued_scope_keys": ["expense:requires_invoice:2026-05", "expense:requires_invoice:2026-04"],
                "row_count": 0,
            },
        )
        self.assertEqual(builder.calls, ["list:expense:requires_invoice"])
        self.assertEqual(
            queue.refreshes,
            [
                ("pending_invoice", "expense:requires_invoice:2026-05", "pending_invoice_month_shard"),
                ("pending_invoice", "expense:requires_invoice:2026-04", "pending_invoice_month_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "pending_invoice", "expense:requires_invoice")])

    def test_refresh_handler_rebuilds_pending_filter_month_shard(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def list_pending_invoice_scope_shards(self, scope_key: str) -> list[str]:
                raise AssertionError(scope_key)

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.calls.append(scope_key)
                return {"scope_key": scope_key, "row_count": 1}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-pending-requires-month",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:requires_invoice:2026-05",
            scope_type="pending_invoice",
            scope_key="expense:requires_invoice:2026-05",
            dedupe_key=None,
            payload={"scope_key": "expense:requires_invoice:2026-05"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "expense:requires_invoice:2026-05", "row_count": 1})
        self.assertEqual(builder.calls, ["expense:requires_invoice:2026-05"])
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(queue.completed, [("tenant-a", "pending_invoice", "expense:requires_invoice:2026-05")])


if __name__ == "__main__":
    unittest.main()
