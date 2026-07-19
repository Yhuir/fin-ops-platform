from __future__ import annotations

from contextlib import contextmanager
from io import StringIO
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import settings_normalization_ops


class FakeConnection:
    def __init__(self) -> None:
        self.transaction_entries = 0

    @contextmanager
    def transaction(self):
        self.transaction_entries += 1
        yield self


class FakeRepository:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.saves: list[tuple[dict[str, object], object]] = []

    def load_settings(self, settings_key: str) -> dict[str, object]:
        assert settings_key == "app_settings"
        return dict(self.payload)

    def save_app_settings_in_transaction(self, payload: dict[str, object], *, transaction: object) -> None:
        self.saves.append((dict(payload), transaction))


class SettingsNormalizationOpsTests(unittest.TestCase):
    def test_dry_run_reports_only_changed_keys_and_hashes_without_writing(self) -> None:
        connection = FakeConnection()
        repository = FakeRepository({"allowed_usernames": [" user ", "user"]})
        stdout = StringIO()

        with (
            patch.object(settings_normalization_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(settings_normalization_ops, "PostgresConnection", return_value=connection),
            patch.object(settings_normalization_ops, "PostgresOpsTaxEtcRepository", return_value=repository),
        ):
            exit_code = settings_normalization_ops.main(["--dry-run"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertTrue(payload["changed"])
        self.assertIn("allowed_usernames", payload["changed_keys"])
        self.assertNotIn("normalized_payload", payload)
        self.assertEqual(connection.transaction_entries, 0)
        self.assertEqual(repository.saves, [])

    def test_execute_writes_canonical_payload_once_in_one_transaction(self) -> None:
        connection = FakeConnection()
        repository = FakeRepository({"bank_flow_rule_batch_tag_rules": {"rules": None}})
        stdout = StringIO()

        with (
            patch.object(settings_normalization_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(settings_normalization_ops, "PostgresConnection", return_value=connection),
            patch.object(settings_normalization_ops, "PostgresOpsTaxEtcRepository", return_value=repository),
        ):
            exit_code = settings_normalization_ops.main(["--execute"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "execute")
        self.assertTrue(payload["written"])
        self.assertEqual(connection.transaction_entries, 1)
        self.assertEqual(len(repository.saves), 1)
        saved, transaction = repository.saves[0]
        self.assertIs(transaction, connection)
        self.assertEqual(
            saved["bank_flow_rule_batch_tag_rules"],
            {"version": 1, "requirements_by_tag_code": {}},
        )


if __name__ == "__main__":
    unittest.main()
