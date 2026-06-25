from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.turnover_ledger_export_service import (
    TurnoverLedgerExportLimitError,
    TurnoverLedgerExportService,
)
from fin_ops_platform.services.turnover_ledger_query_service import TurnoverLedgerQueryService
from fin_ops_platform.services.turnover_ledger_service import TurnoverLedgerService
from fin_ops_platform.services.turnover_relation_service import (
    TurnoverRelationService,
    TurnoverRelationValidationError,
)
from fin_ops_platform.services.turnover_ledger_write_adapters import (
    TurnoverLedgerRelationExtraRequestBoundaryError,
    TurnoverLedgerWritePreconditionError,
)
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryConflictError,
    BankTransactionCategoryValidationError,
)
from fin_ops_platform.services.workbench_idempotency import (
    WorkbenchIdempotencyFailed,
    WorkbenchIdempotencyInProgress,
    WorkbenchIdempotencyKeyConflict,
)


VALID_EXTRA_RATE_TYPES = {"annual", "monthly", "none"}
VALID_FAMILIES = {"all", "personal", "company", "bank", "business", "uncategorized"}
MONEY_QUANT = Decimal("0.01")
RATE_QUANT = Decimal("0.000001")
ZERO = Decimal("0.00")


class TurnoverLedgerExtraValidationError(ValueError):
    pass


class InMemoryTurnoverLedgerExtraService:
    def __init__(self, snapshot: dict[str, object] | None = None) -> None:
        self._extras: dict[str, dict[str, object]] = {}
        if isinstance(snapshot, dict):
            for item in list(snapshot.get("extras") or []):
                if not isinstance(item, dict):
                    continue
                relation_id = str(item.get("relation_id") or "").strip()
                if relation_id:
                    self._extras[relation_id] = self._normalize_extra(relation_id, item, actor=None, touch=False)

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, object] | None) -> "InMemoryTurnoverLedgerExtraService":
        return cls(snapshot)

    def snapshot(self) -> dict[str, object]:
        return {
            "version": 1,
            "extras": [dict(extra) for _, extra in sorted(self._extras.items())],
        }

    def get(self, relation_id: str) -> dict[str, object]:
        normalized_relation_id = self._normalize_relation_id(relation_id)
        return dict(self._extras.get(normalized_relation_id) or self._default_extra(normalized_relation_id))

    def upsert(self, relation_id: str, payload: dict[str, object], *, actor: str) -> dict[str, object]:
        normalized_relation_id = self._normalize_relation_id(relation_id)
        if not isinstance(payload, dict):
            raise TurnoverLedgerExtraValidationError("payload must be an object.")
        current = self.get(normalized_relation_id)
        merged = {**current, **payload, "relation_id": normalized_relation_id}
        normalized = self._normalize_extra(normalized_relation_id, merged, actor=actor, touch=True)
        self._extras[normalized_relation_id] = normalized
        return dict(normalized)

    @staticmethod
    def _normalize_relation_id(relation_id: str) -> str:
        normalized = str(relation_id or "").strip()
        if not normalized:
            raise TurnoverLedgerExtraValidationError("relation_id is required.")
        return normalized

    @classmethod
    def _default_extra(cls, relation_id: str) -> dict[str, object]:
        return {
            "relation_id": relation_id,
            "interest_rate_type": "none",
            "interest_rate_value": "0.000000",
            "interest_paid_amount": "0.00",
            "interest_paid_date": None,
            "interest_payment_method": "",
            "note": "",
            "updated_at": None,
            "updated_by": None,
        }

    @classmethod
    def _normalize_extra(
        cls,
        relation_id: str,
        payload: dict[str, object],
        *,
        actor: str | None,
        touch: bool,
    ) -> dict[str, object]:
        rate_type = str(payload.get("interest_rate_type") or "none").strip().lower()
        if rate_type not in VALID_EXTRA_RATE_TYPES:
            raise TurnoverLedgerExtraValidationError("interest_rate_type must be annual, monthly, or none.")
        rate_value = ZERO if rate_type == "none" else cls._non_negative_decimal(payload.get("interest_rate_value"), RATE_QUANT)
        paid_amount = cls._non_negative_decimal(payload.get("interest_paid_amount"), MONEY_QUANT)
        paid_date = cls._date_or_none(payload.get("interest_paid_date"))
        now = datetime.now(UTC).isoformat() if touch else payload.get("updated_at")
        updated_by = actor if touch else payload.get("updated_by")
        return {
            "relation_id": relation_id,
            "interest_rate_type": rate_type,
            "interest_rate_value": f"{rate_value.quantize(RATE_QUANT):.6f}",
            "interest_paid_amount": f"{paid_amount.quantize(MONEY_QUANT):.2f}",
            "interest_paid_date": paid_date,
            "interest_payment_method": cls._trim_text(payload.get("interest_payment_method"), max_length=80),
            "note": cls._trim_text(payload.get("note"), max_length=500),
            "updated_at": str(now) if now else None,
            "updated_by": str(updated_by) if updated_by else None,
        }

    @staticmethod
    def _non_negative_decimal(value: object, quant: Decimal) -> Decimal:
        if value is None or str(value).strip() == "":
            return ZERO.quantize(quant)
        try:
            amount = Decimal(str(value).replace(",", "").strip()).quantize(quant)
        except (InvalidOperation, ValueError):
            raise TurnoverLedgerExtraValidationError("decimal fields must be valid numbers.") from None
        if amount < ZERO:
            raise TurnoverLedgerExtraValidationError("decimal fields must be non-negative.")
        return amount

    @staticmethod
    def _date_or_none(value: object) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise TurnoverLedgerExtraValidationError("date fields must be ISO date strings.") from None

    @staticmethod
    def _trim_text(value: object, *, max_length: int) -> str:
        return str(value or "").strip()[:max_length]


class TurnoverLedgerApiRoutes:
    def __init__(
        self,
        *,
        ledger_service: TurnoverLedgerService,
        relation_service: TurnoverRelationService,
        extra_service: Any | None = None,
        query_service: TurnoverLedgerQueryService | None = None,
        json_response: Callable[[HTTPStatus, dict[str, object]], Any] | None = None,
        export_response: Callable[[str, bytes], Any] | None = None,
        tag_selection_provider: Callable[[], dict[str, object]] | None = None,
        mutation_session_resolver: Callable[[dict[str, str] | None], Any] | None = None,
        session_error_detector: Callable[[Any], bool] | None = None,
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, object], Any | None]] | None = None,
        tenant_id_provider: Callable[[Any], str] | None = None,
        tag_selection_write_boundary_provider: Callable[[], Any] | None = None,
        bank_row_tags_request_boundary_provider: Callable[[], Any] | None = None,
        relation_extra_request_boundary_provider: Callable[[], Any] | None = None,
        relation_extra_tenant_id_provider: Callable[[], str] | None = None,
        confirm_relation_request_boundary_provider: Callable[[], Any] | None = None,
        closure_request_boundary_provider: Callable[[], Any] | None = None,
        write_precondition_error_payload: Callable[[TurnoverLedgerWritePreconditionError], dict[str, object]] | None = None,
    ) -> None:
        self._ledger_service = ledger_service
        self._relation_service = relation_service
        self._extra_service = extra_service or InMemoryTurnoverLedgerExtraService()
        self._query_service = query_service
        self._export_service = TurnoverLedgerExportService(self.list_grouped_ledger)
        self._json_response = json_response
        self._export_response = export_response
        self._tag_selection_provider = tag_selection_provider
        self._mutation_session_resolver = mutation_session_resolver
        self._session_error_detector = session_error_detector
        self._load_json_body = load_json_body
        self._tenant_id_provider = tenant_id_provider
        self._tag_selection_write_boundary_provider = tag_selection_write_boundary_provider
        self._bank_row_tags_request_boundary_provider = bank_row_tags_request_boundary_provider
        self._relation_extra_request_boundary_provider = relation_extra_request_boundary_provider
        self._relation_extra_tenant_id_provider = relation_extra_tenant_id_provider
        self._confirm_relation_request_boundary_provider = confirm_relation_request_boundary_provider
        self._closure_request_boundary_provider = closure_request_boundary_provider
        self._write_precondition_error_payload = write_precondition_error_payload

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any | None:
        if method == "GET" and route_path == "/api/turnover-ledger/export-preview":
            return self.handle_export_preview_route(query)
        if method == "GET" and route_path == "/api/turnover-ledger/export":
            return self.handle_export_route(query)
        if method == "GET" and route_path == "/api/turnover-ledger/tag-selection":
            return self.handle_tag_selection_route()
        if method == "GET" and route_path == "/api/turnover-ledger":
            return self.handle_list_route(query)
        if method == "PUT" and route_path == "/api/turnover-ledger/tag-selection":
            return self.handle_tag_selection_update_route(body, headers)
        if method == "POST" and route_path == "/api/turnover-ledger/bank-row-tags/batch":
            return self.handle_bank_row_tags_batch_route(body, headers)
        if method == "PUT" and route_path.startswith("/api/turnover-ledger/relations/") and route_path.endswith("/extra"):
            relation_id = unquote(route_path.rsplit("/", 2)[-2])
            return self.handle_relation_extra_update_route(relation_id, body, headers)
        if method == "POST" and route_path == "/api/turnover-ledger/relations/confirm":
            return self.handle_confirm_relation_route(body, headers)
        if method == "POST" and route_path == "/api/turnover-ledger/closures/confirm":
            return self.handle_closure_confirm_route(body, headers)
        if method == "POST" and route_path == "/api/turnover-ledger/closures/withdraw":
            return self.handle_closure_withdraw_route(body, headers)
        if method == "GET" and route_path.startswith("/api/turnover-ledger/relations/") and route_path.endswith("/extra"):
            relation_id = unquote(route_path.rsplit("/", 2)[-2])
            return self.handle_relation_extra_route(relation_id)
        if method == "GET" and route_path.startswith("/api/turnover-ledger/relations/"):
            relation_id = unquote(route_path.rsplit("/", 1)[-1])
            return self.handle_relation_route(relation_id)
        return None

    def handle_list_route(self, query: dict[str, list[str]]) -> Any:
        view = self._query_value(query, "view", None)
        family = self._query_value(query, "family", "all")
        direction = self._query_value(query, "direction", "all")
        status = self._query_value(query, "status", None)
        page = self._query_int(query, "page", 1)
        page_size = self._query_int(query, "page_size", 50)
        try:
            payload = self.list_ledger(
                view=view,
                family=family,
                direction=direction,
                status=status,
                page=page,
                page_size=page_size,
            )
        except (TypeError, ValueError) as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_turnover_ledger_request", "message": str(exc)},
            )
        return self._respond(HTTPStatus.OK, payload)

    def handle_tag_selection_route(self) -> Any:
        if self._tag_selection_provider is None:
            raise RuntimeError("turnover ledger tag selection provider is not configured")
        return self._respond(HTTPStatus.OK, self._tag_selection_provider())

    def handle_tag_selection_update_route(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        self._ensure_tag_selection_write_ports()
        session_response = self._mutation_session_resolver(headers)  # type: ignore[misc]
        if self._session_error_detector(session_response):  # type: ignore[misc]
            return session_response
        payload, error = self._load_json_body(body)  # type: ignore[misc]
        if error is not None:
            return error
        identity = session_response.identity
        actor = identity.username or identity.user_id or "web_finance_user"
        facade = self._tag_selection_write_boundary_provider()  # type: ignore[misc]
        idempotency_key = str(payload.get("idempotency_key") or payload.get("idempotencyKey") or "").strip() or None
        try:
            result = facade.update_tag_selection_from_request(
                payload=payload,
                actor_id=actor,
                tenant_id=self._tenant_id_provider(session_response),  # type: ignore[misc]
                idempotency_key=idempotency_key,
            )
        except AppSettingsValidationError as exc:
            status = (
                HTTPStatus.CONFLICT
                if exc.error_code == "turnover_ledger_tag_selection_version_conflict"
                else HTTPStatus.BAD_REQUEST
            )
            return self._respond(status, {"error": exc.error_code, "message": str(exc)})
        except (WorkbenchIdempotencyKeyConflict, WorkbenchIdempotencyInProgress, WorkbenchIdempotencyFailed) as exc:
            return self._respond(HTTPStatus.CONFLICT, exc.to_response_payload())
        return self._respond(HTTPStatus.OK, result)

    def handle_relation_extra_update_route(
        self,
        relation_id: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        self._ensure_relation_extra_write_ports()
        session_response = self._mutation_session_resolver(headers)  # type: ignore[misc]
        if self._session_error_detector(session_response):  # type: ignore[misc]
            return session_response
        payload, error = self._load_json_body(body)  # type: ignore[misc]
        if error is not None:
            return error
        if not isinstance(payload, dict):
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_turnover_ledger_extra", "message": "payload must be an object."},
            )
        identity = session_response.identity
        actor = identity.username or identity.user_id or "web_finance_user"
        try:
            facade = self._relation_extra_request_boundary_provider()  # type: ignore[misc]
            result = facade.update_relation_extra_from_request(
                relation_id=relation_id,
                payload=payload,
                actor_id=actor,
                tenant_id=self._relation_extra_tenant_id_provider(),  # type: ignore[misc]
                scope_keys=["all"],
            )
        except KeyError:
            return self._unknown_relation_response()
        except TurnoverLedgerRelationExtraRequestBoundaryError as exc:
            return self._respond(
                exc.status_code,
                {"error": exc.error_code, "message": str(exc)},
            )
        except TurnoverLedgerWritePreconditionError as exc:
            return self._respond(
                exc.status_code,
                self._write_precondition_error_payload(exc),  # type: ignore[misc]
            )
        except (WorkbenchIdempotencyKeyConflict, WorkbenchIdempotencyInProgress, WorkbenchIdempotencyFailed) as exc:
            return self._respond(HTTPStatus.CONFLICT, exc.to_response_payload())
        except (TurnoverLedgerExtraValidationError, ValueError) as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_turnover_ledger_extra", "message": str(exc)},
            )
        return self._respond(HTTPStatus.OK, result)

    def handle_confirm_relation_route(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        self._ensure_confirm_relation_write_ports()
        session_response = self._mutation_session_resolver(headers)  # type: ignore[misc]
        if self._session_error_detector(session_response):  # type: ignore[misc]
            return session_response
        payload, error = self._load_json_body(body)  # type: ignore[misc]
        if error is not None:
            return error
        bank_row_ids = payload.get("bank_row_ids")
        if not isinstance(bank_row_ids, list):
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_bank_row_ids", "message": "bank_row_ids must be an array."},
            )
        identity = session_response.identity
        actor = identity.username or identity.user_id or "web_finance_user"
        facade = self._confirm_relation_request_boundary_provider()  # type: ignore[misc]
        expected_versions = payload.get("expected_versions") if isinstance(payload.get("expected_versions"), dict) else {}
        idempotency_key = str(payload.get("idempotency_key") or payload.get("idempotencyKey") or "").strip() or None
        try:
            result = facade.confirm_relation_from_request(
                bank_row_ids=bank_row_ids,
                actor_id=actor,
                tenant_id=self._tenant_id_provider(session_response),  # type: ignore[misc]
                note=str(payload.get("note")) if payload.get("note") is not None else None,
                expected_versions=expected_versions,
                idempotency_key=idempotency_key,
            )
        except TurnoverRelationValidationError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": exc.error_code, "message": str(exc)},
            )
        except TurnoverLedgerWritePreconditionError as exc:
            return self._respond(
                exc.status_code,
                self._write_precondition_error_payload(exc),  # type: ignore[misc]
            )
        except (WorkbenchIdempotencyKeyConflict, WorkbenchIdempotencyInProgress, WorkbenchIdempotencyFailed) as exc:
            return self._respond(HTTPStatus.CONFLICT, exc.to_response_payload())
        return self._respond(HTTPStatus.OK, result)

    def handle_closure_confirm_route(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        self._ensure_closure_write_ports()
        session_response = self._mutation_session_resolver(headers)  # type: ignore[misc]
        if self._session_error_detector(session_response):  # type: ignore[misc]
            return session_response
        payload, error = self._load_json_body(body)  # type: ignore[misc]
        if error is not None:
            return error
        bank_row_ids = payload.get("bank_row_ids")
        if not isinstance(bank_row_ids, list):
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_bank_row_ids", "message": "bank_row_ids must be an array."},
            )
        identity = session_response.identity
        actor = identity.username or identity.user_id or "web_finance_user"
        facade = self._closure_request_boundary_provider()  # type: ignore[misc]
        expected_versions = payload.get("expected_versions") if isinstance(payload.get("expected_versions"), dict) else {}
        idempotency_key = str(payload.get("idempotency_key") or payload.get("idempotencyKey") or "").strip() or None
        try:
            result = facade.confirm_zero_difference_closure_from_request(
                bank_row_ids=bank_row_ids,
                actor_id=actor,
                tenant_id=self._tenant_id_provider(session_response),  # type: ignore[misc]
                note=str(payload.get("note")) if payload.get("note") is not None else None,
                expected_versions=expected_versions,
                idempotency_key=idempotency_key,
            )
        except TurnoverRelationValidationError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": exc.error_code, "message": str(exc)},
            )
        except TurnoverLedgerWritePreconditionError as exc:
            return self._respond(
                exc.status_code,
                self._write_precondition_error_payload(exc),  # type: ignore[misc]
            )
        except (WorkbenchIdempotencyKeyConflict, WorkbenchIdempotencyInProgress, WorkbenchIdempotencyFailed) as exc:
            return self._respond(HTTPStatus.CONFLICT, exc.to_response_payload())
        return self._respond(HTTPStatus.OK, result)

    def handle_closure_withdraw_route(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        self._ensure_closure_write_ports()
        session_response = self._mutation_session_resolver(headers)  # type: ignore[misc]
        if self._session_error_detector(session_response):  # type: ignore[misc]
            return session_response
        payload, error = self._load_json_body(body)  # type: ignore[misc]
        if error is not None:
            return error
        cash_closure_case_id = str(payload.get("cash_closure_case_id") or payload.get("cashClosureCaseId") or "").strip()
        identity = session_response.identity
        actor = identity.username or identity.user_id or "web_finance_user"
        facade = self._closure_request_boundary_provider()  # type: ignore[misc]
        idempotency_key = str(payload.get("idempotency_key") or payload.get("idempotencyKey") or "").strip() or None
        try:
            result = facade.withdraw_cash_closure_case_from_request(
                cash_closure_case_id=cash_closure_case_id,
                actor_id=actor,
                tenant_id=self._tenant_id_provider(session_response),  # type: ignore[misc]
                note=str(payload.get("note")) if payload.get("note") is not None else None,
                idempotency_key=idempotency_key,
            )
        except TurnoverRelationValidationError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": exc.error_code, "message": str(exc)},
            )
        except TurnoverLedgerWritePreconditionError as exc:
            return self._respond(
                exc.status_code,
                self._write_precondition_error_payload(exc),  # type: ignore[misc]
            )
        except (WorkbenchIdempotencyKeyConflict, WorkbenchIdempotencyInProgress, WorkbenchIdempotencyFailed) as exc:
            return self._respond(HTTPStatus.CONFLICT, exc.to_response_payload())
        return self._respond(HTTPStatus.OK, result)

    def handle_bank_row_tags_batch_route(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        self._ensure_bank_row_tags_write_ports()
        session_response = self._mutation_session_resolver(headers)  # type: ignore[misc]
        if self._session_error_detector(session_response):  # type: ignore[misc]
            return session_response
        payload, error = self._load_json_body(body)  # type: ignore[misc]
        if error is not None:
            return error
        if not isinstance(payload, dict) or not isinstance(payload.get("updates"), list):
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_turnover_bank_row_tag_update", "message": "updates must be an array."},
            )
        updates = [dict(update) for update in payload.get("updates") if isinstance(update, dict)]
        if len(updates) != len(payload.get("updates")):
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_turnover_bank_row_tag_update", "message": "each update must be an object."},
            )
        try:
            identity = session_response.identity
            actor = identity.username or identity.user_id or "web_finance_user"
            facade = self._bank_row_tags_request_boundary_provider()  # type: ignore[misc]
            idempotency_key = str(payload.get("idempotency_key") or payload.get("idempotencyKey") or "").strip() or None
            result = facade.update_bank_row_tags_batch_from_request(
                updates=updates,
                actor_id=actor,
                tenant_id=self._tenant_id_provider(session_response),  # type: ignore[misc]
                idempotency_key=idempotency_key,
            )
        except (WorkbenchIdempotencyKeyConflict, WorkbenchIdempotencyInProgress, WorkbenchIdempotencyFailed) as exc:
            return self._respond(HTTPStatus.CONFLICT, exc.to_response_payload())
        except BankTransactionCategoryConflictError as exc:
            return self._respond(
                HTTPStatus.CONFLICT,
                {
                    "error": exc.error_code,
                    "message": str(exc),
                    "transaction_id": exc.transaction_id,
                    "expected_version": exc.expected_version,
                    "actual_version": exc.actual_version,
                },
            )
        except BankTransactionCategoryValidationError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": exc.error_code, "message": str(exc), "transaction_id": exc.transaction_id},
            )
        return self._respond(HTTPStatus.OK, result)

    def handle_export_preview_route(self, query: dict[str, list[str]]) -> Any:
        try:
            payload = self.export_preview(
                family=self._query_value(query, "family", "all") or "all",
                limit=self._query_int(query, "limit", 20),
            )
        except TurnoverLedgerExportLimitError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": exc.error_code, "message": str(exc), "details": dict(exc.details)},
            )
        except (TypeError, ValueError) as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_turnover_ledger_export_request", "message": str(exc)},
            )
        return self._respond(HTTPStatus.OK, payload)

    def handle_export_route(self, query: dict[str, list[str]]) -> Any:
        try:
            filename, content = self.export(family=self._query_value(query, "family", "all") or "all")
        except TurnoverLedgerExportLimitError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": exc.error_code, "message": str(exc), "details": dict(exc.details)},
            )
        except (TypeError, ValueError) as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_turnover_ledger_export_request", "message": str(exc)},
            )
        if self._export_response is None:
            raise RuntimeError("turnover ledger export response port is not configured")
        return self._export_response(filename, content)

    def handle_relation_route(self, relation_id: str) -> Any:
        try:
            payload = self.get_relation(relation_id)
        except KeyError:
            return self._unknown_relation_response()
        return self._respond(HTTPStatus.OK, payload)

    def handle_relation_extra_route(self, relation_id: str) -> Any:
        try:
            payload = self.get_relation_extra(relation_id)
        except KeyError:
            return self._unknown_relation_response()
        return self._respond(HTTPStatus.OK, payload)

    @staticmethod
    def _query_value(
        query: dict[str, list[str]],
        key: str,
        default: str | None,
    ) -> str | None:
        return query.get(key, [default])[0]

    @classmethod
    def _query_int(
        cls,
        query: dict[str, list[str]],
        key: str,
        default: int,
    ) -> int:
        return int(cls._query_value(query, key, str(default)) or default)

    def _unknown_relation_response(self) -> Any:
        return self._respond(
            HTTPStatus.NOT_FOUND,
            {"error": "unknown_relation_id", "message": "往来款关系不存在。"},
        )

    def _respond(self, status: HTTPStatus, payload: dict[str, object]) -> Any:
        if self._json_response is None:
            raise RuntimeError("turnover ledger JSON response port is not configured")
        return self._json_response(status, payload)

    def _ensure_tag_selection_write_ports(self) -> None:
        self._ensure_mutation_route_ports()
        if self._tag_selection_write_boundary_provider is None:
            raise RuntimeError("turnover ledger tag selection write port is not configured")

    def _ensure_bank_row_tags_write_ports(self) -> None:
        self._ensure_mutation_route_ports()
        if self._bank_row_tags_request_boundary_provider is None:
            raise RuntimeError("turnover ledger bank row tags write port is not configured")

    def _ensure_relation_extra_write_ports(self) -> None:
        self._ensure_mutation_route_ports()
        missing = [
            name
            for name, value in {
                "relation_extra_request_boundary_provider": self._relation_extra_request_boundary_provider,
                "relation_extra_tenant_id_provider": self._relation_extra_tenant_id_provider,
                "write_precondition_error_payload": self._write_precondition_error_payload,
            }.items()
            if value is None
        ]
        if missing:
            raise RuntimeError(f"turnover ledger relation extra write ports are not configured: {', '.join(missing)}")

    def _ensure_confirm_relation_write_ports(self) -> None:
        self._ensure_mutation_route_ports()
        missing = [
            name
            for name, value in {
                "confirm_relation_request_boundary_provider": self._confirm_relation_request_boundary_provider,
                "write_precondition_error_payload": self._write_precondition_error_payload,
            }.items()
            if value is None
        ]
        if missing:
            raise RuntimeError(f"turnover ledger confirm write ports are not configured: {', '.join(missing)}")

    def _ensure_closure_write_ports(self) -> None:
        self._ensure_mutation_route_ports()
        missing = [
            name
            for name, value in {
                "closure_request_boundary_provider": self._closure_request_boundary_provider,
                "write_precondition_error_payload": self._write_precondition_error_payload,
            }.items()
            if value is None
        ]
        if missing:
            raise RuntimeError(f"turnover ledger closure write ports are not configured: {', '.join(missing)}")

    def _ensure_mutation_route_ports(self) -> None:
        missing = [
            name
            for name, value in {
                "mutation_session_resolver": self._mutation_session_resolver,
                "session_error_detector": self._session_error_detector,
                "load_json_body": self._load_json_body,
                "tenant_id_provider": self._tenant_id_provider,
            }.items()
            if value is None
        ]
        if missing:
            raise RuntimeError(f"turnover ledger mutation route ports are not configured: {', '.join(missing)}")

    def list_ledger(
        self,
        *,
        view: str | None = None,
        family: str = "all",
        direction: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, object]:
        if self._query_service is not None:
            if str(view or "").strip().lower() == "grouped":
                payload = self._query_service.list_ledger(
                    family=family,
                    direction=direction,
                    status=status,
                    page=page,
                    page_size=page_size,
                )
                if isinstance(payload.get("groups"), list):
                    return self._normalize_grouped_payload(payload)
                if "read_model_status" not in payload:
                    return self.list_grouped_ledger(
                        family=family,
                        direction=direction,
                        status=status,
                        page=page,
                        page_size=page_size,
                    )
                return self._normalize_grouped_payload(self._flat_payload_to_grouped(payload))
            return self._query_service.list_ledger(
                view=view,
                family=family,
                direction=direction,
                status=status,
                page=page,
                page_size=page_size,
            )
        if str(view or "").strip().lower() == "grouped":
            return self.list_grouped_ledger(
                family=family,
                direction=direction,
                status=status,
                page=page,
                page_size=page_size,
            )
        return self._ledger_service.list_ledger(
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
        )

    def list_grouped_ledger(
        self,
        *,
        family: str = "all",
        direction: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, object]:
        list_grouped = getattr(self._ledger_service, "list_grouped_ledger", None)
        if callable(list_grouped):
            payload = list_grouped(family=family, direction=direction, status=status, page=page, page_size=page_size)
            return self._normalize_grouped_payload(payload)
        flat_payload = self._ledger_service.list_ledger(
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
        )
        return self._normalize_grouped_payload(self._flat_payload_to_grouped(flat_payload))

    def get_relation(self, relation_id: str) -> dict[str, object]:
        return self._ledger_service.get_relation_detail(relation_id)

    def get_relation_extra(self, relation_id: str) -> dict[str, object]:
        self._ledger_service.get_relation_detail(relation_id)
        extra = self._extra_service.get(relation_id)
        if extra is None:
            extra = InMemoryTurnoverLedgerExtraService._default_extra(str(relation_id or "").strip())
        return {"extra": extra}

    def update_relation_extra(
        self,
        relation_id: str,
        payload: dict[str, object],
        *,
        actor: str,
    ) -> dict[str, object]:
        self._ledger_service.get_relation_detail(relation_id)
        extra = self._extra_service.upsert(relation_id, payload, actor=actor)
        detail = self._ledger_service.get_relation_detail(relation_id)
        row = dict(detail.get("row") or {})
        row.update(self._row_extra_fields(extra))
        return {"extra": extra, "row": row}

    def confirm_zero_difference_closure(
        self,
        *,
        bank_row_ids: list[str],
        actor: str,
        note: str | None = None,
    ) -> dict[str, object]:
        return self._relation_service.confirm_zero_difference_closure(
            list(bank_row_ids or []),
            actor=actor,
            note=note,
        )

    def extras_snapshot(self) -> dict[str, object]:
        snapshot = getattr(self._extra_service, "snapshot", None)
        if not callable(snapshot):
            return {"version": 1, "extras": []}
        return snapshot()

    def export_preview(self, *, family: str = "all", limit: int = 20) -> dict[str, object]:
        return self._export_service.preview(family=family, limit=limit)

    def export(self, *, family: str = "all", today: date | None = None) -> tuple[str, bytes]:
        return self._export_service.export(family=family, today=today)

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor: str,
        note: str | None = None,
    ) -> dict[str, object]:
        relation = self._relation_service.confirm_relation(
            bank_row_ids,
            actor=actor,
            note=note,
        )
        return {"relation": relation}

    def withdraw_relation(
        self,
        *,
        relation_id: str,
        actor: str,
        note: str | None = None,
    ) -> dict[str, object]:
        relation = self._relation_service.withdraw_relation(
            relation_id,
            actor=actor,
            note=note,
        )
        return {"relation": relation}

    def _flat_payload_to_grouped(self, payload: dict[str, object]) -> dict[str, object]:
        groups_by_key: dict[tuple[str, str], dict[str, object]] = {}
        for row in list(payload.get("rows") or []):
            if not isinstance(row, dict):
                continue
            row_with_extra = dict(row)
            relation_id = str(row_with_extra.get("relation_id") or "")
            if relation_id:
                row_with_extra.update(self._row_extra_fields(self._extra_service.get(relation_id)))
            family = str(row_with_extra.get("family") or "")
            counterparty = str(row_with_extra.get("counterparty_name") or "")
            key = (family, counterparty)
            group = groups_by_key.setdefault(
                key,
                {
                    "group_id": f"counterparty:{family}:{counterparty}",
                    "counterparty_name": counterparty,
                    "family": family,
                    "family_label": row_with_extra.get("family_label") or "",
                    "pending_direction": self._pending_direction(row_with_extra),
                    "pending_direction_label": self._pending_direction_label(row_with_extra),
                    "pending_amount": "0.00",
                    "row_span": 0,
                    "group_tone": row_with_extra.get("row_tone") or "muted",
                    "rows": [],
                    "flow_rows": [],
                    "allocation_lots": [],
                    "lot_rows": [],
                    "_has_breakdown": False,
                    "_pending_repayment_amount": ZERO,
                    "_repaid_amount": ZERO,
                    "_pending_collection_amount": ZERO,
                    "_collected_amount": ZERO,
                    "_closed_amount": ZERO,
                },
            )
            group_rows = list(group.get("rows") or [])
            grouped_row = self._grouped_row_from_flat_row(row_with_extra)
            breakdown_fields = (
                "pending_repayment_amount",
                "repaid_amount",
                "pending_collection_amount",
                "collected_amount",
                "closed_amount",
            )
            has_breakdown = any(row_with_extra.get(field) is not None for field in breakdown_fields)
            if has_breakdown:
                grouped_row.update({field: row_with_extra.get(field) or "0.00" for field in breakdown_fields})
                group["_has_breakdown"] = True
                group["_pending_repayment_amount"] = self._money(group.get("_pending_repayment_amount")) + self._money(
                    row_with_extra.get("pending_repayment_amount")
                )
                group["_repaid_amount"] = self._money(group.get("_repaid_amount")) + self._money(
                    row_with_extra.get("repaid_amount")
                )
                group["_pending_collection_amount"] = self._money(group.get("_pending_collection_amount")) + self._money(
                    row_with_extra.get("pending_collection_amount")
                )
                group["_collected_amount"] = self._money(group.get("_collected_amount")) + self._money(
                    row_with_extra.get("collected_amount")
                )
                group["_closed_amount"] = self._money(group.get("_closed_amount")) + self._money(
                    row_with_extra.get("closed_amount")
                )
            group_rows.append(grouped_row)
            group["rows"] = group_rows
            flow_rows = list(group.get("flow_rows") or [])
            flow_rows.extend(
                dict(item)
                for item in list(row_with_extra.get("flow_rows") or [])
                if isinstance(item, dict)
            )
            group["flow_rows"] = flow_rows
            allocation_lots = list(group.get("allocation_lots") or [])
            allocation_lots.extend(
                dict(item)
                for item in list(row_with_extra.get("allocation_lots") or [])
                if isinstance(item, dict)
            )
            group["allocation_lots"] = allocation_lots
            lot_rows = list(group.get("lot_rows") or [])
            lot_rows.extend(dict(item) for item in list(row_with_extra.get("lot_rows") or []) if isinstance(item, dict))
            group["lot_rows"] = lot_rows
            group["row_span"] = len(group_rows)
            group["pending_amount"] = self._format_money(
                self._money(group.get("pending_amount")) + self._money(row_with_extra.get("balance_amount"))
            )
        groups = list(groups_by_key.values())
        for group in groups:
            has_breakdown = bool(group.pop("_has_breakdown", False))
            pending_repayment = self._money(group.pop("_pending_repayment_amount", ZERO))
            repaid = self._money(group.pop("_repaid_amount", ZERO))
            pending_collection = self._money(group.pop("_pending_collection_amount", ZERO))
            collected = self._money(group.pop("_collected_amount", ZERO))
            closed = self._money(group.pop("_closed_amount", ZERO))
            if has_breakdown:
                group["pending_repayment_amount"] = self._format_money(pending_repayment)
                group["repaid_amount"] = self._format_money(repaid)
                group["pending_collection_amount"] = self._format_money(pending_collection)
                group["collected_amount"] = self._format_money(collected)
                group["closed_amount"] = self._format_money(closed)
                group["pending_amount"] = self._format_money(pending_repayment + pending_collection)
                if pending_repayment > ZERO and pending_collection > ZERO:
                    group["pending_direction"] = "mixed"
                    group["pending_direction_label"] = "混合余额"
                    group["group_tone"] = "warning"
                elif pending_repayment > ZERO:
                    group["pending_direction"] = "repayment"
                    group["pending_direction_label"] = "待还款"
                    group["group_tone"] = "warning"
                elif pending_collection > ZERO:
                    group["pending_direction"] = "collection"
                    group["pending_direction_label"] = "待收款"
                    group["group_tone"] = "success"
                elif closed > ZERO:
                    group["pending_direction"] = "closed"
                    group["pending_direction_label"] = "已闭合"
                    group["group_tone"] = "muted"
        result = {key: value for key, value in dict(payload).items() if key != "rows"}
        result.update({
            "summary": payload.get("summary") or {},
            "family_summaries": list(payload.get("family_summaries") or []),
            "groups": groups,
            "pagination": {
                **dict(payload.get("pagination") or {}),
                "total": len(groups),
            },
            "filters": dict(payload.get("filters") or {}),
        })
        return result

    @classmethod
    def _normalize_grouped_payload(cls, payload: dict[str, object]) -> dict[str, object]:
        normalized_groups: list[dict[str, object]] = []
        for group in list(payload.get("groups") or []):
            if not isinstance(group, dict):
                continue
            normalized_group = dict(group)
            legacy_rows = [row for row in list(group.get("rows") or []) if isinstance(row, dict)]
            explicit_summary = group.get("summary_row")
            summary_row = dict(explicit_summary) if isinstance(explicit_summary, dict) else None
            explicit_lot_rows = [row for row in list(group.get("lot_rows") or []) if isinstance(row, dict)]
            explicit_flow_rows = [row for row in list(group.get("flow_rows") or []) if isinstance(row, dict)]
            explicit_allocation_lots = [
                row for row in list(group.get("allocation_lots") or []) if isinstance(row, dict)
            ]
            if summary_row is None:
                summary_row = cls._summary_row_from_legacy_rows(legacy_rows)
            lot_rows = [cls._normalized_lot_row(row) for row in explicit_lot_rows]
            allocation_lots = [
                cls._normalized_allocation_lot(row) for row in (explicit_allocation_lots or explicit_lot_rows)
            ]
            flow_rows = cls._normalized_flow_rows(explicit_flow_rows)
            summary_row = cls._normalized_summary_row(summary_row)
            normalized_group["summary_row"] = summary_row
            normalized_group["flow_rows"] = flow_rows
            normalized_group["allocation_lots"] = allocation_lots
            normalized_group["lot_rows"] = lot_rows
            normalized_group["row_span"] = 1 + len(flow_rows)
            normalized_group.pop("rows", None)
            normalized_groups.append(normalized_group)
        return {
            **dict(payload),
            "groups": normalized_groups,
        }

    @classmethod
    def _summary_row_from_legacy_rows(cls, rows: list[dict[str, object]]) -> dict[str, object]:
        for row in rows:
            if str(row.get("row_kind") or "").strip().lower() == "summary":
                return dict(row)
        return dict(rows[0]) if rows else {}

    @staticmethod
    def _normalized_summary_row(row: dict[str, object]) -> dict[str, object]:
        normalized = dict(row)
        normalized["row_kind"] = "summary"
        normalized["display_level"] = "group_summary"
        return normalized

    @staticmethod
    def _normalized_lot_row(row: dict[str, object]) -> dict[str, object]:
        normalized = dict(row)
        normalized["row_kind"] = "lot"
        return normalized

    @classmethod
    def _normalized_flow_rows(cls, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        normalized_rows: list[dict[str, object]] = []
        seen_source_ids: set[str] = set()
        for row in rows:
            normalized = dict(row)
            normalized["row_kind"] = "flow"
            source_bank_row_id = str(normalized.get("source_bank_row_id") or "").strip()
            if source_bank_row_id:
                if source_bank_row_id in seen_source_ids:
                    continue
                seen_source_ids.add(source_bank_row_id)
            normalized_rows.append(normalized)
        return normalized_rows

    @staticmethod
    def _normalized_allocation_lot(row: dict[str, object]) -> dict[str, object]:
        normalized = dict(row)
        normalized["row_kind"] = "allocation_lot"
        return normalized

    @classmethod
    def _grouped_row_from_flat_row(cls, row: dict[str, object]) -> dict[str, object]:
        principal = cls._format_money(cls._money(row.get("principal_amount")))
        settled = cls._format_money(cls._money(row.get("settled_amount")))
        return {
            "relation_id": str(row.get("relation_id") or ""),
            "status": row.get("status") or "",
            "status_label": row.get("status_label") or "",
            "row_tone": row.get("row_tone") or "muted",
            "borrow_amount": row.get("borrow_amount") or principal,
            "borrow_date": cls._date_text(row.get("borrow_date") or row.get("first_transaction_at")),
            "borrow_direction": row.get("borrow_direction") or ("income" if row.get("business_type") == "borrow_in" else "expense"),
            "repayment_amount": row.get("repayment_amount") or settled,
            "repayment_date": cls._date_text(row.get("repayment_date") or row.get("last_settlement_at")) or None,
            "repayment_direction": row.get("repayment_direction") or ("expense" if row.get("business_type") == "borrow_in" else "income"),
            "counterparty_bank_name": row.get("counterparty_bank_name") or cls._join_list(row.get("bank_account_labels")),
            "repayment_remark": row.get("repayment_remark") or row.get("summary_text") or "",
            "interest_rate_type": row.get("interest_rate_type") or "none",
            "interest_rate_value": row.get("interest_rate_value") or "0.000000",
            "interest_paid_amount": row.get("interest_paid_amount") or "0.00",
            "loan_days": row.get("loan_days"),
            "accrued_interest": row.get("accrued_interest") or "0.00",
            "interest_paid_date": row.get("interest_paid_date"),
            "interest_payment_method": row.get("interest_payment_method") or "",
            "note": row.get("note") or "",
            "bank_row_ids": list(row.get("bank_row_ids") or []),
            "family": row.get("family") or "",
            "family_label": row.get("family_label") or "",
            "counterparty_name": row.get("counterparty_name") or "",
            "balance_amount": row.get("balance_amount") or "0.00",
            "principal_amount": principal,
            "settled_amount": settled,
            "business_type": row.get("business_type") or "",
        }

    @staticmethod
    def _row_extra_fields(extra: dict[str, object] | None) -> dict[str, object]:
        extra = extra or {}
        return {
            "interest_rate_type": extra.get("interest_rate_type") or "none",
            "interest_rate_value": extra.get("interest_rate_value") or "0.000000",
            "interest_paid_amount": extra.get("interest_paid_amount") or "0.00",
            "interest_paid_date": extra.get("interest_paid_date"),
            "interest_payment_method": extra.get("interest_payment_method") or "",
            "note": extra.get("note") or "",
        }

    @staticmethod
    def _pending_direction(row: dict[str, object]) -> str:
        business_type = str(row.get("business_type") or "")
        balance = TurnoverLedgerApiRoutes._money(row.get("balance_amount"))
        if balance == ZERO:
            return "closed"
        if business_type == "borrow_in":
            return "repayment"
        if business_type in {"borrow_out", "business_receivable"}:
            return "collection"
        return "mixed"

    @staticmethod
    def _pending_direction_label(row: dict[str, object]) -> str:
        return {
            "repayment": "待还款",
            "collection": "待收款",
            "closed": "已闭合",
            "mixed": "混合余额",
        }[TurnoverLedgerApiRoutes._pending_direction(row)]

    @staticmethod
    def _join_list(value: object) -> str:
        if not isinstance(value, list):
            return ""
        return " / ".join(str(item) for item in value if str(item).strip())

    @staticmethod
    def _date_text(value: object) -> str:
        text = str(value or "").strip()
        return text[:10] if text else ""

    @staticmethod
    def _money(value: object) -> Decimal:
        if value is None:
            return ZERO
        text = str(value).replace(",", "").strip()
        if not text:
            return ZERO
        try:
            return Decimal(text).quantize(MONEY_QUANT)
        except (InvalidOperation, ValueError):
            return ZERO

    @staticmethod
    def _format_money(value: Decimal) -> str:
        return f"{value.quantize(MONEY_QUANT):.2f}"
