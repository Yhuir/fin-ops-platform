from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Iterable

from fin_ops_platform.services.etc_reconciliation_models import ParseIssueSeverity, SourceFileKind
from fin_ops_platform.services.etc_service import (
    ETC_BUSINESS_BATCH_MANUAL_STATUS_ALLOWED_STATUSES,
    EtcBusinessBatch,
    EtcBusinessBatchInvalidTransitionError,
    EtcBusinessBatchNotFoundError,
    EtcBusinessBatchStatus,
    EtcService,
    UploadedEtcZipFile,
)


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
        oa_client_factory: Callable[[dict[str, str] | None], Any] | None = None,
        link_etc_invoices_to_existing_invoices: Callable[[list[object]], list[str]] | None = None,
        refresh_after_etc_invoice_link: Callable[[list[str], str], None] | None = None,
    ) -> None:
        self._etc_service = etc_service
        self._reconciliation_task_service = reconciliation_task_service
        self._oa_client_factory = oa_client_factory
        self._link_etc_invoices_to_existing_invoices = link_etc_invoices_to_existing_invoices
        self._refresh_after_etc_invoice_link = refresh_after_etc_invoice_link

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
            EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value,
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
        task_id = self._first_text(payload.get("taskId"), payload.get("task_id"))
        created_task = None
        if not task_id:
            created_task = self._reconciliation_task_service.create_task(
                title=self._first_text(payload.get("title"), payload.get("name")) or "新建ETC对账批次",
                created_by=actor.actor_id,
            )
            task_id = str(getattr(created_task, "task_id", "") or "").strip()
        try:
            batch = self._etc_service.create_business_batch(
                task_id=task_id,
                owner_user_id=self._first_text(actor.username, actor.user_id, payload.get("ownerUserId"), payload.get("owner_user_id")),
                owner_org_id=self._first_text(actor.dept_id, payload.get("ownerOrgId"), payload.get("owner_org_id")),
                idempotency_key=self._first_text(payload.get("idempotencyKey"), payload.get("idempotency_key")),
            )
        except Exception:
            if created_task is not None:
                self._reconciliation_task_service.delete_task(
                    task_id=task_id,
                    expected_version=getattr(created_task, "version", None),
                    actor=actor.actor_id,
                    import_cleanup_confirmed=True,
                )
            raise
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
        self._link_existing_canonical_invoices(batch, "etc_business_batch_import_confirm")
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
        reconciliation_task = self._ensure_reconciliation_task_imported_for_batch(
            current,
            reconciliation_task,
            actor=actor,
        )
        self._assert_reconciliation_task_allows_oa_draft(reconciliation_task)
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
        self._link_existing_canonical_invoices(batch, "etc_business_oa_draft_created")
        return {"businessBatch": self.business_batch_payload(batch)}

    def revoke_oa_draft_payload(
        self,
        business_batch_id: str,
        *,
        reason: str,
        expected_version: int | None,
        actor: EtcBusinessBatchActor,
    ) -> dict[str, object]:
        self._scoped_batch(business_batch_id, actor)
        batch = self._etc_service.revoke_business_batch_oa_draft(
            business_batch_id,
            reason=reason,
            expected_version=expected_version,
        )
        self._link_existing_canonical_invoices(batch, "etc_business_oa_draft_revoked")
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
        if str(getattr(current, "status", "")) not in ETC_BUSINESS_BATCH_MANUAL_STATUS_ALLOWED_STATUSES:
            raise EtcBusinessBatchInvalidTransitionError(
                "manual OA status is allowed only after an OA draft is created and waiting for confirmation.",
                code="invalid_manual_status",
            )
        batch = self._etc_service.manual_business_batch_oa_status(
            business_batch_id,
            decision=decision,
            reason=reason,
            expected_version=expected_version,
            candidate_oa_row_id=candidate_oa_row_id,
        )
        if str(decision or "").strip().lower() == "submitted":
            self._record_reconciliation_task_submitted(batch, actor=actor)
        self._link_existing_canonical_invoices(batch, "etc_business_manual_oa_status")
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

    def _ensure_reconciliation_task_imported_for_batch(
        self,
        batch: EtcBusinessBatch,
        reconciliation_task: object | None,
        *,
        actor: EtcBusinessBatchActor,
    ) -> object | None:
        if reconciliation_task is None:
            return None
        status = self._enum_value(getattr(reconciliation_task, "status", None))
        if status in {"imported", "closed"}:
            return reconciliation_task
        if status not in {"ready_for_import", "importing"}:
            return reconciliation_task
        if not self._business_batch_has_successful_import(batch):
            return reconciliation_task
        task_id = str(getattr(reconciliation_task, "task_id", "") or "").strip()
        confirmed_item_set_hash = str(getattr(reconciliation_task, "confirmed_item_set_hash", "") or "").strip()
        task_version = getattr(reconciliation_task, "version", None)
        if not task_id or not isinstance(task_version, int) or not confirmed_item_set_hash:
            return reconciliation_task
        import_batch_id = self._first_text(*(getattr(batch, "import_batch_ids", []) or []))
        return self._reconciliation_task_service.mark_imported(
            task_id=task_id,
            task_version=task_version,
            confirmed_item_set_hash=confirmed_item_set_hash,
            import_batch_id=import_batch_id,
            etc_batch_id=str(getattr(batch, "external_etc_batch_id", "") or "").strip() or None,
            actor=actor.actor_id,
        )

    @classmethod
    def _business_batch_has_successful_import(cls, batch: EtcBusinessBatch) -> bool:
        if not list(getattr(batch, "invoice_ids", []) or []):
            return False
        for attempt in list(getattr(batch, "import_attempts", []) or []):
            if not isinstance(attempt, dict):
                continue
            summary = attempt.get("summary") if isinstance(attempt.get("summary"), dict) else attempt
            if int(summary.get("failed", 0) or 0) != 0:
                continue
            imported = int(summary.get("imported", 0) or 0)
            attachments_completed = int(summary.get("attachmentsCompleted", 0) or 0)
            if imported > 0 or attachments_completed > 0 or list(attempt.get("import_batch_ids") or []):
                return True
        return False

    @classmethod
    def _assert_reconciliation_task_allows_oa_draft(cls, reconciliation_task: object | None) -> None:
        if reconciliation_task is None:
            return
        status = cls._enum_value(getattr(reconciliation_task, "status", None))
        if status in {"imported", "closed"}:
            return
        raise EtcBusinessBatchInvalidTransitionError(
            "ETC 对账任务尚未完成发票导入，不能创建 OA 草稿。",
            code="invalid_reconciliation_task_status",
        )

    def _link_existing_canonical_invoices(self, batch: EtcBusinessBatch, reason: str) -> None:
        if self._link_etc_invoices_to_existing_invoices is None:
            return
        invoices = self._etc_service.list_invoices_by_ids(list(getattr(batch, "invoice_ids", []) or []))
        changed_months = self._link_etc_invoices_to_existing_invoices(invoices)
        if self._refresh_after_etc_invoice_link is not None:
            self._refresh_after_etc_invoice_link(changed_months, reason=reason)

    def _record_reconciliation_task_submitted(self, batch: EtcBusinessBatch, *, actor: EtcBusinessBatchActor) -> None:
        submission_batch_id = str(getattr(batch, "submission_batch_id", "") or "").strip()
        if not submission_batch_id:
            return
        reconciliation_task = self._get_reconciliation_task(str(getattr(batch, "task_id", "") or ""))
        if reconciliation_task is None:
            return
        self._reconciliation_task_service.record_oa_submitted_confirmed(
            task_id=str(getattr(reconciliation_task, "task_id")),
            oa_draft_batch_id=submission_batch_id,
            actor=actor.actor_id,
        )

    def _matches_list_filters(self, batch: EtcBusinessBatch, *, month: str, plate: str, keyword: str) -> bool:
        invoices = self._etc_service.list_invoices_by_ids(list(getattr(batch, "invoice_ids", []) or []))
        amount_breakdown = getattr(batch, "amount_breakdown", {}) if isinstance(getattr(batch, "amount_breakdown", {}), dict) else {}
        scope_month = str(amount_breakdown.get("scope_month") or "").strip()
        if month:
            if scope_month:
                if scope_month != month:
                    return False
            elif not any(
                any(
                    str(getattr(invoice, field, "") or "").startswith(month)
                    for field in ("issue_date", "passage_start_date", "passage_end_date")
                )
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

    @staticmethod
    def _enum_value(value: object) -> str:
        if isinstance(value, Enum):
            return str(value.value)
        return str(value or "").strip()

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
