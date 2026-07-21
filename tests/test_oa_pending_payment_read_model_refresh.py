from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from fin_ops_platform.services.oa_pending_payment_read_model_refresh import (
    OaPendingPaymentReadModelRefreshService,
)
from fin_ops_platform.services.oa_pending_payment_sql_projection import (
    OaPendingPaymentSqlProjectionBuilder,
    _oa_pending_payment_statistics,
)
from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresInvoiceUsageCollectionReadModelRepository,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class OaPendingPaymentReadModelRefreshTests(unittest.TestCase):
    def test_all_scope_fans_out_month_shards_and_completes_parent_with_source_version(self) -> None:
        builder = FakeProjector(shards=["2026-05"])
        queue = FakeQueue()
        service = OaPendingPaymentReadModelRefreshService(projection_builder=builder, queue_repository=queue)

        result = service.handle_runtime_event(_event("all", source_version=9))

        self.assertEqual(
            result,
            {
                "scope_key": "all",
                "source_version": 9,
                "enqueued_scope_keys": ["2026-05"],
                "row_count": 0,
            },
        )
        self.assertEqual(builder.pruned, ["2026-05"])
        self.assertEqual(builder.list_scope_calls, [("all", "tenant-a")])
        self.assertEqual(queue.refreshes, [("oa_pending_payment", "2026-05", "oa_pending_payment_month_shard")])
        self.assertEqual(queue.completed, [("tenant-a", "oa_pending_payment", "all", 9)])

    def test_stale_event_is_rejected_before_projector_reads(self) -> None:
        builder = FakeProjector()
        queue = FakeQueue(current=False)
        service = OaPendingPaymentReadModelRefreshService(projection_builder=builder, queue_repository=queue)

        result = service.handle_runtime_event(_event("2026-05", source_version=9))

        self.assertEqual(result["skip_reason"], "stale_source_version")
        self.assertEqual(builder.rebuilds, [])
        self.assertEqual(queue.completed, [])

    def test_atomic_publish_that_loses_cas_does_not_clear_new_dirty_version(self) -> None:
        builder = FakeProjector(published=False)
        queue = FakeQueue()
        service = OaPendingPaymentReadModelRefreshService(projection_builder=builder, queue_repository=queue)

        result = service.handle_runtime_event(_event("2026-05", source_version=9))

        self.assertFalse(result["published"])
        self.assertEqual(result["skip_reason"], "superseded_before_publish")
        self.assertEqual(queue.completed, [])

    def test_month_publish_passes_tenant_event_version_and_force_contract(self) -> None:
        builder = FakeProjector()
        queue = FakeQueue()
        service = OaPendingPaymentReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = _event("2026-05", source_version=11)
        event.payload["metadata"] = {"force_refresh": True}

        result = service.handle_runtime_event(event)

        self.assertTrue(result["published"])
        self.assertEqual(builder.rebuilds, [("2026-05", "tenant-a", 11, True)])
        self.assertEqual(queue.completed, [("tenant-a", "oa_pending_payment", "2026-05", 11)])

    def test_oa_projector_module_has_no_external_oa_or_mysql_dependencies(self) -> None:
        source_path = Path("backend/src/fin_ops_platform/services/oa_pending_payment_sql_projection.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden_fragments = (
            "mongo",
            "mysql",
            "oa_sync_source_adapter",
            "oa_payment_admitted_projection",
            "oa_pending_payment_service",
            "workbench_relation_read_facade",
        )

        self.assertFalse(
            {
                module
                for module in imported_modules
                if any(fragment in module.lower() for fragment in forbidden_fragments)
            }
        )

    def test_oa_projector_has_no_workbench_read_model_freshness_dependency(self) -> None:
        source = Path(
            "backend/src/fin_ops_platform/services/oa_pending_payment_sql_projection.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("WorkbenchRelationReadFacade", source)
        self.assertNotIn("workbench_relation_read_model_not_fresh", source)
        self.assertNotIn("workbench_relation_source_versions", source)


class OaPendingPaymentSqlProjectionBuilderTests(unittest.TestCase):
    def test_statistics_publish_full_page_inventory_counts_and_membership_digests(self) -> None:
        connection = CoverageConnection()

        statistics, source_versions = _oa_pending_payment_statistics(
            connection,
            scope_key="2026-05",
            completed_records=[SimpleNamespace(id="oa-1")],
            in_progress_records=[],
            rows=[],
        )

        self.assertEqual(statistics["bank_transaction_count"], 900)
        self.assertEqual(statistics["expense_transaction_count"], 500)
        self.assertEqual(statistics["income_transaction_count"], 400)
        self.assertEqual(statistics["input_invoice_count"], 800)
        self.assertEqual(
            source_versions["oa_pending_payment_bank_coverage_signature"],
            "rows:900|digest:bank-membership",
        )
        self.assertEqual(
            source_versions["oa_pending_payment_input_invoice_coverage_signature"],
            "rows:800|digest:invoice-membership",
        )
        coverage_sql = connection.fetch_one_calls[0][0].lower()
        self.assertIn("coalesce(bank.txn_direction, '')", coverage_sql)
        self.assertIn("coalesce(invoice.invoice_type, '')", coverage_sql)
        self.assertIn("order by coalesce(bank.legacy_mongo_id, bank.id::text)", coverage_sql)
        self.assertIn("order by coalesce(invoice.legacy_mongo_id, invoice.id::text)", coverage_sql)

    def test_rebuild_uses_atomic_repository_publish_with_event_version(self) -> None:
        connection = CallbackConnection()
        read_model_repository = AtomicReadModelRepository()
        builder = TestProjectionBuilder(connection=connection, read_model_repository=read_model_repository)

        result = builder.rebuild_scope(
            "2026-05",
            tenant_id="tenant-a",
            source_version=17,
        )

        self.assertTrue(result["published"])
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(
            read_model_repository.publish_calls,
            [
                {
                    "tenant_id": "tenant-a",
                    "scope_key": "2026-05",
                    "source_version": 17,
                    "rows": [{"id": "row-1"}],
                    "source_versions": {
                        "source": "new",
                        "oa_pending_payment_event_source_version": 17,
                    },
                    "statistics": {"oa_count": 1},
                }
            ],
        )

    def test_repository_cas_publish_rejects_superseded_event_without_replacing_rows(self) -> None:
        connection = CasConnection(current_source_version=18)
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        published = repository.publish_oa_pending_payment_rows(
            tenant_id="tenant-a",
            scope_key="2026-05",
            source_version=17,
            rows=[],
            source_versions={"source": "old"},
        )

        self.assertFalse(published)
        self.assertEqual(connection.executions, [])

    def test_repository_cas_publish_replaces_empty_scope_and_metadata_atomically(self) -> None:
        connection = CasConnection(current_source_version=17)
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        published = repository.publish_oa_pending_payment_rows(
            tenant_id="tenant-a",
            scope_key="2026-05",
            source_version=17,
            rows=[],
            source_versions={"source": "new"},
        )

        self.assertTrue(published)
        executed_sql = "\n".join(sql for sql, _params in connection.executions)
        self.assertIn("delete from read_model.oa_pending_payment_rows where scope_key", executed_sql)
        self.assertIn("insert into read_model.oa_pending_payment_scopes", executed_sql)

    def test_repository_publish_uses_one_values_batch_for_scope_rows(self) -> None:
        connection = CasConnection(current_source_version=17)
        repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)

        published = repository.publish_oa_pending_payment_rows(
            tenant_id="tenant-a",
            scope_key="2026-05",
            source_version=17,
            rows=[
                {
                    "id": "row-1",
                    "oa": {"id": "oa-1", "month": "2026-05", "workflowStatus": "completed"},
                    "paymentStatus": {"code": "unpaid", "label": "未支付"},
                    "bankTransaction": {},
                    "invoice": {},
                }
            ],
            source_versions={"source": "new"},
        )

        self.assertTrue(published)
        self.assertEqual(len(connection.batch_executions), 1)
        batch_sql, batch_params = connection.batch_executions[0]
        self.assertIn("insert into read_model.oa_pending_payment_rows", batch_sql)
        self.assertEqual(len(batch_params), 1)
        self.assertEqual(len(batch_params[0]), 30)


class CoverageConnection:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...]) -> dict[str, object]:
        self.fetch_one_calls.append((sql, params))
        return {
            "bank_transaction_count": 900,
            "expense_bank_transaction_count": 500,
            "income_bank_transaction_count": 400,
            "bank_membership_digest": "bank-membership",
            "input_invoice_count": 800,
            "input_invoice_membership_digest": "invoice-membership",
        }


class TestProjectionBuilder(OaPendingPaymentSqlProjectionBuilder):
    @staticmethod
    def _expected_source_versions(
        _connection: object,
        *,
        scope_key: str,
        tenant_id: str,
    ) -> dict[str, object]:
        del scope_key, tenant_id
        return {"source": "new"}

    def _build_scope_snapshot(
        self,
        _connection: object,
        *,
        scope_key: str,
        tenant_id: str,
    ) -> dict[str, object]:
        del scope_key, tenant_id
        return {
            "rows": [{"id": "row-1"}],
            "source_versions": {"source": "new"},
            "statistics": {"oa_count": 1},
        }


class AtomicReadModelRepository:
    def __init__(self) -> None:
        self.publish_calls: list[dict[str, object]] = []

    def list_oa_pending_payment_rows(self, **_kwargs: object) -> dict[str, object]:
        return {"rows": [], "pagination": {"total": 0}, "source_versions": {"source": "old"}}

    def publish_oa_pending_payment_rows(self, **kwargs: object) -> bool:
        self.publish_calls.append(dict(kwargs))
        return True


class CallbackConnection:
    def transaction(self) -> "CallbackConnection":
        return self

    def __enter__(self) -> "CallbackConnection":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> bool:
        return False


class CasConnection(CallbackConnection):
    def __init__(self, *, current_source_version: int) -> None:
        self.current_source_version = current_source_version
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.batch_executions: list[tuple[str, list[tuple[object, ...]]]] = []

    def fetch_one(self, sql: str, _params: tuple[object, ...]) -> dict[str, object]:
        if "from job.read_model_dirty_scopes" in sql:
            return {"source_version": self.current_source_version}
        raise AssertionError(f"Unexpected query: {sql}")

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executions.append((sql, params))

    def execute_many_values(self, sql: str, params: list[tuple[object, ...]]) -> int:
        self.batch_executions.append((sql, params))
        return len(params)


class FakeProjector:
    def __init__(self, *, shards: list[str] | None = None, published: bool = True) -> None:
        self.shards = list(shards or [])
        self.published = published
        self.pruned: list[str] = []
        self.rebuilds: list[tuple[str, str, int, bool]] = []
        self.list_scope_calls: list[tuple[str, str]] = []

    def list_scope_shards(self, scope_key: str, *, tenant_id: str) -> list[str]:
        self.list_scope_calls.append((scope_key, tenant_id))
        return list(self.shards)

    def prune_scope_shards(self, scope_keys: list[str]) -> None:
        self.pruned = list(scope_keys)

    def rebuild_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
        force_refresh: bool,
    ) -> dict[str, object]:
        self.rebuilds.append((scope_key, tenant_id, source_version, force_refresh))
        if not self.published:
            return {
                "scope_key": scope_key,
                "published": False,
                "skipped": True,
                "skip_reason": "superseded_before_publish",
            }
        return {"scope_key": scope_key, "row_count": 1, "published": True}


class FakeQueue:
    def __init__(self, *, current: bool = True) -> None:
        self.current = current
        self.refreshes: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str, str, int]] = []

    def read_model_refresh_is_current(self, **_kwargs: object) -> bool:
        return self.current

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str, **_kwargs: object) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        source_version: int,
    ) -> None:
        self.completed.append((tenant_id, scope_type, scope_key, source_version))


def _event(scope_key: str, *, source_version: int) -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id=f"event-{scope_key}",
        tenant_id="tenant-a",
        event_type="oa_pending_payment.read_model.refresh",
        aggregate_type="read_model",
        aggregate_id=scope_key,
        scope_type="oa_pending_payment",
        scope_key=scope_key,
        dedupe_key=None,
        payload={"scope_key": scope_key},
        attempts=1,
        status="processing",
        source_version=source_version,
    )


if __name__ == "__main__":
    unittest.main()
