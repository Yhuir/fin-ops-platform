from __future__ import annotations

import unittest

from fin_ops_platform.services.tax_offset_runtime_service import (
    TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
    TaxOffsetRuntimeService,
)
from fin_ops_platform.services.tax_offset_worker_rebuild_executor import TaxOffsetWorkerRebuildExecutor


class _RedisRecorder:
    def __init__(self) -> None:
        self.set_calls: list[dict[str, object]] = []

    def set_json(self, key: str, payload: dict[str, object], *, ttl_seconds: int) -> bool:
        self.set_calls.append({"key": key, "payload": payload, "ttl_seconds": ttl_seconds})
        return True


class TaxOffsetWorkerRebuildExecutorTests(unittest.TestCase):
    def test_rebuild_scope_publishes_fresh_cache_without_read_model_persist(self) -> None:
        redis = _RedisRecorder()
        runtime = TaxOffsetRuntimeService(
            redis_helper=redis,
            source_versions_provider=lambda: {
                "tax_offset_read_model_schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                "invoice_fact_source_version": "invoice:v1",
            },
        )

        executor = TaxOffsetWorkerRebuildExecutor(
            runtime_service=runtime,
            month_payload_loader=lambda month: {
                "month": month,
                "summary": {"output_tax": "13.00"},
                "output_items": [{"id": "out-1"}],
                "input_plan_items": [{"id": "in-1"}],
                "certified_items": [],
            },
        )

        result = executor.rebuild_scope("2026-05")

        self.assertEqual(result, {"scope_key": "2026-05", "month": "2026-05", "entry_count": 2})
        self.assertEqual(len(redis.set_calls), 2)
        month_cache = next(call for call in redis.set_calls if ":month:" in str(call["key"]))
        summary_cache = next(call for call in redis.set_calls if ":summary:" in str(call["key"]))
        self.assertEqual(month_cache["ttl_seconds"], 60)
        self.assertEqual(summary_cache["ttl_seconds"], 60)
        month_payload = month_cache["payload"]["payload"]
        self.assertEqual(month_payload["status"], "fresh")
        self.assertEqual(month_payload["scope_key"], "2026-05")
        self.assertEqual(month_cache["payload"]["fresh_gate"]["status"], "fresh")
        self.assertEqual(month_cache["payload"]["fresh_gate"]["scope_key"], "2026-05")
        self.assertEqual(
            month_cache["payload"]["fresh_gate"]["schema_version"],
            TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
        )
        summary_payload = summary_cache["payload"]["payload"]
        self.assertEqual(summary_payload["summary"], {"output_tax": "13.00"})
        self.assertNotIn("output_items", summary_payload)

    def test_rebuild_scope_rejects_non_month_scope(self) -> None:
        executor = TaxOffsetWorkerRebuildExecutor(
            runtime_service=TaxOffsetRuntimeService(),
            month_payload_loader=lambda month: {"month": month},
        )

        with self.assertRaises(ValueError):
            executor.rebuild_scope("all")


if __name__ == "__main__":
    unittest.main()
