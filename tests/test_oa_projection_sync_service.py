from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class OaProjectionSyncServiceTests(unittest.TestCase):
    def test_oa_sync_marks_oa_pending_payment_read_model_dirty_for_progress_rows(self) -> None:
        records = [
            _oa("oa-pay-completed", "2026-06", workflow_status="completed"),
            _oa("oa-pay-progress", "2026-06", workflow_status="in_progress"),
        ]
        source_adapter = FakeSourceAdapter(months=["2026-06"], records_by_month={"2026-06": records})
        projection_repository = FakeProjectionRepository()
        queue_repository = FakeQueueRepository()
        service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            queue_repository=queue_repository,
            retention_cutoff_date_provider=lambda: "2026-01-01",
        )

        result = service.handle_runtime_event(_event("all"))

        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual([record.workflow_status for record in projection_repository.saved_records], ["completed", "in_progress"])
        self.assertIn(("oa_pending_payment", "2026-06", "oa_projection_sync"), queue_repository.refreshes)
        self.assertIn(("oa_pending_payment", "all", "oa_projection_sync"), queue_repository.refreshes)


class FakeSourceAdapter:
    def __init__(self, *, months: list[str], records_by_month: dict[str, list[OAApplicationRecord]]) -> None:
        self._months = list(months)
        self._records_by_month = {month: list(records) for month, records in records_by_month.items()}

    def list_available_months(self) -> list[str]:
        return list(self._months)

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        return list(self._records_by_month.get(month, []))


class FakeProjectionRepository:
    def __init__(self) -> None:
        self.saved_records: list[OAApplicationRecord] = []
        self.sync_runs: list[dict[str, object]] = []

    def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
        self.saved_records = list(records)
        return len(records)

    def prune_records_before(self, cutoff_month: str) -> list[str]:
        return []

    def record_sync_run(self, payload: dict[str, object]) -> None:
        self.sync_runs.append(dict(payload))


class FakeQueueRepository:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str, **_kwargs: object) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


def _oa(row_id: str, month: str, *, workflow_status: str) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=row_id,
        month=month,
        section="open",
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
    )


def _event(scope_key: str) -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id=f"event-{scope_key}",
        tenant_id="default",
        event_type="oa.sync",
        aggregate_type="oa",
        aggregate_id=scope_key,
        scope_type="oa",
        scope_key=scope_key,
        dedupe_key=None,
        payload={"scope_key": scope_key},
        attempts=1,
        status="processing",
    )


if __name__ == "__main__":
    unittest.main()
