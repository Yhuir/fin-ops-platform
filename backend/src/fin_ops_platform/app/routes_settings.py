from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote
from uuid import UUID, uuid4

from pymongo.errors import PyMongoError

from fin_ops_platform.app.auth import OARequestSession, actor_id_for_session
from fin_ops_platform.services.app_settings_service import (
    AccessControlSyncInconsistentError,
    AppSettingsPersistenceError,
    AppSettingsService,
    AppSettingsValidationError,
)
from fin_ops_platform.services.background_job_service import BackgroundJobAccessError, BackgroundJobNotFoundError
from fin_ops_platform.services.oa_applicant_credentials import (
    OaApplicantCredentialConfigurationError,
    OaApplicantCredentialError,
    OaApplicantCredentialPermissionError,
    OaApplicantCredentialService,
    OaApplicantCredentialValidationError,
)
from fin_ops_platform.services.oa_attachment_refresh_request_service import (
    OAAttachmentRefreshEventNotFoundError,
    OAAttachmentRefreshRequestError,
    OAAttachmentRefreshRowNotCompletedError,
    OAAttachmentRefreshRowNotFoundError,
)
from fin_ops_platform.services.oa_draft_prefill import (
    ETC_OA_DRAFT_PREFILL_FAMILY,
    INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY,
)
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncError
from fin_ops_platform.services.postgres_repositories.settings_data_reset_request import (
    SettingsDataResetAlreadyActive,
    SettingsDataResetIdempotencyConflict,
    SettingsDataResetRecoveryUnavailable,
)
from fin_ops_platform.services.settings_data_reset_request import SettingsDataResetEnqueueError
from fin_ops_platform.services.settings_data_reset_service import (
    RESET_BANK_TRANSACTIONS_ACTION,
    RESET_INVOICES_ACTION,
    RESET_OA_AND_REBUILD_ACTION,
    SettingsDataResetService,
)
from fin_ops_platform.services.state_store_protocol import SettingsAccessControlVersionConflict

JsonResponse = Callable[[HTTPStatus, object], Any]
JsonBodyLoader = Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]]
SessionResolver = Callable[[dict[str, str] | None], tuple[OARequestSession | None, Any | None]]
SettingsServiceProvider = Callable[[], AppSettingsService]
SettingsDataResetServiceProvider = Callable[[], SettingsDataResetService | None]
ServiceProvider = Callable[[], Any]
FinalizeSettingsEvent = Callable[[dict[str, Any]], None]
DataResetRequester = Callable[..., tuple[Any, bool]]


class SettingsApiRoutes:
    """HTTP I/O owner for /api/workbench/settings* routes."""

    def __init__(
        self,
        *,
        app_settings_service_provider: SettingsServiceProvider,
        project_costing_service_provider: ServiceProvider,
        settings_data_reset_service_provider: SettingsDataResetServiceProvider,
        background_job_service_provider: ServiceProvider,
        oa_applicant_credential_service_provider: Callable[[], OaApplicantCredentialService],
        oa_manual_import_service_provider: ServiceProvider,
        oa_attachment_refresh_request_service_provider: ServiceProvider,
        resolve_read_session: SessionResolver,
        resolve_admin_session: SessionResolver,
        verify_reset_oa_password: Callable[[OARequestSession | None, str], Any | None],
        oa_password_verification_failed_response: Callable[[], Any],
        load_json_body: JsonBodyLoader,
        json_response: JsonResponse,
        finalize_settings_event: FinalizeSettingsEvent,
        request_data_reset: DataResetRequester,
        serialize_sync_run: Callable[[object], dict[str, object]],
        serialize_data_reset_background_job: Callable[[Any], dict[str, object]],
        import_job_processing_enabled: Callable[[], bool],
        enqueue_import_process_job: Callable[..., tuple[Any, Any]],
        serialize_import_job: Callable[[Any], dict[str, object]],
        manual_import_affected_scope_keys: Callable[[dict[str, object], list[str]], list[str]],
        manual_import_affected_scope_payload: Callable[[list[str]], dict[str, object]],
    ) -> None:
        self._app_settings_service_provider = app_settings_service_provider
        self._project_costing_service_provider = project_costing_service_provider
        self._settings_data_reset_service_provider = settings_data_reset_service_provider
        self._background_job_service_provider = background_job_service_provider
        self._oa_applicant_credential_service_provider = oa_applicant_credential_service_provider
        self._oa_manual_import_service_provider = oa_manual_import_service_provider
        self._oa_attachment_refresh_request_service_provider = (
            oa_attachment_refresh_request_service_provider
        )
        self._resolve_read_session = resolve_read_session
        self._resolve_admin_session = resolve_admin_session
        self._verify_reset_oa_password = verify_reset_oa_password
        self._oa_password_verification_failed_response = oa_password_verification_failed_response
        self._load_json_body = load_json_body
        self._json_response = json_response
        self._finalize_settings_event = finalize_settings_event
        self._request_data_reset = request_data_reset
        self._serialize_sync_run = serialize_sync_run
        self._serialize_data_reset_background_job = serialize_data_reset_background_job
        self._import_job_processing_enabled = import_job_processing_enabled
        self._enqueue_import_process_job = enqueue_import_process_job
        self._serialize_import_job = serialize_import_job
        self._manual_import_affected_scope_keys = manual_import_affected_scope_keys
        self._manual_import_affected_scope_payload = manual_import_affected_scope_payload

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        request_id: str | None = None,
    ) -> Any | None:
        if method == "GET" and route_path == "/api/workbench/settings":
            return self.settings()
        if method == "POST" and route_path == "/api/workbench/settings":
            return self.update_settings(body, headers)
        if method == "GET" and route_path == "/api/workbench/settings/access-control":
            return self.access_control(headers)
        if method == "PUT" and route_path == "/api/workbench/settings/access-control":
            return self.update_access_control(body, headers, request_id=request_id or uuid4().hex)
        if route_path.startswith("/api/workbench/settings/oa-draft-prefill/"):
            family_slug = unquote(route_path.rsplit("/", 1)[-1])
            if method == "GET":
                return self.oa_draft_prefill(family_slug, headers)
            if method == "PUT":
                return self.update_oa_draft_prefill(family_slug, body, headers)
        if method == "GET" and route_path == "/api/workbench/settings/oa-applicant-credentials":
            return self.oa_applicant_credentials(headers)
        if route_path.startswith("/api/workbench/settings/oa-applicant-credentials/"):
            target_applicant_code = unquote(route_path.rsplit("/", 1)[-1])
            if method == "PUT":
                return self.save_oa_applicant_credential(target_applicant_code, body, headers)
            if method == "DELETE":
                return self.delete_oa_applicant_credential(target_applicant_code, headers)
        if method == "GET" and route_path == "/api/workbench/settings/oa/manual-search":
            return self.oa_manual_search(query)
        if method == "POST" and route_path == "/api/workbench/settings/oa/manual-search/refresh-attachments":
            return self.oa_manual_search_refresh_attachments(body, headers)
        if method == "GET" and route_path.startswith(
            "/api/workbench/settings/oa/manual-search/refresh-attachments/"
        ):
            event_id = unquote(route_path.rsplit("/", 1)[-1])
            return self.oa_manual_search_refresh_status(event_id, headers)
        if method == "GET" and route_path == "/api/workbench/settings/oa/manual-imports":
            return self.oa_manual_imports()
        if method == "POST" and route_path == "/api/workbench/settings/oa/manual-imports":
            return self.create_oa_manual_imports(body, headers)
        if method == "DELETE" and route_path.startswith("/api/workbench/settings/oa/manual-imports/"):
            row_id = unquote(route_path.rsplit("/", 1)[-1])
            return self.delete_oa_manual_import(row_id, body, headers)
        if method == "POST" and route_path == "/api/workbench/settings/projects/sync":
            return self.sync_projects(body, headers)
        if method == "POST" and route_path == "/api/workbench/settings/projects":
            return self.create_project(body, headers)
        if method == "DELETE" and route_path.startswith("/api/workbench/settings/projects/"):
            project_id = unquote(route_path.rsplit("/", 1)[-1])
            return self.delete_project(project_id, headers)
        if method == "GET" and route_path == "/api/workbench/settings/data-reset/preview":
            return self.data_reset_preview(query, headers)
        if method == "POST" and route_path == "/api/workbench/settings/data-reset/jobs":
            return self.create_data_reset_job(body, headers, request_id=request_id or uuid4().hex)
        if method == "GET" and route_path == "/api/workbench/settings/data-reset/jobs/active":
            return self.active_data_reset_job(headers)
        if method == "GET" and route_path.startswith("/api/workbench/settings/data-reset/jobs/"):
            job_id = unquote(route_path.rsplit("/", 1)[-1])
            return self.data_reset_job(job_id, headers)
        return None

    def settings(self) -> Any:
        return self._json_response(HTTPStatus.OK, self._app_settings_service().get_settings_payload())

    def update_settings(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session, auth_error = self._resolve_settings_mutation_session(
            headers,
            denied_message="当前账户没有保存设置权限。",
        )
        if auth_error is not None:
            return auth_error

        forbidden_acl_keys = {
            "access_control",
            "allowed_usernames",
            "readonly_export_usernames",
            "admin_usernames",
            "full_access_usernames",
            "access_control_version",
        }
        if forbidden_acl_keys.intersection(payload):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "access_control_write_forbidden",
                    "message": "Access control can only be changed through the administrator access-control API.",
                },
            )

        completed_project_ids = payload.get("completed_project_ids", [])
        bank_account_mappings = payload.get("bank_account_mappings", [])
        workbench_column_layouts = payload.get("workbench_column_layouts", {})
        oa_retention = payload.get("oa_retention", {})
        oa_invoice_offset = payload.get("oa_invoice_offset", {})
        oa_import = payload.get("oa_import", {})
        pending_invoice_tag_groups = payload.get("pending_invoice_tag_groups")
        pending_output_invoice_tag_groups = payload.get("pending_output_invoice_tag_groups")
        actor_id = actor_id_for_session(session) if session is not None else "workbench_settings"

        app_settings_service = self._app_settings_service()
        if (
            not isinstance(completed_project_ids, list)
            or not isinstance(bank_account_mappings, list)
            or not isinstance(workbench_column_layouts, dict)
            or not isinstance(oa_retention, dict)
            or not isinstance(oa_import, dict)
            or not isinstance(oa_invoice_offset, dict)
        ):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_settings_request",
                    "message": (
                        "completed_project_ids and bank_account_mappings must be arrays, and "
                        "workbench_column_layouts, oa_retention, oa_import, and oa_invoice_offset must be objects."
                    ),
                },
            )
        if "bank_transaction_tags" in payload:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "bank_transaction_tags_write_forbidden",
                    "message": "银行明细自动标签规则只能在银行明细的自动标签规则中保存。",
                },
            )
        if pending_invoice_tag_groups is not None and not isinstance(pending_invoice_tag_groups, dict):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_settings_request",
                    "message": "pending_invoice_tag_groups must be an object when provided.",
                },
            )
        if pending_output_invoice_tag_groups is not None and not isinstance(pending_output_invoice_tag_groups, dict):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_settings_request",
                    "message": "pending_output_invoice_tag_groups must be an object when provided.",
                },
            )
        try:
            updated_payload = app_settings_service.update_settings(
                completed_project_ids=[str(item) for item in completed_project_ids],
                bank_account_mappings=[item for item in bank_account_mappings if isinstance(item, dict)],
                workbench_column_layouts=workbench_column_layouts,
                oa_retention=oa_retention,
                oa_import=oa_import,
                oa_invoice_offset=oa_invoice_offset,
                pending_invoice_tag_groups=pending_invoice_tag_groups,
                pending_output_invoice_tag_groups=pending_output_invoice_tag_groups,
                actor_id=actor_id or "workbench_settings",
                after_bank_transaction_tag_settings_saved=self._finalize_settings_event,
            )
        except AppSettingsValidationError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": exc.error_code, "message": str(exc)},
            )
        except PyMongoError as exc:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "app_settings_persistence_failed",
                    "message": f"设置保存失败：无法写入持久化设置源，请检查配置后重试。底层错误：{exc}",
                },
            )
        return self._json_response(HTTPStatus.OK, updated_payload)

    def access_control(self, headers: dict[str, str] | None) -> Any:
        _session, auth_error = self._resolve_admin_session(headers)
        if auth_error is not None:
            return auth_error
        return self._json_response(
            HTTPStatus.OK,
            self._app_settings_service().get_access_control_payload(),
        )

    def oa_draft_prefill(self, family_slug: str, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_read_session(headers)
        if auth_error is not None:
            return auth_error
        family = self._oa_draft_prefill_family(family_slug)
        if family is None:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "oa_draft_prefill_family_not_found", "message": "OA draft prefill family was not found."},
            )
        identity = session.identity if session is not None else None
        return self._json_response(
            HTTPStatus.OK,
            self._app_settings_service().get_oa_draft_prefill_payload(
                family,
                can_save=bool(session and session.can_admin_access),
                applicant_name=str(
                    getattr(identity, "display_name", "")
                    or getattr(identity, "nickname", "")
                    or getattr(identity, "username", "")
                    or ""
                ),
            ),
        )

    def update_oa_draft_prefill(
        self,
        family_slug: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        family = self._oa_draft_prefill_family(family_slug)
        if family is None:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "oa_draft_prefill_family_not_found", "message": "OA draft prefill family was not found."},
            )
        session, auth_error = self._resolve_admin_session(headers)
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        if set(payload) != {"expected_version", "configuration"}:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_oa_draft_prefill_request",
                    "message": "Request must contain only expected_version and configuration.",
                },
            )
        try:
            identity = session.identity if session is not None else None
            result = self._app_settings_service().update_oa_draft_prefill(
                family,
                payload,
                actor_id=actor_id_for_session(session) if session is not None else "system",
                applicant_name=str(
                    getattr(identity, "display_name", "")
                    or getattr(identity, "nickname", "")
                    or getattr(identity, "username", "")
                    or ""
                ),
            )
        except AppSettingsValidationError as exc:
            status = HTTPStatus.CONFLICT if exc.error_code == "oa_draft_prefill_version_conflict" else HTTPStatus.BAD_REQUEST
            return self._json_response(status, {"error": exc.error_code, "message": str(exc)})
        return self._json_response(HTTPStatus.OK, result)

    @staticmethod
    def _oa_draft_prefill_family(family_slug: str) -> str | None:
        return {
            "etc": ETC_OA_DRAFT_PREFILL_FAMILY,
            "input-invoice-usage": INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY,
        }.get(str(family_slug or "").strip())

    def update_access_control(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        request_id: str,
    ) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session, auth_error = self._resolve_admin_session(headers)
        if auth_error is not None:
            return auth_error
        if set(payload) != {"expected_version", "accounts"}:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_access_control_request",
                    "message": "Request must contain only expected_version and accounts.",
                },
            )
        expected_version = payload.get("expected_version")
        accounts = payload.get("accounts")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_access_control_request", "message": "expected_version must be positive."},
            )
        if not isinstance(accounts, list):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_access_control_request", "message": "accounts must be an array."},
            )
        identity = session.identity if session is not None else None
        try:
            updated = self._app_settings_service().update_access_control(
                expected_version=expected_version,
                accounts=accounts,
                actor_id=actor_id_for_session(session) if session is not None else "system",
                actor_name=str(
                    getattr(identity, "display_name", "")
                    or getattr(identity, "username", "")
                    or ""
                ),
                request_id=request_id,
            )
        except AppSettingsValidationError as exc:
            return self._json_response(HTTPStatus.BAD_REQUEST, {"error": exc.error_code, "message": str(exc)})
        except SettingsAccessControlVersionConflict as exc:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "access_control_version_conflict",
                    "message": str(exc),
                    "current_version": exc.current_version,
                },
            )
        except OARoleSyncError as exc:
            return self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {"error": "oa_role_sync_failed", "message": f"OA 角色同步失败：{exc}"},
            )
        except AccessControlSyncInconsistentError as exc:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "access_control_sync_inconsistent", "message": str(exc)},
            )
        except AppSettingsPersistenceError as exc:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "access_control_persistence_failed", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, updated)

    def oa_applicant_credentials(self, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_read_session(headers)
        if auth_error is not None:
            return auth_error
        try:
            payload = self._oa_applicant_credential_service().list_credentials(
                can_admin_access=bool(session and session.can_admin_access),
            )
        except OaApplicantCredentialError as exc:
            return self._oa_applicant_credential_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def save_oa_applicant_credential(
        self,
        target_applicant_code: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session, auth_error = self._resolve_read_session(headers)
        if auth_error is not None:
            return auth_error
        actor_id = actor_id_for_session(session) if session is not None else "system"
        try:
            credential = self._oa_applicant_credential_service().save_credential(
                target_applicant_code=target_applicant_code,
                target_applicant_name=str(payload.get("targetApplicantName") or ""),
                oa_username=str(payload.get("oaUsername") or ""),
                password=str(payload.get("password") or ""),
                actor_id=actor_id,
                can_admin_access=bool(session and session.can_admin_access),
            )
        except OaApplicantCredentialError as exc:
            return self._oa_applicant_credential_error_response(exc)
        return self._json_response(HTTPStatus.OK, {"credential": credential})

    def delete_oa_applicant_credential(self, target_applicant_code: str, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_read_session(headers)
        if auth_error is not None:
            return auth_error
        actor_id = actor_id_for_session(session) if session is not None else "system"
        try:
            credential = self._oa_applicant_credential_service().delete_credential(
                target_applicant_code=target_applicant_code,
                actor_id=actor_id,
                can_admin_access=bool(session and session.can_admin_access),
            )
        except OaApplicantCredentialError as exc:
            return self._oa_applicant_credential_error_response(exc)
        return self._json_response(HTTPStatus.OK, {"credential": credential})

    def oa_manual_search(self, query: dict[str, list[str]]) -> Any:
        service = self._oa_manual_import_service_or_response()
        if not self._is_service_available(service):
            return service
        pagination, error = self._parse_oa_manual_search_pagination(query)
        if error is not None:
            return error
        payload = service.search(
            q=query.get("q", [None])[0],
            form_types=self._parse_csv_query_values(query, "form_types"),
            statuses=self._parse_csv_query_values(query, "statuses"),
            date_from=query.get("date_from", [None])[0],
            date_to=query.get("date_to", [None])[0],
            page=pagination["page"],
            page_size=pagination["page_size"],
        )
        return self._json_response(HTTPStatus.OK, payload)

    def oa_manual_search_refresh_attachments(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_settings_mutation_session(headers)
        if auth_error is not None:
            return auth_error
        service = self._oa_attachment_refresh_request_service_or_response()
        if not self._is_service_available(service):
            return service
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        row_ids, row_ids_error = self._parse_oa_manual_import_row_ids(payload, max_count=20)
        if row_ids_error is not None:
            return row_ids_error
        actor_id = actor_id_for_session(session) if session is not None else "workbench_settings"
        try:
            result = service.request(row_ids, actor_id=actor_id or "workbench_settings")
        except OAAttachmentRefreshRowNotFoundError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": exc.code, "message": str(exc)},
            )
        except OAAttachmentRefreshRowNotCompletedError as exc:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": exc.code, "message": str(exc)},
            )
        except OAAttachmentRefreshRequestError as exc:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": exc.code,
                    "message": str(exc),
                },
            )
        except RuntimeError:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "oa_attachment_refresh_unavailable",
                    "message": "OA 附件刷新队列暂时不可用，请稍后重试。",
                },
            )
        return self._json_response(HTTPStatus.ACCEPTED, result)

    def oa_manual_search_refresh_status(
        self,
        event_id: str,
        headers: dict[str, str] | None,
    ) -> Any:
        _session, auth_error = self._resolve_settings_mutation_session(headers)
        if auth_error is not None:
            return auth_error
        service = self._oa_attachment_refresh_request_service_or_response()
        if not self._is_service_available(service):
            return service
        try:
            result = service.status(event_id)
        except OAAttachmentRefreshEventNotFoundError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": exc.code, "message": str(exc)},
            )
        except OAAttachmentRefreshRequestError as exc:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": exc.code, "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, result)

    def oa_manual_imports(self) -> Any:
        service = self._oa_manual_import_service_or_response()
        if not self._is_service_available(service):
            return service
        return self._json_response(HTTPStatus.OK, service.list_manual_imports())

    def create_oa_manual_imports(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_settings_mutation_session(headers)
        if auth_error is not None:
            return auth_error
        service = self._oa_manual_import_service_or_response()
        if not self._is_service_available(service):
            return service
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        row_ids, row_ids_error = self._parse_oa_manual_import_row_ids(payload)
        if row_ids_error is not None:
            return row_ids_error
        actor_id = (
            actor_id_for_session(session)
            if session is not None
            else str(payload.get("actor_id") or payload.get("actor") or "workbench_settings").strip()
        )
        normalized_actor_id = actor_id or "workbench_settings"
        if self._import_job_processing_enabled():
            try:
                import_job, event = self._enqueue_import_process_job(
                    import_type="oa_manual_import.create",
                    import_session_id=",".join(sorted(row_ids)),
                    idempotency_key=f"oa_manual_import.create:{normalized_actor_id}:{','.join(sorted(row_ids))}",
                    payload={"row_ids": row_ids, "actor_id": normalized_actor_id},
                    created_by=normalized_actor_id,
                    reason="oa_manual_import_create",
                )
            except RuntimeError as exc:
                return self._json_response(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "import_queue_unavailable", "message": str(exc)},
                )
            return self._json_response(
                HTTPStatus.ACCEPTED,
                {
                    "status": "queued",
                    "import_job": self._serialize_import_job(import_job),
                    "event_id": getattr(event, "event_id", None),
                },
            )
        result = service.import_row_ids(row_ids, actor_id=normalized_actor_id)
        self._add_manual_import_affected_scopes(result, row_ids=row_ids)
        return self._json_response(HTTPStatus.OK, result)

    def delete_oa_manual_import(
        self,
        row_id: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        session, auth_error = self._resolve_settings_mutation_session(headers)
        if auth_error is not None:
            return auth_error
        service = self._oa_manual_import_service_or_response()
        if not self._is_service_available(service):
            return service
        payload: dict[str, object] = {}
        if body:
            payload, error = self._load_json_body(body)
            if error is not None:
                return error
        normalized_row_id = str(row_id or "").strip()
        if not normalized_row_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_manual_import_request", "message": "row_id is required."},
            )
        actor_id = (
            actor_id_for_session(session)
            if session is not None
            else str(payload.get("actor_id") or payload.get("actor") or "workbench_settings").strip()
        )
        result = service.remove_manual_import(normalized_row_id, actor_id=actor_id or "workbench_settings")
        self._add_manual_import_affected_scopes(result, row_ids=[normalized_row_id])
        return self._json_response(HTTPStatus.OK, result)

    def sync_projects(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_settings_mutation_session(headers)
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        actor_id = actor_id_for_session(session) if session is not None else str(payload.get("actor_id", "")).strip()
        if not actor_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_sync_request", "message": "actor_id is required."},
            )
        try:
            run = self._project_costing_service().sync_projects_from_oa(actor_id=actor_id)
        except Exception as exc:
            return self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {"error": "oa_project_sync_failed", "message": f"OA 项目同步失败：{exc}"},
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "sync": self._serialize_sync_run(run),
                "settings": self._app_settings_service().get_settings_payload(),
            },
        )

    def create_project(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_settings_mutation_session(headers)
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        actor_id = actor_id_for_session(session) if session is not None else str(payload.get("actor_id", "")).strip()
        if not actor_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_create_request", "message": "actor_id is required."},
            )
        try:
            settings_payload = self._app_settings_service().create_manual_project(
                actor_id=actor_id,
                project_code=str(payload.get("project_code", "")),
                project_name=str(payload.get("project_name", "")),
                department_name=payload.get("department_name"),
                owner_name=payload.get("owner_name"),
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_create_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"settings": settings_payload})

    def delete_project(self, project_id: str, headers: dict[str, str] | None) -> Any:
        _session, auth_error = self._resolve_settings_mutation_session(headers)
        if auth_error is not None:
            return auth_error
        normalized_project_id = str(project_id).strip()
        if not normalized_project_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_delete_request", "message": "project_id is required."},
            )
        settings_payload = self._app_settings_service().delete_project(normalized_project_id)
        return self._json_response(HTTPStatus.OK, {"settings": settings_payload})

    def data_reset_preview(
        self,
        query: dict[str, list[str]],
        headers: dict[str, str] | None,
    ) -> Any:
        _admin_session, auth_error = self._resolve_admin_session(headers)
        if auth_error is not None:
            return auth_error
        action = str((query.get("action") or [""])[0] or "").strip()
        reset_service = self._settings_data_reset_service()
        if reset_service is None or action not in reset_service.supported_actions():
            return self._unsupported_settings_data_reset_response()
        return self._json_response(HTTPStatus.OK, {"preview": reset_service.preview(action)})

    def create_data_reset_job(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        request_id: str,
    ) -> Any:
        payload, admin_session, error = self._validate_data_reset_request(body, headers)
        if error is not None:
            return error
        action = str(payload.get("action") or "").strip()
        reset_service = self._settings_data_reset_service()
        if reset_service is None or action not in reset_service.supported_actions():
            return self._unsupported_settings_data_reset_response()

        owner_user_id = str(admin_session.identity.username or actor_id_for_session(admin_session))
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "settings_data_reset_idempotency_key_required",
                    "message": "idempotency_key is required.",
                },
            )
        try:
            job, _created = self._request_data_reset(
                action=action,
                owner_user_id=owner_user_id,
                idempotency_key=idempotency_key,
                label=self._data_reset_job_label(action),
                reason=str(payload.get("reason") or "").strip(),
                impact_fingerprint=str(payload.get("impact_fingerprint") or "").strip(),
                recovery_receipt_id=str(payload.get("recovery_receipt_id") or "").strip(),
                request_id=request_id,
            )
        except SettingsDataResetAlreadyActive as exc:
            active_job = self._background_job_service().job_from_payload(exc.payload)
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "settings_data_reset_job_running",
                    "message": "已有数据重置任务正在执行，请等待当前任务完成。",
                    "job": self._serialize_data_reset_background_job(active_job),
                },
            )
        except SettingsDataResetIdempotencyConflict:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "settings_data_reset_idempotency_conflict",
                    "message": "该操作标识已用于不同的数据重置请求。",
                },
            )
        except SettingsDataResetRecoveryUnavailable:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "settings_data_reset_recovery_unavailable",
                    "message": "恢复点已失效或不再匹配当前数据，请重新生成恢复点后再试。",
                },
            )
        except SettingsDataResetEnqueueError as exc:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "settings_data_reset_enqueue_failed",
                    "message": "数据重置任务暂时无法入队，请稍后重试。",
                    "job": self._serialize_data_reset_background_job(exc.job),
                },
            )
        return self._json_response(HTTPStatus.ACCEPTED, {"job": self._serialize_data_reset_background_job(job)})

    def data_reset_job(self, job_id: str, headers: dict[str, str] | None) -> Any:
        admin_session, auth_error = self._resolve_admin_session(headers)
        if auth_error is not None:
            return auth_error
        normalized_job_id = str(job_id or "").strip()
        owner_user_id = str(admin_session.identity.username or actor_id_for_session(admin_session))
        try:
            job = self._background_job_service().get_job(normalized_job_id, owner_user_id)
        except (BackgroundJobNotFoundError, BackgroundJobAccessError):
            return self._settings_data_reset_job_not_found()
        if job.type != "settings_data_reset":
            return self._settings_data_reset_job_not_found()
        return self._json_response(HTTPStatus.OK, {"job": self._serialize_data_reset_background_job(job)})

    def active_data_reset_job(self, headers: dict[str, str] | None) -> Any:
        admin_session, auth_error = self._resolve_admin_session(headers)
        if auth_error is not None:
            return auth_error
        owner_user_id = str(admin_session.identity.username or actor_id_for_session(admin_session))
        active_job = self._active_data_reset_background_job(owner_user_id)
        return self._json_response(
            HTTPStatus.OK,
            {"job": self._serialize_data_reset_background_job(active_job) if active_job is not None else None},
        )

    def _validate_data_reset_request(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> tuple[dict[str, object], OARequestSession | None, Any | None]:
        if self._settings_data_reset_service() is None:
            return {}, None, self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "settings_data_reset_unavailable",
                    "message": "当前运行模式未启用持久化状态存储，不能执行数据重置。",
                },
            )
        admin_session, admin_error = self._resolve_admin_session(headers)
        if admin_error is not None:
            return {}, None, admin_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return {}, None, error
        action = str(payload.get("action") or "").strip()
        if not action:
            return {}, None, self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_settings_reset_request", "message": "action is required."},
            )
        reset_service = self._settings_data_reset_service()
        if reset_service is None or action not in reset_service.supported_actions():
            return {}, None, self._unsupported_settings_data_reset_response()
        reason = str(payload.get("reason") or "").strip()
        if len(reason) < 5 or len(reason) > 500:
            return {}, None, self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "settings_data_reset_reason_required",
                    "message": "请填写 5 至 500 个字符的重置原因。",
                },
            )
        impact_fingerprint = str(payload.get("impact_fingerprint") or "").strip()
        recovery_receipt_id = str(payload.get("recovery_receipt_id") or "").strip()
        try:
            UUID(recovery_receipt_id)
        except (TypeError, ValueError):
            return {}, None, self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "settings_data_reset_recovery_unavailable",
                    "message": "本次重置没有可用的恢复点。",
                },
            )
        preview = reset_service.preview(action)
        if (
            preview.get("impact_fingerprint") != impact_fingerprint
            or preview.get("recovery_receipt_id") != recovery_receipt_id
            or preview.get("recovery_ready") is not True
        ):
            return {}, None, self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "settings_data_reset_impact_changed",
                    "message": "数据范围或恢复点已变化，请重新确认。",
                    "preview": preview,
                },
            )
        oa_password = payload.get("oa_password")
        if not isinstance(oa_password, str) or not oa_password:
            return {}, None, self._oa_password_verification_failed_response()
        password_error = self._verify_reset_oa_password(admin_session, oa_password)
        if password_error is not None:
            return {}, None, password_error
        return dict(payload), admin_session, None

    def _unsupported_settings_data_reset_response(self) -> Any:
        reset_service = self._settings_data_reset_service()
        return self._json_response(
            HTTPStatus.BAD_REQUEST,
            {
                "error": "invalid_workbench_settings_reset_request",
                "message": "unsupported action.",
                "supported_actions": reset_service.supported_actions() if reset_service is not None else [],
                "protected_targets": reset_service.protected_targets() if reset_service is not None else [],
            },
        )

    def _active_data_reset_background_job(self, owner_user_id: str) -> Any | None:
        for job in self._background_job_service().list_active_jobs(owner_user_id, include_system=True):
            if job.type == "settings_data_reset" and job.status in {"queued", "running"}:
                return job
        return None

    @staticmethod
    def _data_reset_job_label(action: str) -> str:
        if action == RESET_BANK_TRANSACTIONS_ACTION:
            return "重置银行流水"
        if action == RESET_INVOICES_ACTION:
            return "重置发票数据"
        if action == RESET_OA_AND_REBUILD_ACTION:
            return "重置 OA 并重建关联台"
        return "数据重置"

    def _settings_data_reset_job_not_found(self) -> Any:
        return self._json_response(
            HTTPStatus.NOT_FOUND,
            {"error": "settings_data_reset_job_not_found", "message": "数据重置任务不存在或已过期。"},
        )

    def _resolve_settings_mutation_session(
        self,
        headers: dict[str, str] | None,
        *,
        denied_message: str = "当前账户没有保存设置权限。",
    ) -> tuple[OARequestSession | None, Any | None]:
        session, auth_error = self._resolve_read_session(headers)
        if auth_error is not None:
            return None, auth_error
        if session is not None and not session.can_mutate_data:
            return None, self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": denied_message},
            )
        return session, None

    def _oa_applicant_credential_error_response(self, exc: OaApplicantCredentialError) -> Any:
        if isinstance(exc, OaApplicantCredentialPermissionError):
            status = HTTPStatus.FORBIDDEN
        elif isinstance(exc, OaApplicantCredentialValidationError):
            status = HTTPStatus.BAD_REQUEST
        elif isinstance(exc, OaApplicantCredentialConfigurationError):
            status = HTTPStatus.SERVICE_UNAVAILABLE
        else:
            status = HTTPStatus.BAD_REQUEST
        return self._json_response(
            status,
            {"error": getattr(exc, "code", "oa_applicant_credentials_error"), "message": str(exc)},
        )

    def _oa_manual_import_service_or_response(self) -> Any:
        service = self._oa_manual_import_service_provider()
        if service is None:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "oa_manual_import_unavailable",
                    "message": "OA 手动导入服务不可用，请检查 OA Mongo 与状态存储配置。",
                },
            )
        return service

    def _oa_attachment_refresh_request_service_or_response(self) -> Any:
        service = self._oa_attachment_refresh_request_service_provider()
        if service is None:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "oa_attachment_refresh_unavailable",
                    "message": "OA 附件刷新队列服务不可用。",
                },
            )
        return service

    @staticmethod
    def _is_service_available(value: Any) -> bool:
        return (
            callable(getattr(value, "search", None))
            or callable(getattr(value, "list_manual_imports", None))
            or callable(getattr(value, "request", None))
        )

    def _parse_oa_manual_search_pagination(
        self,
        query: dict[str, list[str]],
    ) -> tuple[dict[str, int], Any | None]:
        try:
            page = int(query.get("page", ["0"])[0] or 0)
            page_size = int(query.get("page_size", ["20"])[0] or 20)
        except (TypeError, ValueError):
            return {}, self._invalid_oa_manual_search_request("page and page_size must be integers.")
        if page < 0:
            return {}, self._invalid_oa_manual_search_request("page must be greater than or equal to 0.")
        if page_size < 1 or page_size > 100:
            return {}, self._invalid_oa_manual_search_request("page_size must be between 1 and 100.")
        return {"page": page, "page_size": page_size}, None

    def _invalid_oa_manual_search_request(self, message: str) -> Any:
        return self._json_response(
            HTTPStatus.BAD_REQUEST,
            {"error": "invalid_oa_manual_search_request", "message": message},
        )

    def _parse_oa_manual_import_row_ids(
        self,
        payload: dict[str, object],
        *,
        max_count: int | None = None,
    ) -> tuple[list[str], Any | None]:
        row_ids = payload.get("row_ids")
        if not isinstance(row_ids, list):
            return [], self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_manual_import_request", "message": "row_ids must be an array."},
            )
        normalized: list[str] = []
        seen: set[str] = set()
        for row_id in row_ids:
            if not isinstance(row_id, str):
                return [], self._json_response(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "error": "invalid_oa_manual_import_request",
                        "message": "row_ids must contain strings only.",
                    },
                )
            text = row_id.strip()
            if not text or text in seen:
                continue
            normalized.append(text)
            seen.add(text)
        if not normalized:
            return [], self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_manual_import_request", "message": "row_ids is required."},
            )
        if max_count is not None and len(normalized) > max_count:
            return [], self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_oa_manual_import_request",
                    "message": f"row_ids must contain at most {max_count} unique items.",
                },
            )
        return normalized, None

    @staticmethod
    def _parse_csv_query_values(query: dict[str, list[str]], key: str) -> list[str] | None:
        raw_values = query.get(key)
        if raw_values is None:
            return None
        values: list[str] = []
        for raw_value in raw_values:
            values.extend(str(part).strip() for part in str(raw_value or "").split(","))
        return [value for value in values if value]

    def _add_manual_import_affected_scopes(self, result: dict[str, object], *, row_ids: list[str]) -> None:
        scope_keys = self._manual_import_affected_scope_keys(result, row_ids)
        result.update(self._manual_import_affected_scope_payload(scope_keys))

    def _app_settings_service(self) -> AppSettingsService:
        return self._app_settings_service_provider()

    def _project_costing_service(self) -> Any:
        return self._project_costing_service_provider()

    def _settings_data_reset_service(self) -> SettingsDataResetService | None:
        return self._settings_data_reset_service_provider()

    def _background_job_service(self) -> Any:
        return self._background_job_service_provider()

    def _oa_applicant_credential_service(self) -> OaApplicantCredentialService:
        return self._oa_applicant_credential_service_provider()
