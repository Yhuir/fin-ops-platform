from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import json
import unittest

from fin_ops_platform.services.state_store_diff import diff_state_snapshots, redact_diff_payload


class StateStoreDiffTests(unittest.TestCase):
    def test_equal_snapshots_match_and_are_json_serializable(self) -> None:
        result = diff_state_snapshots(
            {"records": {"a": {"status": "ok"}}},
            {"records": {"a": {"status": "ok"}}},
            domain="jobs",
        )

        self.assertTrue(result.matched)
        self.assertEqual(result.domain, "jobs")
        self.assertEqual(result.primary_count, 1)
        self.assertEqual(result.shadow_count, 1)
        self.assertEqual(result.mismatch_count, 0)
        json.dumps(asdict(result), ensure_ascii=False)

    def test_missing_values_use_stable_paths(self) -> None:
        result = diff_state_snapshots(
            {"imports": {"batches": {"batch_1": {"status": "done"}}}},
            {"imports": {"batches": {}}},
            domain="imports",
        )

        self.assertFalse(result.matched)
        self.assertEqual(result.mismatches[0]["path"], "imports.batches.batch_1")
        self.assertEqual(result.mismatches[0]["kind"], "missing_in_shadow")

    def test_mismatched_scalar_uses_stable_path(self) -> None:
        result = diff_state_snapshots(
            {"imports": {"batches": {"batch_1": {"status": "done"}}}},
            {"imports": {"batches": {"batch_1": {"status": "failed"}}}},
        )

        self.assertEqual(result.mismatches[0]["path"], "imports.batches.batch_1.status")
        self.assertEqual(result.mismatches[0]["primary"], "done")
        self.assertEqual(result.mismatches[0]["shadow"], "failed")

    def test_decimal_and_json_string_scalars_are_equivalent(self) -> None:
        result = diff_state_snapshots(
            {"amount_check": {"invoice_total": Decimal("12.30"), "bank_total": Decimal("0")}},
            {"amount_check": {"invoice_total": "12.30", "bank_total": "0"}},
        )

        self.assertTrue(result.matched)

    def test_default_ignored_paths_cover_runtime_metadata(self) -> None:
        primary = {
            "row": {
                "row_id": "row-1",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "raw_payload": {"migration_metadata": {"postgres_uuid": "a"}},
                "status": "ok",
            }
        }
        shadow = {
            "row": {
                "row_id": "row-1",
                "created_at": "2026-01-02T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
                "raw_payload": {"migration_metadata": {"postgres_uuid": "b"}},
                "status": "ok",
            }
        }

        self.assertTrue(diff_state_snapshots(primary, shadow).matched)

    def test_custom_ignored_paths(self) -> None:
        result = diff_state_snapshots(
            {"records": {"a": {"volatile": "primary", "status": "ok"}}},
            {"records": {"a": {"volatile": "shadow", "status": "ok"}}},
            ignored_paths={"records.a.volatile"},
        )

        self.assertTrue(result.matched)

    def test_max_mismatches_limits_output(self) -> None:
        result = diff_state_snapshots(
            {"rows": [{"value": 1}, {"value": 2}, {"value": 3}]},
            {"rows": [{"value": 10}, {"value": 20}, {"value": 30}]},
            max_mismatches=2,
        )

        self.assertEqual(result.mismatch_count, 2)
        self.assertEqual([mismatch["path"] for mismatch in result.mismatches], ["rows[0].value", "rows[1].value"])

    def test_redaction_removes_sensitive_keys_and_full_uris(self) -> None:
        payload = {
            "password": "secret-password",
            "token": "secret-token",
            "nested": {
                "database_url": "postgresql://user:pass@db.example/fin_ops",
                "message": "failed mongodb://user:pass@mongo.example/app",
            },
            "safe": "visible",
        }

        redacted = redact_diff_payload(payload)
        encoded = json.dumps(redacted)
        self.assertNotIn("password", redacted)
        self.assertNotIn("token", redacted)
        self.assertNotIn("database_url", redacted["nested"])
        self.assertIn("<redacted-uri>", redacted["nested"]["message"])
        self.assertIn("visible", encoded)
        self.assertNotIn("secret-password", encoded)
        self.assertNotIn("user:pass", encoded)
        self.assertNotIn("db.example", encoded)

    def test_diff_mismatches_are_redacted(self) -> None:
        result = diff_state_snapshots(
            {"config": {"database_url": "postgresql://user:pass@primary-db.example/app"}},
            {"config": {"database_url": "postgresql://user:pass@shadow-db.example/app"}},
        )

        encoded = json.dumps(result.to_dict())
        self.assertTrue(result.redacted)
        self.assertNotIn("user:pass", encoded)
        self.assertNotIn("primary-db.example", encoded)
        self.assertNotIn("shadow-db.example", encoded)


if __name__ == "__main__":
    unittest.main()
