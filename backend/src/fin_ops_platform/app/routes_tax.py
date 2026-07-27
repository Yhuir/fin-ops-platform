from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from time import monotonic
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.tax_offset_service import TaxOffsetService
from fin_ops_platform.services.tax_offset_plan_service import TaxOffsetPlanConflictError
from fin_ops_platform.services.tax_certified_import_service import UploadedCertifiedImportFile


SessionResolver = Callable[[dict[str, str] | None], tuple[Any | None, Any | None]]
JsonBodyLoader = Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]]
MultipartBodyLoader = Callable[[str | bytes | None, dict[str, str] | None], tuple[dict[str, list[str]], list[Any], Any | None]]
ActorIdProvider = Callable[[Any | None, dict[str, Any], str], str]
CertifiedImportRecordsProvider = Callable[[str], dict[str, Any]]
CertifiedImportPreviewProvider = Callable[..., dict[str, object]]
ImportJobEnabled = Callable[[], bool]
ImportJobEnqueuer = Callable[..., tuple[Any, Any]]
ImportJobSerializer = Callable[[Any], dict[str, object]]
TaxCertifiedImportConfirmExecutor = Callable[[str], dict[str, object]]


class TaxApiRoutes:
    def __init__(
        self,
        tax_offset_service: TaxOffsetService | None,
        *,
        query_service: Any | None = None,
        certified_import_job_service: Any | None = None,
        plan_service: Any | None = None,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any] | None = None,
        resolve_read_session: SessionResolver | None = None,
        resolve_mutation_session: SessionResolver | None = None,
        load_json_body: JsonBodyLoader | None = None,
        load_multipart_body: MultipartBodyLoader | None = None,
        actor_id_provider: ActorIdProvider | None = None,
        certified_import_records_provider: CertifiedImportRecordsProvider | None = None,
        certified_import_preview_provider: CertifiedImportPreviewProvider | None = None,
        import_job_processing_enabled: ImportJobEnabled | None = None,
        enqueue_import_job: ImportJobEnqueuer | None = None,
        serialize_import_job: ImportJobSerializer | None = None,
        execute_tax_certified_import_confirm: TaxCertifiedImportConfirmExecutor | None = None,
        month_metric_emitter: Callable[..., None] | None = None,
        calculate_metric_emitter: Callable[..., None] | None = None,
        duration_ms: Callable[[float], float] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._tax_offset_service = tax_offset_service
        self._query_service = query_service
        self._certified_import_job_service = certified_import_job_service
        self._plan_service = plan_service
        self._json_response = json_response
        self._resolve_read_session = resolve_read_session
        self._resolve_mutation_session = resolve_mutation_session
        self._load_json_body = load_json_body
        self._load_multipart_body = load_multipart_body
        self._actor_id_provider = actor_id_provider
        self._certified_import_records_provider = certified_import_records_provider
        self._certified_import_preview_provider = certified_import_preview_provider
        self._import_job_processing_enabled = import_job_processing_enabled
        self._enqueue_import_job = enqueue_import_job
        self._serialize_import_job = serialize_import_job
        self._execute_tax_certified_import_confirm = execute_tax_certified_import_confirm
        self._month_metric_emitter = month_metric_emitter
        self._calculate_metric_emitter = calculate_metric_emitter
        self._duration_ms = duration_ms or (lambda started_at: (monotonic() - started_at) * 1000)
        self._now_provider = now_provider or datetime.now

    def configure_platform_ports(
        self,
        *,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        resolve_read_session: SessionResolver,
        resolve_mutation_session: SessionResolver,
        load_json_body: JsonBodyLoader,
        load_multipart_body: MultipartBodyLoader,
        actor_id_provider: ActorIdProvider,
        certified_import_records_provider: CertifiedImportRecordsProvider,
        certified_import_preview_provider: CertifiedImportPreviewProvider,
        import_job_processing_enabled: ImportJobEnabled,
        enqueue_import_job: ImportJobEnqueuer,
        serialize_import_job: ImportJobSerializer,
        execute_tax_certified_import_confirm: TaxCertifiedImportConfirmExecutor,
    ) -> "TaxApiRoutes":
        self._json_response = json_response
        self._resolve_read_session = resolve_read_session
        self._resolve_mutation_session = resolve_mutation_session
        self._load_json_body = load_json_body
        self._load_multipart_body = load_multipart_body
        self._actor_id_provider = actor_id_provider
        self._certified_import_records_provider = certified_import_records_provider
        self._certified_import_preview_provider = certified_import_preview_provider
        self._import_job_processing_enabled = import_job_processing_enabled
        self._enqueue_import_job = enqueue_import_job
        self._serialize_import_job = serialize_import_job
        self._execute_tax_certified_import_confirm = execute_tax_certified_import_confirm
        return self

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any | None:
        if method == "GET" and route_path == "/api/tax-offset":
            return self._read(headers, lambda _session: self.handle_month(query.get("month", [None])[0]))
        if method == "GET" and route_path == "/api/tax-offset/summary":
            return self._read(headers, lambda _session: self.handle_summary(query.get("month", [None])[0]))
        if method == "GET" and route_path.startswith("/api/tax-offset/certified-import/jobs/"):
            import_job_id = unquote(route_path.removeprefix("/api/tax-offset/certified-import/jobs/")).strip()
            return self._read(headers, lambda _session: self.handle_import_job(import_job_id))
        if method == "GET" and route_path == "/api/tax-offset/certified-imports":
            return self._read(headers, lambda _session: self.handle_certified_imports(query.get("month", [None])[0]))
        if method == "POST" and route_path == "/api/tax-offset/calculate":
            return self._json_body_read(body, headers, self.handle_calculate)
        if method == "POST" and route_path == "/api/tax-offset/plans":
            return self._json_body_mutation(body, headers, self.handle_save_plan, actor_fallback="tax_offset_api")
        if method == "POST" and route_path == "/api/tax-offset/certified-import/preview":
            return self._certified_import_preview(body, headers)
        if method == "POST" and route_path == "/api/tax-offset/certified-import/confirm":
            return self._certified_import_confirm(body, headers)
        return None

    def get_tax_offset(self, month: str) -> dict[str, object]:
        return self._tax_offset_service.get_month_payload(month)

    def calculate(self, payload: dict[str, object]) -> dict[str, object]:
        return self._tax_offset_service.calculate(
            month=str(payload["month"]),
            selected_output_ids=list(payload["selected_output_ids"]),
            selected_input_ids=list(payload["selected_input_ids"]),
        )

    def calculate_from_month_payload(
        self,
        payload: dict[str, object],
        *,
        month_payload: dict[str, object],
    ) -> dict[str, object]:
        return self._tax_offset_service.calculate_from_month_payload(
            month=str(payload["month"]),
            month_payload=month_payload,
            selected_output_ids=list(payload["selected_output_ids"]),
            selected_input_ids=list(payload["selected_input_ids"]),
        )

    def handle_month(self, month: str | None) -> Any:
        current_month = month or self._now_provider().strftime("%Y-%m")
        started_at = monotonic()
        try:
            payload = self._require_query_service().get_month_payload(current_month)
        except ValueError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_request", "message": str(exc)},
            )
        if self._month_metric_emitter is not None:
            self._month_metric_emitter(
                month=current_month,
                duration_ms=self._duration_ms(started_at),
                payload=payload,
            )
        return self._respond(HTTPStatus.OK, payload)

    def handle_summary(self, month: str | None) -> Any:
        current_month = month or self._now_provider().strftime("%Y-%m")
        try:
            payload = self._require_query_service().get_summary_payload(current_month)
        except ValueError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_request", "message": str(exc)},
            )
        return self._respond(HTTPStatus.OK, payload)

    def handle_calculate(self, payload: dict[str, object]) -> Any:
        started_at = monotonic()
        try:
            result, status_code = self._require_query_service().calculate(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_calculate_request", "message": str(exc)},
            )
        if self._calculate_metric_emitter is not None:
            self._calculate_metric_emitter(
                month=str(payload.get("month") or ""),
                selected_output_count=_safe_list_count(payload.get("selected_output_ids")),
                selected_input_count=_safe_list_count(payload.get("selected_input_ids")),
                duration_ms=self._duration_ms(started_at),
            )
        return self._respond(HTTPStatus(status_code), result)

    def handle_save_plan(self, *, actor_id: str, payload: dict[str, object]) -> Any:
        try:
            result = self._require_plan_service().save_plan(actor_id=actor_id, payload=payload)
        except TaxOffsetPlanConflictError as exc:
            return self._respond(HTTPStatus.CONFLICT, exc.payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_plan_request", "message": str(exc)},
            )
        return self._respond(HTTPStatus.OK, result)

    def handle_import_job(self, import_job_id: str) -> Any:
        try:
            import_job = self._require_import_job_service().get_confirm_job_payload(import_job_id)
        except ValueError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_tax_certified_import_job_request",
                    "message": str(exc),
                },
            )
        except RuntimeError as exc:
            return self._respond(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "import_job_repository_unavailable", "message": str(exc)},
            )
        except KeyError:
            return self._respond(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "tax_certified_import_job_not_found",
                    "import_job_id": str(import_job_id or "").strip(),
                },
            )
        return self._respond(HTTPStatus.OK, {"import_job": import_job})

    def handle_certified_imports(self, month: str | None) -> Any:
        if month is None or not month.strip():
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_tax_certified_import_request",
                    "message": "month is required.",
                },
            )
        if self._certified_import_records_provider is None:
            raise RuntimeError("Tax certified import records provider is not configured.")
        return self._respond(HTTPStatus.OK, self._certified_import_records_provider(month.strip()))

    def handle_certified_import_preview(
        self,
        *,
        imported_by: str,
        uploads: list[UploadedCertifiedImportFile],
    ) -> Any:
        if self._certified_import_preview_provider is None:
            raise RuntimeError("Tax certified import preview provider is not configured.")
        return self._respond(
            HTTPStatus.OK,
            self._certified_import_preview_provider(imported_by=imported_by, uploads=uploads),
        )

    def handle_certified_import_confirm(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> Any:
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_tax_certified_import_confirm_request",
                    "message": "session_id is required.",
                },
            )
        if self._import_job_enabled():
            try:
                import_job, event = self._enqueue_import_job(
                    import_type="tax_certified_import.confirm",
                    import_session_id=session_id,
                    idempotency_key=f"tax_certified_import.confirm:{session_id}",
                    payload={"session_id": session_id},
                    created_by=actor_id,
                    reason="tax_certified_import_confirm",
                )
            except RuntimeError as exc:
                return self._respond(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "import_queue_unavailable", "message": str(exc)},
                )
            return self._respond(
                HTTPStatus.ACCEPTED,
                {
                    "status": "queued",
                    "import_job": self._serialize_job(import_job),
                    "event_id": getattr(event, "event_id", None),
                },
            )
        try:
            result = self._execute_confirm(session_id)
        except KeyError as exc:
            return self._respond(
                HTTPStatus.NOT_FOUND,
                {"error": "tax_certified_import_session_not_found", "message": str(exc)},
            )
        return self._respond(
            HTTPStatus.OK,
            {
                **result,
                **self._tax_certified_import_write_targets(result),
            },
        )

    def _require_query_service(self) -> Any:
        if self._query_service is None:
            raise RuntimeError("Tax offset query service is not configured.")
        return self._query_service

    def _require_import_job_service(self) -> Any:
        if self._certified_import_job_service is None:
            raise RuntimeError("Tax certified import job service is not configured.")
        return self._certified_import_job_service

    def _require_plan_service(self) -> Any:
        if self._plan_service is None:
            raise RuntimeError("Tax offset plan service is not configured.")
        return self._plan_service

    def _respond(self, status: HTTPStatus, payload: dict[str, Any]) -> Any:
        if self._json_response is None:
            return status, payload
        return self._json_response(status, payload)

    def _read(self, headers: dict[str, str] | None, action: Callable[[Any | None], Any]) -> Any:
        session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        return action(session)

    def _json_body_read(self, body: str | bytes | None, headers: dict[str, str] | None, action: Callable[[dict[str, Any]], Any]) -> Any:
        _session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        payload, error = self._json_body(body)
        if error is not None:
            return error
        return action(payload)

    def _json_body_mutation(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        action: Callable[..., Any],
        *,
        actor_fallback: str,
    ) -> Any:
        session, auth_error = self._mutation_session(headers)
        if auth_error is not None:
            return auth_error
        payload, error = self._json_body(body)
        if error is not None:
            return error
        actor_id = self._actor_id(session, payload, actor_fallback)
        return action(actor_id=actor_id, payload=payload)

    def _certified_import_preview(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._mutation_session(headers)
        if auth_error is not None:
            return auth_error
        if self._load_multipart_body is None:
            raise RuntimeError("Tax multipart body loader is not configured.")
        fields, files, error = self._load_multipart_body(body, headers)
        if error is not None:
            return error
        imported_by = (
            self._actor_id(session, {}, "system")
            if session is not None
            else (fields.get("imported_by") or ["system"])[0]
        )
        if not files:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_tax_certified_import_request",
                    "message": "至少上传一个已认证发票文件。",
                },
            )
        uploads = [
            UploadedCertifiedImportFile(file_name=file.file_name, content=file.content)
            for file in files
        ]
        return self.handle_certified_import_preview(imported_by=imported_by, uploads=uploads)

    def _certified_import_confirm(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._mutation_session(headers)
        if auth_error is not None:
            return auth_error
        payload, error = self._json_body(body)
        if error is not None:
            return error
        actor_id = self._actor_id(session, payload, "tax_certified_api")
        return self.handle_certified_import_confirm(payload, actor_id=actor_id)

    def _read_session(self, headers: dict[str, str] | None) -> tuple[Any | None, Any | None]:
        if self._resolve_read_session is None:
            return None, None
        return self._resolve_read_session(headers)

    def _mutation_session(self, headers: dict[str, str] | None) -> tuple[Any | None, Any | None]:
        if self._resolve_mutation_session is None:
            return None, None
        return self._resolve_mutation_session(headers)

    def _json_body(self, body: str | bytes | None) -> tuple[dict[str, Any], Any | None]:
        if self._load_json_body is None:
            raise RuntimeError("Tax JSON body loader is not configured.")
        return self._load_json_body(body)

    def _actor_id(self, session: Any | None, payload: dict[str, Any], fallback: str) -> str:
        if self._actor_id_provider is not None:
            return self._actor_id_provider(session, payload, fallback)
        return fallback

    def _import_job_enabled(self) -> bool:
        return bool(self._import_job_processing_enabled and self._import_job_processing_enabled())

    def _serialize_job(self, import_job: Any) -> dict[str, object]:
        if self._serialize_import_job is None:
            raise RuntimeError("Tax import job serializer is not configured.")
        return self._serialize_import_job(import_job)

    def _execute_confirm(self, session_id: str) -> dict[str, object]:
        if self._execute_tax_certified_import_confirm is None:
            raise RuntimeError("Tax certified import confirm executor is not configured.")
        return self._execute_tax_certified_import_confirm(session_id)

    @staticmethod
    def _tax_certified_import_write_targets(result: dict[str, object]) -> dict[str, object]:
        batch = result.get("batch") if isinstance(result.get("batch"), dict) else {}
        return {"affected_scope_keys": list(batch.get("months") or []) or ["all"]}


def _safe_list_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0
