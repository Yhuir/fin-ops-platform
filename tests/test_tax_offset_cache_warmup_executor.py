from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace

from fin_ops_platform.services.tax_offset_cache_warmup_executor import TaxOffsetCacheWarmupExecutor
from fin_ops_platform.services.tax_offset_read_model_service import TaxOffsetReadModelService
from fin_ops_platform.services.tax_offset_runtime_service import TaxOffsetRuntimeService


class _BackgroundJobRecorder:
    def __init__(self) -> None:
        self.created_jobs: list[dict[str, object]] = []
        self.run_calls: list[dict[str, object]] = []
        self.progress_calls: list[dict[str, object]] = []
        self.succeeded_jobs: list[dict[str, object]] = []

    def create_or_get_idempotent_job_with_created(self, **kwargs):
        self.created_jobs.append(dict(kwargs))
        return SimpleNamespace(job_id="tax-offset-cache-warmup-job-1"), True

    def run_job(self, job, callback) -> None:
        self.run_calls.append({"job": job, "callback": callback})

    def update_progress(self, job_id: str, **kwargs) -> None:
        self.progress_calls.append({"job_id": job_id, **kwargs})

    def succeed_job(self, job_id: str, message: str, *, result_summary: dict[str, object], status: str) -> None:
        self.succeeded_jobs.append(
            {
                "job_id": job_id,
                "message": message,
                "result_summary": dict(result_summary),
                "status": status,
            }
        )


class TaxOffsetCacheWarmupExecutorTests(unittest.TestCase):
    def test_schedule_respects_gate_and_preserves_background_job_contract(self) -> None:
        disabled_jobs = _BackgroundJobRecorder()
        disabled_executor = TaxOffsetCacheWarmupExecutor(
            runtime_service=TaxOffsetRuntimeService(),
            read_model_service=TaxOffsetReadModelService(),
            background_job_service=disabled_jobs,
            month_payload_loader=lambda month: {"month": month},
            persist_read_models=lambda **_kwargs: None,
            enabled_provider=lambda: False,
        )

        disabled_executor.schedule(["2026-05"], reason="unit_disabled")

        self.assertEqual(disabled_jobs.created_jobs, [])
        self.assertEqual(disabled_jobs.run_calls, [])

        enabled_jobs = _BackgroundJobRecorder()
        enabled_executor = TaxOffsetCacheWarmupExecutor(
            runtime_service=TaxOffsetRuntimeService(),
            read_model_service=TaxOffsetReadModelService(),
            background_job_service=enabled_jobs,
            month_payload_loader=lambda month: {"month": month},
            persist_read_models=lambda **_kwargs: None,
            enabled_provider=lambda: True,
        )

        enabled_executor.schedule(
            ["2026-04", "not-a-month", "2026-05", "2026-05"],
            reason="unit_enabled",
        )

        self.assertEqual(len(enabled_jobs.created_jobs), 1)
        created = enabled_jobs.created_jobs[0]
        self.assertEqual(created["job_type"], "tax_offset_cache_warmup")
        self.assertEqual(created["label"], "预热税金抵扣缓存")
        self.assertEqual(created["owner_user_id"], "system")
        self.assertEqual(created["visibility"], "system")
        self.assertEqual(created["phase"], "queued")
        self.assertEqual(created["message"], "税金抵扣缓存预热任务已创建。")
        self.assertEqual(created["source"], {"reason": "unit_enabled"})
        self.assertEqual(created["result_summary"], {"warmed": 0, "failed": 0})
        self.assertEqual(created["affected_months"], ["2026-05", "2026-04"])
        self.assertEqual(created["affected_scopes"], ["2026-05", "2026-04"])
        self.assertEqual(created["idempotency_key"], "tax_offset_cache_warmup:unit_enabled:2026-05,2026-04")
        self.assertEqual(len(enabled_jobs.run_calls), 1)

    def test_run_job_persists_ready_read_model_and_reports_partial_failure(self) -> None:
        read_models = TaxOffsetReadModelService()
        jobs = _BackgroundJobRecorder()
        persisted: list[dict[str, object]] = []

        def load_payload(month: str) -> dict[str, object]:
            if month == "2026-04":
                raise RuntimeError("payload unavailable")
            return {
                "month": month,
                "summary": {"output_tax": "13.00"},
                "output_items": [{"id": "out-1"}],
                "input_plan_items": [{"id": "in-1"}],
                "certified_items": [],
            }

        executor = TaxOffsetCacheWarmupExecutor(
            runtime_service=TaxOffsetRuntimeService(read_model_service=read_models),
            read_model_service=read_models,
            background_job_service=jobs,
            month_payload_loader=load_payload,
            persist_read_models=lambda **kwargs: persisted.append(dict(kwargs)),
            enabled_provider=lambda: True,
            clock=lambda: datetime(2026, 6, 24, 12, 0, 0),
        )

        result = executor.run_job(
            SimpleNamespace(job_id="tax-offset-cache-warmup-job-1"),
            months=["2026-05", "2026-04"],
        )

        self.assertEqual(result, {"warmed": 1, "failed": 1})
        self.assertEqual(len(jobs.progress_calls), 2)
        self.assertEqual(jobs.progress_calls[0]["phase"], "build_tax_offset_cache")
        self.assertEqual(persisted[0]["changed_scope_keys"], ["2026-05"])
        self.assertEqual(persisted[0]["operation"], "tax_offset_cache_warmup")
        self.assertIn("2026-05", persisted[0]["snapshot"]["read_models"])
        persisted_model = persisted[0]["snapshot"]["read_models"]["2026-05"]
        self.assertEqual(persisted_model["cache_status"], "ready")
        self.assertEqual(persisted_model["generated_at"], "2026-06-24T12:00:00")
        self.assertEqual(jobs.succeeded_jobs[0]["status"], "partial_success")
        self.assertEqual(jobs.succeeded_jobs[0]["message"], "税金抵扣缓存预热部分完成。")
        self.assertEqual(jobs.succeeded_jobs[0]["result_summary"], {"warmed": 1, "failed": 1})

    def test_run_job_noops_without_read_model_service(self) -> None:
        jobs = _BackgroundJobRecorder()
        executor = TaxOffsetCacheWarmupExecutor(
            runtime_service=TaxOffsetRuntimeService(),
            read_model_service=None,
            background_job_service=jobs,
            month_payload_loader=lambda month: {"month": month},
            persist_read_models=lambda **_kwargs: None,
            enabled_provider=lambda: True,
        )

        result = executor.run_job(SimpleNamespace(job_id="tax-offset-cache-warmup-job-1"), months=["2026-05"])

        self.assertEqual(result, {"warmed": 0, "failed": 0})
        self.assertEqual(jobs.progress_calls, [])
        self.assertEqual(jobs.succeeded_jobs, [])


if __name__ == "__main__":
    unittest.main()
