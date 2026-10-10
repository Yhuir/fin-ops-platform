from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from unittest.mock import patch

from fin_ops_platform.services.oa_applicant_credentials import (
    OaApplicantCredentialConfigurationError,
    OaApplicantCredentialConflictError,
    OaApplicantCredentialSummary,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_applicant_credentials import PostgresOaApplicantCredentialRepository
from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url


def verified_summary():
    return OaApplicantCredentialSummary("credential-7", "陈秀云", "login-7", "configured", True,
                                        oa_user_id="7", remark="差旅", verified_at=datetime.now(UTC))


class RecordingConnection:
    def __init__(self):
        self.queries = []
        self.row = asdict(verified_summary())

    @contextmanager
    def transaction(self):
        yield self

    def fetch_one(self, sql, params=()):
        self.queries.append((sql, params))
        return self.row

    def fetch_all(self, sql, params=()):
        self.queries.append((sql, params))
        return [self.row]

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        return 1


class PostgresOaApplicantCredentialRepositoryTests(unittest.TestCase):
    def test_save_encrypts_with_parameters_update_has_no_upsert_and_stale_write_fails(self):
        connection = RecordingConnection()
        repo = PostgresOaApplicantCredentialRepository(connection, encryption_key="key")
        repo.save_credential(summary=verified_summary(), password=" secret ", actor_id="admin", expected_version=None)
        sql, params = connection.queries[-1]
        self.assertIn("pgp_sym_encrypt", sql)
        self.assertNotIn(" secret ", sql)
        self.assertIn(" secret ", params)
        connection.row = None
        with self.assertRaises(OaApplicantCredentialConflictError):
            repo.save_credential(summary=replace(verified_summary(), version=2), password="new", actor_id="admin", expected_version=1)
        sql, _ = connection.queries[-1]
        self.assertIn("and version = %s", sql)
        self.assertNotIn("on conflict", sql.lower())

    def test_list_is_nonsecret_and_delete_is_real_with_guard_under_lock(self):
        connection = RecordingConnection()
        guarded = []
        repo = PostgresOaApplicantCredentialRepository(connection, encryption_key="key",
                                                       delete_guard=lambda tx, code: guarded.append((tx, code)))
        self.assertEqual(repo.list_credentials()[0].oa_user_id, "7")
        sql, _ = connection.queries[-1]
        self.assertNotIn("encrypted_password", sql)
        self.assertNotIn("pgp_sym_decrypt", sql)
        repo.delete_credential(target_applicant_code="credential-7", actor_id="admin", expected_version=1)
        self.assertIn("for update", connection.queries[-2][0])
        self.assertIn("delete from", connection.queries[-1][0])
        self.assertEqual(guarded, [(connection, "credential-7")])

    def test_decrypt_preserves_password_whitespace_and_requires_verified_binding(self):
        connection = RecordingConnection()
        connection.row["password"] = " secret "
        repo = PostgresOaApplicantCredentialRepository(connection, encryption_key="key")
        self.assertEqual(repo.resolve_login_credential("credential-7").password, " secret ")
        sql, _ = connection.queries[-1]
        self.assertIn("verified_at is not null", sql)
        self.assertIn("oa_user_id is not null", sql)


class OaApplicantCredentialPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = require_postgres_test_database_url()
        apply_test_migrations(cls.dsn)
        cls.connection = PostgresConnection(PostgresSettings(database_url=cls.dsn, pool_enabled=False))

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def setUp(self):
        self.connection.execute("truncate app.oa_applicant_credentials")
        self.repo = PostgresOaApplicantCredentialRepository(self.connection, encryption_key="isolated-test-key")

    def test_encryption_unique_identity_cas_true_delete_and_no_resurrection(self):
        original = verified_summary()
        self.repo.save_credential(summary=original, password=" secret ", actor_id="test", expected_version=None)
        self.assertEqual(self.repo.resolve_login_credential(original.target_applicant_code).password, " secret ")
        stored = self.connection.fetch_one("select encrypted_password from app.oa_applicant_credentials")["encrypted_password"]
        self.assertNotIn(b"secret", bytes(stored))
        with self.assertRaises(OaApplicantCredentialConflictError):
            self.repo.save_credential(summary=replace(original, target_applicant_code="duplicate"), password="bad",
                                      actor_id="test", expected_version=None)
        updated = self.repo.save_credential(summary=replace(original, version=2, remark="new"), password="new",
                                             actor_id="test", expected_version=1)
        self.assertEqual(updated.version, 2)
        with self.assertRaises(OaApplicantCredentialConflictError):
            self.repo.delete_credential(target_applicant_code=original.target_applicant_code, actor_id="test", expected_version=1)
        self.repo.delete_credential(target_applicant_code=original.target_applicant_code, actor_id="test", expected_version=2)
        with self.assertRaises(OaApplicantCredentialConflictError):
            self.repo.save_credential(summary=replace(original, version=3), password="late", actor_id="test", expected_version=2)
        self.assertEqual(self.repo.list_credentials(), [])

    def test_concurrent_duplicate_create_has_one_winner(self):
        original = verified_summary()
        def create(code):
            try:
                self.repo.save_credential(summary=replace(original, target_applicant_code=code), password="test",
                                          actor_id="test", expected_version=None)
                return "saved"
            except OaApplicantCredentialConflictError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, ["first", "second"]))
        self.assertCountEqual(results, ["saved", "conflict"])
        self.assertEqual(len(self.repo.list_credentials()), 1)

    def test_preserve_updates_and_legacy_verification_keep_exact_ciphertext(self):
        original = verified_summary()
        self.repo.save_credential(summary=original, password=" secret ", actor_id="test", expected_version=None)
        stored = bytes(self.connection.fetch_one("select encrypted_password from app.oa_applicant_credentials")["encrypted_password"])
        no_key = PostgresOaApplicantCredentialRepository(self.connection)
        with patch.dict("os.environ", {"FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY": ""}):
            saved = no_key.save_credential(summary=replace(original, version=2, remark="new", enabled=False),
                password=None, actor_id="test", expected_version=1)
        self.assertFalse(saved.enabled)
        self.assertEqual(saved.verified_at, original.verified_at)
        self.assertEqual(bytes(self.connection.fetch_one("select encrypted_password from app.oa_applicant_credentials")["encrypted_password"]), stored)
        self.connection.execute("update app.oa_applicant_credentials set verified_at=null, oa_user_id=null, enabled=true")
        self.assertIsNone(self.repo.resolve_login_credential(original.target_applicant_code))
        self.assertEqual(self.repo.read_password_for_verification(original.target_applicant_code, 2).password, " secret ")
        with self.assertRaises(OaApplicantCredentialConflictError):
            self.repo.read_password_for_verification(original.target_applicant_code, 1)
        self.repo.save_credential(summary=replace(original, version=3), password=None, actor_id="test", expected_version=2)
        self.assertEqual(bytes(self.connection.fetch_one("select encrypted_password from app.oa_applicant_credentials")["encrypted_password"]), stored)
        self.assertEqual(self.repo.resolve_login_credential(original.target_applicant_code).password, " secret ")

    def test_legacy_service_verification_then_metadata_edit_and_runtime_credential_read(self):
        from tests.test_oa_applicant_credentials_service import credential_service
        original = replace(verified_summary(), oa_user_id=None, verified_at=None)
        self.repo.save_credential(summary=original, password=" saved password ", actor_id="test", expected_version=None)
        calls = []
        service = credential_service(self.repo, login=lambda *args: calls.append(args) or "token")
        self.assertEqual(service.applicant_options(), [])
        self.assertIsNone(service.resolve_login_credential(original.target_applicant_code))
        result = service.save_credential(oa_user_id="7", remark=original.remark, actor_id="admin",
            can_admin_access=True, target_applicant_code=original.target_applicant_code, expected_version=1)
        self.assertEqual(calls, [("login-7", " saved password ")])
        self.assertEqual(service.applicant_options(), [{"code": original.target_applicant_code, "name": "陈秀云", "remark": "差旅"}])
        service._directory = service._login_client = service._identity_resolver = None
        updated = service.save_credential(oa_user_id="7", remark="updated", actor_id="admin", can_admin_access=True,
            target_applicant_code=original.target_applicant_code, expected_version=2)
        self.assertEqual(updated["verifiedAt"], result["verifiedAt"])
        self.assertEqual(updated["version"], 3)
        self.assertEqual(service.resolve_login_credential(original.target_applicant_code).password, " saved password ")
        self.assertEqual(calls, [("login-7", " saved password ")])

    def test_wrong_or_missing_key_cannot_verify_saved_password_and_changes_nothing(self):
        original = verified_summary()
        self.repo.save_credential(summary=original, password="saved", actor_id="test", expected_version=None)
        wrong_key = PostgresOaApplicantCredentialRepository(self.connection, encryption_key="wrong-key")
        with self.assertRaises(OaApplicantCredentialConfigurationError):
            wrong_key.read_password_for_verification(original.target_applicant_code, 1)
        no_key = PostgresOaApplicantCredentialRepository(self.connection)
        with patch.dict("os.environ", {"FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY": ""}):
            with self.assertRaises(OaApplicantCredentialConfigurationError):
                no_key.read_password_for_verification(original.target_applicant_code, 1)
        self.assertEqual(self.repo.get_credential(original.target_applicant_code), original)

    def test_legacy_not_decrypted_and_failed_delete_guard_rolls_back(self):
        original = verified_summary()
        self.repo.save_credential(summary=original, password="test", actor_id="test", expected_version=None)
        def deny(transaction, code):
            transaction.execute("update app.oa_applicant_credentials set remark='must rollback'")
            raise OaApplicantCredentialConflictError("OA 请求正在发送")
        guarded = PostgresOaApplicantCredentialRepository(self.connection, encryption_key="isolated-test-key", delete_guard=deny)
        with self.assertRaises(OaApplicantCredentialConflictError):
            guarded.delete_credential(target_applicant_code=original.target_applicant_code, actor_id="test", expected_version=1)
        self.assertEqual(self.repo.list_credentials()[0].remark, "差旅")
        self.connection.execute("update app.oa_applicant_credentials set verified_at=null, oa_user_id=null")
        self.assertIsNone(self.repo.resolve_login_credential(original.target_applicant_code))
