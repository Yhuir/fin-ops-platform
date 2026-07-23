from __future__ import annotations

import hashlib
import json
import re
from threading import RLock
from typing import Any, Callable, Protocol

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.bank_detail_category_selection import confirmation_selection, manual_assignment_selection
from fin_ops_platform.services.bank_details_export_service import (
    BankDetailsExportResult,
    BankDetailsExportService,
)
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryService,
    BankTransactionCategoryValidationError,
)
from fin_ops_platform.services.postgres_repositories.read_models import BANK_DETAIL_READ_MODEL_SCHEMA_VERSION
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.read_model_write_targets import write_target_envelope


SEARCH_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class BankDetailsReadModelRefreshingError(RuntimeError):
    def __init__(self, payload: dict[str, object]) -> None:
        super().__init__("bank detail read model refreshing")
        self.payload = payload


class BankTransactionCategoryStorePort(Protocol):
    def save_bank_transaction_categories(self, snapshot: dict[str, Any]) -> None:
        ...


class BankDetailsApplicationService:
    def __init__(
        self,
        *,
        app_settings_service: AppSettingsService,
        bank_transaction_category_service: BankTransactionCategoryService,
        bank_transaction_auto_category_service: BankTransactionAutoCategoryService,
        audit_service: AuditTrailService,
        bank_transaction_category_store: BankTransactionCategoryStorePort | None,
        bank_detail_sql_read_repository: Any | None,
        bank_account_balance_read_model_repository: Any | None = None,
        runtime_repositories: Any | None,
        affected_months_provider: Callable[[list[str]], list[str]],
        available_month_scope_keys_provider: Callable[[], list[str]],
        enqueue_bank_account_balance_refresh: Callable[..., bool],
        suggestion_provider: Callable[[str], dict[str, object] | None] | None = None,
        bank_transaction_tags_provider: Callable[[], dict[str, object]] | None = None,
        category_mutation_writer: Any | None = None,
        workbench_relation_reader: Any | None = None,
    ) -> None:
        self._app_settings_service = app_settings_service
        self._bank_transaction_category_service = bank_transaction_category_service
        self._bank_transaction_auto_category_service = bank_transaction_auto_category_service
        self._audit_service = audit_service
        if bank_transaction_category_store is not None and not callable(
            getattr(bank_transaction_category_store, "save_bank_transaction_categories", None)
        ):
            raise TypeError("bank_transaction_category_store must provide save_bank_transaction_categories")
        self._bank_transaction_category_store = bank_transaction_category_store
        self._bank_detail_sql_read_repository = bank_detail_sql_read_repository
        self._bank_account_balance_read_model_repository = bank_account_balance_read_model_repository
        self._runtime_repositories = runtime_repositories
        self._affected_months_provider = affected_months_provider
        self._available_month_scope_keys_provider = available_month_scope_keys_provider
        self._enqueue_bank_account_balance_refresh = enqueue_bank_account_balance_refresh
        self._suggestion_provider = suggestion_provider
        self._bank_transaction_tags_provider = bank_transaction_tags_provider
        self._category_mutation_writer = category_mutation_writer
        self._workbench_relation_reader = workbench_relation_reader
        self._category_mutation_lock = RLock()

    def accounts_payload(self, *, date_from: str | None, date_to: str | None) -> dict[str, object]:
        return self._accounts_from_sql_read_model(date_from=date_from, date_to=date_to)

    def transactions_payload(
        self,
        *,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None = None,
        category_primary_label: str | None = None,
        category_sub_label: str | None = None,
        category_third_label: str | None = None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        return self._transactions_from_sql_read_model(
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
            page=page,
            page_size=page_size,
        )

    def get_auto_tag_rules_payload(self, *, can_save: bool) -> dict[str, Any]:
        return self._app_settings_service.get_bank_auto_tag_rules_payload(can_save=can_save)

    def update_auto_tag_rules(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        priority_scope_keys = self._refresh_scope_keys_from_auto_tag_rules_payload(payload)
        result = self._app_settings_service.update_bank_auto_tag_rules(
            payload,
            actor_id=actor_id,
        )
        return {
            **result,
            **self._bank_detail_access_scope_payload(priority_scope_keys),
        }

    def replace_auto_tag_rules_from_file_source(self, source: object, *, actor_id: str) -> dict[str, Any]:
        result = self._app_settings_service.replace_bank_auto_tag_rules_from_file_source(
            source,
            actor_id=actor_id,
        )
        return {
            **result,
            **self._bank_detail_access_scope_payload([]),
        }

    def reapply_auto_tag_rules(self, *, actor_id: str, can_save: bool) -> dict[str, Any]:
        scope_keys = self._available_month_scope_keys_provider()
        enqueued = self._enqueue_read_model_refreshes(scope_keys, reason="bank_auto_tag_rules_reapply_requested")
        if not enqueued:
            raise RuntimeError("bank_auto_tag_rules_reapply_unavailable")
        version = self._current_bank_auto_tag_rules_version()
        self._audit_service.record_action(
            actor_id=actor_id,
            action="bank_auto_tag_rules_reapply_requested",
            entity_type="app_settings",
            entity_id="bank_auto_tag_rules",
            metadata={
                "version": version,
                "scope_keys": list(scope_keys),
                "reason": "bank_auto_tag_rules_reapply_requested",
                "enqueued_jobs": ["bank_detail.read_model.refresh"],
            },
        )
        payload = self._app_settings_service.get_bank_auto_tag_rules_payload(
            can_save=can_save,
            read_model_status="refreshing",
        )
        payload["read_model_status"] = "refreshing"
        payload.update(self._bank_detail_reapply_contract_payload(scope_keys))
        payload["refresh_enqueued"] = True
        payload["refresh_reason"] = "bank_auto_tag_rules_reapply_requested"
        payload["enqueued_jobs"] = ["bank_detail.read_model.refresh"]
        return payload

    def confirm_category(self, transaction_id: str, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        active_rule_codes = set(self._active_bank_auto_tag_rule_codes())
        suggestion = self._latest_auto_category_suggestion(transaction_id)
        selection = confirmation_selection(
            payload=payload,
            suggestion=suggestion if isinstance(suggestion, dict) else None,
            active_rule_codes=active_rule_codes,
            transaction_id=transaction_id,
        )
        selected_code = str(selection["category_code"])
        candidate_codes = list(selection.get("candidate_category_codes") or [])
        with self._category_mutation_lock:
            before_snapshot = self._bank_transaction_category_service.snapshot()
            try:
                result = self._bank_transaction_category_service.confirm_auto_category(
                    transaction_id=transaction_id,
                    category_code=selected_code,
                    candidate_category_codes=candidate_codes,
                    rule_version=self._bank_transaction_auto_category_service.current_rule_version(),
                    actor=actor_id,
                    category_primary_label=selection.get("category_primary_label"),
                    category_sub_label=selection.get("category_sub_label"),
                    category_third_label=selection.get("category_third_label"),
                    category_label_path=list(selection.get("category_label_path") or []),
                    turnover_action_type=selection.get("turnover_action_type"),
                    turnover_family=selection.get("turnover_family"),
                )
                persisted = self._persist_category_mutation(
                    [transaction_id],
                    transaction_id=transaction_id,
                    mutation_type="confirmation_confirm",
                    actor_id=actor_id,
                    action="bank_detail_category_confirmed",
                    metadata={
                        "selected_category_code": selected_code,
                        "selected_category_third_label": selection.get("category_third_label"),
                        "candidate_category_codes": candidate_codes,
                    },
                )
            except Exception:
                self._bank_transaction_category_service.restore_snapshot(before_snapshot)
                raise
        affected_months = list(persisted.get("affected_months") or [])
        return {
            **result,
            **self._bank_detail_access_scope_payload(affected_months),
            **persisted,
            "affected_months": affected_months,
        }

    def revoke_category_confirmation(self, transaction_id: str, *, actor_id: str) -> dict[str, Any]:
        with self._category_mutation_lock:
            before_snapshot = self._bank_transaction_category_service.snapshot()
            try:
                result = self._bank_transaction_category_service.revoke_auto_category_confirmation(
                    transaction_id=transaction_id,
                    actor=actor_id,
                )
                persisted = self._persist_category_mutation(
                    [transaction_id],
                    transaction_id=transaction_id,
                    mutation_type="confirmation_revoke",
                    actor_id=actor_id,
                    action="bank_detail_category_confirmation_revoked",
                    metadata={},
                )
            except Exception:
                self._bank_transaction_category_service.restore_snapshot(before_snapshot)
                raise
        affected_months = list(persisted.get("affected_months") or [])
        return {
            **result,
            **self._bank_detail_access_scope_payload(affected_months),
            **persisted,
            "affected_months": affected_months,
        }

    def assign_manual_category(self, transaction_id: str, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        selection = manual_assignment_selection(payload)
        selected_code = str(selection["category_code"])
        suggestion = self._latest_auto_category_suggestion(transaction_id)
        previous_resolution_status = "unmatched"
        if isinstance(suggestion, dict):
            previous_resolution_status = str(suggestion.get("category_resolution_status") or "unmatched") or "unmatched"
        if previous_resolution_status != "unmatched":
            raise BankTransactionCategoryValidationError(
                "invalid_manual_category_assignment_target",
                "当前流水已有自动标签或候选确认状态，不能走人工待分类入口。",
                transaction_id=transaction_id,
            )
        if selected_code not in set(self._active_bank_auto_tag_rule_codes()):
            raise BankTransactionCategoryValidationError(
                "invalid_manual_category_assignment_candidate",
                "只能选择当前自动标签规则中的可用标签。",
                transaction_id=transaction_id,
            )
        with self._category_mutation_lock:
            before_snapshot = self._bank_transaction_category_service.snapshot()
            try:
                result = self._bank_transaction_category_service.assign_manual_category(
                    transaction_id=transaction_id,
                    category_code=selected_code,
                    actor=actor_id,
                    category_primary_label=selection.get("category_primary_label"),
                    category_sub_label=selection.get("category_sub_label"),
                    category_third_label=selection.get("category_third_label"),
                    category_label_path=list(selection.get("category_label_path") or []),
                    turnover_action_type=selection.get("turnover_action_type"),
                    turnover_family=selection.get("turnover_family"),
                )
                persisted = self._persist_category_mutation(
                    [transaction_id],
                    transaction_id=transaction_id,
                    mutation_type="manual_assign",
                    actor_id=actor_id,
                    action="bank_detail_category_manually_assigned",
                    metadata={
                        "selected_category_code": selected_code,
                        "selected_category_third_label": selection.get("category_third_label"),
                        "previous_resolution_status": previous_resolution_status,
                        "assignment_source": "manual",
                    },
                )
            except Exception:
                self._bank_transaction_category_service.restore_snapshot(before_snapshot)
                raise
        affected_months = list(persisted.get("affected_months") or [])
        return {
            **result,
            **self._bank_detail_access_scope_payload(affected_months),
            **persisted,
            "affected_months": affected_months,
        }

    def clear_manual_category(self, transaction_id: str, *, actor_id: str) -> dict[str, Any]:
        with self._category_mutation_lock:
            before_snapshot = self._bank_transaction_category_service.snapshot()
            try:
                result = self._bank_transaction_category_service.clear_manual_category(
                    transaction_id=transaction_id,
                    actor=actor_id,
                )
                persisted = self._persist_category_mutation(
                    [transaction_id],
                    transaction_id=transaction_id,
                    mutation_type="manual_clear",
                    actor_id=actor_id,
                    action="bank_detail_category_manual_assignment_cleared",
                    metadata={"assignment_source": "manual"},
                )
            except Exception:
                self._bank_transaction_category_service.restore_snapshot(before_snapshot)
                raise
        affected_months = list(persisted.get("affected_months") or [])
        return {
            **result,
            **self._bank_detail_access_scope_payload(affected_months),
            **persisted,
            "affected_months": affected_months,
        }

    def export_transactions(
        self,
        *,
        mode: str,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None,
        category_primary_label: str | None,
        category_sub_label: str | None,
        category_third_label: str | None,
        actor_id: str,
    ) -> BankDetailsExportResult:
        service = BankDetailsExportService(
            transaction_page_loader=self._export_transaction_page,
            account_loader=self._export_accounts,
        )
        result = service.export(
            mode=mode,
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
        )
        self._audit_service.record_action(
            actor_id=actor_id,
            action="bank_detail_export_downloaded",
            entity_type="bank_detail_export",
            entity_id=result.filename,
            metadata={
                "mode": str(mode or "all"),
                "filters": {
                    "account_key": account_key,
                    "date_from": date_from,
                    "date_to": date_to,
                    "keyword": keyword,
                    "category_code": category_code,
                    "category_primary_label": category_primary_label,
                    "category_sub_label": category_sub_label,
                    "category_third_label": category_third_label,
                },
                "row_count": result.row_count,
                "sheet_names": result.sheet_names,
                "filename": result.filename,
            },
        )
        return result

    def _accounts_from_sql_read_model(self, *, date_from: str | None, date_to: str | None) -> dict[str, object] | None:
        repository = self._bank_account_balance_read_model_repository
        if repository is None:
            enqueued = self._enqueue_read_model_refreshes(["all"], reason="api_sql_repository_unavailable")
            return self._accounts_refreshing_payload(
                scope_keys=["all"],
                date_from=date_from,
                date_to=date_to,
                refresh_enqueued=enqueued,
                refresh_reason="api_sql_repository_unavailable",
            )
        account_balance_loader = getattr(repository, "list_bank_account_balances", None)
        if callable(account_balance_loader):
            try:
                payload = account_balance_loader(date_from=date_from, date_to=date_to)
            except Exception as error:
                if self._is_missing_bank_account_balance_read_model_error(error):
                    enqueued = self._enqueue_bank_account_balance_refresh(reason="api_migration_missing")
                    return self._accounts_refreshing_payload(
                        scope_keys=["all"],
                        date_from=date_from,
                        date_to=date_to,
                        scope_summary={
                            "read_model_status": "refreshing",
                            "balance_read_model_status": "missing",
                            "read_model_scope_keys": ["all"],
                            "read_model_error": "bank_account_balance_read_model_not_migrated",
                        },
                        refresh_enqueued=enqueued,
                        refresh_reason="api_migration_missing",
                    )
                raise
            if not isinstance(payload, dict):
                enqueued = self._enqueue_bank_account_balance_refresh(reason="api_miss")
                return self._accounts_refreshing_payload(
                    scope_keys=["all"],
                    date_from=date_from,
                    date_to=date_to,
                    refresh_enqueued=enqueued,
                    refresh_reason="api_miss",
                )
            payload_status = str(payload.get("balance_read_model_status") or payload.get("read_model_status") or "fresh")
            if payload_status != "fresh" and not (payload.get("accounts") or []):
                enqueued = self._enqueue_bank_account_balance_refresh(reason=f"api_{payload_status or 'stale'}")
                return self._accounts_refreshing_payload(
                    scope_keys=["all"],
                    date_from=date_from,
                    date_to=date_to,
                    scope_summary=payload,
                    refresh_enqueued=enqueued,
                    refresh_reason=f"api_{payload_status or 'stale'}",
                )
            result = dict(payload)
            result["read_model_status"] = payload_status
            result["balance_read_model_status"] = payload_status
            result["cache_status"] = "uncached"
            if payload_status != "fresh":
                result.setdefault("refresh_reason", f"api_{payload_status}")
            return result

        scope_keys = self._scope_keys_for_range(date_from=date_from, date_to=date_to)
        scope_summary = self._scope_summary(scope_keys)
        read_model_status = str(scope_summary.get("read_model_status") or "missing")
        refresh_enqueued = False
        refresh_reason = ""
        if read_model_status == "missing":
            refresh_reason = "api_missing"
            refresh_enqueued = self._enqueue_read_model_refreshes_unless_refreshing(
                scope_keys,
                reason=refresh_reason,
                scope_summary=scope_summary,
            )
            return self._accounts_refreshing_payload(
                scope_keys=scope_keys,
                date_from=date_from,
                date_to=date_to,
                scope_summary=scope_summary,
                refresh_enqueued=refresh_enqueued,
                refresh_reason=refresh_reason,
            )
        if read_model_status != "fresh":
            refresh_reason = f"api_{read_model_status}"
            refresh_enqueued = self._enqueue_read_model_refreshes_unless_refreshing(
                scope_keys,
                reason=refresh_reason,
                scope_summary=scope_summary,
            )
        cache_key = self._redis_cache_key("accounts", {"date_from": date_from, "date_to": date_to}, scope_summary=scope_summary)
        cached = self._get_cached_payload(cache_key) if read_model_status == "fresh" else None
        if cached is not None:
            cached["cache_status"] = "hit"
            return cached
        loader = getattr(repository, "list_bank_detail_accounts", None)
        if not callable(loader):
            enqueued = self._enqueue_read_model_refreshes(scope_keys, reason="api_sql_repository_unavailable")
            return self._accounts_refreshing_payload(
                scope_keys=scope_keys,
                date_from=date_from,
                date_to=date_to,
                refresh_enqueued=enqueued,
                refresh_reason="api_sql_repository_unavailable",
            )
        payload = loader(date_from=date_from, date_to=date_to)
        if not isinstance(payload, dict):
            enqueued = self._enqueue_read_model_refreshes(scope_keys, reason="api_miss")
            return self._accounts_refreshing_payload(
                scope_keys=scope_keys,
                date_from=date_from,
                date_to=date_to,
                refresh_enqueued=enqueued,
                refresh_reason="api_miss",
            )
        payload_status = str(payload.get("read_model_status") or read_model_status or "fresh")
        if read_model_status != "fresh":
            payload = {**payload, **scope_summary, "read_model_status": read_model_status}
            payload_status = read_model_status
        if payload_status != "fresh" and not (payload.get("accounts") or []):
            refresh_reason = f"api_{payload_status or 'stale'}"
            refresh_enqueued = self._enqueue_read_model_refreshes_unless_refreshing(
                scope_keys,
                reason=refresh_reason,
                scope_summary=payload,
            )
            return self._accounts_refreshing_payload(
                scope_keys=scope_keys,
                date_from=date_from,
                date_to=date_to,
                scope_summary=payload,
                refresh_enqueued=refresh_enqueued,
                refresh_reason=refresh_reason,
            )
        result = dict(payload)
        result["read_model_status"] = payload_status
        result["cache_status"] = "miss" if payload_status == "fresh" else "stale"
        if payload_status != "fresh":
            result["refresh_enqueued"] = refresh_enqueued
            result["refresh_reason"] = refresh_reason or f"api_{payload_status}"
        if payload_status == "fresh":
            self._set_cached_payload(cache_key, result)
        return result

    def _transactions_from_sql_read_model(
        self,
        *,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None,
        category_primary_label: str | None,
        category_sub_label: str | None,
        category_third_label: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, object] | None:
        repository = self._bank_detail_sql_read_repository
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 100), 1), 100)
        if repository is None:
            enqueued = self._enqueue_read_model_refreshes(["all"], reason="api_sql_repository_unavailable")
            return self._transactions_refreshing_payload(
                scope_keys=["all"],
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                page=normalized_page,
                page_size=normalized_page_size,
                refresh_enqueued=enqueued,
                refresh_reason="api_sql_repository_unavailable",
            )
        scope_keys = self._scope_keys_for_range(date_from=date_from, date_to=date_to)
        scope_summary = self._scope_summary(scope_keys)
        read_model_status = str(scope_summary.get("read_model_status") or "missing")
        statistics_status = str(scope_summary.get("statistics_status") or "missing")
        statistics_refresh_enqueued = False
        refresh_enqueued = False
        refresh_reason = ""
        if read_model_status == "missing":
            refresh_reason = "api_missing"
            refresh_enqueued = self._enqueue_read_model_refreshes_unless_refreshing(
                scope_keys,
                reason=refresh_reason,
                scope_summary=scope_summary,
            )
            return self._transactions_refreshing_payload(
                scope_keys=scope_keys,
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                page=normalized_page,
                page_size=normalized_page_size,
                scope_summary=scope_summary,
                refresh_enqueued=refresh_enqueued,
                refresh_reason=refresh_reason,
            )
        if read_model_status != "fresh":
            refresh_reason = f"api_{read_model_status}"
            refresh_enqueued = self._enqueue_read_model_refreshes_unless_refreshing(
                scope_keys,
                reason=refresh_reason,
                scope_summary=scope_summary,
            )
        if statistics_status not in {"fresh", "refreshing"}:
            selected_scope_keys = set(scope_keys) if refresh_enqueued else set()
            statistics_scope_keys = [
                scope_key
                for scope_key in list(scope_summary.get("statistics_scope_keys") or scope_keys)
                if scope_key not in selected_scope_keys
            ]
            if statistics_scope_keys:
                statistics_refresh_enqueued = self._enqueue_read_model_refreshes(
                    statistics_scope_keys,
                    reason=f"api_statistics_{statistics_status}",
                )
        cache_key = self._redis_cache_key(
            "transactions",
            {
                "account_key": account_key,
                "date_from": date_from,
                "date_to": date_to,
                "keyword": keyword,
                "category_code": category_code,
                "category_primary_label": category_primary_label,
                "category_sub_label": category_sub_label,
                "category_third_label": category_third_label,
                "page": normalized_page,
                "page_size": normalized_page_size,
            },
            scope_summary=scope_summary,
        )
        cached = (
            self._get_cached_payload(cache_key)
            if read_model_status == "fresh" and statistics_status == "fresh"
            else None
        )
        if cached is not None:
            cached["cache_status"] = "hit"
            return self._with_tag_dictionary(cached)
        loader = getattr(repository, "list_bank_detail_transactions", None)
        if not callable(loader):
            enqueued = self._enqueue_read_model_refreshes(scope_keys, reason="api_sql_repository_unavailable")
            return self._transactions_refreshing_payload(
                scope_keys=scope_keys,
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                page=normalized_page,
                page_size=normalized_page_size,
                refresh_enqueued=enqueued,
                refresh_reason="api_sql_repository_unavailable",
            )
        payload = loader(
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
            page=normalized_page,
            page_size=normalized_page_size,
        )
        if not isinstance(payload, dict):
            enqueued = self._enqueue_read_model_refreshes(scope_keys, reason="api_miss")
            return self._transactions_refreshing_payload(
                scope_keys=scope_keys,
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                page=normalized_page,
                page_size=normalized_page_size,
                refresh_enqueued=enqueued,
                refresh_reason="api_miss",
            )
        payload_status = str(payload.get("read_model_status") or read_model_status or "fresh")
        payload = {
            **payload,
            **{
                key: scope_summary.get(key)
                for key in (
                    "statistics",
                    "statistics_status",
                    "statistics_scope_keys",
                    "statistics_signature",
                )
                if key in scope_summary
            },
        }
        if read_model_status != "fresh":
            payload = {**payload, **scope_summary, "read_model_status": read_model_status}
            payload_status = read_model_status
        if payload_status != "fresh" and not (payload.get("rows") or []):
            refresh_reason = f"api_{payload_status or 'stale'}"
            refresh_enqueued = self._enqueue_read_model_refreshes_unless_refreshing(
                scope_keys,
                reason=refresh_reason,
                scope_summary=payload,
            )
            return self._transactions_refreshing_payload(
                scope_keys=scope_keys,
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                page=normalized_page,
                page_size=normalized_page_size,
                scope_summary=payload,
                refresh_enqueued=refresh_enqueued,
                refresh_reason=refresh_reason,
            )
        result = self._with_tag_dictionary(dict(payload))
        result["read_model_status"] = payload_status
        result["cache_status"] = "miss" if payload_status == "fresh" else "stale"
        if statistics_refresh_enqueued:
            result["statistics_refresh_enqueued"] = True
        if payload_status != "fresh":
            result["refresh_enqueued"] = refresh_enqueued
            result["refresh_reason"] = refresh_reason or f"api_{payload_status}"
        if payload_status == "fresh" and str(result.get("statistics_status") or "") == "fresh":
            self._set_cached_payload(cache_key, result)
        return result

    def _persist_category_mutation(
        self,
        transaction_ids: list[str],
        *,
        transaction_id: str,
        mutation_type: str,
        actor_id: str,
        action: str,
        metadata: dict[str, object],
    ) -> dict[str, object]:
        affected_months = self._affected_months_provider(transaction_ids)
        if self._category_mutation_writer is not None:
            persisted = dict(
                self._category_mutation_writer.persist(
                    transaction_id=transaction_id,
                    mutation_type=mutation_type,
                    record=self._bank_transaction_category_service.get(transaction_id),
                    actor_id=actor_id,
                    action=action,
                    metadata=metadata,
                )
                or {}
            )
            affected_months = list(persisted.get("affected_months") or affected_months)
            self._audit_service.record_action(
                actor_id=actor_id,
                action=action,
                entity_type="bank_transaction_category",
                entity_id=str(transaction_id or ""),
                metadata={
                    "transaction_id": str(transaction_id or ""),
                    "affected_months": affected_months,
                    "persistent_audit": True,
                    **dict(metadata),
                },
            )
            return {**persisted, "affected_months": affected_months}
        if self._bank_transaction_category_store is None:
            raise RuntimeError("durable bank transaction category writer is unavailable")
        if self._bank_transaction_category_store is not None:
            self._bank_transaction_category_store.save_bank_transaction_categories(
                self._bank_transaction_category_service.snapshot()
            )
        self._audit_service.record_action(
            actor_id=actor_id,
            action=action,
            entity_type="bank_transaction_category",
            entity_id=str(transaction_id or ""),
            metadata={
                "transaction_id": str(transaction_id or ""),
                "affected_months": list(affected_months or []),
                **dict(metadata),
            },
        )
        return {"changed": True, "affected_months": affected_months}

    def _latest_auto_category_suggestion(self, transaction_id: str) -> dict[str, object] | None:
        if callable(self._suggestion_provider):
            return self._suggestion_provider(transaction_id)
        return None

    def _scope_keys_for_range(self, *, date_from: str | None, date_to: str | None) -> list[str]:
        scope_key_loader = getattr(self._bank_detail_sql_read_repository, "bank_detail_scope_keys_for_range", None)
        if callable(scope_key_loader):
            return list(scope_key_loader(date_from=date_from, date_to=date_to) or ["all"])
        months: set[str] = set()
        for value in (date_from, date_to):
            month = str(value or "")[:7]
            if SEARCH_MONTH_RE.match(month):
                months.add(month)
        return sorted(months) or ["all"]

    def _refresh_scope_keys_from_auto_tag_rules_payload(self, payload: dict[str, object]) -> list[str]:
        refresh_scope = payload.get("refresh_scope") if isinstance(payload.get("refresh_scope"), dict) else {}
        date_from = str(refresh_scope.get("date_from") or "").strip() if isinstance(refresh_scope, dict) else ""
        date_to = str(refresh_scope.get("date_to") or "").strip() if isinstance(refresh_scope, dict) else ""
        if not date_from and not date_to:
            return []
        return [
            scope_key
            for scope_key in self._scope_keys_for_range(date_from=date_from or None, date_to=date_to or None)
            if scope_key and scope_key != "all"
        ]

    def _bank_detail_access_scope_payload(self, scope_keys: list[str]) -> dict[str, object]:
        target_scope_keys = self._bank_detail_concrete_scope_keys(scope_keys)
        return {
            "affected_scope_keys": target_scope_keys,
            "read_model_scope_keys": target_scope_keys,
        }

    def _bank_detail_reapply_contract_payload(self, scope_keys: list[str]) -> dict[str, object]:
        target_scope_keys = self._bank_detail_concrete_scope_keys(scope_keys)
        return write_target_envelope(
            scope_keys=target_scope_keys,
            targets=self._bank_detail_freshness_targets(target_scope_keys),
        )

    def _bank_detail_freshness_targets(self, scope_keys: list[str]) -> list[dict[str, str]]:
        return [
            {"read_model_key": "bank_detail", "scope_key": scope_key}
            for scope_key in self._bank_detail_concrete_scope_keys(scope_keys)
        ]

    @staticmethod
    def _bank_detail_concrete_scope_keys(scope_keys: list[str]) -> list[str]:
        normalized = [
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if str(scope_key).strip()
        ]
        return list(dict.fromkeys(scope_key for scope_key in normalized if SEARCH_MONTH_RE.match(scope_key)))

    def _scope_summary(self, scope_keys: list[str]) -> dict[str, object]:
        summary_loader = getattr(self._bank_detail_sql_read_repository, "bank_detail_scope_summary", None)
        if callable(summary_loader):
            summary = summary_loader(scope_keys=scope_keys)
            if isinstance(summary, dict):
                return self._with_page_relation_freshness(
                    self._with_auto_tag_rule_freshness(summary),
                    scope_keys=scope_keys,
                )
        return {
            "read_model_status": "missing",
            "read_model_scope_keys": scope_keys,
            "read_model_generated_at": None,
            "read_model_scope_signatures": {},
        }

    def _with_page_relation_freshness(
        self,
        scope_summary: dict[str, object],
        *,
        scope_keys: list[str],
    ) -> dict[str, object]:
        concrete_scope_keys = self._bank_detail_concrete_scope_keys(scope_keys)
        relation_status_loader = getattr(self._workbench_relation_reader, "source_versions_for_scopes", None)
        if not concrete_scope_keys or not callable(relation_status_loader):
            return scope_summary
        relation_status_payload = relation_status_loader(
            concrete_scope_keys,
            require_fresh=True,
            reason="bank_details_page_access",
        )
        if not isinstance(relation_status_payload, dict):
            relation_status_payload = {
                "status": "unavailable",
                "refresh_enqueued": False,
                "stale_reasons": ["workbench_relation_status_unavailable"],
            }
        relation_status = str(relation_status_payload.get("status") or "unavailable")
        result = dict(scope_summary)
        result["read_model_dependency_statuses"] = {"workbench_relation": relation_status}
        if relation_status == "fresh":
            return result
        current_status = str(result.get("read_model_status") or "missing")
        if current_status == "fresh":
            result["read_model_status"] = (
                "refreshing"
                if bool(relation_status_payload.get("refresh_enqueued"))
                else relation_status
            )
        result["read_model_stale_reasons"] = list(
            dict.fromkeys(
                [
                    *list(result.get("read_model_stale_reasons") or []),
                    *[
                        f"workbench_relation:{reason}"
                        for reason in list(relation_status_payload.get("stale_reasons") or [])
                        if str(reason).strip()
                    ],
                ]
            )
        )
        return result

    def _with_auto_tag_rule_freshness(self, scope_summary: dict[str, object]) -> dict[str, object]:
        if str(scope_summary.get("read_model_status") or "") != "fresh":
            return scope_summary
        expected_version = self._current_bank_auto_tag_rules_version()
        signatures = scope_summary.get("read_model_scope_signatures") if isinstance(scope_summary.get("read_model_scope_signatures"), dict) else {}
        statistics_signatures = (
            scope_summary.get("statistics_scope_signatures")
            if isinstance(scope_summary.get("statistics_scope_signatures"), dict)
            else {}
        )

        def stale_scope_keys_for(signature_rows: dict[str, object]) -> list[str]:
            stale_scope_keys: list[str] = []
            for scope_key, signature in signature_rows.items():
                if not isinstance(signature, dict):
                    stale_scope_keys.append(str(scope_key))
                    continue
                source_versions = signature.get("source_versions") if isinstance(signature.get("source_versions"), dict) else {}
                actual_version = self._int_or_none(source_versions.get("bank_auto_tag_rules_version"))
                if actual_version != expected_version:
                    stale_scope_keys.append(str(scope_key))
            return stale_scope_keys

        stale_scope_keys = stale_scope_keys_for(signatures)
        statistics_stale_scope_keys = stale_scope_keys_for(statistics_signatures)
        if not stale_scope_keys and not statistics_stale_scope_keys:
            return scope_summary
        result = dict(scope_summary)
        if statistics_stale_scope_keys:
            result["statistics"] = None
            result["statistics_status"] = "stale"
            result["statistics_stale_scope_keys"] = statistics_stale_scope_keys
        if not stale_scope_keys:
            return result
        result["read_model_status"] = "stale"
        result["read_model_stale_reasons"] = [
            *list(result.get("read_model_stale_reasons") or []),
            "bank_auto_tag_rules_version_mismatch",
        ]
        result["bank_auto_tag_rules_version"] = expected_version
        result["bank_auto_tag_rules_stale_scope_keys"] = stale_scope_keys
        return result

    def _accounts_refreshing_payload(
        self,
        *,
        scope_keys: list[str],
        date_from: str | None,
        date_to: str | None,
        scope_summary: dict[str, object] | None = None,
        refresh_enqueued: bool = False,
        refresh_reason: str = "",
    ) -> dict[str, object]:
        summary = dict(scope_summary or {})
        return {
            "accounts": [],
            "total_balance": None,
            "balance_account_count": 0,
            "missing_balance_account_count": 0,
            "read_model_status": "refreshing",
            **({"balance_read_model_status": summary.get("balance_read_model_status")} if summary.get("balance_read_model_status") is not None else {}),
            **({"read_model_error": summary.get("read_model_error")} if summary.get("read_model_error") is not None else {}),
            "read_model_scope_keys": list(summary.get("read_model_scope_keys") or scope_keys),
            "read_model_generated_at": summary.get("read_model_generated_at"),
            "read_model_stale_reasons": list(summary.get("read_model_stale_reasons") or []),
            "read_model_dependency_statuses": dict(summary.get("read_model_dependency_statuses") or {}),
            "refresh_enqueued": refresh_enqueued,
            "refresh_reason": refresh_reason,
            "date_from": date_from,
            "date_to": date_to,
            "cache_status": "bypass",
        }

    def _transactions_refreshing_payload(
        self,
        *,
        scope_keys: list[str],
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        page: int,
        page_size: int,
        scope_summary: dict[str, object] | None = None,
        refresh_enqueued: bool = False,
        refresh_reason: str = "",
    ) -> dict[str, object]:
        summary = dict(scope_summary or {})
        return self._with_tag_dictionary(
            {
                "account_key": account_key,
                "date_from": date_from,
                "date_to": date_to,
                "rows": [],
                "category_counts": {"uncategorized": 0},
                "pagination": {"page": page, "page_size": page_size, "total": 0},
                "statistics": None,
                "statistics_status": str(summary.get("statistics_status") or "refreshing"),
                "read_model_status": "refreshing",
                "read_model_scope_keys": list(summary.get("read_model_scope_keys") or scope_keys),
                "read_model_generated_at": summary.get("read_model_generated_at"),
                "read_model_stale_reasons": list(summary.get("read_model_stale_reasons") or []),
                "read_model_dependency_statuses": dict(summary.get("read_model_dependency_statuses") or {}),
                "refresh_enqueued": refresh_enqueued,
                "refresh_reason": refresh_reason,
                "cache_status": "bypass",
            }
        )

    def _with_tag_dictionary(self, payload: dict[str, object]) -> dict[str, object]:
        if callable(self._bank_transaction_tags_provider):
            payload.setdefault("bank_transaction_tags", self._bank_transaction_tags_provider())
        return payload

    def _export_accounts(self, *, date_from: str | None, date_to: str | None) -> dict[str, object]:
        payload = self.accounts_payload(date_from=date_from, date_to=date_to)
        if payload.get("read_model_status") == "refreshing":
            raise BankDetailsReadModelRefreshingError(payload)
        return payload

    def _export_transaction_page(
        self,
        *,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None,
        category_primary_label: str | None,
        category_sub_label: str | None,
        category_third_label: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        payload = self.transactions_payload(
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
            page=page,
            page_size=page_size,
        )
        if payload.get("read_model_status") == "refreshing":
            raise BankDetailsReadModelRefreshingError(payload)
        return payload

    def _enqueue_read_model_refreshes_unless_refreshing(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        scope_summary: dict[str, object],
    ) -> bool:
        if str(scope_summary.get("read_model_status") or "").strip() == "refreshing":
            return False
        return self._enqueue_read_model_refreshes(scope_keys, reason=reason)

    def _enqueue_read_model_refreshes(self, scope_keys: list[str], *, reason: str) -> bool:
        queue_repository = getattr(self._runtime_repositories, "queue_repository", None)
        refresh_gateway = ReadModelRefreshGateway(queue_repository=queue_repository)
        if not refresh_gateway.can_enqueue():
            return False
        target_scope_keys = [str(item).strip() for item in list(scope_keys or []) if str(item).strip()]
        for scope_key in target_scope_keys:
            self._delete_redis_cache(scope_key)
        return bool(refresh_gateway.enqueue_many("bank_detail", target_scope_keys, reason=reason))

    def _redis_cache_key(self, kind: str, query: dict[str, object], *, scope_summary: dict[str, object]) -> str:
        signature = {
            "kind": kind,
            "query": query,
            "scope_signatures": scope_summary.get("read_model_scope_signatures") or {},
            "statistics_signature": scope_summary.get("statistics_signature") or "missing",
            "schema": f"bank_detail:v{BANK_DETAIL_READ_MODEL_SCHEMA_VERSION}",
        }
        digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return f"bank_detail:{kind}:{digest}"

    def _get_cached_payload(self, cache_key: str) -> dict[str, object] | None:
        redis_helper = getattr(self._runtime_repositories, "redis_helper", None)
        get_cached = getattr(redis_helper, "get_json", None)
        if not callable(get_cached):
            return None
        try:
            cached = get_cached(cache_key)
            return dict(cached) if isinstance(cached, dict) else None
        except Exception:
            return None

    def _set_cached_payload(self, cache_key: str, payload: dict[str, object]) -> None:
        redis_helper = getattr(self._runtime_repositories, "redis_helper", None)
        set_cached = getattr(redis_helper, "set_json", None)
        if not callable(set_cached):
            return
        try:
            set_cached(cache_key, payload, ttl_seconds=30)
        except Exception:
            return

    def _delete_redis_cache(self, scope_key: str) -> None:
        redis_helper = getattr(self._runtime_repositories, "redis_helper", None)
        publish_wakeup = getattr(redis_helper, "publish_wakeup", None)
        if callable(publish_wakeup):
            try:
                publish_wakeup("bank_detail_read_model_refresh", {"scope_key": scope_key})
            except Exception:
                pass

    def _current_bank_auto_tag_rules_version(self) -> int:
        try:
            payload = self._app_settings_service.get_bank_auto_tag_rules_payload(can_save=False)
        except Exception:
            return 1
        return self._int_or_none(payload.get("version")) or 1

    def _active_bank_auto_tag_rule_codes(self) -> list[str]:
        payload = self._app_settings_service.get_bank_auto_tag_rules_payload(can_save=False)
        active_rules = payload.get("active_rules") if isinstance(payload, dict) else []
        codes: list[str] = []
        seen: set[str] = set()
        if not isinstance(active_rules, list):
            return codes
        for rule in active_rules:
            if not isinstance(rule, dict):
                continue
            code = str(rule.get("code") or "").strip()
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    @staticmethod
    def _is_missing_bank_account_balance_read_model_error(error: Exception) -> bool:
        message = str(error).lower()
        return (
            "read_model.bank_account_balances" in message
            and ("does not exist" in message or "undefinedtable" in error.__class__.__name__.lower())
        )

    @staticmethod
    def _int_or_none(value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
