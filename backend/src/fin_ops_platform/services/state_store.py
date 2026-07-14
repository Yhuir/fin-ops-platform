from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
import pickle
import re
from threading import RLock
from typing import Any

from fin_ops_platform.services.runtime_paths import default_data_dir as _default_data_dir


FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
GRIDFS_REF_PREFIX = "gridfs://"
BANK_FLOW_RULE_BATCH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")


def _base_read_model_scope_key(scope_key: object) -> str:
    normalized = str(scope_key or "").strip()
    if normalized.startswith("visibility:"):
        return normalized.rsplit(":", 1)[-1].strip() or "all"
    return normalized or "all"


def _bank_flow_rule_batch_month_scopes(scope_keys: object) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    iterable = sorted(scope_keys) if isinstance(scope_keys, set) else scope_keys
    for scope_key in iterable if isinstance(iterable, (list, tuple, set)) else []:
        base_scope_key = _base_read_model_scope_key(scope_key)
        if not BANK_FLOW_RULE_BATCH_SCOPE_RE.match(base_scope_key) or base_scope_key in seen:
            continue
        ordered.append(base_scope_key)
        seen.add(base_scope_key)
    return ordered


class ApplicationStateStore:
    def __init__(self, data_dir: Path | None = None, *, read_only: bool = False) -> None:
        root = data_dir or _default_data_dir()
        self._data_dir = root
        self._legacy_state_path = root / "state.pkl"
        self._import_file_root = root / "import_files"
        self._app_settings_path = root / "app_settings.json"
        self._oa_attachment_invoice_cache_path = root / "oa_attachment_invoice_cache.json"
        self._oa_sync_state_path = root / "oa_sync_state.pkl"
        self._manual_oa_imports_path = root / "manual_oa_imports.json"
        self._tax_certified_imports_path = root / "tax_certified_imports.pkl"
        self._tax_offset_plans_path = root / "tax_offset_plans.pkl"
        self._etc_state_path = root / "etc" / "etc_state.pkl"
        self._etc_invoice_file_root = root / "etc" / "invoice_attachments"
        self._etc_reconciliation_state_path = root / "etc_reconciliation" / "tasks.pkl"
        self._etc_reconciliation_file_root = root / "etc_reconciliation" / "files"
        self._historical_etc_repair_root = root / "historical_etc_repair"
        self._historical_etc_repair_bundles_path = self._historical_etc_repair_root / "bundles.json"
        self._historical_etc_repair_parsed_seeds_path = self._historical_etc_repair_root / "parsed_seeds.json"
        self._historical_etc_repair_states_path = self._historical_etc_repair_root / "states.json"
        self._background_jobs_path = root / "background_jobs.pkl"
        self._app_health_alerts_path = root / "app_health_alerts.pkl"
        self._no_oa_bank_batches_path = root / "no_oa_bank_batches.pkl"
        self._bank_flow_rule_batches_path = root / "bank_flow_rule_batches.pkl"
        self._local_pickle_lock = RLock()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._storage_mode = "local_pickle"
        self._read_only = read_only
        self._import_file_root.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def storage_backend(self) -> str:
        return "local_pickle"

    @property
    def storage_mode(self) -> str:
        return self._storage_mode

    @property
    def mongo_database_name(self) -> str | None:
        return None

    def load_app_settings(self) -> dict[str, Any]:
        default_payload = {
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
            "pending_output_invoice_tag_groups": {},
            "bank_flow_rule_batch_tag_rules": {},
            "cost_statistics_tag_selection": {},
            "input_invoice_usage_payment_status_rules": {},
        }
        if not self._app_settings_path.exists():
            return default_payload
        try:
            loaded = json.loads(self._app_settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default_payload
        if not isinstance(loaded, dict):
            return default_payload
        normalized_payload = {
            "completed_project_ids": list(loaded.get("completed_project_ids") or []),
            "manual_projects": list(loaded.get("manual_projects") or []),
            "synced_projects": list(loaded.get("synced_projects") or []),
            "bank_account_mappings": list(loaded.get("bank_account_mappings") or []),
            "allowed_usernames": list(loaded.get("allowed_usernames") or []),
            "readonly_export_usernames": list(loaded.get("readonly_export_usernames") or []),
            "admin_usernames": list(loaded.get("admin_usernames") or []),
            "workbench_column_layouts": dict(loaded.get("workbench_column_layouts") or {}),
            "oa_retention": dict(loaded.get("oa_retention") or {}),
            "oa_import": dict(loaded.get("oa_import") or {}),
            "oa_invoice_offset": dict(loaded.get("oa_invoice_offset") or {}),
            "bank_transaction_tags": dict(loaded.get("bank_transaction_tags") or {}),
            "pending_invoice_tag_groups": dict(loaded.get("pending_invoice_tag_groups") or {}),
            "pending_output_invoice_tag_groups": dict(loaded.get("pending_output_invoice_tag_groups") or {}),
            "bank_flow_rule_batch_tag_rules": dict(loaded.get("bank_flow_rule_batch_tag_rules") or {}),
            "cost_statistics_tag_selection": dict(loaded.get("cost_statistics_tag_selection") or {}),
            "input_invoice_usage_payment_status_rules": dict(
                loaded.get("input_invoice_usage_payment_status_rules") or {}
            ),
        }
        if "no_oa_bank_batch_tag_selection" in loaded:
            normalized_payload["no_oa_bank_batch_tag_selection"] = dict(
                loaded.get("no_oa_bank_batch_tag_selection") or {}
            )
        if "turnover_ledger_tag_selection" in loaded:
            normalized_payload["turnover_ledger_tag_selection"] = dict(
                loaded.get("turnover_ledger_tag_selection") or {}
            )
        return normalized_payload

    def save_app_settings(self, payload: dict[str, Any]) -> None:
        normalized_payload = {
            "completed_project_ids": list(payload.get("completed_project_ids") or []),
            "manual_projects": list(payload.get("manual_projects") or []),
            "synced_projects": list(payload.get("synced_projects") or []),
            "bank_account_mappings": list(payload.get("bank_account_mappings") or []),
            "allowed_usernames": list(payload.get("allowed_usernames") or []),
            "readonly_export_usernames": list(payload.get("readonly_export_usernames") or []),
            "admin_usernames": list(payload.get("admin_usernames") or []),
            "workbench_column_layouts": dict(payload.get("workbench_column_layouts") or {}),
            "oa_retention": dict(payload.get("oa_retention") or {}),
            "oa_import": dict(payload.get("oa_import") or {}),
            "oa_invoice_offset": dict(payload.get("oa_invoice_offset") or {}),
            "bank_transaction_tags": dict(payload.get("bank_transaction_tags") or {}),
            "pending_invoice_tag_groups": dict(payload.get("pending_invoice_tag_groups") or {}),
            "pending_output_invoice_tag_groups": dict(payload.get("pending_output_invoice_tag_groups") or {}),
            "bank_flow_rule_batch_tag_rules": dict(payload.get("bank_flow_rule_batch_tag_rules") or {}),
            "cost_statistics_tag_selection": dict(payload.get("cost_statistics_tag_selection") or {}),
            "input_invoice_usage_payment_status_rules": dict(
                payload.get("input_invoice_usage_payment_status_rules") or {}
            ),
        }
        if "no_oa_bank_batch_tag_selection" in payload:
            normalized_payload["no_oa_bank_batch_tag_selection"] = dict(
                payload.get("no_oa_bank_batch_tag_selection") or {}
            )
        if "turnover_ledger_tag_selection" in payload:
            normalized_payload["turnover_ledger_tag_selection"] = dict(
                payload.get("turnover_ledger_tag_selection") or {}
            )
        self._app_settings_path.write_text(
            json.dumps(normalized_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_oa_attachment_invoice_cache_entry(self, cache_key: str) -> dict[str, object] | None:
        normalized_cache_key = str(cache_key).strip()
        if not normalized_cache_key:
            return None
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

    def load_oa_sync_state(self) -> dict[str, Any]:
        if not self._oa_sync_state_path.exists():
            return {}
        try:
            with self._oa_sync_state_path.open("rb") as handle:
                loaded = pickle.load(handle)  # noqa: S301 - local app state file.
        except (FileNotFoundError, pickle.PickleError, EOFError):
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}

    def save_oa_sync_state(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = dict(snapshot if isinstance(snapshot, dict) else {})
        with self._oa_sync_state_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def load_manual_oa_imports(self) -> dict[str, object]:
        if not self._manual_oa_imports_path.exists():
            return self._normalize_manual_oa_imports({})
        try:
            loaded = json.loads(self._manual_oa_imports_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return self._normalize_manual_oa_imports({})
        return self._normalize_manual_oa_imports(loaded)

    def save_manual_oa_imports(self, payload: dict[str, object]) -> None:
        normalized_payload = self._normalize_manual_oa_imports(payload)
        self._manual_oa_imports_path.write_text(
            json.dumps(normalized_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_manual_oa_imports(
        self,
        row_ids: list[str],
        actor_id: str,
        audit: dict[str, object],
    ) -> dict[str, object]:
        payload = self.load_manual_oa_imports()
        entries = dict(payload.get("entries") or {})
        imported: list[str] = []
        already_imported: list[str] = []
        now = datetime.now(UTC).isoformat()
        normalized_actor_id = str(actor_id or "").strip() or "system"
        for row_id in self._dedupe_text_values(row_ids):
            if row_id in entries:
                already_imported.append(row_id)
                continue
            entries[row_id] = {
                "row_id": row_id,
                "source": "manual_oa_import",
                "actor_id": normalized_actor_id,
                "imported_at": now,
                "audit": self._serialize_value(dict(audit if isinstance(audit, dict) else {})),
            }
            imported.append(row_id)
        payload["entries"] = entries
        payload["row_ids"] = sorted(entries)
        payload.setdefault("audit_log", [])
        audit_log = list(payload.get("audit_log") or [])
        audit_log.append(
            {
                "operation": "import",
                "actor_id": normalized_actor_id,
                "row_ids": self._dedupe_text_values(row_ids),
                "imported": list(imported),
                "already_imported": list(already_imported),
                "audit": self._serialize_value(dict(audit if isinstance(audit, dict) else {})),
                "created_at": now,
            }
        )
        payload["audit_log"] = audit_log
        self.save_manual_oa_imports(payload)
        return {
            "imported": imported,
            "already_imported": already_imported,
            "entries": dict(entries),
            "row_ids": sorted(entries),
        }

    def remove_manual_oa_import(self, row_id: str, actor_id: str) -> bool:
        normalized_row_id = str(row_id or "").strip()
        if not normalized_row_id:
            return False
        payload = self.load_manual_oa_imports()
        entries = dict(payload.get("entries") or {})
        removed = entries.pop(normalized_row_id, None) is not None
        payload["entries"] = entries
        payload["row_ids"] = sorted(entries)
        audit_log = list(payload.get("audit_log") or [])
        audit_log.append(
            {
                "operation": "remove",
                "actor_id": str(actor_id or "").strip() or "system",
                "row_ids": [normalized_row_id],
                "removed": removed,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        payload["audit_log"] = audit_log
        self.save_manual_oa_imports(payload)
        return removed

    def load_tax_certified_imports(self) -> dict[str, Any]:
        if not self._tax_certified_imports_path.exists():
            return {}
        with self._tax_certified_imports_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def save_tax_certified_imports(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        with self._tax_certified_imports_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def save_tax_offset_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        normalized_plan = plan if isinstance(plan, dict) else {}
        current_payload = self._load_tax_offset_plans()
        plans = dict(current_payload.get("plans") if isinstance(current_payload.get("plans"), dict) else {})
        idempotency_index = {
            str(existing.get("idempotency_key")): str(existing_plan_id)
            for existing_plan_id, existing in plans.items()
            if isinstance(existing, dict) and existing.get("idempotency_key")
        }
        idempotency_key = str(normalized_plan.get("idempotency_key") or "").strip()
        if idempotency_key and idempotency_key in idempotency_index:
            return dict(plans[idempotency_index[idempotency_key]])
        plan_id = str(normalized_plan.get("id") or "").strip()
        if not plan_id:
            raise ValueError("tax offset plan id is required.")
        plans[plan_id] = normalized_plan
        with self._tax_offset_plans_path.open("wb") as handle:
            pickle.dump({"plans": plans}, handle)
        return dict(normalized_plan)

    def _load_tax_offset_plans(self) -> dict[str, Any]:
        if not self._tax_offset_plans_path.exists():
            return {}
        with self._tax_offset_plans_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def load_etc_state(self) -> dict[str, Any]:
        if not self._etc_state_path.exists():
            return {}
        with self._etc_state_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def save_etc_state(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        self._etc_state_path.parent.mkdir(parents=True, exist_ok=True)
        with self._etc_state_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def load_etc_reconciliation_state(self) -> dict[str, Any]:
        if not self._etc_reconciliation_state_path.exists():
            return {}
        with self._etc_reconciliation_state_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def save_etc_reconciliation_state(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        self._etc_reconciliation_state_path.parent.mkdir(parents=True, exist_ok=True)
        with self._etc_reconciliation_state_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def store_etc_reconciliation_file(self, *, task_id: str, file_id: str, file_name: str, content: bytes) -> str:
        sanitized_name = self._sanitize_name(file_name)
        content_bytes = bytes(content or b"")
        task_dir = self._etc_reconciliation_file_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        target_path = task_dir / f"{file_id}_{sanitized_name}"
        target_path.write_bytes(content_bytes)
        return str(target_path)

    def read_etc_reconciliation_file(self, stored_file_path: str) -> bytes:
        if self._is_gridfs_ref(stored_file_path):
            raise RuntimeError("Legacy GridFS ETC reconciliation file access is disabled.")
        return Path(stored_file_path).read_bytes()

    def store_etc_invoice_file(self, *, invoice_number: str, file_name: str, content: bytes) -> str:
        sanitized_name = self._sanitize_name(file_name)
        content_bytes = bytes(content or b"")
        normalized_invoice_number = self._sanitize_name(invoice_number)
        invoice_dir = self._etc_invoice_file_root / normalized_invoice_number
        invoice_dir.mkdir(parents=True, exist_ok=True)
        target_path = invoice_dir / sanitized_name
        target_path.write_bytes(content_bytes)
        return str(target_path)

    def read_etc_invoice_file(self, stored_file_path: str) -> bytes:
        if self._is_gridfs_ref(stored_file_path):
            raise RuntimeError("Legacy GridFS ETC invoice file access is disabled.")
        return Path(stored_file_path).read_bytes()

    def etc_invoice_file_exists(self, stored_file_path: str) -> bool:
        if self._is_gridfs_ref(stored_file_path):
            return False
        return Path(stored_file_path).exists()

    def delete_etc_invoice_file(self, stored_file_path: str) -> None:
        if self._is_gridfs_ref(stored_file_path):
            return
        path = Path(stored_file_path)
        if path.exists():
            path.unlink()

    def save_historical_etc_repair_bundle(
        self,
        *,
        bundle_id: str,
        file_name: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_bundle_id = str(bundle_id or "").strip()
        if not resolved_bundle_id:
            raise ValueError("bundle_id is required.")
        resolved_file_name = str(file_name or "").strip() or f"{resolved_bundle_id}.zip"
        content_bytes = bytes(content or b"")
        if not content_bytes:
            raise ValueError("historical ETC repair bundle content must not be empty.")
        content_sha256 = hashlib.sha256(content_bytes).hexdigest()
        updated_at = datetime.now(UTC)
        normalized_metadata = dict(metadata or {})
        normalized_metadata.update(
            {
                "bundle_id": resolved_bundle_id,
                "file_name": resolved_file_name,
                "sha256": content_sha256,
                "size": len(content_bytes),
                "updated_at": updated_at.isoformat(),
            }
        )

        self._historical_etc_repair_root.mkdir(parents=True, exist_ok=True)
        target_path = self._historical_etc_repair_root / f"{resolved_bundle_id}_{self._sanitize_name(resolved_file_name)}"
        target_path.write_bytes(content_bytes)
        bundles = self.load_historical_etc_repair_bundle_metadata()
        document = {
            "_id": resolved_bundle_id,
            **normalized_metadata,
            "stored_file_path": str(target_path),
        }
        bundles[resolved_bundle_id] = document
        self._historical_etc_repair_bundles_path.write_text(
            json.dumps(bundles, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return document

    def load_historical_etc_repair_bundle_metadata(self) -> dict[str, dict[str, Any]]:
        if not self._historical_etc_repair_bundles_path.exists():
            return {}
        try:
            payload = json.loads(self._historical_etc_repair_bundles_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {
            str(bundle_id): dict(document)
            for bundle_id, document in (payload if isinstance(payload, dict) else {}).items()
            if isinstance(document, dict)
        }

    def read_historical_etc_repair_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        resolved_bundle_id = str(bundle_id or "").strip()
        if not resolved_bundle_id:
            return None
        metadata = self.load_historical_etc_repair_bundle_metadata().get(resolved_bundle_id)
        if not isinstance(metadata, dict):
            return None
        stored_file_path = str(metadata.get("stored_file_path") or "").strip()
        if not stored_file_path:
            return None
        if self._is_gridfs_ref(stored_file_path):
            raise RuntimeError("Legacy GridFS historical ETC repair bundle access is disabled.")
        else:
            content = Path(stored_file_path).read_bytes()
        expected_sha256 = str(metadata.get("sha256") or "").strip()
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise RuntimeError(f"Historical ETC repair bundle checksum mismatch: {resolved_bundle_id}")
        return {
            "bundle_id": resolved_bundle_id,
            "file_name": str(metadata.get("file_name") or f"{resolved_bundle_id}.zip"),
            "content": content,
            "metadata": dict(metadata),
        }

    def save_historical_etc_repair_parsed_seed(
        self,
        *,
        bundle_id: str,
        parsed_seed: dict[str, Any],
    ) -> dict[str, Any]:
        resolved_bundle_id = str(bundle_id or "").strip()
        if not resolved_bundle_id:
            raise ValueError("bundle_id is required.")
        if not isinstance(parsed_seed, dict):
            raise ValueError("parsed_seed must be a dict.")
        updated_at = datetime.now(UTC).isoformat()
        document = {
            **parsed_seed,
            "bundle_id": resolved_bundle_id,
            "updated_at": parsed_seed.get("updated_at") or updated_at,
        }
        self._historical_etc_repair_root.mkdir(parents=True, exist_ok=True)
        seeds = self.load_historical_etc_repair_parsed_seeds()
        seeds[resolved_bundle_id] = document
        self._historical_etc_repair_parsed_seeds_path.write_text(
            json.dumps(seeds, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return document

    def load_historical_etc_repair_parsed_seeds(self) -> dict[str, dict[str, Any]]:
        if not self._historical_etc_repair_parsed_seeds_path.exists():
            return {}
        try:
            payload = json.loads(self._historical_etc_repair_parsed_seeds_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {
            str(bundle_id): dict(document)
            for bundle_id, document in (payload if isinstance(payload, dict) else {}).items()
            if isinstance(document, dict)
        }

    def load_historical_etc_repair_parsed_seed(self, bundle_id: str) -> dict[str, Any] | None:
        resolved_bundle_id = str(bundle_id or "").strip()
        if not resolved_bundle_id:
            return None
        seed = self.load_historical_etc_repair_parsed_seeds().get(resolved_bundle_id)
        return dict(seed) if isinstance(seed, dict) else None

    def load_historical_etc_repair_states(self) -> dict[str, dict[str, Any]]:
        if not self._historical_etc_repair_states_path.exists():
            return {}
        try:
            payload = json.loads(self._historical_etc_repair_states_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {
            str(bundle_id): dict(document)
            for bundle_id, document in (payload if isinstance(payload, dict) else {}).items()
            if isinstance(document, dict)
        }

    def save_historical_etc_repair_states(self, states: dict[str, dict[str, Any]]) -> None:
        normalized_states = {
            str(bundle_id): dict(state)
            for bundle_id, state in (states if isinstance(states, dict) else {}).items()
            if str(bundle_id).strip() and isinstance(state, dict)
        }
        self._historical_etc_repair_root.mkdir(parents=True, exist_ok=True)
        self._historical_etc_repair_states_path.write_text(
            json.dumps(normalized_states, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def load_background_jobs(self) -> dict[str, dict[str, Any]]:
        if not self._background_jobs_path.exists():
            return {}
        try:
            with self._background_jobs_path.open("rb") as handle:
                loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        except (FileNotFoundError, pickle.PickleError, EOFError):
            return {}
        if not isinstance(loaded, dict):
            return {}
        return {
            str(job_id): dict(payload)
            for job_id, payload in loaded.items()
            if isinstance(payload, dict)
        }

    def save_background_jobs(self, snapshot: dict[str, dict[str, Any]]) -> None:
        normalized_snapshot = {
            str(job_id): dict(payload)
            for job_id, payload in (snapshot if isinstance(snapshot, dict) else {}).items()
            if isinstance(payload, dict)
        }
        with self._background_jobs_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def load_app_health_alerts(self) -> dict[str, Any]:
        if not self._app_health_alerts_path.exists():
            return {}
        try:
            with self._app_health_alerts_path.open("rb") as handle:
                loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        except (FileNotFoundError, pickle.PickleError, EOFError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def save_app_health_alerts(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        with self._app_health_alerts_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def load_workbench_pair_relations(self) -> dict[str, Any]:
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
        current_payload = self._load_local_pickle()
        if changed_case_ids is None:
            current_payload["workbench_pair_relations"] = normalized_snapshot
        else:
            existing_snapshot = current_payload.get("workbench_pair_relations")
            merged_snapshot = dict(existing_snapshot) if isinstance(existing_snapshot, dict) else {}
            existing_relations = merged_snapshot.get("pair_relations")
            merged_relations = dict(existing_relations) if isinstance(existing_relations, dict) else {}
            incoming_relations = normalized_snapshot.get("pair_relations")
            if isinstance(incoming_relations, dict):
                merged_relations.update(incoming_relations)
            merged_snapshot.update(
                {
                    key: value
                    for key, value in normalized_snapshot.items()
                    if key != "pair_relations"
                }
            )
            merged_snapshot["pair_relations"] = merged_relations
            current_payload["workbench_pair_relations"] = merged_snapshot
        self._save_local_pickle(current_payload)

    def load_oa_pending_payment_bank_relations(self) -> dict[str, Any]:
        current_payload = self._load_local_pickle()
        snapshot = current_payload.get("oa_pending_payment_bank_relations")
        return snapshot if isinstance(snapshot, dict) else {}

    def save_oa_pending_payment_bank_relations(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        current_payload = self._load_local_pickle()
        current_payload["oa_pending_payment_bank_relations"] = normalized_snapshot
        self._save_local_pickle(current_payload)

    def load_no_oa_bank_batches(self) -> dict[str, Any]:
        if not self._no_oa_bank_batches_path.exists():
            return {}
        with self._no_oa_bank_batches_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def load_bank_flow_rule_batches(self) -> dict[str, Any]:
        if not self._bank_flow_rule_batches_path.exists():
            return {}
        with self._bank_flow_rule_batches_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def save_no_oa_bank_batches(
        self,
        snapshot: dict[str, Any],
        *,
        relation_mode: str = "no_oa_bank_batch",
    ) -> None:
        _ = relation_mode
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        with self._no_oa_bank_batches_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def save_bank_flow_rule_batches(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        with self._bank_flow_rule_batches_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def save_bank_flow_rule_batches_scope(
        self,
        snapshot: dict[str, Any],
        *,
        scope_key: str,
    ) -> None:
        _ = scope_key
        self.save_bank_flow_rule_batches(snapshot)

    def load_workbench_read_models(self) -> dict[str, Any]:
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
        current_payload = self._load_local_pickle()
        current_payload["workbench_read_models"] = normalized_snapshot
        self._save_local_pickle(current_payload)

    def save_no_oa_bank_batch_mutation(
        self,
        *,
        pair_relation_snapshot: dict[str, Any],
        no_oa_bank_batch_snapshot: dict[str, Any],
        workbench_read_model_snapshot: dict[str, Any],
        changed_case_ids: set[str] | list[str] | tuple[str, ...],
        changed_scope_keys: set[str] | list[str] | tuple[str, ...],
    ) -> None:
        normalized_case_ids = [str(case_id).strip() for case_id in changed_case_ids if str(case_id).strip()]
        normalized_scope_keys = [str(scope_key).strip() for scope_key in changed_scope_keys if str(scope_key).strip()]
        if normalized_case_ids:
            self.save_workbench_pair_relations(
                pair_relation_snapshot,
                changed_case_ids=normalized_case_ids,
            )
        self.save_no_oa_bank_batches(no_oa_bank_batch_snapshot)
        self.save_workbench_read_models(
            workbench_read_model_snapshot,
            changed_scope_keys=normalized_scope_keys,
        )

    def save_bank_flow_rule_batch_mutation(
        self,
        *,
        pair_relation_snapshot: dict[str, Any],
        bank_flow_rule_batch_snapshot: dict[str, Any],
        changed_case_ids: set[str] | list[str] | tuple[str, ...],
        changed_scope_keys: set[str] | list[str] | tuple[str, ...],
    ) -> None:
        normalized_case_ids = [str(case_id).strip() for case_id in changed_case_ids if str(case_id).strip()]
        normalized_scope_keys = [str(scope_key).strip() for scope_key in changed_scope_keys if str(scope_key).strip()]
        batch_scope_keys = _bank_flow_rule_batch_month_scopes(normalized_scope_keys)
        if normalized_case_ids:
            self.save_workbench_pair_relations(
                pair_relation_snapshot,
                changed_case_ids=normalized_case_ids,
            )
        if batch_scope_keys:
            for scope_key in batch_scope_keys:
                self.save_bank_flow_rule_batches_scope(bank_flow_rule_batch_snapshot, scope_key=scope_key)
        else:
            self.save_bank_flow_rule_batches(bank_flow_rule_batch_snapshot)

    def load_bank_transaction_categories(self) -> dict[str, Any]:
        current_payload = self._load_local_pickle()
        snapshot = current_payload.get("bank_transaction_categories")
        return snapshot if isinstance(snapshot, dict) else {}

    def save_bank_transaction_categories(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        current_payload = self._load_local_pickle()
        current_payload["bank_transaction_categories"] = normalized_snapshot
        self._save_local_pickle(current_payload)

    def load_turnover_relations(self) -> dict[str, Any]:
        current_payload = self._load_local_pickle()
        snapshot = current_payload.get("turnover_relations")
        return snapshot if isinstance(snapshot, dict) else {}

    def save_turnover_relations(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        current_payload = self._load_local_pickle()
        current_payload["turnover_relations"] = normalized_snapshot
        self._save_local_pickle(current_payload)

    def load_turnover_relation_audit_log(self) -> list[Any]:
        snapshot = self.load_turnover_relations()
        audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else None
        return list(audit_log) if isinstance(audit_log, list) else []

    def save_turnover_relation_audit_log(self, snapshot: dict[str, Any] | list[Any]) -> None:
        audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else snapshot
        normalized_audit_log = list(audit_log) if isinstance(audit_log, list) else []
        current_snapshot = self.load_turnover_relations()
        if not isinstance(current_snapshot, dict):
            current_snapshot = {}
        current_snapshot["audit_log"] = normalized_audit_log
        self.save_turnover_relations(current_snapshot)

    def load_turnover_ledger_extras(self) -> dict[str, Any]:
        current_payload = self._load_local_pickle()
        snapshot = current_payload.get("turnover_ledger_extras")
        return snapshot if isinstance(snapshot, dict) else {}

    def save_turnover_ledger_extras(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        current_payload = self._load_local_pickle()
        current_payload["turnover_ledger_extras"] = normalized_snapshot
        self._save_local_pickle(current_payload)

    def load_cost_statistics_read_models(self) -> dict[str, Any]:
        current_payload = self._load_local_pickle()
        snapshot = current_payload.get("cost_statistics_read_models")
        return snapshot if isinstance(snapshot, dict) else {}

    def save_cost_statistics_read_models(
        self,
        snapshot: dict[str, Any],
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        current_payload = self._load_local_pickle()
        current_payload["cost_statistics_read_models"] = normalized_snapshot
        self._save_local_pickle(current_payload)

    def load_tax_offset_read_models(self) -> dict[str, Any]:
        current_payload = self._load_local_pickle()
        snapshot = current_payload.get("tax_offset_read_models")
        return snapshot if isinstance(snapshot, dict) else {}

    def save_tax_offset_read_models(
        self,
        snapshot: dict[str, Any],
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        current_payload = self._load_local_pickle()
        current_payload["tax_offset_read_models"] = normalized_snapshot
        self._save_local_pickle(current_payload)

    def load(self) -> dict[str, Any]:
        return self._load_local_pickle()

    def save(self, payload: dict[str, Any]) -> None:
        self._save_local_pickle(payload)

    def save_import_delta(self, payload: dict[str, Any]) -> None:
        normalized = dict(payload or {})
        if not normalized or set(normalized) - {"imports", "file_imports"}:
            raise ValueError("Import delta requires only imports and file_imports payloads.")
        current_payload = self._load_local_pickle()
        imports_delta = normalized.get("imports")
        if isinstance(imports_delta, dict):
            current_payload["imports"] = self._merge_import_snapshot(
                current_payload.get("imports"),
                imports_delta,
            )
        file_imports_delta = normalized.get("file_imports")
        if isinstance(file_imports_delta, dict):
            current_payload["file_imports"] = self._merge_file_import_snapshot(
                current_payload.get("file_imports"),
                file_imports_delta,
            )
        self._save_local_pickle(current_payload)

    def save_invoices(self, invoices: list[Any]) -> None:
        self._merge_import_invoices(invoices)

    def save_invoice_etc_metadata(self, invoices: list[Any]) -> None:
        self._merge_import_invoices(invoices)

    def _merge_import_invoices(self, invoices: list[Any]) -> None:
        changed = list(invoices or [])
        if not changed:
            return
        current_payload = self._load_local_pickle()
        current_payload["imports"] = self._merge_import_snapshot(
            current_payload.get("imports"),
            {"invoices": changed},
        )
        self._save_local_pickle(current_payload)

    @classmethod
    def _merge_import_snapshot(cls, current: Any, delta: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current) if isinstance(current, dict) else {}
        for counter in ("batch_counter", "row_counter", "invoice_counter", "txn_counter", "counterparty_counter"):
            if counter in delta:
                merged[counter] = max(int(merged.get(counter) or 0), int(delta.get(counter) or 0))
        batches = delta.get("batches")
        if isinstance(batches, dict):
            merged["batches"] = {**dict(merged.get("batches") or {}), **batches}
        for field in ("invoices", "transactions"):
            if field in delta:
                merged[field] = cls._merge_import_entity_list(merged.get(field), delta.get(field))
        return merged

    @staticmethod
    def _merge_file_import_snapshot(current: Any, delta: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current) if isinstance(current, dict) else {}
        for counter in ("session_counter", "file_counter"):
            if counter in delta:
                merged[counter] = max(int(merged.get(counter) or 0), int(delta.get(counter) or 0))
        sessions = delta.get("sessions")
        if isinstance(sessions, dict):
            merged["sessions"] = {**dict(merged.get("sessions") or {}), **sessions}
        return merged

    @classmethod
    def _merge_import_entity_list(cls, current: Any, delta: Any) -> list[Any]:
        existing = list(current or [])
        changed_by_id = {
            entity_id: entity
            for entity in list(delta or [])
            if (entity_id := cls._import_entity_id(entity))
        }
        merged: list[Any] = []
        seen: set[str] = set()
        for entity in existing:
            entity_id = cls._import_entity_id(entity)
            if entity_id in changed_by_id:
                merged.append(changed_by_id[entity_id])
                seen.add(entity_id)
            else:
                merged.append(entity)
        merged.extend(entity for entity_id, entity in changed_by_id.items() if entity_id not in seen)
        return merged

    def save_matching_snapshot(self, snapshot: dict[str, Any]) -> None:
        current_payload = self._load_local_pickle()
        current_payload["matching"] = dict(snapshot or {})
        self._save_local_pickle(current_payload)

    @staticmethod
    def _import_entity_id(entity: Any) -> str:
        if isinstance(entity, dict):
            return str(entity.get("id") or "").strip()
        return str(getattr(entity, "id", "") or "").strip()

    def save_workbench_overrides(
        self,
        workbench_overrides_snapshot: dict[str, Any],
        *,
        changed_row_ids: list[str] | None = None,
    ) -> None:
        current_payload = self._load_local_pickle()
        current_payload["workbench_overrides"] = workbench_overrides_snapshot
        self._save_local_pickle(current_payload)

    def save_workbench_exception_cases(self, snapshot: dict[str, Any]) -> None:
        current_payload = self._load_local_pickle()
        current_payload["workbench_exception_cases"] = snapshot
        self._save_local_pickle(current_payload)

    def store_import_file(self, *, session_id: str, file_id: str, file_name: str, content: bytes) -> str:
        session_dir = self._import_file_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        target_path = session_dir / f"{file_id}_{self._sanitize_name(file_name)}"
        target_path.write_bytes(content)
        return str(target_path)

    def read_import_file(self, stored_file_path: str) -> bytes:
        if self._is_gridfs_ref(stored_file_path):
            raise RuntimeError("Legacy GridFS import file references are not supported by ApplicationStateStore.")
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
                continue
            target_path = Path(normalized_path)
            if target_path.exists():
                target_path.unlink(missing_ok=True)
                deleted_count += 1
        return deleted_count

    def clear_oa_attachment_invoice_cache(self) -> int:
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
        file_imports = self._load_local_pickle().get("file_imports", {})
        sessions = file_imports.get("sessions", {}) if isinstance(file_imports, dict) else {}
        return session_id in sessions

    def import_file_exists(self, file_id: str) -> bool:
        file_imports = self._load_local_pickle().get("file_imports", {})
        sessions = file_imports.get("sessions", {}) if isinstance(file_imports, dict) else {}
        for session in sessions.values():
            files = session.get("files", []) if isinstance(session, dict) else []
            if any(isinstance(file, dict) and file.get("id") == file_id for file in files):
                return True
        return False

    def import_batch_exists(self, batch_id: str) -> bool:
        imports = self._load_local_pickle().get("imports", {})
        batches = imports.get("batches", {}) if isinstance(imports, dict) else {}
        return batch_id in batches

    def invoice_exists(self, invoice_id: str) -> bool:
        imports = self._load_local_pickle().get("imports", {})
        invoices = imports.get("invoices", []) if isinstance(imports, dict) else []
        return any(isinstance(invoice, dict) and invoice.get("id") == invoice_id for invoice in invoices)

    def transaction_exists(self, transaction_id: str) -> bool:
        imports = self._load_local_pickle().get("imports", {})
        transactions = imports.get("transactions", []) if isinstance(imports, dict) else []
        return any(isinstance(transaction, dict) and transaction.get("id") == transaction_id for transaction in transactions)

    def load_pending_invoice_commands(self) -> dict[str, Any]:
        payload = self._load_local_pickle().get("pending_invoice_commands", {})
        return payload if isinstance(payload, dict) else {}

    def save_pending_invoice_commands(self, snapshot: dict[str, Any]) -> None:
        current_payload = self._load_local_pickle()
        current_payload["pending_invoice_commands"] = snapshot if isinstance(snapshot, dict) else {}
        self._save_local_pickle(current_payload)

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

    @classmethod
    def _normalize_manual_oa_imports(cls, payload: object) -> dict[str, object]:
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
        for row_id in cls._dedupe_text_values(raw_payload.get("row_ids") if isinstance(raw_payload, dict) else []):
            entries.setdefault(row_id, {"row_id": row_id, "source": "manual_oa_import"})
        audit_log = raw_payload.get("audit_log")
        return {
            "row_ids": sorted(entries),
            "entries": entries,
            "audit_log": list(audit_log) if isinstance(audit_log, list) else [],
        }

    @staticmethod
    def _dedupe_text_values(values: object) -> list[str]:
        if not isinstance(values, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            result.append(text)
            seen.add(text)
        return result

    @staticmethod
    def _has_non_empty_state(payload: dict[str, Any]) -> bool:
        return any(
            bool(payload.get(key))
            for key in (
                "imports",
                "bank_transaction_categories",
                "file_imports",
                "matching",
                "workbench_overrides",
                "workbench_exception_cases",
                "workbench_pair_relations",
                "workbench_read_models",
                "no_oa_bank_batches",
                "turnover_relations",
                "turnover_ledger_extras",
                "cost_statistics_read_models",
                "tax_offset_read_models",
                "app_health_alerts",
            )
        )

    def _load_local_pickle(self) -> dict[str, Any]:
        with self._local_pickle_lock:
            if not self._legacy_state_path.exists():
                return {}
            with self._legacy_state_path.open("rb") as handle:
                loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def _save_local_pickle(self, payload: dict[str, Any]) -> None:
        with self._local_pickle_lock:
            self._legacy_state_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._legacy_state_path.with_name(f"{self._legacy_state_path.name}.tmp")
            with temp_path.open("wb") as handle:
                pickle.dump(payload, handle)
            temp_path.replace(self._legacy_state_path)

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
    def _is_gridfs_ref(value: str) -> bool:
        return value.startswith(GRIDFS_REF_PREFIX)

    @staticmethod
    def _sanitize_name(file_name: str) -> str:
        cleaned = FILENAME_SAFE_RE.sub("_", file_name).strip("._")
        return cleaned or "uploaded_file"

    def _serialize_value(self, value: Any) -> Any:
        if hasattr(value, "__dataclass_fields__"):
            return {
                key: self._serialize_value(getattr(value, key, None))
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

    @staticmethod
    def _backfill_file_import_preview_item(value: Any) -> None:
        if not hasattr(value, "__dataclass_fields__"):
            return
        fields = getattr(value, "__dataclass_fields__", {})
        if "selected_bank_short_name" not in fields or hasattr(value, "selected_bank_short_name"):
            return
        setattr(value, "selected_bank_short_name", None)
