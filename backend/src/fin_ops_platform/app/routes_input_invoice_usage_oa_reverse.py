from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.input_invoice_usage_oa_reverse_service import (
    InputInvoiceUsageOaReverseService,
    InputInvoiceUsageOaReverseServiceError,
)
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageError
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


class InputInvoiceUsageOaReverseApiRoutes:
    def __init__(
        self,
        *,
        service: InputInvoiceUsageOaReverseService,
        resolve_read_session: Callable[..., tuple[Any | None, Any | None]],
        mutation_actor: Callable[..., tuple[str, Any | None]],
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]],
        json_response: Callable[[HTTPStatus, object], Any],
        input_usage_error_response: Callable[[InputInvoiceUsageError], Any],
        oa_reverse_error_response: Callable[[InputInvoiceUsageOaReverseServiceError | WorkbenchRelationCommandError], Any],
        target_oa_applicant_token_provider: Callable[[], Any],
        oa_draft_client_for_batch: Callable[[str], Any],
        int_or_none: Callable[[object], int | None],
    ) -> None:
        self._service = service
        self._resolve_read_session = resolve_read_session
        self._mutation_actor = mutation_actor
        self._load_json_body = load_json_body
        self._json_response = json_response
        self._input_usage_error_response = input_usage_error_response
        self._oa_reverse_error_response = oa_reverse_error_response
        self._target_oa_applicant_token_provider = target_oa_applicant_token_provider
        self._oa_draft_client_for_batch = oa_draft_client_for_batch
        self._int_or_none = int_or_none

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any | None:
        if method == "POST" and route_path == "/api/input-invoice-usage/oa-reverse/preview":
            return self.preview(body, headers)
        if method == "GET" and route_path == "/api/input-invoice-usage/oa-reverse/staged-drafts":
            return self.staged_drafts(query, headers)
        if method == "GET" and route_path == "/api/input-invoice-usage/oa-reverse/submitted-history":
            return self.submitted_history(query, headers)
        if method == "POST" and route_path == "/api/input-invoice-usage/oa-reverse/batches":
            return self.create_batch(body, headers)
        if method == "POST" and route_path == "/api/input-invoice-usage/oa-reverse/oa-draft":
            return self.create_oa_draft_from_selection(body, headers)
        if route_path.startswith("/api/input-invoice-usage/oa-reverse/batches/"):
            suffix = route_path.removeprefix("/api/input-invoice-usage/oa-reverse/batches/").strip("/")
            parts = [unquote(part) for part in suffix.split("/") if part]
            if len(parts) == 1 and method == "GET":
                return self.get_batch(parts[0], headers)
            if len(parts) == 2 and method == "POST" and parts[1] == "oa-draft":
                return self.create_oa_draft(parts[0], body, headers)
            if len(parts) == 3 and method == "POST" and parts[1:] == ["oa-draft", "revoke"]:
                return self.revoke_oa_draft(parts[0], body, headers)
            if len(parts) == 3 and method == "POST" and parts[1:] == ["oa-status", "refresh"]:
                return self.refresh_oa_status(parts[0], body, headers)
            if len(parts) == 2 and method == "POST" and parts[1] == "manual-oa-status":
                return self.manual_oa_status(parts[0], body, headers)
        return None

    def preview(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_read_session(
            headers,
            denied_message="当前账户没有访问进项发票使用情况页面权限。",
        )
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            result = self._service.preview(
                payload,
                can_create_draft=True,
            )
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)

    def create_batch(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        actor_id, auth_error = self._mutation_actor(
            headers,
            denied_message="当前账户没有创建进项发票反提 OA 批次权限。",
        )
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            result = self._service.create_batch(
                payload if isinstance(payload, dict) else {},
                actor_id=actor_id,
            )
        except (InputInvoiceUsageOaReverseServiceError, WorkbenchRelationCommandError) as exc:
            return self._oa_reverse_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)

    def submitted_history(self, query: dict[str, list[str]], headers: dict[str, str] | None) -> Any:
        _session, auth_error = self._resolve_read_session(
            headers,
            denied_message="当前账户没有访问进项发票反提 OA 已提交历史权限。",
        )
        if auth_error is not None:
            return auth_error
        try:
            result = self._service.submitted_history(
                limit=int(query.get("limit", ["50"])[0] or 50),
            )
        except (ValueError, TypeError):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_reverse_history_query", "message": "limit must be a positive integer."},
            )
        except (InputInvoiceUsageOaReverseServiceError, WorkbenchRelationCommandError) as exc:
            return self._oa_reverse_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)

    def staged_drafts(self, query: dict[str, list[str]], headers: dict[str, str] | None) -> Any:
        _session, auth_error = self._resolve_read_session(
            headers,
            denied_message="当前账户没有访问进项发票反提 OA 暂存批次权限。",
        )
        if auth_error is not None:
            return auth_error
        try:
            result = self._service.staged_drafts(
                limit=int(query.get("limit", ["50"])[0] or 50),
            )
        except (ValueError, TypeError):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_reverse_staged_query", "message": "limit must be a positive integer."},
            )
        except (InputInvoiceUsageOaReverseServiceError, WorkbenchRelationCommandError) as exc:
            return self._oa_reverse_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)

    def get_batch(self, batch_id: str, headers: dict[str, str] | None) -> Any:
        _session, auth_error = self._resolve_read_session(
            headers,
            denied_message="当前账户没有访问进项发票反提 OA 批次权限。",
        )
        if auth_error is not None:
            return auth_error
        try:
            result = self._service.get_batch(batch_id)
        except (InputInvoiceUsageOaReverseServiceError, WorkbenchRelationCommandError) as exc:
            return self._oa_reverse_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)

    def create_oa_draft_from_selection(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        actor_id, auth_error = self._mutation_actor(
            headers,
            denied_message="当前账户没有创建进项发票反提 OA 草稿权限。",
        )
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            result = self._service.create_oa_draft_from_selection(
                payload if isinstance(payload, dict) else {},
                actor_id=actor_id,
                oa_client_provider=self._target_oa_applicant_token_provider(),
            )
        except (InputInvoiceUsageOaReverseServiceError, WorkbenchRelationCommandError) as exc:
            return self._oa_reverse_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)

    def create_oa_draft(self, batch_id: str, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        actor_id, auth_error = self._mutation_actor(
            headers,
            denied_message="当前账户没有创建进项发票反提 OA 草稿权限。",
        )
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        request = payload if isinstance(payload, dict) else {}
        try:
            result = self._service.create_oa_draft(
                batch_id,
                expected_version=self._int_or_none(request.get("expectedVersion", request.get("expected_version"))),
                idempotency_key=str(request.get("idempotencyKey", request.get("idempotency_key")) or ""),
                actor_id=actor_id,
                oa_client=self._oa_draft_client_for_batch(batch_id),
            )
        except (InputInvoiceUsageOaReverseServiceError, WorkbenchRelationCommandError) as exc:
            return self._oa_reverse_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)

    def revoke_oa_draft(self, batch_id: str, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        actor_id, auth_error = self._mutation_actor(
            headers,
            denied_message="当前账户没有撤销进项发票反提 OA 草稿权限。",
        )
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        request = payload if isinstance(payload, dict) else {}
        try:
            result = self._service.revoke_oa_draft(
                batch_id,
                reason=str(request.get("reason") or ""),
                expected_version=self._int_or_none(request.get("expectedVersion", request.get("expected_version"))),
                idempotency_key=str(request.get("idempotencyKey", request.get("idempotency_key")) or ""),
                actor_id=actor_id,
            )
        except (InputInvoiceUsageOaReverseServiceError, WorkbenchRelationCommandError) as exc:
            return self._oa_reverse_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)

    def refresh_oa_status(self, batch_id: str, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        actor_id, auth_error = self._mutation_actor(
            headers,
            denied_message="当前账户没有刷新进项发票反提 OA 状态权限。",
        )
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        request = payload if isinstance(payload, dict) else {}
        try:
            result = self._service.refresh_oa_status(
                batch_id,
                expected_version=self._int_or_none(request.get("expectedVersion", request.get("expected_version"))),
                actor_id=actor_id,
            )
        except (InputInvoiceUsageOaReverseServiceError, WorkbenchRelationCommandError) as exc:
            return self._oa_reverse_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)

    def manual_oa_status(self, batch_id: str, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        actor_id, auth_error = self._mutation_actor(
            headers,
            denied_message="当前账户没有人工标记进项发票反提 OA 状态权限。",
        )
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        request = payload if isinstance(payload, dict) else {}
        try:
            result = self._service.manual_oa_status(
                batch_id,
                decision=str(request.get("decision") or ""),
                reason=str(request.get("reason") or ""),
                expected_version=self._int_or_none(request.get("expectedVersion", request.get("expected_version"))),
                idempotency_key=str(request.get("idempotencyKey", request.get("idempotency_key")) or ""),
                actor_id=actor_id,
                candidate_oa_row_id=str(request.get("candidateOaRowId", request.get("candidate_oa_row_id")) or "") or None,
            )
        except (InputInvoiceUsageOaReverseServiceError, WorkbenchRelationCommandError) as exc:
            return self._oa_reverse_error_response(exc)
        return self._json_response(HTTPStatus.OK, result)
