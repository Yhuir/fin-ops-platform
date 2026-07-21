from __future__ import annotations

from copy import deepcopy
import unittest

from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresInvoiceUsageCollectionReadModelRepository,
    PostgresReadModelRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    oa_pending_payment_coverage_only_source_versions,
)


class OaPendingPaymentReadModelQueryTests(unittest.TestCase):
    def test_coverage_only_scope_is_fresh_without_integration_or_relation_watermarks(self) -> None:
        base_versions = {"schema": 1}
        coverage_versions = {
            **base_versions,
            **oa_pending_payment_coverage_only_source_versions("2026-05"),
            "oa_pending_payment_relation_version": 0,
            "oa_pending_payment_bank_coverage_signature": "rows:2|digest:bank-coverage",
            "oa_pending_payment_input_invoice_coverage_signature": "rows:1|digest:invoice-coverage",
            "oa_pending_payment_event_source_version": 7,
        }
        connection = QueryStateConnection(
            [
                {
                    "scope_key": "2026-05",
                    "row_count": 0,
                    "generated_at": "2026-07-22T10:00:00+08:00",
                    "cache_status": "fresh",
                    "actual_source_versions": coverage_versions,
                    "source_status": None,
                    "source_snapshot_version": None,
                    "source_payload": None,
                    "pending_relation_version": None,
                    "dirty_status": "done",
                    "dirty_source_version": 7,
                    "outbox_blocking": False,
                }
            ]
        )
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        state = repository.oa_pending_payment_query_state(
            scope_key="all",
            tenant_id="default",
            base_source_versions=base_versions,
        )

        self.assertEqual(state["status"], "fresh")
        self.assertEqual(state["blocking_scope_keys"], [])
        self.assertNotIn("2026-05:source_snapshot_missing", state["stale_reasons"])
        self.assertNotIn("2026-05:pending_relation_version_missing", state["stale_reasons"])

    def test_real_oa_source_supersedes_coverage_only_vector(self) -> None:
        base_versions = {"schema": 1}
        actual_versions = {
            **base_versions,
            **oa_pending_payment_coverage_only_source_versions("2026-05"),
            "oa_pending_payment_relation_version": 0,
            "oa_pending_payment_bank_coverage_signature": "rows:2|digest:bank-coverage",
            "oa_pending_payment_input_invoice_coverage_signature": "rows:1|digest:invoice-coverage",
            "oa_pending_payment_event_source_version": 8,
        }
        row = _fresh_state_row(
            scope_key="2026-05",
            base_versions=base_versions,
            snapshot_version=4,
            event_source_version=8,
        )
        row["actual_source_versions"] = actual_versions
        repository = PostgresInvoiceUsageCollectionReadModelRepository(QueryStateConnection([row]))

        state = repository.oa_pending_payment_query_state(
            scope_key="2026-05",
            tenant_id="default",
            base_source_versions=base_versions,
        )

        self.assertEqual(state["status"], "refreshing")
        self.assertIn("2026-05:source_versions_mismatch", state["stale_reasons"])

    def test_failed_integration_watermark_does_not_accept_coverage_only_vector(self) -> None:
        base_versions = {"schema": 1}
        actual_versions = {
            **base_versions,
            **oa_pending_payment_coverage_only_source_versions("2026-05"),
            "oa_pending_payment_relation_version": 0,
            "oa_pending_payment_bank_coverage_signature": "rows:2|digest:bank-coverage",
            "oa_pending_payment_input_invoice_coverage_signature": "rows:1|digest:invoice-coverage",
            "oa_pending_payment_event_source_version": 8,
        }
        connection = QueryStateConnection(
            [
                {
                    "scope_key": "2026-05",
                    "row_count": 0,
                    "generated_at": "2026-07-22T10:00:00+08:00",
                    "cache_status": "fresh",
                    "actual_source_versions": actual_versions,
                    "source_status": "failed",
                    "source_snapshot_version": 4,
                    "source_payload": {},
                    "pending_relation_version": None,
                    "dirty_status": "done",
                    "dirty_source_version": 8,
                    "outbox_blocking": False,
                }
            ]
        )
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        state = repository.oa_pending_payment_query_state(
            scope_key="2026-05",
            tenant_id="default",
            base_source_versions=base_versions,
        )

        self.assertEqual(state["status"], "refreshing")
        self.assertIn("2026-05:source_snapshot_missing", state["stale_reasons"])
        self.assertIn("2026-05:source_versions_mismatch", state["stale_reasons"])

    def test_dynamic_source_state_is_fresh_only_for_exact_published_vector(self) -> None:
        base_versions = {"schema": 1}
        expected_versions = {
            "schema": 1,
            "oa_pending_payment_source_snapshot_version": 3,
            "completed_oa_signature": "completed-3",
            "in_progress_admission_signature": "admission-3",
            "payment_status_signature": "payment-3",
            "oa_pending_payment_source_signature": "source-3",
            "oa_pending_payment_relation_version": 4,
            "oa_pending_payment_bank_coverage_signature": "rows:2|digest:bank-3",
            "oa_pending_payment_input_invoice_coverage_signature": "rows:1|digest:invoice-3",
            "oa_pending_payment_event_source_version": 7,
        }
        state_row = {
            "scope_key": "2026-05",
            "row_count": 2,
            "generated_at": "2026-07-16T10:00:00+08:00",
            "cache_status": "fresh",
            "actual_source_versions": expected_versions,
            "source_status": "succeeded",
            "source_snapshot_version": 3,
            "source_payload": {
                "completed_oa_signature": "completed-3",
                "admission_signature": "admission-3",
                "payment_status_signature": "payment-3",
                "source_signature": "source-3",
            },
            "pending_relation_version": 4,
            "dirty_status": "done",
            "dirty_source_version": 7,
            "outbox_blocking": False,
        }
        connection = QueryStateConnection([state_row])
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        fresh = repository.oa_pending_payment_query_state(
            scope_key="2026-05",
            tenant_id="default",
            base_source_versions=base_versions,
        )
        stale_row = deepcopy(state_row)
        stale_row["actual_source_versions"] = {
            **expected_versions,
            "oa_pending_payment_event_source_version": 6,
        }
        connection.rows = [stale_row]
        stale = repository.oa_pending_payment_query_state(
            scope_key="2026-05",
            tenant_id="default",
            base_source_versions=base_versions,
        )

        self.assertEqual(fresh["status"], "fresh")
        self.assertEqual(fresh["blocking_scope_keys"], [])
        self.assertEqual(stale["status"], "refreshing")
        self.assertEqual(stale["blocking_scope_keys"], ["2026-05"])
        self.assertIn("2026-05:source_versions_mismatch", stale["stale_reasons"])
        self.assertNotEqual(fresh["version_token"], stale["version_token"])
        state_sql = connection.calls[0][0]
        target_inventory_sql = state_sql.split("select\n                target.scope_key", 1)[0]
        self.assertNotIn("select relation_scope.scope_key", target_inventory_sql)
        self.assertIn("dirty.status in ('pending', 'processing', 'failed')", target_inventory_sql)
        self.assertIn(
            "outbox.status in ('pending', 'processing', 'failed', 'dead_lettered')",
            target_inventory_sql,
        )
        self.assertNotIn("group by duplicate_row.row_id", state_sql)
        self.assertNotIn("having count(*) > 1", state_sql)
        self.assertNotIn("from app.bank_transactions", state_sql)
        self.assertNotIn("from app.invoices", state_sql)
        self.assertIn("'dead_lettered'", state_sql)
        self.assertIn(
            "order by dirty.source_version desc, dirty.updated_at desc, dirty.id desc",
            state_sql,
        )
        self.assertNotIn("read_model.workbench_relation_scopes", state_sql)

    def test_all_scope_query_state_leaves_duplicate_detection_to_page_audit(self) -> None:
        base_versions = {"schema": 1}
        duplicate_row = _fresh_state_row(
            scope_key="2026-05",
            base_versions=base_versions,
            snapshot_version=3,
            event_source_version=7,
        )
        repository = PostgresInvoiceUsageCollectionReadModelRepository(QueryStateConnection([duplicate_row]))

        payload = repository.oa_pending_payment_query_state(
            scope_key="all",
            tenant_id="default",
            base_source_versions=base_versions,
        )

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["blocking_scope_keys"], [])

    def test_all_scope_query_state_returns_only_versions_common_to_every_month(self) -> None:
        base_versions = {"schema": 1, "projection": "oa-v3"}
        rows = [
            _fresh_state_row(
                scope_key="2026-04",
                base_versions=base_versions,
                snapshot_version=3,
                event_source_version=7,
            ),
            _fresh_state_row(
                scope_key="2026-05",
                base_versions=base_versions,
                snapshot_version=4,
                event_source_version=8,
            ),
        ]
        connection = QueryStateConnection(rows)
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        payload = repository.oa_pending_payment_query_state(
            scope_key="all",
            tenant_id="default",
            base_source_versions=base_versions,
        )

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["blocking_scope_keys"], [])
        self.assertEqual(payload["source_versions"], base_versions)
        self.assertEqual(set(payload["source_versions_by_scope"]), {"2026-04", "2026-05"})

    def test_rows_use_one_statement_for_set_based_aggregate_and_bounded_page(self) -> None:
        connection = AggregateConnection()
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        payload = repository.list_oa_pending_payment_rows(
            month="2026-05",
            page=1,
            page_size=20,
            view_mode="completed",
        )

        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 20, "total": 1})
        self.assertEqual(payload["summary"]["statusCounts"], {"paid": 1})
        self.assertEqual(payload["statistics"]["oa_count"], 1)
        self.assertEqual(payload["filterOptions"]["bank_direction"][0]["label"], "支出")
        self.assertEqual(len(connection.fetch_one_calls), 1)
        self.assertEqual(len(connection.fetch_all_calls), 0)
        aggregate_sql = connection.fetch_one_calls[0][0].lower()
        self.assertIn("with base_rows as materialized", aggregate_sql)
        base_rows_sql = aggregate_sql.split("filtered_rows as materialized", 1)[0]
        self.assertNotIn("raw_payload", base_rows_sql)
        self.assertNotIn("select *", base_rows_sql)
        self.assertNotIn("payload", base_rows_sql)
        self.assertIn("cross join lateral unnest", aggregate_sql)
        self.assertNotIn("jsonb_array_elements", aggregate_sql)
        self.assertIn("paged_rows as materialized", aggregate_sql)
        self.assertIn("limit %s offset %s", aggregate_sql)
        self.assertIn("jsonb_agg(jsonb_build_object('payload', payload) order by row_order)", aggregate_sql)
        self.assertIn("payload - 'searchtext' - 'sourceversions' - 'source_versions'", aggregate_sql)
        self.assertNotIn("select payload, raw_payload", aggregate_sql)
        self.assertEqual(connection.fetch_one_calls[0][1][-2:], (20, 0))

    def test_lifecycle_source_rows_require_exact_fresh_month_scope(self) -> None:
        connection = LifecycleSourceConnection()
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        payload = repository.list_oa_pending_payment_lifecycle_source_rows(month="2026-05")

        self.assertEqual(payload["refresh_status"], "fresh")
        self.assertEqual(payload["source_versions"], {"oa_pending_payment_signature": "oa-v1"})
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(payload["rows"][0]["id"], "row-1")

    def test_lifecycle_source_rows_reject_missing_month_scope(self) -> None:
        connection = LifecycleSourceConnection(scope_exists=False)
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        payload = repository.list_oa_pending_payment_lifecycle_source_rows(month="2026-05")

        self.assertIsNone(payload)
        self.assertEqual(len(connection.fetch_one_calls), 1)

    def test_read_snapshot_sets_repeatable_read_before_any_query(self) -> None:
        connection = SnapshotConnection()
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        with repository.oa_pending_payment_read_snapshot() as snapshot:
            self.assertIsInstance(snapshot, PostgresInvoiceUsageCollectionReadModelRepository)

        self.assertEqual(
            connection.transaction_handle.executions,
            [("set transaction isolation level repeatable read read only", ())],
        )

    def test_composite_repository_exposes_oa_freshness_gate_and_snapshot(self) -> None:
        base_versions = {"schema": 1}
        state_row = _fresh_state_row(
            scope_key="2026-05",
            base_versions=base_versions,
            snapshot_version=3,
            event_source_version=7,
        )
        connection = QueryStateConnection([state_row])
        repository = PostgresReadModelRepository(connection)

        state = repository.oa_pending_payment_query_state(
            scope_key="2026-05",
            tenant_id="default",
            base_source_versions=base_versions,
        )
        with repository.oa_pending_payment_read_snapshot() as snapshot:
            snapshot_type = type(snapshot)

        self.assertEqual(state["status"], "fresh")
        self.assertIs(snapshot_type, PostgresInvoiceUsageCollectionReadModelRepository)


class QueryStateConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
        self.calls.append((sql, params))
        return deepcopy(self.rows)


def _fresh_state_row(
    *,
    scope_key: str,
    base_versions: dict[str, object],
    snapshot_version: int,
    event_source_version: int,
) -> dict[str, object]:
    source_payload = {
        "completed_oa_signature": f"completed-{snapshot_version}",
        "admission_signature": f"admission-{snapshot_version}",
        "payment_status_signature": f"payment-{snapshot_version}",
        "source_signature": f"source-{snapshot_version}",
    }
    actual_versions = {
        **base_versions,
        "oa_pending_payment_source_snapshot_version": snapshot_version,
        "completed_oa_signature": source_payload["completed_oa_signature"],
        "in_progress_admission_signature": source_payload["admission_signature"],
        "payment_status_signature": source_payload["payment_status_signature"],
        "oa_pending_payment_source_signature": source_payload["source_signature"],
        "oa_pending_payment_relation_version": snapshot_version,
        "oa_pending_payment_bank_coverage_signature": f"rows:1|digest:bank-{snapshot_version}",
        "oa_pending_payment_input_invoice_coverage_signature": (
            f"rows:1|digest:invoice-{snapshot_version}"
        ),
        "oa_pending_payment_event_source_version": event_source_version,
    }
    return {
        "scope_key": scope_key,
        "row_count": 1,
        "generated_at": "2026-07-16T10:00:00+08:00",
        "cache_status": "fresh",
        "actual_source_versions": actual_versions,
        "source_status": "succeeded",
        "source_snapshot_version": snapshot_version,
        "source_payload": source_payload,
        "pending_relation_version": snapshot_version,
        "dirty_status": "done",
        "dirty_source_version": event_source_version,
        "outbox_blocking": False,
    }


class AggregateConnection:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...]) -> dict[str, object]:
        self.fetch_one_calls.append((sql, params))
        return {
            "count": 1,
            "oa_amount_total": "100.00",
            "bank_paid_total": "100.00",
            "completed_count": 1,
            "in_progress_count": 0,
            "status_counts": {"paid": 1},
            "filter_options": {
                "bank_direction": [{"value": "outflow", "label": "outflow", "count": 1}],
            },
            "page_statistics": [
                {
                    "oa_count": 1,
                    "bank_transaction_count": 1,
                    "input_invoice_count": 1,
                    "paid_oa_count": 1,
                    "completed_oa_count": 1,
                    "in_progress_oa_count": 0,
                    "expense_transaction_count": 1,
                    "income_transaction_count": 0,
                    "unpaid_oa_count": 0,
                    "linked_bank_oa_count": 1,
                    "linked_input_invoice_oa_count": 1,
                }
            ],
            "rows": [{"payload": {"id": "row-1"}}],
        }

    def fetch_all(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return [{"payload": {"id": "row-1"}, "raw_payload": {}}]


class LifecycleSourceConnection(AggregateConnection):
    def __init__(self, *, scope_exists: bool = True) -> None:
        super().__init__()
        self.scope_exists = scope_exists

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((sql, params))
        if "with base_rows as materialized" in normalized:
            return {
                "count": 1,
                "oa_amount_total": "100.00",
                "bank_paid_total": "100.00",
                "completed_count": 1,
                "in_progress_count": 0,
                "status_counts": {"paid": 1},
                "filter_options": {},
                "page_statistics": [],
                "rows": [{"payload": {"id": "row-1"}}],
            }
        if "from read_model.oa_pending_payment_scopes" in normalized:
            if not self.scope_exists:
                return None
            return {
                "scope_key": "2026-05",
                "source_versions": {"oa_pending_payment_signature": "oa-v1"},
            }
        if "from job.read_model_dirty_scopes" in normalized:
            return None
        return {
            "count": 1,
            "oa_amount_total": "100.00",
            "bank_paid_total": "100.00",
            "completed_count": 1,
            "in_progress_count": 0,
            "status_counts": {"paid": 1},
            "filter_options": {},
            "rows": [{"payload": {"id": "row-1"}}],
        }


class SnapshotTransaction:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.executions.append((sql, params))


class SnapshotContext:
    def __init__(self, transaction: SnapshotTransaction) -> None:
        self.transaction = transaction

    def __enter__(self) -> SnapshotTransaction:
        return self.transaction

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> bool:
        return False


class SnapshotConnection:
    def __init__(self) -> None:
        self.transaction_handle = SnapshotTransaction()

    def transaction(self) -> SnapshotContext:
        return SnapshotContext(self.transaction_handle)


if __name__ == "__main__":
    unittest.main()
