from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Iterable

from fin_ops_platform.services.etc_reconciliation_models import ParseIssueSeverity, SourceFileKind
from fin_ops_platform.services.etc_invoice_pdf_bundle_service import (
    EtcInvoicePdfBundle,
    EtcInvoicePdfBundleError,
    EtcInvoicePdfBundleService,
)
from fin_ops_platform.services.etc_service import (
    ETC_BUSINESS_BATCH_MANUAL_STATUS_ALLOWED_STATUSES,
    ETC_BUSINESS_BATCH_SUBMITTED_STATUSES,
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


def evaluate_etc_oa_draft_action(
    batch: EtcBusinessBatch,
    task: object | None,
    actor: EtcBusinessBatchActor,
) -> dict[str, object]:
    if not actor.can_mutate_data:
        return {"enabled": False, "code": "read_only", "message": "当前账号仅支持查看和导出，不能提交审批。"}
    status = str(getattr(batch, "status", "") or "")
    if status == EtcBusinessBatchStatus.OA_DRAFT_CREATING.value:
        return {"enabled": False, "code": "oa_draft_creating", "message": "审批草稿正在创建，请勿重复提交。"}
    if status == EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value:
        return {"enabled": False, "code": "oa_confirmation_pending", "message": "审批草稿已创建，请先确认是否已在 OA 提交。"}
    if status not in {
        EtcBusinessBatchStatus.IMPORTED.value,
        EtcBusinessBatchStatus.OA_DRAFT_FAILED.value,
        EtcBusinessBatchStatus.NOT_SUBMITTED.value,
        EtcBusinessBatchStatus.MANUALLY_MARKED_NOT_SUBMITTED.value,
    }:
        return {"enabled": False, "code": "invalid_batch_status", "message": "当前批次状态不能创建审批草稿。"}
    if not list(getattr(batch, "invoice_ids", []) or []):
        return {"enabled": False, "code": "empty_business_batch", "message": "当前批次尚未导入 ETC 发票。"}
    if task is None:
        return {"enabled": False, "code": "reconciliation_task_missing", "message": "当前批次缺少绑定的 ETC 对账任务，请刷新或联系管理员。"}
    task_status = getattr(task, "status", None)
    if isinstance(task, dict):
        task_status = task.get("status")
    task_status = getattr(task_status, "value", task_status)
    if str(task_status or "") not in {"imported", "closed"}:
        return {"enabled": False, "code": "invalid_reconciliation_task_status", "message": "ETC 对账任务尚未完成发票导入。"}
    return {"enabled": True, "code": "ready", "message": "可以提交审批。"}


class EtcBusinessBatchApplicationService:
    def __init__(
        self,
        *,
        etc_service: EtcService,
        reconciliation_task_service: Any,
        oa_client_factory: Callable[[dict[str, str] | None], Any] | None = None,
        link_etc_invoices_to_existing_invoices: Callable[[list[object]], list[str]] | None = None,
        refresh_after_etc_invoice_link: Callable[[list[str], str], None] | None = None,
        refresh_after_etc_business_batch_status_change: Callable[[list[str], str], None] | None = None,
        invoice_pdf_bundle_service: EtcInvoicePdfBundleService | None = None,
        record_invoice_pdf_download: Callable[[EtcBusinessBatchActor, EtcBusinessBatch, EtcInvoicePdfBundle], None] | None = None,
    ) -> None:
        self._etc_service = etc_service
        self._reconciliation_task_service = reconciliation_task_service
        self._oa_client_factory = oa_client_factory
        self._link_etc_invoices_to_existing_invoices = link_etc_invoices_to_existing_invoices
        self._refresh_after_etc_invoice_link = refresh_after_etc_invoice_link
        self._refresh_after_etc_business_batch_status_change = refresh_after_etc_business_batch_status_change
        self._invoice_pdf_bundle_service = invoice_pdf_bundle_service or EtcInvoicePdfBundleService(
            read_invoice_pdf=etc_service.read_invoice_pdf_bytes,
        )
        self._record_invoice_pdf_download = record_invoice_pdf_download

    def list_batches_payload(self, query: dict[str, list[str]], *, actor: EtcBusinessBatchActor) -> dict[str, object]:
        requested_status = str((query.get("bucket") or query.get("status") or [None])[0] or "unsubmitted").strip()
        task_id = (query.get("taskId") or query.get("task_id") or [None])[0]
        month = str((query.get("month") or [None])[0] or "").strip()
        plate = str((query.get("plate") or [None])[0] or "").strip().lower()
        keyword = str((query.get("keyword") or [None])[0] or "").strip().lower()
        page = max(1, self._optional_int((query.get("page") or [1])[0]) or 1)
        page_size = max(1, min(500, self._optional_int((query.get("page_size") or query.get("pageSize") or [100])[0]) or 100))
        result = self._etc_service.list_business_batch_summaries(
            bucket=requested_status,
            task_id=task_id,
            month=month,
            plate=plate,
            keyword=keyword,
            page=page,
            page_size=page_size,
            owner_user_ids=[actor.user_id, actor.username],
            owner_org_id=actor.dept_id,
            can_admin_access=actor.can_admin_access,
        )
        items = []
        for item in list(result.get("items") or []):
            if not isinstance(item, dict) or not isinstance(item.get("business_batch"), EtcBusinessBatch):
                continue
            batch = item["business_batch"]
            payload = self._business_batch_summary_payload(
                batch,
                invoice_count=int(item.get("invoice_count") or len(batch.invoice_ids)),
                total_amount=item.get("total_amount") or "0",
                scope_month=item.get("scope_month"),
            )
            payload["createOaDraftAction"] = evaluate_etc_oa_draft_action(batch, item.get("reconciliation_task"), actor)
            items.append(payload)
        counts = dict(result.get("counts") or {})
        total = int(result.get("total") or 0)
        return {
            "items": items,
            "counts": counts,
            "statistics": dict(result.get("statistics")) if isinstance(result.get("statistics"), dict) else None,
            "page": page,
            "pageSize": page_size,
            "total": total,
            "pagination": {"page": page, "pageSize": page_size, "total": total},
        }

    def create_batch_payload(self, payload: dict[str, Any], *, actor: EtcBusinessBatchActor) -> dict[str, object]:
        task_id = self._first_text(payload.get("taskId"), payload.get("task_id"))
        title = self._first_text(payload.get("title"), payload.get("name")) or "新建ETC批次"
        created_task = None
        if not task_id:
            created_task = self._reconciliation_task_service.create_task(
                title=title,
                created_by=actor.actor_id,
            )
            task_id = str(getattr(created_task, "task_id", "") or "").strip()
        try:
            batch = self._etc_service.create_business_batch(
                task_id=task_id,
                title=title,
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

    def update_title_payload(
        self,
        business_batch_id: str,
        payload: dict[str, Any],
        *,
        actor: EtcBusinessBatchActor,
    ) -> dict[str, object]:
        self._scoped_batch(business_batch_id, actor)
        title = self._first_text(payload.get("title"), payload.get("name"))
        if not title:
            raise EtcBusinessBatchInvalidTransitionError(
                "ETC business batch title is required.",
                code="invalid_business_batch_title",
            )
        batch = self._etc_service.update_business_batch_title(
            business_batch_id,
            title=title,
            expected_version=self._optional_int(payload.get("expectedVersion") or payload.get("expected_version")),
        )
        self._update_reconciliation_task_title(batch, title=title, actor=actor)
        return {"businessBatch": self.business_batch_payload(batch)}

    def detail_payload(self, business_batch_id: str, *, actor: EtcBusinessBatchActor) -> dict[str, object]:
        batch = self._scoped_batch_record(business_batch_id, actor)
        task = self._get_reconciliation_task_record(batch.task_id)
        invoices = self._etc_service.list_invoice_records_by_ids(list(batch.invoice_ids))
        payload = self._business_batch_summary_payload(
            batch,
            invoice_count=len(invoices),
            total_amount=sum((getattr(invoice, "total_amount", Decimal("0")) for invoice in invoices), Decimal("0")),
            scope_month=(batch.amount_breakdown or {}).get("scope_month"),
        )
        payload.update({
            "invoiceIds": list(batch.invoice_ids),
            "importAttempts": list(batch.import_attempts),
            "auditEvents": list(batch.audit_events),
            "invoiceItems": [self._invoice_payload(invoice) for invoice in invoices],
            "createOaDraftAction": evaluate_etc_oa_draft_action(batch, task, actor),
        })
        return {"businessBatch": payload}

    def invoice_pdf_bundle(self, business_batch_id: str, *, actor: EtcBusinessBatchActor) -> EtcInvoicePdfBundle:
        batch = self._scoped_batch(business_batch_id, actor)
        has_oa_draft = bool(str(getattr(batch, "oa_draft_id", "") or "").strip())
        status = str(getattr(batch, "status", "") or "")
        if not has_oa_draft and status not in ETC_BUSINESS_BATCH_SUBMITTED_STATUSES:
            raise EtcInvoicePdfBundleError(
                "审批草稿创建成功或批次已提交后才能下载 ETC 发票 PDF。",
                code="invoice_pdf_bundle_not_ready",
            )
        invoice_ids = list(getattr(batch, "invoice_ids", []) or [])
        try:
            invoices = self._etc_service.list_invoices_by_ids(invoice_ids)
        except Exception as exc:
            raise EtcInvoicePdfBundleError(
                "当前 ETC 业务批次的发票关联不完整，请刷新后重试或联系管理员。",
                code="invoice_pdf_unavailable",
            ) from exc
        bundle = self._invoice_pdf_bundle_service.build(batch=batch, invoices=invoices)
        if self._record_invoice_pdf_download is not None:
            self._record_invoice_pdf_download(actor, batch, bundle)
        return bundle

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
        idempotency_key: str,
        expected_version: int | None,
        actor: EtcBusinessBatchActor,
        headers: dict[str, str] | None,
    ) -> dict[str, object]:
        current = self._scoped_batch(business_batch_id, actor)
        reconciliation_task = self._get_reconciliation_task(current.task_id)
        normalized_key = str(idempotency_key or "").strip()
        if (
            current.status == EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value
            and str(current.oa_draft_idempotency_key or "").strip() == normalized_key
        ):
            self._assert_reconciliation_task_allows_oa_draft(reconciliation_task)
            self._ensure_reconciliation_task_oa_draft_metadata(current, reconciliation_task, actor=actor)
            return {"businessBatch": self.business_batch_payload(current)}
        reconciliation_task = self._ensure_reconciliation_task_imported_for_batch(
            current,
            reconciliation_task,
            actor=actor,
        )
        self._assert_reconciliation_task_allows_oa_draft(reconciliation_task)
        action = evaluate_etc_oa_draft_action(current, reconciliation_task, actor)
        if not bool(action["enabled"]):
            raise EtcBusinessBatchInvalidTransitionError(str(action["message"]), code=str(action["code"]))
        oa_client = self._oa_client_factory(headers) if self._oa_client_factory is not None else None
        batch = self._etc_service.create_business_batch_oa_draft(
            business_batch_id,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            oa_client=oa_client,
            reconciliation_task=reconciliation_task,
        )
        self._ensure_reconciliation_task_oa_draft_metadata(batch, reconciliation_task, actor=actor)
        return {"businessBatch": self.business_batch_payload(batch)}

    def recover_oa_draft_payload(
        self,
        business_batch_id: str,
        *,
        expected_version: int | None,
        reason: str,
        evidence: str,
        oa_draft_id: str | None,
        oa_draft_url: str | None,
        confirmed_not_created: bool,
        actor: EtcBusinessBatchActor,
    ) -> dict[str, object]:
        if not actor.can_admin_access:
            raise EtcBusinessBatchScopeError("只有管理员可以恢复结果未知的 ETC OA 草稿请求。")
        current = self._scoped_batch(business_batch_id, actor)
        if expected_version is None:
            raise EtcBusinessBatchInvalidTransitionError("expectedVersion is required.", code="expected_version_required")
        if current.status == EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value:
            if confirmed_not_created or str(oa_draft_id or "").strip() != str(current.oa_draft_id or "").strip() or str(
                oa_draft_url or ""
            ).strip() != str(current.oa_draft_url or "").strip():
                raise EtcBusinessBatchInvalidTransitionError(
                    "恢复结果与已持久化的 OA 草稿不一致。",
                    code="oa_draft_recovery_conflict",
                )
            reconciliation_task = self._get_reconciliation_task(current.task_id)
            self._ensure_reconciliation_task_oa_draft_metadata(current, reconciliation_task, actor=actor)
            return {"businessBatch": self.business_batch_payload(current)}
        batch = self._etc_service.recover_business_batch_oa_draft(
            business_batch_id,
            expected_version=expected_version,
            reason=reason,
            evidence=evidence,
            oa_draft_id=oa_draft_id,
            oa_draft_url=oa_draft_url,
            confirmed_not_created=confirmed_not_created,
        )
        if batch.status == EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value and batch.submission_batch_id and batch.external_etc_batch_id:
            reconciliation_task = self._get_reconciliation_task(current.task_id)
            self._ensure_reconciliation_task_oa_draft_metadata(batch, reconciliation_task, actor=actor)
        return {"businessBatch": self.business_batch_payload(batch)}

    def _ensure_reconciliation_task_oa_draft_metadata(
        self,
        batch: EtcBusinessBatch,
        reconciliation_task: object | None,
        *,
        actor: EtcBusinessBatchActor,
    ) -> None:
        self._assert_reconciliation_task_allows_oa_draft(reconciliation_task)
        assert reconciliation_task is not None
        expected = (
            str(batch.submission_batch_id or "").strip(),
            str(batch.external_etc_batch_id or "").strip(),
            "draft_created",
        )
        if not expected[0] or not expected[1]:
            raise EtcBusinessBatchInvalidTransitionError(
                "OA 草稿批次元数据不完整。",
                code="oa_draft_attempt_missing",
            )
        actual = (
            str(getattr(reconciliation_task, "oa_draft_batch_id", "") or "").strip(),
            str(getattr(reconciliation_task, "etc_batch_id", "") or "").strip(),
            str(getattr(reconciliation_task, "oa_draft_status", "") or "").strip(),
        )
        if actual == expected:
            return
        if actual[0] or actual[2]:
            raise EtcBusinessBatchInvalidTransitionError(
                "ETC 对账任务已绑定到其它 OA 草稿。",
                code="reconciliation_task_oa_draft_conflict",
            )
        self._reconciliation_task_service.record_oa_draft_created(
            task_id=str(getattr(reconciliation_task, "task_id")),
            oa_draft_batch_id=expected[0],
            etc_batch_id=expected[1],
            actor=actor.actor_id,
        )

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
        self._refresh_business_batch_status_change(batch, reason="etc_business_oa_draft_revoked")
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
        self._refresh_business_batch_status_change(batch, reason="etc_business_manual_oa_status")
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

    @staticmethod
    def _business_batch_summary_payload(
        batch: EtcBusinessBatch,
        *,
        invoice_count: int,
        total_amount: object,
        scope_month: object,
    ) -> dict[str, object]:
        return {
            "businessBatchId": batch.business_batch_id,
            "taskId": batch.task_id,
            "title": batch.title,
            "status": batch.status,
            "version": batch.version,
            "idempotencyKey": batch.idempotency_key,
            "isActive": batch.is_active,
            "taskActiveKey": batch.task_active_key,
            "ownerUserId": batch.owner_user_id,
            "ownerOrgId": batch.owner_org_id,
            "importBatchIds": list(batch.import_batch_ids),
            "submissionBatchId": batch.submission_batch_id,
            "externalEtcBatchId": batch.external_etc_batch_id,
            "oaDraftId": batch.oa_draft_id,
            "oaDraftUrl": batch.oa_draft_url,
            "oaRowId": batch.oa_row_id,
            "oaProcessStatus": batch.oa_process_status,
            "invoiceSummary": {"count": invoice_count, "amount": str(total_amount or "0")},
            "amountBreakdown": {**dict(batch.amount_breakdown or {}), **({"scope_month": str(scope_month)[:7]} if scope_month else {})},
            "createdAt": batch.created_at,
            "updatedAt": batch.updated_at,
        }

    def _scoped_batch_record(self, business_batch_id: str, actor: EtcBusinessBatchActor) -> EtcBusinessBatch:
        batch = self._etc_service.get_business_batch_record(business_batch_id)
        if not self._can_access_batch(actor, batch):
            raise EtcBusinessBatchScopeError("当前账户不能访问该 ETC 业务批次。")
        return batch

    def _get_reconciliation_task_record(self, task_id: str | None) -> object | None:
        normalized = str(task_id or "").strip()
        if not normalized:
            return None
        try:
            return self._reconciliation_task_service.get_task_record(normalized)
        except KeyError:
            return None

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
            raise EtcBusinessBatchInvalidTransitionError(
                "当前批次缺少绑定的 ETC 对账任务，不能创建 OA 草稿。",
                code="reconciliation_task_missing",
            )
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

    def _refresh_business_batch_status_change(self, batch: EtcBusinessBatch, *, reason: str) -> None:
        if self._refresh_after_etc_business_batch_status_change is None:
            return
        months = {
            str((getattr(batch, "amount_breakdown", {}) or {}).get("scope_month") or "").strip()[:7]
        }
        for invoice in self._etc_service.list_invoices_by_ids(list(getattr(batch, "invoice_ids", []) or [])):
            for field_name in ("issue_date", "passage_start_date", "passage_end_date"):
                months.add(str(getattr(invoice, field_name, "") or "").strip()[:7])
        self._refresh_after_etc_business_batch_status_change(
            sorted(month for month in months if len(month) == 7 and month[4:5] == "-"),
            reason=reason,
        )

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

    def _update_reconciliation_task_title(
        self,
        batch: EtcBusinessBatch,
        *,
        title: str,
        actor: EtcBusinessBatchActor,
    ) -> None:
        task_id = str(getattr(batch, "task_id", "") or "").strip()
        if not task_id or not hasattr(self._reconciliation_task_service, "update_task_title"):
            return
        try:
            self._reconciliation_task_service.update_task_title(
                task_id=task_id,
                title=title,
                actor=actor.actor_id,
            )
        except KeyError:
            return

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
                batch.title,
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
        pdf_path = payload.get("pdf_file_path")
        xml_path = payload.get("xml_file_path")
        payload["has_pdf"] = bool(isinstance(pdf_path, str) and pdf_path and payload.get("pdf_file_hash"))
        payload["has_xml"] = bool(isinstance(xml_path, str) and xml_path and payload.get("xml_file_hash"))
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
