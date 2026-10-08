from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.import_job_queue import ImportJobIdempotencyConflict
from fin_ops_platform.services.tax_certified_import_service import UploadedCertifiedImportFile

SessionResolver = Callable[[dict[str, str] | None], tuple[Any | None, Any | None]]
JsonBodyLoader = Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]]
MultipartBodyLoader = Callable[[str | bytes | None, dict[str, str] | None], tuple[dict[str, list[str]], list[Any], Any | None]]
CertifiedImportRecordsProvider = Callable[..., dict[str, Any]]
CertifiedImportPreviewProvider = Callable[..., dict[str, object]]
ImportJobEnqueuer = Callable[..., Any]
ImportJobSerializer = Callable[[Any], dict[str, object]]


class TaxApiRoutes:
    def __init__(
        self,
        *,
        query_service: Any | None = None,
        certified_import_job_service: Any | None = None,
        revoke_batch_provider: Callable[..., dict[str, Any]] | None = None,
        export_service: Any | None = None,
        export_response: Callable[[str, bytes], Any] | None = None,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any] | None = None,
        resolve_read_session: SessionResolver | None = None,
        resolve_mutation_session: SessionResolver | None = None,
        load_json_body: JsonBodyLoader | None = None,
        load_multipart_body: MultipartBodyLoader | None = None,
        certified_import_records_provider: CertifiedImportRecordsProvider | None = None,
        certified_import_preview_provider: CertifiedImportPreviewProvider | None = None,
        enqueue_import_job: ImportJobEnqueuer | None = None,
        serialize_import_job: ImportJobSerializer | None = None,
    ) -> None:
        self._query_service = query_service
        self._certified_import_job_service = certified_import_job_service
        self._revoke_batch_provider = revoke_batch_provider
        self._export_service = export_service
        self._export_response = export_response
        self._json_response = json_response
        self._resolve_read_session = resolve_read_session
        self._resolve_mutation_session = resolve_mutation_session
        self._load_json_body = load_json_body
        self._load_multipart_body = load_multipart_body
        self._certified_import_records_provider = certified_import_records_provider
        self._certified_import_preview_provider = certified_import_preview_provider
        self._enqueue_import_job = enqueue_import_job
        self._serialize_import_job = serialize_import_job

    def configure_platform_ports(
        self,
        *,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        resolve_read_session: SessionResolver,
        resolve_mutation_session: SessionResolver,
        load_json_body: JsonBodyLoader,
        load_multipart_body: MultipartBodyLoader,
        certified_import_records_provider: CertifiedImportRecordsProvider,
        certified_import_preview_provider: CertifiedImportPreviewProvider,
        enqueue_import_job: ImportJobEnqueuer,
        serialize_import_job: ImportJobSerializer,
    ) -> "TaxApiRoutes":
        self._json_response = json_response
        self._resolve_read_session = resolve_read_session
        self._resolve_mutation_session = resolve_mutation_session
        self._load_json_body = load_json_body
        self._load_multipart_body = load_multipart_body
        self._certified_import_records_provider = certified_import_records_provider
        self._certified_import_preview_provider = certified_import_preview_provider
        self._enqueue_import_job = enqueue_import_job
        self._serialize_import_job = serialize_import_job
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
            return self._read(headers, lambda _session: self.handle_list(query))
        if method == "GET" and route_path.startswith("/api/tax-offset/certified-import/jobs/"):
            import_job_id = unquote(route_path.removeprefix("/api/tax-offset/certified-import/jobs/")).strip()
            return self._read(headers, lambda session: self.handle_import_job(
                import_job_id, owner_user_id=self._import_owner(session)))
        if method == "GET" and route_path == "/api/tax-offset/certified-imports":
            return self._read(headers, lambda _session: self.handle_certified_imports(
                query.get("month", [None])[0], records_page=query.get("records_page", ["1"])[0],
                batches_page=query.get("batches_page", ["1"])[0], page_size=query.get("page_size", ["20"])[0]))
        if method == "POST" and route_path.startswith("/api/tax-offset/certified-imports/") and route_path.endswith("/revoke"):
            batch_id = unquote(route_path[len("/api/tax-offset/certified-imports/"):-len("/revoke")]).strip()
            return self._revoke_batch(batch_id, body, headers)
        if method == "POST" and route_path == "/api/tax-offset/export":
            return self._json_body_read(body, headers, self.handle_export)
        if method == "POST" and route_path == "/api/tax-offset/certified-import/preview":
            return self._certified_import_preview(body, headers)
        if method == "POST" and route_path == "/api/tax-offset/certified-import/confirm":
            return self._certified_import_confirm(body, headers)
        return None

    def handle_list(self, query: dict[str, list[str]]) -> Any:
        try:
            if any(len(values) != 1 for values in query.values()):
                raise ValueError("查询参数不能重复。")
            payload = self._require_query_service().list_payload({key: values[0] for key, values in query.items()})
        except ValueError as exc:
            return self._respond(HTTPStatus.BAD_REQUEST, {"error": "invalid_tax_certification_query", "message": str(exc)})
        except RuntimeError as exc:
            return self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "tax_certification_unavailable", "message": str(exc)})
        return self._respond(HTTPStatus.OK, payload)

    def handle_export(self, payload: dict[str, Any]) -> Any:
        try:
            if self._export_service is None or self._export_response is None:
                raise RuntimeError("Tax certification export is not configured.")
            if set(payload) - {"filters", "fields"}:
                raise ValueError("导出请求包含未知字段。")
            filters = payload.get("filters", {})
            fields = payload.get("fields")
            if not isinstance(filters, dict):
                raise ValueError("filters 必须为对象。")
            if fields is not None and (not isinstance(fields, list) or any(not isinstance(field, str) for field in fields)):
                raise ValueError("fields 必须为字段名称数组。")
            filename, content = self._export_service.export(filters, fields)
        except ValueError as exc:
            return self._respond(HTTPStatus.BAD_REQUEST, {"error": "invalid_tax_certification_export", "message": str(exc)})
        except RuntimeError as exc:
            return self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "tax_certification_unavailable", "message": str(exc)})
        return self._export_response(filename, content)

    def handle_import_job(self, import_job_id: str, *, owner_user_id: str) -> Any:
        try:
            import_job = self._require_import_job_service().get_confirm_job_payload(import_job_id, owner_user_id=owner_user_id)
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

    def handle_certified_imports(self, month: str | None, *, records_page: str = "1", batches_page: str = "1", page_size: str = "20") -> Any:
        try:
            if self._certified_import_records_provider is None:
                raise RuntimeError("Tax certified import records provider is not configured.")
            if any(not str(value).isdecimal() or int(value) < 1 for value in (records_page, batches_page, page_size)) or int(page_size) > 100:
                raise ValueError("分页参数无效。")
            result = self._certified_import_records_provider(month, records_page=int(records_page), batches_page=int(batches_page), page_size=int(page_size))
        except ValueError as exc:
            return self._respond(HTTPStatus.BAD_REQUEST, {"error": "invalid_tax_certified_import_request", "message": str(exc)})
        except RuntimeError as exc:
            return self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "tax_certification_unavailable", "message": str(exc)})
        return self._respond(HTTPStatus.OK, result)

    def handle_certified_import_preview(
        self,
        *,
        imported_by: str,
        uploads: list[UploadedCertifiedImportFile],
        month: str | None = None,
        buyer_tax_no: str | None = None,
    ) -> Any:
        try:
            if self._certified_import_preview_provider is None:
                raise RuntimeError("Tax certified import preview provider is not configured.")
            result = self._certified_import_preview_provider(imported_by=imported_by, uploads=uploads, month=month, buyer_tax_no=buyer_tax_no)
        except ValueError as exc:
            return self._respond(HTTPStatus.BAD_REQUEST, {"error": "invalid_tax_certified_import_file", "message": str(exc)})
        except RuntimeError as exc:
            return self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "tax_certification_unavailable", "message": str(exc)})
        return self._respond(HTTPStatus.OK, result)

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
        corrections = payload.get("corrections", [])
        if not isinstance(corrections, list) or any(
            not isinstance(item, dict) or set(item) != {"unique_key", "expected_version"}
            or not isinstance(item["unique_key"], str) or not item["unique_key"].strip()
            or type(item["expected_version"]) is not int or item["expected_version"] < 1
            for item in corrections
        ):
            return self._respond(HTTPStatus.BAD_REQUEST, {"error": "invalid_tax_certified_corrections", "message": "更正记录及版本无效。"})
        if len({item["unique_key"] for item in corrections}) != len(corrections):
            return self._respond(HTTPStatus.BAD_REQUEST, {"error": "invalid_tax_certified_corrections", "message": "更正记录不能重复。"})
        if self._enqueue_import_job is None:
            return self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "import_queue_unavailable", "message": "Import queue is not configured."})
        try:
            self._require_import_job_service().validate_session_owner(session_id, owner_user_id=actor_id)
            import_job = self._enqueue_import_job(
                import_type="tax_certified_import.confirm",
                import_session_id=session_id,
                idempotency_key=f"tax_certified_import.confirm:{session_id}",
                payload={"session_id": session_id, "corrections": corrections},
                created_by=actor_id,
                reason="tax_certified_import_confirm",
            )
        except KeyError:
            return self._respond(HTTPStatus.NOT_FOUND, {"error": "tax_certified_import_session_not_found"})
        except ImportJobIdempotencyConflict:
            return self._respond(HTTPStatus.CONFLICT, {"error": "tax_certified_import_confirmation_conflict", "message": "该预览已提交，请重新识别文件。"})
        except RuntimeError as exc:
            return self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "import_queue_unavailable", "message": str(exc)})
        return self._respond(HTTPStatus.ACCEPTED, {
            "status": "queued", "import_job": self._serialize_job(import_job),
        })

    def _require_query_service(self) -> Any:
        if self._query_service is None:
            raise RuntimeError("Tax offset query service is not configured.")
        return self._query_service

    def _require_import_job_service(self) -> Any:
        if self._certified_import_job_service is None:
            raise RuntimeError("Tax certified import job service is not configured.")
        return self._certified_import_job_service

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
            self._import_owner(session)
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
        return self.handle_certified_import_preview(
            imported_by=imported_by, uploads=uploads,
            month=(fields.get("month") or [None])[0],
            buyer_tax_no=(fields.get("buyer_tax_no") or [None])[0],
        )

    def _certified_import_confirm(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._mutation_session(headers)
        if auth_error is not None:
            return auth_error
        payload, error = self._json_body(body)
        if error is not None:
            return error
        actor_id = self._import_owner(session)
        return self.handle_certified_import_confirm(payload, actor_id=actor_id)

    def _revoke_batch(self, batch_id: str, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._mutation_session(headers)
        if auth_error is not None:
            return auth_error
        payload, error = self._json_body(body)
        if error is not None:
            return error
        version = payload.get("expected_version")
        if not batch_id or type(version) is not int or version < 1:
            return self._respond(HTTPStatus.BAD_REQUEST, {"error": "invalid_tax_certified_revoke", "message": "批次及版本无效。"})
        try:
            if self._revoke_batch_provider is None:
                raise RuntimeError("Tax certified batch revocation is not configured.")
            result = self._revoke_batch_provider(batch_id=batch_id, actor_id=self._import_owner(session), expected_version=version)
        except KeyError:
            return self._respond(HTTPStatus.NOT_FOUND, {"error": "tax_certified_batch_not_found"})
        except PermissionError as exc:
            return self._respond(HTTPStatus.FORBIDDEN, {"error": "tax_certified_batch_forbidden", "message": str(exc)})
        except ValueError as exc:
            return self._respond(HTTPStatus.CONFLICT, {"error": "tax_certified_batch_conflict", "message": str(exc)})
        except RuntimeError as exc:
            return self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "tax_certification_unavailable", "message": str(exc)})
        return self._respond(HTTPStatus.OK, result)

    @staticmethod
    def _import_owner(session: Any | None) -> str:
        return str(session.identity.username) if session is not None else "tax_certified_api"

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

    def _serialize_job(self, import_job: Any) -> dict[str, object]:
        if self._serialize_import_job is None:
            raise RuntimeError("Tax import job serializer is not configured.")
        return self._serialize_import_job(import_job)
