from __future__ import annotations

import unittest
from dataclasses import replace
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
    def test_targeted_attachment_refresh_updates_only_selected_completed_rows(self) -> None:
        selected = replace(
            _oa("oa-selected", "2026-06", workflow_status="completed"),
            attachment_file_count=2,
            attachment_invoices=[{"invoice_no": "001"}],
        )
        unselected = _oa("oa-unselected", "2026-06", workflow_status="completed")
        source = FakeSourceAdapter(
            months=["2026-06"],
            records_by_month={"2026-06": [selected, unselected]},
        )
        repository = FakeProjectionRepository()
        owner_repository = FakePendingPaymentSourceSnapshotRepository()
        promoter = FakeAttachmentInvoicePromoter()
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=repository,
            attachment_invoice_promoter=promoter,
            pending_payment_source_snapshot_repository=owner_repository,
        )

        result = service.handle_runtime_event(_targeted_event(["oa-selected"]))

        self.assertEqual(source.refresh_calls, [["oa-selected"]])
        self.assertEqual(
            [record.id for record in owner_repository.targeted_records],
            ["oa-selected"],
        )
        self.assertEqual(repository.stale_completed_scopes, [])
        self.assertEqual(repository.non_completed_scopes, [])
        self.assertEqual(promoter.records, [selected])
        self.assertTrue(promoter.ensure_matching)
        self.assertEqual(result["rows"][0]["importable_invoice_count"], 1)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["affected_scope_keys"], ["2026-06"])

    def test_targeted_attachment_refresh_fails_when_source_omits_a_row(self) -> None:
        source = FakeSourceAdapter(months=[], records_by_month={})
        repository = FakeProjectionRepository()
        promoter = FakeAttachmentInvoicePromoter()
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=repository,
            attachment_invoice_promoter=promoter,
            pending_payment_source_snapshot_repository=FakePendingPaymentSourceSnapshotRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "did not return row_ids"):
            service.handle_runtime_event(_targeted_event(["missing"]))

        self.assertEqual(repository.saved_records, [])
        self.assertEqual(promoter.call_count, 0)

    def test_targeted_attachment_refresh_promotes_in_progress_expense_claim(self) -> None:
        selected = replace(
            _oa(
                "oa-progress",
                "2026-06",
                workflow_status="in_progress",
                apply_type="日常报销",
            ),
            attachment_file_count=1,
            attachment_invoices=[{"invoice_no": "001"}],
            detail_fields={"paymentFlowId": "flow-progress"},
        )
        source = FakeSourceAdapter(
            months=["2026-06"],
            records_by_month={"2026-06": [selected]},
        )
        repository = FakeProjectionRepository()
        owner_repository = FakePendingPaymentSourceSnapshotRepository()
        promoter = FakeAttachmentInvoicePromoter()
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=repository,
            attachment_invoice_promoter=promoter,
            pending_payment_source_snapshot_repository=owner_repository,
        )

        result = service.handle_runtime_event(_targeted_event(["oa-progress"]))

        self.assertEqual(owner_repository.targeted_records, [selected])
        self.assertEqual(promoter.records, [selected])
        self.assertTrue(promoter.ensure_matching)
        self.assertEqual(result["promotion_summary"]["affected_invoice_count"], 5)
        self.assertEqual(result["upserted_count"], 1)

    def test_targeted_attachment_refresh_rejects_in_progress_payment_request(self) -> None:
        source = FakeSourceAdapter(
            months=["2026-06"],
            records_by_month={
                "2026-06": [_oa("oa-progress", "2026-06", workflow_status="in_progress")]
            },
        )
        owner_repository = FakePendingPaymentSourceSnapshotRepository()
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=FakeProjectionRepository(),
            attachment_invoice_promoter=FakeAttachmentInvoicePromoter(),
            pending_payment_source_snapshot_repository=owner_repository,
        )

        with self.assertRaisesRegex(RuntimeError, "in-progress expense claims only"):
            service.handle_runtime_event(_targeted_event(["oa-progress"]))

        self.assertEqual(owner_repository.targeted_records, [])

    def test_targeted_attachment_refresh_promotes_completed_and_in_progress_expense_claims(self) -> None:
        completed = _oa("oa-completed", "2026-06", workflow_status="completed")
        in_progress = replace(
            _oa(
                "oa-progress",
                "2026-06",
                workflow_status="in_progress",
                apply_type="日常报销",
            ),
            detail_fields={"paymentFlowId": "flow-progress"},
        )
        source = FakeSourceAdapter(
            months=["2026-06"],
            records_by_month={"2026-06": [completed, in_progress]},
        )
        owner_repository = FakePendingPaymentSourceSnapshotRepository()
        promoter = FakeAttachmentInvoicePromoter()
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=FakeProjectionRepository(),
            attachment_invoice_promoter=promoter,
            pending_payment_source_snapshot_repository=owner_repository,
        )

        result = service.handle_runtime_event(
            _targeted_event(["oa-completed", "oa-progress"])
        )

        self.assertEqual(owner_repository.targeted_records, [completed, in_progress])
        self.assertEqual(promoter.records, [completed, in_progress])
        self.assertTrue(promoter.ensure_matching)
        self.assertEqual(result["upserted_count"], 2)

    def test_targeted_attachment_refresh_fails_without_source_capability(self) -> None:
        service = OAProjectionSyncService(
            source_adapter=SimpleNamespace(),
            projection_repository=FakeProjectionRepository(),
            attachment_invoice_promoter=FakeAttachmentInvoicePromoter(),
            pending_payment_source_snapshot_repository=FakePendingPaymentSourceSnapshotRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "must expose refresh_application_record_attachments"):
            service.handle_runtime_event(_targeted_event(["oa-1"]))

    def test_targeted_attachment_refresh_propagates_ocr_failure_for_worker_retry(self) -> None:
        class FailingOcrSource:
            def refresh_application_record_attachments(
                self,
                row_ids: list[str],
            ) -> list[OAApplicationRecord]:
                raise RuntimeError(f"ocr_inference_failed:{','.join(row_ids)}")

        repository = FakeProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=FailingOcrSource(),
            projection_repository=repository,
            attachment_invoice_promoter=FakeAttachmentInvoicePromoter(),
            pending_payment_source_snapshot_repository=FakePendingPaymentSourceSnapshotRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "ocr_inference_failed"):
            service.handle_runtime_event(_targeted_event(["oa-1"]))

        self.assertEqual(repository.saved_records, [])
        self.assertEqual(repository.sync_runs[-1]["status"], "failed")
        self.assertEqual(
            repository.sync_runs[-1]["sync_type"],
            "oa_attachment_refresh",
        )

    def test_targeted_attachment_refresh_rejects_scope_drift_before_write(self) -> None:
        source = FakeSourceAdapter(
            months=["2026-07"],
            records_by_month={
                "2026-07": [_oa("oa-moved", "2026-07", workflow_status="completed")]
            },
        )
        repository = FakeProjectionRepository()
        promoter = FakeAttachmentInvoicePromoter()
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=repository,
            attachment_invoice_promoter=promoter,
            pending_payment_source_snapshot_repository=FakePendingPaymentSourceSnapshotRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "source scopes changed"):
            service.handle_runtime_event(_targeted_event(["oa-moved"]))

        self.assertEqual(repository.saved_records, [])
        self.assertEqual(repository.targeted_scopes, [])
        self.assertEqual(promoter.call_count, 0)

    def test_targeted_attachment_refresh_rejects_artifact_processing_failure(self) -> None:
        selected = replace(
            _oa("oa-failed", "2026-06", workflow_status="completed"),
            attachment_artifacts=[{"parse_status": "download_failed"}],
        )
        source = FakeSourceAdapter(
            months=["2026-06"],
            records_by_month={"2026-06": [selected]},
        )
        repository = FakeProjectionRepository()
        promoter = FakeAttachmentInvoicePromoter()
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=repository,
            attachment_invoice_promoter=promoter,
            pending_payment_source_snapshot_repository=FakePendingPaymentSourceSnapshotRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "failed to download or parse"):
            service.handle_runtime_event(_targeted_event(["oa-failed"]))

        self.assertEqual(repository.saved_records, [])
        self.assertEqual(promoter.call_count, 0)

    def test_targeted_attachment_refresh_accepts_non_invoice_attachment_evidence(self) -> None:
        selected = replace(
            _oa("oa-no-evidence", "2026-06", workflow_status="completed"),
            attachment_file_count=1,
            attachment_artifacts=[{"parse_status": "no_evidence"}],
        )
        source = FakeSourceAdapter(
            months=["2026-06"],
            records_by_month={"2026-06": [selected]},
        )
        repository = FakeProjectionRepository()
        owner_repository = FakePendingPaymentSourceSnapshotRepository()
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=repository,
            attachment_invoice_promoter=FakeAttachmentInvoicePromoter(),
            pending_payment_source_snapshot_repository=owner_repository,
        )

        result = service.handle_runtime_event(_targeted_event(["oa-no-evidence"]))

        self.assertEqual(result["rows"][0]["unrecognized_attachment_count"], 1)
        self.assertEqual([record.id for record in owner_repository.targeted_records], ["oa-no-evidence"])

    def test_targeted_attachment_refresh_validates_promoter_before_source_io(self) -> None:
        source = FakeSourceAdapter(
            months=["2026-06"],
            records_by_month={
                "2026-06": [_oa("oa-1", "2026-06", workflow_status="completed")]
            },
        )
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=FakeProjectionRepository(),
            attachment_invoice_promoter=SimpleNamespace(),
            pending_payment_source_snapshot_repository=FakePendingPaymentSourceSnapshotRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "requires the attachment invoice promoter"):
            service.handle_runtime_event(_targeted_event(["oa-1"]))

        self.assertEqual(source.refresh_calls, [])

    def test_targeted_attachment_refresh_rejects_incomplete_owner_write_result(self) -> None:
        class InvalidOwnerRepository:
            def commit_targeted_attachment_refresh(
                self,
                *,
                records: list[OAApplicationRecord],
            ) -> SimpleNamespace:
                return SimpleNamespace(upserted_completed_count=len(records))

        promoter = FakeAttachmentInvoicePromoter()
        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06"],
                records_by_month={
                    "2026-06": [_oa("oa-1", "2026-06", workflow_status="completed")]
                },
            ),
            projection_repository=FakeProjectionRepository(),
            attachment_invoice_promoter=promoter,
            pending_payment_source_snapshot_repository=InvalidOwnerRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "owner writer returned an invalid result"):
            service.handle_runtime_event(_targeted_event(["oa-1"]))

        self.assertEqual(promoter.call_count, 0)

    def test_payment_status_source_and_postgres_snapshot_must_be_configured_together(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires pending_payment_source_snapshot_repository"):
            OAProjectionSyncService(
                source_adapter=FakeSourceAdapter(months=[], records_by_month={}),
                projection_repository=FakeProjectionRepository(),
                payment_status_repository=FakePaymentStatusRepository({}),
            )

    def test_targeted_owner_repository_does_not_force_optional_payment_snapshot_sync(self) -> None:
        completed = _oa("oa-1", "2026-06", workflow_status="completed")
        projection_repository = FakeProjectionRepository()
        owner_repository = FakePendingPaymentSourceSnapshotRepository()
        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06"],
                records_by_month={"2026-06": [completed]},
            ),
            projection_repository=projection_repository,
            pending_payment_source_snapshot_repository=owner_repository,
        )

        service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(projection_repository.saved_records, [completed])
        self.assertEqual(owner_repository.calls, [])

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

        self.assertEqual([record.id for record in promoter.records], ["oa-pay-completed"])
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

    def test_attachment_invoice_promotion_only_reads_changed_completed_scopes(self) -> None:
        records = [
            _oa("oa-june", "2026-06", workflow_status="completed"),
            _oa("oa-july", "2026-07", workflow_status="completed"),
        ]
        promoter = FakeAttachmentInvoicePromoter()

        class JuneOnlySnapshotRepository(FakePendingPaymentSourceSnapshotRepository):
            def commit_authoritative_snapshot(self, **kwargs: object) -> OaPendingPaymentSourceSnapshotResult:
                self.calls.append(dict(kwargs))
                return OaPendingPaymentSourceSnapshotResult(
                    completed_projection_changed_scopes=("2026-06",),
                    oa_pending_payment_changed_scopes=(),
                    payment_status_count=0,
                    admission_count=0,
                    source_signatures={},
                    upserted_completed_count=1,
                )

        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06", "2026-07"],
                records_by_month={"2026-06": [records[0]], "2026-07": [records[1]]},
            ),
            projection_repository=FakeProjectionRepository(),
            attachment_invoice_promoter=promoter,
            payment_status_repository=FakePaymentStatusRepository({}),
            pending_payment_source_snapshot_repository=JuneOnlySnapshotRepository(),
        )

        service.handle_runtime_event(_event("all"))

        self.assertEqual([record.id for record in promoter.records], ["oa-june"])
        self.assertEqual(promoter.call_count, 1)

    def test_pending_admission_change_promotes_in_progress_expense_claim_only(self) -> None:
        in_progress_expense = _oa(
            "oa-progress-expense",
            "2026-06",
            workflow_status="in_progress",
            apply_type="日常报销",
        )
        in_progress_payment = _oa(
            "oa-progress-payment",
            "2026-06",
            workflow_status="in_progress",
        )
        promoter = FakeAttachmentInvoicePromoter()

        class AdmissionChangedSnapshotRepository(FakePendingPaymentSourceSnapshotRepository):
            def commit_authoritative_snapshot(self, **kwargs: object) -> OaPendingPaymentSourceSnapshotResult:
                self.calls.append(dict(kwargs))
                return OaPendingPaymentSourceSnapshotResult(
                    completed_projection_changed_scopes=(),
                    oa_pending_payment_changed_scopes=("2026-06",),
                    payment_status_count=2,
                    admission_count=2,
                    source_signatures={"2026-06": "signature"},
                    pending_admission_changed_scopes=("2026-06",),
                )

        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06"],
                records_by_month={
                    "2026-06": [in_progress_expense, in_progress_payment]
                },
                projection_records_by_month={"2026-06": []},
            ),
            projection_repository=FakeProjectionRepository(),
            attachment_invoice_promoter=promoter,
            payment_status_repository=FakePaymentStatusRepository({}),
            pending_payment_source_snapshot_repository=AdmissionChangedSnapshotRepository(),
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(promoter.records, [in_progress_expense])
        self.assertEqual(result["pending_admission_changed_scope_keys"], ["2026-06"])

    def test_payment_status_only_change_does_not_repromote_pending_attachments(self) -> None:
        in_progress_expense = _oa(
            "oa-progress-expense",
            "2026-06",
            workflow_status="in_progress",
            apply_type="日常报销",
        )
        promoter = FakeAttachmentInvoicePromoter()

        class PaymentStatusOnlySnapshotRepository(FakePendingPaymentSourceSnapshotRepository):
            def commit_authoritative_snapshot(self, **kwargs: object) -> OaPendingPaymentSourceSnapshotResult:
                self.calls.append(dict(kwargs))
                return OaPendingPaymentSourceSnapshotResult(
                    completed_projection_changed_scopes=(),
                    oa_pending_payment_changed_scopes=("2026-06",),
                    payment_status_count=1,
                    admission_count=1,
                    source_signatures={"2026-06": "signature"},
                    pending_admission_changed_scopes=(),
                )

        service = OAProjectionSyncService(
            source_adapter=FakeSourceAdapter(
                months=["2026-06"],
                records_by_month={"2026-06": [in_progress_expense]},
                projection_records_by_month={"2026-06": []},
            ),
            projection_repository=FakeProjectionRepository(),
            attachment_invoice_promoter=promoter,
            payment_status_repository=FakePaymentStatusRepository({}),
            pending_payment_source_snapshot_repository=PaymentStatusOnlySnapshotRepository(),
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(promoter.call_count, 0)
        self.assertEqual(result["pending_payment_affected_scope_keys"], ["2026-06"])
        self.assertEqual(result["pending_admission_changed_scope_keys"], [])

    def test_unchanged_completed_snapshot_skips_attachment_invoice_promotion(self) -> None:
        records = [_oa("oa-unchanged", "2026-06", workflow_status="completed")]
        promoter = FakeAttachmentInvoicePromoter()

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
            attachment_invoice_promoter=promoter,
            payment_status_repository=FakePaymentStatusRepository({}),
            pending_payment_source_snapshot_repository=UnchangedSnapshotRepository(),
        )

        result = service.handle_runtime_event(_event("2026-06"))

        self.assertEqual(promoter.call_count, 0)
        self.assertEqual(result["scanned_oa_attachment_invoice_candidate_count"], 0)

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
        self.refresh_calls: list[list[str]] = []

    def refresh_application_record_attachments(
        self,
        row_ids: list[str],
    ) -> list[OAApplicationRecord]:
        self.refresh_calls.append(list(row_ids))
        records_by_id = {
            record.id: record
            for records in self._records_by_month.values()
            for record in records
        }
        return [records_by_id[row_id] for row_id in row_ids if row_id in records_by_id]

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
        self.targeted_scopes: list[str] = []

    def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
        self.saved_records.extend(records)
        return len(records)

    def upsert_targeted_application_records(
        self,
        records: list[OAApplicationRecord],
        *,
        scope_key: str,
    ) -> int:
        self.targeted_scopes.append(scope_key)
        self.saved_records.extend(records)
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


class FakeAttachmentInvoicePromoter:
    def __init__(self) -> None:
        self.records: list[OAApplicationRecord] = []
        self.call_count = 0
        self.ensure_matching = False

    def promote_records(
        self,
        records: list[OAApplicationRecord],
        *,
        ensure_matching: bool = False,
    ) -> dict[str, object]:
        self.call_count += 1
        self.records = list(records)
        self.ensure_matching = ensure_matching
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
        self.targeted_records: list[OAApplicationRecord] = []

    def commit_targeted_attachment_refresh(
        self,
        *,
        records: list[OAApplicationRecord],
    ) -> OaPendingPaymentSourceSnapshotResult:
        self.targeted_records = list(records)
        completed_count = sum(
            1 for record in records if record.workflow_status == "completed"
        )
        pending_count = sum(
            1 for record in records if record.workflow_status == "in_progress"
        )
        pending_changed_scopes = tuple(
            sorted(
                {
                    record.month
                    for record in records
                    if record.workflow_status == "in_progress" and record.month
                }
            )
        )
        return OaPendingPaymentSourceSnapshotResult(
            completed_projection_changed_scopes=(),
            oa_pending_payment_changed_scopes=(),
            payment_status_count=0,
            admission_count=pending_count,
            source_signatures={},
            pending_admission_changed_scopes=pending_changed_scopes,
            upserted_completed_count=completed_count,
            upserted_pending_count=pending_count,
        )

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
            pending_admission_changed_scopes=(
                (str(kwargs.get("scope_key") or "all"),)
                if admission_count
                else ()
            ),
            upserted_completed_count=completed_count,
            removed_non_completed_count=non_completed_count,
        )


def _oa(
    row_id: str,
    month: str,
    *,
    workflow_status: str,
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


def _targeted_event(row_ids: list[str]) -> RuntimeQueueEvent:
    event = _event("2026-06")
    return replace(
        event,
        payload={
            "operation": "refresh_attachments",
            "row_ids": row_ids,
            "affected_scope_keys": ["2026-06"],
        },
    )


if __name__ == "__main__":
    unittest.main()
