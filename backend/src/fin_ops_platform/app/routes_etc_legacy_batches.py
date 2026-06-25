from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote


class EtcLegacyBatchApiRoutes:
    def __init__(
        self,
        *,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        list_batches: Callable[..., Any],
        detail: Callable[[str], Any],
        delete: Callable[[str], Any],
        create_draft: Callable[[str | bytes | None, dict[str, str] | None], Any],
        create_draft_for_batch: Callable[[str, dict[str, str] | None], Any],
        confirm_submitted: Callable[[str], Any],
        mark_not_submitted: Callable[[str], Any],
    ) -> None:
        self._json_response = json_response
        self._list_batches = list_batches
        self._detail = detail
        self._delete = delete
        self._create_draft = create_draft
        self._create_draft_for_batch = create_draft_for_batch
        self._confirm_submitted = confirm_submitted
        self._mark_not_submitted = mark_not_submitted

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        if method == "GET" and route_path == "/api/etc/batches":
            return self._list_batches(
                status=query.get("status", [None])[0],
                month=query.get("month", [None])[0],
                plate=query.get("plate", [None])[0],
                keyword=query.get("keyword", [None])[0],
                page=query.get("page", [None])[0],
                page_size=query.get("page_size", query.get("pageSize", [None]))[0],
            )
        if method == "POST" and route_path == "/api/etc/batches/draft":
            return self._create_draft(body, headers)
        if route_path.startswith("/api/etc/batches/"):
            return self._route_batch(method, route_path, body, headers)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_batch_route"})

    def _route_batch(
        self,
        method: str,
        route_path: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        relative = route_path.removeprefix("/api/etc/batches/").strip("/")
        parts = [unquote(part) for part in relative.split("/") if part]
        if not parts:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_batch_route"})
        batch_id = parts[0]
        if method == "DELETE" and len(parts) == 1:
            return self._delete(batch_id)
        if method == "GET" and len(parts) == 1:
            return self._detail(batch_id)
        if method == "POST" and len(parts) == 2 and parts[1] == "draft":
            return self._create_draft_for_batch(batch_id, headers)
        if method == "POST" and len(parts) == 2 and parts[1] == "confirm-submitted":
            return self._confirm_submitted(batch_id)
        if method == "POST" and len(parts) == 2 and parts[1] == "mark-not-submitted":
            return self._mark_not_submitted(batch_id)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_batch_route"})
