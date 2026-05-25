from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from fin_ops_platform.services.invoice_usage_collection_backfill import (
    build_invoice_usage_collection_backfill_plan,
    execute_invoice_usage_collection_backfill_plan,
    invoice_usage_collection_worker_args,
)


class FakeShardProvider:
    def list_input_invoice_usage_scope_shards(self, scope_key: str) -> list[str]:
        self.input_scope_key = scope_key
        return ["2026-05", "2026-04"]

    def list_output_invoice_collection_scope_shards(self, scope_key: str) -> list[str]:
        self.output_scope_key = scope_key
        return ["2026-05"]


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
        return type("Event", (), {"event_id": f"event-{len(self.refreshes)}", "source_version": len(self.refreshes)})()


class FakeBackfillConnection:
    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from app.invoices" in normalized and "union" in normalized:
            return [{"scope_key": "2026-05"}]
        return []


def load_backfill_script_module() -> object:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "backfill-runtime-read-models.py"
    spec = importlib.util.spec_from_file_location("backfill_runtime_read_models", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InvoiceUsageCollectionBackfillTests(unittest.TestCase):
    def test_default_plan_enqueues_all_scope_for_both_invoice_read_models(self) -> None:
        plan = build_invoice_usage_collection_backfill_plan(reason="manual_backfill")

        self.assertEqual(
            [task.to_report() for task in plan],
            [
                {
                    "event_type": "input_invoice_usage.read_model.refresh",
                    "scope_type": "input_invoice_usage",
                    "scope_key": "all",
                    "reason": "manual_backfill",
                    "priority": "normal",
                    "trace_id": None,
                },
                {
                    "event_type": "output_invoice_collection.read_model.refresh",
                    "scope_type": "output_invoice_collection",
                    "scope_key": "all",
                    "reason": "manual_backfill",
                    "priority": "normal",
                    "trace_id": None,
                },
            ],
        )

    def test_expand_all_uses_target_specific_invoice_month_shards(self) -> None:
        provider = FakeShardProvider()

        plan = build_invoice_usage_collection_backfill_plan(
            targets=["both"],
            scope_keys=["all"],
            expand_all=True,
            shard_provider=provider,
            reason="warmup",
        )

        self.assertEqual(provider.input_scope_key, "all")
        self.assertEqual(provider.output_scope_key, "all")
        self.assertEqual(
            [(task.scope_type, task.scope_key, task.reason) for task in plan],
            [
                ("input_invoice_usage", "2026-05", "warmup"),
                ("input_invoice_usage", "2026-04", "warmup"),
                ("output_invoice_collection", "2026-05", "warmup"),
            ],
        )

    def test_dry_run_reports_plan_without_mutating_queue(self) -> None:
        queue = FakeQueue()
        plan = build_invoice_usage_collection_backfill_plan(scope_keys=["2026-05"], reason="dry_run")

        report = execute_invoice_usage_collection_backfill_plan(queue, plan, dry_run=True)

        self.assertEqual(queue.refreshes, [])
        self.assertEqual(report["action"], "enqueue_invoice_usage_collection")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["planned_count"], 2)
        self.assertEqual(report["enqueued_count"], 0)

    def test_execute_plan_enqueues_durable_refresh_events_with_priority_and_trace(self) -> None:
        queue = FakeQueue()
        plan = build_invoice_usage_collection_backfill_plan(
            targets=["input"],
            scope_keys=["2026-05"],
            reason="release_warmup",
            priority="high",
            trace_id="trace-123",
        )

        report = execute_invoice_usage_collection_backfill_plan(queue, plan, dry_run=False)

        self.assertEqual(
            queue.refreshes,
            [
                {
                    "scope_type": "input_invoice_usage",
                    "scope_key": "2026-05",
                    "reason": "release_warmup",
                    "priority": "high",
                    "trace_id": "trace-123",
                }
            ],
        )
        self.assertFalse(report["dry_run"])
        self.assertEqual(report["enqueued_count"], 1)
        self.assertEqual(report["events"], [{"event_id": "event-1", "source_version": 1}])

    def test_invalid_scope_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "invoice read model scope"):
            build_invoice_usage_collection_backfill_plan(scope_keys=["202605"])

    def test_worker_args_include_invoice_usage_collection_handlers(self) -> None:
        args = invoice_usage_collection_worker_args()

        self.assertIn("--enable-input-invoice-usage-read-model-refresh", args)
        self.assertIn("--enable-output-invoice-collection-read-model-refresh", args)
        self.assertIn("input_invoice_usage.read_model.refresh", args)
        self.assertIn("output_invoice_collection.read_model.refresh", args)

    def test_runtime_backfill_script_dry_run_includes_invoice_read_models_without_enqueue_count(self) -> None:
        module = load_backfill_script_module()

        report = module.enqueue_fact_scopes(FakeBackfillConnection(), dry_run=True, reason="dry_run")

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["enqueued_count"], 0)
        self.assertEqual(report["planned_count"], 13)
        self.assertEqual(report["invoice_usage_collection"]["planned_count"], 2)
        self.assertEqual(report["invoice_usage_collection"]["enqueued_count"], 0)


if __name__ == "__main__":
    unittest.main()
