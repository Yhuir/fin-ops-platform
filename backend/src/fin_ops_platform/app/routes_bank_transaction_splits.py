from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.bank_transaction_split_service import (
    BankTransactionSplitError,
    BankTransactionSplitService,
)


class BankTransactionSplitApiRoutes:
    def __init__(self, *, service: BankTransactionSplitService, resolve_session: Callable[..., Any], load_json_body: Callable[..., Any], json_response: Callable[..., Any]) -> None:
        self._service = service
        self._resolve_session = resolve_session
        self._load_json_body = load_json_body
        self._json_response = json_response

    def route(self, method: str, route_path: str, body: str | bytes | None, headers: dict[str, str] | None) -> Any | None:
        prefix, suffix = "/api/bank-transactions/", "/splits"
        is_batch = method == "POST" and route_path == "/api/bank-transactions/splits/query"
        if not is_batch and (not route_path.startswith(prefix) or not route_path.endswith(suffix) or method not in {"GET", "PUT"}):
            return None
        transaction_id = unquote(route_path[len(prefix):-len(suffix)])
        if not is_batch and (not transaction_id or "/" in transaction_id):
            return self._json_response(HTTPStatus.BAD_REQUEST, {"error": "invalid_transaction_id", "message": "流水身份不正确。"})
        session, error = self._resolve_session(headers)
        if error is not None:
            return error
        if session is None:
            return self._json_response(HTTPStatus.UNAUTHORIZED, {"error": "authentication_required", "message": "请登录后访问。"})
        try:
            if is_batch:
                payload, error = self._load_json_body(body)
                if error is not None:
                    return error
                result = self._service.read_many(payload)
                return self._json_response(HTTPStatus.OK, {"rows": [{**row, "can_edit": True} for row in result["rows"]]})
            elif method == "GET":
                result = self._service.read(transaction_id)
            else:
                payload, error = self._load_json_body(body)
                if error is not None:
                    return error
                result = self._service.save(transaction_id, payload, actor_id=str(session.identity.username or session.identity.user_id))
        except BankTransactionSplitError as exc:
            return self._json_response(HTTPStatus(exc.status), {"error": exc.code, "message": str(exc)})
        return self._json_response(HTTPStatus.OK, {**result, "can_edit": True})
