from __future__ import annotations

from dataclasses import is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fin_ops_platform.services.postgres_repositories import (
    PostgresCoreRepository,
    PostgresOpsTaxEtcRepository,
    PostgresReadModelRepository,
    PostgresWorkbenchRepository,
)
from fin_ops_platform.services.postgres_snapshot_contracts import (
    normalize_bank_transaction_categories,
    normalize_no_oa_bank_batches,
    normalize_turnover_relations,
    normalize_workbench_pair_relations,
)
from fin_ops_platform.services.state_store import ApplicationStateStore, GRIDFS_BUCKET_NAME, GRIDFS_REF_PREFIX, load_mongo_state_settings


APP_SETTINGS_KEY = "app_settings"
STATE_KEY_PREFIX = "state:"


def _default_app_settings_payload() -> dict[str, Any]:
    return {
        "completed_project_ids": [],
        "manual_projects": [],
        "synced_projects": [],
        "bank_account_mappings": [],
        "allowed_usernames": [],
        "readonly_export_usernames": [],
        "admin_usernames": [],
        "workbench_column_layouts": {},
        "oa_retention": {},
        "oa_import": {},
        "oa_invoice_offset": {},
        "bank_transaction_tags": {},
        "pending_invoice_tag_groups": {},
    }


def _jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value)


class LegacyGridFSFileReader:
    def __init__(self, *, mongo_uri: str, database: str) -> None:
        self._mongo_uri = mongo_uri
        self._database = database
        self._client: Any | None = None

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> LegacyGridFSFileReader | None:
        settings = load_mongo_state_settings(data_dir)
        if settings is None:
            return None
        return cls(mongo_uri=settings.mongo_uri, database=settings.database)

    def read(self, stored_file_path: str) -> bytes:
        bucket_name, object_id = self._parse_gridfs_uri(stored_file_path)
        bucket = self._bucket(bucket_name)
        stream = bucket.open_download_stream(object_id)
        return bytes(stream.read())

    def _bucket(self, bucket_name: str) -> Any:
        if self._client is None:
            from gridfs import GridFSBucket
            from pymongo import MongoClient

            self._client = MongoClient(self._mongo_uri)
            self._gridfs_bucket_class = GridFSBucket
        database = self._client[self._database]
        return self._gridfs_bucket_class(database, bucket_name=bucket_name)

    @staticmethod
    def _parse_gridfs_uri(stored_file_path: str) -> tuple[str, str]:
        raw = str(stored_file_path or "")[len(GRIDFS_REF_PREFIX) :]
        first, separator, rest = raw.partition("/")
        if not first:
            raise ValueError("Invalid GridFS stored file reference.")
        if separator and first == GRIDFS_BUCKET_NAME and rest:
            return first, rest
        return GRIDFS_BUCKET_NAME, first


class PostgresStateStore:
    def __init__(self, *, data_dir: Path, connection: Any, legacy_file_reader: Any | None = None) -> None:
        self._data_dir = Path(data_dir)
        self._connection = connection
        self._legacy_file_reader = legacy_file_reader or LegacyGridFSFileReader.from_data_dir(self._data_dir)
        self._core_repository = PostgresCoreRepository(connection)
        self._ops_tax_etc_repository = PostgresOpsTaxEtcRepository(connection)
        self._read_model_repository = PostgresReadModelRepository(connection)
        self._workbench_repository = PostgresWorkbenchRepository(connection)
        self._file_root = self._data_dir / "postgres_files"
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

    def health_summary(self) -> dict[str, object]:
        if hasattr(self._connection, "health_summary"):
            return dict(self._connection.health_summary())
        return {"postgres_status": "unknown"}

    def load_app_settings(self) -> dict[str, Any]:
        payload = self._load_settings(APP_SETTINGS_KEY)
        if not payload:
            return _default_app_settings_payload()
        return {**_default_app_settings_payload(), **payload}

    def save_app_settings(self, payload: dict[str, Any]) -> None:
        self._save_settings(APP_SETTINGS_KEY, payload)

    def load_pending_invoice_commands(self) -> dict[str, Any]:
        snapshot = self._ops_tax_etc_repository.load_pending_invoice_commands()
        if snapshot:
            return snapshot
        return self._load_snapshot_or_empty("pending_invoice_commands")

    def save_pending_invoice_commands(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_pending_invoice_commands(snapshot)
        self._save_snapshot("pending_invoice_commands", snapshot)

    def load_oa_attachment_invoice_cache_entry(self, cache_key: str) -> dict[str, object] | None:
        return self._ops_tax_etc_repository.load_oa_attachment_invoice_cache_entry(cache_key)

    def save_oa_attachment_invoice_cache_entry(self, cache_key: str, payload: dict[str, object]) -> None:
        self._ops_tax_etc_repository.save_oa_attachment_invoice_cache_entry(cache_key, payload)

    def clear_oa_attachment_invoice_cache(self) -> int:
        return self._ops_tax_etc_repository.clear_oa_attachment_invoice_cache()

    def load_oa_sync_state(self) -> dict[str, Any]:
        snapshot = self._load_snapshot("oa_sync_state")
        if snapshot:
            return snapshot
        return self._ops_tax_etc_repository.load_oa_sync_state()

    def save_oa_sync_state(self, snapshot: dict[str, Any]) -> None:
        self._save_snapshot("oa_sync_state", snapshot)

    def load_manual_oa_imports(self) -> dict[str, object]:
        snapshot = self._load_snapshot("manual_oa_imports")
        if snapshot:
            return ApplicationStateStore._normalize_manual_oa_imports(snapshot)  # noqa: SLF001
        payload = self._ops_tax_etc_repository.load_manual_oa_imports()
        return ApplicationStateStore._normalize_manual_oa_imports(payload)  # noqa: SLF001

    def save_manual_oa_imports(self, payload: dict[str, object]) -> None:
        normalized = ApplicationStateStore._normalize_manual_oa_imports(payload)  # noqa: SLF001
        self._save_snapshot("manual_oa_imports", normalized)

    def add_manual_oa_imports(
        self,
        row_ids: list[str],
        *,
        actor_id: str | None = None,
        audit: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload = ApplicationStateStore._normalize_manual_oa_imports(self.load_manual_oa_imports())  # noqa: SLF001
        entries = dict(payload.get("entries") if isinstance(payload.get("entries"), dict) else {})
        imported: list[str] = []
        already_imported: list[str] = []
        for row_id in ApplicationStateStore._dedupe_text_values(row_ids):  # noqa: SLF001
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
        payload = ApplicationStateStore._normalize_manual_oa_imports(self.load_manual_oa_imports())  # noqa: SLF001
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
        return self._load_snapshot_or_empty("tax_certified_imports")

    def save_tax_certified_imports(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_tax_certified_imports(snapshot)
        self._save_snapshot("tax_certified_imports", snapshot)

    def load_etc_state(self) -> dict[str, Any]:
        snapshot = self._ops_tax_etc_repository.load_etc_state()
        if snapshot:
            fallback = self._load_snapshot("etc_state") or {}
            if fallback:
                for key in (
                    "invoice_counter",
                    "batch_counter",
                    "import_batch_counter",
                    "business_batch_counter",
                    "batch_day_counters",
                    "invoice_numbers",
                ):
                    if key in fallback:
                        snapshot[key] = fallback[key]
            return snapshot
        return self._load_snapshot_or_empty("etc_state")

    def save_etc_state(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_etc_state(snapshot)
        self._save_snapshot("etc_state", snapshot)

    def load_etc_reconciliation_state(self) -> dict[str, Any]:
        snapshot = self._ops_tax_etc_repository.load_etc_reconciliation_state()
        if snapshot:
            fallback = self._load_snapshot("etc_reconciliation_state") or {}
            if fallback:
                for key in ("schema_version", "task_counter", "file_counter", "audit_counter"):
                    if key in fallback:
                        snapshot[key] = fallback[key]
            return snapshot
        return self._load_snapshot_or_empty("etc_reconciliation_state")

    def save_etc_reconciliation_state(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_etc_reconciliation_state(snapshot)
        self._save_snapshot("etc_reconciliation_state", snapshot)

    def store_etc_reconciliation_file(self, *, task_id: str, file_id: str, file_name: str, content: bytes) -> str:
        stored_file_path = self._store_local_file("etc_reconciliation", file_id, file_name, content)
        self._save_file_object(file_id=file_id, file_name=file_name, stored_file_path=stored_file_path, content=content)
        return stored_file_path

    def read_etc_reconciliation_file(self, stored_file_path: str) -> bytes:
        return self._read_file(stored_file_path)

    def store_etc_invoice_file(self, *, invoice_number: str, file_name: str, content: bytes) -> str:
        normalized_invoice_number = ApplicationStateStore._sanitize_name(invoice_number)  # noqa: SLF001
        file_id = f"etc_invoice:{normalized_invoice_number}:{ApplicationStateStore._sanitize_name(file_name)}"  # noqa: SLF001
        stored_file_path = self._store_local_file("etc_invoice", file_id, file_name, content)
        self._save_file_object(file_id=file_id, file_name=file_name, stored_file_path=stored_file_path, content=content)
        return stored_file_path

    def read_etc_invoice_file(self, stored_file_path: str) -> bytes:
        return self._read_file(stored_file_path)

    def etc_invoice_file_exists(self, stored_file_path: str) -> bool:
        if self._is_gridfs_ref(stored_file_path):
            return self._legacy_file_reader is not None
        return Path(stored_file_path).exists()

    def delete_etc_invoice_file(self, stored_file_path: str) -> None:
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
        stored_file_path = self._store_local_file("historical_etc_repair", normalized_bundle_id, file_name, content)
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
        file_object_id = self._save_file_object(
            file_id=f"historical_etc_repair:{normalized_bundle_id}",
            file_name=file_name,
            stored_file_path=stored_file_path,
            content=content,
        )
        self._ops_tax_etc_repository.save_historical_etc_repair_bundle_metadata(payload, file_object_id=file_object_id)
        bundles = self.load_historical_etc_repair_bundle_metadata()
        bundles[normalized_bundle_id] = payload
        self._save_snapshot("historical_etc_repair_bundles", bundles)
        return payload

    def load_historical_etc_repair_bundle_metadata(self) -> dict[str, dict[str, Any]]:
        rows = self._ops_tax_etc_repository.load_historical_etc_repair_bundle_metadata()
        if rows:
            return rows
        payload = self._load_snapshot("historical_etc_repair_bundles")
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)} if isinstance(payload, dict) else {}

    def read_historical_etc_repair_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        bundle = self.load_historical_etc_repair_bundle_metadata().get(str(bundle_id or "").strip())
        if not bundle:
            return None
        path = str(bundle.get("stored_file_path") or "")
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
        seeds = self.load_historical_etc_repair_parsed_seeds()
        seeds[str(bundle_id)] = seed
        self._save_snapshot("historical_etc_repair_parsed_seeds", seeds)
        return seed

    def load_historical_etc_repair_parsed_seeds(self) -> dict[str, dict[str, Any]]:
        rows = self._ops_tax_etc_repository.load_historical_etc_repair_parsed_seeds()
        if rows:
            return rows
        payload = self._load_snapshot("historical_etc_repair_parsed_seeds")
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)} if isinstance(payload, dict) else {}

    def load_historical_etc_repair_parsed_seed(self, bundle_id: str) -> dict[str, Any] | None:
        seed = self.load_historical_etc_repair_parsed_seeds().get(str(bundle_id or "").strip())
        return dict(seed) if isinstance(seed, dict) else None

    def load_historical_etc_repair_states(self) -> dict[str, dict[str, Any]]:
        rows = self._ops_tax_etc_repository.load_historical_etc_repair_states()
        if rows:
            return rows
        payload = self._load_snapshot("historical_etc_repair_states")
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)} if isinstance(payload, dict) else {}

    def save_historical_etc_repair_states(self, states: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_historical_etc_repair_states(states)
        self._save_snapshot("historical_etc_repair_states", states)

    def load_background_jobs(self) -> dict[str, Any]:
        snapshot = self._load_snapshot("background_jobs")
        if snapshot:
            return snapshot
        return self._ops_tax_etc_repository.load_background_jobs()

    def save_background_jobs(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_background_jobs(snapshot)
        self._save_snapshot("background_jobs", snapshot)

    def load_app_health_alerts(self) -> dict[str, Any]:
        snapshot = self._load_snapshot("app_health_alerts")
        if snapshot:
            return snapshot
        return self._ops_tax_etc_repository.load_app_health_alerts()

    def save_app_health_alerts(self, snapshot: dict[str, Any]) -> None:
        self._ops_tax_etc_repository.save_app_health_alerts(snapshot)
        self._save_snapshot("app_health_alerts", snapshot)

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_workbench_pair_relations()
        fallback = self._load_snapshot("workbench_pair_relations")
        if snapshot or fallback:
            pair_relations = snapshot.get("pair_relations") if isinstance(snapshot, dict) else None
            pair_history = snapshot.get("pair_relation_history") if isinstance(snapshot, dict) else None
            return normalize_workbench_pair_relations(
                pair_relations if pair_relations else None,
                pair_history if pair_history else None,
                snapshot=fallback,
            )
        return {}

    def save_workbench_pair_relations(self, snapshot: dict[str, Any], *, changed_case_ids: set[str] | None = None) -> None:
        self._workbench_repository.save_workbench_pair_relations(snapshot, changed_case_ids=changed_case_ids)
        self._save_snapshot("workbench_pair_relations", snapshot)

    def load_no_oa_bank_batches(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_no_oa_bank_batches()
        fallback = self._load_snapshot("no_oa_bank_batches")
        if snapshot or fallback:
            batches = snapshot.get("batches") if isinstance(snapshot, dict) else None
            audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else None
            return normalize_no_oa_bank_batches(
                batches if batches else None,
                audit_log if audit_log else None,
                snapshot=fallback,
            )
        return {}

    def save_no_oa_bank_batches(self, snapshot: dict[str, Any]) -> None:
        self._workbench_repository.save_no_oa_bank_batches(snapshot)
        self._save_snapshot("no_oa_bank_batches", snapshot)

    def load_workbench_read_models(self) -> dict[str, Any]:
        snapshot = self._read_model_repository.load_workbench_read_models()
        if snapshot:
            return snapshot
        return self._load_snapshot("workbench_read_models") or {}

    def save_workbench_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        self._read_model_repository.save_workbench_read_models(snapshot, changed_scope_keys=changed_scope_keys)
        self._save_snapshot("workbench_read_models", snapshot)

    def load_workbench_candidate_matches(self) -> dict[str, Any]:
        fallback = self._load_snapshot("workbench_candidate_matches")
        if fallback:
            return fallback
        snapshot = self._read_model_repository.load_workbench_candidate_matches()
        if snapshot:
            return snapshot
        return {}

    def save_workbench_candidate_matches(self, snapshot: dict[str, Any], *, changed_scope_months: set[str] | None = None) -> None:
        self._read_model_repository.save_workbench_candidate_matches(snapshot, changed_scope_months=changed_scope_months)
        self._save_snapshot("workbench_candidate_matches", snapshot)

    def save_workbench_matching_dirty_scopes(self, snapshot: dict[str, Any]) -> None:
        self._save_snapshot("workbench_matching_dirty_scopes", snapshot)

    def load_bank_transaction_categories(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_bank_transaction_categories()
        fallback = self._load_snapshot("bank_transaction_categories")
        if snapshot or fallback:
            categories = snapshot.get("categories") if isinstance(snapshot, dict) else None
            audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else None
            return normalize_bank_transaction_categories(
                categories if categories else None,
                audit_log if audit_log else None,
                snapshot=fallback,
            )
        return {}

    def save_bank_transaction_categories(self, snapshot: dict[str, Any]) -> None:
        self._workbench_repository.save_bank_transaction_categories(snapshot)
        self._save_snapshot("bank_transaction_categories", snapshot)

    def load_turnover_relations(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_turnover_relations()
        fallback = self._load_snapshot("turnover_relations")
        if snapshot or fallback:
            relations = snapshot.get("relations") if isinstance(snapshot, dict) else None
            audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else None
            return normalize_turnover_relations(
                relations if relations else None,
                audit_log if audit_log else None,
                snapshot=fallback,
            )
        return {}

    def save_turnover_relations(self, snapshot: dict[str, Any]) -> None:
        self._workbench_repository.save_turnover_relations(snapshot)
        self._save_snapshot("turnover_relations", snapshot)

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
        fallback = self._load_snapshot("turnover_ledger_extras")
        if fallback:
            return fallback
        return {"version": 1, "extras": []}

    def save_turnover_ledger_extras(self, snapshot: dict[str, Any]) -> None:
        self._workbench_repository.save_turnover_ledger_extras(snapshot)
        self._save_snapshot("turnover_ledger_extras", snapshot)

    def load_cost_statistics_read_models(self) -> dict[str, Any]:
        snapshot = self._read_model_repository.load_cost_statistics_read_models()
        if snapshot:
            return snapshot
        return self._load_snapshot("cost_statistics_read_models") or {}

    def save_cost_statistics_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        self._read_model_repository.save_cost_statistics_read_models(snapshot, changed_scope_keys=changed_scope_keys)
        self._save_snapshot("cost_statistics_read_models", snapshot)

    def load_tax_offset_read_models(self) -> dict[str, Any]:
        snapshot = self._read_model_repository.load_tax_offset_read_models()
        if snapshot:
            return snapshot
        return self._load_snapshot("tax_offset_read_models") or {}

    def save_tax_offset_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        self._read_model_repository.save_tax_offset_read_models(snapshot, changed_scope_keys=changed_scope_keys)
        self._save_snapshot("tax_offset_read_models", snapshot)

    def load(self) -> dict[str, Any]:
        snapshot = {
            "imports": self._load_imports(),
            "file_imports": self._load_file_imports(),
            "matching": self._load_matching(),
            "bank_transaction_categories": self.load_bank_transaction_categories(),
            "workbench_overrides": self._load_snapshot_or_empty("workbench_overrides"),
            "workbench_exception_cases": self.load_workbench_exception_cases(),
            "workbench_pair_relations": self.load_workbench_pair_relations(),
            "workbench_read_models": self.load_workbench_read_models(),
            "workbench_candidate_matches": self.load_workbench_candidate_matches(),
            "workbench_matching_dirty_scopes": self._load_snapshot_or_empty("workbench_matching_dirty_scopes"),
            "no_oa_bank_batches": self.load_no_oa_bank_batches(),
            "turnover_relations": self.load_turnover_relations(),
            "turnover_ledger_extras": self.load_turnover_ledger_extras(),
            "cost_statistics_read_models": self.load_cost_statistics_read_models(),
            "tax_offset_read_models": self.load_tax_offset_read_models(),
            "app_health_alerts": self.load_app_health_alerts(),
            "pending_invoice_commands": self.load_pending_invoice_commands(),
        }
        saved_whole = self._load_snapshot("full_state")
        if saved_whole:
            for key, value in saved_whole.items():
                if key not in snapshot or snapshot.get(key) in ({}, [], None):
                    snapshot[key] = value
        return snapshot

    def save(self, payload: dict[str, Any]) -> None:
        normalized = self._serialize_value(payload)
        if not isinstance(normalized, dict):
            raise ValueError("state payload must be a dictionary.")
        if "imports" in normalized:
            self._core_repository.save_imports(normalized.get("imports") or {})
        if "file_imports" in normalized:
            self._core_repository.save_file_imports(normalized.get("file_imports") or {})
        if "bank_transaction_categories" in normalized:
            self.save_bank_transaction_categories(normalized.get("bank_transaction_categories") or {})
        if "matching" in normalized:
            self._save_snapshot("matching", normalized.get("matching") or {})
        if "workbench_overrides" in normalized:
            self.save_workbench_overrides(normalized.get("workbench_overrides") or {})
        if "workbench_exception_cases" in normalized:
            self.save_workbench_exception_cases(normalized.get("workbench_exception_cases") or {})
        if "workbench_pair_relations" in normalized:
            self.save_workbench_pair_relations(normalized.get("workbench_pair_relations") or {})
        if "no_oa_bank_batches" in normalized:
            self.save_no_oa_bank_batches(normalized.get("no_oa_bank_batches") or {})
        if "workbench_read_models" in normalized:
            self.save_workbench_read_models(normalized.get("workbench_read_models") or {})
        if "workbench_candidate_matches" in normalized:
            self.save_workbench_candidate_matches(normalized.get("workbench_candidate_matches") or {})
        if "workbench_matching_dirty_scopes" in normalized:
            self.save_workbench_matching_dirty_scopes(normalized.get("workbench_matching_dirty_scopes") or {})
        if "turnover_relations" in normalized:
            self.save_turnover_relations(normalized.get("turnover_relations") or {})
        if "turnover_ledger_extras" in normalized:
            self.save_turnover_ledger_extras(normalized.get("turnover_ledger_extras") or {})
        if "cost_statistics_read_models" in normalized:
            self.save_cost_statistics_read_models(normalized.get("cost_statistics_read_models") or {})
        if "tax_offset_read_models" in normalized:
            self.save_tax_offset_read_models(normalized.get("tax_offset_read_models") or {})
        if "app_health_alerts" in normalized:
            self.save_app_health_alerts(normalized.get("app_health_alerts") or {})
        if "pending_invoice_commands" in normalized:
            self.save_pending_invoice_commands(normalized.get("pending_invoice_commands") or {})
        self._save_snapshot("full_state", normalized)

    def save_workbench_overrides(self, workbench_overrides_snapshot: dict[str, Any], *, changed_row_ids: set[str] | None = None) -> None:
        self._workbench_repository.save_workbench_overrides(workbench_overrides_snapshot, changed_row_ids=changed_row_ids)
        self._save_snapshot("workbench_overrides", workbench_overrides_snapshot)

    def load_workbench_exception_cases(self) -> dict[str, Any]:
        snapshot = self._workbench_repository.load_workbench_exception_cases()
        if snapshot:
            return snapshot
        return self._load_snapshot("workbench_exception_cases") or {}

    def save_workbench_exception_cases(self, snapshot: dict[str, Any]) -> None:
        self._workbench_repository.save_workbench_exception_cases(snapshot)
        self._save_snapshot("workbench_exception_cases", snapshot)

    def store_import_file(self, *, session_id: str, file_id: str, file_name: str, content: bytes) -> str:
        stored_file_path = self._store_local_file("imports", file_id, file_name, content)
        file_object_id = self._save_file_object(file_id=file_id, file_name=file_name, stored_file_path=stored_file_path, content=content)
        self._connection.execute(
            """
            insert into app.import_files(legacy_mongo_id, session_id, stored_file_path, original_filename, status, file_object_id, raw_payload)
            values (%s, %s, %s, %s, 'stored', %s::uuid, %s)
            on conflict (legacy_mongo_id) do update set
                session_id = excluded.session_id,
                stored_file_path = excluded.stored_file_path,
                original_filename = excluded.original_filename,
                status = excluded.status,
                file_object_id = excluded.file_object_id,
                raw_payload = excluded.raw_payload
            """,
            (
                file_id,
                session_id,
                stored_file_path,
                file_name,
                file_object_id,
                _jsonb({"normalized_payload": {"id": file_id, "file_name": file_name, "stored_file_path": stored_file_path, "session_id": session_id}}),
            ),
        )
        return stored_file_path

    def read_import_file(self, stored_file_path: str) -> bytes:
        return self._read_file(stored_file_path)

    def delete_import_files(self, stored_file_paths: list[str]) -> int:
        deleted = 0
        seen: set[str] = set()
        for path in stored_file_paths:
            normalized = str(path or "")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            if self._is_gridfs_ref(normalized):
                row_count = self._connection.execute(
                    "update app.import_files set status = 'deleted' where stored_file_path = %s",
                    (normalized,),
                )
                deleted += max(row_count, 1)
                continue
            file_path = Path(normalized)
            if file_path.exists():
                file_path.unlink()
                self._connection.execute(
                    "update app.import_files set status = 'deleted' where stored_file_path = %s",
                    (normalized,),
                )
                deleted += 1
        return deleted

    def import_session_exists(self, session_id: str) -> bool:
        row = self._connection.fetch_one("select 1 from app.import_files where session_id = %s limit 1", (session_id,))
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
            where import_files.legacy_mongo_id = %s
               or import_files.id::text = %s
               or file_objects.legacy_mongo_id = %s
               or file_objects.legacy_gridfs_id = %s
               or file_objects.object_key = %s
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

    def _load_snapshot(self, key: str) -> dict[str, Any]:
        return self._load_settings(f"{STATE_KEY_PREFIX}{key}")

    def _save_snapshot(self, key: str, payload: dict[str, Any]) -> None:
        self._save_settings(f"{STATE_KEY_PREFIX}{key}", payload)

    def _load_snapshot_or_empty(self, key: str) -> dict[str, Any]:
        return self._load_snapshot(key) or {}

    def _load_snapshot_or_table_map(self, key: str, sql: str, payload_key: str) -> dict[str, Any]:
        rows = self._connection.fetch_all(sql)
        values = {str(row.get("key")): self._row_payload(row, "payload", "extra_payload", "raw_payload") for row in rows}
        if values:
            return {payload_key: values}
        return self._load_snapshot(key) or {}

    def _load_imports(self) -> dict[str, Any]:
        snapshot = self._core_repository.load_imports()
        if snapshot:
            return snapshot
        saved = self._load_snapshot("imports")
        return saved if saved else {}

    def _load_file_imports(self) -> dict[str, Any]:
        snapshot = self._core_repository.load_file_imports()
        if snapshot:
            return snapshot
        saved = self._load_snapshot("file_imports")
        return saved if saved else {}

    def _load_matching(self) -> dict[str, Any]:
        saved = self._load_snapshot("matching")
        if saved:
            return saved
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

    def _store_local_file(self, namespace: str, file_id: str, file_name: str, content: bytes) -> str:
        safe_name = ApplicationStateStore._sanitize_name(file_name)  # noqa: SLF001
        target_dir = self._file_root / ApplicationStateStore._sanitize_name(namespace) / ApplicationStateStore._sanitize_name(file_id)  # noqa: SLF001
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_name
        target_path.write_bytes(content)
        return str(target_path)

    def _read_file(self, stored_file_path: str) -> bytes:
        if self._is_gridfs_ref(stored_file_path):
            if self._legacy_file_reader is None:
                raise RuntimeError("Legacy GridFS file access is not configured for PostgreSQL state store.")
            return bytes(self._legacy_file_reader.read(stored_file_path))
        path = Path(str(stored_file_path or ""))
        if not path.exists():
            raise FileNotFoundError(stored_file_path)
        return path.read_bytes()

    @staticmethod
    def _is_gridfs_ref(value: str) -> bool:
        return str(value or "").startswith(GRIDFS_REF_PREFIX)

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
