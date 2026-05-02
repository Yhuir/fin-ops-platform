from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Callable

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.state_store import ApplicationStateStore


RESET_BANK_TRANSACTIONS_ACTION = "reset_bank_transactions"
RESET_INVOICES_ACTION = "reset_invoices"
RESET_OA_AND_REBUILD_ACTION = "reset_oa_and_rebuild"

PROHIBITED_RESET_TARGETS = (
    "form_data_db.form_data",
    "fin_ops_platform_app.app_settings",
    "fin_ops_platform_app.*_meta",
    "fin_ops_platform_app.import_file_metadata",
)

SettingsDataResetProgressCallback = Callable[[str, str, int, int], None]


@dataclass(slots=True)
class SettingsDataResetResult:
    action: str
    status: str
    cleared_collections: list[str]
    deleted_counts: dict[str, int]
    protected_targets: list[str]
    rebuild_status: str
    message: str

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class SettingsDataResetService:
    def __init__(
        self,
        *,
        state_store: ApplicationStateStore,
        import_service: Any,
        file_import_service: Any,
        matching_service: Any,
        workbench_override_service: Any,
        workbench_pair_relation_service: Any,
        workbench_read_model_service: Any,
        tax_certified_import_service: Any,
    ) -> None:
        self._state_store = state_store
        self._import_service = import_service
        self._file_import_service = file_import_service
        self._matching_service = matching_service
        self._workbench_override_service = workbench_override_service
        self._workbench_pair_relation_service = workbench_pair_relation_service
        self._workbench_read_model_service = workbench_read_model_service
        self._tax_certified_import_service = tax_certified_import_service

    @staticmethod
    def supported_actions() -> list[str]:
        return [
            RESET_BANK_TRANSACTIONS_ACTION,
            RESET_INVOICES_ACTION,
            RESET_OA_AND_REBUILD_ACTION,
        ]

    @staticmethod
    def protected_targets() -> list[str]:
        return list(PROHIBITED_RESET_TARGETS)

    def execute(
        self,
        action: str,
        *,
        progress_callback: SettingsDataResetProgressCallback | None = None,
    ) -> SettingsDataResetResult:
        normalized_action = str(action or "").strip()
        if normalized_action == RESET_BANK_TRANSACTIONS_ACTION:
            return self._reset_bank_transactions(progress_callback=progress_callback)
        if normalized_action == RESET_INVOICES_ACTION:
            return self._reset_invoices(progress_callback=progress_callback)
        if normalized_action == RESET_OA_AND_REBUILD_ACTION:
            return self._reset_oa_and_rebuild(progress_callback=progress_callback)
        raise ValueError(f"unsupported reset action: {normalized_action}")

    def _reset_bank_transactions(
        self,
        *,
        progress_callback: SettingsDataResetProgressCallback | None,
    ) -> SettingsDataResetResult:
        self._emit_progress(progress_callback, "prepare_imports", "正在统计银行流水域数据。", 0, 4)
        imports_snapshot, import_deleted_counts = self._build_filtered_imports_snapshot(
            remove_bank_transactions=True,
            remove_invoices=False,
        )
        self._emit_progress(progress_callback, "prepare_file_imports", "正在统计银行流水导入文件。", 1, 4)
        file_imports_snapshot, removed_file_paths, file_deleted_counts = self._build_filtered_file_imports_snapshot(
            removed_batch_types={BatchType.BANK_TRANSACTION.value}
        )
        self._emit_progress(progress_callback, "persist_state", "正在写入银行流水重置结果。", 2, 4)
        self._state_store.save(
            {
                "imports": imports_snapshot,
                "file_imports": file_imports_snapshot,
                "matching": {},
                "workbench_overrides": {},
                "workbench_pair_relations": {},
                "workbench_read_models": {},
            }
        )
        self._emit_progress(progress_callback, "delete_import_files", "正在删除银行流水导入文件。", 3, 4)
        deleted_blob_count = self._state_store.delete_import_files(removed_file_paths)
        deleted_counts = {
            **import_deleted_counts,
            **file_deleted_counts,
            "matching_runs": len(self._matching_service.list_runs()),
            "matching_results": len(self._matching_service.list_results()),
            "workbench_row_overrides": len(self._row_overrides()),
            "workbench_pair_relations": len(self._pair_relations()),
            "workbench_read_models": len(self._read_models()),
            "stored_import_files": deleted_blob_count,
        }
        return SettingsDataResetResult(
            action=RESET_BANK_TRANSACTIONS_ACTION,
            status="completed",
            cleared_collections=[
                "bank_transactions",
                "matching_runs",
                "matching_results",
                "workbench_row_overrides",
                "workbench_pair_relations",
                "workbench_read_models",
                "import_batches(bank_transaction)",
                "file_import_sessions(bank_transaction)",
                "file_import_files(bank_transaction)",
                "import_file_blobs(bank_transaction)",
            ],
            deleted_counts=deleted_counts,
            protected_targets=self.protected_targets(),
            rebuild_status="not_applicable",
            message="已清除银行流水域数据，并保留发票与 OA 源数据。",
        )

    def _reset_invoices(
        self,
        *,
        progress_callback: SettingsDataResetProgressCallback | None,
    ) -> SettingsDataResetResult:
        self._emit_progress(progress_callback, "prepare_imports", "正在统计发票域数据。", 0, 5)
        imports_snapshot, import_deleted_counts = self._build_filtered_imports_snapshot(
            remove_bank_transactions=False,
            remove_invoices=True,
        )
        self._emit_progress(progress_callback, "prepare_file_imports", "正在统计发票导入文件。", 1, 5)
        file_imports_snapshot, removed_file_paths, file_deleted_counts = self._build_filtered_file_imports_snapshot(
            removed_batch_types={BatchType.INPUT_INVOICE.value, BatchType.OUTPUT_INVOICE.value}
        )
        self._emit_progress(progress_callback, "prepare_tax_certified_imports", "正在统计税金认证记录。", 2, 5)
        tax_deleted_counts = self._tax_import_deleted_counts()
        self._emit_progress(progress_callback, "persist_state", "正在写入发票重置结果。", 3, 5)
        self._state_store.save(
            {
                "imports": imports_snapshot,
                "file_imports": file_imports_snapshot,
                "matching": {},
                "workbench_overrides": {},
                "workbench_pair_relations": {},
                "workbench_read_models": {},
            }
        )
        self._state_store.save_tax_certified_imports({})
        self._emit_progress(progress_callback, "delete_import_files", "正在删除发票导入文件。", 4, 5)
        deleted_blob_count = self._state_store.delete_import_files(removed_file_paths)
        deleted_counts = {
            **import_deleted_counts,
            **file_deleted_counts,
            "matching_runs": len(self._matching_service.list_runs()),
            "matching_results": len(self._matching_service.list_results()),
            "workbench_row_overrides": len(self._row_overrides()),
            "workbench_pair_relations": len(self._pair_relations()),
            "workbench_read_models": len(self._read_models()),
            "tax_certified_import_sessions": tax_deleted_counts["sessions"],
            "tax_certified_import_batches": tax_deleted_counts["batches"],
            "tax_certified_import_records": tax_deleted_counts["records"],
            "stored_import_files": deleted_blob_count,
        }
        return SettingsDataResetResult(
            action=RESET_INVOICES_ACTION,
            status="completed",
            cleared_collections=[
                "invoices",
                "matching_runs",
                "matching_results",
                "workbench_row_overrides",
                "workbench_pair_relations",
                "workbench_read_models",
                "tax_certified_import_sessions",
                "tax_certified_import_batches",
                "tax_certified_import_records",
                "import_batches(input/output_invoice)",
                "file_import_sessions(input/output_invoice)",
                "file_import_files(input/output_invoice)",
                "import_file_blobs(input/output_invoice)",
            ],
            deleted_counts=deleted_counts,
            protected_targets=self.protected_targets(),
            rebuild_status="not_applicable",
            message="已清除发票域数据、税金认证记录及相关工作台状态，不影响 OA 源数据。",
        )

    def _reset_oa_and_rebuild(
        self,
        *,
        progress_callback: SettingsDataResetProgressCallback | None,
    ) -> SettingsDataResetResult:
        self._emit_progress(progress_callback, "clear_oa_state", "正在清空 OA 工作台人工状态。", 0, 2)
        deleted_counts = {
            "workbench_row_overrides": len(self._row_overrides()),
            "workbench_pair_relations": len(self._pair_relations()),
            "workbench_read_models": len(self._read_models()),
        }
        self._emit_progress(progress_callback, "persist_state", "正在写入 OA 重置结果。", 1, 2)
        self._state_store.save_workbench_overrides({})
        self._state_store.save_workbench_pair_relations({})
        self._state_store.save_workbench_read_models({})
        return SettingsDataResetResult(
            action=RESET_OA_AND_REBUILD_ACTION,
            status="completed",
            cleared_collections=[
                "workbench_row_overrides",
                "workbench_pair_relations",
                "workbench_read_models",
            ],
            deleted_counts=deleted_counts,
            protected_targets=self.protected_targets(),
            rebuild_status="pending",
            message="已清空 OA 工作台人工状态与读模型，后续需要重新拉取 OA 并重建关联台。",
        )

    @staticmethod
    def _emit_progress(
        progress_callback: SettingsDataResetProgressCallback | None,
        phase: str,
        message: str,
        current: int,
        total: int,
    ) -> None:
        if progress_callback is not None:
            progress_callback(phase, message, current, total)

    def _build_filtered_imports_snapshot(
        self,
        *,
        remove_bank_transactions: bool,
        remove_invoices: bool,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        snapshot = deepcopy(self._import_service.snapshot())
        batches = snapshot.get("batches", {})
        invoices = list(snapshot.get("invoices", []))
        transactions = list(snapshot.get("transactions", []))

        removed_batch_count = 0
        filtered_batches: dict[str, Any] = {}
        for batch_id, preview in batches.items():
            batch_type = self._preview_batch_type(preview)
            if remove_bank_transactions and batch_type == BatchType.BANK_TRANSACTION.value:
                removed_batch_count += 1
                continue
            if remove_invoices and batch_type in {BatchType.INPUT_INVOICE.value, BatchType.OUTPUT_INVOICE.value}:
                removed_batch_count += 1
                continue
            filtered_batches[str(batch_id)] = preview

        removed_invoice_count = len(invoices) if remove_invoices else 0
        removed_transaction_count = len(transactions) if remove_bank_transactions else 0

        snapshot["batches"] = filtered_batches
        snapshot["invoices"] = [] if remove_invoices else invoices
        snapshot["transactions"] = [] if remove_bank_transactions else transactions
        return (
            snapshot,
            {
                "import_batches": removed_batch_count,
                "invoices": removed_invoice_count,
                "bank_transactions": removed_transaction_count,
            },
        )

    def _build_filtered_file_imports_snapshot(
        self,
        *,
        removed_batch_types: set[str],
    ) -> tuple[dict[str, Any], list[str], dict[str, int]]:
        snapshot = deepcopy(self._file_import_service.snapshot())
        sessions = snapshot.get("sessions", {})
        filtered_sessions: dict[str, Any] = {}
        removed_session_count = 0
        removed_file_count = 0
        removed_file_paths: list[str] = []
        normalized_removed_batch_types = {str(item).strip() for item in removed_batch_types if str(item).strip()}

        for session_id, session in sessions.items():
            files = list(self._get_value(session, "files") or [])
            kept_files: list[Any] = []
            removed_any = False
            for file_item in files:
                batch_type = self._file_batch_type(file_item)
                if batch_type in normalized_removed_batch_types:
                    removed_any = True
                    removed_file_count += 1
                    stored_file_path = self._get_value(file_item, "stored_file_path")
                    if stored_file_path:
                        removed_file_paths.append(str(stored_file_path))
                    continue
                kept_files.append(file_item)
            if not kept_files:
                if removed_any:
                    removed_session_count += 1
                continue
            updated_session = deepcopy(session)
            self._set_value(updated_session, "files", kept_files)
            self._set_value(updated_session, "file_count", len(kept_files))
            filtered_sessions[str(session_id)] = updated_session

        snapshot["sessions"] = filtered_sessions
        return (
            snapshot,
            removed_file_paths,
            {
                "file_import_sessions": removed_session_count,
                "file_import_files": removed_file_count,
            },
        )

    def _tax_import_deleted_counts(self) -> dict[str, int]:
        snapshot = self._tax_certified_import_service.snapshot()
        return {
            "sessions": len(snapshot.get("sessions", {})),
            "batches": len(snapshot.get("batches", {})),
            "records": len(snapshot.get("records", {})),
        }

    def _row_overrides(self) -> dict[str, Any]:
        snapshot = self._workbench_override_service.snapshot()
        row_overrides = snapshot.get("row_overrides")
        return row_overrides if isinstance(row_overrides, dict) else {}

    def _pair_relations(self) -> dict[str, Any]:
        snapshot = self._workbench_pair_relation_service.snapshot()
        pair_relations = snapshot.get("pair_relations")
        return pair_relations if isinstance(pair_relations, dict) else {}

    def _read_models(self) -> dict[str, Any]:
        snapshot = self._workbench_read_model_service.snapshot()
        read_models = snapshot.get("read_models")
        return read_models if isinstance(read_models, dict) else {}

    @staticmethod
    def _preview_batch_type(preview: Any) -> str:
        batch = SettingsDataResetService._get_value(preview, "batch")
        batch_type = SettingsDataResetService._get_value(batch, "batch_type")
        if batch_type is None:
            return ""
        return str(getattr(batch_type, "value", batch_type))

    @staticmethod
    def _file_batch_type(file_item: Any) -> str:
        batch_type = SettingsDataResetService._get_value(file_item, "batch_type")
        if batch_type is None:
            return ""
        return str(getattr(batch_type, "value", batch_type))

    @staticmethod
    def _get_value(container: Any, key: str) -> Any:
        if isinstance(container, dict):
            return container.get(key)
        return getattr(container, key, None)

    @staticmethod
    def _set_value(container: Any, key: str, value: Any) -> None:
        if isinstance(container, dict):
            container[key] = value
            return
        setattr(container, key, value)
