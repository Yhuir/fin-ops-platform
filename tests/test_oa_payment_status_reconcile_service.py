from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_reconcile import (
    OAPaymentStatusReconcileError,
    OAPaymentStatusReconcileService,
)
from fin_ops_platform.services.oa_payment_status_reconcile_contract import (
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


class MemoryPaymentStatusRepository:
    def __init__(self, statuses: dict[str, int]) -> None:
        self.statuses = dict(statuses)
        self.marked_paid: list[str] = []
        self.marked_pending: list[str] = []

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


class MemoryReconcileRepository:
    def __init__(
        self,
        *,
        active_outflow: dict[str, bool] | None = None,
    ) -> None:
        self.active_outflow = dict(active_outflow or {})

    def active_outflow_by_oa_row_id(self, row_ids: list[str]) -> dict[str, bool]:
        return {row_id: self.active_outflow.get(row_id, False) for row_id in row_ids}


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


def _service(
    *,
    records: list[OAApplicationRecord],
    statuses: dict[str, int],
    active_outflow: dict[str, bool] | None = None,
) -> tuple[
    OAPaymentStatusReconcileService,
    MemoryPaymentStatusRepository,
    MemoryReconcileRepository,
    RecordingSnapshotWriter,
]:
    payment = MemoryPaymentStatusRepository(statuses)
    reconcile = MemoryReconcileRepository(active_outflow=active_outflow)
    snapshot = RecordingSnapshotWriter()
    return (
        OAPaymentStatusReconcileService(
            oa_projection=StaticProjection(records),
            reconcile_repository=reconcile,  # type: ignore[arg-type]
            payment_status_repository=payment,
            payment_status_snapshot_writer=snapshot,
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
