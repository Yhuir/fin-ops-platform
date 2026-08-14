from __future__ import annotations

from contextlib import contextmanager
import unittest

from fin_ops_platform.services.page_audit_registry import page_audit_registration
from fin_ops_platform.services.postgres_repositories.audit_report import AuditSnapshot
from fin_ops_platform.services.postgres_repositories.cost_statistics_page_audit import (
    audit_cost_statistics_page,
)


class _Connection:
    def __init__(self, issues: list[dict[str, object]] | None = None) -> None:
        self.issues = list(issues or [])
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_one_calls: list[str] = []
        self.fetch_all_calls: list[str] = []

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((sql, params))
        return 0

    def fetch_one(
        self,
        sql: str,
        _params: tuple[object, ...] = (),
    ) -> dict[str, object]:
        self.fetch_one_calls.append(sql)
        return {
            "source_fact_count": 12,
            "active_relation_count": 3,
        }

    def fetch_all(
        self,
        sql: str,
        _params: tuple[object, ...] = (),
    ) -> list[dict[str, object]]:
        self.fetch_all_calls.append(sql)
        return list(self.issues)


class CostStatisticsPageAuditTests(unittest.TestCase):
    def test_clean_direct_canonical_audit_has_no_read_model_or_queue_contract(self) -> None:
        connection = _Connection()

        report = audit_cost_statistics_page(connection)

        self.assertEqual(report["mode"], "page-business-canonical-read-audit")
        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(
            report["audit_status"],
            {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        )
        self.assertEqual(report["summary"]["source_fact_count"], 12)
        self.assertEqual(report["summary"]["active_relation_count"], 3)
        self.assertEqual(report["audit_contract"]["derived_tables"], [])
        self.assertEqual(report["audit_contract"]["scope_types"], [])
        self.assertEqual(report["audit_contract"]["event_types"], [])
        self.assertEqual(
            report["audit_contract"]["snapshot_consistency"],
            "repeatable_read_read_only",
        )
        self.assertEqual(len(connection.fetch_one_calls), 1)
        self.assertEqual(len(connection.fetch_all_calls), 1)
        self.assertTrue(
            all(
                "read_model.cost_statistics" not in sql
                and "job.outbox_events" not in sql
                and "job.read_model_dirty_scopes" not in sql
                for sql in [*connection.fetch_one_calls, *connection.fetch_all_calls]
            )
        )

    def test_missing_canonical_relation_member_fails_integrity(self) -> None:
        connection = _Connection(
            [
                {
                    "code": "cost_statistics_relation_member_missing",
                    "subject_id": "case-1",
                    "details": {"row_id": "bank-missing", "row_type": "bank"},
                }
            ]
        )

        report = audit_cost_statistics_page(connection)

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["issues"][0]["code"],
            "cost_statistics_relation_member_missing",
        )

    def test_explicit_caller_snapshot_is_reused(self) -> None:
        connection = _Connection()
        snapshot = AuditSnapshot(
            connection=connection,
            consistency="caller_snapshot",
            database_snapshot=True,
        )

        report = audit_cost_statistics_page(
            connection,
            audit_snapshot=snapshot,
        )

        self.assertEqual(
            report["audit_contract"]["snapshot_consistency"],
            "caller_snapshot",
        )
        self.assertFalse(connection.executed)

    def test_registry_declares_cost_as_direct_canonical_without_dependencies(self) -> None:
        registration = page_audit_registration("cost-statistics")

        self.assertEqual(registration.executor, "cost_statistics")


if __name__ == "__main__":
    unittest.main()
