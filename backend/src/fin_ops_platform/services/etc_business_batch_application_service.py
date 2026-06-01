from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Iterable

from fin_ops_platform.services.etc_oa_detection import EtcOADetectionContext, EtcOADetectionService
from fin_ops_platform.services.etc_reconciliation_models import ParseIssueSeverity, SourceFileKind
from fin_ops_platform.services.etc_service import (
    ETC_BUSINESS_BATCH_MANUAL_FALLBACK_STATUSES,
    EtcBusinessBatch,
    EtcBusinessBatchInvalidTransitionError,
    EtcBusinessBatchNotFoundError,
    EtcBusinessBatchStatus,
    EtcService,
    UploadedEtcZipFile,
)


ETC_BUSINESS_OA_DETECTION_EVENT_TYPE = "etc_business.oa_detection.refresh"


@dataclass(frozen=True, slots=True)
class EtcBusinessBatchActor:
    user_id: str | None = None
    username: str | None = None
    dept_id: str | None = None
    can_admin_access: bool = False
    can_mutate_data: bool = False

    @property
    def actor_id(self) -> str:
        return str(self.username or self.user_id or "web_finance_user").strip() or "web_finance_user"


class EtcBusinessBatchScopeError(PermissionError):
    pass


class EtcBusinessBatchApplicationService:
    def __init__(
        self,
        *,
        etc_service: EtcService,
        reconciliation_task_service: Any,
        queue_repository: Any | None = None,
        oa_client_factory: Callable[[dict[str, str] | None], Any] | None = None,
        oa_adapter_provider: Callable[[], Any] | None = None,
        sync_etc_invoices_to_canonical_invoices: Callable[[list[object]], list[str]] | None = None,
        refresh_after_etc_invoice_sync: Callable[[list[str], str], None] | None = None,
    ) -> None:
        self._etc_service = etc_service
        self._reconciliation_task_service = reconciliation_task_service
        self._queue_repository = queue_repository
        self._oa_client_factory = oa_client_factory
        self._oa_adapter_provider = oa_adapter_provider
        self._sync_etc_invoices_to_canonical_invoices = sync_etc_invoices_to_canonical_invoices
        self._refresh_after_etc_invoice_sync = refresh_after_etc_invoice_sync

    def list_batches_payload(self, query: dict[str, list[str]], *, actor: EtcBusinessBatchActor) -> dict[str, object]:
        requested_status = str((query.get("status") or [None])[0] or "").strip()
        task_id = (query.get("taskId") or query.get("task_id") or [None])[0]
        batches = [
            batch
            for batch in self._etc_service.list_business_batches(task_id=task_id)
            if self._can_access_batch(actor, batch)
        ]
        month = str((query.get("month") or [None])[0] or "").strip()
        plate = str((query.get("plate") or [None])[0] or "").strip().lower()
        keyword = str((query.get("keyword") or [None])[0] or "").strip().lower()
        if month or plate or keyword:
            batches = [batch for batch in batches if self._matches_list_filters(batch, month=month, plate=plate, keyword=keyword)]
        active_statuses = {
            EtcBusinessBatchStatus.DRAFT.value,
            EtcBusinessBatchStatus.REVIEWING.value,
            EtcBusinessBatchStatus.READY_FOR_IMPORT.value,
            EtcBusinessBatchStatus.IMPORTING.value,
            EtcBusinessBatchStatus.IMPORTED.value,
            EtcBusinessBatchStatus.IMPORT_FAILED.value,
            EtcBusinessBatchStatus.IMPORT_PARTIAL_FAILED.value,
            EtcBusinessBatchStatus.OA_DRAFT_CREATING.value,
            EtcBusinessBatchStatus.OA_DRAFT_FAILED.value,
            EtcBusinessBatchStatus.OA_SUBMISSION_DETECTING.value,
            EtcBusinessBatchStatus.OA_DETECTION_TIMEOUT.value,
            EtcBusinessBatchStatus.OA_DETECTION_CONFLICT.value,
            EtcBusinessBatchStatus.OA_DETECTION_UNAVAILABLE.value,
            EtcBusinessBatchStatus.NOT_SUBMITTED.value,
            EtcBusinessBatchStatus.MANUALLY_MARKED_NOT_SUBMITTED.value,
            EtcBusinessBatchStatus.MIGRATION_CONFLICT.value,
            EtcBusinessBatchStatus.BUSINESS_BATCH_INVARIANT_BROKEN.value,
        }
        submitted_statuses = {
            EtcBusinessBatchStatus.OA_SUBMITTED.value,
            EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value,
            EtcBusinessBatchStatus.CLOSED.value,
        }
        counts = {
            "active": sum(1 for batch in batches if str(batch.status) in active_statuses),
            "submitted": sum(1 for batch in batches if str(batch.status) in submitted_statuses),
        }
        if requested_status == "active":
            batches = [batch for batch in batches if str(batch.status) in active_statuses]
        elif requested_status == "submitted":
            batches = [batch for batch in batches if str(batch.status) in submitted_statuses]
        elif requested_status:
            batches = [batch for batch in batches if str(batch.status) == requested_status]
        page = max(1, self._optional_int((query.get("page") or [1])[0]) or 1)
        page_size = max(1, min(500, self._optional_int((query.get("page_size") or query.get("pageSize") or [100])[0]) or 100))
        total = len(batches)
        start = (page - 1) * page_size
        page_items = batches[start : start + page_size]
        items = [self.business_batch_payload(batch) for batch in page_items]
        return {
            "items": items,
            "counts": counts,
            "page": page,
            "pageSize": page_size,
            "total": total,
            "pagination": {"page": page, "pageSize": page_size, "total": total},
        }

    def create_batch_payload(self, payload: dict[str, Any], *, actor: EtcBusinessBatchActor) -> dict[str, object]:
        batch = self._etc_service.create_business_batch(
            task_id=str(payload.get("taskId") or payload.get("task_id") or ""),
            owner_user_id=self._first_text(actor.username, actor.user_id, payload.get("ownerUserId"), payload.get("owner_user_id")),
            owner_org_id=self._first_text(actor.dept_id, payload.get("ownerOrgId"), payload.get("owner_org_id")),
            idempotency_key=self._first_text(payload.get("idempotencyKey"), payload.get("idempotency_key")),
        )
        return {"businessBatch": self.business_batch_payload(batch)}

    def detail_payload(self, business_batch_id: str, *, actor: EtcBusinessBatchActor) -> dict[str, object]:
        batch = self._scoped_batch(business_batch_id, actor)
        return {"businessBatch": self.business_batch_payload(batch, include_invoice_items=True)}

    def preview_import_payload(
        self,
        business_batch_id: str,
        uploads: list[UploadedEtcZipFile],
        *,
        expected_version: int | None,
        actor: EtcBusinessBatchActor,
    ) -> dict[str, object]:
        self._scoped_batch(business_batch_id, actor)
        return self._etc_service.preview_business_batch_import_zips(
            business_batch_id,
            uploads,
            expected_version=expected_version,
        )

    def confirm_import_payload(
        self,
        business_batch_id: str,
        *,
        session_id: str,
        expected_version: int | None,
        idempotency_key: str | None,
        actor: EtcBusinessBatchActor,
    ) -> dict[str, object]:
        self._scoped_batch(business_batch_id, actor)
        batch, result = self._etc_service.confirm_business_batch_import(
            business_batch_id,
            session_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
        self._sync_invoices(batch, "etc_business_batch_import_confirm")
        return {
            "businessBatch": self.business_batch_payload(batch),
            "importResult": self._etc_service.import_result_payload(result),
        }

    def create_oa_draft_payload(
        self,
        business_batch_id: str,
        *,
        expected_version: int | None,
        actor: EtcBusinessBatchActor,
        headers: dict[str, str] | None,
    ) -> dict[str, object]:
        current = self._scoped_batch(business_batch_id, actor)
        reconciliation_task = self._get_reconciliation_task(current.task_id)
        oa_client = self._oa_client_factory(headers) if self._oa_client_factory is not None else None
        batch = self._etc_service.create_business_batch_oa_draft(
            business_batch_id,
            expected_version=expected_version,
            oa_client=oa_client,
            reconciliation_task=reconciliation_task,
        )
        if reconciliation_task is not None and batch.submission_batch_id and batch.external_etc_batch_id:
            self._reconciliation_task_service.record_oa_draft_created(
                task_id=str(getattr(reconciliation_task, "task_id")),
                oa_draft_batch_id=batch.submission_batch_id,
                etc_batch_id=batch.external_etc_batch_id,
                actor=actor.actor_id,
            )
        self._sync_invoices(batch, "etc_business_oa_draft_created")
        self.enqueue_oa_detection(batch)
        return {"businessBatch": self.business_batch_payload(batch)}

    def refresh_oa_status_payload(
        self,
        business_batch_id: str,
        *,
        expected_version: int | None,
        actor: EtcBusinessBatchActor,
    ) -> dict[str, object]:
        self._scoped_batch(business_batch_id, actor)
        batch = self.refresh_oa_detection(business_batch_id, expected_version=expected_version)
        if str(getattr(batch, "status", "")) in {
            EtcBusinessBatchStatus.OA_SUBMITTED.value,
            EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value,
        }:
            self._sync_invoices(batch, "etc_business_oa_status_detected")
        return {"businessBatch": self.business_batch_payload(batch)}

    def manual_oa_status_payload(
        self,
        business_batch_id: str,
        *,
        decision: str,
        reason: str,
        expected_version: int | None,
        candidate_oa_row_id: str | None,
        actor: EtcBusinessBatchActor,
    ) -> dict[str, object]:
        current = self._scoped_batch(business_batch_id, actor)
        if str(getattr(current, "status", "")) not in ETC_BUSINESS_BATCH_MANUAL_FALLBACK_STATUSES:
            raise EtcBusinessBatchInvalidTransitionError(
                "manual OA status is allowed only after OA detection timed out, conflicted, or became unavailable.",
                code="invalid_manual_status",
            )
        if str(decision or "").strip().lower() == "submitted" and candidate_oa_row_id:
            self._validate_candidate_oa_row(current, candidate_oa_row_id)
        batch = self._etc_service.manual_business_batch_oa_status(
            business_batch_id,
            decision=decision,
            reason=reason,
            expected_version=expected_version,
            candidate_oa_row_id=candidate_oa_row_id,
        )
        self._sync_invoices(batch, "etc_business_manual_oa_status")
        return {"businessBatch": self.business_batch_payload(batch)}

    def source_files_payload(
        self,
        business_batch_id: str,
        uploads: list[object],
        *,
        actor: EtcBusinessBatchActor,
    ) -> dict[str, object]:
        batch = self._scoped_batch(business_batch_id, actor)
        task_id = str(getattr(batch, "task_id", "") or "").strip()
        if not task_id:
            raise EtcBusinessBatchInvalidTransitionError("business batch is not linked to a reconciliation task.", code="task_id_required")
        created = []
        for upload in uploads:
            created.append(
                self._reconciliation_task_service.store_uploaded_source_file(
                    task_id=task_id,
                    source_kind=SourceFileKind.ETC_ZIP,
                    original_name=str(getattr(upload, "file_name", "") or "source-file"),
                    content_type=str(getattr(upload, "content_type", "") or "application/octet-stream"),
                    content=bytes(getattr(upload, "content", b"") or b""),
                    created_by=actor.actor_id,
                )
            )
        task = self._reconciliation_task_service.get_task(task_id)
        return {
            "businessBatch": self.business_batch_payload(batch, include_invoice_items=True),
            "sourceFiles": self.source_file_payloads(task),
            "createdSourceFiles": [self._source_file_payload(item, blocking_file_ids=set()) for item in created],
        }

    def enqueue_oa_detection(self, batch_or_id: EtcBusinessBatch | str) -> bool:
        queue = self._queue_repository
        enqueue = getattr(queue, "enqueue", None)
        if not callable(enqueue):
            return False
        batch = self._etc_service.get_business_batch(batch_or_id) if isinstance(batch_or_id, str) else batch_or_id
        enqueue(
            event_type=ETC_BUSINESS_OA_DETECTION_EVENT_TYPE,
            aggregate_type="etc_business_batch",
            aggregate_id=batch.business_batch_id,
            scope_type="etc_business_batch",
            scope_key=batch.business_batch_id,
            dedupe_key=f"{ETC_BUSINESS_OA_DETECTION_EVENT_TYPE}:{batch.business_batch_id}:{batch.version}",
            payload={"business_batch_id": batch.business_batch_id, "expected_version": batch.version},
            source_version=batch.version,
            priority=50,
        )
        return True

    def refresh_oa_detection(self, business_batch_id: str, *, expected_version: int | None) -> EtcBusinessBatch:
        batch = self._etc_service.get_business_batch(business_batch_id)
        payload = self._etc_service.business_batch_payload(batch)
        invoice_summary = payload.get("invoiceSummary") if isinstance(payload.get("invoiceSummary"), dict) else {}
        context = EtcOADetectionContext(
            business_batch_id=str(payload.get("businessBatchId") or ""),
            external_etc_batch_id=str(payload.get("externalEtcBatchId") or ""),
            amount=invoice_summary.get("amount", "0.00") if isinstance(invoice_summary, dict) else "0.00",
            invoice_count=int(invoice_summary.get("count", 0) or 0) if isinstance(invoice_summary, dict) else 0,
            owner_user_id=str(payload.get("ownerUserId") or "").strip() or None,
            owner_org_id=str(payload.get("ownerOrgId") or "").strip() or None,
            oa_draft_created_at=getattr(batch, "updated_at", None),
            oa_detection_deadline_at=getattr(batch, "oa_detection_deadline_at", None),
            oa_detection_final_retry_until=getattr(batch, "oa_detection_final_retry_until", None),
        )
        adapter = self._oa_adapter_provider() if self._oa_adapter_provider is not None else None
        candidate_loader = getattr(adapter, "list_etc_oa_detection_candidates", None)
        if not callable(candidate_loader):
            return self._etc_service.apply_business_batch_oa_detection_result(
                business_batch_id,
                expected_version=expected_version,
                detection_status="unavailable",
                reason="oa_detector_not_configured",
                error="OA detector is not configured.",
            )
        detector = EtcOADetectionService()
        start, end = detector.detection_window(context)
        if start is None or end is None:
            now = datetime.now(UTC)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        result = detector.detect_with_adapter(
            context,
            lambda detection_context: candidate_loader(
                business_batch_id=detection_context.business_batch_id,
                external_etc_batch_id=detection_context.external_etc_batch_id,
                created_from=start,
                created_to=end,
            ),
            now=datetime.now(UTC),
        )
        return self._etc_service.apply_business_batch_oa_detection_result(
            business_batch_id,
            expected_version=expected_version,
            detection_status=result.status,
            reason=result.reason,
            oa_row_id=result.oa_row_id,
            process_status=result.process_status,
            error=result.error,
            candidates=result.candidates,
        )

    def sync_invoices_after_oa_detection(self, batch: EtcBusinessBatch, *, reason: str) -> None:
        self._sync_invoices(batch, reason)

    def business_batch_payload(self, batch: EtcBusinessBatch, *, include_invoice_items: bool = False) -> dict[str, object]:
        payload = self._etc_service.business_batch_payload(batch)
        if include_invoice_items:
            invoices = self._etc_service.list_invoices_by_ids(list(getattr(batch, "invoice_ids", []) or []))
            payload["invoiceItems"] = [self._invoice_payload(invoice) for invoice in invoices]
        return payload

    def _scoped_batch(self, business_batch_id: str, actor: EtcBusinessBatchActor) -> EtcBusinessBatch:
        batch = self._etc_service.get_business_batch(business_batch_id)
        if not self._can_access_batch(actor, batch):
            raise EtcBusinessBatchScopeError("当前账户不能访问该 ETC 业务批次。")
        return batch

    def _can_access_batch(self, actor: EtcBusinessBatchActor, batch: EtcBusinessBatch) -> bool:
        if actor.can_admin_access:
            return True
        owner_user_id = str(getattr(batch, "owner_user_id", "") or "").strip()
        owner_org_id = str(getattr(batch, "owner_org_id", "") or "").strip()
        if not owner_user_id and not owner_org_id:
            return True
        actor_ids = {str(actor.user_id or "").strip(), str(actor.username or "").strip()}
        actor_ids.discard("")
        if owner_user_id and owner_user_id in actor_ids:
            return True
        return bool(owner_org_id and owner_org_id == str(actor.dept_id or "").strip())

    def _get_reconciliation_task(self, task_id: str | None) -> object | None:
        normalized = str(task_id or "").strip()
        if not normalized:
            return None
        try:
            return self._reconciliation_task_service.get_task(normalized)
        except KeyError:
            return None

    def _sync_invoices(self, batch: EtcBusinessBatch, reason: str) -> None:
        if self._sync_etc_invoices_to_canonical_invoices is None:
            return
        invoices = self._etc_service.list_invoices_by_ids(list(getattr(batch, "invoice_ids", []) or []))
        changed_months = self._sync_etc_invoices_to_canonical_invoices(invoices)
        if self._refresh_after_etc_invoice_sync is not None:
            self._refresh_after_etc_invoice_sync(changed_months, reason=reason)

    def _matches_list_filters(self, batch: EtcBusinessBatch, *, month: str, plate: str, keyword: str) -> bool:
        invoices = self._etc_service.list_invoices_by_ids(list(getattr(batch, "invoice_ids", []) or []))
        if month and not any(
            str(getattr(invoice, "issue_date", "") or getattr(invoice, "passage_start_date", "") or "").startswith(month)
            for invoice in invoices
        ):
            return False
        if plate and not any(plate in str(getattr(invoice, "plate_number", "") or "").lower() for invoice in invoices):
            return False
        if keyword:
            batch_fields = [
                batch.business_batch_id,
                batch.external_etc_batch_id,
                batch.oa_row_id,
            ]
            if not any(keyword in str(value or "").lower() for value in batch_fields) and not any(
                keyword in str(getattr(invoice, "invoice_number", "") or "").lower()
                or keyword in str(getattr(invoice, "plate_number", "") or "").lower()
                for invoice in invoices
            ):
                return False
        return True

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    def _validate_candidate_oa_row(self, batch: EtcBusinessBatch, candidate_oa_row_id: str) -> None:
        adapter = self._oa_adapter_provider() if self._oa_adapter_provider is not None else None
        candidate_loader = getattr(adapter, "list_etc_oa_detection_candidates", None)
        if not callable(candidate_loader):
            raise EtcBusinessBatchInvalidTransitionError("OA detector is not configured.", code="invalid_manual_oa_candidate")
        detected = self.refresh_oa_detection(batch.business_batch_id, expected_version=None)
        latest_payload = self._etc_service.business_batch_payload(detected)
        audit_events = list(latest_payload.get("auditEvents") or [])
        candidate_rows = [
            str(candidate.get("oaRowId") or "").strip()
            for event in reversed(audit_events)
            if isinstance(event, dict)
            for candidate in list(event.get("candidates") or [])
            if isinstance(candidate, dict)
        ]
        if str(candidate_oa_row_id or "").strip() not in candidate_rows:
            raise EtcBusinessBatchInvalidTransitionError(
                "人工确认的 OA 行未通过实时检测候选校验。",
                code="invalid_manual_oa_candidate",
            )

    def _invoice_payload(self, invoice: object) -> dict[str, object]:
        payload = self._serialize_value(invoice)
        if not isinstance(payload, dict):
            return {}
        file_exists = getattr(self._etc_service, "_stored_invoice_file_exists", None)
        pdf_path = payload.get("pdf_file_path")
        xml_path = payload.get("xml_file_path")
        payload["has_pdf"] = bool(callable(file_exists) and isinstance(pdf_path, str) and pdf_path and file_exists(pdf_path))
        payload["has_xml"] = bool(callable(file_exists) and isinstance(xml_path, str) and xml_path and file_exists(xml_path))
        return payload

    @classmethod
    def source_file_payloads(cls, task: object) -> list[dict[str, object]]:
        blocking_file_ids = {
            str(getattr(issue, "file_id", "") or "")
            for issue in getattr(task, "parse_issues", []) or []
            if getattr(getattr(issue, "severity", ""), "value", getattr(issue, "severity", "")) == ParseIssueSeverity.BLOCKING.value
        }
        return [cls._source_file_payload(source_file, blocking_file_ids=blocking_file_ids) for source_file in getattr(task, "source_files", []) or []]

    @staticmethod
    def _source_file_payload(source_file: object, *, blocking_file_ids: set[str]) -> dict[str, object]:
        return {
            "fileId": getattr(source_file, "file_id", ""),
            "taskId": getattr(source_file, "task_id", ""),
            "sourceKind": getattr(getattr(source_file, "source_kind", ""), "value", getattr(source_file, "source_kind", "")),
            "originalName": getattr(source_file, "original_name", ""),
            "contentType": getattr(source_file, "content_type", ""),
            "sizeBytes": getattr(source_file, "size_bytes", 0),
            "sha256": getattr(source_file, "sha256", ""),
            "storedPath": getattr(source_file, "stored_path", ""),
            "createdBy": getattr(source_file, "created_by", ""),
            "createdAt": getattr(source_file, "created_at", None),
            "hasBlockingIssue": getattr(source_file, "file_id", "") in blocking_file_ids,
        }

    @staticmethod
    def _first_text(*values: object) -> str | None:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return None

    @classmethod
    def _serialize_value(cls, value: object) -> object:
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): cls._serialize_value(item) for key, item in value.items()}
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
            return [cls._serialize_value(item) for item in value]
        return value
