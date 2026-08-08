from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.services.app_settings_service import (
    AppSettingsPersistenceError,
    AppSettingsValidationError,
)
from fin_ops_platform.services.batch_accounting_service import BatchAccountingError, BatchAccountingService


class BatchAccountingApiRoutes:
    def __init__(
        self,
        service_factory: Callable[..., BatchAccountingService],
    ) -> None:
        self._service_factory = service_factory

    def list_payload(
        self,
        query: dict[str, list[str]],
        *,
        timing_observer: Callable[[str, float], None] | None = None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        year = (query.get("year") or [""])[0]
        bank_year = (query.get("bank_year") or [year])[0]
        bucket = (query.get("bucket") or ["unsubmitted"])[0] or "unsubmitted"
        try:
            payload = self._service_factory().build_payload(
                year=year,
                bank_year=bank_year,
                bucket=bucket,
                page=self._query_value(query, "page"),
                page_size=self._query_value(query, "page_size", "pageSize"),
                bank_page=self._query_value(query, "bank_page", "bankPage"),
                bank_page_size=self._query_value(query, "bank_page_size", "bankPageSize"),
                oa_page=self._query_value(query, "oa_page", "oaPage"),
                oa_page_size=self._query_value(query, "oa_page_size", "oaPageSize"),
                oa_search=self._query_value(query, "oa_search", "oaSearch"),
                timing_observer=timing_observer,
            )
        except BatchAccountingError as exc:
            return self._batch_accounting_error_response(exc)
        return HTTPStatus.OK, payload

    def submit(self, payload: dict[str, Any], *, session: OARequestSession) -> tuple[HTTPStatus, dict[str, Any]]:
        actor = self._actor(payload, session)
        year = str(payload.get("year") or "")
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            return HTTPStatus.BAD_REQUEST, {
                "error": "batch_accounting_idempotency_key_required",
                "message": "idempotency_key is required.",
            }
        try:
            result = self._service_factory().submit(
                year=year,
                bank_year=str(payload.get("bank_year") or year),
                bank_row_id=str(payload.get("bank_row_id") or ""),
                oa_row_ids=list(payload.get("oa_row_ids") or []),
                actor=actor,
                note=str(payload.get("note") or ""),
                expected_version=self._optional_int(payload.get("expected_version")),
                expected_tag_selection_version=self._optional_int(
                    payload.get("expected_tag_selection_version")
                ),
                idempotency_key=idempotency_key,
            )
        except BatchAccountingError as exc:
            return self._batch_accounting_error_response(exc)
        except (TypeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "invalid_batch_accounting_request", "message": str(exc)}

        changed_scope_keys = self._changed_scope_keys(result)
        return HTTPStatus.OK, {
            **result,
            "affected_months": changed_scope_keys,
        }

    def tag_rules(self, *, can_save: bool) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            return HTTPStatus.OK, self._service_factory().tag_rules_payload(can_save=can_save)
        except BatchAccountingError as exc:
            return self._batch_accounting_error_response(exc)

    def update_tag_rules(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._service_factory().update_tag_rules(
                payload,
                actor=self._actor(payload, session),
            )
        except AppSettingsValidationError as exc:
            status = (
                HTTPStatus.CONFLICT
                if exc.error_code == "batch_accounting_tag_selection_version_conflict"
                else HTTPStatus.BAD_REQUEST
            )
            return status, {"error": exc.error_code, "message": str(exc)}
        except AppSettingsPersistenceError as exc:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": "batch_accounting_tag_selection_persistence_failed",
                "message": str(exc),
            }
        except BatchAccountingError as exc:
            return self._batch_accounting_error_response(exc)
        return HTTPStatus.OK, result

    def withdraw(
        self,
        relation_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            return HTTPStatus.BAD_REQUEST, {
                "error": "batch_accounting_idempotency_key_required",
                "message": "idempotency_key is required.",
            }
        try:
            result = self._service_factory().withdraw(
                relation_id=relation_id,
                actor=self._actor(payload, session),
                reason=str(payload.get("reason") or payload.get("note") or ""),
                expected_version=self._optional_int(payload.get("expected_version")),
                idempotency_key=idempotency_key,
            )
        except BatchAccountingError as exc:
            return self._batch_accounting_error_response(exc)
        except KeyError as exc:
            return HTTPStatus.BAD_REQUEST, {
                "error": str(exc).strip("'") or "workbench_pair_relation_no_withdraw_history",
                "message": str(exc),
            }

        changed_scope_keys = self._changed_scope_keys(result)
        return HTTPStatus.OK, {
            **result,
            "affected_months": changed_scope_keys,
        }

    @staticmethod
    def _actor(payload: dict[str, Any], session: OARequestSession) -> str:
        del payload
        return str(session.identity.username or session.identity.user_id or "web_finance_user")

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    def _changed_scope_keys(self, result: dict[str, Any]) -> list[str]:
        explicit_scope_keys = self._normalized_scope_keys(result.get("affected_scope_keys"))
        if explicit_scope_keys:
            return explicit_scope_keys
        affected_months = self._normalized_scope_keys(result.get("affected_months"))
        if affected_months:
            return affected_months
        return ["all"]

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

    @staticmethod
    def _query_value(query: dict[str, list[str]], *names: str) -> str | None:
        for name in names:
            if name in query:
                return (query.get(name) or [None])[0]
        return None

    @staticmethod
    def _batch_accounting_error_response(exc: BatchAccountingError) -> tuple[HTTPStatus, dict[str, Any]]:
        if exc.code in {
            "batch_accounting_version_conflict",
            "batch_accounting_relation_conflict",
            "batch_accounting_bank_row_already_linked",
            "batch_accounting_tag_selection_version_conflict",
            "batch_accounting_bank_tag_not_selected",
        }:
            status = HTTPStatus.CONFLICT
        elif exc.code in {
            "batch_accounting_canonical_query_unavailable",
            "batch_accounting_relation_command_unavailable",
        }:
            status = HTTPStatus.SERVICE_UNAVAILABLE
        else:
            status = HTTPStatus.BAD_REQUEST
        payload: dict[str, Any] = {"error": exc.code, "message": str(exc)}
        payload.update(exc.payload)
        return status, payload
