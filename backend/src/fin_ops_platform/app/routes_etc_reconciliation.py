from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.etc_reconciliation_models import SourceFileKind


class EtcReconciliationTaskApiRoutes:
    def __init__(
        self,
        *,
        task_service: Any,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]],
        task_payload: Callable[[Any], dict[str, Any]],
        unavailable_task_payload: Callable[[Any], dict[str, Any]],
        upload_source: Callable[..., Any],
        upload_supplement_for_card: Callable[..., Any],
        submit_ticket_root_texts: Callable[[str, str | bytes | None], Any],
        delete_source_file: Callable[[str, str, str | bytes | None], Any],
        patch_item: Callable[[str, str, str | bytes | None], Any],
        confirm_task: Callable[[str, str | bytes | None], Any],
        reopen_task: Callable[[str, str | bytes | None], Any],
        refresh_matches: Callable[[str], Any],
        delete_imported_invoices: Callable[[str, str | bytes | None], Any],
        delete_task: Callable[[str, str | bytes | None], Any],
    ) -> None:
        self._task_service = task_service
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._task_payload = task_payload
        self._unavailable_task_payload = unavailable_task_payload
        self._upload_source = upload_source
        self._upload_supplement_for_card = upload_supplement_for_card
        self._submit_ticket_root_texts = submit_ticket_root_texts
        self._delete_source_file = delete_source_file
        self._patch_item = patch_item
        self._confirm_task = confirm_task
        self._reopen_task = reopen_task
        self._refresh_matches = refresh_matches
        self._delete_imported_invoices = delete_imported_invoices
        self._delete_task = delete_task

    def route(
        self,
        method: str,
        route_path: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        if method == "GET" and route_path == "/api/etc/reconciliation-tasks/ready-for-import":
            return self.ready_for_import()
        if method == "GET" and route_path == "/api/etc/reconciliation-tasks":
            return self.list_tasks()
        if method == "POST" and route_path == "/api/etc/reconciliation-tasks":
            return self.create_task(body)
        if route_path.startswith("/api/etc/reconciliation-tasks/"):
            return self.route_task(method, route_path, body, headers)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task_route"})

    def list_tasks(self) -> Any:
        return self._json_response(
            HTTPStatus.OK,
            {"tasks": [self._task_payload(task) for task in self._task_service.list_tasks()]},
        )

    def ready_for_import(self) -> Any:
        ready_tasks = self._task_service.list_ready_for_import_tasks()
        unavailable_tasks = [
            task
            for task in self._task_service.list_tasks()
            if getattr(getattr(task, "status", ""), "value", getattr(task, "status", "")) != "ready_for_import"
        ]
        return self._json_response(
            HTTPStatus.OK,
            {
                "tasks": [self._task_payload(task) for task in ready_tasks],
                "unavailableTasks": [self._unavailable_task_payload(task) for task in unavailable_tasks],
            },
        )

    def create_task(self, body: str | bytes | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        task = self._task_service.create_task(
            title=str(payload.get("title") or "").strip(),
            created_by=str(payload.get("createdBy") or payload.get("created_by") or "web_finance_user"),
        )
        return self._json_response(HTTPStatus.CREATED, self._task_payload(task))

    def route_task(
        self,
        method: str,
        route_path: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        relative = route_path.removeprefix("/api/etc/reconciliation-tasks/").strip("/")
        parts = [unquote(part) for part in relative.split("/") if part]
        if not parts:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        task_id = parts[0]
        if method == "GET" and len(parts) == 1:
            return self.detail(task_id)
        if method == "DELETE" and len(parts) == 1:
            return self._delete_task(task_id, body)
        if method == "DELETE" and len(parts) == 3 and parts[1] == "source-files":
            return self._delete_source_file(task_id, parts[2], body)
        if method == "POST" and len(parts) == 2 and parts[1] == "credit-card-statement":
            return self._upload_source(
                task_id=task_id,
                source_kind=SourceFileKind.CREDIT_CARD_STATEMENT,
                body=body,
                headers=headers,
            )
        if method == "POST" and len(parts) == 2 and parts[1] == "ticket-root-files":
            return self._upload_source(
                task_id=task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                body=body,
                headers=headers,
            )
        if method == "POST" and len(parts) == 2 and parts[1] == "ticket-root-texts":
            return self._submit_ticket_root_texts(task_id, body)
        if method == "POST" and len(parts) == 2 and parts[1] == "supplement-evidences":
            return self._upload_source(
                task_id=task_id,
                source_kind=SourceFileKind.SUPPLEMENT_EVIDENCE,
                body=body,
                headers=headers,
            )
        if method == "POST" and len(parts) == 3 and parts[1] == "supplement-evidences":
            return self._upload_supplement_for_card(
                task_id=task_id,
                item_id=parts[2],
                body=body,
                headers=headers,
            )
        if method == "PATCH" and len(parts) == 3 and parts[1] == "items":
            return self._patch_item(task_id, parts[2], body)
        if method == "POST" and len(parts) == 2 and parts[1] == "confirm":
            return self._confirm_task(task_id, body)
        if method == "POST" and len(parts) == 2 and parts[1] == "reopen":
            return self._reopen_task(task_id, body)
        if method == "POST" and len(parts) == 2 and parts[1] == "refresh-matches":
            return self._refresh_matches(task_id)
        if method == "DELETE" and len(parts) == 2 and parts[1] == "imported-invoices":
            return self._delete_imported_invoices(task_id, body)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task_route"})

    def detail(self, task_id: str) -> Any:
        try:
            task = self._task_service.get_task(task_id)
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        return self._json_response(HTTPStatus.OK, self._task_payload(task))
