from __future__ import annotations

from typing import Any

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.import_job_queue import ImportJob
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import OAAttachmentInvoicePromotionService
from fin_ops_platform.services.oa_attachment_summary import record_attachment_summary
from fin_ops_platform.services.oa_manual_import_service import OAManualImportService
from fin_ops_platform.services.postgres_repositories.common import serialize_value
from fin_ops_platform.services.postgres_repositories.oa_attachment_invoice import PostgresOAAttachmentInvoiceRepository
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_repositories.shared_imports import PostgresSharedImportRepository
from fin_ops_platform.services.postgres_repositories.tax_certified_imports import PostgresTaxCertifiedImportRepository
from fin_ops_platform.services.tax_certified_import_service import TaxCertifiedImportService


class SharedImportProcessor:
    """Preserve OA/manual and tax-certified contracts on the single import queue."""

    def __init__(self, connection: Any, *, oa_source_adapter: Any = None) -> None:
        self._connection = connection
        self._oa_source_adapter = oa_source_adapter

    def tax_certified(self, job: ImportJob) -> dict[str, Any]:
        if job.completion is None:
            raise RuntimeError("A claimed import job is required.")
        session_id = str(job.payload.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("import payload.session_id is required.")
        with self._connection.transaction() as transaction:
            job.completion.lock(transaction)
            service = TaxCertifiedImportService(repository=PostgresTaxCertifiedImportRepository(transaction))
            if service.get_session(session_id).imported_by != job.created_by:
                raise ValueError("Tax import session is not owned by the task actor.")
            result = {"success": True, "batch": serialize_value(service.confirm_session(session_id, actor_id=job.created_by, corrections=job.payload.get("corrections") or []))}
            self._record_completion(transaction, job, result)
            job.completion.succeed(transaction, result)
        return result

    def oa_manual(self, job: ImportJob) -> dict[str, Any]:
        if job.completion is None:
            raise RuntimeError("A claimed import job is required.")
        row_ids = job.payload.get("row_ids")
        if not isinstance(row_ids, list) or not all(isinstance(value, str) and value.strip() for value in row_ids):
            raise ValueError("import payload.row_ids must contain nonempty strings.")
        actor_id = str(job.payload.get("actor_id") or job.created_by or "").strip()
        if not actor_id:
            raise ValueError("Import owner is required.")
        if self._oa_source_adapter is None:
            raise RuntimeError("OA manual import requires the source adapter.")
        preparation_started_at = job.payload.get("attachment_preparation_started_at", job.created_at.isoformat())
        records = list(self._oa_source_adapter.prepare_application_record_attachments(row_ids, preparation_started_at=preparation_started_at))
        records_by_id = {record.id: record for record in records}
        if len(records_by_id) != len(records) or set(records_by_id) - set(row_ids):
            raise ValueError("OA source returned duplicate or unrequested records.")
        selected = []
        failed = []
        for row_id in dict.fromkeys(row_ids):
            record = records_by_id.get(row_id)
            if record is None:
                failed.append({"row_id": row_id, "code": "not_found", "message": "OA row_id 不存在"})
            elif str(record.detail_fields.get("流程状态") or "").strip() != "已完成":
                failed.append({"row_id": row_id, "code": "not_completed", "message": "流程未完成，不能导入"})
            else:
                attachments = record_attachment_summary(record)
                if attachments["pending_attachment_count"] or attachments["failed_attachment_count"]:
                    failed.append({"row_id": row_id, "code": "attachment_preparation_failed",
                                   "message": "附件尚未完成解析或解析失败，请修复后重试", **attachments})
                else:
                    selected.append(record)
        with self._connection.transaction() as transaction:
            job.completion.lock(transaction)
            repository = PostgresSharedImportRepository(transaction)
            repository.save_oa_records(selected)
            settings = AppSettingsService.normalize_settings_payload(
                PostgresOpsTaxEtcRepository(transaction).load_settings("app_settings"))
            promotion = OAAttachmentInvoicePromotionService(
                invoice_repository=PostgresOAAttachmentInvoiceRepository(transaction, transaction_bound=True),
                promotion_mode_provider=lambda: settings["oa_import"]["attachment_invoice_promotion_mode"],
            ).promote_records(selected)
            result = repository.add_manual_oa_imports([record.id for record in selected], actor_id=actor_id)
            presentation = OAManualImportService(state_store=repository,
                oa_adapter=self._oa_source_adapter)
            result.update(attachment_invoice_promotion=promotion, failed=failed, rows=presentation.serialize_import_result_rows(
                              selected, imported_entries=result["entries"]),
                          affected_scope_keys=sorted({record.month for record in selected}),
                          outcome=("partial_success" if selected else "failed") if failed else "success")
            self._record_completion(transaction, job, result)
            if result["outcome"] == "failed":
                job.completion.fail(transaction, result, error="所有选中 OA 均未导入，请查看逐条失败原因。")
            else:
                job.completion.succeed(transaction, result)
        return result

    @staticmethod
    def _record_completion(transaction: Any, job: ImportJob, result: dict[str, Any]) -> None:
        AuditTrailService(PostgresOperationsAuditRepository(transaction)).record_action(
            actor_id=job.created_by, action=job.import_type, entity_type="import_job",
            entity_id=job.import_job_id, metadata={"event_type": "operation.completed",
                "page_key": "settings" if job.import_type == "oa_manual_import.create" else "tax-offset",
                "operation_location": "import_worker", "outcome": str(result.get("outcome") or "success"), "result": result})
