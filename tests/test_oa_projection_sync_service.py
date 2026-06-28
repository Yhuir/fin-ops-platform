from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService
from fin_ops_platform.services.postgres_repositories.oa_projection import _record_application_date
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class OaProjectionSyncServiceTests(unittest.TestCase):
    def test_projection_application_date_uses_record_detail_date_not_month_start(self) -> None:
        record = _oa("oa-pay-application-date", "2026-01", workflow_status="completed")
        record.detail_fields["申请日期"] = "2026-01-14 14:04:00"

        self.assertEqual(_record_application_date(record), "2026-01-14")

    def test_month_sync_with_no_source_records_clears_existing_projection_scope(self) -> None:
        source_adapter = FakeSourceAdapter(months=[], records_by_month={"2026-06": []})
        projection_repository = FakeProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            queue_repository=object(),
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(result["scanned_count"], 0)
        self.assertEqual(projection_repository.stale_completed_scopes, ["2026-06"])
        self.assertEqual(projection_repository.non_completed_scopes, ["2026-06"])

    def test_oa_sync_persists_completed_rows_without_read_model_enqueue_for_progress_rows(self) -> None:
        records = [
            _oa("oa-pay-completed", "2026-06", workflow_status="completed"),
            _oa("oa-pay-progress", "2026-06", workflow_status="in_progress"),
        ]
        source_adapter = FakeSourceAdapter(months=["2026-06"], records_by_month={"2026-06": records})
        projection_repository = FakeProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            queue_repository=object(),
            retention_cutoff_date_provider=lambda: "2026-01-01",
        )

        result = service.handle_runtime_event(_event("all"))

        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual(result["upserted_count"], 1)
        self.assertEqual(result["removed_non_completed_count"], 1)
        self.assertEqual([record.workflow_status for record in projection_repository.saved_records], ["completed"])
        self.assertEqual([record.workflow_status for record in projection_repository.deleted_non_completed_records], ["completed", "in_progress"])

    def test_oa_sync_no_longer_enqueues_downstream_page_read_model_refresh(self) -> None:
        records = [_oa("oa-pay-completed", "2026-06", workflow_status="completed")]
        source_adapter = FakeSourceAdapter(months=["2026-06"], records_by_month={"2026-06": records})
        projection_repository = FakeProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            queue_repository=object(),
        )

        service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(projection_repository.sync_runs[0]["status"], "succeeded")

    def test_oa_sync_promotes_completed_pending_payment_relations_without_read_model_enqueue(self) -> None:
        records = [_oa("oa-pay-completed", "2026-06", workflow_status="completed")]
        source_adapter = FakeSourceAdapter(months=["2026-06"], records_by_month={"2026-06": records})
        projection_repository = FakeProjectionRepository()
        promoter = FakePendingPaymentRelationPromoter(
            {
                "promoted_count": 1,
                "skipped_count": 0,
                "error_count": 0,
                "errors": [],
                "affected_months": ["2026-02"],
            }
        )
        service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            queue_repository=object(),
            pending_payment_relation_promoter=promoter,
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual([record.id for record in promoter.completed_records], ["oa-pay-completed"])
        self.assertEqual(result["promoted_pending_payment_relation_count"], 1)
        self.assertEqual(result["pending_payment_relation_promotion_error_count"], 0)


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
        self.deleted_non_completed_records: list[OAApplicationRecord] = []
        self.stale_completed_scopes: list[str] = []
        self.non_completed_scopes: list[str] = []
        self.sync_runs: list[dict[str, object]] = []

    def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
        self.saved_records = list(records)
        return len(records)

    def prune_records_before(self, cutoff_month: str) -> list[str]:
        return []

    def delete_stale_completed_application_records(
        self,
        *,
        scope_key: str,
        records: list[OAApplicationRecord],
        scanned_records: list[OAApplicationRecord],
    ) -> list[str]:
        self.stale_completed_scopes.append(scope_key)
        return []

    def delete_non_completed_application_records(
        self,
        *,
        scope_key: str,
        records: list[OAApplicationRecord],
    ) -> list[str]:
        self.non_completed_scopes.append(scope_key)
        self.deleted_non_completed_records = list(records)
        return [record.id for record in records if record.workflow_status == "in_progress"]

    def record_sync_run(self, payload: dict[str, object]) -> None:
        self.sync_runs.append(dict(payload))


class FakePendingPaymentRelationPromoter:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = dict(result)
        self.completed_records: list[OAApplicationRecord] = []

    def promote_completed_records(self, records: list[OAApplicationRecord], *, actor_id: str) -> dict[str, object]:
        self.completed_records = list(records)
        self.actor_id = actor_id
        return dict(self.result)


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
