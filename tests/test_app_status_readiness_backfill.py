from __future__ import annotations

import io
import json
import unittest

from fin_ops_platform.tools import app_status_readiness_backfill


class FakeConnection:
    def __init__(self, *, has_fact: bool = True) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.has_fact = has_fact

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_relation_scopes" in normalized and self.has_fact:
            return {
                "scope_key": "2026-05",
                "status": "fresh",
                "row_count": 0,
                "schema_version": "",
                "source_versions": {"workbench_relation_source_version": 8},
                "generated_at": "2026-06-04T10:00:00+00:00",
                "last_error": None,
            }
        if "from read_model.app_status_readiness" in normalized:
            raise AssertionError("dry-run should not inspect app_status_readiness as proof")
        return None

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from read_model.app_status_readiness" in normalized:
            return []
        return []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((sql, params))
        return 1


class AppStatusReadinessBackfillTests(unittest.TestCase):
    def test_dry_run_reports_real_fresh_without_writing(self) -> None:
        connection = FakeConnection()
        stdout = io.StringIO()

        exit_code = app_status_readiness_backfill.main(
            ["--dry-run", "--read-model-key", "workbench_relation"],
            connection=connection,
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["results"][0]["read_model_key"], "workbench_relation")
        self.assertEqual(payload["results"][0]["status"], "fresh")
        self.assertEqual(payload["results"][0]["row_count"], 0)
        self.assertEqual(connection.executed, [])

    def test_apply_writes_only_computed_result(self) -> None:
        connection = FakeConnection()
        stdout = io.StringIO()

        exit_code = app_status_readiness_backfill.main(
            ["--apply", "--read-model-key", "workbench_relation"],
            connection=connection,
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "apply")
        self.assertEqual(payload["results"][0]["status"], "fresh")
        self.assertEqual(len(connection.executed), 1)
        self.assertIn("insert into read_model.app_status_readiness", connection.executed[0][0])

    def test_missing_projection_fact_is_missing_not_fresh(self) -> None:
        stdout = io.StringIO()

        exit_code = app_status_readiness_backfill.main(
            ["--dry-run", "--read-model-key", "workbench_relation"],
            connection=FakeConnection(has_fact=False),
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["results"][0]["status"], "missing")
        self.assertIn("no fresh projection fact", payload["results"][0]["last_error"])


if __name__ == "__main__":
    unittest.main()
