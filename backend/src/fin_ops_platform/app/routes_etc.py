from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from uuid import uuid4

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.services.etc_business_batch_application_service import (
    EtcBusinessBatchActor,
    EtcBusinessBatchApplicationService,
    EtcBusinessBatchScopeError,
)
from fin_ops_platform.services.etc_service import (
    EtcBusinessBatchActiveExistsError,
    EtcBusinessBatchInvalidTransitionError,
    EtcBusinessBatchNotFoundError,
    EtcBusinessBatchVersionConflictError,
    EtcDraftRequestError,
    EtcOADraftOutcomeUnknownError,
    EtcOAClientError,
    EtcServiceError,
    UploadedEtcZipFile,
)
from fin_ops_platform.services.etc_business_batch_delete_service import EtcBusinessBatchDeleteService
from fin_ops_platform.services.etc_invoice_pdf_bundle_service import EtcInvoicePdfBundle, EtcInvoicePdfBundleError
from fin_ops_platform.services.object_storage import ObjectStorageWriteError
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


class EtcBusinessBatchApiRoutes:
    def __init__(
        self,
        application_service: EtcBusinessBatchApplicationService,
        *,
        delete_service: EtcBusinessBatchDeleteService,
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]],
        refresh_after_etc_invoice_link: Callable[[list[str], str], None],
        persist_state: Callable[[], None],
    ) -> None:
        self._application_service = application_service
        self._delete_service = delete_service
        self._load_json_body = load_json_body
        self._refresh_after_etc_invoice_link = refresh_after_etc_invoice_link
        self._persist_state = persist_state

    def list_batches(
        self,
        query: dict[str, list[str]],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        return self._success(
            HTTPStatus.OK,
            self._application_service.list_batches_payload(query, actor=self._actor(session)),
        )

    def create_batch(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.create_batch_payload(payload, actor=self._actor(session))
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.CREATED, result)

    def detail(
        self,
        business_batch_id: str,
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.detail_payload(business_batch_id, actor=self._actor(session))
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, result)

    def update_batch(
        self,
        business_batch_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.update_title_payload(
                business_batch_id,
                payload,
                actor=self._actor(session),
            )
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, result)

    def invoice_pdf_bundle(
        self,
        business_batch_id: str,
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, EtcInvoicePdfBundle | dict[str, Any]]:
        try:
            result = self._application_service.invoice_pdf_bundle(
                business_batch_id,
                actor=self._actor(session),
            )
        except Exception as exc:
            return self._error_response(exc)
        return HTTPStatus.OK, result

    def delete_batch(
        self,
        business_batch_id: str,
        body: str | bytes | None,
    ) -> tuple[HTTPStatus, dict[str, Any]] | Any:
        payload: dict[str, Any] = {}
        if body:
            payload, error = self._load_json_body(body)
            if error is not None:
                return error
        try:
            delete_result = self._delete_service.delete_business_batch(
                business_batch_id,
                expected_version=self._optional_int(payload.get("expectedVersion") or payload.get("expected_version")),
                reason=str(payload.get("reason") or "").strip() or None,
            )
            for event in delete_result.refresh_events:
                if event.changed_months:
                    self._refresh_after_etc_invoice_link(event.changed_months, event.reason)
                if event.persist_required:
                    self._persist_state()
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, delete_result.delete_result)

    def preview_import(
        self,
        business_batch_id: str,
        uploads: list[UploadedEtcZipFile],
        *,
        expected_version: int | None,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.preview_import_payload(
                business_batch_id,
                uploads,
                expected_version=expected_version,
                actor=self._actor(session),
            )
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, result)

    def confirm_import(
        self,
        business_batch_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.confirm_import_payload(
                business_batch_id,
                session_id=str(payload.get("sessionId") or payload.get("session_id") or "").strip(),
                expected_version=self._optional_int(payload.get("expectedVersion") or payload.get("expected_version")),
                idempotency_key=str(payload.get("idempotencyKey") or payload.get("idempotency_key") or "").strip() or None,
                actor=self._actor(session),
            )
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, result)

    def create_oa_draft(
        self,
        business_batch_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
        headers: dict[str, str] | None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.create_oa_draft_payload(
                business_batch_id,
                idempotency_key=str(payload.get("idempotencyKey") or payload.get("idempotency_key") or "").strip(),
                expected_version=self._optional_int(payload.get("expectedVersion") or payload.get("expected_version")),
                actor=self._actor(session),
                headers=headers,
            )
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, result)

    def recover_oa_draft(
        self,
        business_batch_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            confirmed_not_created = self._required_boolean_alias(
                payload,
                "confirmedNotCreated",
                "confirmed_not_created",
            )
            oa_draft_id = str(payload.get("draftId") or payload.get("draft_id") or "").strip() or None
            oa_draft_url = str(payload.get("draftUrl") or payload.get("draft_url") or "").strip() or None
            if confirmed_not_created and (oa_draft_id or oa_draft_url):
                raise EtcBusinessBatchInvalidTransitionError(
                    "确认未创建 OA 草稿时不能同时提交草稿编号或链接。",
                    code="invalid_oa_draft_recovery_decision",
                )
            if not confirmed_not_created and (not oa_draft_id or not oa_draft_url):
                raise EtcBusinessBatchInvalidTransitionError(
                    "确认已创建 OA 草稿时必须同时提交草稿编号和链接。",
                    code="invalid_oa_draft_recovery_decision",
                )
            result = self._application_service.recover_oa_draft_payload(
                business_batch_id,
                expected_version=self._optional_int(payload.get("expectedVersion") or payload.get("expected_version")),
                reason=str(payload.get("reason") or "").strip(),
                evidence=str(payload.get("evidence") or "").strip(),
                oa_draft_id=oa_draft_id,
                oa_draft_url=oa_draft_url,
                confirmed_not_created=confirmed_not_created,
                actor=self._actor(session),
            )
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, result)

    def revoke_oa_draft(
        self,
        business_batch_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.revoke_oa_draft_payload(
                business_batch_id,
                reason=str(payload.get("reason") or "").strip(),
                expected_version=self._optional_int(payload.get("expectedVersion") or payload.get("expected_version")),
                actor=self._actor(session),
            )
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, result)

    def manual_oa_status(
        self,
        business_batch_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.manual_oa_status_payload(
                business_batch_id,
                decision=str(payload.get("decision") or "").strip(),
                reason=str(payload.get("reason") or "").strip(),
                expected_version=self._optional_int(payload.get("expectedVersion") or payload.get("expected_version")),
                candidate_oa_row_id=str(payload.get("candidateOaRowId") or payload.get("candidate_oa_row_id") or "").strip() or None,
                actor=self._actor(session),
            )
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, result)

    def source_files(
        self,
        business_batch_id: str,
        uploads: list[object],
        *,
        session: OARequestSession,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            result = self._application_service.source_files_payload(
                business_batch_id,
                uploads,
                actor=self._actor(session),
            )
        except Exception as exc:
            return self._error_response(exc)
        return self._success(HTTPStatus.OK, result)

    @staticmethod
    def _actor(session: OARequestSession) -> EtcBusinessBatchActor:
        return EtcBusinessBatchActor(
            user_id=session.identity.user_id,
            username=session.identity.username,
            dept_id=session.identity.dept_id,
            can_admin_access=session.can_admin_access,
            can_mutate_data=session.can_mutate_data,
        )

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    @staticmethod
    def _required_boolean_alias(payload: dict[str, Any], camel_name: str, snake_name: str) -> bool:
        supplied = [(name, payload[name]) for name in (camel_name, snake_name) if name in payload]
        if len(supplied) != 1 or type(supplied[0][1]) is not bool:
            raise EtcBusinessBatchInvalidTransitionError(
                f"{camel_name} 必须且只能提供一次，并且必须是布尔值。",
                code="invalid_oa_draft_recovery_decision",
            )
        return supplied[0][1]

    @staticmethod
    def _success(status: HTTPStatus, data: object) -> tuple[HTTPStatus, dict[str, Any]]:
        return status, {"ok": True, "data": data, "error": None, "requestId": uuid4().hex[:12]}

    @classmethod
    def _error(cls, code: str, message: str, *, details: dict[str, object] | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "data": None,
            "error": {"code": code, "message": message, "details": details or {}},
            "requestId": uuid4().hex[:12],
        }

    @classmethod
    def _error_response(cls, exc: Exception) -> tuple[HTTPStatus, dict[str, Any]]:
        if isinstance(exc, EtcBusinessBatchNotFoundError):
            return HTTPStatus.NOT_FOUND, cls._error("business_batch_not_found", str(exc))
        if isinstance(exc, EtcBusinessBatchScopeError):
            return HTTPStatus.FORBIDDEN, cls._error("forbidden_scope", str(exc))
        if isinstance(exc, EtcBusinessBatchActiveExistsError):
            return HTTPStatus.CONFLICT, cls._error("active_business_batch_exists", str(exc))
        if isinstance(exc, EtcBusinessBatchVersionConflictError):
            return HTTPStatus.CONFLICT, cls._error(
                "version_conflict",
                "批次状态已变化，请刷新后重试。",
                details={
                    "businessBatchId": exc.business_batch_id,
                    "expectedVersion": exc.expected_version,
                    "actualVersion": exc.actual_version,
                },
            )
        if isinstance(exc, EtcInvoicePdfBundleError):
            status_by_code = {
                "invoice_pdf_bundle_not_ready": HTTPStatus.CONFLICT,
                "invoice_pdf_bundle_empty": HTTPStatus.CONFLICT,
                "invoice_pdf_bundle_too_large": HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "invoice_pdf_unavailable": HTTPStatus.SERVICE_UNAVAILABLE,
                "invoice_pdf_invalid": HTTPStatus.UNPROCESSABLE_ENTITY,
                "invoice_pdf_page_count_invalid": HTTPStatus.UNPROCESSABLE_ENTITY,
                "invoice_pdf_bundle_invariant_failed": HTTPStatus.INTERNAL_SERVER_ERROR,
            }
            return status_by_code.get(exc.code, HTTPStatus.UNPROCESSABLE_ENTITY), cls._error(exc.code, str(exc))
        if isinstance(exc, WorkbenchRelationCommandError):
            return HTTPStatus.CONFLICT, cls._error(
                exc.error_code,
                exc.message,
                details=dict(exc.payload or {}),
            )
        if isinstance(exc, EtcBusinessBatchInvalidTransitionError):
            return HTTPStatus.UNPROCESSABLE_ENTITY, cls._error(
                getattr(exc, "code", "invalid_status_transition"),
                str(exc),
            )
        if isinstance(exc, EtcOADraftOutcomeUnknownError):
            return HTTPStatus.CONFLICT, cls._error(
                "oa_draft_outcome_unknown",
                str(exc),
                details={"businessBatchId": exc.business_batch_id, "recoveryRequired": True},
            )
        if isinstance(exc, (EtcDraftRequestError, EtcOAClientError)):
            return HTTPStatus.BAD_REQUEST, cls._error("invalid_etc_draft_request", str(exc))
        if isinstance(exc, ObjectStorageWriteError):
            return HTTPStatus.SERVICE_UNAVAILABLE, cls._error(
                "reconciliation_file_storage_unavailable",
                "文件存储暂时不可用，上传未保存。请稍后重试或联系管理员检查对象存储配置。",
            )
        if isinstance(exc, EtcServiceError):
            return HTTPStatus.BAD_REQUEST, cls._error("invalid_etc_business_batch_request", str(exc))
        raise exc
