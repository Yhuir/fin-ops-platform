"""Run exact previous-release credential writes against the candidate schema.

Apply the candidate migrations to an isolated database first, then set
FIN_OPS_SCHEMA_COMPAT_PREVIOUS_SRC and select its backend/src with PYTHONPATH.
This probe does not contact OA or load production credentials.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from uuid import uuid4


class OaCredentialsSchemaCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous_src = os.environ.get("FIN_OPS_SCHEMA_COMPAT_PREVIOUS_SRC")
        if not previous_src:
            raise unittest.SkipTest("Requires explicit exact previous-release source and candidate test schema")
        from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
        from fin_ops_platform.services.postgres_repositories import oa_applicant_credentials

        expected = Path(previous_src).resolve() / "backend/src"
        if not Path(oa_applicant_credentials.__file__).resolve().is_relative_to(expected):
            raise RuntimeError("Compatibility probe must import the exact previous release")
        cls.connection = PostgresConnection(PostgresSettings(os.environ["FIN_OPS_TEST_DATABASE_URL"], pool_enabled=False))
        cls.addClassCleanup(cls.connection.close)
        name = cls.connection.fetch_one("select current_database() as name")["name"]
        if not name.startswith(("fin_ops_test_oa_compat_", "fin_ops_cash_test_")):
            raise RuntimeError("Compatibility writes require an isolated OA or cash compatibility test database")
        cls.repository = oa_applicant_credentials.PostgresOaApplicantCredentialRepository(
            cls.connection, encryption_key="synthetic-compatibility-key")

    def setUp(self):
        self.code = "oa-compat-" + uuid4().hex
        self.addCleanup(self.connection.execute,
                        "delete from app.oa_applicant_credentials where target_applicant_code=%s", (self.code,))

    def save(self, password="synthetic-password", name="Synthetic applicant"):
        return self.repository.save_credential(target_applicant_code=self.code,
            target_applicant_name=name, oa_username="synthetic-login", password=password,
            actor_id="synthetic-compatibility-test")

    def mark_verified(self):
        self.connection.execute("""update app.oa_applicant_credentials
            set oa_user_id=%s, remark='Synthetic remark', verified_at=now(), version=2
            where target_applicant_code=%s""", ("user-" + self.code, self.code))

    def test_previous_create_update_and_read_with_new_column_defaults(self):
        self.save()
        row = self.connection.fetch_one("""select oa_user_id, remark, verified_at, version
            from app.oa_applicant_credentials where target_applicant_code=%s""", (self.code,))
        self.assertEqual(row, {"oa_user_id": None, "remark": "", "verified_at": None, "version": 1})
        self.mark_verified()
        self.save(password="updated-synthetic-password", name="Updated synthetic applicant")
        self.assertEqual(self.repository.resolve_login_credential(self.code).password, "updated-synthetic-password")
        summary = next(item for item in self.repository.list_credentials() if item.target_applicant_code == self.code)
        self.assertEqual(summary.target_applicant_name, "Updated synthetic applicant")
        row = self.connection.fetch_one("""select oa_user_id, remark, verified_at, version
            from app.oa_applicant_credentials where target_applicant_code=%s""", (self.code,))
        self.assertEqual(row["oa_user_id"], "user-" + self.code)
        self.assertEqual(row["remark"], "Synthetic remark")
        self.assertIsNotNone(row["verified_at"])
        self.assertEqual(row["version"], 2)

    def test_previous_delete_clears_verified_record_without_constraint_failure(self):
        self.save()
        self.mark_verified()
        summary = self.repository.delete_credential(target_applicant_code=self.code,
                                                   actor_id="synthetic-compatibility-test")
        self.assertFalse(summary.has_credential)
        self.assertIsNone(self.repository.resolve_login_credential(self.code))
        row = self.connection.fetch_one("""select credential_status, encrypted_password, oa_user_id
            from app.oa_applicant_credentials where target_applicant_code=%s""", (self.code,))
        self.assertEqual(row["credential_status"], "unconfigured")
        self.assertIsNone(row["encrypted_password"])
        self.assertEqual(row["oa_user_id"], "user-" + self.code)

    def test_previous_delete_missing_record_and_repeat_stay_valid(self):
        for _ in range(2):
            summary = self.repository.delete_credential(target_applicant_code=self.code,
                                                       actor_id="synthetic-compatibility-test")
            self.assertFalse(summary.has_credential)
        self.assertEqual(self.connection.fetch_one("""select count(*) as n from app.oa_applicant_credentials
            where target_applicant_code=%s""", (self.code,))["n"], 1)


if __name__ == "__main__":
    unittest.main()
