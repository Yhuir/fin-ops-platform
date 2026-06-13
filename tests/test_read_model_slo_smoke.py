from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import read_model_slo_smoke


class FakeConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        self.readiness_rows = [
            {
                "read_model_key": "workbench",
                "scope_type": "workbench",
                "scope_key": "all",
                "status": "fresh",
                "row_count": 100,
                "updated_at": "2026-06-13 10:00:00+08",
            },
            {
                "read_model_key": "search",
                "scope_type": "search",
                "scope_key": "all",
                "status": "fresh",
                "row_count": 100,
                "updated_at": "2026-06-13 10:00:00+08",
            },
            {
                "read_model_key": "search",
                "scope_type": "search",
                "scope_key": "2026-01",
                "status": "fresh",
                "row_count": 20,
                "updated_at": "2026-06-13 10:01:00+08",
            },
            {
                "read_model_key": "cost_statistics",
                "scope_type": "cost_statistics",
                "scope_key": "active:all",
                "status": "fresh",
                "row_count": 30,
                "updated_at": "2026-06-13 10:00:00+08",
            },
            {
                "read_model_key": "cost_statistics",
                "scope_type": "cost_statistics",
                "scope_key": "active:2026-01",
                "status": "fresh",
                "row_count": 12,
                "updated_at": "2026-06-13 10:02:00+08",
            },
            {
                "read_model_key": "turnover_ledger",
                "scope_type": "turnover_ledger",
                "scope_key": "all",
                "status": "fresh",
                "row_count": 3,
                "updated_at": "2026-06-13 10:03:00+08",
            },
            {
                "read_model_key": "bank_account_balance",
                "scope_type": "bank_account_balance",
                "scope_key": "all",
                "status": "fresh",
                "row_count": 2,
                "updated_at": "2026-06-13 10:04:00+08",
            },
        ]
        self.workbench_generations = [
            {"scope_key": "all", "row_count": 100, "updated_at": "2026-06-13 10:05:00+08"},
            {"scope_key": "2026-01", "row_count": 10, "updated_at": "2026-06-13 10:04:00+08"},
        ]
        self.event_created_at = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)
        self.event_processed_at = self.event_created_at + timedelta(seconds=3)

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from read_model.app_status_readiness" in normalized:
            return list(self.readiness_rows)
        if "from read_model.workbench_generations" in normalized:
            return list(self.workbench_generations)
        raise AssertionError(sql)

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.fetch_one_calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from job.outbox_events" in normalized:
            return {
                "event_id": params[0],
                "tenant_id": "default",
                "event_type": "bank_detail.read_model.refresh",
                "scope_type": "bank_detail",
                "scope_key": "2026-01",
                "status": "done",
                "source_version": 4,
                "created_at": self.event_created_at,
                "processed_at": self.event_processed_at,
                "raw_payload": {"runtime_result": {"duration_ms": 500}},
            }
        if "from read_model.app_status_readiness" in normalized:
            return {"status": "fresh", "updated_at": self.event_processed_at, "row_count": 10, "source_versions": {}}
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "done", "source_version": 4, "updated_at": self.event_processed_at}
        raise AssertionError(sql)


class FakeQueueRepository:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> object:
        self.enqueued.append(dict(kwargs))
        return SimpleNamespace(
            event_id="event-1",
            event_type=f"{kwargs['scope_type']}.read_model.refresh",
            scope_type=kwargs["scope_type"],
            scope_key=kwargs["scope_key"],
        )


class ReadModelSloSmokeTests(unittest.TestCase):
    def test_dry_run_discovers_direct_scopes_without_enqueueing(self) -> None:
        report = read_model_slo_smoke.run_smoke(
            FakeConnection(),
            apply=False,
            read_model_keys=["workbench", "search", "cost_statistics", "turnover_ledger"],
        )

        self.assertEqual(report["status"], "dry_run")
        scopes = {item["read_model_key"]: item["scope_key"] for item in report["planned_scopes"]}
        self.assertEqual(scopes["workbench"], "2026-01")
        self.assertEqual(scopes["search"], "2026-01")
        self.assertEqual(scopes["cost_statistics"], "active:2026-01")
        self.assertEqual(scopes["turnover_ledger"], "all")

    def test_critical_only_excludes_non_critical_read_models_by_default(self) -> None:
        report = read_model_slo_smoke.run_smoke(
            FakeConnection(),
            apply=False,
            critical_only=True,
        )

        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["critical_only"], True)
        planned_keys = {item["read_model_key"] for item in report["planned_scopes"]}
        self.assertIn("workbench", planned_keys)
        self.assertIn("turnover_ledger", planned_keys)
        self.assertNotIn("bank_account_balance", planned_keys)

    def test_explicit_key_still_includes_non_critical_read_model(self) -> None:
        report = read_model_slo_smoke.run_smoke(
            FakeConnection(),
            apply=False,
            critical_only=True,
            read_model_keys=["bank_account_balance"],
        )

        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["critical_only"], True)
        self.assertEqual(report["planned_scopes"][0]["read_model_key"], "bank_account_balance")

    def test_apply_enqueues_and_waits_for_done_fresh_under_target(self) -> None:
        connection = FakeConnection()
        with patch.object(read_model_slo_smoke, "RuntimeQueueRepository", FakeQueueRepository):
            report = read_model_slo_smoke.run_smoke(
                connection,
                apply=True,
                read_model_keys=["bank_detail"],
                scope_overrides={"bank_detail": "2026-01"},
                target_ms=5_000,
                poll_interval_seconds=0.1,
            )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["result_count"], 1)
        result = report["results"][0]
        self.assertEqual(result["event_status"], "done")
        self.assertEqual(result["dirty_status"], "done")
        self.assertEqual(result["readiness_status"], "fresh")
        self.assertEqual(result["enqueue_to_fresh_ms"], 3000.0)
        self.assertEqual(result["handler_duration_ms"], 500.0)

    def test_apply_fails_when_enqueue_to_fresh_exceeds_target(self) -> None:
        connection = FakeConnection()
        connection.event_processed_at = connection.event_created_at + timedelta(seconds=6)
        with patch.object(read_model_slo_smoke, "RuntimeQueueRepository", FakeQueueRepository):
            report = read_model_slo_smoke.run_smoke(
                connection,
                apply=True,
                read_model_keys=["bank_detail"],
                scope_overrides={"bank_detail": "2026-01"},
                target_ms=5_000,
                poll_interval_seconds=0.1,
            )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["failed_count"], 1)
        self.assertIn("enqueue_to_fresh_ms_exceeded_target", report["results"][0]["error"])


if __name__ == "__main__":
    unittest.main()
