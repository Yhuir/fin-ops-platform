from __future__ import annotations

import unittest
from datetime import datetime

from fin_ops_platform.services.tax_offset_read_model_service import (
    TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
    TaxOffsetReadModelService,
)
from fin_ops_platform.services.tax_offset_runtime_service import TaxOffsetRuntimeService
from fin_ops_platform.services.tax_offset_worker_rebuild_executor import TaxOffsetWorkerRebuildExecutor


class _RedisRecorder:
    def __init__(self) -> None:
        self.set_calls: list[dict[str, object]] = []

    def set_json(self, key: str, payload: dict[str, object], *, ttl_seconds: int) -> bool:
        self.set_calls.append({"key": key, "payload": payload, "ttl_seconds": ttl_seconds})
        return True


class TaxOffsetWorkerRebuildExecutorTests(unittest.TestCase):
    def test_rebuild_scope_persists_without_prepublishing_an_unstable_generation_cache(self) -> None:
        redis = _RedisRecorder()
        read_models = TaxOffsetReadModelService()
        persisted: list[dict[str, object]] = []
        runtime = TaxOffsetRuntimeService(
            read_model_service=read_models,
            redis_helper=redis,
            source_versions_provider=lambda: {
                "tax_offset_read_model_schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                "invoice_fact_source_version": "invoice:v1",
            },
            statistics_generation_token_provider=lambda: "generation-1",
        )

        executor = TaxOffsetWorkerRebuildExecutor(
            runtime_service=runtime,
            read_model_service=read_models,
            month_payload_loader=lambda month: {
                "month": month,
                "summary": {"output_tax": "13.00"},
                "output_items": [{"id": "out-1"}],
                "input_plan_items": [{"id": "in-1"}],
                "certified_items": [],
            },
            persist_read_models=lambda **kwargs: persisted.append(dict(kwargs)),
            clock=lambda: datetime(2026, 6, 24, 10, 30, 0),
        )

        result = executor.rebuild_scope("2026-05")

        self.assertEqual(result, {"scope_key": "2026-05", "month": "2026-05", "entry_count": 2})
        self.assertEqual(persisted[0]["changed_scope_keys"], ["2026-05"])
        self.assertEqual(persisted[0]["operation"], "worker_tax_offset_read_model_refresh")
        self.assertIn("2026-05", persisted[0]["snapshot"]["read_models"])
        self.assertEqual(redis.set_calls, [])

    def test_rebuild_scope_rejects_non_month_scope(self) -> None:
        executor = TaxOffsetWorkerRebuildExecutor(
            runtime_service=TaxOffsetRuntimeService(),
            read_model_service=TaxOffsetReadModelService(),
            month_payload_loader=lambda month: {"month": month},
            persist_read_models=lambda **_kwargs: None,
        )

        with self.assertRaises(ValueError):
            executor.rebuild_scope("all")


if __name__ == "__main__":
    unittest.main()
