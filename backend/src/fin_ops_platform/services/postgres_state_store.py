from __future__ import annotations

import hashlib
import re
from dataclasses import is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from fin_ops_platform.services.bank_flow_rule_batch_canonical_query import (
    bank_flow_rule_batch_candidate_guard,
    bank_flow_rule_batch_effective_categories,
    bank_flow_rule_batch_rule_proof,
    bank_flow_rule_batch_selected_row_proofs,
    build_live_bank_flow_rule_batch_service,
)
from fin_ops_platform.services.file_object_migration import verified_object_key_from_uri, write_verified_object
from fin_ops_platform.services.object_storage import (
    ObjectStorageReadError,
    ObjectStorageRepository,
    ObjectStorageWriteError,
)
from fin_ops_platform.services.postgres_repositories import (
    PostgresBankTransactionCategoryRepository,
    PostgresCoreRepository,
    PostgresEtcImportSessionRepository,
    PostgresOAProjectionRepository,
    PostgresOpsTaxEtcRepository,
    PostgresSettingsDataResetRepository,
    PostgresWorkbenchRelationRepository,
    PostgresWorkbenchMatchingQueueRepository,
    PostgresWorkbenchRepository,
)
from fin_ops_platform.services.postgres_repositories.bank_flow_rule_batch_canonical_query import (
    BankFlowRuleBatchCanonicalQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.common import run_in_transaction
from fin_ops_platform.services.postgres_snapshot_contracts import (
    normalize_no_oa_bank_batches,
    normalize_turnover_relations,
    normalize_workbench_pair_relations,
)
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository
from fin_ops_platform.services.state_store_protocol import default_settings_access_control

APP_SETTINGS_KEY = "app_settings"
GRIDFS_REF_PREFIX = "gridfs://"
FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _default_app_settings_payload() -> dict[str, Any]:
    return {
        "completed_project_ids": [],
        "manual_projects": [],
        "synced_projects": [],
        "bank_account_mappings": [],
        **default_settings_access_control(),
        "workbench_column_layouts": {},
        "oa_retention": {},
        "oa_import": {},
        "oa_invoice_offset": {},
        "bank_transaction_tags": {},
        "pending_invoice_tag_groups": {},
        "pending_output_invoice_tag_groups": {},
        "bank_flow_rule_batch_tag_rules": {},
        "cost_statistics_tag_selection": {},
        "input_invoice_usage_payment_status_rules": {},
    }


def _jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def _dedupe_text_values(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def _normalize_manual_oa_imports(payload: object) -> dict[str, object]:
    raw_payload = payload if isinstance(payload, dict) else {}
    raw_entries = raw_payload.get("entries")
    entries: dict[str, object] = {}
    if isinstance(raw_entries, dict):
        for row_id, entry in raw_entries.items():
            normalized_row_id = str(row_id or "").strip()
            if not normalized_row_id:
                continue
            entry_payload = dict(entry) if isinstance(entry, dict) else {}
            entry_payload["row_id"] = normalized_row_id
            entries[normalized_row_id] = entry_payload
    for row_id in _dedupe_text_values(raw_payload.get("row_ids") if isinstance(raw_payload, dict) else []):
        entries.setdefault(row_id, {"row_id": row_id, "source": "manual_oa_import"})
    audit_log = raw_payload.get("audit_log")
    return {
        "row_ids": sorted(entries),
        "entries": entries,
        "audit_log": list(audit_log) if isinstance(audit_log, list) else [],
    }


def _sanitize_name(file_name: str) -> str:
    cleaned = FILENAME_SAFE_RE.sub("_", file_name).strip("._")
    return cleaned or "uploaded_file"


class PostgresStateStore:
    def __init__(
        self,
        *,
        data_dir: Path,
        connection: Any,
        sql_read_connection: Any | None = None,
        object_storage_repository: ObjectStorageRepository | None = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._connection = connection
        self._sql_read_connection = sql_read_connection or connection
        self._object_storage_repository = object_storage_repository
        self._object_storage_backend = str(getattr(object_storage_repository, "backend", "minio")) if object_storage_repository is not None else None
        self._object_storage_bucket = str(getattr(object_storage_repository, "bucket", "")) if object_storage_repository is not None else None
        self._core_repository = PostgresCoreRepository(connection)
        self._oa_projection_repository = PostgresOAProjectionRepository(connection)
        self._ops_tax_etc_repository = PostgresOpsTaxEtcRepository(connection)
        self._etc_import_session_repository = PostgresEtcImportSessionRepository(connection)
        self._workbench_matching_queue_repository = PostgresWorkbenchMatchingQueueRepository(connection)
        self._bank_flow_rule_batch_canonical_query_repository = (
            BankFlowRuleBatchCanonicalQueryRepository(self._sql_read_connection)
            if callable(getattr(self._sql_read_connection, "transaction", None))
            else None
        )
        self._workbench_repository = PostgresWorkbenchRepository(connection)
        self._bank_transaction_category_repository = PostgresBankTransactionCategoryRepository(connection)
        self._workbench_relation_repository = PostgresWorkbenchRelationRepository(connection)
        self._file_root = self._data_dir / "postgres_files"
        if self._object_storage_repository is None:
            self._file_root.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def storage_backend(self) -> str:
        return "postgres"

    @property
    def storage_mode(self) -> str:
        return "postgres"

    @property
    def mongo_database_name(self) -> str | None:
        return None

    def close(self) -> None:
        connections = {id(self._connection): self._connection, id(self._sql_read_connection): self._sql_read_connection}
        for connection in connections.values():
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def health_summary(self) -> dict[str, object]:
        summary: dict[str, object]
        if hasattr(self._connection, "health_summary"):
            summary = dict(self._connection.health_summary())
        else:
            summary = {"postgres_status": "unknown"}
        try:
            summary["runtime_infrastructure"] = RuntimeMonitoringRepository(self._connection).health_summary()
        except Exception as exc:  # pragma: no cover - health should degrade instead of blocking readiness.
            summary["runtime_infrastructure"] = {"status": "error", "error": str(exc)}
        return summary

    def ready_health_summary(self) -> dict[str, object]:
        summary: dict[str, object]
        if hasattr(self._connection, "health_summary"):
            summary = dict(self._connection.health_summary())
        else:
            summary = {"postgres_status": "unknown"}
        try:
            summary["runtime_infrastructure"] = RuntimeMonitoringRepository(self._connection).ready_health_summary()
        except Exception as exc:  # pragma: no cover - readiness should degrade instead of blocking probes.
            summary["runtime_infrastructure"] = {"status": "error", "error": str(exc)}
        return summary

    def app_status_runtime_snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        try:
            return RuntimeMonitoringRepository(self._connection).app_status_runtime_snapshot()
        except Exception as exc:  # pragma: no cover - app status should degrade instead of hiding runtime failures.
            payload = {
                "status": "unavailable",
                "last_error": str(exc) or exc.__class__.__name__,
            }
            return {
                "worker_statuses": {"__runtime__": dict(payload)},
                "outbox_statuses": {"__runtime__": dict(payload)},
            }

    @property
    def oa_projection_repository(self) -> PostgresOAProjectionRepository:
        return self._oa_projection_repository

    def load_app_settings(self) -> dict[str, Any]:
        payload = self._load_settings(APP_SETTINGS_KEY)
        if not payload:
            return _default_app_settings_payload()
        return {**_default_app_settings_payload(), **payload}

    def save_app_settings(self, payload: dict[str, Any]) -> None:
        self._save_settings(APP_SETTINGS_KEY, payload)

    def begin_settings_acl_critical_section(self, expected_version: int):
        return self._ops_tax_etc_repository.begin_settings_acl_critical_section(expected_version)

    def recover_settings_acl_commit(self, mutation_id: str) -> dict[str, Any]:
        return self._ops_tax_etc_repository.recover_settings_acl_commit(mutation_id)

    def save_app_settings_for_bank_flow_rule_version_in_transaction(
        self,
        payload: dict[str, Any],
        *,
        expected_version: int,
        transaction: Any,
    ) -> dict[str, Any] | None:
        return self._ops_tax_etc_repository.save_app_settings_for_bank_flow_rule_version_in_transaction(
            payload,
            expected_version=expected_version,
            transaction=transaction,
        )

    def save_app_settings_for_batch_accounting_tag_selection_version_in_transaction(
        self,
        payload: dict[str, Any],
        *,
        expected_version: int,
        transaction: Any,
    ) -> dict[str, Any] | None:
        return self._ops_tax_etc_repository.save_app_settings_for_batch_accounting_tag_selection_version_in_transaction(
            payload,
            expected_version=expected_version,
            transaction=transaction,
        )

    def save_app_settings_for_versioned_family_in_transaction(
        self,
        payload: dict[str, Any],
        *,
        family_key: str,
        expected_version: int,
        transaction: Any,
    ) -> dict[str, Any] | None:
        return self._ops_tax_etc_repository.save_app_settings_for_versioned_family_in_transaction(
            payload,
            family_key=family_key,
            expected_version=expected_version,
            transaction=transaction,
        )

    def load_pending_invoice_commands(self) -> dict[str, Any]:
        snapshot = self._ops_tax_etc_repository.load_pending_invoice_commands()
        if snapshot:
            return snapshot
        return {}

    def save_pending_invoice_commands(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_pending_invoice_commands(snapshot)

    def load_oa_attachment_invoice_cache_entry(self, cache_key: str) -> dict[str, object] | None:
        return self._ops_tax_etc_repository.load_oa_attachment_invoice_cache_entry(cache_key)

    def save_oa_attachment_invoice_cache_entry(self, cache_key: str, payload: dict[str, object]) -> None:
        self._ops_tax_etc_repository.save_oa_attachment_invoice_cache_entry(cache_key, payload)

    def clear_oa_attachment_invoice_cache(self) -> int:
        return self._ops_tax_etc_repository.clear_oa_attachment_invoice_cache()

    def load_oa_sync_state(self) -> dict[str, Any]:
        return self._ops_tax_etc_repository.load_oa_sync_state()

    def save_oa_sync_state(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_oa_sync_state(snapshot)

    def load_manual_oa_imports(self) -> dict[str, object]:
        payload = self._ops_tax_etc_repository.load_manual_oa_imports()
        return _normalize_manual_oa_imports(payload)

    def save_manual_oa_imports(self, payload: dict[str, object]) -> None:
        normalized = _normalize_manual_oa_imports(payload)
        self._ops_tax_etc_repository.save_manual_oa_imports(normalized)

    def add_manual_oa_imports(
        self,
        row_ids: list[str],
        *,
        actor_id: str | None = None,
        audit: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload = _normalize_manual_oa_imports(self.load_manual_oa_imports())
        entries = dict(payload.get("entries") if isinstance(payload.get("entries"), dict) else {})
        imported: list[str] = []
        already_imported: list[str] = []
        for row_id in _dedupe_text_values(row_ids):
            if row_id in entries:
                already_imported.append(row_id)
                continue
            entry = {
                "row_id": row_id,
                "source": "manual_oa_import",
                "actor_id": actor_id,
                "imported_at": datetime.now(UTC).isoformat(),
                "audit": self._serialize_value(dict(audit if isinstance(audit, dict) else {})),
            }
            entries[row_id] = entry
            imported.append(row_id)
        payload["entries"] = entries
        payload["row_ids"] = sorted(entries)
        self.save_manual_oa_imports(payload)
        return {"imported": imported, "already_imported": already_imported, "entries": entries, "row_ids": payload["row_ids"]}

    def remove_manual_oa_import(self, row_id: str, *, actor_id: str | None = None) -> bool:
        normalized_row_id = str(row_id or "").strip()
        if not normalized_row_id:
            return False
        payload = _normalize_manual_oa_imports(self.load_manual_oa_imports())
        entries = dict(payload.get("entries") if isinstance(payload.get("entries"), dict) else {})
        removed = entries.pop(normalized_row_id, None) is not None
        if not removed:
            return False
        payload["entries"] = entries
        payload["row_ids"] = sorted(entries)
        audit_log = list(payload.get("audit_log") if isinstance(payload.get("audit_log"), list) else [])
        audit_log.append({"row_id": normalized_row_id, "actor_id": actor_id, "action": "remove", "removed_at": datetime.now(UTC).isoformat()})
        payload["audit_log"] = audit_log
        self.save_manual_oa_imports(payload)
        return True

    def load_tax_certified_imports(self) -> dict[str, Any]:
        snapshot = self._ops_tax_etc_repository.load_tax_certified_imports()
        if snapshot:
            return snapshot
        return {}

    def save_tax_certified_imports(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_tax_certified_imports(snapshot)

    def save_tax_offset_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        return self._ops_tax_etc_repository.save_tax_offset_plan(plan)

    def load_etc_state(self) -> dict[str, Any]:
        return self._ops_tax_etc_repository.load_etc_state()

    def list_etc_business_batch_summaries(self, **query: Any) -> dict[str, Any]:
        return self._ops_tax_etc_repository.list_etc_business_batch_summaries(**query)

    def get_etc_business_batch_record(self, business_batch_id: str) -> dict[str, Any] | None:
        return self._ops_tax_etc_repository.get_etc_business_batch_record(business_batch_id)

    def list_etc_invoice_records_by_ids(self, invoice_ids: list[str]) -> list[dict[str, Any]]:
        return self._ops_tax_etc_repository.list_etc_invoice_records_by_ids(invoice_ids)

    def get_etc_reconciliation_task_record(self, task_id: str) -> dict[str, Any] | None:
        return self._ops_tax_etc_repository.get_etc_reconciliation_task_record(task_id)

    def save_etc_state(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_etc_state(snapshot)

    def save_etc_oa_draft_attempt(
        self,
        snapshot: dict[str, Any],
        *,
        business_batch_id: str,
        expected_version: int,
    ) -> bool:
        return self._ops_tax_etc_repository.save_etc_oa_draft_attempt(
            snapshot,
            business_batch_id=business_batch_id,
            expected_version=expected_version,
        )

    def load_etc_reconciliation_state(self) -> dict[str, Any]:
        return self._ops_tax_etc_repository.load_etc_reconciliation_state()

    def save_etc_reconciliation_state(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_etc_reconciliation_state(snapshot)

    def store_etc_reconciliation_file(self, *, task_id: str, file_id: str, file_name: str, content: bytes) -> str:
        if self._object_storage_repository is not None:
            return self._store_object_file(namespace="etc_reconciliation", file_id=file_id, file_name=file_name, content=content)
        stored_file_path = self._store_local_file("etc_reconciliation", file_id, file_name, content)
        self._save_file_object(file_id=file_id, file_name=file_name, stored_file_path=stored_file_path, content=content)
        return stored_file_path

    @property
    def etc_import_session_repository(self) -> PostgresEtcImportSessionRepository:
        return self._etc_import_session_repository

    def store_etc_import_archive(
        self,
        *,
        session_id: str,
        file_id: str,
        file_name: str,
        content: bytes,
    ) -> dict[str, object]:
        storage_file_id = f"{session_id}:{file_id}"
        if self._object_storage_repository is not None:
            stored_file_path = self._store_object_file(
                namespace="etc_import",
                file_id=storage_file_id,
                file_name=file_name,
                content=content,
            )
        else:
            stored_file_path = self._store_local_file("etc_import", storage_file_id, file_name, content)
            self._save_file_object(
                file_id=f"etc_import:{storage_file_id}",
                file_name=file_name,
                stored_file_path=stored_file_path,
                content=content,
            )
        row = self._file_object_for_storage_uri(stored_file_path)
        if row is None or not row.get("id"):
            raise RuntimeError("ETC import archive file object registration failed.")
        return {
            "stored_file_path": stored_file_path,
            "file_object_id": str(row["id"]),
            "sha256": str(row.get("sha256") or ""),
            "size_bytes": int(row.get("size_bytes") or 0),
        }

    def read_etc_import_archive(self, stored_file_path: str) -> bytes:
        return self._read_file(stored_file_path)

    def delete_etc_import_archives(self, stored_file_paths: list[str]) -> int:
        deleted = 0
        for stored_file_path in stored_file_paths:
            try:
                if self._is_object_storage_ref(stored_file_path):
                    self._delete_object_file(stored_file_path)
                else:
                    Path(stored_file_path).unlink(missing_ok=True)
                deleted += 1
            except FileNotFoundError:
                continue
        return deleted

    def read_etc_reconciliation_file(self, stored_file_path: str) -> bytes:
        return self._read_file(stored_file_path)

    def store_etc_invoice_file(self, *, invoice_number: str, file_name: str, content: bytes) -> str:
        normalized_invoice_number = _sanitize_name(invoice_number)
        file_id = f"etc_invoice:{normalized_invoice_number}:{_sanitize_name(file_name)}"
        if self._object_storage_repository is not None:
            return self._store_object_file(namespace="etc_invoice", file_id=file_id, file_name=file_name, content=content)
        stored_file_path = self._store_local_file("etc_invoice", file_id, file_name, content)
        self._save_file_object(file_id=file_id, file_name=file_name, stored_file_path=stored_file_path, content=content)
        return stored_file_path

    def read_etc_invoice_file(self, stored_file_path: str) -> bytes:
        return self._read_file(stored_file_path)

    def etc_invoice_file_exists(self, stored_file_path: str) -> bool:
        if self._is_object_storage_ref(stored_file_path):
            try:
                self._read_object_file(stored_file_path)
            except Exception:
                return False
            return True
        if self._is_gridfs_ref(stored_file_path):
            return False
        return Path(stored_file_path).exists()

    def delete_etc_invoice_file(self, stored_file_path: str) -> None:
        if self._is_object_storage_ref(stored_file_path):
            self._delete_object_file(stored_file_path)
            return
        Path(stored_file_path).unlink(missing_ok=True)

    def save_historical_etc_repair_bundle(
        self,
        *,
        bundle_id: str,
        file_name: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_bundle_id = str(bundle_id or "").strip()
        if not normalized_bundle_id:
            raise ValueError("bundle_id is required.")
        if not content:
            raise ValueError("bundle content is required.")
        if self._object_storage_repository is not None:
            stored_file_path = self._store_object_file(
                namespace="historical_etc_repair",
                file_id=f"historical_etc_repair:{normalized_bundle_id}",
                file_name=file_name,
                content=content,
            )
            file_object_id = self._file_object_id_for_storage_uri(stored_file_path)
        else:
            stored_file_path = self._store_local_file("historical_etc_repair", normalized_bundle_id, file_name, content)
            file_object_id = self._save_file_object(
                file_id=f"historical_etc_repair:{normalized_bundle_id}",
                file_name=file_name,
                stored_file_path=stored_file_path,
                content=content,
            )
        payload = {
            "_id": normalized_bundle_id,
            "bundle_id": normalized_bundle_id,
            "file_name": file_name,
            "stored_file_path": stored_file_path,
            **self._serialize_value(metadata or {}),
            "size_bytes": len(content),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        self._ops_tax_etc_repository.save_historical_etc_repair_bundle_metadata(payload, file_object_id=file_object_id)
        return payload

    def load_historical_etc_repair_bundle_metadata(self) -> dict[str, dict[str, Any]]:
        return self._ops_tax_etc_repository.load_historical_etc_repair_bundle_metadata()

    def read_historical_etc_repair_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        bundle = self.load_historical_etc_repair_bundle_metadata().get(str(bundle_id or "").strip())
        if not bundle:
            return None
        path = str(bundle.get("stored_file_path") or "")
        if self._is_object_storage_ref(path):
            return {
                "bundle_id": str(bundle.get("bundle_id") or bundle_id),
                "file_name": str(bundle.get("file_name") or f"{bundle_id}.zip"),
                "content": self._read_file(path),
                "metadata": dict(bundle),
            }
        if path and Path(path).exists():
            return {
                "bundle_id": str(bundle.get("bundle_id") or bundle_id),
                "file_name": str(bundle.get("file_name") or f"{bundle_id}.zip"),
                "content": Path(path).read_bytes(),
                "metadata": dict(bundle),
            }
        return dict(bundle)

    def save_historical_etc_repair_parsed_seed(
        self,
        *,
        bundle_id: str,
        parsed_seed: dict[str, Any],
    ) -> dict[str, Any]:
        seed = self._ops_tax_etc_repository.save_historical_etc_repair_parsed_seed(
            bundle_id=bundle_id,
            parsed_seed=parsed_seed,
        )
        return seed

    def load_historical_etc_repair_parsed_seeds(self) -> dict[str, dict[str, Any]]:
        return self._ops_tax_etc_repository.load_historical_etc_repair_parsed_seeds()

    def load_historical_etc_repair_parsed_seed(self, bundle_id: str) -> dict[str, Any] | None:
        seed = self.load_historical_etc_repair_parsed_seeds().get(str(bundle_id or "").strip())
        return dict(seed) if isinstance(seed, dict) else None

    def load_historical_etc_repair_states(self) -> dict[str, dict[str, Any]]:
        return self._ops_tax_etc_repository.load_historical_etc_repair_states()

    def save_historical_etc_repair_states(self, states: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_historical_etc_repair_states(states)

    def load_background_jobs(self) -> dict[str, Any]:
        return self._ops_tax_etc_repository.load_background_jobs()

    def load_background_job(self, job_id: str) -> dict[str, Any] | None:
        return self._ops_tax_etc_repository.load_background_job(job_id)

    def save_background_job(self, job_payload: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_background_job(job_payload)

    def create_or_requeue_background_job(
        self,
        job_payload: dict[str, Any],
        *,
        reuse_any_status: bool = False,
    ) -> tuple[dict[str, Any] | None, bool]:
        return self._ops_tax_etc_repository.create_or_requeue_background_job(
            job_payload,
            reuse_any_status=reuse_any_status,
        )

    def load_app_health_alerts(self) -> dict[str, Any]:
        return self._ops_tax_etc_repository.load_app_health_alerts()

    def save_app_health_alerts(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_app_health_alerts(snapshot)

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        snapshot = self._workbench_relation_repository.load_workbench_pair_relations()
        if snapshot:
            pair_relations = snapshot.get("pair_relations") if isinstance(snapshot, dict) else None
            pair_history = snapshot.get("pair_relation_history") if isinstance(snapshot, dict) else None
            return normalize_workbench_pair_relations(
                pair_relations if pair_relations else None,
                pair_history if pair_history else None,
            )
        return {}

    def load_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        snapshot = self._workbench_relation_repository.load_workbench_pair_relations_for_row_ids(
            list(row_ids or []),
            case_ids=list(case_ids or []),
        )
        if snapshot:
            pair_relations = snapshot.get("pair_relations") if isinstance(snapshot, dict) else None
            pair_history = snapshot.get("pair_relation_history") if isinstance(snapshot, dict) else None
            return normalize_workbench_pair_relations(
                pair_relations if pair_relations else None,
                pair_history if pair_history else None,
            )
        return {}

    def load_active_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._workbench_relation_repository.load_active_workbench_pair_relations_for_row_ids(
            list(row_ids or []),
            case_ids=list(case_ids or []),
        )

    def load_active_workbench_pair_relations_for_typed_rows(
        self,
        row_ids: list[str],
        row_types: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._workbench_relation_repository.load_active_workbench_pair_relations_for_typed_rows(
            list(row_ids or []),
            list(row_types or []),
            case_ids=list(case_ids or []),
        )

    def save_workbench_pair_relations(self, snapshot: dict[str, Any], *, changed_case_ids: set[str] | None = None) -> None:
        self._workbench_relation_repository.save_workbench_pair_relations(snapshot, changed_case_ids=changed_case_ids)

    def load_no_oa_bank_batches(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_no_oa_bank_batches()
        if snapshot:
            batches = snapshot.get("batches") if isinstance(snapshot, dict) else None
            audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else None
            return normalize_no_oa_bank_batches(
                batches if batches else None,
                audit_log if audit_log else None,
            )
        return {}

    def load_bank_flow_rule_batches(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_bank_flow_rule_batches()
        if snapshot:
            batches = snapshot.get("batches") if isinstance(snapshot, dict) else None
            audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else None
            return normalize_no_oa_bank_batches(
                batches if batches else None,
                audit_log if audit_log else None,
            )
        return {}

    def save_no_oa_bank_batches(
        self,
        snapshot: dict[str, Any],
        *,
        relation_mode: str = "no_oa_bank_batch",
    ) -> None:
        self._workbench_repository.save_no_oa_bank_batches(snapshot, relation_mode=relation_mode)

    def save_bank_flow_rule_batch_items(
        self,
        snapshot: dict[str, Any],
        *,
        batch_ids: set[str] | list[str] | tuple[str, ...],
    ) -> None:
        self._workbench_repository.save_bank_flow_rule_batch_items(
            snapshot,
            batch_ids=batch_ids,
        )

    def save_no_oa_bank_batch_mutation(
        self,
        *,
        pair_relation_snapshot: dict[str, Any],
        no_oa_bank_batch_snapshot: dict[str, Any],
        changed_case_ids: set[str] | list[str] | tuple[str, ...],
        changed_scope_keys: set[str] | list[str] | tuple[str, ...],
    ) -> None:
        normalized_case_ids = {str(case_id).strip() for case_id in changed_case_ids if str(case_id).strip()}
        _ = changed_scope_keys

        def write(_connection: Any) -> None:
            if normalized_case_ids:
                self.save_workbench_pair_relations(
                    pair_relation_snapshot,
                    changed_case_ids=normalized_case_ids,
                )
            self.save_no_oa_bank_batches(no_oa_bank_batch_snapshot)

        run_in_transaction(self._connection, write)

    def save_bank_flow_rule_batch_mutation(
        self,
        *,
        pair_relation_snapshot: dict[str, Any],
        bank_flow_rule_batch_snapshot: dict[str, Any],
        changed_case_ids: set[str] | list[str] | tuple[str, ...],
        changed_scope_keys: set[str] | list[str] | tuple[str, ...],
        changed_batch_ids: set[str] | list[str] | tuple[str, ...] = (),
        candidate_guard: dict[str, object] | None = None,
    ) -> None:
        normalized_case_ids = {str(case_id).strip() for case_id in changed_case_ids if str(case_id).strip()}
        _ = changed_scope_keys
        normalized_batch_ids = {str(batch_id).strip() for batch_id in changed_batch_ids if str(batch_id).strip()}
        mutation_batch_ids = normalized_batch_ids | self._bank_flow_rule_batch_ids_from_mutation(
            pair_relation_snapshot=pair_relation_snapshot,
            bank_flow_rule_batch_snapshot=bank_flow_rule_batch_snapshot,
            changed_case_ids=normalized_case_ids,
        )

        def write(transaction: Any) -> None:
            transaction_repository = PostgresWorkbenchRepository(transaction)
            if isinstance(candidate_guard, dict):
                self._assert_bank_flow_rule_batch_candidate_guard(
                    transaction,
                    candidate_guard,
                )
            if normalized_case_ids:
                transaction_repository.save_workbench_pair_relations(
                    pair_relation_snapshot,
                    changed_case_ids=normalized_case_ids,
                )
            if mutation_batch_ids:
                transaction_repository.save_bank_flow_rule_batch_items(
                    bank_flow_rule_batch_snapshot,
                    batch_ids=mutation_batch_ids,
                )
            else:
                raise ValueError("bank-flow rule batch mutation requires an explicit changed batch id")

        run_in_transaction(self._connection, write)

    @staticmethod
    def _assert_bank_flow_rule_batch_candidate_guard(
        transaction: Any,
        candidate_guard: dict[str, object],
    ) -> None:
        transaction.execute("set transaction isolation level serializable")
        row_ids = [
            str(row_id).strip()
            for row_id in list(candidate_guard.get("row_ids") or [])
            if str(row_id).strip()
        ]
        transaction.fetch_all(
            """
            select id
            from app.bank_transactions
            where id::text = any(%s::text[])
               or legacy_mongo_id = any(%s::text[])
            order by id
            for update
            """,
            (row_ids, row_ids),
        )
        transaction.fetch_all(
            """
            select id
            from app.bank_transaction_category_confirmations
            where status = 'active'
              and (
                  bank_transaction_id::text = any(%s::text[])
                  or legacy_transaction_id = any(%s::text[])
              )
            order by id
            for share
            """,
            (row_ids, row_ids),
        )
        transaction.fetch_all(
            """
            select id
            from app.bank_transaction_categories
            where status = 'active'
              and (
                  bank_transaction_id::text = any(%s::text[])
                  or legacy_transaction_id = any(%s::text[])
              )
            order by id
            for share
            """,
            (row_ids, row_ids),
        )
        transaction.fetch_all(
            """
            select case_id
            from app.workbench_pair_relations
            where status = 'active'
              and row_ids && %s::text[]
            order by case_id
            for update
            """,
            (row_ids,),
        )
        transaction.fetch_all(
            """
            select settings_key
            from app.app_settings
            where settings_key = 'app_settings'
            for share
            """
        )
        source = BankFlowRuleBatchCanonicalQueryRepository.read_candidate_guard_source(
            transaction,
            scope_month=str(candidate_guard.get("scope_month") or ""),
        )
        categories_by_transaction_id = bank_flow_rule_batch_effective_categories(
            source
        )
        if candidate_guard.get("guard_mode") == "selected_rows":
            active_row_ids = {
                str(active_row_id).strip()
                for relation in list(source.get("active_relations") or [])
                if isinstance(relation, dict)
                for active_row_id in list(relation.get("row_ids") or [])
                if str(active_row_id).strip()
            }
            expected_proofs = [
                dict(proof)
                for proof in list(candidate_guard.get("selected_row_proofs") or [])
                if isinstance(proof, dict)
            ]
            actual_proofs = bank_flow_rule_batch_selected_row_proofs(
                [
                    dict(row)
                    for row in list(source.get("candidate_rows") or [])
                    if isinstance(row, dict)
                    and str(row.get("id") or row.get("transaction_id") or "").strip()
                    in row_ids
                ],
                categories_by_transaction_id,
            )
            expected_rule_proof = candidate_guard.get("rule_proof")
            expected_rule_proof = (
                dict(expected_rule_proof)
                if isinstance(expected_rule_proof, dict)
                else {}
            )
            actual_rule_proof = bank_flow_rule_batch_rule_proof(
                source.get("tag_policy")
                if isinstance(source.get("tag_policy"), dict)
                else {},
                str(candidate_guard.get("batch_type") or ""),
            )
            if (
                active_row_ids.intersection(row_ids)
                or actual_proofs != expected_proofs
                or actual_rule_proof != expected_rule_proof
                or actual_rule_proof.get("eligible") is not True
                or {proof.get("row_id") for proof in actual_proofs} != set(row_ids)
                or {proof.get("scope_month") for proof in actual_proofs}
                != {str(candidate_guard.get("scope_month") or "")}
                or {proof.get("category_code") for proof in actual_proofs}
                != {str(candidate_guard.get("batch_type") or "")}
            ):
                raise RuntimeError("bank_flow_rule_batch_candidate_guard_conflict")
            return
        live_service = build_live_bank_flow_rule_batch_service(source)
        try:
            candidate = live_service.get_batch(
                str(candidate_guard.get("batch_id") or "")
            )
        except KeyError as exc:
            raise RuntimeError(
                "bank_flow_rule_batch_candidate_guard_conflict"
            ) from exc
        actual_guard = bank_flow_rule_batch_candidate_guard(candidate)
        expected_guard = bank_flow_rule_batch_candidate_guard(candidate_guard)
        expected_rule_proof = candidate_guard.get("rule_proof")
        expected_rule_proof = (
            dict(expected_rule_proof)
            if isinstance(expected_rule_proof, dict)
            else {}
        )
        actual_rule_proof = bank_flow_rule_batch_rule_proof(
            source.get("tag_policy")
            if isinstance(source.get("tag_policy"), dict)
            else {},
            str(candidate_guard.get("batch_type") or ""),
        )
        if (
            actual_guard != expected_guard
            or actual_rule_proof != expected_rule_proof
            or actual_rule_proof.get("eligible") is not True
        ):
            raise RuntimeError("bank_flow_rule_batch_candidate_guard_conflict")

    @staticmethod
    def _bank_flow_rule_batch_ids_from_mutation(
        *,
        pair_relation_snapshot: dict[str, Any],
        bank_flow_rule_batch_snapshot: dict[str, Any],
        changed_case_ids: set[str],
    ) -> set[str]:
        if not changed_case_ids:
            return set()
        batch_ids = set(changed_case_ids)
        relations = pair_relation_snapshot.get("pair_relations") if isinstance(pair_relation_snapshot, dict) else None
        if isinstance(relations, dict):
            for case_id in changed_case_ids:
                relation = relations.get(case_id)
                metadata = relation.get("special_metadata") if isinstance(relation, dict) else None
                source_batch_id = metadata.get("source_batch_id") if isinstance(metadata, dict) else None
                normalized_source_batch_id = str(source_batch_id or "").strip()
                if normalized_source_batch_id:
                    batch_ids.add(normalized_source_batch_id)
        batches = bank_flow_rule_batch_snapshot.get("batches") if isinstance(bank_flow_rule_batch_snapshot, dict) else None
        if isinstance(batches, dict):
            for batch_id, payload in batches.items():
                normalized_batch_id = str(batch_id or "").strip()
                if not normalized_batch_id or not isinstance(payload, dict):
                    continue
                relation_case_id = str(payload.get("relation_case_id") or payload.get("batch_id") or "").strip()
                if relation_case_id in changed_case_ids:
                    batch_ids.add(normalized_batch_id)
        return {batch_id for batch_id in batch_ids if batch_id}

    def load_bank_transaction_categories(self) -> dict[str, Any]:
        return self._bank_transaction_category_repository.load_snapshot()

    def load_turnover_relations(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_turnover_relations()
        if snapshot:
            relations = snapshot.get("relations") if isinstance(snapshot, dict) else None
            audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else None
            return normalize_turnover_relations(
                relations if relations else None,
                audit_log if audit_log else None,
            )
        return {}

    def save_turnover_relations(self, snapshot: dict[str, Any]) -> None:
        self._workbench_repository.save_turnover_relations(snapshot)

    def load_turnover_relation_audit_log(self) -> list[Any]:
        snapshot = self.load_turnover_relations()
        audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else None
        return list(audit_log) if isinstance(audit_log, list) else []

    def save_turnover_relation_audit_log(self, snapshot: list[Any]) -> None:
        self._workbench_repository.save_turnover_relation_audit_log(
            snapshot,
            load_snapshot=self.load_turnover_relations,
            save_snapshot=self.save_turnover_relations,
        )

    def load_turnover_ledger_extras(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_turnover_ledger_extras()
        if snapshot:
            return snapshot
        return {"version": 1, "extras": []}

    def save_turnover_ledger_extras(self, snapshot: dict[str, Any]) -> None:
        self._workbench_repository.save_turnover_ledger_extras(snapshot)

    @property
    def import_fact_repository(self) -> PostgresCoreRepository:
        return self._core_repository

    @property
    def workbench_matching_queue_repository(self) -> PostgresWorkbenchMatchingQueueRepository:
        return self._workbench_matching_queue_repository

    @property
    def bank_transaction_category_repository(self) -> PostgresBankTransactionCategoryRepository:
        return self._bank_transaction_category_repository

    @property
    def workbench_relation_repository(self) -> PostgresWorkbenchRelationRepository:
        return self._workbench_relation_repository

    @property
    def bank_flow_rule_batch_canonical_query_repository(
        self,
    ) -> BankFlowRuleBatchCanonicalQueryRepository | None:
        return self._bank_flow_rule_batch_canonical_query_repository

    def list_invoices_page(self, **kwargs: Any) -> tuple[list[Any], int]:
        return self._core_repository.list_invoices_page(**kwargs)

    def list_bank_transactions_page(self, **kwargs: Any) -> tuple[list[Any], int]:
        return self._core_repository.list_bank_transactions_page(**kwargs)

    def list_bank_transactions_by_ids(self, transaction_ids: list[str]) -> list[Any]:
        return self._core_repository.list_bank_transactions_by_ids(transaction_ids)

    def list_bank_transactions_auto_category_context(self, **kwargs: Any) -> list[Any]:
        return self._core_repository.list_bank_transactions_auto_category_context(**kwargs)

    def list_bank_transaction_accounts(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._core_repository.list_bank_transaction_accounts(**kwargs)

    def list_import_batches_page(self, **kwargs: Any) -> tuple[list[Any], int]:
        return self._core_repository.list_import_batches_page(**kwargs)

    def list_import_files_page(self, **kwargs: Any) -> tuple[list[Any], int]:
        return self._core_repository.list_import_files_page(**kwargs)

    def list_submitted_etc_invoices(self) -> list[Any]:
        return self._core_repository.list_submitted_etc_invoices()

    def save_invoices(self, invoices: list[Any]) -> None:
        self._core_repository.save_invoices(invoices)

    def save_invoice_etc_metadata(self, invoices: list[Any]) -> None:
        self._core_repository.save_invoice_etc_metadata(invoices)

    def load(self) -> dict[str, Any]:
        return self._load_snapshot_payload(include_import_facts=True)

    def reset_bank_transaction_data(
        self,
        *,
        source_snapshot: dict[str, Any] | None = None,
        reset_context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del source_snapshot
        context = dict(reset_context or {})
        with self._connection.transaction() as transaction:
            return PostgresSettingsDataResetRepository(
                transaction
            ).reset_bank_transaction_data(
                expected_impact_fingerprint=context.get("impact_fingerprint", ""),
                recovery_receipt_id=context.get("recovery_receipt_id", ""),
                job_id=context.get("job_id", ""),
                actor_id=context.get("actor_id", ""),
                reason=context.get("reason", ""),
            )

    def reset_invoice_data(
        self,
        *,
        source_snapshot: dict[str, Any] | None = None,
        reset_context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del source_snapshot
        context = dict(reset_context or {})
        with self._connection.transaction() as transaction:
            return PostgresSettingsDataResetRepository(transaction).reset_invoice_data(
                expected_impact_fingerprint=context.get("impact_fingerprint", ""),
                recovery_receipt_id=context.get("recovery_receipt_id", ""),
                job_id=context.get("job_id", ""),
                actor_id=context.get("actor_id", ""),
                reason=context.get("reason", ""),
            )

    def reset_oa_workbench_data(
        self,
        *,
        row_ids: list[str],
        case_ids: list[str],
        source_snapshot: dict[str, Any] | None = None,
        reset_context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del source_snapshot
        context = dict(reset_context or {})
        with self._connection.transaction() as transaction:
            return PostgresSettingsDataResetRepository(
                transaction
            ).reset_oa_workbench_data(
                row_ids=row_ids,
                case_ids=case_ids,
                expected_impact_fingerprint=context.get("impact_fingerprint", ""),
                recovery_receipt_id=context.get("recovery_receipt_id", ""),
                job_id=context.get("job_id", ""),
                actor_id=context.get("actor_id", ""),
                reason=context.get("reason", ""),
            )

    def preview_settings_data_reset(
        self,
        action: str,
        *,
        row_ids: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return PostgresSettingsDataResetRepository(self._connection).preview(
            action,
            row_ids=row_ids,
            case_ids=case_ids,
        )

    def load_imports_snapshot(self) -> dict[str, Any]:
        return self._load_imports()

    def load_file_imports_snapshot(self) -> dict[str, Any]:
        return self._load_file_imports()

    def load_matching_snapshot(self) -> dict[str, Any]:
        return self._load_matching()

    def _load_snapshot_payload(self, *, include_import_facts: bool) -> dict[str, Any]:
        snapshot = {
            "imports": self._load_imports() if include_import_facts else {},
            "file_imports": self._load_file_imports() if include_import_facts else {},
            "matching": self._load_matching(),
            "bank_transaction_categories": self.load_bank_transaction_categories(),
            "workbench_overrides": self.load_workbench_overrides(),
            "workbench_exception_cases": self.load_workbench_exception_cases(),
            "workbench_pair_relations": self.load_workbench_pair_relations(),
            "no_oa_bank_batches": self.load_no_oa_bank_batches(),
            "turnover_relations": self.load_turnover_relations(),
            "turnover_ledger_extras": self.load_turnover_ledger_extras(),
            "app_health_alerts": self.load_app_health_alerts(),
            "pending_invoice_commands": self.load_pending_invoice_commands(),
        }
        return snapshot

    def save(self, payload: dict[str, Any]) -> None:
        normalized = self._serialize_value(payload)
        if not isinstance(normalized, dict):
            raise ValueError("state payload must be a dictionary.")
        if "imports" in normalized:
            self._core_repository.save_imports(normalized.get("imports") or {})
        if "file_imports" in normalized:
            self._core_repository.save_file_imports(normalized.get("file_imports") or {})
        if "workbench_overrides" in normalized:
            self.save_workbench_overrides(normalized.get("workbench_overrides") or {})
        if "workbench_exception_cases" in normalized:
            self.save_workbench_exception_cases(normalized.get("workbench_exception_cases") or {})
        if "workbench_pair_relations" in normalized:
            self.save_workbench_pair_relations(normalized.get("workbench_pair_relations") or {})
        if "no_oa_bank_batches" in normalized:
            self.save_no_oa_bank_batches(normalized.get("no_oa_bank_batches") or {})
        if "turnover_relations" in normalized:
            self.save_turnover_relations(normalized.get("turnover_relations") or {})
        if "turnover_ledger_extras" in normalized:
            self.save_turnover_ledger_extras(normalized.get("turnover_ledger_extras") or {})
        if "app_health_alerts" in normalized:
            self.save_app_health_alerts(normalized.get("app_health_alerts") or {})
        if "pending_invoice_commands" in normalized:
            self.save_pending_invoice_commands(normalized.get("pending_invoice_commands") or {})

    def save_import_delta(self, payload: dict[str, Any]) -> None:
        normalized = self._serialize_value(payload)
        if not isinstance(normalized, dict) or not normalized or set(normalized) - {"imports", "file_imports"}:
            raise ValueError("Import delta requires only imports and file_imports payloads.")
        self._core_repository.save_import_delta(
            normalized.get("imports") or {},
            normalized.get("file_imports") or {},
        )

    def save_workbench_overrides(self, workbench_overrides_snapshot: dict[str, Any], *, changed_row_ids: set[str] | None = None) -> None:
        self._workbench_repository.save_workbench_overrides(workbench_overrides_snapshot, changed_row_ids=changed_row_ids)

    def load_workbench_overrides(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_workbench_overrides()
        if snapshot:
            return snapshot
        return {}

    def load_workbench_exception_cases(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_workbench_exception_cases()
        if snapshot:
            return snapshot
        return {}

    def save_workbench_exception_cases(self, snapshot: dict[str, Any]) -> None:
        self._workbench_repository.save_workbench_exception_cases(snapshot)

    def store_import_file(
        self,
        *,
        session_id: str,
        file_id: str,
        file_name: str,
        content: bytes,
        imported_by: str | None = None,
    ) -> str:
        normalized_imported_by = str(imported_by or "").strip() or None
        if self._object_storage_repository is not None:
            stored_file_path = self._store_object_file(namespace="imports", file_id=file_id, file_name=file_name, content=content)
            file_object_id = self._file_object_id_for_storage_uri(stored_file_path)
        else:
            stored_file_path = self._store_local_file("imports", file_id, file_name, content)
            file_object_id = self._save_file_object(file_id=file_id, file_name=file_name, stored_file_path=stored_file_path, content=content)
        self._connection.execute(
            """
            insert into app.import_files(
                legacy_mongo_id, session_id, stored_file_path, original_filename,
                status, file_object_id, uploaded_by, raw_payload
            )
            values (%s, %s, %s, %s, 'stored', %s::uuid, %s, %s)
            on conflict (legacy_mongo_id) do update set
                session_id = excluded.session_id,
                stored_file_path = excluded.stored_file_path,
                original_filename = excluded.original_filename,
                status = excluded.status,
                file_object_id = excluded.file_object_id,
                uploaded_by = excluded.uploaded_by,
                raw_payload = excluded.raw_payload
            """,
            (
                file_id,
                session_id,
                stored_file_path,
                file_name,
                file_object_id,
                normalized_imported_by,
                _jsonb({
                    "normalized_payload": {
                        "id": file_id,
                        "file_name": file_name,
                        "stored_file_path": stored_file_path,
                        "session_id": session_id,
                        "imported_by": normalized_imported_by,
                    }
                }),
            ),
        )
        return stored_file_path

    def read_import_file(self, stored_file_path: str) -> bytes:
        return self._read_file(stored_file_path)

    def find_confirmed_import_file_by_sha256(
        self,
        *,
        content_sha256: str,
        exclude_file_id: str,
    ) -> dict[str, Any] | None:
        return self._connection.fetch_one(
            """
            select import_files.original_filename as file_name, import_files.uploaded_at
            from app.import_files import_files
            join app.file_objects file_objects on file_objects.id = import_files.file_object_id
            where file_objects.sha256 = %s
              and import_files.status = 'confirmed'
              and coalesce(import_files.legacy_mongo_id, import_files.id::text) <> %s
            order by import_files.uploaded_at desc
            limit 1
            """,
            (content_sha256, exclude_file_id),
        )

    def delete_import_files(self, stored_file_paths: list[str]) -> int:
        deleted = 0
        seen: set[str] = set()
        for path in stored_file_paths:
            normalized = str(path or "")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            if self._is_gridfs_ref(normalized):
                if self._object_storage_repository is not None:
                    raise RuntimeError("Legacy GridFS delete is disabled when object storage is enabled.")
                row_count = self._connection.execute(
                    "update app.import_files set status = 'deleted' where stored_file_path = %s",
                    (normalized,),
                )
                deleted += max(row_count, 1)
                continue
            if self._is_object_storage_ref(normalized):
                self._delete_object_file(normalized)
                row_count = self._connection.execute(
                    "update app.import_files set status = 'deleted' where stored_file_path = %s",
                    (normalized,),
                )
                deleted += max(row_count, 1)
                continue
            file_path = Path(normalized)
            if file_path.exists():
                file_path.unlink()
            row_count = self._connection.execute(
                "update app.import_files set status = 'deleted' where stored_file_path = %s",
                (normalized,),
            )
            deleted += max(row_count, 1)
        return deleted

    def import_session_exists(self, session_id: str) -> bool:
        row = self._connection.fetch_one(
            "select 1 from app.import_files where session_id = %s and status <> 'deleted' limit 1",
            (session_id,),
        )
        return row is not None

    def import_file_exists(self, file_id: str) -> bool:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            return False
        row = self._connection.fetch_one(
            """
            select 1
            from app.import_files import_files
            left join app.file_objects file_objects on file_objects.id = import_files.file_object_id
            where import_files.status <> 'deleted'
              and (
                   import_files.legacy_mongo_id = %s
                or import_files.id::text = %s
                or file_objects.legacy_mongo_id = %s
                or file_objects.legacy_gridfs_id = %s
                or file_objects.object_key = %s
              )
            limit 1
            """,
            (normalized_file_id, normalized_file_id, normalized_file_id, normalized_file_id, normalized_file_id),
        )
        return row is not None

    def import_batch_exists(self, batch_id: str) -> bool:
        row = self._connection.fetch_one(
            "select 1 from app.import_batches where legacy_mongo_id = %s or id::text = %s limit 1",
            (batch_id, batch_id),
        )
        return row is not None

    def invoice_exists(self, invoice_id: str) -> bool:
        row = self._connection.fetch_one(
            "select 1 from app.invoices where legacy_mongo_id = %s or id::text = %s limit 1",
            (invoice_id, invoice_id),
        )
        return row is not None

    def transaction_exists(self, transaction_id: str) -> bool:
        row = self._connection.fetch_one(
            "select 1 from app.bank_transactions where legacy_mongo_id = %s or id::text = %s limit 1",
            (transaction_id, transaction_id),
        )
        return row is not None

    def _load_settings(self, settings_key: str) -> dict[str, Any]:
        return self._ops_tax_etc_repository.load_settings(settings_key)

    def _save_settings(self, settings_key: str, payload: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_settings(settings_key, payload)

    def _load_imports(self) -> dict[str, Any]:
        snapshot = self._core_repository.load_imports()
        if snapshot:
            return snapshot
        return {}

    def _load_file_imports(self) -> dict[str, Any]:
        snapshot = self._core_repository.load_file_imports()
        if snapshot:
            return snapshot
        return {}

    def _load_matching(self) -> dict[str, Any]:
        runs = self._load_keyed_rows("select run_id as key, raw_payload from app.matching_runs order by executed_at, run_id")
        results = self._load_keyed_rows("select coalesce(legacy_mongo_id, id::text) as key, raw_payload from app.matching_results order by created_at, key")
        if not runs and not results:
            return {}
        return {"runs": runs, "results": results}

    def _load_keyed_rows(self, sql: str) -> dict[str, Any]:
        rows = self._connection.fetch_all(sql)
        return {str(row.get("key")): self._row_payload(row, "payload", "raw_payload") for row in rows}

    @staticmethod
    def _row_payload(row: dict[str, Any] | None, *columns: str) -> Any:
        if not row:
            return None
        for column in columns:
            value = row.get(column)
            if value is None:
                continue
            if isinstance(value, dict) and "normalized_payload" in value:
                return value.get("normalized_payload") or {}
            return value
        raw_payload = row.get("raw_payload")
        if isinstance(raw_payload, dict):
            return raw_payload.get("normalized_payload") or raw_payload
        return None

    def _save_file_object(self, *, file_id: str, file_name: str, stored_file_path: str, content: bytes) -> str | None:
        row = self._connection.fetch_one(
            """
            insert into app.file_objects(legacy_mongo_id, storage_backend, storage_uri, filename, sha256, size_bytes, raw_payload)
            values (%s, 'local_filesystem', %s, %s, %s, %s, %s)
            on conflict (legacy_mongo_id) do update set
                storage_backend = excluded.storage_backend,
                storage_uri = excluded.storage_uri,
                filename = excluded.filename,
                sha256 = excluded.sha256,
                size_bytes = excluded.size_bytes,
                raw_payload = excluded.raw_payload
            returning id::text as id
            """,
            (
                file_id,
                stored_file_path,
                file_name,
                hashlib.sha256(content).hexdigest(),
                len(content),
                _jsonb({"normalized_payload": {"id": file_id, "file_name": file_name, "stored_file_path": stored_file_path}}),
            ),
        )
        file_object_id = row.get("id") if row else None
        if isinstance(file_object_id, bytes):
            file_object_id = file_object_id.decode()
        return str(file_object_id) if file_object_id else None

    def _store_object_file(
        self,
        *,
        namespace: str,
        file_id: str,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
        legacy_gridfs_id: str | None = None,
    ) -> str:
        if self._object_storage_repository is None or not self._object_storage_backend or not self._object_storage_bucket:
            raise ObjectStorageWriteError("Object storage repository is not configured for PostgreSQL file writes.")
        content_bytes = bytes(content or b"")
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        temporary_object_key = (
            f"tmp/{_sanitize_name(namespace)}/"
            f"{_sanitize_name(file_id)}/{sha256}/"
            f"{_sanitize_name(file_name)}"
        )
        pending_uri = f"{self._object_storage_backend}://{self._object_storage_bucket}/{temporary_object_key}"
        row = self._upsert_file_object(
            file_id=file_id,
            legacy_gridfs_id=legacy_gridfs_id,
            storage_backend=self._object_storage_backend,
            storage_uri=pending_uri,
            bucket_name=self._object_storage_bucket,
            object_key=temporary_object_key,
            file_name=file_name,
            sha256=sha256,
            size_bytes=len(content_bytes),
            content_type=content_type,
            etag=None,
            migration_status="pending_upload",
            temporary_object_key=temporary_object_key,
            source_storage_backend=None,
            source_storage_uri=None,
            last_error=None,
            raw_payload={
                "normalized_payload": {
                    "id": file_id,
                    "file_name": file_name,
                    "stored_file_path": pending_uri,
                    "sha256": sha256,
                    "size_bytes": len(content_bytes),
                    "migration_status": "pending_upload",
                }
            },
        )
        file_object_id = str(row.get("id") or "") if row else ""
        try:
            result = write_verified_object(
                object_storage_repository=self._object_storage_repository,
                storage_backend=self._object_storage_backend,
                bucket_name=self._object_storage_bucket,
                namespace=namespace,
                file_id=file_id,
                file_name=file_name,
                content=content_bytes,
                content_type=content_type,
            )
        except ObjectStorageWriteError as exc:
            self._mark_file_object_failed(file_object_id, str(exc))
            raise
        except Exception as exc:
            self._mark_file_object_failed(file_object_id, str(exc) or exc.__class__.__name__)
            raise ObjectStorageWriteError(str(exc) or exc.__class__.__name__) from exc

        self._mark_file_object_verified(
            file_object_id,
            storage_backend=result.storage_backend,
            storage_uri=result.storage_uri,
            bucket_name=result.bucket_name,
            object_key=result.object_key,
            etag=result.etag,
            raw_payload={
                "normalized_payload": {
                    "id": file_id,
                    "file_name": file_name,
                    "stored_file_path": result.storage_uri,
                    "sha256": result.sha256,
                    "size_bytes": result.size_bytes,
                    "migration_status": "verified",
                }
            },
        )
        return result.storage_uri

    def _upsert_file_object(
        self,
        *,
        file_id: str,
        legacy_gridfs_id: str | None,
        storage_backend: str,
        storage_uri: str,
        bucket_name: str | None,
        object_key: str | None,
        file_name: str,
        sha256: str,
        size_bytes: int,
        content_type: str | None,
        etag: str | None,
        migration_status: str,
        temporary_object_key: str | None,
        source_storage_backend: str | None,
        source_storage_uri: str | None,
        last_error: str | None,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self._connection.fetch_one(
            """
            insert into app.file_objects(
                legacy_mongo_id, legacy_gridfs_id, storage_backend, storage_uri,
                bucket_name, object_key, filename, sha256, size_bytes, content_type,
                etag, migration_status, temporary_object_key, source_storage_backend,
                source_storage_uri, last_error, uploaded_at, raw_payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
            on conflict (legacy_mongo_id) do update set
                legacy_gridfs_id = excluded.legacy_gridfs_id,
                storage_backend = excluded.storage_backend,
                storage_uri = excluded.storage_uri,
                bucket_name = excluded.bucket_name,
                object_key = excluded.object_key,
                filename = excluded.filename,
                sha256 = excluded.sha256,
                size_bytes = excluded.size_bytes,
                content_type = excluded.content_type,
                etag = excluded.etag,
                migration_status = excluded.migration_status,
                temporary_object_key = excluded.temporary_object_key,
                source_storage_backend = excluded.source_storage_backend,
                source_storage_uri = excluded.source_storage_uri,
                last_error = excluded.last_error,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            returning id::text as id
            """,
            (
                file_id,
                legacy_gridfs_id,
                storage_backend,
                storage_uri,
                bucket_name,
                object_key,
                file_name,
                sha256,
                size_bytes,
                content_type,
                etag,
                migration_status,
                temporary_object_key,
                source_storage_backend,
                source_storage_uri,
                last_error,
                _jsonb(raw_payload),
            ),
        )

    def _mark_file_object_verified(
        self,
        file_object_id: str,
        *,
        storage_backend: str,
        storage_uri: str,
        bucket_name: str,
        object_key: str,
        etag: str | None,
        raw_payload: dict[str, Any],
    ) -> None:
        if not file_object_id:
            return
        self._connection.execute(
            """
            update app.file_objects
            set storage_backend = %s,
                storage_uri = %s,
                bucket_name = %s,
                object_key = %s,
                etag = %s,
                migration_status = 'verified',
                temporary_object_key = null,
                verified_at = now(),
                last_error = null,
                raw_payload = %s,
                updated_at = now()
            where id = %s::uuid
            """,
            (storage_backend, storage_uri, bucket_name, object_key, etag, _jsonb(raw_payload), file_object_id),
        )

    def _mark_file_object_failed(self, file_object_id: str, error: str) -> None:
        if not file_object_id:
            return
        self._connection.execute(
            """
            update app.file_objects
            set migration_status = 'failed',
                last_error = %s,
                failed_at = now(),
                updated_at = now()
            where id = %s::uuid
            """,
            (error[:1000], file_object_id),
        )

    def _file_object_id_for_storage_uri(self, stored_file_path: str) -> str | None:
        row = self._file_object_for_storage_uri(stored_file_path)
        value = row.get("id") if row else None
        return str(value) if value else None

    def _file_object_for_storage_uri(self, stored_file_path: str) -> dict[str, Any] | None:
        return self._connection.fetch_one(
            """
            select id::text as id, storage_backend, storage_uri, bucket_name, object_key,
                   sha256, size_bytes, migration_status
            from app.file_objects
            where storage_uri = %s
            limit 1
            """,
            (stored_file_path,),
        )

    def _store_local_file(self, namespace: str, file_id: str, file_name: str, content: bytes) -> str:
        safe_name = _sanitize_name(file_name)
        target_dir = self._file_root / _sanitize_name(namespace) / _sanitize_name(file_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_name
        target_path.write_bytes(content)
        return str(target_path)

    def _read_file(self, stored_file_path: str) -> bytes:
        if self._is_object_storage_ref(stored_file_path):
            return self._read_object_file(stored_file_path)
        if self._is_gridfs_ref(stored_file_path):
            raise RuntimeError("Legacy GridFS file access is disabled for PostgreSQL state store.")
        path = Path(str(stored_file_path or ""))
        if not path.exists():
            raise FileNotFoundError(stored_file_path)
        return path.read_bytes()

    def _read_object_file(self, stored_file_path: str) -> bytes:
        if self._object_storage_repository is None or not self._object_storage_bucket:
            raise RuntimeError("Object storage is not configured for PostgreSQL file access.")
        row = self._file_object_for_storage_uri(stored_file_path)
        if not row or str(row.get("migration_status") or "") != "verified":
            raise RuntimeError("Only verified object storage file records can be read from production paths.")
        object_key = str(row.get("object_key") or "") or verified_object_key_from_uri(stored_file_path, expected_bucket=self._object_storage_bucket)
        try:
            content = self._object_storage_repository.get_object(object_key)
        except Exception as exc:
            raise ObjectStorageReadError(str(exc) or exc.__class__.__name__) from exc
        expected_size = row.get("size_bytes")
        if expected_size not in (None, "") and int(expected_size) != len(content):
            raise ObjectStorageReadError("Object storage file size mismatch.")
        expected_sha256 = str(row.get("sha256") or "").strip()
        if expected_sha256 and hashlib.sha256(content).hexdigest() != expected_sha256:
            raise ObjectStorageReadError("Object storage file checksum mismatch.")
        return bytes(content)

    def _delete_object_file(self, stored_file_path: str) -> None:
        if self._object_storage_repository is None:
            raise RuntimeError("Object storage is not configured for PostgreSQL file delete.")
        row = self._file_object_for_storage_uri(stored_file_path)
        object_key = str(row.get("object_key") or "") if row else verified_object_key_from_uri(stored_file_path, expected_bucket=self._object_storage_bucket)
        self._object_storage_repository.delete_object(object_key)
        self._connection.execute(
            """
            update app.file_objects
            set migration_status = 'tombstoned',
                tombstoned_at = now(),
                updated_at = now()
            where storage_uri = %s
            """,
            (stored_file_path,),
        )

    @staticmethod
    def _is_gridfs_ref(value: str) -> bool:
        return str(value or "").startswith(GRIDFS_REF_PREFIX)

    @staticmethod
    def _is_object_storage_ref(value: str) -> bool:
        return str(value or "").startswith(("s3://", "minio://"))

    def _serialize_value(self, value: Any) -> Any:
        if is_dataclass(value):
            return {key: self._serialize_value(getattr(value, key, None)) for key in value.__dataclass_fields__}  # type: ignore[attr-defined]
        if isinstance(value, dict):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, bytes):
            return {"sha256": hashlib.sha256(value).hexdigest(), "size_bytes": len(value)}
        return value
