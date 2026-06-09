from __future__ import annotations

from http import HTTPStatus
from typing import Any
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
    EtcOAClientError,
    EtcServiceError,
    UploadedEtcZipFile,
)
from fin_ops_platform.services.object_storage import ObjectStorageWriteError


class EtcBusinessBatchApiRoutes:
    def __init__(self, application_service: EtcBusinessBatchApplicationService) -> None:
        self._application_service = application_service

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
                expected_version=self._optional_int(payload.get("expectedVersion") or payload.get("expected_version")),
                actor=self._actor(session),
                headers=headers,
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
        if isinstance(exc, EtcBusinessBatchInvalidTransitionError):
            return HTTPStatus.UNPROCESSABLE_ENTITY, cls._error(
                getattr(exc, "code", "invalid_status_transition"),
                str(exc),
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
