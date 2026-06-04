from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import unittest

from fin_ops_platform.services.read_model_readiness import ReadModelReadinessReporter
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class RecordingReadinessRepository:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record_read_model_readiness(self, **kwargs: object) -> None:
        self.records.append(dict(kwargs))


def _event(
    *,
    event_type: str = "bank_detail.read_model.refresh",
    scope_type: str = "bank_detail",
    scope_key: str = "2026-05",
    source_version: int | None = 7,
) -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id=f"evt-{scope_type}-{scope_key}",
        tenant_id="tenant-a",
        event_type=event_type,
        aggregate_type="read_model",
        aggregate_id=scope_key,
        scope_type=scope_type,
        scope_key=scope_key,
        dedupe_key=None,
        payload={"scope_type": scope_type, "scope_key": scope_key, "source_version": source_version},
        attempts=1,
        status="processing",
        source_version=source_version,
    )


class ReadModelReadinessReporterTests(unittest.TestCase):
    def test_records_fresh_from_runtime_event_result(self) -> None:
        repository = RecordingReadinessRepository()
        reporter = ReadModelReadinessReporter(readiness_repository=repository, clock=lambda: datetime(2026, 6, 4, tzinfo=UTC))

        reporter.record_event_success(
            _event(),
            {"scope_key": "2026-05", "row_count": 0, "source_versions": {"bank_detail_schema_version": 8}},
        )

        self.assertEqual(len(repository.records), 1)
        record = repository.records[0]
        self.assertEqual(record["tenant_id"], "tenant-a")
        self.assertEqual(record["read_model_key"], "bank_detail")
        self.assertEqual(record["scope_type"], "bank_detail")
        self.assertEqual(record["scope_key"], "2026-05")
        self.assertEqual(record["status"], "fresh")
        self.assertEqual(record["row_count"], 0)
        self.assertEqual(record["source_versions"], {"bank_detail_schema_version": 8})
        self.assertEqual(record["generated_at"], datetime(2026, 6, 4, tzinfo=UTC))

    def test_records_failed_then_reraises_wrapped_handler_exception(self) -> None:
        repository = RecordingReadinessRepository()
        reporter = ReadModelReadinessReporter(readiness_repository=repository)

        def failing_handler(_event: RuntimeQueueEvent) -> dict[str, object]:
            raise RuntimeError("projection failed")

        wrapped = reporter.wrap_handler(failing_handler)

        with self.assertRaisesRegex(RuntimeError, "projection failed"):
            wrapped(_event())

        self.assertEqual(repository.records[0]["status"], "failed")
        self.assertEqual(repository.records[0]["read_model_key"], "bank_detail")
        self.assertEqual(repository.records[0]["last_error"], "projection failed")

    def test_explicit_mismatch_result_is_not_recorded_as_fresh(self) -> None:
        repository = RecordingReadinessRepository()
        reporter = ReadModelReadinessReporter(readiness_repository=repository)

        reporter.record_event_success(
            _event(),
            {
                "scope_key": "2026-05",
                "readiness_status": "schema_mismatch",
                "schema_version": "old",
                "last_error": "schema version mismatch",
            },
        )

        self.assertEqual(repository.records[0]["status"], "schema_mismatch")
        self.assertEqual(repository.records[0]["schema_version"], "old")
        self.assertEqual(repository.records[0]["last_error"], "schema version mismatch")

    def test_all_scope_shard_fanout_does_not_record_fake_fresh(self) -> None:
        repository = RecordingReadinessRepository()
        reporter = ReadModelReadinessReporter(readiness_repository=repository)

        reporter.record_event_success(
            _event(scope_key="all"),
            {"scope_key": "all", "enqueued_scope_keys": ["2026-05"], "row_count": 0},
        )

        self.assertEqual(repository.records, [])

    def test_unknown_read_model_key_fails_fast(self) -> None:
        repository = RecordingReadinessRepository()
        reporter = ReadModelReadinessReporter(readiness_repository=repository)

        with self.assertRaisesRegex(ValueError, "Unregistered app status read model"):
            reporter.record_fresh(
                read_model_key="not_registered",
                scope_key="all",
                row_count=0,
            )

    def test_runtime_worker_read_model_handlers_are_wrapped_by_reporter(self) -> None:
        worker_source = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "src"
            / "fin_ops_platform"
            / "app"
            / "worker.py"
        ).read_text(encoding="utf-8")

        expected_assignments = (
            'handlers["workbench.read_model.refresh"] = _read_model_handler',
            "handlers[WORKBENCH_RELATION_REFRESH_EVENT_TYPE] = _read_model_handler",
            'handlers["cost_statistics.read_model.refresh"] = _read_model_handler',
            'handlers["tax_offset.read_model.refresh"] = _read_model_handler',
            'handlers["search.read_model.refresh"] = _read_model_handler',
            'handlers["pending_invoice.read_model.refresh"] = _read_model_handler',
            'handlers["bank_detail.read_model.refresh"] = _read_model_handler',
            "handlers[NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE] = _read_model_handler",
            'handlers["turnover_ledger.read_model.refresh"] = _read_model_handler',
            'handlers["bank_account_balance.read_model.refresh"] = _read_model_handler',
            "handlers[INVOICE_LIFECYCLE_REFRESH_EVENT_TYPE] = _read_model_handler",
            'handlers["input_invoice_usage.read_model.refresh"] = _read_model_handler',
            'handlers["output_invoice_collection.read_model.refresh"] = _read_model_handler',
            'handlers["oa_pending_payment.read_model.refresh"] = _read_model_handler',
        )
        for assignment in expected_assignments:
            self.assertIn(assignment, worker_source)


if __name__ == "__main__":
    unittest.main()
