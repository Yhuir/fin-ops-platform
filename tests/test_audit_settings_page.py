from __future__ import annotations

import unittest

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.postgres_repositories import settings_page_audit


class FakeConnection:
    def __init__(self) -> None:
        payload = AppSettingsService._normalize_settings(
            AppSettingsService._normalize_settings({}, validate_pending_invoice_tag_groups=False),
            validate_pending_invoice_tag_groups=False,
        )
        self.settings = [
            {
                "settings_key": "app_settings",
                "version": 1,
                "settings_payload": payload,
                "raw_payload": {"normalized_payload": payload},
            }
        ]
        self.credentials: list[dict[str, object]] = []
        self.jobs: list[dict[str, object]] = []
        self.executed: list[str] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        if "from app.app_settings" in sql:
            return [dict(row) for row in self.settings]
        if "from app.oa_applicant_credentials" in sql:
            return [dict(row) for row in self.credentials]
        if "from job.background_jobs" in sql:
            return [dict(row) for row in self.jobs]
        raise AssertionError(sql)

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append(sql)
        raise AssertionError("Settings Audit must be read-only")


class SettingsPageAuditTests(unittest.TestCase):
    def test_clean_settings_contract_passes_without_writes(self) -> None:
        connection = FakeConnection()

        report = settings_page_audit.audit_settings_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(
            report["audit_status"],
            {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        )
        self.assertEqual(connection.executed, [])

    def test_missing_settings_singleton_is_blocking(self) -> None:
        connection = FakeConnection()
        connection.settings = []

        report = settings_page_audit.audit_settings_page(connection)

        self.assertIn("settings_singleton_count_mismatch", report["summary"]["issue_sample_counts_by_code"])

    def test_non_normalized_settings_are_blocking(self) -> None:
        connection = FakeConnection()
        payload = connection.settings[0]["settings_payload"]
        payload["allowed_usernames"] = ["duplicate", "duplicate"]
        connection.settings[0]["raw_payload"] = {"normalized_payload": dict(payload)}

        report = settings_page_audit.audit_settings_page(connection)

        self.assertIn("settings_payload_not_normalized", report["summary"]["issue_sample_counts_by_code"])

    def test_secret_value_is_never_returned(self) -> None:
        connection = FakeConnection()
        payload = connection.settings[0]["settings_payload"]
        payload["oa_password"] = "do-not-leak-this"
        connection.settings[0]["raw_payload"] = {"normalized_payload": dict(payload)}

        report = settings_page_audit.audit_settings_page(connection)

        self.assertIn("settings_payload_contains_secret_field", report["summary"]["issue_sample_counts_by_code"])
        self.assertNotIn("do-not-leak-this", repr(report))

    def test_credential_status_is_proven_without_selecting_secret(self) -> None:
        connection = FakeConnection()
        connection.credentials = [
            {
                "target_applicant_code": "OA-1",
                "target_applicant_name": "申请人",
                "oa_username": "oa-user",
                "credential_status": "configured",
                "has_credential": False,
                "enabled": True,
            }
        ]

        report = settings_page_audit.audit_settings_page(connection)

        self.assertIn("settings_credential_status_mismatch", report["summary"]["issue_sample_counts_by_code"])
        self.assertNotIn("pgp_sym_decrypt", settings_page_audit._CREDENTIAL_SQL)
        self.assertNotIn("select encrypted_password", settings_page_audit._CREDENTIAL_SQL)

    def test_active_reset_job_blocks_freshness_and_queue(self) -> None:
        connection = FakeConnection()
        connection.jobs = [
            {
                "job_id": "reset-1",
                "status": "running",
                "normalized_payload": {"job_id": "reset-1", "status": "running"},
            }
        ]

        report = settings_page_audit.audit_settings_page(connection)

        self.assertEqual(report["audit_status"]["integrity"], "pass")
        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "backlog")


if __name__ == "__main__":
    unittest.main()
