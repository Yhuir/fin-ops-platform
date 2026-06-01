from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.services.app_settings_service import (
    BankAutoTagRulesPersistenceError,
)
from fin_ops_platform.services.bank_details_application_service import (
    BankDetailsApplicationService,
    BankDetailsReadModelRefreshingError,
)
from fin_ops_platform.services.bank_details_export_service import BankDetailsExportError
from fin_ops_platform.services.bank_transaction_category_service import (
    BankAutoTagRulesValidationError,
    BankTransactionCategoryValidationError,
)


class BankDetailsApiRoutes:
    def __init__(self, application_service: BankDetailsApplicationService) -> None:
        self._application_service = application_service

    def accounts(self, *, date_from: str | None, date_to: str | None) -> tuple[HTTPStatus, dict[str, Any]]:
        payload = self._application_service.accounts_payload(date_from=date_from, date_to=date_to)
        return self._status_for_payload(payload, item_key="accounts"), payload

    def transactions(
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
        page: str | None,
        page_size: str | None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            payload = self._application_service.transactions_payload(
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                keyword=keyword,
                category_code=category_code,
                category_primary_label=category_primary_label,
                category_sub_label=category_sub_label,
                category_third_label=category_third_label,
                page=int(page or 1),
                page_size=int(page_size or 100),
            )
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "invalid_bank_details_request", "message": str(exc)}
        return self._status_for_payload(payload, item_key="rows"), payload

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
        session: OARequestSession | None = None,
    ) -> tuple[HTTPStatus, Any]:
        try:
            result = self._application_service.export_transactions(
                mode=mode,
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                keyword=keyword,
                category_code=category_code,
                category_primary_label=category_primary_label,
                category_sub_label=category_sub_label,
                category_third_label=category_third_label,
                actor_id=self._actor(session, "bank_detail_export"),
            )
        except BankDetailsReadModelRefreshingError as exc:
            return HTTPStatus.ACCEPTED, exc.payload
        except BankDetailsExportError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": exc.error_code, "message": str(exc)}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "invalid_bank_details_request", "message": str(exc)}
        return HTTPStatus.OK, result

    def auto_tag_rules(self, *, session: OARequestSession | None) -> tuple[HTTPStatus, dict[str, Any]]:
        can_save = True if session is None else bool(session.can_mutate_data)
        return HTTPStatus.OK, self._application_service.get_auto_tag_rules_payload(can_save=can_save)

    def update_auto_tag_rules(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        if session is not None and not session.can_mutate_data:
            return self._permission_denied("当前账户没有保存自动标签规则权限。")
        try:
            updated = self._application_service.update_auto_tag_rules(
                payload,
                actor_id=self._actor(session, "bank_auto_tag_rules"),
            )
        except BankAutoTagRulesValidationError as exc:
            status = HTTPStatus.CONFLICT if exc.error_code == "bank_transaction_tags_version_conflict" else HTTPStatus.BAD_REQUEST
            return status, {
                "error": exc.error_code,
                "message": str(exc),
                "field_errors": list(exc.field_errors),
                "references": list(exc.references),
            }
        except BankAutoTagRulesPersistenceError as exc:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"error": exc.error_code, "message": str(exc)}
        return HTTPStatus.OK, updated

    def replace_auto_tag_rules_from_file_source(
        self,
        source: object,
        *,
        session: OARequestSession | None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        if session is not None and not session.can_mutate_data:
            return self._permission_denied("当前账户没有替换自动标签规则权限。")
        try:
            updated = self._application_service.replace_auto_tag_rules_from_file_source(
                source,
                actor_id=self._actor(session, "bank_auto_tag_rules_file_replacement"),
            )
        except (BankAutoTagRulesValidationError, FileNotFoundError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "error": getattr(exc, "error_code", "invalid_bank_auto_tag_rule_file"),
                "message": str(exc),
                "field_errors": list(getattr(exc, "field_errors", [])),
                "references": list(getattr(exc, "references", [])),
            }
        except BankAutoTagRulesPersistenceError as exc:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"error": exc.error_code, "message": str(exc)}
        return HTTPStatus.OK, updated

    def reapply_auto_tag_rules(self, *, session: OARequestSession | None) -> tuple[HTTPStatus, dict[str, Any]]:
        if session is not None and not session.can_mutate_data:
            return self._permission_denied("当前账户没有重新应用自动标签规则权限。")
        try:
            payload = self._application_service.reapply_auto_tag_rules(
                actor_id=self._actor(session, "bank_auto_tag_rules_reapply"),
                can_save=True if session is None else bool(session.can_mutate_data),
            )
        except RuntimeError as exc:
            if str(exc) == "bank_auto_tag_rules_reapply_unavailable":
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "error": "bank_auto_tag_rules_reapply_unavailable",
                    "message": "自动标签规则已保存，但银行明细刷新队列暂时不可用，请稍后重试。",
                }
            raise
        return HTTPStatus.ACCEPTED, payload

    def confirm_category(
        self,
        transaction_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        if session is not None and not session.can_mutate_data:
            return self._permission_denied("当前账户没有确认银行明细标签权限。")
        try:
            result = self._application_service.confirm_category(
                transaction_id,
                payload,
                actor_id=self._actor(session, "bank_category_confirmation"),
            )
        except BankTransactionCategoryValidationError as exc:
            return self._category_error(exc)
        return HTTPStatus.OK, result

    def revoke_category_confirmation(
        self,
        transaction_id: str,
        *,
        session: OARequestSession | None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        if session is not None and not session.can_mutate_data:
            return self._permission_denied("当前账户没有撤销银行明细标签确认权限。")
        try:
            result = self._application_service.revoke_category_confirmation(
                transaction_id,
                actor_id=self._actor(session, "bank_category_confirmation"),
            )
        except BankTransactionCategoryValidationError as exc:
            return self._category_error(exc)
        return HTTPStatus.OK, result

    def assign_category(
        self,
        transaction_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        if session is not None and not session.can_mutate_data:
            return self._permission_denied("当前账户没有设置银行明细标签权限。")
        try:
            result = self._application_service.assign_manual_category(
                transaction_id,
                payload,
                actor_id=self._actor(session, "bank_category_assignment"),
            )
        except BankTransactionCategoryValidationError as exc:
            return self._category_error(exc)
        return HTTPStatus.OK, result

    def clear_category_assignment(
        self,
        transaction_id: str,
        *,
        session: OARequestSession | None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        if session is not None and not session.can_mutate_data:
            return self._permission_denied("当前账户没有撤销银行明细人工标签权限。")
        try:
            result = self._application_service.clear_manual_category(
                transaction_id,
                actor_id=self._actor(session, "bank_category_assignment"),
            )
        except BankTransactionCategoryValidationError as exc:
            return self._category_error(exc)
        return HTTPStatus.OK, result

    @staticmethod
    def _status_for_payload(payload: dict[str, Any], *, item_key: str) -> HTTPStatus:
        if str(payload.get("read_model_status") or "") == "refreshing" and not list(payload.get(item_key) or []):
            return HTTPStatus.ACCEPTED
        return HTTPStatus.OK

    @staticmethod
    def _actor(session: OARequestSession | None, fallback: str) -> str:
        return str(session.identity.username or session.identity.user_id) if session is not None else fallback

    @staticmethod
    def _permission_denied(message: str) -> tuple[HTTPStatus, dict[str, Any]]:
        return HTTPStatus.FORBIDDEN, {"error": "permission_denied", "message": message}

    @staticmethod
    def _category_error(exc: BankTransactionCategoryValidationError) -> tuple[HTTPStatus, dict[str, Any]]:
        status = HTTPStatus.NOT_FOUND if exc.error_code == "unknown_transaction_id" else HTTPStatus.BAD_REQUEST
        return status, {"error": exc.error_code, "message": str(exc), "transaction_id": exc.transaction_id}
