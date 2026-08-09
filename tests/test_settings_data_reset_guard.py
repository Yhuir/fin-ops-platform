from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.postgres_repositories.settings_data_reset import (
    PostgresSettingsDataResetRepository,
    SettingsDataResetImpactChanged,
    SettingsDataResetRecoveryEvidenceInvalid,
)
from fin_ops_platform.tools.settings_data_reset_restore_point import register


class _Connection:
    def __init__(self) -> None:
        self.signature = "impact-a"
        self.receipt_valid = True
        self.executed: list[str] = []

    def execute(self, statement: str, _params=None) -> int:
        self.executed.append(" ".join(statement.split()))
        return 0

    def fetch_one(self, statement: str, _params=None):
        normalized = " ".join(statement.split()).lower()
        if "as impact_target" in normalized:
            return {"count": 1, "signature": self.signature}
        if "consumed_by_job_id = %s" in normalized:
            return {"receipt_id": "receipt-1"} if self.receipt_valid else None
        if "consumed_by_job_id is null" in normalized:
            return None
        return {"count": 0}


class SettingsDataResetGuardTests(unittest.TestCase):
    def test_guard_blocks_when_impact_changes_after_preview(self) -> None:
        connection = _Connection()
        repository = PostgresSettingsDataResetRepository(connection)
        expected = repository.preview("reset_bank_transactions")["impact_fingerprint"]
        connection.signature = "impact-b"

        with self.assertRaises(SettingsDataResetImpactChanged):
            repository._validate_guard(
                "reset_bank_transactions",
                expected_impact_fingerprint=expected,
                recovery_receipt_id="00000000-0000-0000-0000-000000000001",
                job_id="job-1",
            )
        self.assertTrue(connection.executed[0].startswith("lock table"))

    def test_restore_point_registration_requires_audit_identity(self) -> None:
        with TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest_path.write_text(json.dumps({"status": "created", "format": "postgresql_custom"}))

            with self.assertRaises(ValueError):
                register(
                    object(),
                    action="reset_bank_transactions",
                    manifest_path=manifest_path,
                    expected_impact_fingerprint="a" * 64,
                    created_by="",
                )

    def test_guard_blocks_missing_or_expired_recovery_receipt(self) -> None:
        connection = _Connection()
        repository = PostgresSettingsDataResetRepository(connection)
        expected = repository.preview("reset_bank_transactions")["impact_fingerprint"]
        connection.receipt_valid = False

        with self.assertRaises(SettingsDataResetRecoveryEvidenceInvalid):
            repository._validate_guard(
                "reset_bank_transactions",
                expected_impact_fingerprint=expected,
                recovery_receipt_id="00000000-0000-0000-0000-000000000001",
                job_id="job-1",
            )


if __name__ == "__main__":
    unittest.main()
