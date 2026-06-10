from __future__ import annotations

import os
from typing import Any

from fin_ops_platform.services.oa_applicant_credentials import (
    OaApplicantCredentialConfigurationError,
    OaApplicantCredentialSummary,
    OaApplicantLoginCredential,
)
from fin_ops_platform.services.postgres_repositories.common import jsonb as _jsonb


OA_APPLICANT_CREDENTIAL_KEY_ENV = "FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY"


class PostgresOaApplicantCredentialRepository:
    def __init__(self, connection: Any, *, encryption_key: str | None = None) -> None:
        self._connection = connection
        self._encryption_key = encryption_key

    def list_credentials(self) -> list[OaApplicantCredentialSummary]:
        rows = self._connection.fetch_all(
            """
            select
                target_applicant_code,
                target_applicant_name,
                oa_username,
                credential_status,
                (credential_status = 'configured') as has_credential,
                enabled
            from app.oa_applicant_credentials
            where enabled = true
            order by target_applicant_name, target_applicant_code
            """,
            (),
        )
        return [self._summary_from_row(row) for row in rows]

    def save_credential(
        self,
        *,
        target_applicant_code: str,
        target_applicant_name: str,
        oa_username: str,
        password: str,
        actor_id: str,
    ) -> OaApplicantCredentialSummary:
        key = self._required_encryption_key()
        payload = {
            "target_applicant_code": target_applicant_code,
            "target_applicant_name": target_applicant_name,
            "oa_username": oa_username,
            "credential_status": "configured",
            "updated_by": actor_id,
        }
        self._connection.execute(
            """
            insert into app.oa_applicant_credentials(
                target_applicant_code,
                target_applicant_name,
                oa_username,
                encrypted_password,
                credential_status,
                enabled,
                updated_by,
                raw_payload,
                created_at,
                updated_at
            )
            values (
                %s,
                %s,
                %s,
                pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256, compress-algo=1'),
                'configured',
                true,
                %s,
                %s,
                now(),
                now()
            )
            on conflict (target_applicant_code) do update set
                target_applicant_name = excluded.target_applicant_name,
                oa_username = excluded.oa_username,
                encrypted_password = excluded.encrypted_password,
                credential_status = 'configured',
                enabled = true,
                updated_by = excluded.updated_by,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                target_applicant_code,
                target_applicant_name,
                oa_username,
                password,
                key,
                actor_id,
                _jsonb(payload),
            ),
        )
        return OaApplicantCredentialSummary(
            target_applicant_code=target_applicant_code,
            target_applicant_name=target_applicant_name,
            oa_username=oa_username,
            credential_status="configured",
            has_credential=True,
            enabled=True,
        )

    def delete_credential(self, *, target_applicant_code: str, actor_id: str) -> OaApplicantCredentialSummary:
        self._connection.execute(
            """
            insert into app.oa_applicant_credentials(
                target_applicant_code,
                target_applicant_name,
                oa_username,
                encrypted_password,
                credential_status,
                enabled,
                updated_by,
                raw_payload,
                created_at,
                updated_at
            )
            values (
                %s,
                '',
                '',
                null,
                'unconfigured',
                true,
                %s,
                %s,
                now(),
                now()
            )
            on conflict (target_applicant_code) do update set
                encrypted_password = null,
                credential_status = 'unconfigured',
                enabled = true,
                updated_by = excluded.updated_by,
                raw_payload = app.oa_applicant_credentials.raw_payload || excluded.raw_payload,
                updated_at = now()
            """,
            (
                target_applicant_code,
                actor_id,
                _jsonb({"target_applicant_code": target_applicant_code, "credential_status": "unconfigured"}),
            ),
        )
        row = self._connection.fetch_one(
            """
            select
                target_applicant_code,
                target_applicant_name,
                oa_username,
                credential_status,
                (credential_status = 'configured') as has_credential,
                enabled
            from app.oa_applicant_credentials
            where target_applicant_code = %s
            """,
            (target_applicant_code,),
        )
        if row:
            return self._summary_from_row(row)
        return OaApplicantCredentialSummary(
            target_applicant_code=target_applicant_code,
            target_applicant_name="",
            oa_username="",
            credential_status="unconfigured",
            has_credential=False,
            enabled=True,
        )

    def resolve_login_credential(self, target_applicant_code: str) -> OaApplicantLoginCredential | None:
        key = self._required_encryption_key()
        row = self._connection.fetch_one(
            """
            select
                target_applicant_code,
                oa_username,
                pgp_sym_decrypt(encrypted_password, %s) as password
            from app.oa_applicant_credentials
            where target_applicant_code = %s
              and credential_status = 'configured'
              and enabled = true
              and encrypted_password is not null
            """,
            (key, target_applicant_code),
        )
        if not row:
            return None
        password = str(row.get("password") or "").strip()
        oa_username = str(row.get("oa_username") or "").strip()
        if not password or not oa_username:
            return None
        return OaApplicantLoginCredential(
            target_applicant_code=str(row.get("target_applicant_code") or target_applicant_code).strip(),
            oa_username=oa_username,
            password=password,
        )

    def _required_encryption_key(self) -> str:
        key = str(self._encryption_key or os.getenv(OA_APPLICANT_CREDENTIAL_KEY_ENV) or "").strip()
        if not key:
            raise OaApplicantCredentialConfigurationError(
                f"{OA_APPLICANT_CREDENTIAL_KEY_ENV} is required to save or read OA applicant credentials."
            )
        return key

    @staticmethod
    def _summary_from_row(row: dict[str, Any]) -> OaApplicantCredentialSummary:
        status = str(row.get("credential_status") or "").strip() or "unconfigured"
        has_credential = bool(row.get("has_credential")) and status == "configured"
        return OaApplicantCredentialSummary(
            target_applicant_code=str(row.get("target_applicant_code") or "").strip(),
            target_applicant_name=str(row.get("target_applicant_name") or "").strip(),
            oa_username=str(row.get("oa_username") or "").strip(),
            credential_status="configured" if has_credential else "unconfigured",
            has_credential=has_credential,
            enabled=bool(row.get("enabled", True)),
        )
