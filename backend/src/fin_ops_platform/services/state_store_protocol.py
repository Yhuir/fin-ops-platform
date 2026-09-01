from __future__ import annotations

import unicodedata
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

PROTECTED_ADMIN_USERNAME = "YNSYLP005"
SETTINGS_ACCESS_CONTROL_KEYS = frozenset(
    {
        "page_access_accounts",
        "access_control_version",
    }
)


def default_settings_access_control() -> dict[str, Any]:
    return {
        "page_access_accounts": [],
        "access_control_version": 1,
    }


def settings_username_comparison_key(value: object) -> str:
    raw = str(value or "")
    if any(unicodedata.category(character) == "Cc" for character in raw):
        raise ValueError("Access-control usernames cannot contain control characters.")
    canonical = raw.strip()
    if not canonical or len(canonical) > 128:
        raise ValueError("Access-control usernames must contain 1 to 128 characters.")
    return canonical.casefold()


def settings_access_control_from_payload(payload: object) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    try:
        version = max(1, int(source.get("access_control_version") or 1))
    except (TypeError, ValueError):
        version = 1

    raw_accounts = source.get("page_access_accounts", [])
    if not isinstance(raw_accounts, list):
        raise ValueError("Access-control page_access_accounts must be an array.")

    protected_key = settings_username_comparison_key(PROTECTED_ADMIN_USERNAME)
    seen_usernames: set[str] = set()
    accounts: list[dict[str, Any]] = []
    for raw_account in raw_accounts:
        if not isinstance(raw_account, dict) or set(raw_account) != {"username", "page_keys"}:
            raise ValueError("Access-control accounts must contain only username and page_keys.")
        username = str(raw_account.get("username") or "").strip()
        username_key = settings_username_comparison_key(username)
        if username_key == protected_key:
            raise ValueError("The protected administrator cannot be stored as an ordinary account.")
        if username_key in seen_usernames:
            raise ValueError("Access-control page_access_accounts contains duplicate usernames.")
        seen_usernames.add(username_key)

        raw_page_keys = raw_account.get("page_keys")
        if not isinstance(raw_page_keys, list) or not raw_page_keys:
            raise ValueError("Access-control page_keys must be a non-empty array.")
        page_keys: list[str] = []
        seen_page_keys: set[str] = set()
        for raw_page_key in raw_page_keys:
            page_key = str(raw_page_key or "").strip()
            if not page_key or len(page_key) > 128:
                raise ValueError("Access-control page keys must contain 1 to 128 characters.")
            if any(unicodedata.category(character) == "Cc" for character in page_key):
                raise ValueError("Access-control page keys cannot contain control characters.")
            if page_key in seen_page_keys:
                raise ValueError("Access-control accounts cannot contain duplicate page keys.")
            seen_page_keys.add(page_key)
            page_keys.append(page_key)
        accounts.append({"username": username, "page_keys": sorted(page_keys)})

    return {
        "page_access_accounts": sorted(
            accounts,
            key=lambda account: settings_username_comparison_key(account["username"]),
        ),
        "access_control_version": version,
    }


class SettingsAccessControlVersionConflict(RuntimeError):
    def __init__(self, current_version: int) -> None:
        super().__init__("Settings access-control version conflict.")
        self.current_version = int(current_version)


class SettingsAccessControlCommitOutcomeUnknown(RuntimeError):
    def __init__(self, mutation_id: str) -> None:
        super().__init__("Settings access-control commit outcome is unknown.")
        self.mutation_id = str(mutation_id)


class SettingsAccessControlCriticalSectionProtocol(Protocol):
    @property
    def locked_current(self) -> dict[str, Any]: ...

    def commit(
        self,
        next_access_control: dict[str, Any],
        durable_audit: dict[str, Any],
    ) -> dict[str, Any]: ...


@runtime_checkable
class ApplicationStateStoreProtocol(Protocol):
    @property
    def data_dir(self) -> Path: ...

    @property
    def storage_backend(self) -> str: ...

    @property
    def storage_mode(self) -> str: ...

    @property
    def mongo_database_name(self) -> str | None: ...

    def load(self) -> dict[str, Any]: ...

    def save(self, payload: dict[str, Any]) -> None: ...

    def reset_bank_transaction_data(
        self,
        *,
        source_snapshot: dict[str, Any] | None = None,
        reset_context: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def reset_invoice_data(
        self,
        *,
        source_snapshot: dict[str, Any] | None = None,
        reset_context: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def reset_oa_workbench_data(
        self,
        *,
        row_ids: list[str],
        case_ids: list[str],
        source_snapshot: dict[str, Any] | None = None,
        reset_context: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def preview_settings_data_reset(
        self,
        action: str,
        *,
        row_ids: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def save_import_delta(self, payload: dict[str, Any]) -> None: ...

    def save_confirmed_import_delta_with_oa_attachment_promotion(
        self,
        payload: dict[str, Any],
        *,
        scope_months: list[str],
        promotion_mode: str,
        source_versions: dict[str, object],
    ) -> dict[str, Any]: ...

    def save_invoices(self, invoices: list[Any]) -> None: ...

    def save_invoice_etc_metadata(self, invoices: list[Any]) -> None: ...

    def load_app_settings(self) -> dict[str, Any]: ...

    def save_app_settings(self, payload: dict[str, Any]) -> None: ...

    def begin_settings_acl_critical_section(
        self,
        expected_version: int,
    ) -> AbstractContextManager[SettingsAccessControlCriticalSectionProtocol]: ...

    def recover_settings_acl_commit(self, mutation_id: str) -> dict[str, Any]: ...

    def load_pending_invoice_commands(self) -> dict[str, Any]: ...

    def save_pending_invoice_commands(self, snapshot: dict[str, Any]) -> None: ...

    def load_oa_attachment_invoice_cache_entry(self, cache_key: str) -> dict[str, object] | None: ...

    def save_oa_attachment_invoice_cache_entry(self, cache_key: str, payload: dict[str, object]) -> None: ...

    def clear_oa_attachment_invoice_cache(self) -> int: ...

    def load_oa_sync_state(self) -> dict[str, Any]: ...

    def save_oa_sync_state(self, snapshot: dict[str, Any]) -> None: ...

    def load_manual_oa_imports(self) -> dict[str, object]: ...

    def save_manual_oa_imports(self, payload: dict[str, object]) -> None: ...

    def add_manual_oa_imports(
        self,
        row_ids: list[str],
        *,
        actor_id: str | None = None,
        audit: dict[str, object] | None = None,
    ) -> dict[str, object]: ...

    def remove_manual_oa_import(self, row_id: str, *, actor_id: str | None = None) -> bool: ...

    def store_import_file(
        self,
        *,
        session_id: str,
        file_id: str,
        file_name: str,
        content: bytes,
        imported_by: str | None = None,
    ) -> str: ...

    def find_confirmed_import_file_by_sha256(
        self,
        *,
        content_sha256: str,
        exclude_file_id: str,
    ) -> dict[str, Any] | None: ...

    def read_import_file(self, stored_file_path: str) -> bytes: ...

    def delete_import_files(self, stored_file_paths: list[str]) -> int: ...

    def store_etc_import_archive(
        self,
        *,
        session_id: str,
        file_id: str,
        file_name: str,
        content: bytes,
    ) -> dict[str, object]: ...

    def read_etc_import_archive(self, stored_file_path: str) -> bytes: ...

    def delete_etc_import_archives(self, stored_file_paths: list[str]) -> int: ...

    def import_session_exists(self, session_id: str) -> bool: ...

    def import_file_exists(self, file_id: str) -> bool: ...

    def import_batch_exists(self, batch_id: str) -> bool: ...

    def invoice_exists(self, invoice_id: str) -> bool: ...

    def transaction_exists(self, transaction_id: str) -> bool: ...

    def load_workbench_pair_relations(self) -> dict[str, Any]: ...

    def save_workbench_pair_relations(self, snapshot: dict[str, Any], *, changed_case_ids: set[str] | None = None) -> None: ...

    def load_workbench_overrides(self) -> dict[str, Any]: ...

    def load_no_oa_bank_batches(self) -> dict[str, Any]: ...

    def save_no_oa_bank_batches(self, snapshot: dict[str, Any], *, relation_mode: str = "no_oa_bank_batch") -> None: ...

    def load_bank_flow_rule_batches(self) -> dict[str, Any]: ...
    def save_bank_flow_rule_batches(self, snapshot: dict[str, Any]) -> None: ...
    def save_bank_flow_rule_batch_mutation(
        self,
        *,
        pair_relation_snapshot: dict[str, Any],
        bank_flow_rule_batch_snapshot: dict[str, Any],
        changed_case_ids: set[str] | list[str] | tuple[str, ...],
        changed_scope_keys: set[str] | list[str] | tuple[str, ...],
        changed_batch_ids: set[str] | list[str] | tuple[str, ...] = (),
        candidate_guard: dict[str, object] | None = None,
    ) -> None: ...

    def load_bank_transaction_categories(self) -> dict[str, Any]: ...

    def save_bank_transaction_categories(self, snapshot: dict[str, Any]) -> None: ...

    def load_turnover_relations(self) -> dict[str, Any]: ...

    def save_turnover_relations(self, snapshot: dict[str, Any]) -> None: ...

    def load_turnover_relation_audit_log(self) -> list[Any]: ...

    def save_turnover_relation_audit_log(self, snapshot: list[Any]) -> None: ...

    def load_turnover_ledger_extras(self) -> dict[str, Any]: ...

    def save_turnover_ledger_extras(self, snapshot: dict[str, Any]) -> None: ...

    def load_tax_certified_imports(self) -> dict[str, Any]: ...

    def save_tax_certified_imports(self, snapshot: dict[str, Any]) -> None: ...

    def load_etc_state(self) -> dict[str, Any]: ...

    def list_etc_business_batch_summaries(self, **query: Any) -> dict[str, Any]: ...

    def get_etc_business_batch_record(self, business_batch_id: str) -> dict[str, Any] | None: ...

    def list_etc_invoice_records_by_ids(self, invoice_ids: list[str]) -> list[dict[str, Any]]: ...

    def get_etc_reconciliation_task_record(self, task_id: str) -> dict[str, Any] | None: ...

    def list_etc_reconciliation_import_task_summaries(self) -> list[dict[str, Any]]: ...

    def save_etc_state(self, snapshot: dict[str, Any]) -> None: ...

    def save_etc_oa_draft_attempt(
        self,
        snapshot: dict[str, Any],
        *,
        business_batch_id: str,
        expected_version: int,
    ) -> bool: ...

    def load_etc_reconciliation_state(self) -> dict[str, Any]: ...

    def save_etc_reconciliation_state(self, snapshot: dict[str, Any]) -> None: ...

    def store_etc_reconciliation_file(self, *, task_id: str, file_id: str, file_name: str, content: bytes) -> str: ...

    def read_etc_reconciliation_file(self, stored_file_path: str) -> bytes: ...

    def store_etc_invoice_file(self, *, invoice_number: str, file_name: str, content: bytes) -> str: ...

    def read_etc_invoice_file(self, stored_file_path: str) -> bytes: ...

    def etc_invoice_file_exists(self, stored_file_path: str) -> bool: ...

    def delete_etc_invoice_file(self, stored_file_path: str) -> None: ...

    def load_background_jobs(self) -> dict[str, Any]: ...

    def load_background_job(self, job_id: str) -> dict[str, Any] | None: ...

    def save_background_job(self, job_payload: dict[str, Any]) -> None: ...

    def create_or_requeue_background_job(
        self,
        job_payload: dict[str, Any],
        *,
        reuse_any_status: bool = False,
    ) -> tuple[dict[str, Any] | None, bool]: ...

    def load_app_health_alerts(self) -> dict[str, Any]: ...

    def save_app_health_alerts(self, snapshot: dict[str, Any]) -> None: ...

    def save_workbench_overrides(
        self,
        workbench_overrides_snapshot: dict[str, Any],
        *,
        changed_row_ids: set[str] | None = None,
    ) -> None: ...

    def save_workbench_exception_cases(self, snapshot: dict[str, Any]) -> None: ...

    def save_historical_etc_repair_bundle(
        self,
        *,
        bundle_id: str,
        file_name: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def load_historical_etc_repair_bundle_metadata(self) -> dict[str, dict[str, Any]]: ...

    def read_historical_etc_repair_bundle(self, bundle_id: str) -> dict[str, Any] | None: ...

    def save_historical_etc_repair_parsed_seed(
        self,
        *,
        bundle_id: str,
        parsed_seed: dict[str, Any],
    ) -> dict[str, Any]: ...

    def load_historical_etc_repair_parsed_seeds(self) -> dict[str, dict[str, Any]]: ...

    def load_historical_etc_repair_parsed_seed(self, bundle_id: str) -> dict[str, Any] | None: ...

    def load_historical_etc_repair_states(self) -> dict[str, dict[str, Any]]: ...

    def save_historical_etc_repair_states(self, states: dict[str, Any]) -> None: ...
