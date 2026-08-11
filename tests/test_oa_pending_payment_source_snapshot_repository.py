from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentSourceSnapshotRepository,
    _signature,
)


class OaPendingPaymentSourceSnapshotRepositoryTests(unittest.TestCase):
    def test_complete_snapshot_replaces_status_and_admission_in_one_canonical_transaction(self) -> None:
        connection = FakeConnection()
        relation_commands = FakeRelationCommandService()
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: relation_commands,
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
        self.assertEqual(relation_commands.calls, [])
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
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
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
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
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

    def test_commit_removes_relation_member_when_completed_oa_disappears_from_both_sources(self) -> None:
        connection = FakeConnection(
            application_delete_results=[[{"row_id": "oa-completed-gone"}], []]
        )
        relation_commands = FakeRelationCommandService()
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: relation_commands,
        )

        result = repository.commit_authoritative_snapshot(
            scope_key="2026-06",
            projection_records=[],
            admission_records=[],
            payment_statuses={},
        )

        self.assertEqual(result.removed_stale_completed_count, 1)
        self.assertEqual(relation_commands.calls[0]["row_ids"], ["oa-completed-gone"])

    def test_commit_preserves_deleted_row_ids_when_other_completed_oa_remains(self) -> None:
        connection = FakeConnection(
            application_delete_results=[[{"row_id": "oa-completed-gone"}], []]
        )
        relation_commands = FakeRelationCommandService()
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: relation_commands,
        )
        retained = _oa("oa-completed-retained", "2026-06", workflow_status="completed", flow_id="flow-1")

        result = repository.commit_authoritative_snapshot(
            scope_key="2026-06",
            projection_records=[retained],
            admission_records=[retained],
            payment_statuses={"flow-1": OAPaymentStatusRecord(flow_id="flow-1", pay_status=0)},
        )

        self.assertEqual(result.removed_stale_completed_count, 1)
        self.assertEqual(relation_commands.calls[0]["row_ids"], ["oa-completed-gone"])

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
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
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
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
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
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
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
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
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
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
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
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
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
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
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
        application_delete_results: list[list[dict[str, object]]],
    ) -> None:
        self.status_rows = list(status_rows)
        self.admission_rows = list(admission_rows)
        self.watermark_rows = list(watermark_rows)
        self.application_delete_results = [list(rows) for rows in application_delete_results]
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
        if "delete from app.oa_applications" in sql:
            return self.application_delete_results.pop(0) if self.application_delete_results else []
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
        application_delete_results: list[list[dict[str, object]]] | None = None,
    ) -> None:
        self.transaction_handle = FakeTransaction(
            status_rows=list(status_rows or []),
            admission_rows=list(admission_rows or []),
            watermark_rows=list(watermark_rows or []),
            application_delete_results=list(application_delete_results or []),
        )
        self.transaction_count = 0
        self.committed = False
        self.rolled_back = False

    def transaction(self) -> FakeTransactionContext:
        self.transaction_count += 1
        return FakeTransactionContext(self)


class FakeRelationCommandService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def remove_rows_from_active_relations(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"changed_case_ids": [], "affected_months": []}


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
