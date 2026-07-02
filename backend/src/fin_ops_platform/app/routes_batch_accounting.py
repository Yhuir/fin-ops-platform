from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.services.read_model_write_targets import write_target_envelope
from fin_ops_platform.services.batch_accounting_service import BatchAccountingError, BatchAccountingService


class BatchAccountingApiRoutes:
    def __init__(
        self,
        service_factory: Callable[..., BatchAccountingService],
        *,
        scope_keys_for_row_ids: Callable[..., set[str]],
        execute_derived_data_lifecycle_event: Callable[..., Any],
        schedule_read_model_persist: Callable[..., Any],
    ) -> None:
        self._service_factory = service_factory
        self._scope_keys_for_row_ids = scope_keys_for_row_ids
        self._execute_derived_data_lifecycle_event = execute_derived_data_lifecycle_event
        self._schedule_read_model_persist = schedule_read_model_persist

    def list_payload(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        year = (query.get("year") or [""])[0]
        bank_year = (query.get("bank_year") or [year])[0]
        bucket = (query.get("bucket") or ["unsubmitted"])[0] or "unsubmitted"
        try:
            payload = self._service_factory(use_sql_read_model=True).build_payload(
                year=year,
                bank_year=bank_year,
                bucket=bucket,
                page=self._query_value(query, "page"),
                page_size=self._query_value(query, "page_size", "pageSize"),
                bank_page=self._query_value(query, "bank_page", "bankPage"),
                bank_page_size=self._query_value(query, "bank_page_size", "bankPageSize"),
                oa_page=self._query_value(query, "oa_page", "oaPage"),
                oa_page_size=self._query_value(query, "oa_page_size", "oaPageSize"),
            )
        except BatchAccountingError as exc:
            return self._batch_accounting_error_response(exc)
        return HTTPStatus.OK, payload

    def submit(self, payload: dict[str, Any], *, session: OARequestSession) -> tuple[HTTPStatus, dict[str, Any]]:
        actor = self._actor(payload, session)
        year = str(payload.get("year") or "")
        try:
            result = self._service_factory(use_sql_read_model=True).submit(
                year=year,
                bank_year=str(payload.get("bank_year") or year),
                bank_row_id=str(payload.get("bank_row_id") or ""),
                oa_row_ids=list(payload.get("oa_row_ids") or []),
                actor=actor,
                note=str(payload.get("note") or ""),
                expected_version=self._optional_int(payload.get("expected_version")),
            )
        except BatchAccountingError as exc:
            return self._batch_accounting_error_response(exc)
        except (TypeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "invalid_batch_accounting_request", "message": str(exc)}

        changed_scope_keys = self._changed_scope_keys(result)
        self._after_relation_mutation(
            action_name="submit_batch_accounting",
            changed_scope_keys=changed_scope_keys,
        )
        return HTTPStatus.OK, {
            **result,
            "affected_months": changed_scope_keys,
            **write_target_envelope(read_model_key="workbench_relation", scope_keys=changed_scope_keys),
        }

    def withdraw(
        self,
        relation_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._service_factory(use_sql_read_model=True).withdraw(
                relation_id=relation_id,
                actor=self._actor(payload, session),
                reason=str(payload.get("reason") or payload.get("note") or ""),
                expected_version=self._optional_int(payload.get("expected_version")),
            )
        except BatchAccountingError as exc:
            return self._batch_accounting_error_response(exc)
        except KeyError as exc:
            return HTTPStatus.BAD_REQUEST, {
                "error": str(exc).strip("'") or "workbench_pair_relation_no_withdraw_history",
                "message": str(exc),
            }

        changed_scope_keys = self._changed_scope_keys(result)
        self._after_relation_mutation(
            action_name="withdraw_batch_accounting",
            changed_scope_keys=changed_scope_keys,
        )
        return HTTPStatus.OK, {
            **result,
            "affected_months": changed_scope_keys,
            **write_target_envelope(read_model_key="workbench_relation", scope_keys=changed_scope_keys),
        }

    @staticmethod
    def _actor(payload: dict[str, Any], session: OARequestSession) -> str:
        return str(payload.get("actor") or session.identity.username or session.identity.user_id or "web_finance_user")

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    def _changed_scope_keys(self, result: dict[str, Any]) -> list[str]:
        explicit_scope_keys = self._normalized_scope_keys(result.get("affected_scope_keys"))
        if explicit_scope_keys:
            return explicit_scope_keys
        return sorted(
            self._scope_keys_for_row_ids(
                month="all",
                row_ids=list(result.get("affected_row_ids") or []),
                month_scope=str(result.get("month_scope") or ""),
            )
        )

    @staticmethod
    def _normalized_scope_keys(value: Any) -> list[str]:
        values = [value] if isinstance(value, str) else list(value or []) if isinstance(value, list | tuple | set) else []
        concrete: list[str] = []
        seen: set[str] = set()
        has_all = False
        for item in values:
            scope_key = str(item or "").strip()
            if scope_key == "all":
                has_all = True
                continue
            if not scope_key or len(scope_key) != 7 or scope_key[4] != "-":
                continue
            if scope_key not in seen:
                seen.add(scope_key)
                concrete.append(scope_key)
        if concrete:
            return sorted(concrete)
        return ["all"] if has_all else []

    def _after_relation_mutation(self, *, action_name: str, changed_scope_keys: list[str]) -> None:
        self._execute_derived_data_lifecycle_event(
            "batch_accounting_relation_changed",
            scope_keys=changed_scope_keys,
            include_all=False,
            metadata={"source": action_name},
        )
        self._schedule_read_model_persist(
            changed_scope_keys=changed_scope_keys,
            action_name=action_name,
        )

    @staticmethod
    def _query_value(query: dict[str, list[str]], *names: str) -> str | None:
        for name in names:
            if name in query:
                return (query.get(name) or [None])[0]
        return None

    @staticmethod
    def _batch_accounting_error_response(exc: BatchAccountingError) -> tuple[HTTPStatus, dict[str, Any]]:
        status = HTTPStatus.CONFLICT if exc.code == "batch_accounting_version_conflict" else HTTPStatus.BAD_REQUEST
        payload: dict[str, Any] = {"error": exc.code, "message": str(exc)}
        payload.update(exc.payload)
        return status, payload
