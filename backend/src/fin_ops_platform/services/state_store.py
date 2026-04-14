from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from io import BytesIO
import json
import os
from pathlib import Path
import pickle
import re
from typing import Any
from urllib.parse import quote_plus

from bson.binary import Binary
from gridfs import GridFSBucket
from pymongo import MongoClient


FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
DEFAULT_APP_MONGO_DATABASE = "fin_ops_platform_app"
LEGACY_APP_MONGO_COLLECTION = "application_state"
STATE_COLLECTIONS = {
    "imports": "imports_state",
    "file_imports": "file_import_sessions_state",
    "matching": "matching_state",
}
FILE_METADATA_COLLECTION = "import_file_metadata"
META_COLLECTION = "app_state_meta"
IMPORTS_META_COLLECTION = "imports_meta"
IMPORT_BATCHES_COLLECTION = "import_batches"
INVOICES_COLLECTION = "invoices"
BANK_TRANSACTIONS_COLLECTION = "bank_transactions"
FILE_IMPORTS_META_COLLECTION = "file_imports_meta"
FILE_IMPORT_SESSIONS_COLLECTION = "file_import_sessions"
FILE_IMPORT_FILES_COLLECTION = "file_import_files"
MATCHING_META_COLLECTION = "matching_meta"
MATCHING_RUNS_COLLECTION = "matching_runs"
MATCHING_RESULTS_COLLECTION = "matching_results"
WORKBENCH_OVERRIDES_META_COLLECTION = "workbench_overrides_meta"
WORKBENCH_ROW_OVERRIDES_COLLECTION = "workbench_row_overrides"
WORKBENCH_PAIR_RELATIONS_META_COLLECTION = "workbench_pair_relations_meta"
WORKBENCH_PAIR_RELATIONS_COLLECTION = "workbench_pair_relations"
WORKBENCH_READ_MODELS_META_COLLECTION = "workbench_read_models_meta"
WORKBENCH_READ_MODELS_COLLECTION = "workbench_read_models"
OA_ATTACHMENT_INVOICE_CACHE_COLLECTION = "oa_attachment_invoice_cache"
APP_SETTINGS_COLLECTION = "app_settings"
TAX_CERTIFIED_IMPORTS_META_COLLECTION = "tax_certified_imports_meta"
TAX_CERTIFIED_IMPORT_SESSIONS_COLLECTION = "tax_certified_import_sessions"
TAX_CERTIFIED_IMPORT_BATCHES_COLLECTION = "tax_certified_import_batches"
TAX_CERTIFIED_IMPORT_RECORDS_COLLECTION = "tax_certified_import_records"
STATE_DOCUMENT_ID = "current_state"
META_DOCUMENT_ID = "_meta"
APP_SETTINGS_DOCUMENT_ID = "settings"
GRIDFS_BUCKET_NAME = "import_file_blobs"
GRIDFS_REF_PREFIX = "gridfs://"
MONGO_ONLY_STORAGE_MODE = "mongo_only"


@dataclass(slots=True)
class MongoStateSettings:
    host: str
    database: str = DEFAULT_APP_MONGO_DATABASE
    port: int = 27017
    username: str | None = None
    password: str | None = None
    auth_source: str = "admin"
    request_timeout_ms: int = 5000

    @property
    def mongo_uri(self) -> str:
        credentials = ""
        if self.username:
            password = quote_plus(self.password or "")
            credentials = f"{quote_plus(self.username)}:{password}@"
        return (
            f"mongodb://{credentials}{self.host}:{self.port}/{self.database}"
            f"?authSource={quote_plus(self.auth_source)}"
        )


def default_data_dir() -> Path:
    return Path(__file__).resolve().parents[4] / ".runtime" / "fin_ops_platform"


def load_mongo_state_settings(data_dir: Path | None = None) -> MongoStateSettings | None:
    file_payload: dict[str, Any] = {}
    oa_payload: dict[str, Any] = {}
    explicit_enable = False

    if data_dir is not None:
        app_config_path = data_dir / "app_mongo_config.json"
        if app_config_path.exists():
            loaded = json.loads(app_config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                file_payload = loaded
                explicit_enable = True

        oa_config_path = data_dir / "oa_mongo_config.json"
        if oa_config_path.exists():
            loaded = json.loads(oa_config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                oa_payload = loaded

    def pick(env_name: str, file_key: str, oa_key: str | None = None, default: Any = None) -> Any:
        env_value = os.getenv(env_name)
        if env_value not in (None, ""):
            return env_value
        if file_key in file_payload and file_payload.get(file_key) not in (None, ""):
            return file_payload[file_key]
        if oa_key is not None and oa_payload.get(oa_key) not in (None, ""):
            return oa_payload.get(oa_key)
        return default

    env_explicit = any(
        os.getenv(name) not in (None, "")
        for name in (
            "FIN_OPS_APP_MONGO_HOST",
            "FIN_OPS_APP_MONGO_DATABASE",
            "FIN_OPS_APP_MONGO_USERNAME",
            "FIN_OPS_APP_MONGO_PASSWORD",
        )
    )
    host = pick("FIN_OPS_APP_MONGO_HOST", "host", "host" if explicit_enable or env_explicit else None)
    if not (explicit_enable or env_explicit):
        return None
    if not host:
        return None

    return MongoStateSettings(
        host=str(host),
        port=int(pick("FIN_OPS_APP_MONGO_PORT", "port", "port", 27017)),
        database=str(pick("FIN_OPS_APP_MONGO_DATABASE", "database", None, DEFAULT_APP_MONGO_DATABASE)),
        username=pick("FIN_OPS_APP_MONGO_USERNAME", "username", "username"),
        password=pick("FIN_OPS_APP_MONGO_PASSWORD", "password", "password"),
        auth_source=str(pick("FIN_OPS_APP_MONGO_AUTH_SOURCE", "auth_source", "auth_source", "admin")),
        request_timeout_ms=int(pick("FIN_OPS_APP_MONGO_TIMEOUT_MS", "request_timeout_ms", "request_timeout_ms", 5000)),
    )


class ApplicationStateStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        root = data_dir or default_data_dir()
        self._data_dir = root
        self._legacy_state_path = root / "state.pkl"
        self._import_file_root = root / "import_files"
        self._app_settings_path = root / "app_settings.json"
        self._oa_attachment_invoice_cache_path = root / "oa_attachment_invoice_cache.json"
        self._tax_certified_imports_path = root / "tax_certified_imports.pkl"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._mongo_settings = load_mongo_state_settings(root)
        self._storage_mode = (
            os.getenv("FIN_OPS_STORAGE_MODE")
            or (MONGO_ONLY_STORAGE_MODE if self._mongo_settings is not None else "auto")
        ).strip().lower()
        if self._storage_mode == MONGO_ONLY_STORAGE_MODE and self._mongo_settings is None:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        self._mongo_client: MongoClient | None = None
        self._mongo_database: Any | None = None
        self._legacy_mongo_collection: Any | None = None
        self._mongo_state_collections: dict[str, Any] = {}
        self._mongo_metadata_collection: Any | None = None
        self._mongo_meta_collection: Any | None = None
        self._mongo_detailed_collections: dict[str, Any] = {}
        self._mongo_file_bucket: GridFSBucket | None = None
        if self._mongo_settings is not None:
            self._mongo_client = MongoClient(
                self._mongo_settings.mongo_uri,
                serverSelectionTimeoutMS=self._mongo_settings.request_timeout_ms,
                connectTimeoutMS=self._mongo_settings.request_timeout_ms,
                socketTimeoutMS=self._mongo_settings.request_timeout_ms,
            )
            self._mongo_database = self._mongo_client[self._mongo_settings.database]
            self._legacy_mongo_collection = self._mongo_database[LEGACY_APP_MONGO_COLLECTION]
            self._mongo_state_collections = {
                key: self._mongo_database[collection_name]
                for key, collection_name in STATE_COLLECTIONS.items()
            }
            self._mongo_metadata_collection = self._mongo_database[FILE_METADATA_COLLECTION]
            self._mongo_meta_collection = self._mongo_database[META_COLLECTION]
            self._mongo_detailed_collections = {
                "imports_meta": self._mongo_database[IMPORTS_META_COLLECTION],
                "import_batches": self._mongo_database[IMPORT_BATCHES_COLLECTION],
                "invoices": self._mongo_database[INVOICES_COLLECTION],
                "bank_transactions": self._mongo_database[BANK_TRANSACTIONS_COLLECTION],
                "file_imports_meta": self._mongo_database[FILE_IMPORTS_META_COLLECTION],
                "file_import_sessions": self._mongo_database[FILE_IMPORT_SESSIONS_COLLECTION],
                "file_import_files": self._mongo_database[FILE_IMPORT_FILES_COLLECTION],
                "matching_meta": self._mongo_database[MATCHING_META_COLLECTION],
                "matching_runs": self._mongo_database[MATCHING_RUNS_COLLECTION],
                "matching_results": self._mongo_database[MATCHING_RESULTS_COLLECTION],
                "workbench_overrides_meta": self._mongo_database[WORKBENCH_OVERRIDES_META_COLLECTION],
                "workbench_row_overrides": self._mongo_database[WORKBENCH_ROW_OVERRIDES_COLLECTION],
                "workbench_pair_relations_meta": self._mongo_database[WORKBENCH_PAIR_RELATIONS_META_COLLECTION],
                "workbench_pair_relations": self._mongo_database[WORKBENCH_PAIR_RELATIONS_COLLECTION],
                "workbench_read_models_meta": self._mongo_database[WORKBENCH_READ_MODELS_META_COLLECTION],
                "workbench_read_models": self._mongo_database[WORKBENCH_READ_MODELS_COLLECTION],
                "oa_attachment_invoice_cache": self._mongo_database[OA_ATTACHMENT_INVOICE_CACHE_COLLECTION],
                "app_settings": self._mongo_database[APP_SETTINGS_COLLECTION],
                "tax_certified_imports_meta": self._mongo_database[TAX_CERTIFIED_IMPORTS_META_COLLECTION],
                "tax_certified_import_sessions": self._mongo_database[TAX_CERTIFIED_IMPORT_SESSIONS_COLLECTION],
                "tax_certified_import_batches": self._mongo_database[TAX_CERTIFIED_IMPORT_BATCHES_COLLECTION],
                "tax_certified_import_records": self._mongo_database[TAX_CERTIFIED_IMPORT_RECORDS_COLLECTION],
            }
            self._mongo_file_bucket = GridFSBucket(self._mongo_database, bucket_name=GRIDFS_BUCKET_NAME)
            self._ensure_mongo_metadata()
        else:
            self._import_file_root.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def storage_backend(self) -> str:
        return "mongo" if self._mongo_database is not None else "local_pickle"

    @property
    def storage_mode(self) -> str:
        return self._storage_mode

    @property
    def mongo_database_name(self) -> str | None:
        return self._mongo_settings.database if self._mongo_settings is not None else None

    def load_app_settings(self) -> dict[str, Any]:
        default_payload = {
            "completed_project_ids": [],
            "bank_account_mappings": [],
            "allowed_usernames": [],
            "readonly_export_usernames": [],
            "admin_usernames": [],
            "workbench_column_layouts": {},
            "oa_retention": {},
            "oa_invoice_offset": {},
        }
        if self._mongo_database is not None:
            document = self._mongo_detailed_collections["app_settings"].find_one({"_id": APP_SETTINGS_DOCUMENT_ID})
            payload = self._load_binary_payload(document)
            if isinstance(payload, dict):
                return {
                    "completed_project_ids": list(payload.get("completed_project_ids") or []),
                    "bank_account_mappings": list(payload.get("bank_account_mappings") or []),
                    "allowed_usernames": list(payload.get("allowed_usernames") or []),
                    "readonly_export_usernames": list(payload.get("readonly_export_usernames") or []),
                    "admin_usernames": list(payload.get("admin_usernames") or []),
                    "workbench_column_layouts": dict(payload.get("workbench_column_layouts") or {}),
                    "oa_retention": dict(payload.get("oa_retention") or {}),
                    "oa_invoice_offset": dict(payload.get("oa_invoice_offset") or {}),
                }
            return default_payload

        if not self._app_settings_path.exists():
            return default_payload
        try:
            loaded = json.loads(self._app_settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default_payload
        if not isinstance(loaded, dict):
            return default_payload
        return {
            "completed_project_ids": list(loaded.get("completed_project_ids") or []),
            "bank_account_mappings": list(loaded.get("bank_account_mappings") or []),
            "allowed_usernames": list(loaded.get("allowed_usernames") or []),
            "readonly_export_usernames": list(loaded.get("readonly_export_usernames") or []),
            "admin_usernames": list(loaded.get("admin_usernames") or []),
            "workbench_column_layouts": dict(loaded.get("workbench_column_layouts") or {}),
            "oa_retention": dict(loaded.get("oa_retention") or {}),
            "oa_invoice_offset": dict(loaded.get("oa_invoice_offset") or {}),
        }

    def save_app_settings(self, payload: dict[str, Any]) -> None:
        normalized_payload = {
            "completed_project_ids": list(payload.get("completed_project_ids") or []),
            "bank_account_mappings": list(payload.get("bank_account_mappings") or []),
            "allowed_usernames": list(payload.get("allowed_usernames") or []),
            "readonly_export_usernames": list(payload.get("readonly_export_usernames") or []),
            "admin_usernames": list(payload.get("admin_usernames") or []),
            "workbench_column_layouts": dict(payload.get("workbench_column_layouts") or {}),
            "oa_retention": dict(payload.get("oa_retention") or {}),
            "oa_invoice_offset": dict(payload.get("oa_invoice_offset") or {}),
        }
        if self._mongo_database is not None:
            self._mongo_detailed_collections["app_settings"].update_one(
                {"_id": APP_SETTINGS_DOCUMENT_ID},
                {
                    "$set": {
                        "completed_project_ids": normalized_payload["completed_project_ids"],
                        "bank_account_mappings": normalized_payload["bank_account_mappings"],
                        "allowed_usernames": normalized_payload["allowed_usernames"],
                        "readonly_export_usernames": normalized_payload["readonly_export_usernames"],
                        "admin_usernames": normalized_payload["admin_usernames"],
                        "workbench_column_layouts": normalized_payload["workbench_column_layouts"],
                        "oa_retention": normalized_payload["oa_retention"],
                        "oa_invoice_offset": normalized_payload["oa_invoice_offset"],
                        "payload": Binary(pickle.dumps(normalized_payload)),
                        "updated_at": datetime.now(UTC),
                    }
                },
                upsert=True,
            )
            return

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        self._app_settings_path.write_text(
            json.dumps(normalized_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_oa_attachment_invoice_cache_entry(self, cache_key: str) -> dict[str, object] | None:
        normalized_cache_key = str(cache_key).strip()
        if not normalized_cache_key:
            return None
        if self._mongo_database is not None:
            document = self._mongo_detailed_collections["oa_attachment_invoice_cache"].find_one({"_id": normalized_cache_key})
            payload = self._load_binary_payload(document)
            return dict(payload) if isinstance(payload, dict) else None

        if not self._oa_attachment_invoice_cache_path.exists():
            return None
        try:
            loaded = json.loads(self._oa_attachment_invoice_cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        entry = loaded.get(normalized_cache_key) if isinstance(loaded, dict) else None
        return dict(entry) if isinstance(entry, dict) else None

    def save_oa_attachment_invoice_cache_entry(self, cache_key: str, payload: dict[str, object]) -> None:
        normalized_cache_key = str(cache_key).strip()
        if not normalized_cache_key:
            return
        normalized_payload = dict(payload if isinstance(payload, dict) else {})
        normalized_payload["cache_key"] = normalized_cache_key
        if self._mongo_database is not None:
            self._mongo_detailed_collections["oa_attachment_invoice_cache"].update_one(
                {"_id": normalized_cache_key},
                {
                    "$set": {
                        "payload": Binary(pickle.dumps(normalized_payload)),
                        "updated_at": datetime.now(UTC),
                    }
                },
                upsert=True,
            )
            return

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        try:
            loaded = json.loads(self._oa_attachment_invoice_cache_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            loaded = {}
        cache_payload = loaded if isinstance(loaded, dict) else {}
        cache_payload[normalized_cache_key] = self._serialize_value(normalized_payload)
        self._oa_attachment_invoice_cache_path.write_text(
            json.dumps(cache_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_tax_certified_imports(self) -> dict[str, Any]:
        if self._mongo_database is not None:
            meta_document = self._mongo_detailed_collections["tax_certified_imports_meta"].find_one({"_id": STATE_DOCUMENT_ID})
            meta_payload = self._load_binary_payload(meta_document)
            sessions = self._load_entities_by_id(self._mongo_detailed_collections["tax_certified_import_sessions"])
            batches = self._load_entities_by_id(self._mongo_detailed_collections["tax_certified_import_batches"])
            records = self._load_entities_by_id(self._mongo_detailed_collections["tax_certified_import_records"])
            if not meta_payload and not sessions and not batches and not records:
                return {}
            payload = meta_payload if isinstance(meta_payload, dict) else {}
            payload["sessions"] = sessions
            payload["batches"] = batches
            payload["records"] = records
            return payload

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        if not self._tax_certified_imports_path.exists():
            return {}
        with self._tax_certified_imports_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def save_tax_certified_imports(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        if self._mongo_database is not None:
            self._save_tax_certified_imports_detailed(normalized_snapshot, datetime.now(UTC))
            return

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        with self._tax_certified_imports_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        if self._mongo_database is not None:
            return self._load_workbench_pair_relations_detailed_payload()

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        current_payload = self._load_local_pickle()
        snapshot = current_payload.get("workbench_pair_relations")
        return snapshot if isinstance(snapshot, dict) else {}

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: list[str] | None = None,
    ) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        if self._mongo_database is not None:
            self._save_workbench_pair_relations_detailed(
                normalized_snapshot,
                datetime.now(UTC),
                changed_case_ids=changed_case_ids,
            )
            return

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        current_payload = self._load_local_pickle()
        current_payload["workbench_pair_relations"] = normalized_snapshot
        with self._legacy_state_path.open("wb") as handle:
            pickle.dump(current_payload, handle)

    def load_workbench_read_models(self) -> dict[str, Any]:
        if self._mongo_database is not None:
            return self._load_workbench_read_models_detailed_payload()

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        current_payload = self._load_local_pickle()
        snapshot = current_payload.get("workbench_read_models")
        return snapshot if isinstance(snapshot, dict) else {}

    def save_workbench_read_models(
        self,
        snapshot: dict[str, Any],
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        if self._mongo_database is not None:
            self._save_workbench_read_models_detailed(
                normalized_snapshot,
                datetime.now(UTC),
                changed_scope_keys=changed_scope_keys,
            )
            return

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        current_payload = self._load_local_pickle()
        current_payload["workbench_read_models"] = normalized_snapshot
        with self._legacy_state_path.open("wb") as handle:
            pickle.dump(current_payload, handle)

    def load(self) -> dict[str, Any]:
        if self._mongo_database is not None:
            detailed_payload = self._load_detailed_mongo_payload()
            if detailed_payload:
                return detailed_payload

            split_payload = self._load_split_mongo_payload()
            if split_payload:
                if self._migrate_legacy_file_refs_to_gridfs(split_payload):
                    self.save(split_payload)
                else:
                    self.save(split_payload)
                return split_payload

            legacy_payload = self._load_legacy_mongo_payload()
            if legacy_payload:
                if self._migrate_legacy_file_refs_to_gridfs(legacy_payload):
                    self.save(legacy_payload)
                else:
                    self.save(legacy_payload)
                return legacy_payload
            return {}

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        return self._load_local_pickle()

    def save(self, payload: dict[str, Any]) -> None:
        if self._mongo_database is not None:
            updated_at = datetime.now(UTC)
            self._save_imports_detailed(payload.get("imports", {}), updated_at)
            self._save_file_imports_detailed(payload.get("file_imports", {}), updated_at)
            self._save_matching_detailed(payload.get("matching", {}), updated_at)
            self._save_workbench_overrides_detailed(payload.get("workbench_overrides", {}), updated_at)
            if "workbench_pair_relations" in payload:
                self._save_workbench_pair_relations_detailed(payload.get("workbench_pair_relations", {}), updated_at)
            if "workbench_read_models" in payload:
                self._save_workbench_read_models_detailed(payload.get("workbench_read_models", {}), updated_at)
            self._save_file_import_metadata(payload.get("file_imports", {}), updated_at)
            if self._has_non_empty_state(payload):
                self._clear_legacy_snapshot_collections()
            return

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        with self._legacy_state_path.open("wb") as handle:
            pickle.dump(payload, handle)

    def save_workbench_overrides(
        self,
        workbench_overrides_snapshot: dict[str, Any],
        *,
        changed_row_ids: list[str] | None = None,
    ) -> None:
        if self._mongo_database is not None:
            updated_at = datetime.now(UTC)
            if changed_row_ids is None:
                self._save_workbench_overrides_detailed(workbench_overrides_snapshot, updated_at)
            else:
                self._save_workbench_overrides_detailed_incremental(
                    workbench_overrides_snapshot,
                    updated_at,
                    changed_row_ids,
                )
            return

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")

        current_payload = self._load_local_pickle()
        current_payload["workbench_overrides"] = workbench_overrides_snapshot
        with self._legacy_state_path.open("wb") as handle:
            pickle.dump(current_payload, handle)

    def store_import_file(self, *, session_id: str, file_id: str, file_name: str, content: bytes) -> str:
        if self._mongo_file_bucket is not None:
            sanitized_name = self._sanitize_name(file_name)
            self._mongo_file_bucket.upload_from_stream_with_id(
                file_id,
                sanitized_name,
                BytesIO(content),
                metadata={
                    "session_id": session_id,
                    "file_id": file_id,
                    "file_name": file_name,
                    "stored_at": datetime.now(UTC),
                },
            )
            return self._build_gridfs_ref(file_id, sanitized_name)
        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo GridFS is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        session_dir = self._import_file_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        target_path = session_dir / f"{file_id}_{self._sanitize_name(file_name)}"
        target_path.write_bytes(content)
        return str(target_path)

    def read_import_file(self, stored_file_path: str) -> bytes:
        if self._is_gridfs_ref(stored_file_path):
            if self._mongo_file_bucket is None:
                raise RuntimeError("Mongo GridFS is not configured for stored import file access.")
            file_id = self._parse_gridfs_ref(stored_file_path)
            stream = self._mongo_file_bucket.open_download_stream(file_id)
            return stream.read()
        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Local import file access is disabled in FIN_OPS_STORAGE_MODE=mongo_only.")
        return Path(stored_file_path).read_bytes()

    def delete_import_files(self, stored_file_paths: list[str]) -> int:
        deleted_count = 0
        seen_paths: set[str] = set()
        for stored_file_path in stored_file_paths:
            normalized_path = str(stored_file_path or "").strip()
            if not normalized_path or normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)
            if self._is_gridfs_ref(normalized_path):
                if self._mongo_file_bucket is None:
                    continue
                try:
                    self._mongo_file_bucket.delete(self._parse_gridfs_ref(normalized_path))
                    deleted_count += 1
                except Exception:
                    continue
                continue
            if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
                continue
            target_path = Path(normalized_path)
            if target_path.exists():
                target_path.unlink(missing_ok=True)
                deleted_count += 1
        return deleted_count

    def clear_oa_attachment_invoice_cache(self) -> int:
        if self._mongo_database is not None:
            result = self._mongo_detailed_collections["oa_attachment_invoice_cache"].delete_many({})
            return int(result.deleted_count)

        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            raise RuntimeError("Mongo state storage is required when FIN_OPS_STORAGE_MODE=mongo_only.")
        if not self._oa_attachment_invoice_cache_path.exists():
            return 0
        try:
            loaded = json.loads(self._oa_attachment_invoice_cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        entry_count = len(loaded) if isinstance(loaded, dict) else 0
        self._oa_attachment_invoice_cache_path.write_text("{}", encoding="utf-8")
        return entry_count

    def import_session_exists(self, session_id: str) -> bool:
        if self._mongo_database is not None:
            return self._mongo_detailed_collections["file_import_sessions"].find_one({"_id": session_id}) is not None
        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            return False
        file_imports = self._load_local_pickle().get("file_imports", {})
        sessions = file_imports.get("sessions", {}) if isinstance(file_imports, dict) else {}
        return session_id in sessions

    def import_file_exists(self, file_id: str) -> bool:
        if self._mongo_database is not None:
            if self._mongo_detailed_collections["file_import_files"].find_one({"_id": file_id}) is not None:
                return True
            files_collection = self._mongo_database[f"{GRIDFS_BUCKET_NAME}.files"]
            return files_collection.find_one({"_id": file_id}) is not None
        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            return False
        file_imports = self._load_local_pickle().get("file_imports", {})
        sessions = file_imports.get("sessions", {}) if isinstance(file_imports, dict) else {}
        for session in sessions.values():
            files = session.get("files", []) if isinstance(session, dict) else []
            if any(isinstance(file, dict) and file.get("id") == file_id for file in files):
                return True
        return False

    def import_batch_exists(self, batch_id: str) -> bool:
        if self._mongo_database is not None:
            return self._mongo_detailed_collections["import_batches"].find_one({"_id": batch_id}) is not None
        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            return False
        imports = self._load_local_pickle().get("imports", {})
        batches = imports.get("batches", {}) if isinstance(imports, dict) else {}
        return batch_id in batches

    def invoice_exists(self, invoice_id: str) -> bool:
        if self._mongo_database is not None:
            return self._mongo_detailed_collections["invoices"].find_one({"_id": invoice_id}) is not None
        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            return False
        imports = self._load_local_pickle().get("imports", {})
        invoices = imports.get("invoices", []) if isinstance(imports, dict) else []
        return any(isinstance(invoice, dict) and invoice.get("id") == invoice_id for invoice in invoices)

    def transaction_exists(self, transaction_id: str) -> bool:
        if self._mongo_database is not None:
            return self._mongo_detailed_collections["bank_transactions"].find_one({"_id": transaction_id}) is not None
        if self._storage_mode == MONGO_ONLY_STORAGE_MODE:
            return False
        imports = self._load_local_pickle().get("imports", {})
        transactions = imports.get("transactions", []) if isinstance(imports, dict) else []
        return any(isinstance(transaction, dict) and transaction.get("id") == transaction_id for transaction in transactions)

    def _ensure_mongo_metadata(self) -> None:
        if self._mongo_meta_collection is None:
            return
        self._mongo_meta_collection.update_one(
            {"_id": META_DOCUMENT_ID},
            {
                "$setOnInsert": {
                    "schema_version": 2,
                    "storage_backend": "detailed_mongo_collections",
                    "state_collections": dict(STATE_COLLECTIONS),
                    "detailed_collections": {
                        "imports_meta": IMPORTS_META_COLLECTION,
                        "import_batches": IMPORT_BATCHES_COLLECTION,
                        "invoices": INVOICES_COLLECTION,
                        "bank_transactions": BANK_TRANSACTIONS_COLLECTION,
                        "file_imports_meta": FILE_IMPORTS_META_COLLECTION,
                        "file_import_sessions": FILE_IMPORT_SESSIONS_COLLECTION,
                        "file_import_files": FILE_IMPORT_FILES_COLLECTION,
                        "matching_meta": MATCHING_META_COLLECTION,
                        "matching_runs": MATCHING_RUNS_COLLECTION,
                        "matching_results": MATCHING_RESULTS_COLLECTION,
                        "workbench_overrides_meta": WORKBENCH_OVERRIDES_META_COLLECTION,
                        "workbench_row_overrides": WORKBENCH_ROW_OVERRIDES_COLLECTION,
                        "workbench_pair_relations_meta": WORKBENCH_PAIR_RELATIONS_META_COLLECTION,
                        "workbench_pair_relations": WORKBENCH_PAIR_RELATIONS_COLLECTION,
                        "workbench_read_models_meta": WORKBENCH_READ_MODELS_META_COLLECTION,
                        "workbench_read_models": WORKBENCH_READ_MODELS_COLLECTION,
                        "oa_attachment_invoice_cache": OA_ATTACHMENT_INVOICE_CACHE_COLLECTION,
                        "tax_certified_imports_meta": TAX_CERTIFIED_IMPORTS_META_COLLECTION,
                        "tax_certified_import_sessions": TAX_CERTIFIED_IMPORT_SESSIONS_COLLECTION,
                        "tax_certified_import_batches": TAX_CERTIFIED_IMPORT_BATCHES_COLLECTION,
                        "tax_certified_import_records": TAX_CERTIFIED_IMPORT_RECORDS_COLLECTION,
                    },
                    "file_metadata_collection": FILE_METADATA_COLLECTION,
                    "gridfs_bucket": GRIDFS_BUCKET_NAME,
                    "created_at": datetime.now(UTC),
                }
            },
            upsert=True,
        )

    def _load_detailed_mongo_payload(self) -> dict[str, Any]:
        if not self._mongo_detailed_collections:
            return {}

        imports_payload = self._load_imports_detailed_payload()
        file_imports_payload = self._load_file_imports_detailed_payload()
        matching_payload = self._load_matching_detailed_payload()
        workbench_overrides_payload = self._load_workbench_overrides_detailed_payload()
        workbench_pair_relations_payload = self._load_workbench_pair_relations_detailed_payload()
        workbench_read_models_payload = self._load_workbench_read_models_detailed_payload()
        found_any = any(
            bool(section)
            for section in (
                imports_payload,
                file_imports_payload,
                matching_payload,
                workbench_overrides_payload,
                workbench_pair_relations_payload,
                workbench_read_models_payload,
            )
        )
        if not found_any:
            return {}
        payload = {
            "imports": imports_payload or {},
            "file_imports": file_imports_payload or {},
            "matching": matching_payload or {},
        }
        if workbench_overrides_payload:
            payload["workbench_overrides"] = workbench_overrides_payload
        if workbench_pair_relations_payload:
            payload["workbench_pair_relations"] = workbench_pair_relations_payload
        if workbench_read_models_payload:
            payload["workbench_read_models"] = workbench_read_models_payload
        if self._migrate_legacy_file_refs_to_gridfs(payload):
            self.save(payload)
        return payload

    def _load_split_mongo_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        found_any = False
        for key, collection in self._mongo_state_collections.items():
            document = collection.find_one({"_id": STATE_DOCUMENT_ID})
            loaded = self._load_binary_payload(document)
            if isinstance(loaded, dict):
                payload[key] = loaded if isinstance(loaded, dict) else {}
                found_any = True
            else:
                payload[key] = {}
        return payload if found_any else {}

    def _load_legacy_mongo_payload(self) -> dict[str, Any]:
        if self._legacy_mongo_collection is None:
            return {}
        document = self._legacy_mongo_collection.find_one({"_id": STATE_DOCUMENT_ID})
        loaded = self._load_binary_payload(document)
        if isinstance(loaded, dict):
            return loaded if isinstance(loaded, dict) else {}
        return {}

    def _load_imports_detailed_payload(self) -> dict[str, Any]:
        meta_document = self._mongo_detailed_collections["imports_meta"].find_one({"_id": STATE_DOCUMENT_ID})
        meta_payload = self._load_binary_payload(meta_document)
        batches = self._load_entities_by_id(self._mongo_detailed_collections["import_batches"])
        invoices = self._load_entities_list(self._mongo_detailed_collections["invoices"])
        transactions = self._load_entities_list(self._mongo_detailed_collections["bank_transactions"])
        found_any = bool(meta_payload or batches or invoices or transactions)
        if not found_any:
            return {}
        payload = meta_payload if isinstance(meta_payload, dict) else {}
        payload["batches"] = batches
        payload["invoices"] = invoices
        payload["transactions"] = transactions
        return payload

    def _load_file_imports_detailed_payload(self) -> dict[str, Any]:
        meta_document = self._mongo_detailed_collections["file_imports_meta"].find_one({"_id": STATE_DOCUMENT_ID})
        meta_payload = self._load_binary_payload(meta_document)
        raw_sessions = self._load_entities_by_id(self._mongo_detailed_collections["file_import_sessions"])
        raw_file_documents = sorted(
            self._mongo_detailed_collections["file_import_files"].find({}),
            key=lambda item: str(item.get("_id", "")),
        )
        raw_files: list[tuple[str, Any]] = []
        for document in raw_file_documents:
            loaded = self._load_binary_payload(document)
            if loaded is None:
                continue
            session_id = str(document.get("session_id", ""))
            raw_files.append((session_id, loaded))
        found_any = bool(meta_payload or raw_sessions or raw_files)
        if not found_any:
            return {}

        files_by_session: dict[str, list[Any]] = {}
        for session_id, file_item in raw_files:
            if not session_id:
                continue
            files_by_session.setdefault(str(session_id), []).append(file_item)

        sessions: dict[str, Any] = {}
        for session_id, session in raw_sessions.items():
            files = sorted(
                files_by_session.get(str(session_id), []),
                key=lambda item: str(self._get_container_value(item, "id") or ""),
            )
            self._set_container_value(session, "files", files)
            self._set_container_value(session, "file_count", len(files))
            sessions[str(session_id)] = session

        payload = meta_payload if isinstance(meta_payload, dict) else {}
        payload["sessions"] = sessions
        return payload

    def _load_matching_detailed_payload(self) -> dict[str, Any]:
        meta_document = self._mongo_detailed_collections["matching_meta"].find_one({"_id": STATE_DOCUMENT_ID})
        meta_payload = self._load_binary_payload(meta_document)
        raw_runs = self._load_entities_by_id(self._mongo_detailed_collections["matching_runs"])
        raw_results = self._load_entities_list(self._mongo_detailed_collections["matching_results"])
        found_any = bool(meta_payload or raw_runs or raw_results)
        if not found_any:
            return {}

        results_by_run: dict[str, list[Any]] = {}
        result_map: dict[str, Any] = {}
        for result in raw_results:
            result_id = self._get_container_value(result, "id")
            run_id = self._get_container_value(result, "run_id")
            if result_id:
                result_map[str(result_id)] = result
            if run_id:
                results_by_run.setdefault(str(run_id), []).append(result)

        runs: dict[str, Any] = {}
        for run_id, run in raw_runs.items():
            run_results = sorted(
                results_by_run.get(str(run_id), []),
                key=lambda item: str(self._get_container_value(item, "id") or ""),
            )
            self._set_container_value(run, "results", run_results)
            runs[str(run_id)] = run

        payload = meta_payload if isinstance(meta_payload, dict) else {}
        payload["runs"] = runs
        payload["results"] = result_map
        return payload

    def _save_file_import_metadata(self, file_import_snapshot: Any, updated_at: datetime) -> None:
        if self._mongo_metadata_collection is None:
            return
        metadata_payload = self._extract_file_import_metadata(file_import_snapshot)
        self._mongo_metadata_collection.update_one(
            {"_id": STATE_DOCUMENT_ID},
            {
                "$set": {
                    "file_count": len(metadata_payload["files"]),
                    "payload": Binary(pickle.dumps(metadata_payload)),
                    "updated_at": updated_at,
                }
            },
            upsert=True,
        )

    def _save_imports_detailed(self, imports_snapshot: Any, updated_at: datetime) -> None:
        snapshot = imports_snapshot if isinstance(imports_snapshot, dict) else {}
        meta_payload = {
            key: value
            for key, value in snapshot.items()
            if key not in {"batches", "invoices", "transactions"}
        }
        batches = snapshot.get("batches", {})
        invoices = snapshot.get("invoices", [])
        transactions = snapshot.get("transactions", [])

        self._mongo_detailed_collections["imports_meta"].update_one(
            {"_id": STATE_DOCUMENT_ID},
            {
                "$set": {
                    **meta_payload,
                    "batch_count": len(batches) if isinstance(batches, dict) else 0,
                    "invoice_count": len(invoices) if isinstance(invoices, list) else 0,
                    "transaction_count": len(transactions) if isinstance(transactions, list) else 0,
                    "payload": Binary(pickle.dumps(meta_payload)),
                    "updated_at": updated_at,
                }
            },
            upsert=True,
        )

        batch_documents = []
        if isinstance(batches, dict):
            for batch_id, preview in batches.items():
                preview_payload = self._serialize_value(preview)
                batch_payload = self._get_container_value(preview, "batch")
                serialized_batch = self._serialize_value(batch_payload) if batch_payload is not None else {}
                batch_documents.append(
                    {
                        "_id": str(batch_id),
                        "batch_type": serialized_batch.get("batch_type"),
                        "source_name": serialized_batch.get("source_name"),
                        "imported_by": serialized_batch.get("imported_by"),
                        "row_count": serialized_batch.get("row_count"),
                        "success_count": serialized_batch.get("success_count"),
                        "error_count": serialized_batch.get("error_count"),
                        "status": serialized_batch.get("status"),
                        "imported_at": serialized_batch.get("imported_at"),
                        "payload": Binary(pickle.dumps(preview)),
                        "updated_at": updated_at,
                        "summary": preview_payload,
                    }
                )
        self._replace_collection_documents(self._mongo_detailed_collections["import_batches"], batch_documents)

        invoice_documents = []
        if isinstance(invoices, list):
            for invoice in invoices:
                serialized_invoice = self._serialize_value(invoice)
                invoice_documents.append(
                    {
                        "_id": str(self._get_container_value(invoice, "id")),
                        "invoice_type": serialized_invoice.get("invoice_type"),
                        "invoice_no": serialized_invoice.get("invoice_no"),
                        "invoice_code": serialized_invoice.get("invoice_code"),
                        "digital_invoice_no": serialized_invoice.get("digital_invoice_no"),
                        "invoice_date": serialized_invoice.get("invoice_date"),
                        "amount": serialized_invoice.get("amount"),
                        "signed_amount": serialized_invoice.get("signed_amount"),
                        "counterparty": serialized_invoice.get("counterparty"),
                        "source_batch_id": serialized_invoice.get("source_batch_id"),
                        "status": serialized_invoice.get("status"),
                        "payload": Binary(pickle.dumps(invoice)),
                        "updated_at": updated_at,
                    }
                )
        self._replace_collection_documents(self._mongo_detailed_collections["invoices"], invoice_documents)

        transaction_documents = []
        if isinstance(transactions, list):
            for transaction in transactions:
                serialized_transaction = self._serialize_value(transaction)
                transaction_documents.append(
                    {
                        "_id": str(self._get_container_value(transaction, "id")),
                        "account_no": serialized_transaction.get("account_no"),
                        "txn_direction": serialized_transaction.get("txn_direction"),
                        "counterparty_name_raw": serialized_transaction.get("counterparty_name_raw"),
                        "amount": serialized_transaction.get("amount"),
                        "signed_amount": serialized_transaction.get("signed_amount"),
                        "txn_date": serialized_transaction.get("txn_date"),
                        "trade_time": serialized_transaction.get("trade_time"),
                        "source_batch_id": serialized_transaction.get("source_batch_id"),
                        "status": serialized_transaction.get("status"),
                        "payload": Binary(pickle.dumps(transaction)),
                        "updated_at": updated_at,
                    }
                )
        self._replace_collection_documents(self._mongo_detailed_collections["bank_transactions"], transaction_documents)

    def _save_file_imports_detailed(self, file_import_snapshot: Any, updated_at: datetime) -> None:
        snapshot = file_import_snapshot if isinstance(file_import_snapshot, dict) else {}
        meta_payload = {
            key: value
            for key, value in snapshot.items()
            if key not in {"sessions"}
        }
        raw_sessions = snapshot.get("sessions", {})
        self._mongo_detailed_collections["file_imports_meta"].update_one(
            {"_id": STATE_DOCUMENT_ID},
            {
                "$set": {
                    **meta_payload,
                    "session_count": len(raw_sessions) if isinstance(raw_sessions, dict) else 0,
                    "payload": Binary(pickle.dumps(meta_payload)),
                    "updated_at": updated_at,
                }
            },
            upsert=True,
        )

        session_documents = []
        file_documents = []
        if isinstance(raw_sessions, dict):
            for session_id, session in raw_sessions.items():
                serialized_session = self._serialize_value(session)
                session_documents.append(
                    {
                        "_id": str(session_id),
                        "imported_by": serialized_session.get("imported_by"),
                        "status": serialized_session.get("status"),
                        "file_count": serialized_session.get("file_count"),
                        "created_at": serialized_session.get("created_at"),
                        "payload": Binary(pickle.dumps(session)),
                        "updated_at": updated_at,
                    }
                )
                files = self._get_container_value(session, "files")
                if not isinstance(files, list):
                    continue
                for file_item in files:
                    serialized_file = self._serialize_value(file_item)
                    file_documents.append(
                        {
                            "_id": str(self._get_container_value(file_item, "id")),
                            "session_id": str(session_id),
                            "file_name": serialized_file.get("file_name"),
                            "status": serialized_file.get("status"),
                            "template_code": serialized_file.get("template_code"),
                            "batch_type": serialized_file.get("batch_type"),
                            "stored_file_path": serialized_file.get("stored_file_path"),
                            "preview_batch_id": serialized_file.get("preview_batch_id"),
                            "batch_id": serialized_file.get("batch_id"),
                            "payload": Binary(pickle.dumps(file_item)),
                            "updated_at": updated_at,
                        }
                    )

        self._replace_collection_documents(self._mongo_detailed_collections["file_import_sessions"], session_documents)
        self._replace_collection_documents(self._mongo_detailed_collections["file_import_files"], file_documents)

    def _save_matching_detailed(self, matching_snapshot: Any, updated_at: datetime) -> None:
        snapshot = matching_snapshot if isinstance(matching_snapshot, dict) else {}
        meta_payload = {
            key: value
            for key, value in snapshot.items()
            if key not in {"runs", "results"}
        }
        raw_runs = snapshot.get("runs", {})
        raw_results = snapshot.get("results", {})
        self._mongo_detailed_collections["matching_meta"].update_one(
            {"_id": STATE_DOCUMENT_ID},
            {
                "$set": {
                    **meta_payload,
                    "run_count": len(raw_runs) if isinstance(raw_runs, dict) else 0,
                    "result_count": len(raw_results) if isinstance(raw_results, dict) else 0,
                    "payload": Binary(pickle.dumps(meta_payload)),
                    "updated_at": updated_at,
                }
            },
            upsert=True,
        )

        run_documents = []
        if isinstance(raw_runs, dict):
            for run_id, run in raw_runs.items():
                serialized_run = self._serialize_value(run)
                run_documents.append(
                    {
                        "_id": str(run_id),
                        "triggered_by": serialized_run.get("triggered_by"),
                        "invoice_count": serialized_run.get("invoice_count"),
                        "transaction_count": serialized_run.get("transaction_count"),
                        "executed_at": serialized_run.get("executed_at"),
                        "result_count": len(serialized_run.get("results", []) or []),
                        "payload": Binary(pickle.dumps(run)),
                        "updated_at": updated_at,
                    }
                )

        result_documents = []
        if isinstance(raw_results, dict):
            for result_id, result in raw_results.items():
                serialized_result = self._serialize_value(result)
                result_documents.append(
                    {
                        "_id": str(result_id),
                        "run_id": serialized_result.get("run_id"),
                        "result_type": serialized_result.get("result_type"),
                        "confidence": serialized_result.get("confidence"),
                        "rule_code": serialized_result.get("rule_code"),
                        "amount": serialized_result.get("amount"),
                        "difference_amount": serialized_result.get("difference_amount"),
                        "counterparty_name": serialized_result.get("counterparty_name"),
                        "invoice_ids": serialized_result.get("invoice_ids"),
                        "transaction_ids": serialized_result.get("transaction_ids"),
                        "payload": Binary(pickle.dumps(result)),
                        "updated_at": updated_at,
                    }
                )

        self._replace_collection_documents(self._mongo_detailed_collections["matching_runs"], run_documents)
        self._replace_collection_documents(self._mongo_detailed_collections["matching_results"], result_documents)

    def _load_workbench_overrides_detailed_payload(self) -> dict[str, Any]:
        meta_document = self._mongo_detailed_collections["workbench_overrides_meta"].find_one({"_id": STATE_DOCUMENT_ID})
        meta_payload = self._load_binary_payload(meta_document)
        row_overrides = self._load_entities_by_id(self._mongo_detailed_collections["workbench_row_overrides"])
        if not meta_payload and not row_overrides:
            return {}

        payload = meta_payload if isinstance(meta_payload, dict) else {}
        payload["row_overrides"] = row_overrides
        return payload

    def _load_workbench_pair_relations_detailed_payload(self) -> dict[str, Any]:
        meta_document = self._mongo_detailed_collections["workbench_pair_relations_meta"].find_one(
            {"_id": STATE_DOCUMENT_ID}
        )
        meta_payload = self._load_binary_payload(meta_document)
        pair_relations = self._load_entities_by_id(self._mongo_detailed_collections["workbench_pair_relations"])
        if not meta_payload and not pair_relations:
            return {}

        payload = meta_payload if isinstance(meta_payload, dict) else {}
        payload["pair_relations"] = pair_relations
        return payload

    def _load_workbench_read_models_detailed_payload(self) -> dict[str, Any]:
        meta_document = self._mongo_detailed_collections["workbench_read_models_meta"].find_one({"_id": STATE_DOCUMENT_ID})
        meta_payload = self._load_binary_payload(meta_document)
        read_models = self._load_entities_by_id(self._mongo_detailed_collections["workbench_read_models"])
        if not meta_payload and not read_models:
            return {}

        payload = meta_payload if isinstance(meta_payload, dict) else {}
        payload["read_models"] = read_models
        return payload

    def _save_workbench_overrides_detailed(self, workbench_overrides_snapshot: Any, updated_at: datetime) -> None:
        snapshot = workbench_overrides_snapshot if isinstance(workbench_overrides_snapshot, dict) else {}
        meta_payload = {
            key: value
            for key, value in snapshot.items()
            if key not in {"row_overrides"}
        }
        row_overrides = snapshot.get("row_overrides", {})
        self._mongo_detailed_collections["workbench_overrides_meta"].update_one(
            {"_id": STATE_DOCUMENT_ID},
            {
                "$set": {
                    **meta_payload,
                    "row_override_count": len(row_overrides) if isinstance(row_overrides, dict) else 0,
                    "payload": Binary(pickle.dumps(meta_payload)),
                    "updated_at": updated_at,
                }
            },
            upsert=True,
        )

        override_documents = []
        if isinstance(row_overrides, dict):
            for row_id, override in row_overrides.items():
                override_documents.append(
                    {
                        "_id": str(row_id),
                        "payload": Binary(pickle.dumps(override)),
                        "updated_at": updated_at,
                    }
                )
        self._replace_collection_documents(self._mongo_detailed_collections["workbench_row_overrides"], override_documents)

    def _save_workbench_overrides_detailed_incremental(
        self,
        workbench_overrides_snapshot: Any,
        updated_at: datetime,
        changed_row_ids: list[str],
    ) -> None:
        snapshot = workbench_overrides_snapshot if isinstance(workbench_overrides_snapshot, dict) else {}
        meta_payload = {
            key: value
            for key, value in snapshot.items()
            if key not in {"row_overrides"}
        }
        row_overrides = snapshot.get("row_overrides", {})
        self._mongo_detailed_collections["workbench_overrides_meta"].update_one(
            {"_id": STATE_DOCUMENT_ID},
            {
                "$set": {
                    **meta_payload,
                    "row_override_count": len(row_overrides) if isinstance(row_overrides, dict) else 0,
                    "payload": Binary(pickle.dumps(meta_payload)),
                    "updated_at": updated_at,
                }
            },
            upsert=True,
        )

        collection = self._mongo_detailed_collections["workbench_row_overrides"]
        if not isinstance(row_overrides, dict):
            row_overrides = {}
        for row_id in {str(value) for value in changed_row_ids}:
            override = row_overrides.get(row_id)
            if isinstance(override, dict):
                collection.replace_one(
                    {"_id": row_id},
                    {
                        "_id": row_id,
                        "payload": Binary(pickle.dumps(override)),
                        "updated_at": updated_at,
                    },
                    upsert=True,
                )
            else:
                collection.delete_many({"_id": row_id})

    def _save_workbench_pair_relations_detailed(
        self,
        snapshot: dict[str, Any],
        updated_at: datetime,
        *,
        changed_case_ids: list[str] | None = None,
    ) -> None:
        meta_payload = {
            key: value
            for key, value in snapshot.items()
            if key not in {"pair_relations"}
        }
        pair_relations = snapshot.get("pair_relations", {})
        collection = self._mongo_detailed_collections["workbench_pair_relations"]
        if changed_case_ids is not None:
            normalized_case_ids = {str(case_id) for case_id in changed_case_ids if str(case_id)}
            for case_id in normalized_case_ids:
                relation = pair_relations.get(case_id) if isinstance(pair_relations, dict) else None
                if isinstance(relation, dict):
                    serialized_relation = self._serialize_value(relation)
                    collection.replace_one(
                        {"_id": case_id},
                        {
                            "_id": case_id,
                            "case_id": serialized_relation.get("case_id"),
                            "row_ids": serialized_relation.get("row_ids"),
                            "row_types": serialized_relation.get("row_types"),
                            "status": serialized_relation.get("status"),
                            "relation_mode": serialized_relation.get("relation_mode"),
                            "month_scope": serialized_relation.get("month_scope"),
                            "created_by": serialized_relation.get("created_by"),
                            "created_at": serialized_relation.get("created_at"),
                            "updated_at": serialized_relation.get("updated_at"),
                            "payload": Binary(pickle.dumps(relation)),
                        },
                        upsert=True,
                    )
                else:
                    collection.delete_many({"_id": case_id})
            self._mongo_detailed_collections["workbench_pair_relations_meta"].update_one(
                {"_id": STATE_DOCUMENT_ID},
                {
                    "$set": {
                        **meta_payload,
                        "pair_relation_count": collection.count_documents({}),
                        "payload": Binary(pickle.dumps(meta_payload)),
                        "updated_at": updated_at,
                    }
                },
                upsert=True,
            )
            return

        relation_documents = []
        if isinstance(pair_relations, dict):
            for case_id, relation in pair_relations.items():
                serialized_relation = self._serialize_value(relation)
                relation_documents.append(
                    {
                        "_id": str(case_id),
                        "case_id": serialized_relation.get("case_id"),
                        "row_ids": serialized_relation.get("row_ids"),
                        "row_types": serialized_relation.get("row_types"),
                        "status": serialized_relation.get("status"),
                        "relation_mode": serialized_relation.get("relation_mode"),
                        "month_scope": serialized_relation.get("month_scope"),
                        "created_by": serialized_relation.get("created_by"),
                        "created_at": serialized_relation.get("created_at"),
                        "updated_at": serialized_relation.get("updated_at"),
                        "payload": Binary(pickle.dumps(relation)),
                    }
                )
        self._replace_collection_documents(collection, relation_documents)
        self._mongo_detailed_collections["workbench_pair_relations_meta"].update_one(
            {"_id": STATE_DOCUMENT_ID},
            {
                "$set": {
                    **meta_payload,
                    "pair_relation_count": len(pair_relations) if isinstance(pair_relations, dict) else 0,
                    "payload": Binary(pickle.dumps(meta_payload)),
                    "updated_at": updated_at,
                }
            },
            upsert=True,
        )

    def _save_workbench_read_models_detailed(
        self,
        snapshot: dict[str, Any],
        updated_at: datetime,
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        meta_payload = {
            key: value
            for key, value in snapshot.items()
            if key not in {"read_models"}
        }
        read_models = snapshot.get("read_models", {})
        collection = self._mongo_detailed_collections["workbench_read_models"]
        if changed_scope_keys is not None:
            normalized_scope_keys = {str(scope_key) for scope_key in changed_scope_keys if str(scope_key)}
            for scope_key in normalized_scope_keys:
                read_model = read_models.get(scope_key) if isinstance(read_models, dict) else None
                if isinstance(read_model, dict):
                    serialized_read_model = self._serialize_value(read_model)
                    collection.replace_one(
                        {"_id": scope_key},
                        {
                            "_id": str(scope_key),
                            "scope_key": serialized_read_model.get("scope_key"),
                            "scope_type": serialized_read_model.get("scope_type"),
                            "generated_at": serialized_read_model.get("generated_at"),
                            "payload": Binary(pickle.dumps(read_model)),
                            "updated_at": updated_at,
                        },
                        upsert=True,
                    )
                else:
                    collection.delete_many({"_id": scope_key})
            self._mongo_detailed_collections["workbench_read_models_meta"].update_one(
                {"_id": STATE_DOCUMENT_ID},
                {
                    "$set": {
                        **meta_payload,
                        "read_model_count": collection.count_documents({}),
                        "payload": Binary(pickle.dumps(meta_payload)),
                        "updated_at": updated_at,
                    }
                },
                upsert=True,
            )
            return

        read_model_documents = []
        if isinstance(read_models, dict):
            for scope_key, read_model in read_models.items():
                serialized_read_model = self._serialize_value(read_model)
                read_model_documents.append(
                    {
                        "_id": str(scope_key),
                        "scope_key": serialized_read_model.get("scope_key"),
                        "scope_type": serialized_read_model.get("scope_type"),
                        "generated_at": serialized_read_model.get("generated_at"),
                        "payload": Binary(pickle.dumps(read_model)),
                        "updated_at": updated_at,
                    }
                )
        self._replace_collection_documents(collection, read_model_documents)
        self._mongo_detailed_collections["workbench_read_models_meta"].update_one(
            {"_id": STATE_DOCUMENT_ID},
            {
                "$set": {
                    **meta_payload,
                    "read_model_count": len(read_models) if isinstance(read_models, dict) else 0,
                    "payload": Binary(pickle.dumps(meta_payload)),
                    "updated_at": updated_at,
                }
            },
            upsert=True,
        )

    def _save_tax_certified_imports_detailed(self, snapshot: dict[str, Any], updated_at: datetime) -> None:
        meta_payload = {
            key: value
            for key, value in snapshot.items()
            if key not in {"sessions", "batches", "records"}
        }
        sessions = snapshot.get("sessions", {})
        batches = snapshot.get("batches", {})
        records = snapshot.get("records", {})

        self._mongo_detailed_collections["tax_certified_imports_meta"].update_one(
            {"_id": STATE_DOCUMENT_ID},
            {
                "$set": {
                    **meta_payload,
                    "session_count": len(sessions) if isinstance(sessions, dict) else 0,
                    "batch_count": len(batches) if isinstance(batches, dict) else 0,
                    "record_count": len(records) if isinstance(records, dict) else 0,
                    "payload": Binary(pickle.dumps(meta_payload)),
                    "updated_at": updated_at,
                }
            },
            upsert=True,
        )

        session_documents = []
        if isinstance(sessions, dict):
            for session_id, session in sessions.items():
                serialized_session = self._serialize_value(session)
                session_documents.append(
                    {
                        "_id": str(session_id),
                        "imported_by": serialized_session.get("imported_by"),
                        "status": serialized_session.get("status"),
                        "file_count": serialized_session.get("file_count"),
                        "created_at": serialized_session.get("created_at"),
                        "payload": Binary(pickle.dumps(session)),
                        "updated_at": updated_at,
                    }
                )

        batch_documents = []
        if isinstance(batches, dict):
            for batch_id, batch in batches.items():
                serialized_batch = self._serialize_value(batch)
                batch_documents.append(
                    {
                        "_id": str(batch_id),
                        "session_id": serialized_batch.get("session_id"),
                        "imported_by": serialized_batch.get("imported_by"),
                        "file_count": serialized_batch.get("file_count"),
                        "months": serialized_batch.get("months"),
                        "persisted_record_count": serialized_batch.get("persisted_record_count"),
                        "created_at": serialized_batch.get("created_at"),
                        "payload": Binary(pickle.dumps(batch)),
                        "updated_at": updated_at,
                    }
                )

        record_documents = []
        if isinstance(records, dict):
            for record_id, record in records.items():
                serialized_record = self._serialize_value(record)
                record_documents.append(
                    {
                        "_id": str(record_id),
                        "month": serialized_record.get("month"),
                        "invoice_no": serialized_record.get("invoice_no"),
                        "digital_invoice_no": serialized_record.get("digital_invoice_no"),
                        "invoice_code": serialized_record.get("invoice_code"),
                        "seller_tax_no": serialized_record.get("seller_tax_no"),
                        "seller_name": serialized_record.get("seller_name"),
                        "issue_date": serialized_record.get("issue_date"),
                        "tax_amount": serialized_record.get("tax_amount"),
                        "selection_status": serialized_record.get("selection_status"),
                        "invoice_status": serialized_record.get("invoice_status"),
                        "source_file_name": serialized_record.get("source_file_name"),
                        "source_row_number": serialized_record.get("source_row_number"),
                        "payload": Binary(pickle.dumps(record)),
                        "updated_at": updated_at,
                    }
                )

        self._replace_collection_documents(self._mongo_detailed_collections["tax_certified_import_sessions"], session_documents)
        self._replace_collection_documents(self._mongo_detailed_collections["tax_certified_import_batches"], batch_documents)
        self._replace_collection_documents(self._mongo_detailed_collections["tax_certified_import_records"], record_documents)

    def _extract_file_import_metadata(self, file_import_snapshot: Any) -> dict[str, Any]:
        sessions_by_id = {}
        files: list[dict[str, Any]] = []

        if isinstance(file_import_snapshot, dict):
            raw_sessions = file_import_snapshot.get("sessions", {})
            if isinstance(raw_sessions, dict):
                for session_id, session in raw_sessions.items():
                    session_payload = self._serialize_value(session)
                    files_in_session = session_payload.get("files", []) if isinstance(session_payload, dict) else []
                    sessions_by_id[str(session_id)] = {
                        "id": str(session_id),
                        "imported_by": session_payload.get("imported_by"),
                        "status": session_payload.get("status"),
                        "file_count": session_payload.get("file_count"),
                        "created_at": session_payload.get("created_at"),
                    }
                    if isinstance(files_in_session, list):
                        for file_payload in files_in_session:
                            if not isinstance(file_payload, dict):
                                continue
                            files.append(
                                {
                                    "session_id": str(session_id),
                                    "file_id": file_payload.get("id"),
                                    "file_name": file_payload.get("file_name"),
                                    "status": file_payload.get("status"),
                                    "template_code": file_payload.get("template_code"),
                                    "batch_type": file_payload.get("batch_type"),
                                    "stored_file_path": file_payload.get("stored_file_path"),
                                    "preview_batch_id": file_payload.get("preview_batch_id"),
                                    "batch_id": file_payload.get("batch_id"),
                                }
                            )

        return {
            "sessions": list(sessions_by_id.values()),
            "files": files,
        }

    def _replace_collection_documents(self, collection: Any, documents: list[dict[str, Any]]) -> None:
        collection.delete_many({})
        for document in documents:
            collection.replace_one({"_id": document["_id"]}, document, upsert=True)

    def _load_entities_by_id(self, collection: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        documents = sorted(collection.find({}), key=lambda item: str(item.get("_id", "")))
        for document in documents:
            loaded = self._load_binary_payload(document)
            if loaded is None:
                continue
            payload[str(document["_id"])] = loaded
        return payload

    def _load_entities_list(self, collection: Any) -> list[Any]:
        payload: list[Any] = []
        documents = sorted(collection.find({}), key=lambda item: str(item.get("_id", "")))
        for document in documents:
            loaded = self._load_binary_payload(document)
            if loaded is None:
                continue
            payload.append(loaded)
        return payload

    @staticmethod
    def _load_binary_payload(document: dict[str, Any] | None) -> Any | None:
        if not isinstance(document, dict):
            return None
        raw_payload = document.get("payload")
        if isinstance(raw_payload, dict):
            return raw_payload
        if isinstance(raw_payload, (Binary, bytes, bytearray)):
            return pickle.loads(bytes(raw_payload))  # noqa: S301 - trusted app state
        return None

    def _clear_legacy_snapshot_collections(self) -> None:
        if self._legacy_mongo_collection is not None:
            self._legacy_mongo_collection.delete_many({})
        for collection in self._mongo_state_collections.values():
            collection.delete_many({})

    @staticmethod
    def _has_non_empty_state(payload: dict[str, Any]) -> bool:
        return any(
            bool(payload.get(key))
            for key in (
                "imports",
                "file_imports",
                "matching",
                "workbench_overrides",
                "workbench_pair_relations",
                "workbench_read_models",
            )
        )

    def _load_local_pickle(self) -> dict[str, Any]:
        if not self._legacy_state_path.exists():
            return {}
        with self._legacy_state_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def _migrate_legacy_file_refs_to_gridfs(self, payload: dict[str, Any]) -> bool:
        if self._mongo_file_bucket is None:
            return False
        file_import_snapshot = payload.get("file_imports")
        if not isinstance(file_import_snapshot, dict):
            return False

        migrated_any = False
        raw_sessions = file_import_snapshot.get("sessions", {})
        if not isinstance(raw_sessions, dict):
            return False
        for session_id, session_payload in raw_sessions.items():
            files = self._get_container_value(session_payload, "files")
            if not isinstance(files, list):
                continue
            for file_payload in files:
                stored_file_path = self._get_container_value(file_payload, "stored_file_path")
                file_id = self._get_container_value(file_payload, "id")
                file_name = self._get_container_value(file_payload, "file_name")
                if not stored_file_path or not file_id or not file_name:
                    continue
                if self._is_gridfs_ref(str(stored_file_path)):
                    continue
                source_path = Path(str(stored_file_path))
                if not source_path.exists():
                    raise RuntimeError(f"Legacy import file is missing and cannot be migrated: {source_path}")
                migrated_ref = self.store_import_file(
                    session_id=str(session_id),
                    file_id=str(file_id),
                    file_name=str(file_name),
                    content=source_path.read_bytes(),
                )
                self._set_container_value(file_payload, "stored_file_path", migrated_ref)
                source_path.unlink(missing_ok=True)
                migrated_any = True
        return migrated_any

    @staticmethod
    def _get_container_value(container: Any, key: str) -> Any:
        if isinstance(container, dict):
            return container.get(key)
        return getattr(container, key, None)

    @staticmethod
    def _set_container_value(container: Any, key: str, value: Any) -> None:
        if isinstance(container, dict):
            container[key] = value
            return
        setattr(container, key, value)

    @staticmethod
    def _build_gridfs_ref(file_id: str, file_name: str) -> str:
        return f"{GRIDFS_REF_PREFIX}{file_id}/{file_name}"

    @staticmethod
    def _is_gridfs_ref(value: str) -> bool:
        return value.startswith(GRIDFS_REF_PREFIX)

    @staticmethod
    def _parse_gridfs_ref(value: str) -> str:
        raw = value[len(GRIDFS_REF_PREFIX) :]
        file_id, _, _ = raw.partition("/")
        if not file_id:
            raise ValueError("Invalid GridFS stored file reference.")
        return file_id

    @staticmethod
    def _sanitize_name(file_name: str) -> str:
        cleaned = FILENAME_SAFE_RE.sub("_", file_name).strip("._")
        return cleaned or "uploaded_file"

    def _serialize_value(self, value: Any) -> Any:
        if hasattr(value, "__dataclass_fields__"):
            return {
                key: self._serialize_value(getattr(value, key))
                for key in value.__dataclass_fields__  # type: ignore[attr-defined]
            }
        if isinstance(value, dict):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        return value
