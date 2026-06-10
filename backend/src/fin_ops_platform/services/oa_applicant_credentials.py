from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Protocol


class OaApplicantCredentialError(RuntimeError):
    code = "oa_applicant_credentials_error"


class OaApplicantCredentialPermissionError(OaApplicantCredentialError):
    code = "permission_denied"


class OaApplicantCredentialValidationError(OaApplicantCredentialError):
    code = "invalid_oa_applicant_credential"


class OaApplicantCredentialConfigurationError(OaApplicantCredentialError):
    code = "oa_applicant_credentials_unavailable"


@dataclass(slots=True, frozen=True)
class OaApplicantCredentialSummary:
    target_applicant_code: str
    target_applicant_name: str
    oa_username: str
    credential_status: str
    has_credential: bool
    enabled: bool = True


@dataclass(slots=True, frozen=True)
class OaApplicantLoginCredential:
    target_applicant_code: str
    oa_username: str
    password: str


class OaApplicantCredentialRepository(Protocol):
    def list_credentials(self) -> list[OaApplicantCredentialSummary]:
        ...

    def save_credential(
        self,
        *,
        target_applicant_code: str,
        target_applicant_name: str,
        oa_username: str,
        password: str,
        actor_id: str,
    ) -> OaApplicantCredentialSummary:
        ...

    def delete_credential(self, *, target_applicant_code: str, actor_id: str) -> OaApplicantCredentialSummary:
        ...

    def resolve_login_credential(self, target_applicant_code: str) -> OaApplicantLoginCredential | None:
        ...


class OaApplicantCredentialService:
    def __init__(self, *, repository: OaApplicantCredentialRepository) -> None:
        self._repository = repository

    def list_credentials(self, *, can_admin_access: bool) -> dict[str, object]:
        self._require_admin(can_admin_access)
        return {"credentials": [self._summary_payload(item) for item in self._repository.list_credentials()]}

    def save_credential(
        self,
        *,
        target_applicant_code: str,
        target_applicant_name: str,
        oa_username: str,
        password: str,
        actor_id: str,
        can_admin_access: bool,
    ) -> dict[str, object]:
        self._require_admin(can_admin_access)
        normalized_code = self._required_text(target_applicant_code, "targetApplicantCode")
        normalized_name = self._required_text(target_applicant_name, "targetApplicantName")
        normalized_username = self._required_text(oa_username, "oaUsername")
        normalized_password = self._required_text(password, "password")
        summary = self._repository.save_credential(
            target_applicant_code=normalized_code,
            target_applicant_name=normalized_name,
            oa_username=normalized_username,
            password=normalized_password,
            actor_id=self._actor(actor_id),
        )
        return self._summary_payload(summary)

    def delete_credential(
        self,
        *,
        target_applicant_code: str,
        actor_id: str,
        can_admin_access: bool,
    ) -> dict[str, object]:
        self._require_admin(can_admin_access)
        normalized_code = self._required_text(target_applicant_code, "targetApplicantCode")
        summary = self._repository.delete_credential(
            target_applicant_code=normalized_code,
            actor_id=self._actor(actor_id),
        )
        return self._summary_payload(summary)

    def resolve_login_credential(self, target_applicant_code: str) -> OaApplicantLoginCredential | None:
        normalized_code = str(target_applicant_code or "").strip()
        if not normalized_code:
            return None
        return self._repository.resolve_login_credential(normalized_code)

    @staticmethod
    def _require_admin(can_admin_access: bool) -> None:
        if not can_admin_access:
            raise OaApplicantCredentialPermissionError("当前账户没有维护 OA 申请人凭据的权限。")

    @staticmethod
    def _required_text(value: object, field_name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise OaApplicantCredentialValidationError(f"{field_name} is required.")
        return normalized

    @staticmethod
    def _actor(actor_id: object) -> str:
        normalized = str(actor_id or "").strip()
        return normalized or "system"

    @staticmethod
    def _summary_payload(summary: OaApplicantCredentialSummary) -> dict[str, object]:
        return {
            "targetApplicantCode": summary.target_applicant_code,
            "targetApplicantName": summary.target_applicant_name,
            "oaUsername": summary.oa_username,
            "credentialStatus": summary.credential_status,
            "hasCredential": bool(summary.has_credential),
            "enabled": bool(summary.enabled),
        }


@dataclass(slots=True)
class _InMemoryCredentialRecord:
    target_applicant_code: str
    target_applicant_name: str
    oa_username: str
    password: str | None
    credential_status: str
    enabled: bool = True


class InMemoryOaApplicantCredentialRepository:
    def __init__(self) -> None:
        self._records: dict[str, _InMemoryCredentialRecord] = {}
        self._lock = RLock()

    def list_credentials(self) -> list[OaApplicantCredentialSummary]:
        with self._lock:
            records = sorted(
                self._records.values(),
                key=lambda item: (item.target_applicant_name, item.target_applicant_code),
            )
            return [self._summary(record) for record in records]

    def save_credential(
        self,
        *,
        target_applicant_code: str,
        target_applicant_name: str,
        oa_username: str,
        password: str,
        actor_id: str,
    ) -> OaApplicantCredentialSummary:
        del actor_id
        with self._lock:
            record = _InMemoryCredentialRecord(
                target_applicant_code=target_applicant_code,
                target_applicant_name=target_applicant_name,
                oa_username=oa_username,
                password=password,
                credential_status="configured",
                enabled=True,
            )
            self._records[target_applicant_code] = record
            return self._summary(record)

    def delete_credential(self, *, target_applicant_code: str, actor_id: str) -> OaApplicantCredentialSummary:
        del actor_id
        with self._lock:
            existing = self._records.get(target_applicant_code)
            record = _InMemoryCredentialRecord(
                target_applicant_code=target_applicant_code,
                target_applicant_name=existing.target_applicant_name if existing else "",
                oa_username=existing.oa_username if existing else "",
                password=None,
                credential_status="unconfigured",
                enabled=True,
            )
            self._records[target_applicant_code] = record
            return self._summary(record)

    def resolve_login_credential(self, target_applicant_code: str) -> OaApplicantLoginCredential | None:
        with self._lock:
            record = self._records.get(target_applicant_code)
            if record is None or record.credential_status != "configured" or not record.password:
                return None
            return OaApplicantLoginCredential(
                target_applicant_code=record.target_applicant_code,
                oa_username=record.oa_username,
                password=record.password,
            )

    @staticmethod
    def _summary(record: _InMemoryCredentialRecord) -> OaApplicantCredentialSummary:
        has_credential = record.credential_status == "configured" and bool(record.password)
        return OaApplicantCredentialSummary(
            target_applicant_code=record.target_applicant_code,
            target_applicant_name=record.target_applicant_name,
            oa_username=record.oa_username,
            credential_status="configured" if has_credential else "unconfigured",
            has_credential=has_credential,
            enabled=record.enabled,
        )
