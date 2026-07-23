from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentSourceSnapshotRepository,
    _signature,
    oa_pending_payment_workbench_relation_versions_by_scope,
)


class OaPendingPaymentSourceSnapshotRepositoryTests(unittest.TestCase):
    def test_workbench_relation_versions_are_set_based_and_scope_exact(self) -> None:
        connection = RelationVersionConnection()

        versions = oa_pending_payment_workbench_relation_versions_by_scope(
            connection,
            scope_keys=["2026-06", "invalid", "2026-05", "2026-06"],
        )

        self.assertEqual(
            versions,
            {
                "2026-05": {
                    "oa_pending_payment_workbench_pair_relations_updated_at": "",
                },
                "2026-06": {
                    "oa_pending_payment_workbench_pair_relations_updated_at": (
                        "2026-07-23 22:55:53.931405+08"
                    ),
                },
            },
        )
        self.assertEqual(connection.params, (["2026-06", "2026-05"],))
        self.assertIn("source.row_id = any(relation.row_ids)", connection.sql)
        self.assertIn("source.scope_month = to_date(requested.scope_key, 'YYYY-MM')", connection.sql)

    def test_complete_snapshot_replaces_status_and_admission_in_one_canonical_transaction(self) -> None:
        connection = FakeConnection()
        pending_relations = FakePendingRelationRepository()
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=pending_relations,
        )

        result = repository.replace_authoritative_snapshot(
            scope_key="2026-06",
            completed_projection_records=[],
            admission_records=[_oa("oa-pay-row-1", "2026-06", workflow_status="in_progress", flow_id="flow-1")],
            payment_statuses={"flow-1": OAPaymentStatusRecord(flow_id="flow-1", pay_status=0)},
        )

        self.assertEqual(result.completed_projection_changed_scopes, ())
        self.assertEqual(result.oa_pending_payment_changed_scopes, ("2026-06",))
        self.assertEqual(result.payment_status_count, 1)
        self.assertEqual(result.admission_count, 1)
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertEqual(pending_relations.calls[0]["admitted_oa_row_ids"], ["oa-pay-row-1"])
        self.assertIs(pending_relations.calls[0]["transaction"], connection.transaction_handle)
        self.assertEqual(len(pending_relations.ensure_calls), 1)
        self.assertEqual(pending_relations.ensure_calls[0]["scope_key"], "2026-06")
        self.assertIs(pending_relations.ensure_calls[0]["transaction"], connection.transaction_handle)
        executed_sql = "\n".join(sql for sql, _params in connection.transaction_handle.executions)
        self.assertIn("delete from app.oa_pending_payment_status_snapshots", executed_sql)
        self.assertIn("insert into app.oa_pending_payment_status_snapshots", executed_sql)
        self.assertIn("(item.scope_month || '-01')::date", executed_sql)
        self.assertIn("is distinct from", executed_sql)
        self.assertIn("delete from app.oa_pending_payment_admissions", executed_sql)
        self.assertIn("insert into app.oa_pending_payment_admissions", executed_sql)
        self.assertIn("insert into app.oa_sync_watermarks", executed_sql)
        self.assertNotIn("job.read_model_dirty_scopes", executed_sql)
        self.assertNotIn("job.outbox_events", executed_sql)

    def test_authoritative_empty_snapshot_reports_removed_rows_old_month(self) -> None:
        connection = FakeConnection(
            status_rows=[
                {
                    "flow_id": "deleted-flow",
                    "pay_status": 0,
                    "scope_month": "2026-05",
                    "source_signature": "old-status",
                }
            ],
            admission_rows=[
                {
                    "scope_key": "2026-05",
                    "oa_id": "oa-pay-deleted",
                    "source_signature": "old-admission",
                    "source_payload": {"id": "oa-pay-deleted"},
                }
            ],
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=FakePendingRelationRepository(),
        )

        result = repository.replace_authoritative_snapshot(
            scope_key="all",
            completed_projection_records=[],
            admission_records=[],
            payment_statuses={},
        )

        self.assertEqual(result.completed_projection_changed_scopes, ())
        self.assertEqual(result.oa_pending_payment_changed_scopes, ("2026-05",))
        self.assertEqual(result.payment_status_count, 0)
        self.assertEqual(result.admission_count, 0)

    def test_completed_projection_change_is_reported_without_page_refresh_side_effects(self) -> None:
        connection = FakeConnection()
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=FakePendingRelationRepository(),
        )
        completed = _oa("oa-pay-row-1", "2026-06", workflow_status="completed", flow_id="flow-1")

        result = repository.commit_authoritative_snapshot(
            scope_key="2026-06",
            projection_records=[completed],
            admission_records=[completed],
            payment_statuses={"flow-1": OAPaymentStatusRecord(flow_id="flow-1", pay_status=0)},
        )

        self.assertEqual(result.completed_projection_changed_scopes, ("2026-06",))
        self.assertEqual(result.oa_pending_payment_changed_scopes, ("2026-06",))
        self.assertFalse(hasattr(repository, "_queue_repository"))

    def test_payment_status_only_change_does_not_report_completed_projection_change(self) -> None:
        connection = FakeConnection(
            status_rows=[
                {
                    "flow_id": "flow-1",
                    "pay_status": 0,
                    "scope_month": "2026-06",
                    "source_signature": "old-status",
                }
            ],
            watermark_rows=[_watermark("2026-06", completed_signature=_signature([]))],
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=FakePendingRelationRepository(),
        )

        result = repository.replace_authoritative_snapshot(
            scope_key="2026-06",
            completed_projection_records=[],
            admission_records=[],
            payment_statuses={"flow-1": OAPaymentStatusRecord(flow_id="flow-1", pay_status=1)},
        )

        self.assertEqual(result.completed_projection_changed_scopes, ())
        self.assertEqual(result.oa_pending_payment_changed_scopes, ("2026-06",))

    def test_removed_completed_only_scope_uses_old_watermark_and_reports_shared_projection_change(self) -> None:
        connection = FakeConnection(watermark_rows=[_watermark("2026-05")])
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=FakePendingRelationRepository(),
        )

        result = repository.replace_authoritative_snapshot(
            scope_key="all",
            completed_projection_records=[],
            admission_records=[],
            payment_statuses={},
        )

        self.assertEqual(result.completed_projection_changed_scopes, ("2026-05",))
        self.assertEqual(result.oa_pending_payment_changed_scopes, ("2026-05",))

    def test_paid_writeback_updates_snapshot_watermark_without_downstream_outbox(self) -> None:
        connection = FakeConnection(
            status_rows=[
                {
                    "flow_id": "flow-1",
                    "pay_status": 0,
                    "scope_month": "2026-06",
                    "source_signature": "pending-signature",
                }
            ],
            watermark_rows=[_watermark("2026-06")],
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=FakePendingRelationRepository(),
        )

        result = repository.record_paid_statuses(
            records=[_oa("oa-pay-row-1", "2026-06", workflow_status="completed", flow_id="flow-1")]
        )

        self.assertEqual(result.oa_pending_payment_changed_scopes, ("2026-06",))
        executed_sql = "\n".join(sql for sql, _params in connection.transaction_handle.executions)
        self.assertIn("insert into app.oa_pending_payment_status_snapshots", executed_sql)
        self.assertIn("(item.scope_month || '-01')::date", executed_sql)
        self.assertIn("insert into app.oa_sync_watermarks", executed_sql)
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)

    def test_paid_writeback_is_idempotent_when_snapshot_is_already_paid(self) -> None:
        connection = FakeConnection(
            status_rows=[
                {
                    "flow_id": "flow-1",
                    "pay_status": 1,
                    "scope_month": "2026-06",
                    "source_signature": "paid-signature",
                }
            ]
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=FakePendingRelationRepository(),
        )

        result = repository.record_paid_statuses(
            records=[_oa("oa-pay-row-1", "2026-06", workflow_status="completed", flow_id="flow-1")]
        )

        self.assertEqual(result.oa_pending_payment_changed_scopes, ())
        self.assertEqual(connection.transaction_handle.executions, [])
        self.assertTrue(connection.committed)

    def test_paid_writeback_does_not_require_a_downstream_queue_dependency(self) -> None:
        connection = FakeConnection(
            status_rows=[
                {
                    "flow_id": "flow-1",
                    "pay_status": 0,
                    "scope_month": "2026-06",
                    "source_signature": "pending-signature",
                }
            ],
            watermark_rows=[_watermark("2026-06")],
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=FakePendingRelationRepository(),
        )

        result = repository.record_paid_statuses(
            records=[_oa("oa-pay-row-1", "2026-06", workflow_status="completed", flow_id="flow-1")]
        )

        self.assertEqual(result.oa_pending_payment_changed_scopes, ("2026-06",))
        self.assertFalse(hasattr(repository, "_queue_repository"))
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)

    def test_paid_writeback_fails_fast_when_authoritative_snapshot_is_not_initialized(self) -> None:
        connection = FakeConnection(
            status_rows=[
                {
                    "flow_id": "flow-1",
                    "pay_status": 0,
                    "scope_month": "2026-06",
                    "source_signature": "pending-signature",
                }
            ]
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=FakePendingRelationRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "not initialized for scopes: 2026-06"):
            repository.record_paid_statuses(
                records=[_oa("oa-pay-row-1", "2026-06", workflow_status="completed", flow_id="flow-1")]
            )

        self.assertEqual(connection.transaction_handle.executions, [])
        self.assertFalse(connection.committed)
        self.assertTrue(connection.rolled_back)

    def test_invalid_payment_status_aborts_before_transaction_writes(self) -> None:
        connection = FakeConnection()
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            pending_relation_repository=FakePendingRelationRepository(),
        )

        with self.assertRaisesRegex(ValueError, "invalid pay_status"):
            repository.replace_authoritative_snapshot(
                scope_key="2026-06",
                completed_projection_records=[],
                admission_records=[],
                payment_statuses={"flow-1": {"flow_id": "flow-1", "pay_status": "bad"}},  # type: ignore[dict-item]
            )

        self.assertEqual(connection.transaction_count, 0)


class FakeTransaction:
    def __init__(
        self,
        *,
        status_rows: list[dict[str, object]],
        admission_rows: list[dict[str, object]],
        watermark_rows: list[dict[str, object]],
    ) -> None:
        self.status_rows = list(status_rows)
        self.admission_rows = list(admission_rows)
        self.watermark_rows = list(watermark_rows)
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, _params: tuple[object, ...]) -> dict[str, object] | None:
        if "insert into app.oa_applications" in sql:
            self.executions.append((sql, _params))
            return {"application_id": "00000000-0000-0000-0000-000000000001"}
        raise AssertionError(f"Unexpected query: {sql}")

    def fetch_all(self, sql: str, _params: tuple[object, ...]) -> list[dict[str, object]]:
        if "from app.oa_pending_payment_status_snapshots" in sql:
            return list(self.status_rows)
        if "from app.oa_pending_payment_admissions" in sql:
            return list(self.admission_rows)
        if "from app.oa_sync_watermarks" in sql:
            return list(self.watermark_rows)
        if "app.oa_applications" in sql:
            return []
        raise AssertionError(f"Unexpected query: {sql}")

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executions.append((sql, params))


class FakeTransactionContext:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> FakeTransaction:
        return self.connection.transaction_handle

    def __exit__(self, exc_type: object, _exc: object, _traceback: object) -> bool:
        if exc_type is None:
            self.connection.committed = True
        else:
            self.connection.rolled_back = True
        return False


class FakeConnection:
    def __init__(
        self,
        *,
        status_rows: list[dict[str, object]] | None = None,
        admission_rows: list[dict[str, object]] | None = None,
        watermark_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.transaction_handle = FakeTransaction(
            status_rows=list(status_rows or []),
            admission_rows=list(admission_rows or []),
            watermark_rows=list(watermark_rows or []),
        )
        self.transaction_count = 0
        self.committed = False
        self.rolled_back = False

    def transaction(self) -> FakeTransactionContext:
        self.transaction_count += 1
        return FakeTransactionContext(self)


class RelationVersionConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[object, ...] = ()

    def fetch_all(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
        self.sql = sql
        self.params = params
        return [
            {
                "scope_key": "2026-05",
                "relation_updated_at": "",
            },
            {
                "scope_key": "2026-06",
                "relation_updated_at": "2026-07-23 22:55:53.931405+08",
            },
        ]


class FakePendingRelationRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.ensure_calls: list[dict[str, object]] = []

    def cancel_active_relations_missing_oa_admission(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"changed_relation_ids": [], "affected_months": []}

    def ensure_scope_source_version(self, **kwargs: object) -> None:
        self.ensure_calls.append(dict(kwargs))


def _oa(row_id: str, month: str, *, workflow_status: str, flow_id: str) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=row_id,
        month=month,
        section="unpaired",
        case_id=None,
        applicant="测试申请人",
        project_name="测试项目",
        apply_type="支付申请",
        amount="100.00",
        counterparty_name="测试供应商",
        reason="测试付款",
        relation_code="pending_match",
        relation_label="待找流水与发票",
        relation_tone="warn",
        workflow_status=workflow_status,
        detail_fields={"Mongo文档ID": flow_id},
    )


def _watermark(scope_key: str, *, completed_signature: str = "completed-signature") -> dict[str, object]:
    return {
        "sync_key": f"oa_pending_payment_source:default:{scope_key}",
        "payload": {
            "scope_key": scope_key,
            "completed_oa_signature": completed_signature,
            "admission_signature": "admission-signature",
            "payment_status_signature": "pending-status-signature",
            "source_signature": "source-signature",
            "admission_count": 0,
            "payment_status_count": 1,
        },
    }


if __name__ == "__main__":
    unittest.main()
