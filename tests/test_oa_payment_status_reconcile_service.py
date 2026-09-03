from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_reconcile import (
    OAPaymentStatusReconcileError,
    OAPaymentStatusReconcileService,
)
from fin_ops_platform.services.oa_payment_status_reconcile_contract import (
    OA_PAYMENT_STATUS_REMOVE_MISSING_OPERATION,
    OA_PAYMENT_STATUS_RECONCILE_EVENT,
)
from fin_ops_platform.services.oa_payment_status_service import (
    OAPaymentStatusRecord,
    PAY_STATUS_FAILED,
    PAY_STATUS_PAID,
    PAY_STATUS_PENDING,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class StaticProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self._records = {record.id: record for record in records}

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        return [self._records[row_id] for row_id in row_ids if row_id in self._records]

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self._records.values())


class StaticSourceIdentityReader:
    def __init__(self, flow_ids: set[str] | None = None) -> None:
        self.flow_ids = set(flow_ids or set())
        self.calls: list[list[str]] = []

    def list_existing_payment_flow_ids(self, flow_ids: list[str]) -> set[str]:
        self.calls.append(list(flow_ids))
        return self.flow_ids.intersection(flow_ids)


class MemoryPaymentStatusRepository:
    def __init__(self, statuses: dict[str, int]) -> None:
        self.statuses = dict(statuses)
        self.marked_paid: list[str] = []
        self.marked_pending: list[str] = []
        self.removal_calls: list[list[str]] = []

    def resolve_flow_id(self, record: OAApplicationRecord) -> str | None:
        return str(record.detail_fields.get("支付状态FlowID") or "") or None

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None:
        value = self.statuses.get(flow_id)
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=value) if value is not None else None

    def mark_paid(self, flow_id: str) -> OAPaymentStatusRecord:
        self.marked_paid.append(flow_id)
        self.statuses[flow_id] = PAY_STATUS_PAID
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PAID)

    def mark_pending(self, flow_id: str) -> OAPaymentStatusRecord:
        self.marked_pending.append(flow_id)
        self.statuses[flow_id] = PAY_STATUS_PENDING
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PENDING)

    def remove_payment_statuses(self, flow_ids: list[str]) -> int:
        normalized = list(dict.fromkeys(flow_ids))
        self.removal_calls.append(normalized)
        removed = 0
        for flow_id in normalized:
            if flow_id in self.statuses:
                removed += 1
                self.statuses.pop(flow_id)
        return removed


class MemoryReconcileRepository:
    def __init__(
        self,
        *,
        active_outflow: dict[str, bool] | None = None,
        pending_flow_ids: set[str] | None = None,
    ) -> None:
        self.active_outflow = dict(active_outflow or {})
        self.pending_flow_ids = set(pending_flow_ids or set())

    def active_outflow_by_oa_row_id(self, row_ids: list[str]) -> dict[str, bool]:
        return {row_id: self.active_outflow.get(row_id, False) for row_id in row_ids}

    def current_pending_oa_flow_ids(self, *, tenant_id: str) -> set[str]:
        self.pending_tenant_id = tenant_id
        return set(self.pending_flow_ids)


class RecordingSnapshotWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def record_payment_statuses(self, **payload: object) -> SimpleNamespace:
        self.calls.append(dict(payload))
        return SimpleNamespace(oa_pending_payment_changed_scopes=("2026-08",))


class OAPaymentStatusReconcileServiceTests(unittest.TestCase):
    def test_active_formal_outflow_relation_marks_paid_without_amount_gate(self) -> None:
        service, payment, reconcile, snapshot = _service(
            records=[_record("oa-1", "flow-1")],
            statuses={"flow-1": PAY_STATUS_PENDING},
            active_outflow={"oa-1": True},
        )

        result = service.handle_runtime_event(_event(["oa-1"]))

        self.assertEqual(payment.marked_paid, ["flow-1"])
        self.assertEqual(payment.marked_pending, [])
        self.assertEqual(snapshot.calls[0]["pay_statuses_by_flow_id"], {"flow-1": PAY_STATUS_PAID})
        self.assertEqual(result["status"], "reconciled")

    def test_withdrawn_outflow_relation_reverts_paid_status_without_ownership_gate(self) -> None:
        service, payment, _, snapshot = _service(
            records=[_record("oa-1", "flow-1")],
            statuses={"flow-1": PAY_STATUS_PAID},
        )

        service.handle_runtime_event(_event(["oa-1"]))

        self.assertEqual(payment.marked_pending, ["flow-1"])
        self.assertEqual(snapshot.calls[0]["pay_statuses_by_flow_id"], {"flow-1": PAY_STATUS_PENDING})

    def test_preexisting_paid_status_without_outflow_is_reverted_to_pending(self) -> None:
        service, payment, _, snapshot = _service(
            records=[_record("oa-1", "flow-1")],
            statuses={"flow-1": PAY_STATUS_PAID},
        )

        service.handle_runtime_event(_event(["oa-1"]))

        self.assertEqual(payment.marked_pending, ["flow-1"])
        self.assertEqual(snapshot.calls[0]["pay_statuses_by_flow_id"], {"flow-1": PAY_STATUS_PENDING})

    def test_inflow_only_relation_does_not_mark_paid(self) -> None:
        service, payment, _, snapshot = _service(
            records=[_record("oa-1", "flow-1")],
            statuses={"flow-1": PAY_STATUS_PENDING},
            active_outflow={"oa-1": False},
        )

        service.handle_runtime_event(_event(["oa-1"]))

        self.assertEqual(payment.marked_paid, [])
        self.assertEqual(payment.marked_pending, [])
        self.assertEqual(snapshot.calls[0]["pay_statuses_by_flow_id"], {"flow-1": PAY_STATUS_PENDING})

    def test_missing_external_status_without_outflow_is_created_as_pending(self) -> None:
        service, payment, _, snapshot = _service(
            records=[_record("oa-1", "flow-1")],
            statuses={},
        )

        service.handle_runtime_event(_event(["oa-1"]))

        self.assertEqual(payment.marked_pending, ["flow-1"])
        self.assertEqual(snapshot.calls[0]["pay_statuses_by_flow_id"], {"flow-1": PAY_STATUS_PENDING})

    def test_existing_status_already_matching_topology_is_not_written_again(self) -> None:
        service, payment, _, snapshot = _service(
            records=[_record("oa-1", "flow-1")],
            statuses={"flow-1": PAY_STATUS_PAID},
            active_outflow={"oa-1": True},
        )

        service.handle_runtime_event(_event(["oa-1"]))

        self.assertEqual(payment.marked_paid, [])
        self.assertEqual(payment.marked_pending, [])
        self.assertEqual(snapshot.calls[0]["pay_statuses_by_flow_id"], {"flow-1": PAY_STATUS_PAID})

    def test_failed_payment_status_is_never_overwritten(self) -> None:
        service, payment, _, snapshot = _service(
            records=[_record("oa-1", "flow-1")],
            statuses={"flow-1": PAY_STATUS_FAILED},
            active_outflow={"oa-1": True},
        )

        with self.assertRaisesRegex(OAPaymentStatusReconcileError, "failed"):
            service.handle_runtime_event(_event(["oa-1"]))

        self.assertEqual(payment.marked_paid, [])
        self.assertEqual(snapshot.calls, [])

    def test_missing_flow_id_fails_instead_of_guessing(self) -> None:
        service, payment, _, snapshot = _service(
            records=[_record("oa-1", "")],
            statuses={},
            active_outflow={"oa-1": True},
        )

        with self.assertRaisesRegex(OAPaymentStatusReconcileError, "Flow ID"):
            service.handle_runtime_event(_event(["oa-1"]))

        self.assertEqual(payment.marked_paid, [])
        self.assertEqual(snapshot.calls, [])

    def test_duplicate_oa_rows_with_same_flow_id_are_reconciled_once(self) -> None:
        records = [
            _record("oa-completed", "flow-shared", workflow_status="completed"),
            _record("oa-progress", "flow-shared", workflow_status="in_progress"),
        ]
        service, payment, _, snapshot = _service(
            records=records,
            statuses={"flow-shared": PAY_STATUS_PENDING},
            active_outflow={"oa-completed": True, "oa-progress": False},
        )

        service.handle_runtime_event(_event(["oa-completed", "oa-progress"]))

        self.assertEqual(payment.marked_paid, ["flow-shared"])
        self.assertEqual(snapshot.calls[0]["pay_statuses_by_flow_id"], {"flow-shared": PAY_STATUS_PAID})

    def test_missing_oa_operation_removes_only_flows_still_absent_from_canonical_oa(self) -> None:
        service, payment, _, snapshot = _service(
            records=[_record("oa-reappeared", "flow-reappeared")],
            statuses={
                "flow-removed": PAY_STATUS_PAID,
                "flow-reappeared": PAY_STATUS_PENDING,
            },
        )

        result = service.handle_runtime_event(
            _remove_event(["flow-removed", "flow-reappeared", "flow-removed"])
        )

        self.assertEqual(payment.removal_calls, [["flow-removed"]])
        self.assertNotIn("flow-removed", payment.statuses)
        self.assertIn("flow-reappeared", payment.statuses)
        self.assertEqual(snapshot.calls, [])
        self.assertEqual(result["status"], "removed_missing_oa_statuses")
        self.assertEqual(result["requested_flow_count"], 2)
        self.assertEqual(result["removed_flow_count"], 1)
        self.assertEqual(result["skipped_reappeared_flow_ids"], ["flow-reappeared"])

    def test_missing_oa_operation_is_idempotent_when_external_rows_are_already_absent(self) -> None:
        service, payment, _, snapshot = _service(records=[], statuses={})

        result = service.handle_runtime_event(_remove_event(["flow-removed"]))

        self.assertEqual(payment.removal_calls, [["flow-removed"]])
        self.assertEqual(result["removed_row_count"], 0)
        self.assertEqual(snapshot.calls, [])

    def test_missing_oa_operation_preserves_flow_that_reappeared_as_pending(self) -> None:
        service, payment, _, snapshot = _service(
            records=[],
            statuses={"flow-reappeared": PAY_STATUS_PAID},
            pending_flow_ids={"flow-reappeared"},
        )

        result = service.handle_runtime_event(_remove_event(["flow-reappeared"]))

        self.assertEqual(payment.removal_calls, [])
        self.assertIn("flow-reappeared", payment.statuses)
        self.assertEqual(result["skipped_reappeared_flow_ids"], ["flow-reappeared"])
        self.assertEqual(snapshot.calls, [])

    def test_missing_oa_operation_preserves_flow_that_exists_outside_projection_retention(self) -> None:
        service, payment, _, snapshot = _service(
            records=[],
            statuses={"flow-outside-retention": PAY_STATUS_PAID},
            source_flow_ids={"flow-outside-retention"},
        )

        result = service.handle_runtime_event(_remove_event(["flow-outside-retention"]))

        self.assertEqual(payment.removal_calls, [])
        self.assertIn("flow-outside-retention", payment.statuses)
        self.assertEqual(result["skipped_reappeared_flow_ids"], ["flow-outside-retention"])
        self.assertEqual(snapshot.calls, [])

    def test_missing_oa_operation_requires_explicit_flow_ids(self) -> None:
        service, payment, _, snapshot = _service(records=[], statuses={})

        with self.assertRaisesRegex(OAPaymentStatusReconcileError, "removed_flow_ids"):
            service.handle_runtime_event(_remove_event([]))

        self.assertEqual(payment.removal_calls, [])
        self.assertEqual(snapshot.calls, [])


def _service(
    *,
    records: list[OAApplicationRecord],
    statuses: dict[str, int],
    active_outflow: dict[str, bool] | None = None,
    pending_flow_ids: set[str] | None = None,
    source_flow_ids: set[str] | None = None,
) -> tuple[
    OAPaymentStatusReconcileService,
    MemoryPaymentStatusRepository,
    MemoryReconcileRepository,
    RecordingSnapshotWriter,
]:
    payment = MemoryPaymentStatusRepository(statuses)
    reconcile = MemoryReconcileRepository(
        active_outflow=active_outflow,
        pending_flow_ids=pending_flow_ids,
    )
    snapshot = RecordingSnapshotWriter()
    return (
        OAPaymentStatusReconcileService(
            oa_projection=StaticProjection(records),
            reconcile_repository=reconcile,  # type: ignore[arg-type]
            payment_status_repository=payment,
            payment_status_snapshot_writer=snapshot,
            oa_source_identity_reader=StaticSourceIdentityReader(source_flow_ids),
        ),
        payment,
        reconcile,
        snapshot,
    )


def _event(row_ids: list[str]) -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id="event-1",
        tenant_id="default",
        event_type=OA_PAYMENT_STATUS_RECONCILE_EVENT,
        aggregate_type="workbench_relation",
        aggregate_id="case-1",
        scope_type=None,
        scope_key=None,
        dedupe_key="event-1",
        payload={"oa_row_ids": row_ids},
        attempts=0,
        status="processing",
    )


def _remove_event(flow_ids: list[str]) -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id="event-remove-1",
        tenant_id="default",
        event_type=OA_PAYMENT_STATUS_RECONCILE_EVENT,
        aggregate_type="oa_payment_status",
        aggregate_id="2026-08",
        scope_type="oa_payment_status",
        scope_key="2026-08",
        dedupe_key=None,
        payload={
            "operation": OA_PAYMENT_STATUS_REMOVE_MISSING_OPERATION,
            "removed_flow_ids": flow_ids,
        },
        attempts=0,
        status="processing",
    )


def _record(
    row_id: str,
    flow_id: str,
    *,
    workflow_status: str = "completed",
) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=row_id,
        month="2026-08",
        section="paired",
        case_id="case-1",
        applicant="测试申请人",
        project_name="测试项目",
        apply_type="日常报销",
        amount="100.00",
        counterparty_name="测试供应商",
        reason="测试付款",
        relation_code="matched",
        relation_label="已配对",
        relation_tone="success",
        workflow_status=workflow_status,
        detail_fields={"支付状态FlowID": flow_id} if flow_id else {},
    )

if __name__ == "__main__":
    unittest.main()
