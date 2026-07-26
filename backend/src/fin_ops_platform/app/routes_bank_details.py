from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.services.app_settings_service import (
    BankAutoTagRulesPersistenceError,
)
from fin_ops_platform.services.bank_details_application_service import (
    BankDetailsApplicationService,
)
from fin_ops_platform.services.bank_details_export_service import BankDetailsExportError
from fin_ops_platform.services.bank_transaction_category_service import (
    BankAutoTagRulesValidationError,
    BankTransactionCategoryValidationError,
)

ReadSessionResolver = Callable[[dict[str, str] | None], tuple[OARequestSession | None, Any | None]]
JsonResponse = Callable[[HTTPStatus, object], Any]
ExportResponse = Callable[[HTTPStatus, Any], Any]
JsonBodyLoader = Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]]
DefaultAutoTagRulesSourceProvider = Callable[[], object]


class BankDetailsApiRoutes:
    def __init__(
        self,
        application_service: BankDetailsApplicationService,
        *,
        resolve_read_session: ReadSessionResolver | None = None,
        json_response: JsonResponse | None = None,
        export_response: ExportResponse | None = None,
        load_json_body: JsonBodyLoader | None = None,
        default_auto_tag_rules_source_provider: DefaultAutoTagRulesSourceProvider | None = None,
    ) -> None:
        self._application_service = application_service
        self._resolve_read_session = resolve_read_session
        self._json_response = json_response
        self._export_response = export_response
        self._load_json_body = load_json_body
        self._default_auto_tag_rules_source_provider = default_auto_tag_rules_source_provider

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any | None:
        if method == "GET" and route_path == "/api/bank-details/auto-tag-rules":
            return self._json_read(headers, lambda session: self.auto_tag_rules(session=session))
        if method == "POST" and route_path == "/api/bank-details/auto-tag-rules/reapply":
            return self._json_write_without_body(
                headers,
                "当前账户没有重新应用自动标签规则权限。",
                lambda session: self.reapply_auto_tag_rules(session=session),
            )
        if method == "POST" and route_path == "/api/bank-details/auto-tag-rules/file-replacement":
            return self._replace_auto_tag_rules_from_file_route(body, headers)
        if method == "PUT" and route_path == "/api/bank-details/auto-tag-rules":
            return self._json_write_body(
                body,
                headers,
                "当前账户没有保存自动标签规则权限。",
                lambda payload, session: self.update_auto_tag_rules(payload, session=session),
            )
        if method == "PATCH" and route_path == "/api/bank-details/transactions/categories":
            return self._json_response_for(
                HTTPStatus.GONE,
                {
                    "error": "manual_bank_transaction_category_disabled",
                    "message": "银行明细分类已改为系统自动分配，不能人工保存分类。",
                },
            )
        if method == "GET" and route_path == "/api/bank-details/accounts":
            return self._json_response_for(
                *self.accounts(
                    date_from=query.get("date_from", [None])[0],
                    date_to=query.get("date_to", [None])[0],
                )
            )
        if method == "GET" and route_path == "/api/bank-details/transactions/export":
            return self._export_read(query, headers)
        if method == "GET" and route_path == "/api/bank-details/transactions":
            return self._json_response_for(
                *self.transactions(
                    account_key=query.get("account_key", [None])[0],
                    date_from=query.get("date_from", [None])[0],
                    date_to=query.get("date_to", [None])[0],
                    keyword=query.get("keyword", [None])[0],
                    category_code=query.get("category_code", [None])[0],
                    category_primary_label=query.get("category_primary_label", [None])[0],
                    category_sub_label=query.get("category_sub_label", [None])[0],
                    category_third_label=query.get("category_third_label", [None])[0],
                    page=query.get("page", [None])[0],
                    page_size=query.get("page_size", [None])[0],
                )
            )
        category_prefix = "/api/bank-details/transactions/"
        confirmation_suffix = "/category-confirmation"
        assignment_suffix = "/category-assignment"
        if route_path.startswith(category_prefix) and route_path.endswith(assignment_suffix):
            transaction_id = unquote(route_path[len(category_prefix):-len(assignment_suffix)])
            if method == "POST":
                return self._json_write_body(
                    body,
                    headers,
                    "当前账户没有设置银行明细标签权限。",
                    lambda payload, session: self.assign_category(transaction_id, payload, session=session),
                )
            if method == "DELETE":
                return self._json_write_without_body(
                    headers,
                    "当前账户没有撤销银行明细人工标签权限。",
                    lambda session: self.clear_category_assignment(transaction_id, session=session),
                )
        if route_path.startswith(category_prefix) and route_path.endswith(confirmation_suffix):
            transaction_id = unquote(route_path[len(category_prefix):-len(confirmation_suffix)])
            if method == "POST":
                return self._json_write_body(
                    body,
                    headers,
                    "当前账户没有确认银行明细标签权限。",
                    lambda payload, session: self.confirm_category(transaction_id, payload, session=session),
                )
            if method == "DELETE":
                return self._json_write_without_body(
                    headers,
                    "当前账户没有撤销银行明细标签确认权限。",
                    lambda session: self.revoke_category_confirmation(transaction_id, session=session),
                )
        return None

    def accounts(self, *, date_from: str | None, date_to: str | None) -> tuple[HTTPStatus, dict[str, Any]]:
        payload = self._application_service.accounts_payload(date_from=date_from, date_to=date_to)
        return HTTPStatus.OK, payload

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
        return HTTPStatus.OK, payload

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
        payload = self._application_service.reapply_auto_tag_rules(
            actor_id=self._actor(session, "bank_auto_tag_rules_reapply"),
            can_save=True if session is None else bool(session.can_mutate_data),
        )
        return HTTPStatus.OK, payload

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
    def _actor(session: OARequestSession | None, fallback: str) -> str:
        return str(session.identity.username or session.identity.user_id) if session is not None else fallback

    @staticmethod
    def _permission_denied(message: str) -> tuple[HTTPStatus, dict[str, Any]]:
        return HTTPStatus.FORBIDDEN, {"error": "permission_denied", "message": message}

    @staticmethod
    def _category_error(exc: BankTransactionCategoryValidationError) -> tuple[HTTPStatus, dict[str, Any]]:
        status = HTTPStatus.NOT_FOUND if exc.error_code == "unknown_transaction_id" else HTTPStatus.BAD_REQUEST
        return status, {"error": exc.error_code, "message": str(exc), "transaction_id": exc.transaction_id}

    def _json_read(
        self,
        headers: dict[str, str] | None,
        handler: Callable[[OARequestSession | None], tuple[HTTPStatus, dict[str, Any]]],
    ) -> Any:
        session, auth_error = self._resolve_read(headers)
        if auth_error is not None:
            return auth_error
        return self._json_response_for(*handler(session))

    def _json_write_body(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        permission_message: str,
        handler: Callable[[dict[str, Any], OARequestSession | None], tuple[HTTPStatus, dict[str, Any]]],
    ) -> Any:
        session, auth_error = self._resolve_read(headers)
        if auth_error is not None:
            return auth_error
        if session is not None and not session.can_mutate_data:
            return self._permission_response(permission_message)
        payload, error = self._load_body(body)
        if error is not None:
            return error
        return self._json_response_for(*handler(payload, session))

    def _json_write_without_body(
        self,
        headers: dict[str, str] | None,
        permission_message: str,
        handler: Callable[[OARequestSession | None], tuple[HTTPStatus, dict[str, Any]]],
    ) -> Any:
        session, auth_error = self._resolve_read(headers)
        if auth_error is not None:
            return auth_error
        if session is not None and not session.can_mutate_data:
            return self._permission_response(permission_message)
        return self._json_response_for(*handler(session))

    def _replace_auto_tag_rules_from_file_route(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_read(headers)
        if auth_error is not None:
            return auth_error
        if session is not None and not session.can_mutate_data:
            return self._permission_response("当前账户没有替换自动标签规则权限。")
        if body not in (None, b"", ""):
            payload, error = self._load_body(body)
            if error is not None:
                return error
            source: object = payload.get("source") if isinstance(payload, dict) and "source" in payload else payload
        else:
            if self._default_auto_tag_rules_source_provider is None:
                raise RuntimeError("bank_details_default_auto_tag_rules_source_port_missing")
            source = self._default_auto_tag_rules_source_provider()
        return self._json_response_for(*self.replace_auto_tag_rules_from_file_source(source, session=session))

    def _export_read(self, query: dict[str, list[str]], headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_read(headers)
        if auth_error is not None:
            return auth_error
        mode = query.get("mode", ["all"])[0]
        account_key = query.get("account_key", [None])[0]
        date_from = query.get("date_from", [None])[0]
        date_to = query.get("date_to", [None])[0]
        keyword = query.get("keyword", [None])[0]
        category_code = query.get("category_code", [None])[0]
        category_primary_label = query.get("category_primary_label", [None])[0]
        category_sub_label = query.get("category_sub_label", [None])[0]
        category_third_label = query.get("category_third_label", [None])[0]
        status, result = self.export_transactions(
            mode=mode,
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
            session=session,
        )
        if isinstance(result, dict):
            return self._json_response_for(status, result)
        if self._export_response is None:
            raise RuntimeError("bank_details_export_response_port_missing")
        return self._export_response(status, result)

    def _resolve_read(self, headers: dict[str, str] | None) -> tuple[OARequestSession | None, Any | None]:
        if self._resolve_read_session is None:
            return None, None
        return self._resolve_read_session(headers)

    def _load_body(self, body: str | bytes | None) -> tuple[dict[str, Any], Any | None]:
        if self._load_json_body is None:
            raise RuntimeError("bank_details_json_body_loader_port_missing")
        return self._load_json_body(body)

    def _json_response_for(self, status: HTTPStatus, payload: object) -> Any:
        if self._json_response is None:
            return status, payload
        return self._json_response(status, payload)

    def _permission_response(self, message: str) -> Any:
        return self._json_response_for(HTTPStatus.FORBIDDEN, {"error": "permission_denied", "message": message})
