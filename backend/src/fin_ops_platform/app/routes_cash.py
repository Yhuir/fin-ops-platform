"""Cash HTTP boundary. Authentication precedes this dispatcher in Application."""

from __future__ import annotations

import json
from typing import Any, Callable

from psycopg import OperationalError
from psycopg.errors import InsufficientPrivilege, InvalidSchemaName, LockNotAvailable, QueryCanceled, UndefinedTable, UniqueViolation
from psycopg_pool import PoolTimeout, TooManyRequests

from fin_ops_platform.services.cash_domain import CashError, serialize


class CashApiRoutes:
    def __init__(self, service: Any, queries: Any, tasks: Any, projects: Any,
                 json_response: Callable) -> None:
        self.service = service
        self.queries = queries
        self.tasks = tasks
        self.projects = projects
        self._json_response = json_response

    def route(self, method: str, route_path: str, query: dict[str, list[str]],
              body: str | bytes | None, *, session: Any) -> Any:
        try:
            if session is None:
                raise CashError("cash_session_required", "请先登录。", 401)
            if not session.can_admin_access and "cash" not in session.allowed_page_keys:
                raise CashError("cash_access_denied", "当前账号不可使用现金账。", 403)
            if any(len(values) != 1 for values in query.values()):
                raise CashError("cash_invalid_input", "查询参数不能重复。")
            params = {key: values[0] for key, values in query.items()}
            actor = {"account": session.identity.username, "name": session.identity.display_name}
            payload = self._parse_body(body) if method in {"POST", "PUT"} else None
            result, status = self._dispatch(method, route_path, params, payload, actor)
            return self._json_response(status, serialize(result), {"Cache-Control": "no-store"})
        except CashError as exc:
            return self._json_response(exc.status, {"error": exc.code, "message": exc.message},
                                       {"Cache-Control": "no-store"})
        except UniqueViolation:
            return self._json_response(409, {"error": "cash_allocation_conflict",
                                            "message": "相同现金分配或任务月份已存在，请刷新后核对。"},
                                       {"Cache-Control": "no-store"})
        except (OperationalError, PoolTimeout, TooManyRequests, LockNotAvailable, QueryCanceled,
                InsufficientPrivilege, InvalidSchemaName, UndefinedTable):
            return self._json_response(503, {"error": "cash_storage_unavailable",
                                            "message": "现金服务暂不可用，请稍后重新查询并核对提交结果。"},
                                       {"Cache-Control": "no-store"})

    @staticmethod
    def _parse_body(body: str | bytes | None) -> dict:
        if body is None:
            raise CashError("cash_invalid_input", "请求正文不能为空。")
        try:
            payload = json.loads(body, parse_constant=CashApiRoutes._reject_constant,
                                 object_pairs_hook=CashApiRoutes._unique_keys)
        except (ValueError, UnicodeDecodeError):
            raise CashError("cash_invalid_input", "请求必须是合法 JSON，不能含重复字段或非有限数值。") from None
        if not isinstance(payload, dict):
            raise CashError("cash_invalid_input", "请求正文必须是对象。")
        return payload

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise ValueError("Nonfinite JSON number")

    @staticmethod
    def _unique_keys(pairs: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def _dispatch(self, method: str, path: str, query: dict, payload: dict | None,
                  actor: dict) -> tuple[dict, int]:
        if method == "GET":
            reads = {
                "/api/cash/flows": self.queries.list_flows,
                "/api/cash/items": self.queries.list_items,
                "/api/cash/settlements": self.queries.list_settlements,
                "/api/cash/reports/turnover": self.queries.query_turnover,
                "/api/cash/reports/ticket-payments": self.queries.query_tickets,
                "/api/cash/reports/personal": self.queries.query_personal,
                "/api/cash/reports/project-options": self.queries.project_options,
                "/api/cash/tasks": self.tasks.list_templates,
                "/api/cash/task-occurrences": self.tasks.list_occurrences,
                "/api/cash/projects": self.projects.list_projects,
            }
            if path in reads:
                return reads[path](query), 200
            if path == "/api/cash/settings/project-selection":
                self._no_query(query)
                return self.service.get_project_selection(), 200
            if path == "/api/cash/settings/personal-opening":
                self._no_query(query)
                return self.service.get_personal_opening(), 200
            for name in ("accounts", "categories", "bill-labels"):
                if path == f"/api/cash/settings/{name}":
                    return self.queries.list_configuration(name, query), 200
            parts = path.split("/")
            if len(parts) == 5 and parts[3] == "flows":
                self._no_query(query)
                return self.queries.get_flow(parts[4]), 200
            if len(parts) == 5 and parts[3] == "items":
                self._no_query(query)
                return self.queries.get_item(parts[4]), 200

        if method in {"POST", "PUT"}:
            self._no_query(query)
        if method == "POST":
            if path == "/api/cash/flows":
                result = dict(self.service.create_flow(payload, actor))
                created = result.pop("created")
                return result, 201 if created else 200
            if path == "/api/cash/items":
                return self.service.create_item(payload, actor), 201
            if path == "/api/cash/settlements":
                return self.service.create_settlement(payload, actor), 201
            if path == "/api/cash/tasks":
                return self.tasks.create_template(payload), 201
            if path == "/api/cash/task-occurrences/confirm":
                return self.tasks.confirm(payload, actor), 200
            task_actions = {
                "/api/cash/task-occurrences/adjust": self.tasks.adjust,
                "/api/cash/task-occurrences/mark-unpaid": self.tasks.mark_unpaid,
                "/api/cash/task-occurrences/complete-check": self.tasks.complete_check,
            }
            if path in task_actions:
                return task_actions[path](payload), 200
            for name, command in (("accounts", self.service.create_account),
                                  ("categories", self.service.create_category),
                                  ("bill-labels", self.service.create_bill_label)):
                if path == f"/api/cash/settings/{name}":
                    return command(payload), 201

        parts = path.split("/")
        if method == "PUT":
            if path == "/api/cash/settings/project-selection":
                return self.service.update_project_selection(payload), 200
            if path == "/api/cash/settings/personal-opening":
                return self.service.update_personal_opening(payload), 200
            if len(parts) == 5:
                family, identity = parts[3:]
                if family == "flows":
                    return self.service.update_flow(identity, payload, actor), 200
                if family == "items":
                    return self.service.update_item(identity, payload, actor), 200
                if family == "settlements":
                    return self.service.update_settlement(identity, payload, actor), 200
                if family == "tasks":
                    return self.tasks.update_template(identity, payload), 200
            if len(parts) == 6 and parts[3] == "settings":
                for name, command in (("accounts", self.service.update_account),
                                      ("categories", self.service.update_category),
                                      ("bill-labels", self.service.update_bill_label)):
                    if parts[4] == name:
                        return command(parts[5], payload), 200
        if method == "POST" and len(parts) == 6:
            family, identity, action = parts[3:]
            if family == "flows" and action == "delete":
                return self.service.delete_flow(identity, payload, actor), 200
            if family == "flows" and action == "unlink-task":
                return self.service.unlink_task(identity, payload, actor), 200
            if family == "items" and action == "remove":
                return self.service.delete_item(identity, payload, actor), 200
            if family == "settlements" and action == "remove":
                return self.service.delete_settlement(identity, payload, actor), 200
            if family == "task-occurrences" and action == "reopen-check":
                return self.tasks.reopen_check(identity, payload), 200
        raise CashError("cash_not_found", "现金接口不存在或不支持该方法。", 404)

    @staticmethod
    def _no_query(query: dict) -> None:
        if query:
            raise CashError("cash_invalid_input", "此操作不接受查询参数。")
