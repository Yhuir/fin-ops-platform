from __future__ import annotations

from io import StringIO
import json
import unittest

from fin_ops_platform.tools import workbench_matching_scope_retry_ops


class FakeRepository:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = dict(row)
        self.mark_calls: list[dict[str, object]] = []

    def list_workbench_matching_dirty_scopes(self, *, tenant_id: str) -> list[dict[str, object]]:
        self.row["tenant_id"] = tenant_id
        return [dict(self.row)]

    def retry_failed_workbench_matching_scope(self, **kwargs: object) -> bool:
        self.mark_calls.append(dict(kwargs))
        return True


def _failed_row() -> dict[str, object]:
    return {
        "scope_month": "2025-10",
        "status": "failed",
        "attempt_count": 8,
        "request_id": "workbench-dirty:2025-10",
        "last_error": "canceling statement due to statement timeout",
        "source_versions": {"workbench_formal_relation_rule_version": "rules-v1"},
    }


class WorkbenchMatchingScopeRetryOpsTests(unittest.TestCase):
    def test_dry_run_reports_stable_fingerprint_without_writing(self) -> None:
        repository = FakeRepository(_failed_row())
        stdout = StringIO()

        exit_code = workbench_matching_scope_retry_ops.main(
            ["--scope-month", "2025-10", "--dry-run"],
            repository=repository,
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "dry_run")
        self.assertEqual(payload["scope_month"], "2025-10")
        self.assertEqual(payload["status_before"], "failed")
        self.assertEqual(len(payload["fingerprint"]), 64)
        self.assertFalse(payload["written"])
        self.assertEqual(repository.mark_calls, [])

    def test_execute_requeues_exact_failed_scope_after_fingerprint_check(self) -> None:
        repository = FakeRepository(_failed_row())
        dry_run_stdout = StringIO()
        workbench_matching_scope_retry_ops.main(
            ["--scope-month", "2025-10", "--dry-run"],
            repository=repository,
            stdout=dry_run_stdout,
        )
        fingerprint = json.loads(dry_run_stdout.getvalue())["fingerprint"]
        stdout = StringIO()

        exit_code = workbench_matching_scope_retry_ops.main(
            [
                "--scope-month",
                "2025-10",
                "--execute",
                "--expected-fingerprint",
                fingerprint,
            ],
            repository=repository,
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["written"])
        self.assertEqual(
            repository.mark_calls,
            [
                {
                    "tenant_id": "default",
                    "scope_month": "2025-10",
                    "reason": "operator_retry_failed_scope",
                    "expected_attempt_count": 8,
                    "expected_request_id": "workbench-dirty:2025-10",
                    "expected_last_error": "canceling statement due to statement timeout",
                    "expected_source_versions": {"workbench_formal_relation_rule_version": "rules-v1"},
                }
            ],
        )

    def test_execute_refuses_fingerprint_drift(self) -> None:
        repository = FakeRepository(_failed_row())

        with self.assertRaisesRegex(RuntimeError, "changed after dry-run"):
            workbench_matching_scope_retry_ops.main(
                [
                    "--scope-month",
                    "2025-10",
                    "--execute",
                    "--expected-fingerprint",
                    "0" * 64,
                ],
                repository=repository,
                stdout=StringIO(),
            )

        self.assertEqual(repository.mark_calls, [])

    def test_non_failed_scope_is_not_requeued(self) -> None:
        repository = FakeRepository({**_failed_row(), "status": "completed"})

        with self.assertRaisesRegex(RuntimeError, "is not failed"):
            workbench_matching_scope_retry_ops.main(
                ["--scope-month", "2025-10", "--dry-run"],
                repository=repository,
                stdout=StringIO(),
            )

        self.assertEqual(repository.mark_calls, [])


if __name__ == "__main__":
    unittest.main()
