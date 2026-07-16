from __future__ import annotations

from copy import deepcopy
import unittest

from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresInvoiceUsageCollectionReadModelRepository,
    PostgresReadModelRepository,
)


class OaPendingPaymentReadModelQueryTests(unittest.TestCase):
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
            "oa_pending_payment_event_source_version": 7,
            "workbench_relation_source_versions": {"relation": 2},
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
            "relation_scope_exists": True,
            "relation_cache_status": "fresh",
            "relation_source_versions": {"relation": 2},
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
        self.assertIn("group by duplicate_row.row_id", state_sql)
        self.assertIn("having count(*) > 1", state_sql)
        self.assertIn("'dead_lettered'", state_sql)

    def test_all_scope_query_state_fails_closed_on_cross_scope_duplicate_row_identity(self) -> None:
        base_versions = {"schema": 1}
        duplicate_row = _fresh_state_row(
            scope_key="2026-05",
            base_versions=base_versions,
            snapshot_version=3,
            event_source_version=7,
        )
        duplicate_row["duplicate_row_identity"] = True
        repository = PostgresInvoiceUsageCollectionReadModelRepository(QueryStateConnection([duplicate_row]))

        payload = repository.oa_pending_payment_query_state(
            scope_key="all",
            tenant_id="default",
            base_source_versions=base_versions,
        )

        self.assertEqual(payload["status"], "refreshing")
        self.assertEqual(payload["blocking_scope_keys"], ["2026-05"])
        self.assertIn("all:duplicate_row_identity", payload["stale_reasons"])

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

    def test_rows_use_one_set_based_aggregate_and_one_bounded_page_query(self) -> None:
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
        self.assertEqual(payload["filterOptions"]["bank_direction"][0]["label"], "支出")
        self.assertEqual(len(connection.fetch_one_calls), 1)
        self.assertEqual(len(connection.fetch_all_calls), 1)
        aggregate_sql = connection.fetch_one_calls[0][0].lower()
        self.assertIn("with base_rows as materialized", aggregate_sql)
        self.assertNotIn("raw_payload", aggregate_sql)
        base_rows_sql = aggregate_sql.split("filtered_rows as materialized", 1)[0]
        self.assertNotIn("select *", base_rows_sql)
        self.assertNotIn("payload", base_rows_sql)
        self.assertIn("cross join lateral unnest", aggregate_sql)
        self.assertNotIn("jsonb_array_elements", aggregate_sql)
        page_sql = connection.fetch_all_calls[0][0]
        self.assertIn("payload - 'searchText' - 'sourceVersions' - 'source_versions'", page_sql)
        self.assertNotIn("select payload, raw_payload", page_sql.lower())

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
    relation_versions = {"relation": snapshot_version}
    actual_versions = {
        **base_versions,
        "oa_pending_payment_source_snapshot_version": snapshot_version,
        "completed_oa_signature": source_payload["completed_oa_signature"],
        "in_progress_admission_signature": source_payload["admission_signature"],
        "payment_status_signature": source_payload["payment_status_signature"],
        "oa_pending_payment_source_signature": source_payload["source_signature"],
        "oa_pending_payment_relation_version": snapshot_version,
        "oa_pending_payment_event_source_version": event_source_version,
        "workbench_relation_source_versions": relation_versions,
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
        "relation_scope_exists": True,
        "relation_cache_status": "fresh",
        "relation_source_versions": relation_versions,
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
        }

    def fetch_all(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return [{"payload": {"id": "row-1"}, "raw_payload": {}}]


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
