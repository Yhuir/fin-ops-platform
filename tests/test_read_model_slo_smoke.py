from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import read_model_slo_smoke


class FakeConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        self.readiness_rows = [
            {
                "read_model_key": key,
                "scope_type": key,
                "scope_key": "2026-01",
                "status": "fresh",
                "row_count": 10,
                "updated_at": "2026-07-27 10:00:00+08",
            }
            for key in ("workbench_relation", "search", "no_oa_bank_batch")
        ]
        self.started_at = datetime(2026, 7, 27, 2, 0, tzinfo=timezone.utc)
        self.finished_at = self.started_at + timedelta(milliseconds=350)

    def fetch_all(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from read_model.app_status_readiness" in normalized:
            return list(self.readiness_rows)
        raise AssertionError(f"unexpected read-model SLO query: {sql}")

    def fetch_one(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        if "from job.outbox_events" in normalized:
            return {
                "event_id": params[0],
                "tenant_id": "default",
                "event_type": "search.read_model.refresh",
                "scope_type": "search",
                "scope_key": "2026-01",
                "status": "done",
                "source_version": 3,
                "created_at": self.started_at,
                "available_at": self.started_at,
                "processed_at": self.finished_at,
                "raw_payload": {"runtime_result": {"duration_ms": 220}},
                "last_error": None,
            }
        if "from read_model.app_status_readiness" in normalized:
            return {
                "status": "fresh",
                "updated_at": self.finished_at,
                "row_count": 10,
                "source_versions": {},
                "last_error": None,
            }
        if "from job.read_model_dirty_scopes" in normalized:
            return {
                "status": "done",
                "source_version": 3,
                "updated_at": self.finished_at,
                "last_error": None,
            }
        raise AssertionError(f"unexpected read-model SLO query: {sql}")


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
    def test_dry_run_discovers_only_active_shared_read_models(self) -> None:
        connection = FakeConnection()

        report = read_model_slo_smoke.run_smoke(connection, apply=False)

        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(
            {row["read_model_key"] for row in report["planned_scopes"]},
            {"workbench_relation", "search", "no_oa_bank_batch"},
        )
        self.assertFalse(any("workbench_generations" in sql for sql, _params in connection.fetch_all_calls))

    def test_critical_only_uses_current_app_status_registry(self) -> None:
        connection = FakeConnection()

        report = read_model_slo_smoke.run_smoke(
            connection,
            apply=False,
            critical_only=True,
        )

        self.assertEqual(report["missing_read_model_keys"], [])
        self.assertEqual(
            {row["read_model_key"] for row in report["planned_scopes"]},
            {"workbench_relation", "search"},
        )

    def test_explicit_key_limits_scope_selection(self) -> None:
        report = read_model_slo_smoke.run_smoke(
            FakeConnection(),
            apply=False,
            read_model_keys=["search"],
            scope_overrides={"search": "all"},
        )

        self.assertEqual(
            report["planned_scopes"],
            [
                {
                    "read_model_key": "search",
                    "scope_type": "search",
                    "scope_key": "all",
                    "source": "override",
                    "row_count": None,
                    "updated_at": None,
                }
            ],
        )

    def test_apply_enqueues_and_measures_active_shared_read_model(self) -> None:
        connection = FakeConnection()
        queue = FakeQueueRepository(connection)

        with patch.object(read_model_slo_smoke, "RuntimeQueueRepository", return_value=queue):
            report = read_model_slo_smoke.run_smoke(
                connection,
                apply=True,
                read_model_keys=["search"],
                target_ms=500,
                poll_interval_seconds=0.05,
            )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["result_count"], 1)
        self.assertEqual(report["results"][0]["enqueue_to_fresh_ms"], 350.0)
        self.assertEqual(queue.enqueued[0]["scope_type"], "search")

    def test_apply_fails_when_enqueue_to_fresh_exceeds_target(self) -> None:
        connection = FakeConnection()
        queue = FakeQueueRepository(connection)

        with patch.object(read_model_slo_smoke, "RuntimeQueueRepository", return_value=queue):
            report = read_model_slo_smoke.run_smoke(
                connection,
                apply=True,
                read_model_keys=["search"],
                target_ms=100,
                poll_interval_seconds=0.05,
            )

        self.assertEqual(report["status"], "fail")
        self.assertIn("enqueue_to_fresh_ms_exceeded_target", report["results"][0]["error"])

    def test_summary_reports_enqueue_and_handler_percentiles(self) -> None:
        result = read_model_slo_smoke.SmokeEventResult(
            read_model_key="search",
            scope_type="search",
            scope_key="2026-01",
            event_type="search.read_model.refresh",
            event_id="event-1",
            status="pass",
            enqueue_to_fresh_ms=350.0,
            handler_duration_ms=220.0,
            event_status="done",
            dirty_status="done",
            readiness_status="fresh",
            source_version=3,
        )

        summary = read_model_slo_smoke._results_summary([result])

        self.assertEqual(summary["enqueue_to_fresh_ms"]["p95"], 350.0)
        self.assertEqual(summary["handler_duration_ms"]["p95"], 220.0)


if __name__ == "__main__":
    unittest.main()
