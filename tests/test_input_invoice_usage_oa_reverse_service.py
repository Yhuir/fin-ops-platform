from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_oa_reverse_service import (
    InMemoryInputInvoiceUsageOaReverseBatchRepository,
    InputInvoiceUsageOaEvidence,
    InputInvoiceUsageOaReverseMissingClientError,
    InputInvoiceUsageOaReverseService,
    InputInvoiceUsageOaReverseStatus,
    InputInvoiceUsageOaReverseVersionConflictError,
)
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from tests.test_pending_invoice_service import FakeWorkbenchRelationFacade


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = records

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]


class FakeOaDraftClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        self.requests.append({"form_id": form_id, "payload": payload})
        return "oa-draft-001", "https://oa.example/drafts/oa-draft-001"


class FakeTargetOaDraftClientProvider:
    def __init__(self, client: FakeOaDraftClient | None = None, *, fail: bool = False) -> None:
        self.client = client or FakeOaDraftClient()
        self.fail = fail
        self.requested_codes: list[str] = []

    def draft_client_for(self, target_applicant_code: str) -> FakeOaDraftClient:
        self.requested_codes.append(target_applicant_code)
        if self.fail:
            raise InputInvoiceUsageOaReverseMissingClientError("目标 OA 申请人凭据未配置。")
        return self.client


class StaticEvidenceProvider:
    def __init__(self, evidence: InputInvoiceUsageOaEvidence | None) -> None:
        self.evidence = evidence

    def find_oa_draft_evidence(self, batch: object) -> InputInvoiceUsageOaEvidence | None:
        return self.evidence


class InputInvoiceUsageOaReverseServiceTests(unittest.TestCase):
    def test_preview_returns_backend_candidates_rejections_display_rows_and_hash(self) -> None:
        vendor = self._counterparty("vendor", "供应商")
        available = self._invoice("inv-available", "9401", vendor, total_with_tax="99.72")
        bound = self._invoice("inv-bound", "9402", vendor, total_with_tax="1.00")
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-bound", [bound.id, "oa-bound"])
        service = self._service(
            invoices=[available, bound],
            pair_service=pair_service,
            oa_projection=StaticOAProjection([self._oa("oa-bound", "李四", "1.00")]),
        )

        preview = service.preview(
            {
                "source": "explicitSelection",
                "invoiceIds": ["inv-available", "inv-bound", "inv-missing"],
                "targetApplicantCode": "chen_xiuyun",
            },
            can_create_draft=True,
        )

        self.assertEqual(preview["invoiceCount"], 1)
        self.assertEqual(preview["totalWithTax"], "99.72")
        self.assertEqual(preview["targetApplicantName"], "陈秀云")
        self.assertIn(
            {"code": "zhou_jieying", "name": "周洁莹"},
            preview["targetApplicants"],
        )
        self.assertEqual(preview["invoiceRows"][0]["invoiceId"], "inv-available")
        self.assertEqual(preview["invoiceRows"][0]["sellerName"], "供应商")
        reason_codes = {item["reasonCode"] for item in preview["rejectedInvoices"]}
        self.assertEqual(reason_codes, {"already_has_active_oa", "invoice_not_found"})
        self.assertTrue(str(preview["previewId"]).startswith("oa_reverse_preview_"))
        self.assertEqual(len(str(preview["previewHash"])), 64)
        self.assertTrue(preview["canCreateDraft"])
        self.assertEqual(preview["nextAction"], "create_batch")

    def test_create_batch_is_idempotent_and_persists_audit_metadata(self) -> None:
        service = self._service(invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))])
        preview = service.preview({"invoiceIds": ["inv-1"], "targetApplicantCode": "chen_xiuyun"}, can_create_draft=True)

        first = service.create_batch(
            {
                "invoiceIds": ["inv-1"],
                "targetApplicantCode": "chen_xiuyun",
                "expectedPreviewHash": preview["previewHash"],
                "idempotencyKey": "create-key-1",
            },
            actor_id="user-1",
            can_mutate=True,
        )
        second = service.create_batch(
            {
                "invoiceIds": ["inv-1"],
                "targetApplicantCode": "chen_xiuyun",
                "expectedPreviewHash": preview["previewHash"],
                "idempotencyKey": "create-key-1",
            },
            actor_id="user-1",
            can_mutate=True,
        )

        self.assertEqual(first["batchId"], second["batchId"])
        self.assertEqual(first["status"], InputInvoiceUsageOaReverseStatus.DRAFT.value)
        self.assertEqual(first["version"], 1)
        self.assertEqual(first["createdBy"], "user-1")
        self.assertEqual(first["auditEvents"][0]["eventType"], "oa_reverse_batch_created")

    def test_create_oa_draft_from_selection_creates_internal_batch_and_uses_target_provider(self) -> None:
        service = self._service(invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))])
        provider = FakeTargetOaDraftClientProvider()
        preview = service.preview({"invoiceIds": ["inv-1"], "targetApplicantCode": "zhou_jieying"}, can_create_draft=True)

        drafted = service.create_oa_draft_from_selection(
            {
                "invoiceIds": ["inv-1"],
                "targetApplicantCode": "zhou_jieying",
                "expectedPreviewHash": preview["previewHash"],
                "idempotencyKey": "one-step-key-1",
            },
            actor_id="login-user",
            can_mutate=True,
            oa_client_provider=provider,
        )

        self.assertEqual(drafted["status"], InputInvoiceUsageOaReverseStatus.OA_DRAFT_CREATED.value)
        self.assertEqual(provider.requested_codes, ["zhou_jieying"])
        self.assertEqual(provider.client.requests[0]["payload"]["data"]["applicant"], "周洁莹")
        self.assertIn("input_invoice_usage_oa_reverse_batch_", drafted["batchId"])

    def test_create_oa_draft_from_selection_missing_target_credential_does_not_create_batch(self) -> None:
        service = self._service(invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))])
        provider = FakeTargetOaDraftClientProvider(fail=True)
        preview = service.preview({"invoiceIds": ["inv-1"], "targetApplicantCode": "chen_xiuyun"}, can_create_draft=True)

        with self.assertRaises(InputInvoiceUsageOaReverseMissingClientError):
            service.create_oa_draft_from_selection(
                {
                    "invoiceIds": ["inv-1"],
                    "targetApplicantCode": "chen_xiuyun",
                    "expectedPreviewHash": preview["previewHash"],
                    "idempotencyKey": "one-step-missing-credential",
                },
                actor_id="login-user",
                can_mutate=True,
                oa_client_provider=provider,
            )

        self.assertEqual(provider.requested_codes, ["chen_xiuyun"])
        self.assertIsNone(service._repository.find_batch_by_create_idempotency_key("one-step-missing-credential:batch"))

    def test_create_oa_draft_rejects_stale_expected_version(self) -> None:
        service = self._service(invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))])
        batch = self._create_batch(service, ["inv-1"])

        with self.assertRaises(InputInvoiceUsageOaReverseVersionConflictError) as context:
            service.create_oa_draft(
                str(batch["batchId"]),
                expected_version=99,
                idempotency_key="draft-key-1",
                actor_id="user-1",
                can_mutate=True,
                oa_client=FakeOaDraftClient(),
            )

        self.assertEqual(context.exception.actual_version, 1)

    def test_create_oa_draft_missing_client_records_failed_recoverable_batch_without_fake_success(self) -> None:
        service = self._service(invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))])
        batch = self._create_batch(service, ["inv-1"])

        with self.assertRaises(InputInvoiceUsageOaReverseMissingClientError):
            service.create_oa_draft(
                str(batch["batchId"]),
                expected_version=int(batch["version"]),
                idempotency_key="draft-key-1",
                actor_id="user-1",
                can_mutate=True,
            )

        failed = service.get_batch(str(batch["batchId"]))
        self.assertEqual(failed["status"], InputInvoiceUsageOaReverseStatus.OA_DRAFT_FAILED.value)
        self.assertEqual(failed["oaDetectionStatus"], "draft_failed")
        self.assertIsNone(failed["oaDraftId"])
        self.assertEqual(failed["version"], 2)

    def test_revoke_releases_local_draft_binding_and_keeps_external_draft_metadata_in_detection_payload(self) -> None:
        invalidations: list[tuple[list[str], str]] = []
        service = self._service(
            invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))],
            oa_client=FakeOaDraftClient(),
            read_model_invalidator=lambda months, reason: invalidations.append((months, reason)),
        )
        batch = self._create_batch(service, ["inv-1"])
        drafted = service.create_oa_draft(
            str(batch["batchId"]),
            expected_version=int(batch["version"]),
            idempotency_key="draft-key-1",
            actor_id="user-1",
            can_mutate=True,
        )

        revoked = service.revoke_oa_draft(
            str(batch["batchId"]),
            reason="用户撤销本地绑定",
            expected_version=int(drafted["version"]),
            idempotency_key="revoke-key-1",
            actor_id="user-1",
            can_mutate=True,
        )

        self.assertEqual(revoked["status"], InputInvoiceUsageOaReverseStatus.NOT_SUBMITTED.value)
        self.assertIsNone(revoked["oaDraftId"])
        self.assertEqual(revoked["oaDetectionStatus"], "revoked")
        self.assertEqual(revoked["oaDetectionPayload"]["revokedOaDraftId"], "oa-draft-001")
        self.assertIn((["2026-05"], "input_invoice_usage_oa_reverse_draft_revoked"), invalidations)

    def test_create_oa_draft_uses_selected_applicant_form_data_and_waits_for_user_submission_choice(self) -> None:
        client = FakeOaDraftClient()
        service = self._service(
            invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))],
            oa_client=client,
        )
        preview = service.preview({"invoiceIds": ["inv-1"], "targetApplicantCode": "zhou_jieying"}, can_create_draft=True)
        batch = service.create_batch(
            {
                "invoiceIds": ["inv-1"],
                "targetApplicantCode": "zhou_jieying",
                "expectedPreviewHash": preview["previewHash"],
                "idempotencyKey": "create-key-selected-applicant",
            },
            actor_id="login-user",
            can_mutate=True,
        )

        drafted = service.create_oa_draft(
            str(batch["batchId"]),
            expected_version=int(batch["version"]),
            idempotency_key="draft-key-selected-applicant",
            actor_id="login-user",
            can_mutate=True,
        )

        self.assertEqual(drafted["status"], "oa_draft_created")
        self.assertEqual(drafted["oaDetectionStatus"], "draft_created")
        self.assertTrue(drafted["canConfirmSubmission"])
        self.assertFalse(drafted["canRefreshStatus"])
        request_payload = client.requests[0]["payload"]
        form_data = request_payload["data"]
        self.assertEqual(request_payload["formId"], 2)
        self.assertIs(request_payload["isDraft"], True)
        self.assertEqual(form_data["userName"], "周洁莹")
        self.assertEqual(form_data["applicant"], "周洁莹")
        self.assertIn(str(batch["batchId"]), form_data["cause"])

        confirmed = service.manual_oa_status(
            str(batch["batchId"]),
            decision="submitted",
            reason="",
            expected_version=int(drafted["version"]),
            idempotency_key="confirm-submitted-key",
            actor_id="login-user",
            can_mutate=True,
        )

        self.assertEqual(confirmed["status"], "submitted_confirmed")
        self.assertEqual(confirmed["oaDetectionStatus"], "user_confirmed_submitted")
        self.assertFalse(confirmed["canRefreshStatus"])

        history = service.submitted_history()
        self.assertEqual(len(history["items"]), 1)
        self.assertEqual(history["items"][0]["targetApplicantName"], "周洁莹")
        self.assertEqual(history["items"][0]["totalWithTax"], "100.00")
        self.assertEqual(history["items"][0]["invoiceCount"], 1)
        self.assertEqual(history["items"][0]["invoices"][0]["invoiceNo"], "1001")
        self.assertNotIn("batchId", history["items"][0])
        self.assertNotIn("invoiceIds", history["items"][0])

    def test_user_can_mark_created_oa_draft_not_submitted_and_return_to_create_state(self) -> None:
        service = self._service(
            invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))],
            oa_client=FakeOaDraftClient(),
        )
        batch = self._create_batch(service, ["inv-1"])
        drafted = service.create_oa_draft(
            str(batch["batchId"]),
            expected_version=int(batch["version"]),
            idempotency_key="draft-key-1",
            actor_id="user-1",
            can_mutate=True,
        )

        marked = service.manual_oa_status(
            str(batch["batchId"]),
            decision="not_submitted",
            reason="",
            expected_version=int(drafted["version"]),
            idempotency_key="confirm-not-submitted-key",
            actor_id="user-1",
            can_mutate=True,
        )

        self.assertEqual(marked["status"], InputInvoiceUsageOaReverseStatus.NOT_SUBMITTED.value)
        self.assertEqual(marked["oaDetectionStatus"], "user_confirmed_not_submitted")
        self.assertIsNone(marked["oaDraftId"])
        self.assertIsNone(marked["oaDraftUrl"])
        self.assertFalse(marked["canRevoke"])
        self.assertTrue(marked["canCreateDraft"])

    def test_status_refresh_without_evidence_does_not_create_relation_or_complete_batch(self) -> None:
        relation_calls: list[object] = []
        service = self._service(
            invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))],
            oa_client=FakeOaDraftClient(),
            evidence_provider=StaticEvidenceProvider(None),
            relation_writer=lambda batch, evidence: relation_calls.append((batch, evidence)),
        )
        batch = self._create_batch(service, ["inv-1"])
        drafted = service.create_oa_draft(
            str(batch["batchId"]),
            expected_version=int(batch["version"]),
            idempotency_key="draft-key-1",
            actor_id="user-1",
            can_mutate=True,
        )
        detecting = self._force_detection_state(service, str(drafted["batchId"]), int(drafted["version"]))

        refreshed = service.refresh_oa_status(
            str(batch["batchId"]),
            expected_version=int(detecting.version),
            actor_id="user-1",
            can_mutate=True,
        )

        self.assertEqual(refreshed["status"], InputInvoiceUsageOaReverseStatus.OA_DETECTION_MISSING.value)
        self.assertEqual(refreshed["oaDetectionStatus"], "missing")
        self.assertIsNone(refreshed["oaRowId"])
        self.assertEqual(relation_calls, [])

    def test_status_refresh_with_evidence_updates_detection_and_calls_relation_writer_once(self) -> None:
        relation_calls: list[tuple[object, InputInvoiceUsageOaEvidence]] = []
        evidence = InputInvoiceUsageOaEvidence(
            oa_row_id="oa-projected-001",
            process_status="进行中",
            candidates=[{"oaRowId": "oa-projected-001"}],
        )
        service = self._service(
            invoices=[self._invoice("inv-1", "1001", self._counterparty("vendor", "供应商"))],
            oa_client=FakeOaDraftClient(),
            evidence_provider=StaticEvidenceProvider(evidence),
            relation_writer=lambda batch, evidence: relation_calls.append((batch, evidence)),
        )
        batch = self._create_batch(service, ["inv-1"])
        drafted = service.create_oa_draft(
            str(batch["batchId"]),
            expected_version=int(batch["version"]),
            idempotency_key="draft-key-1",
            actor_id="user-1",
            can_mutate=True,
        )
        detecting = self._force_detection_state(service, str(drafted["batchId"]), int(drafted["version"]))

        refreshed = service.refresh_oa_status(
            str(batch["batchId"]),
            expected_version=int(detecting.version),
            actor_id="user-1",
            can_mutate=True,
        )

        self.assertEqual(refreshed["status"], InputInvoiceUsageOaReverseStatus.OA_DETECTED.value)
        self.assertEqual(refreshed["oaDetectionStatus"], "detected")
        self.assertEqual(refreshed["oaRowId"], "oa-projected-001")
        self.assertEqual(len(relation_calls), 1)

    def _create_batch(self, service: InputInvoiceUsageOaReverseService, invoice_ids: list[str]) -> dict[str, object]:
        preview = service.preview({"invoiceIds": invoice_ids, "targetApplicantCode": "chen_xiuyun"}, can_create_draft=True)
        return service.create_batch(
            {
                "invoiceIds": invoice_ids,
                "targetApplicantCode": "chen_xiuyun",
                "expectedPreviewHash": preview["previewHash"],
                "idempotencyKey": f"create-key-{'-'.join(invoice_ids)}",
            },
            actor_id="user-1",
            can_mutate=True,
        )

    @staticmethod
    def _force_detection_state(
        service: InputInvoiceUsageOaReverseService,
        batch_id: str,
        current_version: int,
    ):
        batch = service._repository.get_batch(batch_id)
        batch.status = InputInvoiceUsageOaReverseStatus.OA_SUBMISSION_DETECTING.value
        batch.oa_detection_status = "legacy_detection_pending"
        batch.version = current_version + 1
        service._repository.save_batch(batch)
        return batch

    @staticmethod
    def _counterparty(counterparty_id: str, name: str) -> Counterparty:
        return Counterparty(id=counterparty_id, name=name, normalized_name=name, counterparty_type="supplier")

    @staticmethod
    def _invoice(
        invoice_id: str,
        invoice_no: str,
        counterparty: Counterparty,
        *,
        total_with_tax: str = "100.00",
        invoice_date: str = "2026-05-20",
    ) -> Invoice:
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.INPUT,
            invoice_no=invoice_no,
            counterparty=counterparty,
            amount=Decimal(total_with_tax) - Decimal("6.00"),
            signed_amount=Decimal(total_with_tax) - Decimal("6.00"),
            invoice_date=invoice_date,
            seller_name=counterparty.name,
            seller_tax_no="91530000SELLER",
            buyer_tax_no="91530000BUYER",
            tax_rate="6%",
            tax_amount=Decimal("6.00"),
            total_with_tax=Decimal(total_with_tax),
            taxable_item_name="服务费",
            source_batch_id="batch-001",
            source_links=[{"kind": "import_batch", "id": "batch-001"}],
        )

    @staticmethod
    def _oa(oa_id: str, applicant: str, amount: str) -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month="2026-05",
            section="进行中",
            case_id=f"OA-{oa_id}",
            applicant=applicant,
            project_name=f"{applicant}项目",
            apply_type="报销",
            amount=amount,
            counterparty_name="供应商",
            reason="费用报销",
            relation_code="in_progress",
            relation_label="进行中",
            relation_tone="success",
        )

    @staticmethod
    def _relation(pair_service: WorkbenchPairRelationService, case_id: str, row_ids: list[str]) -> None:
        row_types = ["invoice" if row_id.startswith("inv") else "oa" for row_id in row_ids]
        pair_service.create_active_relation(
            case_id=case_id,
            row_ids=row_ids,
            row_types=row_types,
            relation_mode="manual_confirmed",
            created_by="tester",
            amount_check={"matched": True},
        )

    @staticmethod
    def _service(
        *,
        invoices: list[Invoice],
        pair_service: WorkbenchPairRelationService | None = None,
        oa_projection: object | None = None,
        oa_client: object | None = None,
        evidence_provider: object | None = None,
        relation_writer: object | None = None,
        read_model_invalidator: object | None = None,
    ) -> InputInvoiceUsageOaReverseService:
        query_service = InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(existing_invoices=invoices),
            relation_facade=FakeWorkbenchRelationFacade.from_pair_service(
                pair_service=pair_service or WorkbenchPairRelationService(),
                transactions=[],
                invoices=invoices,
                oa_projection=oa_projection,
            ),
            oa_projection=oa_projection,
        )
        return InputInvoiceUsageOaReverseService(
            query_service=query_service,
            repository=InMemoryInputInvoiceUsageOaReverseBatchRepository(),
            oa_client=oa_client,
            evidence_provider=evidence_provider,
            relation_writer=relation_writer,
            read_model_invalidator=read_model_invalidator,
        )


if __name__ == "__main__":
    unittest.main()
