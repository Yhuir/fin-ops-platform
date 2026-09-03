from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord
from fin_ops_platform.services.oa_payment_status_reconcile_contract import (
    OA_PAYMENT_STATUS_REMOVE_MISSING_OPERATION,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentSourceSnapshotRepository,
    _signature,
)


class OaPendingPaymentSourceSnapshotRepositoryTests(unittest.TestCase):
    def test_owner_snapshot_refuses_duplicate_winning_status_before_transaction(self) -> None:
        record = _oa(
            "oa-exp-duplicate",
            "2026-06",
            workflow_status="in_progress",
            flow_id="flow-duplicate",
            apply_type="日常报销",
        )
        connection = FakeConnection()
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
        )

        with self.assertRaisesRegex(ValueError, "duplicate winning row_id"):
            repository.commit_authoritative_snapshot(
                scope_key="2026-06",
                projection_records=[],
                admission_records=[record, record],
                payment_statuses={
                    "flow-duplicate": OAPaymentStatusRecord(
                        flow_id="flow-duplicate",
                        pay_status=0,
                    )
                },
            )

        self.assertEqual(connection.transaction_count, 0)

    def test_targeted_in_progress_refresh_requires_one_existing_pending_owner(self) -> None:
        record = _oa(
            "oa-exp-targeted",
            "2026-06",
            workflow_status="in_progress",
            flow_id="flow-targeted",
            apply_type="日常报销",
        )

        for admission_rows in (
            [],
            [
                {
                    "scope_key": "2026-06",
                    "oa_id": record.id,
                    "source_signature": "one",
                    "source_payload": {"id": record.id},
                },
                {
                    "scope_key": "2026-05",
                    "oa_id": record.id,
                    "source_signature": "two",
                    "source_payload": {"id": record.id},
                },
            ],
        ):
            with self.subTest(owner_count=len(admission_rows)):
                connection = FakeConnection(admission_rows=admission_rows)
                repository = PostgresOaPendingPaymentSourceSnapshotRepository(
                    connection,
                    relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
                )

                with self.assertRaisesRegex(RuntimeError, "exactly one existing pending owner"):
                    repository.commit_targeted_attachment_refresh(records=[record])

                self.assertFalse(connection.committed)
                self.assertTrue(connection.rolled_back)
                executed_sql = "\n".join(
                    sql for sql, _params in connection.transaction_handle.executions
                )
                self.assertNotIn("insert into app.oa_pending_payment_admissions", executed_sql)

    def test_targeted_in_progress_refresh_replaces_the_existing_pending_owner(self) -> None:
        record = _oa(
            "oa-exp-targeted",
            "2026-06",
            workflow_status="in_progress",
            flow_id="flow-targeted",
            apply_type="日常报销",
        )
        connection = FakeConnection(
            admission_rows=[
                {
                    "scope_key": "2026-06",
                    "oa_id": record.id,
                    "source_signature": "stale",
                    "source_payload": {"id": record.id},
                }
            ]
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
        )

        result = repository.commit_targeted_attachment_refresh(records=[record])

        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertEqual(result.upserted_completed_count, 0)
        self.assertEqual(result.upserted_pending_count, 1)
        self.assertEqual(result.pending_admission_changed_scopes, ("2026-06",))
        executed_sql = "\n".join(sql for sql, _params in connection.transaction_handle.executions)
        self.assertIn("delete from app.oa_pending_payment_admissions", executed_sql)
        self.assertIn("insert into app.oa_pending_payment_admissions", executed_sql)

    def test_targeted_in_progress_refresh_refuses_pending_owner_scope_drift(self) -> None:
        record = _oa(
            "oa-exp-targeted",
            "2026-06",
            workflow_status="in_progress",
            flow_id="flow-targeted",
            apply_type="日常报销",
        )
        connection = FakeConnection(
            admission_rows=[
                {
                    "scope_key": "2026-05",
                    "oa_id": record.id,
                    "source_signature": "stale",
                    "source_payload": {"id": record.id},
                }
            ]
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
        )

        with self.assertRaisesRegex(RuntimeError, "existing pending owner scope"):
            repository.commit_targeted_attachment_refresh(records=[record])

        self.assertFalse(connection.committed)
        self.assertTrue(connection.rolled_back)
        executed_sql = "\n".join(sql for sql, _params in connection.transaction_handle.executions)
        self.assertNotIn("insert into app.oa_pending_payment_admissions", executed_sql)

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
        self.assertEqual(result.pending_admission_changed_scopes, ("2026-06",))
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
        matching_writes = [
            params
            for sql, params in connection.transaction_handle.executions
            if "insert into job.workbench_matching_dirty_scopes" in sql
        ]
        self.assertEqual(len(matching_writes), 5)
        self.assertEqual(
            [str(params[1])[:7] for params in matching_writes],
            ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08"],
        )
        self.assertNotIn("job.read_model_dirty_scopes", executed_sql)
        self.assertNotIn("job.outbox_events", executed_sql)

    def test_completed_admission_clears_pending_owner_even_when_projection_excludes_it(
        self,
    ) -> None:
        completed = _oa(
            "oa-completed-filtered",
            "2026-06",
            workflow_status="completed",
            flow_id="flow-completed-filtered",
            apply_type="日常报销",
        )
        connection = FakeConnection(
            admission_rows=[
                {
                    "scope_key": "2026-05",
                    "oa_id": completed.id,
                    "source_signature": "pending-before-completion",
                    "source_payload": {"id": completed.id},
                }
            ]
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
        )

        result = repository.replace_authoritative_snapshot(
            scope_key="2026-06",
            completed_projection_records=[],
            admission_records=[completed],
            payment_statuses={},
        )

        self.assertIn("2026-05", result.oa_pending_payment_changed_scopes)
        admission_deletes = [
            params
            for sql, params in connection.transaction_handle.executions
            if "delete from app.oa_pending_payment_admissions" in sql
        ]
        self.assertEqual(admission_deletes, [("default", ["2026-05"])])
        executed_sql = "\n".join(sql for sql, _params in connection.transaction_handle.executions)
        self.assertNotIn("insert into app.oa_pending_payment_admissions", executed_sql)

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
        self.assertFalse(relation_commands.calls[0]["emit_payment_status_reconcile"])

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

    def test_payment_status_without_current_oa_is_removed_and_enqueued_for_external_delete(self) -> None:
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
            scope_key="all",
            completed_projection_records=[],
            admission_records=[],
            payment_statuses={"flow-1": OAPaymentStatusRecord(flow_id="flow-1", pay_status=1)},
        )

        self.assertEqual(result.completed_projection_changed_scopes, ())
        self.assertEqual(result.oa_pending_payment_changed_scopes, ("2026-06",))
        self.assertEqual(result.payment_status_count, 0)
        self.assertEqual(result.removed_payment_status_flow_ids, ("flow-1",))
        executed_sql = "\n".join(sql for sql, _params in connection.transaction_handle.executions)
        self.assertNotIn("job.workbench_matching_dirty_scopes", executed_sql)
        outbox_calls = [
            params
            for sql, params in connection.transaction_handle.executions
            if "insert into job.outbox_events" in sql
        ]
        self.assertEqual(len(outbox_calls), 1)
        self.assertEqual(outbox_calls[0][7]["operation"], OA_PAYMENT_STATUS_REMOVE_MISSING_OPERATION)
        self.assertEqual(outbox_calls[0][7]["removed_flow_ids"], ["flow-1"])

    def test_month_snapshot_preserves_payment_status_owned_by_another_scope(self) -> None:
        connection = FakeConnection(
            status_rows=[
                {
                    "flow_id": "flow-other-month",
                    "pay_status": 1,
                    "scope_month": "2026-05",
                    "source_signature": "old-status",
                }
            ]
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
        )

        result = repository.replace_authoritative_snapshot(
            scope_key="2026-06",
            completed_projection_records=[],
            admission_records=[],
            payment_statuses={
                "flow-other-month": OAPaymentStatusRecord(
                    flow_id="flow-other-month",
                    pay_status=1,
                )
            },
        )

        self.assertEqual(result.payment_status_count, 1)
        self.assertEqual(result.removed_payment_status_flow_ids, ())
        self.assertFalse(
            any(
                "insert into job.outbox_events" in sql
                for sql, _params in connection.transaction_handle.executions
            )
        )

    def test_full_snapshot_removes_status_for_disappeared_pending_admission(self) -> None:
        connection = FakeConnection(
            admission_rows=[
                {
                    "scope_key": "2026-06",
                    "oa_id": "oa-pending-gone",
                    "source_signature": "old-admission",
                    "source_payload": {"flow_id": "flow-pending-gone"},
                }
            ],
            watermark_rows=[_watermark("2026-06")],
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
        )

        result = repository.replace_authoritative_snapshot(
            scope_key="all",
            completed_projection_records=[],
            admission_records=[],
            payment_statuses={
                "flow-pending-gone": OAPaymentStatusRecord(
                    flow_id="flow-pending-gone",
                    pay_status=1,
                )
            },
        )

        self.assertEqual(result.payment_status_count, 0)
        self.assertEqual(
            result.removed_payment_status_flow_ids,
            ("flow-pending-gone",),
        )
        outbox_payloads = [
            params[7]
            for sql, params in connection.transaction_handle.executions
            if "insert into job.outbox_events" in sql
        ]
        self.assertEqual(outbox_payloads[0]["removed_flow_ids"], ["flow-pending-gone"])

    def test_full_snapshot_does_not_claim_unscoped_external_status_ownership(self) -> None:
        connection = FakeConnection(
            status_rows=[
                {
                    "flow_id": "flow-never-canonical",
                    "pay_status": 1,
                    "scope_month": None,
                    "source_signature": "external-status",
                }
            ]
        )
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
        )

        result = repository.replace_authoritative_snapshot(
            scope_key="all",
            completed_projection_records=[],
            admission_records=[],
            payment_statuses={
                "flow-never-canonical": OAPaymentStatusRecord(
                    flow_id="flow-never-canonical",
                    pay_status=1,
                )
            },
        )

        self.assertEqual(result.payment_status_count, 1)
        self.assertEqual(result.removed_payment_status_flow_ids, ())
        self.assertFalse(
            any(
                "insert into job.outbox_events" in sql
                for sql, _params in connection.transaction_handle.executions
            )
        )

    def test_matching_dirty_write_failure_rolls_back_the_oa_snapshot(self) -> None:
        connection = FakeConnection(fail_execute_contains="job.workbench_matching_dirty_scopes")
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda _transaction: FakeRelationCommandService(),
        )

        with self.assertRaisesRegex(RuntimeError, "matching dirty write failed"):
            repository.replace_authoritative_snapshot(
                scope_key="2026-06",
                completed_projection_records=[],
                admission_records=[
                    _oa("oa-pay-row-1", "2026-06", workflow_status="in_progress", flow_id="flow-1")
                ],
                payment_statuses={"flow-1": OAPaymentStatusRecord(flow_id="flow-1", pay_status=0)},
            )

        self.assertFalse(connection.committed)
        self.assertTrue(connection.rolled_back)

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

        result = repository.record_payment_statuses(
            records=[_oa("oa-pay-row-1", "2026-06", workflow_status="completed", flow_id="flow-1")],
            pay_statuses_by_flow_id={"flow-1": 1},
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

        result = repository.record_payment_statuses(
            records=[_oa("oa-pay-row-1", "2026-06", workflow_status="completed", flow_id="flow-1")],
            pay_statuses_by_flow_id={"flow-1": 1},
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

        result = repository.record_payment_statuses(
            records=[_oa("oa-pay-row-1", "2026-06", workflow_status="completed", flow_id="flow-1")],
            pay_statuses_by_flow_id={"flow-1": 1},
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
            repository.record_payment_statuses(
                records=[_oa("oa-pay-row-1", "2026-06", workflow_status="completed", flow_id="flow-1")],
                pay_statuses_by_flow_id={"flow-1": 1},
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
        fail_execute_contains: str | None = None,
    ) -> None:
        self.status_rows = list(status_rows)
        self.admission_rows = list(admission_rows)
        self.watermark_rows = list(watermark_rows)
        self.application_delete_results = [list(rows) for rows in application_delete_results]
        self.fail_execute_contains = fail_execute_contains
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, _params: tuple[object, ...]) -> dict[str, object] | None:
        if "insert into app.oa_applications" in sql:
            self.executions.append((sql, _params))
            return {"application_id": "00000000-0000-0000-0000-000000000001"}
        if "insert into job.outbox_events" in sql:
            self.executions.append((sql, _params))
            return {
                "event_id": "event-payment-status-remove",
                "tenant_id": _params[0],
                "event_type": _params[1],
                "aggregate_type": _params[2],
                "aggregate_id": _params[3],
                "scope_type": _params[4],
                "scope_key": _params[5],
                "dedupe_key": _params[6],
                "payload": _params[7],
                "attempts": 0,
                "status": "pending",
                "schema_version": 1,
                "source_version": _params[9],
                "priority": _params[10],
                "trace_id": _params[11],
            }
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
        if self.fail_execute_contains and self.fail_execute_contains in sql:
            raise RuntimeError("matching dirty write failed")
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
        fail_execute_contains: str | None = None,
    ) -> None:
        self.transaction_handle = FakeTransaction(
            status_rows=list(status_rows or []),
            admission_rows=list(admission_rows or []),
            watermark_rows=list(watermark_rows or []),
            application_delete_results=list(application_delete_results or []),
            fail_execute_contains=fail_execute_contains,
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


def _oa(
    row_id: str,
    month: str,
    *,
    workflow_status: str,
    flow_id: str,
    apply_type: str = "支付申请",
) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=row_id,
        month=month,
        section="unpaired",
        case_id=None,
        applicant="测试申请人",
        project_name="测试项目",
        apply_type=apply_type,
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
