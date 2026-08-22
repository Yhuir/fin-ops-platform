from __future__ import annotations

import hashlib
import json
import pickle
import re
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any

from fin_ops_platform.services.runtime_paths import default_data_dir as _default_data_dir
from fin_ops_platform.services.state_store_protocol import (
    PROTECTED_ADMIN_USERNAME,
    SETTINGS_ACCESS_CONTROL_KEYS,
    SettingsAccessControlVersionConflict,
    settings_access_control_from_payload,
)

FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
GRIDFS_REF_PREFIX = "gridfs://"
LOCAL_SETTINGS_ACL_AUDIT_KEY = "_settings_acl_audit_events"


class _LocalSettingsAccessControlCriticalSection:
    def __init__(self, store: "ApplicationStateStore", current: dict[str, Any]) -> None:
        self._store = store
        self._current = deepcopy(current)
        self._committed = False

    @property
    def locked_current(self) -> dict[str, Any]:
        return deepcopy(settings_access_control_from_payload(self._current))

    def commit(
        self,
        next_access_control: dict[str, Any],
        durable_audit: dict[str, Any],
    ) -> dict[str, Any]:
        if self._committed:
            raise RuntimeError("Settings access-control critical section was already committed.")
        mutation_id = str(durable_audit.get("mutation_id") or "").strip()
        if not mutation_id:
            raise ValueError("Settings access-control audit mutation_id is required.")
        current_acl = settings_access_control_from_payload(self._current)
        next_acl = settings_access_control_from_payload(next_access_control)
        next_acl["access_control_version"] = current_acl["access_control_version"] + 1
        persisted = {**self._current, **next_acl}
        audits = list(persisted.get(LOCAL_SETTINGS_ACL_AUDIT_KEY) or [])
        audits.append({**deepcopy(durable_audit), "access_control_version": next_acl["access_control_version"]})
        persisted[LOCAL_SETTINGS_ACL_AUDIT_KEY] = audits[-100:]
        self._store._write_app_settings_unlocked(persisted)
        self._current = persisted
        self._committed = True
        return deepcopy(next_acl)


def _etc_business_batch_bucket(status: str) -> str | None:
    if status in {"oa_submitted", "manually_marked_submitted", "closed"}:
        return "submitted"
    if status in {"oa_draft_creating", "oa_confirmation_pending"}:
        return "staged"
    if status in {"deleted", "superseded"}:
        return None
    return "unsubmitted"


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
        with self._local_pickle_lock:
            return self._load_app_settings_unlocked()

    def _load_app_settings_unlocked(self) -> dict[str, Any]:
        default_payload = {
            "completed_project_ids": [],
            "manual_projects": [],
            "synced_projects": [],
            "bank_account_mappings": [],
            "allowed_usernames": [PROTECTED_ADMIN_USERNAME],
            "readonly_export_usernames": [],
            "admin_usernames": [PROTECTED_ADMIN_USERNAME],
            "full_access_usernames": [],
            "access_control_version": 1,
            "workbench_column_layouts": {},
            "oa_retention": {},
            "oa_import": {},
            "oa_invoice_offset": {},
            "bank_transaction_tags": {},
            "pending_invoice_tag_groups": {},
            "pending_output_invoice_tag_groups": {},
            "bank_flow_rule_batch_tag_rules": {},
            "cost_statistics_time_tag_selection": {},
            "cost_statistics_no_oa_projects": {},
            "input_invoice_usage_payment_status_rules": {},
            "etc_oa_draft_prefill": {},
            "input_invoice_usage_oa_draft_prefill": {},
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
            **settings_access_control_from_payload(loaded),
            "workbench_column_layouts": dict(loaded.get("workbench_column_layouts") or {}),
            "oa_retention": dict(loaded.get("oa_retention") or {}),
            "oa_import": dict(loaded.get("oa_import") or {}),
            "oa_invoice_offset": dict(loaded.get("oa_invoice_offset") or {}),
            "bank_transaction_tags": dict(loaded.get("bank_transaction_tags") or {}),
            "pending_invoice_tag_groups": dict(loaded.get("pending_invoice_tag_groups") or {}),
            "pending_output_invoice_tag_groups": dict(loaded.get("pending_output_invoice_tag_groups") or {}),
            "bank_flow_rule_batch_tag_rules": dict(loaded.get("bank_flow_rule_batch_tag_rules") or {}),
            "input_invoice_usage_payment_status_rules": dict(
                loaded.get("input_invoice_usage_payment_status_rules") or {}
            ),
            "etc_oa_draft_prefill": dict(loaded.get("etc_oa_draft_prefill") or {}),
            "input_invoice_usage_oa_draft_prefill": dict(
                loaded.get("input_invoice_usage_oa_draft_prefill") or {}
            ),
        }
        if "no_oa_bank_batch_tag_selection" in loaded:
            normalized_payload["no_oa_bank_batch_tag_selection"] = dict(
                loaded.get("no_oa_bank_batch_tag_selection") or {}
            )
        if "cost_statistics_time_tag_selection" in loaded:
            normalized_payload["cost_statistics_time_tag_selection"] = dict(
                loaded.get("cost_statistics_time_tag_selection") or {}
            )
        if "cost_statistics_no_oa_projects" in loaded:
            normalized_payload["cost_statistics_no_oa_projects"] = dict(
                loaded.get("cost_statistics_no_oa_projects") or {}
            )
        if (
            "cost_statistics_tag_selection" in loaded
            and "cost_statistics_no_oa_projects" not in loaded
        ):
            normalized_payload["cost_statistics_tag_selection"] = dict(
                loaded.get("cost_statistics_tag_selection") or {}
            )
        if "turnover_ledger_tag_selection" in loaded:
            normalized_payload["turnover_ledger_tag_selection"] = dict(
                loaded.get("turnover_ledger_tag_selection") or {}
            )
        if "batch_accounting_tag_selection" in loaded:
            normalized_payload["batch_accounting_tag_selection"] = dict(
                loaded.get("batch_accounting_tag_selection") or {}
            )
        if LOCAL_SETTINGS_ACL_AUDIT_KEY in loaded:
            normalized_payload[LOCAL_SETTINGS_ACL_AUDIT_KEY] = list(
                loaded.get(LOCAL_SETTINGS_ACL_AUDIT_KEY) or []
            )
        return normalized_payload

    def save_app_settings(self, payload: dict[str, Any]) -> None:
        with self._local_pickle_lock:
            current = self._load_app_settings_unlocked()
            next_payload = dict(payload)
            next_payload.update({key: current[key] for key in SETTINGS_ACCESS_CONTROL_KEYS})
            if LOCAL_SETTINGS_ACL_AUDIT_KEY in current:
                next_payload[LOCAL_SETTINGS_ACL_AUDIT_KEY] = current[LOCAL_SETTINGS_ACL_AUDIT_KEY]
            self._write_app_settings_unlocked(next_payload)

    def _write_app_settings_unlocked(self, payload: dict[str, Any]) -> None:
        normalized_payload = {
            "completed_project_ids": list(payload.get("completed_project_ids") or []),
            "manual_projects": list(payload.get("manual_projects") or []),
            "synced_projects": list(payload.get("synced_projects") or []),
            "bank_account_mappings": list(payload.get("bank_account_mappings") or []),
            **settings_access_control_from_payload(payload),
            "workbench_column_layouts": dict(payload.get("workbench_column_layouts") or {}),
            "oa_retention": dict(payload.get("oa_retention") or {}),
            "oa_import": dict(payload.get("oa_import") or {}),
            "oa_invoice_offset": dict(payload.get("oa_invoice_offset") or {}),
            "bank_transaction_tags": dict(payload.get("bank_transaction_tags") or {}),
            "pending_invoice_tag_groups": dict(payload.get("pending_invoice_tag_groups") or {}),
            "pending_output_invoice_tag_groups": dict(payload.get("pending_output_invoice_tag_groups") or {}),
            "bank_flow_rule_batch_tag_rules": dict(payload.get("bank_flow_rule_batch_tag_rules") or {}),
            "cost_statistics_time_tag_selection": dict(
                payload.get("cost_statistics_time_tag_selection") or {}
            ),
            "cost_statistics_no_oa_projects": dict(
                payload.get("cost_statistics_no_oa_projects") or {}
            ),
            "input_invoice_usage_payment_status_rules": dict(
                payload.get("input_invoice_usage_payment_status_rules") or {}
            ),
            "etc_oa_draft_prefill": dict(payload.get("etc_oa_draft_prefill") or {}),
            "input_invoice_usage_oa_draft_prefill": dict(
                payload.get("input_invoice_usage_oa_draft_prefill") or {}
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
        if "batch_accounting_tag_selection" in payload:
            normalized_payload["batch_accounting_tag_selection"] = dict(
                payload.get("batch_accounting_tag_selection") or {}
            )
        if LOCAL_SETTINGS_ACL_AUDIT_KEY in payload:
            normalized_payload[LOCAL_SETTINGS_ACL_AUDIT_KEY] = list(
                payload.get(LOCAL_SETTINGS_ACL_AUDIT_KEY) or []
            )
        temporary_path = self._app_settings_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(normalized_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self._app_settings_path)

    @contextmanager
    def begin_settings_acl_critical_section(self, expected_version: int):
        with self._local_pickle_lock:
            current = self._load_app_settings_unlocked()
            current_version = settings_access_control_from_payload(current)["access_control_version"]
            if current_version != int(expected_version):
                raise SettingsAccessControlVersionConflict(current_version)
            yield _LocalSettingsAccessControlCriticalSection(self, current)

    def recover_settings_acl_commit(self, mutation_id: str) -> dict[str, Any]:
        normalized_mutation_id = str(mutation_id or "").strip()
        if not normalized_mutation_id:
            raise ValueError("Settings access-control mutation_id is required.")
        with self._local_pickle_lock:
            current = self._load_app_settings_unlocked()
            audits = list(current.get(LOCAL_SETTINGS_ACL_AUDIT_KEY) or [])
            return {
                "access_control": settings_access_control_from_payload(current),
                "audit_present": any(
                    str(item.get("mutation_id") or "") == normalized_mutation_id
                    for item in audits
                    if isinstance(item, dict)
                ),
            }

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

    def list_etc_business_batch_summaries(self, **query: Any) -> dict[str, Any]:
        snapshot = self.load_etc_state()
        batches = [
            self._serialize_value(value)
            for value in dict(snapshot.get("business_batches") or {}).values()
        ]
        invoices = [
            self._serialize_value(value)
            for value in dict(snapshot.get("invoices") or {}).values()
        ]
        invoices_by_id = {
            str(invoice.get("id") or ""): invoice
            for invoice in invoices
            if isinstance(invoice, dict) and str(invoice.get("id") or "")
        }
        task_records = dict(self.load_etc_reconciliation_state().get("tasks") or {})
        normalized_task_id = str(query.get("task_id") or "").strip()
        owner_user_ids = {str(value or "").strip() for value in query.get("owner_user_ids") or [] if str(value or "").strip()}
        owner_org_id = str(query.get("owner_org_id") or "").strip()
        can_admin_access = bool(query.get("can_admin_access"))
        month = str(query.get("month") or "").strip()
        plate = str(query.get("plate") or "").strip().lower()
        keyword = str(query.get("keyword") or "").strip().lower()
        visible: list[dict[str, Any]] = []
        for raw_batch in batches:
            if not isinstance(raw_batch, dict) or str(raw_batch.get("status") or "") in {"deleted", "superseded"}:
                continue
            if normalized_task_id and str(raw_batch.get("task_id") or "") != normalized_task_id:
                continue
            owner_user_id = str(raw_batch.get("owner_user_id") or "").strip()
            batch_owner_org_id = str(raw_batch.get("owner_org_id") or "").strip()
            if not can_admin_access and (owner_user_id or batch_owner_org_id):
                if owner_user_id not in owner_user_ids and (not owner_org_id or batch_owner_org_id != owner_org_id):
                    continue
            batch_invoice_ids = {str(value) for value in raw_batch.get("invoice_ids") or []}
            batch_invoices = [invoice for invoice in invoices if isinstance(invoice, dict) and str(invoice.get("id") or "") in batch_invoice_ids]
            scope_month = str((raw_batch.get("amount_breakdown") or {}).get("scope_month") or "")[:7] if isinstance(raw_batch.get("amount_breakdown"), dict) else ""
            if month:
                month_matches = scope_month == month if scope_month else any(
                    month in {
                        str(invoice.get("issue_date") or "")[:7],
                        str(invoice.get("passage_start_date") or "")[:7],
                        str(invoice.get("passage_end_date") or "")[:7],
                    }
                    for invoice in batch_invoices
                )
                if not month_matches:
                    continue
            if plate and not any(plate in str(invoice.get("plate_number") or "").lower() for invoice in batch_invoices):
                continue
            if keyword:
                haystack = " ".join(
                    [
                        str(raw_batch.get("business_batch_id") or ""),
                        str(raw_batch.get("title") or ""),
                        str(raw_batch.get("external_etc_batch_id") or ""),
                        *(str(invoice.get("invoice_number") or "") for invoice in batch_invoices),
                    ]
                ).lower()
                if keyword not in haystack:
                    continue
            visible.append(raw_batch)
        visible.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        bucket = str(query.get("bucket") or "unsubmitted").strip()
        counts = {name: sum(1 for item in visible if _etc_business_batch_bucket(str(item.get("status") or "")) == name) for name in ("unsubmitted", "staged", "submitted")}
        bucket_items = [item for item in visible if _etc_business_batch_bucket(str(item.get("status") or "")) == bucket]
        page = max(1, int(query.get("page") or 1))
        page_size = max(1, min(500, int(query.get("page_size") or 100)))
        start = (page - 1) * page_size
        return {
            "items": [
                {
                    "business_batch": item,
                    "reconciliation_task": self._serialize_value(task_records.get(str(item.get("task_id") or ""))),
                    "scope_month": (item.get("amount_breakdown") or {}).get("scope_month") if isinstance(item.get("amount_breakdown"), dict) else None,
                    "invoice_count": len(item.get("invoice_ids") or []),
                    "total_amount": str(sum((Decimal(str(invoices_by_id.get(str(invoice_id), {}).get("total_amount") or "0")) for invoice_id in item.get("invoice_ids") or []), Decimal("0"))),
                }
                for item in bucket_items[start : start + page_size]
            ],
            "counts": counts,
            "total": len(bucket_items),
        }

    def get_etc_business_batch_record(self, business_batch_id: str) -> dict[str, Any] | None:
        value = dict(self.load_etc_state().get("business_batches") or {}).get(str(business_batch_id or "").strip())
        payload = self._serialize_value(value)
        return payload if isinstance(payload, dict) else None

    def list_etc_invoice_records_by_ids(self, invoice_ids: list[str]) -> list[dict[str, Any]]:
        records = dict(self.load_etc_state().get("invoices") or {})
        result: list[dict[str, Any]] = []
        for invoice_id in invoice_ids:
            payload = self._serialize_value(records.get(str(invoice_id)))
            if isinstance(payload, dict):
                result.append(payload)
        return result

    def get_etc_reconciliation_task_record(self, task_id: str) -> dict[str, Any] | None:
        value = dict(self.load_etc_reconciliation_state().get("tasks") or {}).get(str(task_id or "").strip())
        payload = self._serialize_value(value)
        return payload if isinstance(payload, dict) else None

    def save_etc_state(self, snapshot: dict[str, Any]) -> None:
        normalized_snapshot = snapshot if isinstance(snapshot, dict) else {}
        with self._local_pickle_lock:
            self._etc_state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._etc_state_path.open("wb") as handle:
                pickle.dump(normalized_snapshot, handle)

    def save_etc_oa_draft_attempt(
        self,
        snapshot: dict[str, Any],
        *,
        business_batch_id: str,
        expected_version: int,
    ) -> bool:
        with self._local_pickle_lock:
            current = self.load_etc_state()
            current_batch = dict(current.get("business_batches") or {}).get(business_batch_id)
            current_version = (
                current_batch.get("version")
                if isinstance(current_batch, dict)
                else getattr(current_batch, "version", None)
            )
            if int(current_version or 0) != int(expected_version):
                return False
            merged = dict(current)
            for collection in ("invoices", "batches", "import_batches", "business_batches"):
                values = dict(merged.get(collection) or {})
                values.update(dict(snapshot.get(collection) or {}))
                merged[collection] = values
            for counter in ("invoice_counter", "batch_counter", "import_batch_counter", "business_batch_counter"):
                merged[counter] = max(int(merged.get(counter, 0) or 0), int(snapshot.get(counter, 0) or 0))
            day_counters = dict(merged.get("batch_day_counters") or {})
            for day, value in dict(snapshot.get("batch_day_counters") or {}).items():
                day_counters[str(day)] = max(int(day_counters.get(str(day), 0) or 0), int(value or 0))
            merged["batch_day_counters"] = day_counters
            self.save_etc_state(merged)
            return True

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

    def load_background_job(self, job_id: str) -> dict[str, Any] | None:
        payload = self.load_background_jobs().get(str(job_id or "").strip())
        return dict(payload) if isinstance(payload, dict) else None

    def save_background_job(self, job_payload: dict[str, Any]) -> None:
        payload = dict(job_payload)
        job_id = str(payload.get("job_id") or payload.get("id") or "").strip()
        if not job_id:
            raise ValueError("job_id is required.")
        jobs = self.load_background_jobs()
        payload["job_id"] = job_id
        jobs[job_id] = payload
        self._save_background_jobs_snapshot(jobs)

    def _save_background_jobs_snapshot(self, snapshot: dict[str, dict[str, Any]]) -> None:
        normalized_snapshot = {
            str(job_id): dict(payload)
            for job_id, payload in (snapshot if isinstance(snapshot, dict) else {}).items()
            if isinstance(payload, dict)
        }
        with self._background_jobs_path.open("wb") as handle:
            pickle.dump(normalized_snapshot, handle)

    def create_or_requeue_background_job(
        self,
        job_payload: dict[str, Any],
        *,
        reuse_any_status: bool = False,
    ) -> tuple[dict[str, Any] | None, bool]:
        candidate = dict(job_payload)
        jobs = self.load_background_jobs()
        owner_id = str(candidate.get("owner_user_id") or "")
        job_type = str(candidate.get("type") or "")
        idempotency_key = str(candidate.get("idempotency_key") or "")
        fingerprint = str(candidate.get("request_fingerprint") or "")
        for existing in jobs.values():
            if (
                str(existing.get("owner_user_id") or "") != owner_id
                or str(existing.get("type") or "") != job_type
                or str(existing.get("idempotency_key") or "") != idempotency_key
            ):
                continue
            existing_fingerprint = str(existing.get("request_fingerprint") or "")
            if existing_fingerprint and existing_fingerprint != fingerprint:
                return None, False
            if not reuse_any_status and str(existing.get("status") or "") in {"failed", "partial_success"}:
                candidate["job_id"] = existing.get("job_id")
                candidate["created_at"] = existing.get("created_at")
                jobs[str(candidate["job_id"])] = candidate
                self._save_background_jobs_snapshot(jobs)
                return candidate, True
            return dict(existing), False
        jobs[str(candidate["job_id"])] = candidate
        self._save_background_jobs_snapshot(jobs)
        return candidate, True

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

    def load_no_oa_bank_batches(self) -> dict[str, Any]:
        if not self._no_oa_bank_batches_path.exists():
            return {}
        with self._no_oa_bank_batches_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def load_bank_flow_rule_batches(self) -> dict[str, Any]:
        current_payload = self._load_local_pickle()
        snapshot = current_payload.get("bank_flow_rule_batches")
        if isinstance(snapshot, dict):
            return snapshot
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
        with self._local_pickle_lock:
            current_payload = self._load_local_pickle()
            current_payload["bank_flow_rule_batches"] = normalized_snapshot
            self._save_local_pickle(current_payload)

    def save_no_oa_bank_batch_mutation(
        self,
        *,
        pair_relation_snapshot: dict[str, Any],
        no_oa_bank_batch_snapshot: dict[str, Any],
        changed_case_ids: set[str] | list[str] | tuple[str, ...],
        changed_scope_keys: set[str] | list[str] | tuple[str, ...],
    ) -> None:
        normalized_case_ids = [str(case_id).strip() for case_id in changed_case_ids if str(case_id).strip()]
        _ = changed_scope_keys
        if normalized_case_ids:
            self.save_workbench_pair_relations(
                pair_relation_snapshot,
                changed_case_ids=normalized_case_ids,
            )
        self.save_no_oa_bank_batches(no_oa_bank_batch_snapshot)

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
        normalized_case_ids = [str(case_id).strip() for case_id in changed_case_ids if str(case_id).strip()]
        _ = changed_scope_keys
        normalized_batch_ids = {
            str(batch_id).strip()
            for batch_id in changed_batch_ids
            if str(batch_id).strip()
        }
        if isinstance(candidate_guard, dict):
            batches = bank_flow_rule_batch_snapshot.get("batches")
            candidate = (
                batches.get(str(candidate_guard.get("batch_id") or ""))
                if isinstance(batches, dict)
                else None
            )
            expected_members = sorted(
                str(row_id).strip()
                for row_id in list(candidate_guard.get("row_ids") or [])
                if str(row_id).strip()
            )
            actual_members = sorted(
                str(row_id).strip()
                for row_id in (
                    list(candidate.get("row_ids") or [])
                    if isinstance(candidate, dict)
                    else []
                )
                if str(row_id).strip()
            )
            if not isinstance(candidate, dict) or expected_members != actual_members:
                raise RuntimeError("bank_flow_rule_batch_candidate_guard_conflict")
        if not normalized_batch_ids:
            raise ValueError("bank-flow rule batch mutation requires an explicit changed batch id")
        with self._local_pickle_lock:
            current_payload = self._load_local_pickle()
            if normalized_case_ids:
                normalized_relation_snapshot = (
                    pair_relation_snapshot
                    if isinstance(pair_relation_snapshot, dict)
                    else {}
                )
                existing_snapshot = current_payload.get("workbench_pair_relations")
                merged_snapshot = (
                    dict(existing_snapshot)
                    if isinstance(existing_snapshot, dict)
                    else {}
                )
                existing_relations = merged_snapshot.get("pair_relations")
                merged_relations = (
                    dict(existing_relations)
                    if isinstance(existing_relations, dict)
                    else {}
                )
                incoming_relations = normalized_relation_snapshot.get("pair_relations")
                if isinstance(incoming_relations, dict):
                    merged_relations.update(incoming_relations)
                merged_snapshot.update(
                    {
                        key: value
                        for key, value in normalized_relation_snapshot.items()
                        if key != "pair_relations"
                    }
                )
                merged_snapshot["pair_relations"] = merged_relations
                current_payload["workbench_pair_relations"] = merged_snapshot
            current_payload["bank_flow_rule_batches"] = (
                bank_flow_rule_batch_snapshot
                if isinstance(bank_flow_rule_batch_snapshot, dict)
                else {}
            )
            self._save_local_pickle(current_payload)

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

    def load(self) -> dict[str, Any]:
        return self._load_local_pickle()

    def preview_settings_data_reset(
        self,
        action: str,
        *,
        row_ids: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        fingerprint_payload = {
            "action": str(action or "").strip(),
            "row_ids": sorted(set(row_ids or [])),
            "case_ids": sorted(set(case_ids or [])),
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "action": fingerprint_payload["action"],
            "impact_counts": {},
            "impact_fingerprint": fingerprint,
            "recovery_ready": True,
            "recovery_receipt_id": "00000000-0000-0000-0000-000000000001",
            "recovery_valid_until": None,
        }

    def reset_bank_transaction_data(
        self,
        *,
        source_snapshot: dict[str, Any] | None = None,
        reset_context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del reset_context
        return self._reset_local_import_domain(
            source_snapshot=source_snapshot,
            removed_batch_types={"bank_transaction"},
            remove_bank_transactions=True,
            remove_invoices=False,
            workbench_row_types={"bank", "bank_transaction"},
            workbench_row_id_prefixes=("bk-", "bk_", "txn-", "txn_", "bank-", "bank_"),
        )

    def reset_invoice_data(
        self,
        *,
        source_snapshot: dict[str, Any] | None = None,
        reset_context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del reset_context
        result = self._reset_local_import_domain(
            source_snapshot=source_snapshot,
            removed_batch_types={"input_invoice", "output_invoice"},
            remove_bank_transactions=False,
            remove_invoices=True,
            workbench_row_types={"invoice", "input_invoice", "output_invoice"},
            workbench_row_id_prefixes=(
                "iv-",
                "iv_",
                "inv-",
                "inv_",
                "invoice-",
                "invoice_",
                "oa-att-inv-",
                "etc-summary-",
            ),
        )
        tax_snapshot = (
            dict(source_snapshot.get("tax_certified_imports") or {})
            if isinstance(source_snapshot, dict)
            else self.load_tax_certified_imports()
        )
        result.update(
            {
                "tax_certified_import_sessions": len(
                    dict(tax_snapshot.get("sessions") or {})
                ),
                "tax_certified_import_batches": len(
                    dict(tax_snapshot.get("batches") or {})
                ),
                "tax_certified_import_records": len(
                    dict(tax_snapshot.get("records") or {})
                ),
                "etc_batch_invoice_links": 0,
            }
        )
        self.save_tax_certified_imports({})
        return result

    def reset_oa_workbench_data(
        self,
        *,
        row_ids: list[str],
        case_ids: list[str],
        source_snapshot: dict[str, Any] | None = None,
        reset_context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del reset_context
        normalized_row_ids = {
            str(row_id or "").strip()
            for row_id in row_ids
            if str(row_id or "").strip()
        }
        normalized_case_ids = {
            str(case_id or "").strip()
            for case_id in case_ids
            if str(case_id or "").strip()
        }
        with self._local_pickle_lock:
            current_payload = self._load_local_pickle()
            override_snapshot = (
                source_snapshot.get("workbench_overrides")
                if isinstance(source_snapshot, dict)
                else current_payload.get("workbench_overrides")
            )
            row_overrides = (
                dict(override_snapshot.get("row_overrides") or {})
                if isinstance(override_snapshot, dict)
                else {}
            )
            kept_row_overrides = {
                override_key: override
                for override_key, override in row_overrides.items()
                if str(
                    self._get_container_value(override, "row_id")
                    or override_key
                )
                not in normalized_row_ids
            }
            relation_snapshot = (
                source_snapshot.get("workbench_pair_relations")
                if isinstance(source_snapshot, dict)
                else current_payload.get("workbench_pair_relations")
            )
            pair_relations = (
                dict(relation_snapshot.get("pair_relations") or {})
                if isinstance(relation_snapshot, dict)
                else {}
            )
            kept_pair_relations = {
                case_id: relation
                for case_id, relation in pair_relations.items()
                if str(case_id) not in normalized_case_ids
            }
            current_payload["workbench_overrides"] = self._snapshot_with_filtered_items(
                override_snapshot,
                key="row_overrides",
                items=kept_row_overrides,
            )
            current_payload["workbench_pair_relations"] = {
                **(dict(relation_snapshot) if isinstance(relation_snapshot, dict) else {}),
                "pair_relations": kept_pair_relations,
            }
            self._save_local_pickle(current_payload)
        removed_override_count = len(row_overrides) - len(kept_row_overrides)
        removed_relation_count = len(pair_relations) - len(kept_pair_relations)
        return {
            "workbench_row_overrides": removed_override_count,
            "workbench_oa_row_overrides": removed_override_count,
            "workbench_pair_relations": removed_relation_count,
            "workbench_oa_pair_relations": removed_relation_count,
            "workbench_pair_relation_history_preserved": 0,
            "workbench_preserved_non_oa_pair_relations": len(kept_pair_relations),
        }

    def _reset_local_import_domain(
        self,
        *,
        source_snapshot: dict[str, Any] | None,
        removed_batch_types: set[str],
        remove_bank_transactions: bool,
        remove_invoices: bool,
        workbench_row_types: set[str],
        workbench_row_id_prefixes: tuple[str, ...],
    ) -> dict[str, Any]:
        normalized_batch_types = {
            str(batch_type or "").strip()
            for batch_type in removed_batch_types
            if str(batch_type or "").strip()
        }
        with self._local_pickle_lock:
            current_payload = self._load_local_pickle()
            reset_source = source_snapshot if isinstance(source_snapshot, dict) else current_payload
            imports_snapshot = deepcopy(reset_source.get("imports") or {})
            batches = dict(imports_snapshot.get("batches") or {})
            invoices = list(imports_snapshot.get("invoices") or [])
            transactions = list(imports_snapshot.get("transactions") or [])
            filtered_batches = {
                batch_id: preview
                for batch_id, preview in batches.items()
                if self._local_preview_batch_type(preview) not in normalized_batch_types
            }
            imports_snapshot["batches"] = filtered_batches
            if remove_bank_transactions:
                imports_snapshot["transactions"] = []
            if remove_invoices:
                imports_snapshot["invoices"] = []

            file_snapshot = deepcopy(reset_source.get("file_imports") or {})
            sessions = dict(file_snapshot.get("sessions") or {})
            kept_sessions: dict[str, Any] = {}
            removed_file_paths: list[str] = []
            removed_file_count = 0
            removed_session_count = 0
            for session_id, session in sessions.items():
                files = list(self._get_container_value(session, "files") or [])
                kept_files: list[Any] = []
                for file_item in files:
                    if (
                        self._local_file_batch_type(file_item)
                        not in normalized_batch_types
                    ):
                        kept_files.append(file_item)
                        continue
                    removed_file_count += 1
                    stored_file_path = self._get_container_value(
                        file_item,
                        "stored_file_path",
                    )
                    if stored_file_path:
                        removed_file_paths.append(str(stored_file_path))
                if not kept_files:
                    if files:
                        removed_session_count += 1
                    continue
                updated_session = deepcopy(session)
                self._set_container_value(updated_session, "files", kept_files)
                self._set_container_value(updated_session, "file_count", len(kept_files))
                kept_sessions[str(session_id)] = updated_session
            file_snapshot["sessions"] = kept_sessions

            override_snapshot = reset_source.get("workbench_overrides")
            row_overrides = (
                dict(override_snapshot.get("row_overrides") or {})
                if isinstance(override_snapshot, dict)
                else {}
            )
            kept_row_overrides = {
                override_key: override
                for override_key, override in row_overrides.items()
                if not self._local_workbench_item_matches_domain(
                    row_id=str(
                        self._get_container_value(override, "row_id")
                        or override_key
                    ),
                    row_type=(
                        self._get_container_value(override, "row_type")
                        or self._get_container_value(override, "type")
                    ),
                    row_types=workbench_row_types,
                    row_id_prefixes=workbench_row_id_prefixes,
                )
            }

            relation_snapshot = reset_source.get("workbench_pair_relations")
            pair_relations = (
                dict(relation_snapshot.get("pair_relations") or {})
                if isinstance(relation_snapshot, dict)
                else {}
            )
            kept_pair_relations = {
                case_id: relation
                for case_id, relation in pair_relations.items()
                if not self._local_relation_matches_domain(
                    relation,
                    row_types=workbench_row_types,
                    row_id_prefixes=workbench_row_id_prefixes,
                )
            }

            matching_snapshot = reset_source.get("matching")
            matching_runs = (
                dict(matching_snapshot.get("runs") or {})
                if isinstance(matching_snapshot, dict)
                else {}
            )
            matching_results = (
                dict(matching_snapshot.get("results") or {})
                if isinstance(matching_snapshot, dict)
                else {}
            )
            current_payload["imports"] = imports_snapshot
            current_payload["file_imports"] = file_snapshot
            current_payload["matching"] = {}
            current_payload["workbench_overrides"] = self._snapshot_with_filtered_items(
                override_snapshot,
                key="row_overrides",
                items=kept_row_overrides,
            )
            current_payload["workbench_pair_relations"] = self._snapshot_with_filtered_items(
                relation_snapshot,
                key="pair_relations",
                items=kept_pair_relations,
            )
            if remove_bank_transactions:
                current_payload["bank_transaction_categories"] = {}
                current_payload["turnover_relations"] = {}
            self._save_local_pickle(current_payload)

        return {
            "import_batches": len(batches) - len(filtered_batches),
            "import_batch_rows": 0,
            "invoices": len(invoices) if remove_invoices else 0,
            "bank_transactions": (
                len(transactions) if remove_bank_transactions else 0
            ),
            "file_import_sessions": removed_session_count,
            "file_import_files": removed_file_count,
            "matching_runs": len(matching_runs),
            "matching_results": len(matching_results),
            "workbench_row_overrides": len(row_overrides) - len(kept_row_overrides),
            "workbench_pair_relations": len(pair_relations)
            - len(kept_pair_relations),
            "workbench_pair_relation_history_preserved": 0,
            "stored_import_file_paths": list(dict.fromkeys(removed_file_paths)),
        }

    @staticmethod
    def _snapshot_with_filtered_items(
        snapshot: Any,
        *,
        key: str,
        items: dict[str, Any],
    ) -> dict[str, Any]:
        if not items:
            return {}
        normalized = dict(snapshot) if isinstance(snapshot, dict) else {}
        normalized[key] = items
        return normalized

    @classmethod
    def _local_relation_matches_domain(
        cls,
        relation: Any,
        *,
        row_types: set[str],
        row_id_prefixes: tuple[str, ...],
    ) -> bool:
        if not isinstance(relation, dict):
            return False
        relation_row_ids = list(relation.get("row_ids") or [])
        relation_row_types = list(relation.get("row_types") or [])
        for index, row_id in enumerate(relation_row_ids):
            row_type = (
                relation_row_types[index]
                if index < len(relation_row_types)
                else ""
            )
            if cls._local_workbench_item_matches_domain(
                row_id=str(row_id or ""),
                row_type=row_type,
                row_types=row_types,
                row_id_prefixes=row_id_prefixes,
            ):
                return True
        return False

    @staticmethod
    def _local_workbench_item_matches_domain(
        *,
        row_id: str,
        row_type: Any,
        row_types: set[str],
        row_id_prefixes: tuple[str, ...],
    ) -> bool:
        normalized_row_type = str(row_type or "").strip().lower()
        normalized_row_id = str(row_id or "").strip().lower()
        return normalized_row_type in row_types or normalized_row_id.startswith(
            row_id_prefixes
        )

    @classmethod
    def _local_preview_batch_type(cls, preview: Any) -> str:
        batch = cls._get_container_value(preview, "batch")
        batch_type = cls._get_container_value(batch, "batch_type")
        return str(getattr(batch_type, "value", batch_type) or "")

    @classmethod
    def _local_file_batch_type(cls, file_item: Any) -> str:
        batch_type = cls._get_container_value(file_item, "batch_type")
        return str(getattr(batch_type, "value", batch_type) or "")

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

    def save_confirmed_import_delta_with_oa_attachment_promotion(
        self,
        payload: dict[str, Any],
        *,
        scope_months: list[str],
        promotion_mode: str,
        source_versions: dict[str, object],
    ) -> dict[str, Any]:
        del scope_months, promotion_mode, source_versions
        self.save_import_delta(payload)
        return {
            "queued_matching_months": [],
            "oa_attachment_invoice_promotion": {},
        }

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
        for counter in ("batch_counter", "invoice_counter", "txn_counter", "counterparty_counter"):
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

    def store_import_file(
        self,
        *,
        session_id: str,
        file_id: str,
        file_name: str,
        content: bytes,
        imported_by: str | None = None,
    ) -> str:
        session_dir = self._import_file_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        target_path = session_dir / f"{file_id}_{self._sanitize_name(file_name)}"
        target_path.write_bytes(content)
        return str(target_path)

    def read_import_file(self, stored_file_path: str) -> bytes:
        if self._is_gridfs_ref(stored_file_path):
            raise RuntimeError("Legacy GridFS import file references are not supported by ApplicationStateStore.")
        return Path(stored_file_path).read_bytes()

    def find_confirmed_import_file_by_sha256(
        self,
        *,
        content_sha256: str,
        exclude_file_id: str,
    ) -> dict[str, Any] | None:
        return None

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
                "no_oa_bank_batches",
                "turnover_relations",
                "turnover_ledger_extras",
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
