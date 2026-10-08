from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import uuid4

from fin_ops_platform.services.oa_identity_service import OAIdentityServiceError, OAUserIdentity
from fin_ops_platform.services.oa_role_sync_service import OAUserDirectoryEntry, OARoleSyncError
from fin_ops_platform.services.target_oa_applicant_token_provider import (
    TargetOaApplicantConfigurationError,
    TargetOaApplicantLoginError,
    TargetOaApplicantLoginUnavailableError,
)


class OaApplicantCredentialError(RuntimeError):
    code = "oa_applicant_credentials_error"


class OaApplicantCredentialPermissionError(OaApplicantCredentialError):
    code = "permission_denied"


class OaApplicantCredentialValidationError(OaApplicantCredentialError):
    code = "invalid_oa_applicant_credential"


class OaApplicantCredentialConfigurationError(OaApplicantCredentialError):
    code = "oa_applicant_credentials_unavailable"


class OaApplicantCredentialConflictError(OaApplicantCredentialError):
    code = "oa_applicant_credential_conflict"


class OaApplicantCredentialNotFoundError(OaApplicantCredentialError):
    code = "oa_applicant_credential_not_found"


class OaApplicantCredentialVerificationError(OaApplicantCredentialError):
    code = "oa_applicant_verification_failed"


@dataclass(slots=True, frozen=True)
class OaApplicantCredentialSummary:
    target_applicant_code: str
    target_applicant_name: str
    oa_username: str
    credential_status: str
    has_credential: bool
    enabled: bool = True
    oa_user_id: str | None = None
    remark: str = ""
    verified_at: datetime | None = None
    version: int = 1


@dataclass(slots=True, frozen=True)
class OaApplicantLoginCredential:
    target_applicant_code: str
    oa_username: str
    password: str


class OaApplicantCredentialRepository(Protocol):
    def list_credentials(self) -> list[OaApplicantCredentialSummary]: ...
    def get_credential(self, code: str) -> OaApplicantCredentialSummary | None: ...
    def save_credential(self, *, summary: OaApplicantCredentialSummary, password: str,
                        actor_id: str, expected_version: int | None) -> OaApplicantCredentialSummary: ...
    def delete_credential(self, *, target_applicant_code: str, actor_id: str, expected_version: int) -> None: ...
    def resolve_login_credential(self, target_applicant_code: str) -> OaApplicantLoginCredential | None: ...


class OaApplicantDirectory(Protocol):
    def list_users(self) -> list[OAUserDirectoryEntry]: ...
    def get_user(self, user_id: str) -> OAUserDirectoryEntry | None: ...


class OaCredentialLoginClient(Protocol):
    def login(self, username: str, password: str) -> str: ...


class OaCredentialIdentityResolver(Protocol):
    def resolve_identity(self, token: str) -> OAUserIdentity: ...


class OaApplicantCredentialService:
    def __init__(self, *, repository: OaApplicantCredentialRepository,
                 directory: OaApplicantDirectory | None = None,
                 login_client: OaCredentialLoginClient | None = None,
                 identity_resolver: OaCredentialIdentityResolver | None = None) -> None:
        self._repository = repository
        self._directory = directory
        self._login_client = login_client
        self._identity_resolver = identity_resolver

    def list_credentials(self, *, can_admin_access: bool) -> dict[str, object]:
        self._require_admin(can_admin_access)
        return {"credentials": [self._summary_payload(item) for item in self._repository.list_credentials()]}

    def list_users(self, *, can_admin_access: bool) -> dict[str, object]:
        self._require_admin(can_admin_access)
        if self._directory is None:
            raise OaApplicantCredentialConfigurationError("OA 用户目录未配置。")
        try:
            users = self._directory.list_users()
        except OARoleSyncError as exc:
            raise OaApplicantCredentialConfigurationError("OA 用户目录读取失败，请重试。") from exc
        return {"users": [{"userId": user.user_id, "username": user.username,
                           "displayName": user.display_name, "active": user.active}
                          for user in sorted(users, key=lambda user: (not user.active, user.display_name, user.username))]}

    def applicant_options(self) -> list[dict[str, str]]:
        return [{"code": item.target_applicant_code, "name": item.target_applicant_name, "remark": item.remark}
                for item in self._repository.list_credentials()
                if item.enabled and item.has_credential and item.credential_status == "configured"
                and item.verified_at is not None and item.oa_user_id]

    def save_credential(self, *, oa_user_id: object, password: object, remark: object,
                        actor_id: str, can_admin_access: bool,
                        target_applicant_code: str | None = None,
                        expected_version: object = None) -> dict[str, object]:
        self._require_admin(can_admin_access)
        user_id = self._required_text(oa_user_id, "oaUserId")
        if not isinstance(password, str) or not password or len(password) > 4096:
            raise OaApplicantCredentialValidationError("请输入有效的 OA 登录密码。")
        if not isinstance(remark, str) or len(remark.strip()) > 100:
            raise OaApplicantCredentialValidationError("备注须为不超过 100 字的文本。")
        existing = None
        if target_applicant_code is not None:
            self._require_version(expected_version)
            existing = self._repository.get_credential(target_applicant_code)
            if existing is None:
                raise OaApplicantCredentialNotFoundError("申请人记录已删除，请刷新。")
            if existing.version != expected_version:
                raise OaApplicantCredentialConflictError("申请人记录已修改，请刷新。")
            if existing.oa_user_id is not None and existing.oa_user_id != user_id:
                raise OaApplicantCredentialValidationError("已绑定的 OA 申请人不能更换。")
        elif expected_version is not None:
            raise OaApplicantCredentialValidationError("新增申请人不能指定版本。")
        if self._directory is None or self._login_client is None or self._identity_resolver is None:
            raise OaApplicantCredentialConfigurationError("OA 凭据验证服务未配置。")
        try:
            user = self._directory.get_user(user_id)
        except OARoleSyncError as exc:
            raise OaApplicantCredentialConfigurationError("OA 用户目录读取失败，请重试。") from exc
        if user is None:
            raise OaApplicantCredentialValidationError("OA 用户不存在，请重新选择。")
        if not user.active:
            raise OaApplicantCredentialValidationError("OA 账号已停用。")
        if (existing is not None and existing.oa_user_id is None and existing.oa_username
                and existing.oa_username.casefold() != user.username.casefold()):
            raise OaApplicantCredentialValidationError("请选择该记录原有的 OA 登录账号。")
        if any(item.target_applicant_code != target_applicant_code
               and (item.oa_user_id == user_id or
                    (item.oa_user_id is None and item.oa_username.casefold() == user.username.casefold()))
               for item in self._repository.list_credentials()):
            raise OaApplicantCredentialConflictError("该 OA 申请人已配置，请编辑已有记录。")
        try:
            token = self._login_client.login(user.username, password)
            identity = self._identity_resolver.resolve_identity(token)
        except (TargetOaApplicantConfigurationError, TargetOaApplicantLoginUnavailableError, OAIdentityServiceError, TimeoutError, OSError) as exc:
            raise OaApplicantCredentialConfigurationError("暂时无法验证 OA 账号，请重试。") from exc
        except TargetOaApplicantLoginError as exc:
            raise OaApplicantCredentialVerificationError(str(exc)) from exc
        if identity.user_id != user.user_id or identity.username.casefold() != user.username.casefold():
            raise OaApplicantCredentialVerificationError("账号身份校验失败。")
        summary = OaApplicantCredentialSummary(
            target_applicant_code=target_applicant_code or uuid4().hex,
            target_applicant_name=user.display_name, oa_username=user.username,
            credential_status="configured", has_credential=True, oa_user_id=user.user_id,
            remark=remark.strip(), verified_at=datetime.now(UTC),
            version=expected_version + 1 if isinstance(expected_version, int) else 1,
        )
        saved = self._repository.save_credential(summary=summary, password=password,
                                                actor_id=self._actor(actor_id), expected_version=expected_version)
        return self._summary_payload(saved)

    def delete_credential(self, *, target_applicant_code: str, actor_id: str,
                          can_admin_access: bool, expected_version: object) -> dict[str, object]:
        self._require_admin(can_admin_access)
        self._require_version(expected_version)
        self._repository.delete_credential(target_applicant_code=target_applicant_code,
                                           actor_id=self._actor(actor_id), expected_version=expected_version)
        return {"deleted": True, "targetApplicantCode": target_applicant_code}

    def resolve_login_credential(self, target_applicant_code: str) -> OaApplicantLoginCredential | None:
        return self._repository.resolve_login_credential(target_applicant_code)

    @staticmethod
    def _require_admin(can_admin_access: bool) -> None:
        if not can_admin_access:
            raise OaApplicantCredentialPermissionError("当前账户没有维护 OA 申请人凭据的权限。")

    @staticmethod
    def _require_version(value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise OaApplicantCredentialValidationError("expectedVersion 须为正整数。")

    @staticmethod
    def _required_text(value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise OaApplicantCredentialValidationError(f"{field_name} 须为非空文本。")
        return value.strip()

    @staticmethod
    def _actor(actor_id: object) -> str:
        return str(actor_id or "").strip() or "system"

    @staticmethod
    def _summary_payload(summary: OaApplicantCredentialSummary) -> dict[str, object]:
        return {"targetApplicantCode": summary.target_applicant_code,
                "targetApplicantName": summary.target_applicant_name, "oaUsername": summary.oa_username,
                "credentialStatus": summary.credential_status, "hasCredential": summary.has_credential,
                "enabled": summary.enabled, "oaUserId": summary.oa_user_id, "remark": summary.remark,
                "verifiedAt": summary.verified_at.isoformat() if summary.verified_at else None,
                "version": summary.version}


class InMemoryOaApplicantCredentialRepository:
    """Explicit test double; application startup never selects this repository."""

    def __init__(self) -> None:
        self._records: dict[str, tuple[OaApplicantCredentialSummary, str]] = {}
        self._lock = RLock()

    def list_credentials(self) -> list[OaApplicantCredentialSummary]:
        with self._lock:
            return sorted((row[0] for row in self._records.values()),
                          key=lambda row: (row.target_applicant_name, row.target_applicant_code))

    def get_credential(self, code: str) -> OaApplicantCredentialSummary | None:
        with self._lock:
            row = self._records.get(code)
            return row[0] if row else None

    def save_credential(self, *, summary: OaApplicantCredentialSummary, password: str,
                        actor_id: str, expected_version: int | None) -> OaApplicantCredentialSummary:
        del actor_id
        with self._lock:
            current = self.get_credential(summary.target_applicant_code)
            if expected_version is not None and (current is None or current.version != expected_version):
                raise OaApplicantCredentialConflictError("申请人记录已修改或删除，请刷新。")
            if expected_version is None and current is not None:
                raise OaApplicantCredentialConflictError("申请人记录已存在。")
            if summary.oa_user_id and any(row[0].oa_user_id == summary.oa_user_id
                    and code != summary.target_applicant_code for code, row in self._records.items()):
                raise OaApplicantCredentialConflictError("该 OA 申请人已配置。")
            self._records[summary.target_applicant_code] = (summary, password)
            return summary

    def delete_credential(self, *, target_applicant_code: str, actor_id: str, expected_version: int) -> None:
        del actor_id
        with self._lock:
            current = self.get_credential(target_applicant_code)
            if current is None:
                raise OaApplicantCredentialNotFoundError("申请人记录已删除，请刷新。")
            if current.version != expected_version:
                raise OaApplicantCredentialConflictError("申请人记录已修改，请刷新。")
            del self._records[target_applicant_code]

    def resolve_login_credential(self, target_applicant_code: str) -> OaApplicantLoginCredential | None:
        with self._lock:
            row = self._records.get(target_applicant_code)
            if row is None:
                return None
            summary, password = row
            if (not summary.enabled or summary.credential_status != "configured"
                    or not summary.verified_at or not summary.oa_user_id or not password):
                return None
            return OaApplicantLoginCredential(target_applicant_code, summary.oa_username, password)
