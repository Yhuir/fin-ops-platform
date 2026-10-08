from __future__ import annotations

import os
from typing import Any, Callable

from psycopg.errors import UniqueViolation

from fin_ops_platform.services.oa_applicant_credentials import (
    OaApplicantCredentialConfigurationError,
    OaApplicantCredentialConflictError,
    OaApplicantCredentialNotFoundError,
    OaApplicantCredentialSummary,
    OaApplicantCredentialValidationError,
    OaApplicantLoginCredential,
)

OA_APPLICANT_CREDENTIAL_KEY_ENV = "FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY"
_SUMMARY_COLUMNS = """target_applicant_code, target_applicant_name, oa_username,
    credential_status, (credential_status = 'configured') as has_credential,
    enabled, oa_user_id, remark, verified_at, version"""


class PostgresOaApplicantCredentialRepository:
    def __init__(self, connection: Any, *, encryption_key: str | None = None,
                 delete_guard: Callable[[Any, str], None] | None = None) -> None:
        self._connection = connection
        self._encryption_key = encryption_key
        self._delete_guard = delete_guard

    def list_credentials(self) -> list[OaApplicantCredentialSummary]:
        rows = self._connection.fetch_all(
            f"select {_SUMMARY_COLUMNS} from app.oa_applicant_credentials "
            "order by target_applicant_name, target_applicant_code", (),
        )
        return [self._summary_from_row(row) for row in rows]

    def get_credential(self, code: str) -> OaApplicantCredentialSummary | None:
        row = self._connection.fetch_one(
            f"select {_SUMMARY_COLUMNS} from app.oa_applicant_credentials where target_applicant_code = %s", (code,))
        return self._summary_from_row(row) if row else None

    def save_credential(self, *, summary: OaApplicantCredentialSummary, password: str,
                        actor_id: str, expected_version: int | None) -> OaApplicantCredentialSummary:
        key = self._required_encryption_key()
        values = (summary.target_applicant_name, summary.oa_username, password, key, actor_id,
                  summary.oa_user_id, summary.remark, summary.verified_at, summary.version)
        try:
            with self._connection.transaction() as transaction:
                if expected_version is None:
                    row = transaction.fetch_one(
                        f"""insert into app.oa_applicant_credentials(
                            target_applicant_name, oa_username, encrypted_password, updated_by,
                            oa_user_id, remark, verified_at, version, target_applicant_code,
                            credential_status, enabled)
                        values (%s, %s, pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256, compress-algo=1'),
                                %s, %s, %s, %s, %s, %s, 'configured', true)
                        returning {_SUMMARY_COLUMNS}""", (*values, summary.target_applicant_code))
                else:
                    row = transaction.fetch_one(
                        f"""update app.oa_applicant_credentials set
                            target_applicant_name = %s, oa_username = %s,
                            encrypted_password = pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256, compress-algo=1'),
                            updated_by = %s, oa_user_id = %s, remark = %s, verified_at = %s,
                            version = %s, credential_status = 'configured', enabled = true, updated_at = now()
                        where target_applicant_code = %s and version = %s
                          and (oa_user_id is null or oa_user_id = %s)
                        returning {_SUMMARY_COLUMNS}""",
                        (*values, summary.target_applicant_code, expected_version, summary.oa_user_id))
                if row is None:
                    raise OaApplicantCredentialConflictError("申请人记录已修改或删除，请刷新。")
                return self._summary_from_row(row)
        except UniqueViolation as exc:
            raise OaApplicantCredentialConflictError("该 OA 申请人已配置，请编辑已有记录。") from exc

    def delete_credential(self, *, target_applicant_code: str, actor_id: str, expected_version: int) -> None:
        del actor_id
        with self._connection.transaction() as transaction:
            current = transaction.fetch_one(
                "select version from app.oa_applicant_credentials where target_applicant_code = %s for update",
                (target_applicant_code,))
            if current is None:
                raise OaApplicantCredentialNotFoundError("申请人记录已删除，请刷新。")
            if current["version"] != expected_version:
                raise OaApplicantCredentialConflictError("申请人记录已修改，请刷新。")
            if self._delete_guard is not None:
                self._delete_guard(transaction, target_applicant_code)
            transaction.execute("delete from app.oa_applicant_credentials where target_applicant_code = %s",
                                (target_applicant_code,))

    @staticmethod
    def lock_verified_credential(connection: Any, target_code: str) -> None:
        row = connection.fetch_one(
            """select oa_user_id, verified_at, credential_status, enabled
               from app.oa_applicant_credentials where target_applicant_code = %s for update""", (target_code,))
        if row is None:
            raise OaApplicantCredentialNotFoundError("反提 OA 申请人已删除。")
        if not row["oa_user_id"] or not row["verified_at"] or row["credential_status"] != "configured" or not row["enabled"]:
            raise OaApplicantCredentialValidationError("反提 OA 申请人凭据尚未验证。")

    def resolve_login_credential(self, target_applicant_code: str) -> OaApplicantLoginCredential | None:
        key = self._required_encryption_key()
        row = self._connection.fetch_one(
            """select target_applicant_code, oa_username,
                      pgp_sym_decrypt(encrypted_password, %s) as password
               from app.oa_applicant_credentials where target_applicant_code = %s
                 and credential_status = 'configured' and enabled = true
                 and verified_at is not null and oa_user_id is not null
                 and encrypted_password is not null""", (key, target_applicant_code))
        if row is None:
            return None
        return OaApplicantLoginCredential(target_applicant_code=row["target_applicant_code"],
                                          oa_username=row["oa_username"], password=row["password"])

    def _required_encryption_key(self) -> str:
        key = str(self._encryption_key or os.getenv(OA_APPLICANT_CREDENTIAL_KEY_ENV) or "").strip()
        if not key:
            raise OaApplicantCredentialConfigurationError("OA 申请人凭据加密密钥未配置。")
        return key

    @staticmethod
    def _summary_from_row(row: dict[str, Any]) -> OaApplicantCredentialSummary:
        return OaApplicantCredentialSummary(
            target_applicant_code=row["target_applicant_code"], target_applicant_name=row["target_applicant_name"],
            oa_username=row["oa_username"], credential_status=row["credential_status"],
            has_credential=row["has_credential"], enabled=row["enabled"], oa_user_id=row["oa_user_id"],
            remark=row["remark"], verified_at=row["verified_at"], version=row["version"])
