from __future__ import annotations

import json
import re
from io import StringIO
import unittest
from unittest.mock import patch

from fin_ops_platform.services.postgres_connection import PostgresConfigurationError
from fin_ops_platform.tools import workbench_compute_evidence


MUTATING_SQL_RE = re.compile(r"\b(insert|update|delete|create|drop|alter|truncate|grant|revoke)\b", re.IGNORECASE)


class FakeWorkbenchComputeEvidenceConnection:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self._assert_read_only(sql)
        normalized = self._record(self.fetch_all_calls, sql, params)
        if self.empty:
            return []
        if "from job.workbench_matching_dirty_scopes" in normalized and "group by status" in normalized:
            return [
                {
                    "status": "completed",
                    "scope_count": 12,
                    "p50_duration_ms": 80.0,
                    "p95_duration_ms": 210.0,
                    "p99_duration_ms": 390.0,
                    "max_duration_ms": 420.0,
                    "first_seen_at": "2026-06-24T00:00:00+00:00",
                    "last_seen_at": "2026-06-24T01:00:00+00:00",
                },
                {"status": "failed", "scope_count": 1, "p95_duration_ms": None, "p99_duration_ms": None},
            ]
        if "from job.workbench_matching_dirty_scopes" in normalized and "order by updated_at desc" in normalized:
            return [
                {
                    "tenant_id": "default",
                    "scope_month": "2026-03",
                    "status": "completed",
                    "reason": "matching_rule_changed",
                    "duration_ms": 210,
                    "source_versions": {"workbench_matching_rules_version": "v1"},
                }
            ]
        if "from job.runtime_worker_heartbeats" in normalized:
            return [
                {
                    "worker_id": "worker-1",
                    "worker_kind": "workbench-matching",
                    "status": "ready",
                    "heartbeat_lag_seconds": 1.5,
                    "last_seen_at": "2026-06-24T01:00:00+00:00",
                    "payload": {"worker_instance": "workbench-matching"},
                }
            ]
        if "from read_model.workbench_candidate_matches" in normalized:
            return [
                {
                    "scope_month": "2026-03",
                    "candidate_count": 5,
                    "auto_closed_count": 2,
                    "conflict_count": 1,
                }
            ]
        if "from read_model.workbench_reconciliation_decisions" in normalized and "group by scope_month" in normalized:
            return [
                {
                    "scope_month": "2026-03",
                    "decision_count": 8,
                    "paired_count": 3,
                    "open_count": 2,
                    "expired_count": 1,
                    "suppressed_count": 1,
                    "consumed_count": 1,
                }
            ]
        if "from pg_stat_statements" in normalized:
            return [
                {
                    "query": "select * from read_model.workbench_candidate_matches where scope_month = $1",
                    "calls": 10,
                    "total_exec_time": 70.0,
                    "mean_exec_time": 7.0,
                    "rows": 300,
                }
            ]
        raise AssertionError(sql)

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        self._assert_read_only(sql)
        normalized = self._record(self.fetch_one_calls, sql, params)
        if normalized.startswith("explain"):
            return {"QUERY PLAN": [{"Plan": {"Node Type": "Aggregate"}}]}
        if "from job.outbox_events" in normalized:
            if self.empty:
                return {}
            return {
                "sample_count": 9,
                "p50_enqueue_to_done_ms": 500.0,
                "p95_enqueue_to_done_ms": 1400.0,
                "p99_enqueue_to_done_ms": 2300.0,
                "last_seen_at": "2026-06-24T01:00:00+00:00",
            }
        raise AssertionError(sql)

    def _record(
        self,
        calls: list[tuple[str, tuple[object, ...]]],
        sql: str,
        params: tuple[object, ...],
    ) -> str:
        normalized = " ".join(sql.lower().split())
        calls.append((normalized, params))
        return normalized

    def _assert_read_only(self, sql: str) -> None:
        normalized = " ".join(sql.split())
        if normalized.lower().startswith("explain"):
            normalized = re.sub(r"^explain\s+\(format json\)\s+", "", normalized, flags=re.IGNORECASE)
        if MUTATING_SQL_RE.search(normalized):
            raise AssertionError(f"Workbench compute evidence collector used mutating SQL: {sql}")


class WorkbenchComputeEvidenceTests(unittest.TestCase):
    def test_collect_evidence_combines_required_read_only_sections(self) -> None:
        connection = FakeWorkbenchComputeEvidenceConnection()

        payload = workbench_compute_evidence.collect_evidence(
            connection,
            tenant_id="default",
            limit=5,
            window_hours=12,
        )

        self.assertEqual(payload["tool"], "workbench_compute_evidence")
        self.assertEqual(payload["mode"], "read_only")
        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["admission_status"], "evidence_collected")
        self.assertFalse(payload["production_evidence_required"])
        sections = payload["sections"]
        self.assertEqual(
            sections["matching_scope_durations"]["data"]["required_metrics"]["worker_scope_duration_p95_ms"],
            210.0,
        )
        self.assertEqual(sections["worker_heartbeat"]["data"]["required_metrics"]["worker_status"], "ready")
        self.assertEqual(
            sections["candidate_decision_counts"]["data"]["decision_counts_by_scope"][0]["paired_count"],
            3,
        )
        self.assertTrue(sections["query_timing_evidence"]["data"]["required_metrics"]["query_timing_available"])
        self.assertEqual(sections["explain_probes"]["status"], "available")
        self.assertIn("database_writes", payload["forbidden_actions"])
        self.assertTrue(connection.fetch_all_calls)
        self.assertTrue(connection.fetch_one_calls)

    def test_collect_evidence_reports_missing_sections_without_passing_admission(self) -> None:
        payload = workbench_compute_evidence.collect_evidence(
            FakeWorkbenchComputeEvidenceConnection(empty=True),
            include_explain=False,
        )

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["admission_status"], "blocked_by_missing_real_evidence")
        self.assertTrue(payload["production_evidence_required"])
        self.assertIn("worker p95/p99 duration by scope", payload["missing_evidence_fields"])
        self.assertEqual(payload["sections"]["explain_probes"]["status"], "skipped")

    def test_main_returns_structured_configuration_missing_report(self) -> None:
        stdout = StringIO()

        with patch.object(
            workbench_compute_evidence.PostgresSettings,
            "from_env",
            side_effect=PostgresConfigurationError("database url missing"),
        ):
            exit_code = workbench_compute_evidence.main(["--json"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "configuration_missing")
        self.assertEqual(payload["tool"], "workbench_compute_evidence")
        self.assertEqual(payload["blocking_condition"], "database_url_required")
        self.assertTrue(payload["production_evidence_required"])
        self.assertIn("FIN_OPS_POSTGRES_DATABASE_URL", payload["required_env"])
        self.assertIn("database writes", " ".join(payload["forbidden_without_approval"]))


if __name__ == "__main__":
    unittest.main()
