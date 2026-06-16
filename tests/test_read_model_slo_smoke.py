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
            {
                "read_model_key": "pending_invoice",
                "scope_type": "pending_invoice",
                "scope_key": "expense:all:2026-01",
                "status": "fresh",
                "row_count": 8,
                "updated_at": "2026-06-13 10:05:00+08",
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


class MissingTurnoverReadinessConnection(FakeConnection):
    def __init__(self) -> None:
        super().__init__()
        self.readiness_rows = [
            row
            for row in self.readiness_rows
            if str(row.get("read_model_key") or "") != "turnover_ledger"
        ]


class PendingThenFreshConnection(FakeConnection):
    def __init__(self) -> None:
        super().__init__()
        self.event_fetch_count = 0
        self.event_processed_at = self.event_created_at + timedelta(milliseconds=850)

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.fetch_one_calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from job.outbox_events" in normalized:
            self.event_fetch_count += 1
            if self.event_fetch_count == 1:
                return {
                    "event_id": params[0],
                    "tenant_id": "default",
                    "event_type": "turnover_ledger.read_model.refresh",
                    "scope_type": "turnover_ledger",
                    "scope_key": "all",
                    "status": "pending",
                    "source_version": 8,
                    "created_at": self.event_created_at,
                    "processed_at": None,
                    "raw_payload": {},
                    "last_error": None,
                }
            return {
                "event_id": params[0],
                "tenant_id": "default",
                "event_type": "turnover_ledger.read_model.refresh",
                "scope_type": "turnover_ledger",
                "scope_key": "all",
                "status": "done",
                "source_version": 8,
                "created_at": self.event_created_at,
                "processed_at": self.event_processed_at,
                "raw_payload": {"runtime_result": {"duration_ms": 620}},
                "last_error": None,
            }
        if "from read_model.app_status_readiness" in normalized:
            if self.event_fetch_count == 1:
                return {
                    "status": "failed",
                    "updated_at": self.event_created_at - timedelta(minutes=1),
                    "row_count": 0,
                    "source_versions": {},
                    "last_error": "bank_detail_read_model_not_fresh",
                }
            return {
                "status": "fresh",
                "updated_at": self.event_processed_at,
                "row_count": 16,
                "source_versions": {"turnover_ledger": 8},
                "last_error": None,
            }
        if "from job.read_model_dirty_scopes" in normalized:
            return {
                "status": "pending" if self.event_fetch_count == 1 else "done",
                "source_version": 8,
                "updated_at": self.event_processed_at,
                "last_error": None,
            }
        raise AssertionError(sql)


class DirtyDoneWithoutReadinessConnection(FakeConnection):
    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.fetch_one_calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from job.outbox_events" in normalized:
            return {
                "event_id": params[0],
                "tenant_id": "default",
                "event_type": "pending_invoice.read_model.refresh",
                "scope_type": "pending_invoice",
                "scope_key": "expense:all",
                "status": "done",
                "source_version": 9,
                "created_at": self.event_created_at,
                "processed_at": self.event_processed_at,
                "raw_payload": {"runtime_result": {"duration_ms": 27}},
                "last_error": None,
            }
        if "from read_model.app_status_readiness" in normalized:
            return None
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "done", "source_version": 9, "updated_at": self.event_processed_at}
        raise AssertionError(sql)


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

    def test_critical_only_includes_bank_account_balance_page_read_model(self) -> None:
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
        self.assertIn("bank_account_balance", planned_keys)

    def test_pending_invoice_smoke_includes_page_first_screen_aggregate_scope(self) -> None:
        report = read_model_slo_smoke.run_smoke(
            FakeConnection(),
            apply=False,
            read_model_keys=["pending_invoice"],
        )

        self.assertEqual(report["status"], "dry_run")
        scopes = {item["scope_key"]: item["source"] for item in report["planned_scopes"]}
        self.assertEqual(scopes["expense:all:2026-01"], "readiness")
        self.assertEqual(scopes["expense:all"], "page_first_screen_scope")

    def test_missing_fresh_readiness_still_plans_default_scope_for_selected_read_model(self) -> None:
        report = read_model_slo_smoke.run_smoke(
            MissingTurnoverReadinessConnection(),
            apply=False,
            read_model_keys=["turnover_ledger"],
        )

        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["missing_read_model_keys"], [])
        self.assertEqual(report["planned_scope_count"], 1)
        self.assertEqual(report["planned_scopes"][0]["read_model_key"], "turnover_ledger")
        self.assertEqual(report["planned_scopes"][0]["scope_key"], "all")
        self.assertEqual(report["planned_scopes"][0]["source"], "default_scope")

    def test_explicit_key_still_limits_critical_only_selection(self) -> None:
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
        self.assertEqual(report["summary"]["sample_count"], 1)
        self.assertEqual(report["summary"]["measured_enqueue_sample_count"], 1)
        self.assertEqual(report["summary"]["enqueue_to_fresh_ms"]["p95"], 3000.0)
        self.assertEqual(report["summary"]["enqueue_to_fresh_ms"]["p99"], 3000.0)
        self.assertEqual(report["summary"]["handler_duration_ms"]["p95"], 500.0)

    def test_apply_fails_when_no_smoke_scopes_are_discovered(self) -> None:
        with patch.dict(read_model_slo_smoke.APP_STATUS_READ_MODEL_REGISTRY, {}, clear=True):
            report = read_model_slo_smoke.run_smoke(
                FakeConnection(),
                apply=True,
            )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["planned_scope_count"], 0)
        self.assertEqual(report["result_count"], 0)
        self.assertEqual(report["failed_count"], 1)
        self.assertEqual(report["error"], "no_smoke_scopes_discovered")
        self.assertEqual(report["summary"]["sample_count"], 0)

    def test_wait_does_not_fail_on_stale_failed_readiness_while_event_is_pending(self) -> None:
        connection = PendingThenFreshConnection()
        with patch.object(read_model_slo_smoke, "sleep", lambda _seconds: None):
            result = read_model_slo_smoke.wait_for_event_fresh(
                connection,
                event_id="event-1",
                read_model_key="turnover_ledger",
                scope_type="turnover_ledger",
                scope_key="all",
                tenant_id="default",
                target_ms=5_000,
                timeout_seconds=5,
                poll_interval_seconds=0.1,
            )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.event_status, "done")
        self.assertEqual(result.readiness_status, "fresh")
        self.assertEqual(result.enqueue_to_fresh_ms, 850.0)
        self.assertEqual(result.handler_duration_ms, 620.0)
        self.assertIsNone(result.error)

    def test_page_first_scope_can_pass_when_dirty_done_but_app_status_readiness_is_absent(self) -> None:
        result = read_model_slo_smoke.wait_for_event_fresh(
            DirtyDoneWithoutReadinessConnection(),
            event_id="event-1",
            read_model_key="pending_invoice",
            scope_type="pending_invoice",
            scope_key="expense:all",
            tenant_id="default",
            target_ms=5_000,
            timeout_seconds=5,
            poll_interval_seconds=0.1,
            allow_dirty_done_without_readiness=True,
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.event_status, "done")
        self.assertEqual(result.dirty_status, "done")
        self.assertEqual(result.readiness_status, "dirty_done")
        self.assertEqual(result.handler_duration_ms, 27.0)

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
        self.assertEqual(report["summary"]["failed_count"], 1)
        self.assertEqual(report["summary"]["enqueue_to_fresh_ms"]["max"], 6000.0)

    def test_summary_reports_enqueue_and_handler_percentiles(self) -> None:
        base = {
            "read_model_key": "bank_detail",
            "scope_type": "bank_detail",
            "scope_key": "2026-01",
            "event_type": "bank_detail.read_model.refresh",
            "event_id": "event",
            "status": "pass",
            "event_status": "done",
            "dirty_status": "done",
            "readiness_status": "fresh",
            "source_version": 1,
            "error": None,
        }
        results = [
            read_model_slo_smoke.SmokeEventResult(
                **base,
                enqueue_to_fresh_ms=float(index * 100),
                handler_duration_ms=float(index * 10),
            )
            for index in range(1, 21)
        ]

        summary = read_model_slo_smoke._results_summary(results)

        self.assertEqual(summary["sample_count"], 20)
        self.assertEqual(summary["measured_enqueue_sample_count"], 20)
        self.assertEqual(summary["enqueue_to_fresh_ms"], {"p50": 1000.0, "p95": 1900.0, "p99": 2000.0, "max": 2000.0})
        self.assertEqual(summary["handler_duration_ms"], {"p50": 100.0, "p95": 190.0, "p99": 200.0, "max": 200.0})


if __name__ == "__main__":
    unittest.main()
