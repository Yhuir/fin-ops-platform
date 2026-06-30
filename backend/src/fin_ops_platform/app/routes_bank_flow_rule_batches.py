from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.bank_batch_application_service import BankBatchPersistenceError
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE
from fin_ops_platform.services.bank_flow_rule_batch_application_service import BankFlowRuleBatchApplicationService
from fin_ops_platform.services.read_model_write_targets import write_target_envelope

MutationSessionResolver = Callable[[dict[str, str] | None], OARequestSession | Any]
JsonBodyLoader = Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]]
JsonResponse = Callable[[HTTPStatus, dict[str, Any]], Any]


class BankFlowRuleBatchApiRoutes:
    def __init__(
        self,
        application_service: BankFlowRuleBatchApplicationService,
        *,
        resolve_mutation_session: MutationSessionResolver | None = None,
        load_json_body: JsonBodyLoader | None = None,
        json_response: JsonResponse | None = None,
    ) -> None:
        self._application_service = application_service
        self._resolve_mutation_session = resolve_mutation_session
        self._load_json_body = load_json_body
        self._json_response = json_response

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any | None:
        if method == "GET" and route_path == "/api/bank-flow-rule-batches":
            return self._json_response_for(*self.list_batches(query))
        if method == "GET" and route_path == "/api/bank-flow-rule-batches/tag-rules":
            return self._json_response_for(*self.tag_rules())
        if method == "PUT" and route_path == "/api/bank-flow-rule-batches/tag-rules":
            return self._json_write(body, headers, lambda payload, session: self.update_tag_rules(payload, session=session))
        if method == "POST" and route_path == "/api/bank-flow-rule-batches/submit-selection":
            return self._json_write(body, headers, lambda payload, session: self.submit_selection(payload, session=session))
        if method == "POST" and route_path == "/api/bank-flow-rule-batches/reset-submitted":
            return self._json_write(
                body,
                headers,
                lambda payload, session: self.reset_submitted_batches(payload, session=session),
            )
        if method == "POST" and route_path == "/api/bank-flow-rule-batches/rebaseline-no-oa/dry-run":
            return self._json_write(body, headers, lambda payload, session: self.rebaseline_no_oa_dry_run(payload, session=session))
        if method == "POST" and route_path == "/api/bank-flow-rule-batches/rebaseline-no-oa/apply":
            return self._json_write(body, headers, lambda payload, session: self.apply_rebaseline_no_oa(payload, session=session))

        prefix = "/api/bank-flow-rule-batches/"
        submit_suffix = "/submit"
        withdraw_suffix = "/withdraw"
        if not route_path.startswith(prefix):
            return None
        if method == "GET":
            batch_id = unquote(route_path[len(prefix):])
            return self._json_response_for(*self.detail(batch_id))
        if method == "POST" and route_path.endswith(submit_suffix):
            batch_id = unquote(route_path[len(prefix):-len(submit_suffix)])
            return self._json_write(
                body,
                headers,
                lambda payload, session: self.submit_batch(batch_id, payload, session=session),
            )
        if method == "POST" and route_path.endswith(withdraw_suffix):
            batch_id = unquote(route_path[len(prefix):-len(withdraw_suffix)])
            return self._json_write(
                body,
                headers,
                lambda payload, session: self.withdraw_batch(batch_id, payload, session=session),
            )
        return None

    def list_batches(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            return HTTPStatus.OK, self._application_service.list_batches_payload(
                query,
                relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            )
        except ValueError as exc:
            return self._value_error_response(exc)

    def detail(self, batch_id: str) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            return HTTPStatus.OK, self._application_service.detail_payload(batch_id)
        except KeyError:
            return self._unknown_batch_response()

    def tag_rules(self) -> tuple[HTTPStatus, dict[str, Any]]:
        return HTTPStatus.OK, self._tag_rules_payload(self._application_service.tag_selection_payload())

    def update_tag_rules(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        if "selected_tag_codes" in payload or "selectedTagCodes" in payload:
            return HTTPStatus.BAD_REQUEST, {
                "error": "bank_flow_rule_batch_selected_tag_codes_forbidden",
                "message": "流水规则批量处理不接受 selected_tag_codes，请提交 rules。",
            }
        try:
            result = self._application_service.update_tag_selection(
                payload,
                actor_id=self._actor(payload, session),
            )
        except AppSettingsValidationError as exc:
            status = (
                HTTPStatus.CONFLICT
                if exc.error_code == "no_oa_bank_batch_tag_selection_version_conflict"
                else HTTPStatus.BAD_REQUEST
            )
            error = (
                "bank_flow_rule_batch_tag_rules_version_conflict"
                if exc.error_code == "no_oa_bank_batch_tag_selection_version_conflict"
                else exc.error_code
            )
            return status, {"error": error, "message": str(exc)}
        return HTTPStatus.OK, self._tag_rules_payload(result)

    def submit_batch(
        self,
        batch_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.submit_batch(
                batch_id,
                actor=self._actor(payload, session),
                expected_version=self._optional_int(payload.get("expected_version")),
                note=str(payload.get("note") or "").strip() or None,
                relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            )
        except KeyError:
            return self._unknown_batch_response()
        except BankBatchPersistenceError as exc:
            return self._persistence_error_response(exc)
        except ValueError as exc:
            return self._value_error_response(exc)
        return HTTPStatus.OK, result

    def withdraw_batch(
        self,
        batch_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.withdraw_batch(
                batch_id,
                actor=self._actor(payload, session),
                expected_version=self._optional_int(payload.get("expected_version")),
                reason=str(payload.get("reason") or payload.get("note") or "").strip() or None,
            )
        except KeyError:
            return self._unknown_batch_response()
        except BankBatchPersistenceError as exc:
            return self._persistence_error_response(exc)
        except ValueError as exc:
            return self._value_error_response(exc)
        result.update(
            write_target_envelope(
                read_model_key=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                scope_keys=result.get("affected_months"),
                fallback_scope_key="all",
            )
        )
        return HTTPStatus.OK, result

    def submit_selection(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        raw_transaction_ids = payload.get("transaction_ids")
        if not isinstance(raw_transaction_ids, list):
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_bank_flow_rule_batch_request",
                "message": "transaction_ids must be an array.",
            }
        try:
            result = self._application_service.submit_selected_rows(
                row_ids=[str(row_id) for row_id in raw_transaction_ids],
                actor=self._actor(payload, session),
                note=str(payload.get("note") or "").strip() or None,
                relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            )
        except BankBatchPersistenceError as exc:
            return self._persistence_error_response(exc)
        except ValueError as exc:
            return self._value_error_response(exc)
        return HTTPStatus.OK, result

    def reset_submitted_batches(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.reset_submitted_bank_flow_rule_batches(
                actor=self._actor(payload, session),
                reason=str(payload.get("reason") or payload.get("note") or "").strip() or None,
            )
        except BankBatchPersistenceError as exc:
            return self._persistence_error_response(exc)
        except ValueError as exc:
            return self._value_error_response(exc)
        return HTTPStatus.OK, result

    def rebaseline_no_oa_dry_run(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        del payload, session
        return HTTPStatus.OK, self._application_service.rebaseline_submitted_no_oa_batches_dry_run()

    def apply_rebaseline_no_oa(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.apply_submitted_no_oa_rebaseline(
                actor=self._actor(payload, session),
                reason=str(payload.get("reason") or payload.get("note") or "").strip() or None,
                manifest=payload.get("manifest") or payload.get("dry_run_manifest"),
            )
        except BankBatchPersistenceError as exc:
            return self._persistence_error_response(exc)
        except ValueError as exc:
            return self._value_error_response(exc)
        return HTTPStatus.OK, result

    @staticmethod
    def _tag_rules_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in dict(payload).items()
            if key
            not in {
                "selected_tag_codes",
                "selectedTagCodes",
                "inactive_selected_tag_codes",
                "inactiveSelectedTagCodes",
            }
        }

    @staticmethod
    def _actor(payload: dict[str, Any], session: OARequestSession) -> str:
        return str(payload.get("actor") or session.identity.username or session.identity.user_id or "web_finance_user")

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    @staticmethod
    def _unknown_batch_response() -> tuple[HTTPStatus, dict[str, Any]]:
        return HTTPStatus.NOT_FOUND, {"error": "unknown_bank_flow_rule_batch", "message": "流水规则批次不存在。"}

    @staticmethod
    def _persistence_error_response(exc: BankBatchPersistenceError) -> tuple[HTTPStatus, dict[str, Any]]:
        return HTTPStatus.INTERNAL_SERVER_ERROR, {
            "error": exc.error_code,
            "message": str(exc) or "流水规则批次保存失败，请稍后重试。",
        }

    @classmethod
    def _value_error_response(cls, exc: ValueError) -> tuple[HTTPStatus, dict[str, Any]]:
        error_code = cls._error_code(exc)
        status = (
            HTTPStatus.CONFLICT
            if error_code
            in {
                "no_oa_bank_batch_version_conflict",
                "no_oa_bank_batch_relation_read_model_not_fresh",
                "no_oa_bank_batch_relation_active_row_conflict",
            }
            else HTTPStatus.BAD_REQUEST
        )
        response: dict[str, Any] = {"error": error_code, "message": str(exc)}
        details = getattr(exc, "payload", None)
        if isinstance(details, dict):
            response.update(
                {
                    str(key): value
                    for key, value in details.items()
                    if str(key)
                    in {
                        "read_model_status",
                        "read_model_stale_reasons",
                        "read_model_scope_keys",
                        "refresh_enqueued",
                        "conflicting_case_ids",
                        "row_ids",
                        "case_id",
                    }
                }
            )
        return status, response

    @staticmethod
    def _error_code(exc: ValueError) -> str:
        error_code = getattr(exc, "error_code", None)
        if isinstance(error_code, str) and error_code.strip():
            return error_code.strip()
        message = str(exc).strip()
        if message == "no_oa_bank_batch_version_conflict":
            return message
        return message or "invalid_bank_flow_rule_batch_request"

    def _json_write(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        handler: Callable[[dict[str, Any], OARequestSession], tuple[HTTPStatus, dict[str, Any]]],
    ) -> Any:
        if self._resolve_mutation_session is None:
            raise RuntimeError("Bank flow rule batch mutation session resolver is not configured.")
        session = self._resolve_mutation_session(headers)
        if not isinstance(session, OARequestSession):
            return session
        payload, error = self._load_body(body)
        if error is not None:
            return error
        return self._json_response_for(*handler(payload, session))

    def _load_body(self, body: str | bytes | None) -> tuple[dict[str, Any], Any | None]:
        if self._load_json_body is None:
            raise RuntimeError("Bank flow rule batch JSON body loader is not configured.")
        return self._load_json_body(body)

    def _json_response_for(self, status: HTTPStatus, payload: dict[str, Any]) -> Any:
        if self._json_response is None:
            return status, payload
        return self._json_response(status, payload)
