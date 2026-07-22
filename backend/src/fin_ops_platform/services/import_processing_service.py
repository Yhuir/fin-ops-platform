from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.import_job_queue import ImportJob
from fin_ops_platform.services.read_model_write_targets import normalized_scope_keys


class ImportProcessingService:
    def __init__(
        self,
        *,
        file_import_service: Any,
        tax_certified_import_service: Any,
        etc_service: Any,
        etc_reconciliation_task_service: Any,
        background_job_service: Any,
        serialize_value: Callable[[Any], Any],
        enqueue_workbench_auto_matching_for_scopes: Callable[..., Any],
        persist_confirmed_import_delta: Callable[..., Any],
        workbench_matching_scope_months_for_import_file_session: Callable[[Any, list[str]], list[str]],
        tax_offset_scope_keys_for_import_file_session: Callable[[Any, list[str]], list[str]],
        cost_statistics_scope_keys_for_import_file_session: Callable[[Any, list[str]], list[str]],
        bank_detail_scope_keys_for_import_file_session: Callable[[Any, list[str]], list[str]],
        input_invoice_usage_scope_keys_for_import_file_session: Callable[[Any, list[str]], list[str]],
        output_invoice_collection_scope_keys_for_import_file_session: Callable[[Any, list[str]], list[str]],
        link_etc_import_result_to_existing_invoices: Callable[[Any], list[str]],
        etc_import_preview_service: Any,
        oa_manual_import_create_processor: Callable[[ImportJob], dict[str, object]] | None = None,
    ) -> None:
        self._file_import_service = file_import_service
        self._tax_certified_import_service = tax_certified_import_service
        self._etc_service = etc_service
        self._etc_reconciliation_task_service = etc_reconciliation_task_service
        self._background_job_service = background_job_service
        self._serialize_value = serialize_value
        self._enqueue_workbench_auto_matching_for_scopes = enqueue_workbench_auto_matching_for_scopes
        self._persist_confirmed_import_delta = persist_confirmed_import_delta
        self._workbench_matching_scope_months_for_import_file_session = workbench_matching_scope_months_for_import_file_session
        self._tax_offset_scope_keys_for_import_file_session = tax_offset_scope_keys_for_import_file_session
        self._cost_statistics_scope_keys_for_import_file_session = cost_statistics_scope_keys_for_import_file_session
        self._bank_detail_scope_keys_for_import_file_session = bank_detail_scope_keys_for_import_file_session
        self._input_invoice_usage_scope_keys_for_import_file_session = input_invoice_usage_scope_keys_for_import_file_session
        self._output_invoice_collection_scope_keys_for_import_file_session = output_invoice_collection_scope_keys_for_import_file_session
        self._link_etc_import_result_to_existing_invoices = link_etc_import_result_to_existing_invoices
        self._etc_import_preview_service = etc_import_preview_service
        self._oa_manual_import_create_processor = oa_manual_import_create_processor

    def build_import_job_processors(self) -> dict[str, Callable[[ImportJob], dict[str, object]]]:
        processors: dict[str, Callable[[ImportJob], dict[str, object]]] = {
            "file_import.confirm": self.process_file_import_confirm_job,
            "etc_invoice_import.confirm": self.process_etc_invoice_import_confirm_job,
            "tax_certified_import.confirm": self.process_tax_certified_import_confirm_job,
        }
        if self._oa_manual_import_create_processor is not None:
            processors["oa_manual_import.create"] = self._oa_manual_import_create_processor
        return processors

    def process_tax_certified_import_confirm_job(self, import_job: ImportJob) -> dict[str, object]:
        session_id = str(import_job.payload.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("import job payload.session_id is required.")
        return self.execute_tax_certified_import_confirm(session_id)

    def process_file_import_confirm_job(self, import_job: ImportJob) -> dict[str, object]:
        session_id = str(import_job.payload.get("session_id") or "").strip()
        selected_file_ids = import_job.payload.get("selected_file_ids")
        if not session_id or not isinstance(selected_file_ids, list):
            raise ValueError("import job payload.session_id and payload.selected_file_ids are required.")
        return self.execute_file_import_confirm_job(
            session_id=session_id,
            selected_file_ids=[str(item) for item in selected_file_ids],
            owner_user_id=str(import_job.payload.get("owner_user_id") or import_job.created_by or "system"),
            background_job_id=str(import_job.payload.get("background_job_id") or "").strip(),
        )

    def process_etc_invoice_import_confirm_job(self, import_job: ImportJob) -> dict[str, object]:
        payload = import_job.payload
        return self.execute_etc_invoice_import_confirm_job(
            session_id=str(payload.get("session_id") or "").strip(),
            task_id=str(payload.get("task_id") or "").strip(),
            owner_user_id=str(payload.get("owner_user_id") or import_job.created_by or "system").strip(),
            background_job_id=str(payload.get("background_job_id") or "").strip(),
            task_version=int(payload.get("task_version") or 0),
            confirmed_item_set_hash=str(payload.get("confirmed_item_set_hash") or "").strip(),
            total=int(payload.get("total") or 0),
        )

    def execute_tax_certified_import_confirm(self, session_id: str) -> dict[str, object]:
        batch = self._tax_certified_import_service.confirm_session(session_id)
        return {
            "success": True,
            "batch": self._serialize_value(batch),
        }

    def execute_file_import_confirm_job(
        self,
        *,
        session_id: str,
        selected_file_ids: list[str],
        owner_user_id: str,
        background_job_id: str,
    ) -> dict[str, object]:
        session = self._file_import_service.get_session(session_id)
        selected = set(selected_file_ids)
        total = len(selected_file_ids)
        label = self.file_import_job_label(session, selected_file_ids)
        running_job = self._background_job_service.start_job(background_job_id) if background_job_id else None

        def progress_callback(progress_session: Any, current: int, progress_total: int) -> None:
            if running_job is None:
                return
            confirmed_count = sum(1 for file in progress_session.files if file.id in selected and file.status == "confirmed")
            self._background_job_service.update_progress(
                running_job.job_id,
                phase="confirm_files",
                message=f"正在{label} {current}/{max(progress_total, 1)}。",
                current=current,
                total=progress_total,
                result_summary={
                    "confirmed": confirmed_count,
                    "selected": progress_total,
                    "matching_results": 0,
                },
            )

        try:
            confirmed_session = self._file_import_service.confirm_session(
                session_id=session_id,
                selected_file_ids=selected_file_ids,
                progress_callback=progress_callback,
            )
            confirmed_count = sum(1 for file in confirmed_session.files if file.id in selected and file.status == "confirmed")
            scope_months = self._workbench_matching_scope_months_for_import_file_session(
                confirmed_session,
                selected_file_ids,
            )
            tax_offset_scope_keys = self._tax_offset_scope_keys_for_import_file_session(
                confirmed_session,
                selected_file_ids,
            )
            cost_statistics_scope_keys = self._cost_statistics_scope_keys_for_import_file_session(
                confirmed_session,
                selected_file_ids,
            )
            bank_detail_scope_keys = self._bank_detail_scope_keys_for_import_file_session(
                confirmed_session,
                selected_file_ids,
            )
            input_invoice_usage_scope_keys = self._input_invoice_usage_scope_keys_for_import_file_session(
                confirmed_session,
                selected_file_ids,
            )
            output_invoice_collection_scope_keys = self._output_invoice_collection_scope_keys_for_import_file_session(
                confirmed_session,
                selected_file_ids,
            )
            import_state_payload = self._file_import_service.confirmed_session_persistence_payload(
                session_id=session_id,
                selected_file_ids=selected_file_ids,
            )
            self._persist_confirmed_import_delta(
                import_state_payload=import_state_payload,
            )
            matching_job_id = None
            if any(file.status == "confirmed" for file in confirmed_session.files):
                matching_job = self._enqueue_workbench_auto_matching_for_scopes(
                    scope_months,
                    reason="import_file_confirm",
                    owner_user_id=owner_user_id,
                    source={
                        "session_id": confirmed_session.id,
                        "selected_file_ids": selected_file_ids,
                        "trigger_job_id": background_job_id,
                    },
                    triggered_by=f"import_session:{confirmed_session.id}",
                )
                matching_job_id = matching_job.job_id if matching_job is not None else None
            result_summary = {
                "confirmed": confirmed_count,
                "selected": total,
                "affected_months": scope_months,
                "enqueued_matching_job_id": matching_job_id,
                **self._write_result_envelope(
                    cost_statistics_scope_keys=cost_statistics_scope_keys,
                    tax_offset_scope_keys=tax_offset_scope_keys,
                    bank_detail_scope_keys=bank_detail_scope_keys,
                    input_invoice_usage_scope_keys=input_invoice_usage_scope_keys,
                    output_invoice_collection_scope_keys=output_invoice_collection_scope_keys,
                ),
            }
            if running_job is not None:
                self._background_job_service.succeed_job(
                    running_job.job_id,
                    f"{label}完成。",
                    result_summary=result_summary,
                )
            return result_summary
        except Exception as exc:
            if running_job is not None:
                self._background_job_service.fail_job(running_job.job_id, "后台任务失败。", str(exc))
            raise

    def execute_etc_invoice_import_confirm_job(
        self,
        *,
        session_id: str,
        task_id: str,
        owner_user_id: str,
        background_job_id: str,
        task_version: int,
        confirmed_item_set_hash: str,
        total: int,
    ) -> dict[str, object]:
        if not session_id or not task_id or task_version <= 0:
            raise ValueError("ETC import job payload requires session_id, task_id and task_version.")
        running_job = self._background_job_service.start_job(background_job_id) if background_job_id else None

        def progress_callback(result: Any) -> None:
            if running_job is None:
                return
            summary = self.etc_import_job_summary(result, total)
            self._background_job_service.update_progress(
                running_job.job_id,
                phase="persist_items",
                message=f"正在导入 ETC发票 {summary['total_current']}/{total}。",
                current=int(summary["total_current"]),
                total=total,
                result_summary={key: value for key, value in summary.items() if key != "total_current"},
            )

        try:
            validated_preview = self._etc_import_preview_service.validate(session_id=session_id, task_id=task_id)
            self._etc_reconciliation_task_service.begin_import(
                task_id=task_id,
                task_version=task_version,
                confirmed_item_set_hash=confirmed_item_set_hash,
                import_session_id=session_id,
                actor=owner_user_id,
            )
            self._etc_import_preview_service.mark_status(
                session_id,
                status="processing",
                imported_by=owner_user_id,
            )
            business_batch = self.resolve_task_etc_business_batch(
                task_id=task_id,
                owner_user_id=owner_user_id,
                idempotency_key=f"etc_business_task_import:{task_id}:{session_id}",
            )
            business_batch, result = self._etc_service.confirm_business_batch_import(
                business_batch.business_batch_id,
                session_id,
                expected_version=business_batch.version,
                idempotency_key=f"etc_import_session:{session_id}",
                progress_callback=progress_callback,
                uploads=list(validated_preview.uploads),
            )
        except Exception as exc:
            self._etc_reconciliation_task_service.mark_import_failed(
                task_id=task_id,
                task_version=task_version,
                confirmed_item_set_hash=confirmed_item_set_hash,
                actor=owner_user_id,
                note=str(exc),
            )
            if running_job is not None:
                self._background_job_service.fail_job(running_job.job_id, "后台任务失败。", str(exc))
            self._etc_import_preview_service.mark_status(
                session_id,
                status="failed",
                imported_by=owner_user_id,
                last_error=str(exc),
            )
            raise
        import_batch = next(
            (
                batch
                for batch in self._etc_service.list_import_batches()
                if batch.id in set(getattr(business_batch, "import_batch_ids", []) or [])
            ),
            None,
        )
        changed_months = self._link_etc_import_result_to_existing_invoices(result)
        summary = self.etc_import_job_summary(result, total)
        changed_scope_keys = normalized_scope_keys(changed_months)
        result_summary = {
            key: value
            for key, value in summary.items()
            if key != "total_current"
        }
        result_summary.update(
            {
                "affected_months": changed_scope_keys,
                **self._write_result_envelope(
                    cost_statistics_scope_keys=changed_scope_keys,
                    tax_offset_scope_keys=changed_scope_keys,
                    bank_detail_scope_keys=[],
                    input_invoice_usage_scope_keys=changed_scope_keys,
                    output_invoice_collection_scope_keys=[],
                ),
            }
            if changed_scope_keys
            else {"affected_months": []}
        )
        status = "partial_success" if result.failed > 0 else "succeeded"
        if status == "partial_success":
            self._etc_reconciliation_task_service.mark_import_failed(
                task_id=task_id,
                task_version=task_version,
                confirmed_item_set_hash=confirmed_item_set_hash,
                actor=owner_user_id,
                note="ETC zip import partially failed; task remains ready for retry.",
            )
        else:
            self._etc_reconciliation_task_service.mark_imported(
                task_id=task_id,
                task_version=task_version,
                confirmed_item_set_hash=confirmed_item_set_hash,
                import_batch_id=getattr(import_batch, "id", None),
                actor=owner_user_id,
            )
        self._etc_import_preview_service.mark_status(
            session_id,
            status=status,
            imported_by=owner_user_id,
        )
        message = "ETC发票导入部分完成。" if status == "partial_success" else "ETC发票导入完成。"
        if running_job is not None:
            self._background_job_service.succeed_job(
                running_job.job_id,
                message,
                result_summary=result_summary,
                status=status,
            )
        return result_summary

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
    def etc_import_job_summary(result: Any, total: int) -> dict[str, int]:
        total_current = result.imported + result.attachments_completed + result.duplicates_skipped + result.failed
        return {
            "created": result.imported,
            "imported": result.imported,
            "updated": result.attachments_completed,
            "attachments_completed": result.attachments_completed,
            "duplicates": result.duplicates_skipped,
            "failed": result.failed,
            "total": total,
            "total_current": total_current,
        }

    @staticmethod
    def _write_result_envelope(
        *,
        cost_statistics_scope_keys: list[str],
        tax_offset_scope_keys: list[str],
        bank_detail_scope_keys: list[str],
        input_invoice_usage_scope_keys: list[str],
        output_invoice_collection_scope_keys: list[str],
    ) -> dict[str, object]:
        scope_keys = normalized_scope_keys(
            [
                *cost_statistics_scope_keys,
                *tax_offset_scope_keys,
                *bank_detail_scope_keys,
                *input_invoice_usage_scope_keys,
                *output_invoice_collection_scope_keys,
            ]
        )
        return {
            "affected_scope_keys": scope_keys,
            "read_model_scope_keys": scope_keys,
            "freshness_targets": [],
            "operation_barrier_targets": [],
        }

    def resolve_task_etc_business_batch(
        self,
        *,
        task_id: str,
        owner_user_id: str,
        idempotency_key: str,
    ) -> Any:
        existing_batches = self._etc_service.list_business_batches(task_id=task_id)
        for batch in existing_batches:
            if getattr(batch, "is_active", False):
                return batch
        return self._etc_service.create_business_batch(
            task_id=task_id,
            owner_user_id=owner_user_id,
            idempotency_key=idempotency_key,
        )
