from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from fin_ops_platform.services.state_store_protocol import ApplicationStateStoreProtocol


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


class SettingsDataResetPairSnapshotPort:
    def __init__(
        self,
        *,
        pair_relation_snapshot: Callable[[], dict[str, Any]],
    ) -> None:
        self._pair_relation_snapshot = pair_relation_snapshot

    def pair_relations(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        pair_relations = snapshot.get("pair_relations")
        return pair_relations if isinstance(pair_relations, dict) else {}

    def snapshot(self) -> dict[str, Any]:
        return dict(self._pair_relation_snapshot() or {})


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
        state_store: ApplicationStateStoreProtocol,
        import_service: Any,
        file_import_service: Any,
        matching_service: Any,
        workbench_override_service: Any,
        workbench_pair_snapshot_port: SettingsDataResetPairSnapshotPort,
        tax_certified_import_service: Any,
    ) -> None:
        self._state_store = state_store
        self._import_service = import_service
        self._file_import_service = file_import_service
        self._matching_service = matching_service
        self._workbench_override_service = workbench_override_service
        self._workbench_pair_snapshot_port = workbench_pair_snapshot_port
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
        reset_context: dict[str, str] | None = None,
    ) -> SettingsDataResetResult:
        normalized_action = str(action or "").strip()
        if normalized_action == RESET_BANK_TRANSACTIONS_ACTION:
            return self._reset_bank_transactions(
                progress_callback=progress_callback,
                reset_context=reset_context,
            )
        if normalized_action == RESET_INVOICES_ACTION:
            return self._reset_invoices(
                progress_callback=progress_callback,
                reset_context=reset_context,
            )
        if normalized_action == RESET_OA_AND_REBUILD_ACTION:
            return self._reset_oa_and_rebuild(
                progress_callback=progress_callback,
                reset_context=reset_context,
            )
        raise ValueError(f"unsupported reset action: {normalized_action}")

    def preview(self, action: str) -> dict[str, Any]:
        normalized_action = str(action or "").strip()
        if normalized_action not in self.supported_actions():
            raise ValueError(f"unsupported reset action: {normalized_action}")
        row_ids: list[str] = []
        case_ids: list[str] = []
        if normalized_action == RESET_OA_AND_REBUILD_ACTION:
            row_ids, case_ids = self._oa_target_ids()
        return dict(
            self._state_store.preview_settings_data_reset(
                normalized_action,
                row_ids=row_ids,
                case_ids=case_ids,
            )
        )

    def _reset_bank_transactions(
        self,
        *,
        progress_callback: SettingsDataResetProgressCallback | None,
        reset_context: dict[str, str] | None,
    ) -> SettingsDataResetResult:
        self._emit_progress(progress_callback, "reset_data", "正在事务性清除银行流水域数据。", 0, 2)
        reset_result = dict(
            self._state_store.reset_bank_transaction_data(
                source_snapshot=self._local_source_snapshot(),
                reset_context=reset_context,
            )
        )
        removed_file_paths = list(reset_result.pop("stored_import_file_paths", []) or [])
        self._emit_progress(progress_callback, "delete_import_files", "正在删除银行流水导入文件。", 1, 2)
        deleted_blob_count = self._state_store.delete_import_files(removed_file_paths)
        deleted_counts = {
            **reset_result,
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
                "bank_transaction_categories",
                "bank_flow_rule_batches",
                "no_oa_bank_batches",
                "turnover_relations",
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
        reset_context: dict[str, str] | None,
    ) -> SettingsDataResetResult:
        self._emit_progress(progress_callback, "reset_data", "正在事务性清除发票域数据。", 0, 2)
        reset_result = dict(
            self._state_store.reset_invoice_data(
                source_snapshot=self._local_source_snapshot(),
                reset_context=reset_context,
            )
        )
        removed_file_paths = list(reset_result.pop("stored_import_file_paths", []) or [])
        self._emit_progress(progress_callback, "delete_import_files", "正在删除发票导入文件。", 1, 2)
        deleted_blob_count = self._state_store.delete_import_files(removed_file_paths)
        deleted_counts = {
            **reset_result,
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
        reset_context: dict[str, str] | None,
    ) -> SettingsDataResetResult:
        self._emit_progress(progress_callback, "clear_oa_state", "正在清空 OA 工作台人工状态。", 0, 2)
        oa_row_ids, oa_case_ids = self._oa_target_ids()
        self._emit_progress(progress_callback, "persist_state", "正在写入 OA 重置结果。", 1, 2)
        deleted_counts = self._state_store.reset_oa_workbench_data(
            row_ids=oa_row_ids,
            case_ids=oa_case_ids,
            source_snapshot=self._local_source_snapshot(),
            reset_context=reset_context,
        )
        return SettingsDataResetResult(
            action=RESET_OA_AND_REBUILD_ACTION,
            status="completed",
            cleared_collections=[
                "workbench_row_overrides",
                "workbench_pair_relations",
            ],
            deleted_counts=deleted_counts,
            protected_targets=self.protected_targets(),
            rebuild_status="pending",
            message="已清空 OA 相关工作台人工状态，后续需要重新拉取 OA 并重建关联台。",
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

    def _row_overrides(self) -> dict[str, Any]:
        snapshot = self._workbench_override_service.snapshot()
        row_overrides = snapshot.get("row_overrides")
        return row_overrides if isinstance(row_overrides, dict) else {}

    def _pair_relations(self) -> dict[str, Any]:
        return self._workbench_pair_snapshot_port.pair_relations()

    def _oa_target_ids(self) -> tuple[list[str], list[str]]:
        row_ids = [
            str(override.get("row_id") or override_key)
            for override_key, override in self._row_overrides().items()
            if isinstance(override, dict)
            and self._is_oa_workbench_row_override(override_key, override)
        ]
        case_ids = [
            str(case_id)
            for case_id, relation in self._pair_relations().items()
            if self._is_oa_pair_relation(relation)
        ]
        return row_ids, case_ids

    def _local_source_snapshot(self) -> dict[str, Any] | None:
        if self._state_store.storage_backend != "local_pickle":
            return None
        return {
            "imports": self._import_service.snapshot(),
            "file_imports": self._file_import_service.snapshot(),
            "matching": self._matching_service.snapshot(),
            "workbench_overrides": self._workbench_override_service.snapshot(),
            "workbench_pair_relations": self._workbench_pair_snapshot_port.snapshot(),
            "tax_certified_imports": self._tax_certified_import_service.snapshot(),
        }

    @classmethod
    def _is_oa_workbench_row_override(cls, row_id: str, override: Any) -> bool:
        if cls._is_oa_derived_row_id(row_id):
            return True
        if not isinstance(override, dict):
            return False
        if str(
            override.get("row_type") or override.get("type") or ""
        ).strip().lower() == "oa":
            return True
        return cls._payload_references_oa_derived_row(override)

    @classmethod
    def _is_oa_pair_relation(cls, relation: Any) -> bool:
        if not isinstance(relation, dict):
            return False
        row_ids = relation.get("row_ids")
        if not isinstance(row_ids, list):
            return False
        return any(cls._is_oa_derived_row_id(row_id) for row_id in row_ids)

    @staticmethod
    def _is_oa_derived_row_id(row_id: Any) -> bool:
        normalized_row_id = str(row_id or "").strip()
        return normalized_row_id.startswith("oa-") or normalized_row_id.startswith("oa-att-inv-")

    @classmethod
    def _payload_references_oa_derived_row(cls, value: Any, *, id_context: bool = False) -> bool:
        if isinstance(value, dict):
            if str(value.get("type") or "").strip().lower() == "oa":
                return True
            for key, nested_value in value.items():
                if cls._payload_references_oa_derived_row(
                    nested_value,
                    id_context=id_context or cls._is_row_id_reference_key(key),
                ):
                    return True
            return False
        if isinstance(value, list):
            return any(cls._payload_references_oa_derived_row(item, id_context=id_context) for item in value)
        if isinstance(value, tuple):
            return any(cls._payload_references_oa_derived_row(item, id_context=id_context) for item in value)
        if id_context:
            return cls._is_oa_derived_row_id(value)
        return False

    @staticmethod
    def _is_row_id_reference_key(key: Any) -> bool:
        normalized_key = str(key or "").strip().lower()
        return normalized_key in {
            "id",
            "row_id",
            "row_ids",
            "source_row_id",
            "source_row_ids",
            "linked_row_id",
            "linked_row_ids",
            "affected_row_id",
            "affected_row_ids",
        }
