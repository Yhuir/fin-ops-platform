from __future__ import annotations

from threading import RLock
from typing import Any, Callable, Protocol

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.bank_detail_category_selection import (
    confirmation_selection,
    manual_assignment_selection,
)
from fin_ops_platform.services.bank_details_canonical_query import (
    BankDetailsCanonicalQueryService,
)
from fin_ops_platform.services.bank_details_export_service import (
    BankDetailsExportResult,
    BankDetailsExportService,
)
from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BankTransactionAutoCategoryService,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    BANK_AUTO_TAG_INTERNAL_TRANSFER_CODE,
    BankTransactionCategoryService,
    BankTransactionCategoryValidationError,
)


class BankTransactionCategoryStorePort(Protocol):
    def save_bank_transaction_categories(
        self,
        snapshot: dict[str, Any],
    ) -> None:
        ...


class BankDetailsCanonicalQueryUnavailableError(RuntimeError):
    """Raised when the canonical PostgreSQL page query boundary is unavailable."""


class BankDetailsApplicationService:
    def __init__(
        self,
        *,
        query_service: BankDetailsCanonicalQueryService | None = None,
        app_settings_service: AppSettingsService,
        bank_transaction_category_service: BankTransactionCategoryService,
        bank_transaction_auto_category_service: BankTransactionAutoCategoryService,
        audit_service: AuditTrailService,
        bank_transaction_category_store: BankTransactionCategoryStorePort | None,
        affected_months_provider: Callable[[list[str]], list[str]],
        suggestion_provider: Callable[[str], dict[str, object] | None] | None = None,
        category_mutation_service: Any | None = None,
    ) -> None:
        if bank_transaction_category_store is not None and not callable(
            getattr(
                bank_transaction_category_store,
                "save_bank_transaction_categories",
                None,
            )
        ):
            raise TypeError(
                "bank_transaction_category_store must provide "
                "save_bank_transaction_categories"
            )
        self._query_service = query_service
        self._app_settings_service = app_settings_service
        self._bank_transaction_category_service = (
            bank_transaction_category_service
        )
        self._bank_transaction_auto_category_service = (
            bank_transaction_auto_category_service
        )
        self._audit_service = audit_service
        self._bank_transaction_category_store = (
            bank_transaction_category_store
        )
        self._affected_months_provider = affected_months_provider
        self._suggestion_provider = suggestion_provider
        self._category_mutation_service = category_mutation_service
        self._category_mutation_lock = RLock()

    def accounts_payload(
        self,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> dict[str, object]:
        return self._canonical_query_service().accounts_payload(
            date_from=date_from,
            date_to=date_to,
        )

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
        return self._canonical_query_service().transactions_payload(
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

    def get_auto_tag_rules_payload(
        self,
        *,
        can_save: bool,
    ) -> dict[str, Any]:
        return self._app_settings_service.get_bank_auto_tag_rules_payload(
            can_save=can_save
        )

    def update_auto_tag_rules(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        return self._app_settings_service.update_bank_auto_tag_rules(
            payload,
            actor_id=actor_id,
        )

    def replace_auto_tag_rules_from_file_source(
        self,
        source: object,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        return (
            self._app_settings_service.replace_bank_auto_tag_rules_from_file_source(
                source,
                actor_id=actor_id,
            )
        )

    def reapply_auto_tag_rules(
        self,
        *,
        actor_id: str,
        can_save: bool,
    ) -> dict[str, Any]:
        version = self._current_bank_auto_tag_rules_version()
        self._audit_service.record_action(
            actor_id=actor_id,
            action="bank_auto_tag_rules_reapply_requested",
            entity_type="app_settings",
            entity_id="bank_auto_tag_rules",
            metadata={
                "version": version,
                "reason": "canonical_query_reapplied",
            },
        )
        payload = self._app_settings_service.get_bank_auto_tag_rules_payload(
            can_save=can_save
        )
        return payload

    def _canonical_query_service(self) -> BankDetailsCanonicalQueryService:
        if self._query_service is None:
            raise BankDetailsCanonicalQueryUnavailableError(
                "bank_details_canonical_postgres_query_repository_unavailable"
            )
        return self._query_service

    def confirm_category(
        self,
        transaction_id: str,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        active_rule_codes = set(self._active_bank_auto_tag_rule_codes())
        suggestion = self._latest_auto_category_suggestion(transaction_id)
        selection = confirmation_selection(
            payload=payload,
            suggestion=(
                suggestion if isinstance(suggestion, dict) else None
            ),
            active_rule_codes=active_rule_codes,
            transaction_id=transaction_id,
        )
        selected_code = str(selection["category_code"])
        candidate_codes = list(
            selection.get("candidate_category_codes") or []
        )
        with self._category_mutation_lock:
            before_snapshot = (
                self._bank_transaction_category_service.snapshot()
            )
            try:
                result = (
                    self._bank_transaction_category_service.confirm_auto_category(
                        transaction_id=transaction_id,
                        category_code=selected_code,
                        candidate_category_codes=candidate_codes,
                        rule_version=self._bank_transaction_auto_category_service.current_rule_version(),
                        actor=actor_id,
                        category_primary_label=selection.get(
                            "category_primary_label"
                        ),
                        category_sub_label=selection.get(
                            "category_sub_label"
                        ),
                        category_third_label=selection.get(
                            "category_third_label"
                        ),
                        category_label_path=list(
                            selection.get("category_label_path") or []
                        ),
                        turnover_action_type=selection.get(
                            "turnover_action_type"
                        ),
                        turnover_family=selection.get("turnover_family"),
                    )
                )
                persisted = self._persist_category_mutation(
                    [transaction_id],
                    transaction_id=transaction_id,
                    mutation_type="confirmation_confirm",
                    actor_id=actor_id,
                    action="bank_detail_category_confirmed",
                    metadata={
                        "selected_category_code": selected_code,
                        "selected_category_third_label": selection.get(
                            "category_third_label"
                        ),
                        "candidate_category_codes": candidate_codes,
                    },
                )
            except Exception:
                self._bank_transaction_category_service.restore_snapshot(
                    before_snapshot
                )
                raise
        return {**result, **persisted}

    def revoke_category_confirmation(
        self,
        transaction_id: str,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        with self._category_mutation_lock:
            before_snapshot = (
                self._bank_transaction_category_service.snapshot()
            )
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
                self._bank_transaction_category_service.restore_snapshot(
                    before_snapshot
                )
                raise
        return {**result, **persisted}

    def assign_manual_category(
        self,
        transaction_id: str,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        selection = manual_assignment_selection(payload)
        selected_code = str(selection["category_code"])
        suggestion = self._latest_auto_category_suggestion(transaction_id)
        previous_resolution_status = "unmatched"
        if isinstance(suggestion, dict):
            previous_resolution_status = (
                str(
                    suggestion.get("category_resolution_status")
                    or "unmatched"
                )
                or "unmatched"
            )
        assignable_codes = {
            *self._active_bank_auto_tag_rule_codes(),
            BANK_AUTO_TAG_INTERNAL_TRANSFER_CODE,
        }
        if selected_code not in assignable_codes:
            raise BankTransactionCategoryValidationError(
                "invalid_manual_category_assignment_candidate",
                "只能选择当前可用的银行明细标签。",
                transaction_id=transaction_id,
            )
        with self._category_mutation_lock:
            before_snapshot = (
                self._bank_transaction_category_service.snapshot()
            )
            try:
                result = (
                    self._bank_transaction_category_service.assign_manual_category(
                        transaction_id=transaction_id,
                        category_code=selected_code,
                        actor=actor_id,
                        category_primary_label=selection.get(
                            "category_primary_label"
                        ),
                        category_sub_label=selection.get(
                            "category_sub_label"
                        ),
                        category_third_label=selection.get(
                            "category_third_label"
                        ),
                        category_label_path=list(
                            selection.get("category_label_path") or []
                        ),
                        turnover_action_type=selection.get(
                            "turnover_action_type"
                        ),
                        turnover_family=selection.get("turnover_family"),
                    )
                )
                persisted = self._persist_category_mutation(
                    [transaction_id],
                    transaction_id=transaction_id,
                    mutation_type="manual_assign",
                    actor_id=actor_id,
                    action="bank_detail_category_manually_assigned",
                    metadata={
                        "selected_category_code": selected_code,
                        "selected_category_third_label": selection.get(
                            "category_third_label"
                        ),
                        "previous_resolution_status": (
                            previous_resolution_status
                        ),
                        "assignment_source": "manual",
                    },
                )
            except Exception:
                self._bank_transaction_category_service.restore_snapshot(
                    before_snapshot
                )
                raise
        return {**result, **persisted}

    def clear_manual_category(
        self,
        transaction_id: str,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        with self._category_mutation_lock:
            before_snapshot = (
                self._bank_transaction_category_service.snapshot()
            )
            try:
                result = (
                    self._bank_transaction_category_service.clear_manual_category(
                        transaction_id=transaction_id,
                        actor=actor_id,
                    )
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
                self._bank_transaction_category_service.restore_snapshot(
                    before_snapshot
                )
                raise
        return {**result, **persisted}

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
        normalized_mode = str(mode or "").strip().lower()
        snapshot = self._canonical_query_service().export_payload(
            include_accounts=normalized_mode == "account",
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
        )
        transactions = dict(snapshot["transactions"])
        accounts = (
            dict(snapshot["accounts"])
            if isinstance(snapshot.get("accounts"), dict)
            else {
                "accounts": [],
                "total_balance": None,
                "balance_account_count": 0,
                "missing_balance_account_count": 0,
            }
        )
        service = BankDetailsExportService(
            transaction_page_loader=lambda **_kwargs: transactions,
            account_loader=lambda **_kwargs: accounts,
        )
        result = service.export(
            mode=normalized_mode,
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
                "mode": normalized_mode,
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
        if self._category_mutation_service is not None:
            persisted = dict(
                self._category_mutation_service.persist(
                    transaction_id=transaction_id,
                    mutation_type=mutation_type,
                    record=self._bank_transaction_category_service.get(
                        transaction_id
                    ),
                    actor_id=actor_id,
                    action=action,
                    metadata=metadata,
                )
                or {}
            )
            affected_months = list(
                persisted.get("affected_months") or affected_months
            )
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
            raise RuntimeError(
                "durable bank transaction category writer is unavailable"
            )
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

    def _latest_auto_category_suggestion(
        self,
        transaction_id: str,
    ) -> dict[str, object] | None:
        if callable(self._suggestion_provider):
            return self._suggestion_provider(transaction_id)
        return None

    def _current_bank_auto_tag_rules_version(self) -> int:
        try:
            payload = (
                self._app_settings_service.get_bank_auto_tag_rules_payload(
                    can_save=False
                )
            )
            return int(payload.get("version") or 1)
        except (TypeError, ValueError):
            return 1

    def _active_bank_auto_tag_rule_codes(self) -> list[str]:
        payload = self._app_settings_service.get_bank_auto_tag_rules_payload(
            can_save=False
        )
        active_rules = (
            payload.get("active_rules")
            if isinstance(payload, dict)
            else []
        )
        return list(
            dict.fromkeys(
                str(rule.get("code") or "").strip()
                for rule in list(active_rules or [])
                if isinstance(rule, dict)
                and str(rule.get("code") or "").strip()
            )
        )
