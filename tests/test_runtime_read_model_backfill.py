from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ACTIVE_SCOPE_TYPES = ("workbench", "workbench_relation", "search", "no_oa_bank_batch")


class FakeQueue:
    def __init__(self) -> None:
        self.refreshes: list[dict[str, object]] = []

    def enqueue_read_model_refresh(
        self,
        *,
        scope_type: str,
        scope_key: str,
        reason: str,
        priority: str = "normal",
        trace_id: str | None = None,
    ) -> object:
        self.refreshes.append(
            {
                "scope_type": scope_type,
                "scope_key": scope_key,
                "reason": reason,
                "priority": priority,
                "trace_id": trace_id,
            }
        )
        return type("Event", (), {"event_id": f"event-{len(self.refreshes)}"})()

    def enqueue(self, **kwargs: object) -> object:
        self.refreshes.append(dict(kwargs))
        return type("Event", (), {"event_id": f"event-{len(self.refreshes)}"})()


class FakeConnection:
    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        del params
        normalized = " ".join(sql.lower().split())
        if "from job.read_model_dirty_scopes" in normalized:
            return [{"scope_type": "search", "status": "pending", "count": 1}]
        if "from job.outbox_events" in normalized:
            return [{"event_type": "search.read_model.refresh", "status": "pending", "count": 1}]
        return []


def load_backfill_script_module() -> object:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "backfill-runtime-read-models.py"
    spec = importlib.util.spec_from_file_location("backfill_runtime_read_models", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeReadModelBackfillTests(unittest.TestCase):
    def test_dry_run_plans_only_active_read_model_fan_out_commands(self) -> None:
        module = load_backfill_script_module()

        report = module.enqueue_fact_scopes(FakeConnection(), dry_run=True, reason="dry_run")

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["planned_count"], len(ACTIVE_SCOPE_TYPES))
        self.assertEqual(report["enqueued_count"], 0)
        self.assertEqual(tuple(report["scope_types"]), ACTIVE_SCOPE_TYPES)

    def test_enqueue_missing_writes_only_active_read_model_fan_out_commands(self) -> None:
        module = load_backfill_script_module()
        queue = FakeQueue()
        module.RuntimeQueueRepository = lambda _connection: queue

        report = module.enqueue_fact_scopes(
            FakeConnection(),
            reason="release_warmup",
            priority="high",
            trace_id="trace-123",
        )

        self.assertEqual(report["enqueued_count"], len(ACTIVE_SCOPE_TYPES))
        self.assertEqual(
            queue.refreshes,
            [
                {
                    "scope_type": scope_type,
                    "scope_key": "all",
                    "reason": "release_warmup",
                    "priority": "high",
                    "trace_id": "trace-123",
                }
                for scope_type in ACTIVE_SCOPE_TYPES
            ],
        )

    def test_worker_dry_run_uses_only_active_read_model_handlers(self) -> None:
        module = load_backfill_script_module()
        module.PostgresConnection = lambda _settings: FakeConnection()
        module.PostgresSettings = type("FakePostgresSettings", (), {"from_env": staticmethod(lambda: object())})
        stdout = StringIO()

        with patch.object(
            sys,
            "argv",
            ["backfill-runtime-read-models.py", "--run-worker", "--dry-run", "--json"],
        ), redirect_stdout(stdout):
            exit_code = module.main()

        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        worker_action = next(action for action in report["actions"] if action["action"] == "run_worker")
        worker_args = worker_action["worker_args"]
        self.assertIn("--enable-workbench-relation-read-model-refresh", worker_args)
        self.assertIn("--enable-search-read-model-refresh", worker_args)
        self.assertIn("--enable-no-oa-bank-batch-read-model-refresh", worker_args)
        self.assertNotIn("--enable-bank-flow-rule-batch-canonical-draft-refresh", worker_args)
        self.assertNotIn("bank_flow_rule_batch.canonical_draft.refresh", worker_args)
        self.assertNotIn("input_invoice_usage.read_model.refresh", worker_args)
        self.assertNotIn("output_invoice_collection.read_model.refresh", worker_args)
        self.assertNotIn("bank_detail.read_model.refresh", worker_args)

    def test_coverage_report_is_limited_to_active_registry_and_queue_state(self) -> None:
        module = load_backfill_script_module()

        report = module.coverage_report(FakeConnection())

        self.assertEqual(tuple(report["active_scope_types"]), ACTIVE_SCOPE_TYPES)
        self.assertEqual(report["dirty"], [{"scope_type": "search", "status": "pending", "count": 1}])
        self.assertEqual(
            report["outbox"],
            [{"event_type": "search.read_model.refresh", "status": "pending", "count": 1}],
        )


if __name__ == "__main__":
    unittest.main()
