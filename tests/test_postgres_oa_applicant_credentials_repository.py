from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.oa_applicant_credentials import (
    PostgresOaApplicantCredentialRepository,
)


class RecordingConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetches: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_rows: list[dict[str, object]] = []
        self.fetch_one_row: dict[str, object] | None = None

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((" ".join(sql.split()), params))
        return 1

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetches.append((" ".join(sql.split()), params))
        return list(self.fetch_all_rows)

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.fetches.append((" ".join(sql.split()), params))
        return self.fetch_one_row


class PostgresOaApplicantCredentialRepositoryTests(unittest.TestCase):
    def test_save_uses_pgcrypto_encryption_and_never_embeds_plain_password_in_sql(self) -> None:
        connection = RecordingConnection()
        repository = PostgresOaApplicantCredentialRepository(connection, encryption_key="test-key")

        repository.save_credential(
            target_applicant_code="chen_xiuyun",
            target_applicant_name="陈秀云",
            oa_username="chen_xiuyun",
            password="correct-password",
            actor_id="YNSYLP005",
        )

        sql = connection.executed[0][0].lower()
        self.assertIn("app.oa_applicant_credentials", sql)
        self.assertIn("pgp_sym_encrypt", sql)
        self.assertNotIn("correct-password", sql)
        self.assertIn("test-key", connection.executed[0][1])

    def test_list_credentials_does_not_decrypt_or_select_password_material(self) -> None:
        connection = RecordingConnection()
        connection.fetch_all_rows = [
            {
                "target_applicant_code": "chen_xiuyun",
                "target_applicant_name": "陈秀云",
                "oa_username": "chen_xiuyun",
                "credential_status": "configured",
                "has_credential": True,
                "enabled": True,
            }
        ]
        repository = PostgresOaApplicantCredentialRepository(connection, encryption_key="test-key")

        credentials = repository.list_credentials()

        sql = connection.fetches[0][0].lower()
        self.assertEqual(credentials[0].target_applicant_code, "chen_xiuyun")
        self.assertTrue(credentials[0].has_credential)
        self.assertNotIn("pgp_sym_decrypt", sql)
        self.assertNotIn("encrypted_password", sql)

    def test_resolve_login_credential_uses_pgcrypto_decryption_only_for_internal_use(self) -> None:
        connection = RecordingConnection()
        connection.fetch_one_row = {
            "target_applicant_code": "chen_xiuyun",
            "oa_username": "chen_xiuyun",
            "password": "correct-password",
        }
        repository = PostgresOaApplicantCredentialRepository(connection, encryption_key="test-key")

        credential = repository.resolve_login_credential("chen_xiuyun")

        sql = connection.fetches[0][0].lower()
        self.assertIsNotNone(credential)
        self.assertEqual(credential.oa_username, "chen_xiuyun")
        self.assertEqual(credential.password, "correct-password")
        self.assertIn("pgp_sym_decrypt", sql)


if __name__ == "__main__":
    unittest.main()
