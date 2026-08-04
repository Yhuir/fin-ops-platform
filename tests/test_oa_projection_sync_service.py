from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord
from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    OaPendingPaymentSourceSnapshotResult,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import _record_application_date
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class OaProjectionSyncServiceTests(unittest.TestCase):
    def test_payment_status_source_and_postgres_snapshot_must_be_configured_together(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be configured together"):
            OAProjectionSyncService(
                source_adapter=FakeSourceAdapter(months=[], records_by_month={}),
                projection_repository=FakeProjectionRepository(),
                payment_status_repository=FakePaymentStatusRepository({}),
            )

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
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(result["scanned_count"], 0)
        self.assertEqual(projection_repository.stale_completed_scopes, ["2026-06"])
        self.assertEqual(projection_repository.non_completed_scopes, ["2026-06"])

    def test_oa_sync_commits_projection_facts_without_downstream_page_fan_out(self) -> None:
        records = [
            _oa("oa-pay-completed", "2026-06", workflow_status="completed"),
            _oa("oa-pay-progress", "2026-06", workflow_status="in_progress"),
        ]
        source_adapter = FakeSourceAdapter(months=["2026-06"], records_by_month={"2026-06": records})
        projection_repository = FakeProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            retention_cutoff_date_provider=lambda: "2026-01-01",
        )

        result = service.handle_runtime_event(_event("all"))

        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual(source_adapter.last_retention_cutoff_month, "2026-01")
        self.assertEqual(result["upserted_count"], 1)
        self.assertEqual(result["removed_non_completed_count"], 1)
        self.assertEqual([record.workflow_status for record in projection_repository.saved_records], ["completed"])
        self.assertEqual([record.workflow_status for record in projection_repository.deleted_non_completed_records], ["completed", "in_progress"])
        self.assertFalse(hasattr(service, "_queue_repository"))

    def test_completed_projection_change_does_not_publish_matching_work(self) -> None:
        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06"],
                records_by_month={"2026-06": [_oa("oa-etc", "2026-06", workflow_status="completed")]},
            ),
            projection_repository=FakeProjectionRepository(),
        )

        service.handle_runtime_event(_event("2026-06"))

        self.assertFalse(hasattr(service, "_workbench_matching_dirty_queue"))

    def test_oa_sync_treats_legacy_completed_workflow_aliases_as_completed(self) -> None:
        records = [
            _oa("oa-pay-legacy-cn", "2026-06", workflow_status="已完成"),
            _oa("oa-pay-legacy-approved", "2026-06", workflow_status="approved"),
            _oa("oa-pay-progress", "2026-06", workflow_status="in_progress"),
        ]
        source_adapter = FakeSourceAdapter(months=["2026-06"], records_by_month={"2026-06": records})
        projection_repository = FakeProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            retention_cutoff_date_provider=lambda: "2026-01-01",
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(result["scanned_count"], 3)
        self.assertEqual(result["upserted_count"], 2)
        self.assertEqual(
            [record.id for record in projection_repository.saved_records],
            ["oa-pay-legacy-cn", "oa-pay-legacy-approved"],
        )
        self.assertEqual(
            [record.id for record in projection_repository.deleted_non_completed_records],
            ["oa-pay-legacy-cn", "oa-pay-legacy-approved", "oa-pay-progress"],
        )

    def test_oa_sync_has_no_search_refresh_collaborator(self) -> None:
        records = [_oa("oa-pay-completed", "2026-06", workflow_status="completed")]
        source_adapter = FakeSourceAdapter(months=["2026-06"], records_by_month={"2026-06": records})
        projection_repository = FakeProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
        )

        service.handle_runtime_event(_event("2026-06"))

        self.assertFalse(hasattr(service, "_search_read_model_refresh_producer"))

    def test_oa_sync_promotes_completed_pending_payment_relations_and_marks_affected_scopes_dirty(self) -> None:
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
            pending_payment_relation_promoter=promoter,
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual([record.id for record in promoter.completed_records], ["oa-pay-completed"])
        self.assertEqual(result["promoted_pending_payment_relation_count"], 1)
        self.assertEqual(result["pending_payment_relation_promotion_error_count"], 0)
        self.assertFalse(hasattr(service, "_queue_repository"))

    def test_oa_sync_promotes_attachment_invoices_from_completed_records(self) -> None:
        records = [
            _oa("oa-pay-completed", "2026-06", workflow_status="completed"),
            _oa("oa-pay-progress", "2026-06", workflow_status="in_progress"),
        ]
        promoter = FakeAttachmentInvoicePromoter()
        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06"],
                records_by_month={"2026-06": records},
            ),
            projection_repository=FakeProjectionRepository(),
            attachment_invoice_promoter=promoter,
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual([record.id for record in promoter.completed_records], ["oa-pay-completed"])
        self.assertEqual(result["scanned_oa_attachment_invoice_candidate_count"], 5)
        self.assertEqual(result["promoted_oa_attachment_invoice_count"], 5)
        self.assertEqual(result["linked_existing_oa_attachment_invoice_count"], 5)
        self.assertEqual(result["created_oa_attachment_invoice_count"], 0)

    def test_attachment_invoice_promotion_failure_marks_oa_sync_failed_for_retry(self) -> None:
        projection_repository = FakeProjectionRepository()

        class FailingPromoter:
            def promote_records(self, records: list[OAApplicationRecord]) -> dict[str, object]:
                raise RuntimeError(f"promotion failed for {len(records)} record")

        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06"],
                records_by_month={
                    "2026-06": [_oa("oa-pay-completed", "2026-06", workflow_status="completed")]
                },
            ),
            projection_repository=projection_repository,
            attachment_invoice_promoter=FailingPromoter(),
        )

        with self.assertRaisesRegex(RuntimeError, "promotion failed"):
            service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(projection_repository.sync_runs[-1]["status"], "failed")

    def test_oa_sync_replaces_payment_status_and_admission_snapshot_after_complete_external_reads(self) -> None:
        records = [
            _oa("oa-pay-completed", "2026-06", workflow_status="completed"),
            _oa("oa-pay-progress", "2026-06", workflow_status="in_progress"),
        ]
        payment_statuses = {"progress": OAPaymentStatusRecord(flow_id="progress", pay_status=0)}
        snapshot_repository = FakePendingPaymentSourceSnapshotRepository()
        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(months=["2026-06"], records_by_month={"2026-06": records}),
            projection_repository=FakeProjectionRepository(),
            payment_status_repository=FakePaymentStatusRepository(payment_statuses),
            pending_payment_source_snapshot_repository=snapshot_repository,
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(snapshot_repository.calls[0]["scope_key"], "2026-06")
        self.assertEqual(snapshot_repository.calls[0]["projection_records"], records)
        self.assertEqual(snapshot_repository.calls[0]["admission_records"], records)
        self.assertEqual(snapshot_repository.calls[0]["payment_statuses"], payment_statuses)
        self.assertEqual(result["pending_payment_source_snapshot_count"], 1)
        self.assertEqual(result["pending_payment_admission_count"], 1)
        self.assertEqual(result["pending_payment_affected_scope_keys"], ["2026-06"])
        self.assertFalse(hasattr(service, "_queue_repository"))

    def test_identical_authoritative_snapshot_does_not_fan_out_downstream_refreshes(self) -> None:
        records = [_oa("oa-pay-completed", "2026-06", workflow_status="completed")]
        class UnchangedSnapshotRepository(FakePendingPaymentSourceSnapshotRepository):
            def commit_authoritative_snapshot(self, **kwargs: object) -> OaPendingPaymentSourceSnapshotResult:
                self.calls.append(dict(kwargs))
                return OaPendingPaymentSourceSnapshotResult(
                    completed_projection_changed_scopes=(),
                    oa_pending_payment_changed_scopes=(),
                    payment_status_count=0,
                    admission_count=0,
                    source_signatures={},
                    upserted_completed_count=0,
                )

        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(months=["2026-06"], records_by_month={"2026-06": records}),
            projection_repository=FakeProjectionRepository(),
            payment_status_repository=FakePaymentStatusRepository({}),
            pending_payment_source_snapshot_repository=UnchangedSnapshotRepository(),
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(result["upserted_count"], 0)
        self.assertEqual(result["pending_payment_affected_scope_keys"], [])

    def test_admission_only_change_does_not_fan_out_shared_read_models(self) -> None:
        in_progress = _oa("oa-pay-progress", "2026-06", workflow_status="in_progress")
        class AdmissionOnlySnapshotRepository(FakePendingPaymentSourceSnapshotRepository):
            def commit_authoritative_snapshot(self, **kwargs: object) -> OaPendingPaymentSourceSnapshotResult:
                self.calls.append(dict(kwargs))
                return OaPendingPaymentSourceSnapshotResult(
                    completed_projection_changed_scopes=(),
                    oa_pending_payment_changed_scopes=("2026-06",),
                    payment_status_count=1,
                    admission_count=1,
                    source_signatures={"2026-06": "signature"},
                )

        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06"],
                records_by_month={"2026-06": [in_progress]},
                projection_records_by_month={"2026-06": []},
            ),
            projection_repository=FakeProjectionRepository(),
            payment_status_repository=FakePaymentStatusRepository(
                {"progress": OAPaymentStatusRecord(flow_id="progress", pay_status=0)}
            ),
            pending_payment_source_snapshot_repository=AdmissionOnlySnapshotRepository(),
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(result["completed_projection_changed_scope_keys"], [])
        self.assertEqual(result["pending_payment_affected_scope_keys"], ["2026-06"])

    def test_external_payment_status_failure_prevents_any_postgres_projection_write(self) -> None:
        projection_repository = FakeProjectionRepository()
        snapshot_repository = FakePendingPaymentSourceSnapshotRepository()
        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06"],
                records_by_month={"2026-06": [_oa("oa-pay-progress", "2026-06", workflow_status="in_progress")]},
            ),
            projection_repository=projection_repository,
            payment_status_repository=FakePaymentStatusRepository(error=RuntimeError("incomplete mysql read")),
            pending_payment_source_snapshot_repository=snapshot_repository,
        )

        with self.assertRaisesRegex(RuntimeError, "incomplete mysql read"):
            service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(projection_repository.saved_records, [])
        self.assertEqual(projection_repository.stale_completed_scopes, [])
        self.assertEqual(projection_repository.non_completed_scopes, [])
        self.assertEqual(snapshot_repository.calls, [])

    def test_source_batch_failure_records_failed_sync_run_without_projection_write(self) -> None:
        projection_repository = FakeProjectionRepository()

        class FailingSourceAdapter:
            def load_sync_application_batch(
                self,
                _scope_key: str,
                *,
                retention_cutoff_month: str | None = None,
            ) -> object:
                del retention_cutoff_month
                raise RuntimeError("partial mongo read")

        service = OAProjectionSyncService(
            source_adapter=FailingSourceAdapter(),
            projection_repository=projection_repository,
        )

        with self.assertRaisesRegex(RuntimeError, "partial mongo read"):
            service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(projection_repository.saved_records, [])
        self.assertEqual(projection_repository.sync_runs[0]["status"], "failed")
        self.assertEqual(projection_repository.sync_runs[0]["error_count"], 1)


class FakeSourceAdapter:
    def __init__(
        self,
        *,
        months: list[str],
        records_by_month: dict[str, list[OAApplicationRecord]],
        projection_records_by_month: dict[str, list[OAApplicationRecord]] | None = None,
    ) -> None:
        self._months = list(months)
        self._records_by_month = {month: list(records) for month, records in records_by_month.items()}
        self._projection_records_by_month = (
            {month: list(records) for month, records in projection_records_by_month.items()}
            if projection_records_by_month is not None
            else self._records_by_month
        )
        self.last_retention_cutoff_month: str | None = None

    def load_sync_application_batch(
        self,
        scope_key: str,
        *,
        retention_cutoff_month: str | None = None,
    ) -> SimpleNamespace:
        self.last_retention_cutoff_month = retention_cutoff_month
        if scope_key == "all":
            months = self._months or sorted(self._records_by_month)
            records = [
                record
                for month in months
                for record in self._records_by_month.get(month, [])
            ]
            projection_records = [
                record
                for month in months
                for record in self._projection_records_by_month.get(month, [])
            ]
        else:
            records = list(self._records_by_month.get(scope_key, []))
            projection_records = list(self._projection_records_by_month.get(scope_key, []))
        return SimpleNamespace(
            projection_records=tuple(projection_records),
            admission_records=tuple(records),
        )


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


class FakeAttachmentInvoicePromoter:
    def __init__(self) -> None:
        self.completed_records: list[OAApplicationRecord] = []

    def promote_records(self, records: list[OAApplicationRecord]) -> dict[str, object]:
        self.completed_records = list(records)
        return {
            "summary": {
                "cache_candidate_count": 5,
                "affected_invoice_count": 5,
                "linked_existing_invoice_count": 5,
                "created_invoice_count": 0,
            }
        }


class FakePaymentStatusRepository:
    def __init__(
        self,
        statuses: dict[str, OAPaymentStatusRecord] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._statuses = dict(statuses or {})
        self._error = error

    def list_payment_statuses(self) -> dict[str, OAPaymentStatusRecord]:
        if self._error is not None:
            raise self._error
        return dict(self._statuses)


class FakePendingPaymentSourceSnapshotRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def commit_authoritative_snapshot(self, **kwargs: object) -> OaPendingPaymentSourceSnapshotResult:
        self.calls.append(dict(kwargs))
        statuses = kwargs.get("payment_statuses") if isinstance(kwargs.get("payment_statuses"), dict) else {}
        projection_records = (
            kwargs.get("projection_records") if isinstance(kwargs.get("projection_records"), list) else []
        )
        admission_records = (
            kwargs.get("admission_records") if isinstance(kwargs.get("admission_records"), list) else []
        )
        admission_count = sum(
            1 for record in admission_records if getattr(record, "workflow_status", "") == "in_progress"
        )
        completed_count = sum(
            1 for record in projection_records if getattr(record, "workflow_status", "") == "completed"
        )
        non_completed_count = len(admission_records) - completed_count
        return OaPendingPaymentSourceSnapshotResult(
            completed_projection_changed_scopes=(str(kwargs.get("scope_key") or "all"),),
            oa_pending_payment_changed_scopes=(str(kwargs.get("scope_key") or "all"),),
            payment_status_count=len(statuses),
            admission_count=admission_count,
            source_signatures={str(kwargs.get("scope_key") or "all"): "signature"},
            upserted_completed_count=completed_count,
            removed_non_completed_count=non_completed_count,
        )


def _oa(row_id: str, month: str, *, workflow_status: str) -> OAApplicationRecord:
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
