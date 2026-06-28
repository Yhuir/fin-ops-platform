from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
import re
from typing import Any, Callable

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.bank_detail_category_side_effects import BankDetailCategoryMutationSideEffectPort
from fin_ops_platform.services.bank_detail_category_selection import confirmation_selection, manual_assignment_selection
from fin_ops_platform.services.bank_details_export_service import (
    BankDetailsExportResult,
    BankDetailsExportService,
)
from fin_ops_platform.services.bank_details_service import BankDetailsService
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryService,
    BankTransactionCategoryValidationError,
)


SEARCH_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class BankDetailsApplicationService:
    def __init__(
        self,
        *,
        import_service: Any,
        bank_details_service: BankDetailsService,
        app_settings_service: AppSettingsService,
        bank_transaction_category_service: BankTransactionCategoryService,
        bank_transaction_auto_category_service: BankTransactionAutoCategoryService,
        audit_service: AuditTrailService,
        state_store: Any | None,
        runtime_repositories: Any | None,
        affected_months_provider: Callable[[list[str]], list[str]],
        invalidate_after_category_mutation: Callable[[list[str]], bool],
        execute_derived_data_lifecycle_event: Callable[..., Any],
        clear_turnover_ledger_read_model: Callable[[], Any],
        clear_relation_tag_projection_cache: Callable[[], Any],
        available_month_scope_keys_provider: Callable[[], list[str]],
        enqueue_turnover_ledger_refresh: Callable[..., bool] | None = None,
        suggestion_provider: Callable[[str], dict[str, object] | None] | None = None,
        category_mutation_side_effects: BankDetailCategoryMutationSideEffectPort | None = None,
    ) -> None:
        self._import_service = import_service
        self._bank_details_service = bank_details_service
        self._app_settings_service = app_settings_service
        self._bank_transaction_category_service = bank_transaction_category_service
        self._bank_transaction_auto_category_service = bank_transaction_auto_category_service
        self._audit_service = audit_service
        self._state_store = state_store
        self._runtime_repositories = runtime_repositories
        self._affected_months_provider = affected_months_provider
        self._invalidate_after_category_mutation = invalidate_after_category_mutation
        self._execute_derived_data_lifecycle_event = execute_derived_data_lifecycle_event
        self._clear_turnover_ledger_read_model = clear_turnover_ledger_read_model
        self._clear_relation_tag_projection_cache = clear_relation_tag_projection_cache
        self._available_month_scope_keys_provider = available_month_scope_keys_provider
        self._enqueue_turnover_ledger_refresh = enqueue_turnover_ledger_refresh
        self._suggestion_provider = suggestion_provider
        self._category_mutation_side_effects = category_mutation_side_effects

    def accounts_payload(self, *, date_from: str | None, date_to: str | None) -> dict[str, object]:
        return dict(self._bank_details_service.list_accounts(date_from=date_from, date_to=date_to))

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
        return dict(
            self._bank_details_service.list_transactions(
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
        )

    def get_auto_tag_rules_payload(self, *, can_save: bool) -> dict[str, Any]:
        return self._app_settings_service.get_bank_auto_tag_rules_payload(can_save=can_save)

    def update_auto_tag_rules(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        priority_scope_keys = self._refresh_scope_keys_from_auto_tag_rules_payload(payload)
        result = self._app_settings_service.update_bank_auto_tag_rules(
            payload,
            actor_id=actor_id,
            after_bank_auto_tag_rules_saved=lambda event: self.finalize_auto_tag_rules_update(
                {
                    **dict(event),
                    **({"bank_detail_priority_scope_keys": priority_scope_keys} if priority_scope_keys else {}),
                }
            ),
        )
        return {
            **result,
            **self._bank_detail_refresh_contract_payload(priority_scope_keys),
        }

    def replace_auto_tag_rules_from_file_source(self, source: object, *, actor_id: str) -> dict[str, Any]:
        result = self._app_settings_service.replace_bank_auto_tag_rules_from_file_source(
            source,
            actor_id=actor_id,
            after_bank_auto_tag_rules_saved=self.finalize_auto_tag_rules_update,
        )
        return {
            **result,
            **self._bank_detail_refresh_contract_payload([]),
        }

    def reapply_auto_tag_rules(self, *, actor_id: str, can_save: bool) -> dict[str, Any]:
        scope_keys = self._available_month_scope_keys_provider()
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
            },
        )
        self.finalize_auto_tag_rules_update(
            {
                "new_version": version,
                "bank_detail_priority_scope_keys": list(scope_keys),
            }
        )
        payload = self._app_settings_service.get_bank_auto_tag_rules_payload(can_save=can_save)
        payload.update(self._bank_detail_refresh_contract_payload(scope_keys))
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
        affected_months = self._persist_category_mutation(
            [transaction_id],
            transaction_id=transaction_id,
            actor_id=actor_id,
            action="bank_detail_category_confirmed",
            metadata={
                "selected_category_code": selected_code,
                "selected_category_third_label": selection.get("category_third_label"),
                "candidate_category_codes": candidate_codes,
            },
        )
        return {
            **result,
            "affected_months": affected_months,
            **self._bank_detail_refresh_contract_payload(affected_months),
        }

    def revoke_category_confirmation(self, transaction_id: str, *, actor_id: str) -> dict[str, Any]:
        result = self._bank_transaction_category_service.revoke_auto_category_confirmation(
            transaction_id=transaction_id,
            actor=actor_id,
        )
        affected_months = self._persist_category_mutation(
            [transaction_id],
            transaction_id=transaction_id,
            actor_id=actor_id,
            action="bank_detail_category_confirmation_revoked",
            metadata={},
        )
        return {
            **result,
            "affected_months": affected_months,
            **self._bank_detail_refresh_contract_payload(affected_months),
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
        affected_months = self._persist_category_mutation(
            [transaction_id],
            transaction_id=transaction_id,
            actor_id=actor_id,
            action="bank_detail_category_manually_assigned",
            metadata={
                "selected_category_code": selected_code,
                "selected_category_third_label": selection.get("category_third_label"),
                "previous_resolution_status": previous_resolution_status,
                "assignment_source": "manual",
            },
        )
        return {
            **result,
            "affected_months": affected_months,
            **self._bank_detail_refresh_contract_payload(affected_months),
        }

    def clear_manual_category(self, transaction_id: str, *, actor_id: str) -> dict[str, Any]:
        result = self._bank_transaction_category_service.clear_manual_category(
            transaction_id=transaction_id,
            actor=actor_id,
        )
        affected_months = self._persist_category_mutation(
            [transaction_id],
            transaction_id=transaction_id,
            actor_id=actor_id,
            action="bank_detail_category_manual_assignment_cleared",
            metadata={"assignment_source": "manual"},
        )
        return {
            **result,
            "affected_months": affected_months,
            **self._bank_detail_refresh_contract_payload(affected_months),
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

    def finalize_auto_tag_rules_update(self, event: dict[str, object]) -> None:
        self._clear_relation_tag_projection_cache()
        self._clear_turnover_ledger_read_model()
        self._enqueue_turnover_ledger_read_model_refreshes(["all"], reason="bank_auto_tag_rules_changed")
        priority_scope_keys = [
            str(scope_key).strip()
            for scope_key in list(event.get("bank_detail_priority_scope_keys") or [])
            if str(scope_key).strip() and str(scope_key).strip() != "all"
        ]
        self._execute_derived_data_lifecycle_event(
            "bank_auto_tag_rules_changed",
            scope_keys=["all"],
            include_all=True,
            metadata={
                "reason": "bank_auto_tag_rules_changed",
                "new_version": event.get("new_version"),
            },
            schedule_cost_warmup=False,
        )

    def _persist_category_mutation(
        self,
        transaction_ids: list[str],
        *,
        transaction_id: str,
        actor_id: str,
        action: str,
        metadata: dict[str, object],
    ) -> list[str]:
        affected_months = self._affected_months_provider(transaction_ids)
        if self._state_store is not None:
            self._state_store.save_bank_transaction_categories(self._bank_transaction_category_service.snapshot())
        if self._category_mutation_side_effects is not None:
            self._category_mutation_side_effects.after_mutation(
                transaction_id=transaction_id,
                actor_id=actor_id,
                action=action,
                affected_months=affected_months,
                metadata=metadata,
            )
        else:
            self._enqueue_turnover_ledger_read_model_refreshes(
                ["all"],
                reason="bank_detail_category_confirmation_changed",
            )
            self._invalidate_after_category_mutation(affected_months)
            self._audit_service.record_action(
                actor_id=actor_id,
                action=action,
                entity_type="bank_transaction_category_confirmation",
                entity_id=str(transaction_id or ""),
                metadata={
                    "transaction_id": str(transaction_id or ""),
                    "affected_months": list(affected_months or []),
                    **dict(metadata),
                },
            )
        return affected_months

    def _latest_auto_category_suggestion(self, transaction_id: str) -> dict[str, object] | None:
        if callable(self._suggestion_provider):
            return self._suggestion_provider(transaction_id)
        normalized_transaction_id = str(transaction_id or "").strip()
        transaction = self._import_service.get_transaction(normalized_transaction_id)
        row = self._serialize_value(transaction)
        if not isinstance(row, dict):
            row = dict(row or {})
        row["id"] = normalized_transaction_id
        input_row = self._bank_details_service.auto_category_input_row(row)
        return self._bank_transaction_auto_category_service.suggest_for_rows([input_row]).get(normalized_transaction_id)

    def _scope_keys_for_range(self, *, date_from: str | None, date_to: str | None) -> list[str]:
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

    def _bank_detail_refresh_contract_payload(self, scope_keys: list[str]) -> dict[str, object]:
        target_scope_keys = self._bank_detail_operation_scope_keys(scope_keys)
        return {"affected_scope_keys": target_scope_keys or ["all"]}

    def _bank_detail_operation_scope_keys(self, scope_keys: list[str]) -> list[str]:
        normalized = [
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if str(scope_key).strip()
        ]
        concrete = [scope_key for scope_key in normalized if scope_key != "all"]
        if not concrete:
            concrete = [
                str(scope_key).strip()
                for scope_key in list(self._available_month_scope_keys_provider() or [])
                if str(scope_key).strip() and str(scope_key).strip() != "all"
            ]
        return list(dict.fromkeys(concrete or normalized or ["all"]))

    def _export_accounts(self, *, date_from: str | None, date_to: str | None) -> dict[str, object]:
        return self.accounts_payload(date_from=date_from, date_to=date_to)

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
        return self.transactions_payload(
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

    def _enqueue_turnover_ledger_read_model_refreshes(self, scope_keys: list[str], *, reason: str) -> bool:
        enqueue = self._enqueue_turnover_ledger_refresh
        if callable(enqueue):
            return bool(enqueue(scope_keys, reason=reason))
        return False

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
    def _int_or_none(value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _serialize_value(value: object) -> object:
        if is_dataclass(value):
            return {key: BankDetailsApplicationService._serialize_value(val) for key, val in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): BankDetailsApplicationService._serialize_value(val) for key, val in value.items()}
        if isinstance(value, list):
            return [BankDetailsApplicationService._serialize_value(item) for item in value]
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        if isinstance(value, Enum):
            return value.value
        return value
