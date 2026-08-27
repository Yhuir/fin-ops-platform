from __future__ import annotations

from typing import Any

from fin_ops_platform.services.imports import clean_string
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import (
    OAPaymentStatusRepository,
    PAY_STATUS_FAILED,
    PAY_STATUS_PAID,
    PAY_STATUS_PENDING,
)
from fin_ops_platform.services.oa_payment_status_reconcile_contract import (
    OA_PAYMENT_STATUS_RECONCILE_EVENT,
)
from fin_ops_platform.services.postgres_repositories.oa_payment_status_reconcile import (
    PostgresOAPaymentStatusReconcileRepository,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class OAPaymentStatusReconcileError(RuntimeError):
    pass


class OAPaymentStatusReconcileService:
    def __init__(
        self,
        *,
        oa_projection: Any,
        reconcile_repository: PostgresOAPaymentStatusReconcileRepository,
        payment_status_repository: OAPaymentStatusRepository,
        payment_status_snapshot_writer: Any,
    ) -> None:
        self._oa_projection = oa_projection
        self._reconcile_repository = reconcile_repository
        self._payment_status_repository = payment_status_repository
        self._payment_status_snapshot_writer = payment_status_snapshot_writer

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        oa_row_ids = _text_list(event.payload.get("oa_row_ids"))
        if not oa_row_ids:
            raise OAPaymentStatusReconcileError("oa_row_ids are required for payment-status reconciliation.")
        records = list(self._oa_projection.list_application_records_by_row_ids(oa_row_ids) or [])
        records_by_id = {
            record.id: record
            for record in records
            if isinstance(record, OAApplicationRecord)
        }
        missing = [row_id for row_id in oa_row_ids if row_id not in records_by_id]
        if missing:
            raise OAPaymentStatusReconcileError(
                "OA payment-status reconciliation cannot find rows: " + ",".join(missing)
            )

        records_by_flow_id: dict[str, list[OAApplicationRecord]] = {}
        for row_id in oa_row_ids:
            record = records_by_id[row_id]
            flow_id = clean_string(self._payment_status_repository.resolve_flow_id(record) or "")
            if not flow_id:
                raise OAPaymentStatusReconcileError(
                    f"OA payment-status reconciliation cannot resolve Flow ID for {row_id}."
                )
            records_by_flow_id.setdefault(flow_id, []).append(record)

        active_outflow = self._reconcile_repository.active_outflow_by_oa_row_id(oa_row_ids)
        final_statuses: dict[str, int] = {}
        for flow_id, flow_records in records_by_flow_id.items():
            desired_status = (
                PAY_STATUS_PAID
                if any(active_outflow.get(record.id, False) for record in flow_records)
                else PAY_STATUS_PENDING
            )
            final_statuses[flow_id] = self._reconcile_flow(
                event=event,
                flow_id=flow_id,
                records=flow_records,
                desired_status=desired_status,
            )

        result = self._payment_status_snapshot_writer.record_payment_statuses(
            records=[record for values in records_by_flow_id.values() for record in values],
            pay_statuses_by_flow_id=final_statuses,
            tenant_id=event.tenant_id,
        )
        return {
            "status": "reconciled",
            "oa_row_ids": oa_row_ids,
            "flow_count": len(records_by_flow_id),
            "changed_scopes": list(result.oa_pending_payment_changed_scopes),
        }

    def _reconcile_flow(
        self,
        *,
        event: RuntimeQueueEvent,
        flow_id: str,
        records: list[OAApplicationRecord],
        desired_status: int,
    ) -> int:
        current = self._payment_status_repository.get_payment_status(flow_id)
        if current is not None and current.pay_status == PAY_STATUS_FAILED:
            raise OAPaymentStatusReconcileError(
                f"OA payment status is failed and requires explicit handling: {flow_id}"
            )
        state = self._reconcile_repository.load_state(
            tenant_id=event.tenant_id,
            flow_id=flow_id,
        )
        row_ids = [record.id for record in records]

        if desired_status == PAY_STATUS_PAID:
            if current is not None and current.pay_status == PAY_STATUS_PAID:
                app_owned = bool(state and state.app_owned)
            else:
                self._save_state(
                    event=event,
                    flow_id=flow_id,
                    row_ids=row_ids,
                    app_owned=True,
                    sync_state="applying",
                    desired_status=PAY_STATUS_PAID,
                    observed_status=current.pay_status if current else None,
                )
                current = self._payment_status_repository.mark_paid(flow_id)
                app_owned = True
            self._save_state(
                event=event,
                flow_id=flow_id,
                row_ids=row_ids,
                app_owned=app_owned,
                sync_state="stable",
                desired_status=PAY_STATUS_PAID,
                observed_status=PAY_STATUS_PAID,
            )
            return PAY_STATUS_PAID

        if state is not None and state.app_owned:
            if current is None:
                raise OAPaymentStatusReconcileError(
                    f"App-owned OA payment status disappeared before revert: {flow_id}"
                )
            self._save_state(
                event=event,
                flow_id=flow_id,
                row_ids=row_ids,
                app_owned=True,
                sync_state="applying",
                desired_status=PAY_STATUS_PENDING,
                observed_status=current.pay_status,
            )
            if current.pay_status != PAY_STATUS_PENDING:
                current = self._payment_status_repository.mark_pending(flow_id)
            self._save_state(
                event=event,
                flow_id=flow_id,
                row_ids=row_ids,
                app_owned=False,
                sync_state="stable",
                desired_status=PAY_STATUS_PENDING,
                observed_status=PAY_STATUS_PENDING,
            )
            return PAY_STATUS_PENDING

        observed_status = current.pay_status if current is not None else PAY_STATUS_PENDING
        self._save_state(
            event=event,
            flow_id=flow_id,
            row_ids=row_ids,
            app_owned=False,
            sync_state="stable",
            desired_status=PAY_STATUS_PENDING,
            observed_status=observed_status,
        )
        return observed_status

    def _save_state(
        self,
        *,
        event: RuntimeQueueEvent,
        flow_id: str,
        row_ids: list[str],
        app_owned: bool,
        sync_state: str,
        desired_status: int,
        observed_status: int | None,
    ) -> None:
        self._reconcile_repository.save_state(
            tenant_id=event.tenant_id,
            flow_id=flow_id,
            oa_row_ids=row_ids,
            app_owned=app_owned,
            sync_state=sync_state,
            desired_pay_status=desired_status,
            observed_pay_status=observed_status,
            event_id=event.event_id,
        )


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(clean_string(item or "") for item in value if clean_string(item or "")))
