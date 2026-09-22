from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.etc_reconciliation_zip_filter import StaleReconciliationPreviewError
from fin_ops_platform.services.etc_service import EtcBusinessBatchInvalidTransitionError, EtcImportPreviewStaleError
from fin_ops_platform.services.import_job_queue import ImportJob, ImportJobDataError


class ImportProcessingService:
    def __init__(
        self,
        *,
        file_import_service: Any,
        etc_service: Any,
        etc_reconciliation_task_service: Any,
        serialize_value: Callable[[Any], Any],
        persist_confirmed_import_delta: Callable[..., Any],
        workbench_matching_scope_months_for_import_file_session: Callable[[Any, list[str]], list[str]],
        tax_offset_scope_keys_for_import_file_session: Callable[[Any, list[str]], list[str]],
        bank_scope_keys_for_import_file_session: Callable[[Any, list[str]], list[str]],
        input_invoice_usage_scope_keys_for_import_file_session: Callable[[Any, list[str]], list[str]],
        output_invoice_collection_scope_keys_for_import_file_session: Callable[[Any, list[str]], list[str]],
        etc_import_preview_service: Any,
        etc_import_uow: Any = None,
        persist_import_preview_delta: Callable[..., Any] | None = None,
    ) -> None:
        self._file_import_service = file_import_service
        self._etc_service = etc_service
        self._etc_reconciliation_task_service = etc_reconciliation_task_service
        self._serialize_value = serialize_value
        self._persist_confirmed_import_delta = persist_confirmed_import_delta
        self._workbench_matching_scope_months_for_import_file_session = workbench_matching_scope_months_for_import_file_session
        self._tax_offset_scope_keys_for_import_file_session = tax_offset_scope_keys_for_import_file_session
        self._bank_scope_keys_for_import_file_session = (
            bank_scope_keys_for_import_file_session
        )
        self._input_invoice_usage_scope_keys_for_import_file_session = input_invoice_usage_scope_keys_for_import_file_session
        self._output_invoice_collection_scope_keys_for_import_file_session = output_invoice_collection_scope_keys_for_import_file_session
        self._etc_import_preview_service = etc_import_preview_service
        self._etc_import_uow = etc_import_uow
        self._persist_import_preview_delta = persist_import_preview_delta

    def build_import_job_processors(self) -> dict[str, Callable[[ImportJob], dict[str, object]]]:
        processors: dict[str, Callable[[ImportJob], dict[str, object]]] = {
            "file_import.confirm": self.process_file_import_confirm_job,
            "etc_invoice_import.confirm": self.process_etc_invoice_import_confirm_job,
        }
        return processors

    def process_file_import_confirm_job(self, import_job: ImportJob) -> dict[str, object]:
        session_id = str(import_job.payload.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("import job payload.session_id is required.")
        if import_job.stage == "prepare":
            if self._persist_import_preview_delta is None or import_job.completion is None:
                raise RuntimeError("durable prepare requires preview persistence and task completion")
            session = self._file_import_service.prepare_registered_session(session_id)
            result = {"session_id": session.id, "summary": {
                "files": len(session.files),
                "created": sum(item.success_count for item in session.files),
                "duplicates": sum(item.duplicate_count for item in session.files),
                "failed": sum(item.error_count for item in session.files),
            }}
            if not session.files or all(self._file_import_service.file_requires_review(item) for item in session.files):
                result["outcome"] = "needs_review"
            # Bank duplicates have no enrichment or provenance write. Invoice
            # duplicates may still enrich canonical facts and require confirmation.
            if "outcome" not in result and session.files and all(
                item.batch_type == BatchType.BANK_TRANSACTION
                and item.status == "preview_ready" and item.row_results
                and all(row.decision.value == "duplicate_skipped" for row in item.row_results)
                for item in session.files
            ):
                result.update(outcome="no_changes", created=0, updated=0,
                              duplicates=sum(len(item.row_results) for item in session.files), failed=0)
            self._persist_import_preview_delta(
                session_id, completion=import_job.completion, result_payload=result,
            )
            return result
        selected_file_ids = import_job.payload.get("selected_file_ids")
        if not isinstance(selected_file_ids, list):
            raise ValueError("import job payload.selected_file_ids is required.")
        return self.execute_file_import_confirm_job(
            session_id=session_id,
            selected_file_ids=[str(item) for item in selected_file_ids],
            completion=import_job.completion,
        )

    def process_etc_invoice_import_confirm_job(self, import_job: ImportJob) -> dict[str, object]:
        payload = import_job.payload
        owner = str(import_job.created_by or "").strip()
        if not owner or str(payload.get("owner_user_id") or owner).strip() != owner:
            raise ImportJobDataError("ETC import task owner is missing or inconsistent.")
        session_id = str(payload.get("session_id") or "").strip()
        if import_job.stage == "prepare":
            return self._etc_import_preview_service.prepare(
                session_id=session_id, imported_by=owner, completion=import_job.completion)
        return self.execute_etc_invoice_import_confirm_job(
            session_id=session_id, task_id=str(payload.get("task_id") or "").strip(),
            owner_user_id=owner,
            task_version=int(payload.get("task_version") or 0),
            confirmed_item_set_hash=str(payload.get("confirmed_item_set_hash") or "").strip(),
            completion=import_job.completion,
        )

    def execute_file_import_confirm_job(
        self,
        *,
        session_id: str,
        selected_file_ids: list[str],
        completion: Any | None = None,
    ) -> dict[str, object]:
        confirmed_session = self._file_import_service.confirm_session(
            session_id=session_id, selected_file_ids=selected_file_ids,
        )
        selected = set(selected_file_ids)
        confirmed_files = [item for item in confirmed_session.files if item.id in selected and item.status == "confirmed"]
        if len(confirmed_files) != len(selected):
            raise ValueError("selected import scope did not complete")
        scope_months = self._workbench_matching_scope_months_for_import_file_session(confirmed_session, selected_file_ids)
        result_summary = {
            "session_id": session_id,
            "confirmed": len(confirmed_files),
            "selected": len(selected),
            "created": sum(row.decision.value == "created" for item in confirmed_files for row in item.row_results),
            "updated": sum(row.decision.value == "status_updated" for item in confirmed_files for row in item.row_results),
            "duplicates": sum(row.decision.value == "duplicate_skipped" for item in confirmed_files for row in item.row_results),
            "failed": 0,
            "affected_months": scope_months,
            **self._write_result_envelope(
                tax_offset_scope_keys=self._tax_offset_scope_keys_for_import_file_session(confirmed_session, selected_file_ids),
                bank_scope_keys=self._bank_scope_keys_for_import_file_session(confirmed_session, selected_file_ids),
                input_invoice_usage_scope_keys=self._input_invoice_usage_scope_keys_for_import_file_session(confirmed_session, selected_file_ids),
                output_invoice_collection_scope_keys=self._output_invoice_collection_scope_keys_for_import_file_session(confirmed_session, selected_file_ids),
            ),
        }
        import_state_payload = self._file_import_service.confirmed_session_persistence_payload(
            session_id=session_id, selected_file_ids=selected_file_ids,
        )
        persistence_result = self._persist_confirmed_import_delta(
            import_state_payload=import_state_payload,
            scope_months=scope_months,
            completion=completion,
            result_payload=result_summary,
        )
        return {**result_summary, **persistence_result}

    def execute_etc_invoice_import_confirm_job(
        self, *, session_id: str, task_id: str, owner_user_id: str,
        task_version: int, confirmed_item_set_hash: str, completion: Any = None,
    ) -> dict[str, object]:
        if self._etc_import_uow is None or completion is None:
            raise RuntimeError("ETC import requires its transactional unit of work and task completion port.")
        try:
            validated = self._etc_import_preview_service.validate(
                session_id=session_id, task_id=task_id, imported_by=owner_user_id, load_manifest=True,
            )
            if (validated.session.task_version != task_version
                    or validated.session.confirmed_item_set_hash != confirmed_item_set_hash):
                raise ImportJobDataError("stale_reconciliation_task_preview")
            return self._etc_import_uow.commit(validated=validated, owner_user_id=owner_user_id, completion=completion)
        except (EtcImportPreviewStaleError, StaleReconciliationPreviewError, EtcBusinessBatchInvalidTransitionError) as error:
            raise ImportJobDataError(str(error)) from error

    @staticmethod
    def file_import_job_label(session: Any, selected_file_ids: list[str]) -> str:
        selected = set(selected_file_ids)
        batch_types = {
            file.batch_type.value if isinstance(file.batch_type, BatchType) else str(file.batch_type)
            for file in session.files
            if file.id in selected and file.batch_type is not None
        }
        if batch_types == {BatchType.BANK_TRANSACTION.value}:
            return "导入 银行流水"
        if batch_types and batch_types.issubset({BatchType.INPUT_INVOICE.value, BatchType.OUTPUT_INVOICE.value}):
            return "导入 发票"
        return "导入文件"

    @staticmethod
    def _write_result_envelope(
        *,
        tax_offset_scope_keys: list[str],
        bank_scope_keys: list[str],
        input_invoice_usage_scope_keys: list[str],
        output_invoice_collection_scope_keys: list[str],
    ) -> dict[str, object]:
        scope_keys = list(
            dict.fromkeys(
                str(scope_key).strip()
                for scope_key in [
                    *tax_offset_scope_keys,
                    *bank_scope_keys,
                    *input_invoice_usage_scope_keys,
                    *output_invoice_collection_scope_keys,
                ]
                if str(scope_key).strip()
            )
        )
        return {
            "affected_scope_keys": scope_keys,
        }
