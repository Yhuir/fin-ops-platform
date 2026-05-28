from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.app import worker as worker_app
from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.import_job_queue import (
    IMPORT_PROCESS_REQUESTED_EVENT,
    ImportJob,
    ImportJobRepository,
    ImportJobWorker,
)


class FakeTransaction:
    def __init__(self, rows: list[dict[str, object] | None] | None = None) -> None:
        self.rows = list(rows or [])
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.calls.append(("fetch_one", sql, params))
        return self.rows.pop(0) if self.rows else None


class FakeConnection:
    def __init__(self, transaction: FakeTransaction) -> None:
        self.transaction_obj = transaction

    def transaction(self):
        transaction_obj = self.transaction_obj

        class TransactionContext:
            def __enter__(self) -> FakeTransaction:
                return transaction_obj

            def __exit__(self, exc_type, exc, traceback) -> bool:
                return False

        return TransactionContext()


class FakeRuntimeQueue:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue(self, **kwargs):
        self.enqueued.append(kwargs)
        return kwargs


class FakeApplicationImportJobRepository:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.enqueued: list[ImportJob] = []

    def create_or_get_job(self, **kwargs) -> ImportJob:
        self.created.append(kwargs)
        return import_job(
            import_job_id="app-import-job-1",
            import_type=str(kwargs["import_type"]),
            tenant_id=str(kwargs.get("tenant_id") or "default"),
            priority=str(kwargs.get("priority") or "normal"),
        )

    def enqueue_process_requested(self, *, queue_repository, import_job: ImportJob, reason: str = "import_job_created"):
        self.enqueued.append(import_job)
        return queue_repository.enqueue(
            event_type=IMPORT_PROCESS_REQUESTED_EVENT,
            aggregate_type="import_job",
            aggregate_id=import_job.import_job_id,
            scope_type="import",
            scope_key=import_job.import_type,
            dedupe_key=f"{IMPORT_PROCESS_REQUESTED_EVENT}:{import_job.tenant_id}:{import_job.import_job_id}",
            payload={"import_job_id": import_job.import_job_id, "import_type": import_job.import_type, "reason": reason},
            tenant_id=import_job.tenant_id,
            source_version=0,
            priority=import_job.priority,
            trace_id=import_job.trace_id,
        )


class FakeImportJobRepository:
    def __init__(self, job: ImportJob | None) -> None:
        self.job = job
        self.processing: list[tuple[str, str]] = []
        self.succeeded: list[tuple[str, str, dict[str, object]]] = []
        self.failed: list[tuple[str, str, str, dict[str, object], str]] = []

    def mark_processing(self, import_job_id: str, *, worker_id: str):
        self.processing.append((import_job_id, worker_id))
        return self.job

    def get_job(self, import_job_id: str):
        return self.job

    def mark_succeeded(self, import_job_id: str, *, worker_id: str, result_payload=None, stage="succeeded"):
        self.succeeded.append((import_job_id, worker_id, result_payload or {}))
        return True

    def mark_failed(self, import_job_id: str, *, worker_id: str, error: str, result_payload=None, stage="failed"):
        self.failed.append((import_job_id, worker_id, error, result_payload or {}, stage))
        return True


def job_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "import_job_id": "job-1",
        "tenant_id": "default",
        "import_type": "bank_transactions.import",
        "import_session_id": "session-1",
        "source_file_id": "file-1",
        "idempotency_key": "bank_transactions.import:session-1",
        "status": "pending",
        "stage": "queued",
        "priority": "normal",
        "attempt_count": 0,
        "max_attempts": 5,
        "last_error": None,
        "payload": {"session_id": "session-1"},
        "result_payload": {},
        "raw_payload": {"source": "postgres"},
        "created_by": "operator",
        "trace_id": "trace-1",
    }
    row.update(overrides)
    return row


def import_job(**overrides: object) -> ImportJob:
    return ImportJob(
        import_job_id=str(overrides.get("import_job_id", "job-1")),
        tenant_id=str(overrides.get("tenant_id", "default")),
        import_type=str(overrides.get("import_type", "bank_transactions.import")),
        import_session_id="session-1",
        source_file_id="file-1",
        idempotency_key="bank_transactions.import:session-1",
        status=str(overrides.get("status", "pending")),
        stage=str(overrides.get("stage", "queued")),
        priority=str(overrides.get("priority", "normal")),
        attempt_count=int(overrides.get("attempt_count", 0)),
        max_attempts=int(overrides.get("max_attempts", 5)),
        last_error=None,
        payload=overrides.get("payload", {"session_id": "session-1"}),
        result_payload=overrides.get("result_payload", {}),
        raw_payload=overrides.get("raw_payload", {}),
        created_by="operator",
        trace_id="trace-1",
    )


class ImportJobRepositoryTests(unittest.TestCase):
    def test_create_or_get_job_uses_idempotency_key_and_returns_job(self) -> None:
        transaction = FakeTransaction(rows=[job_row()])
        repository = ImportJobRepository(FakeConnection(transaction))

        job = repository.create_or_get_job(
            import_type="bank_transactions.import",
            import_session_id="session-1",
            source_file_id="file-1",
            idempotency_key="bank_transactions.import:session-1",
            payload={"session_id": "session-1"},
            raw_payload={"source": "postgres"},
            created_by="operator",
            trace_id="trace-1",
        )

        self.assertEqual(job.import_job_id, "job-1")
        self.assertEqual(job.import_type, "bank_transactions.import")
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("insert into job.import_jobs", normalized_sql)
        self.assertIn("on conflict (tenant_id, idempotency_key)", normalized_sql)
        self.assertIn("where idempotency_key is not null", normalized_sql)
        self.assertEqual(params[:5], ("default", "bank_transactions.import", "session-1", "file-1", "bank_transactions.import:session-1"))

    def test_enqueue_process_requested_keeps_rabbitmq_envelope_small(self) -> None:
        repository = ImportJobRepository(FakeConnection(FakeTransaction()))
        queue = FakeRuntimeQueue()

        repository.enqueue_process_requested(queue_repository=queue, import_job=import_job(), reason="confirmed")

        self.assertEqual(len(queue.enqueued), 1)
        event = queue.enqueued[0]
        self.assertEqual(event["event_type"], IMPORT_PROCESS_REQUESTED_EVENT)
        self.assertEqual(event["aggregate_type"], "import_job")
        self.assertEqual(event["aggregate_id"], "job-1")
        self.assertEqual(event["scope_type"], "import")
        self.assertEqual(event["scope_key"], "bank_transactions.import")
        self.assertEqual(event["source_version"], 0)
        self.assertEqual(event["payload"], {"import_job_id": "job-1", "import_type": "bank_transactions.import", "reason": "confirmed"})

    def test_worker_marks_unknown_processor_failed_without_throwing(self) -> None:
        repository = FakeImportJobRepository(import_job())
        worker = ImportJobWorker(repository=repository, worker_id="worker-1", processors={})
        event = _runtime_event()

        result = worker.handle_runtime_event(event)

        self.assertEqual(result["error_code"], "processor_not_registered")
        self.assertEqual(repository.failed[0][0], "job-1")
        self.assertIn("not registered", repository.failed[0][2])
        self.assertEqual(repository.succeeded, [])

    def test_worker_runs_registered_processor_and_marks_success(self) -> None:
        repository = FakeImportJobRepository(import_job())
        worker = ImportJobWorker(
            repository=repository,
            worker_id="worker-1",
            processors={"bank_transactions.import": lambda job: {"row_count": 431}},
        )

        result = worker.handle_runtime_event(_runtime_event())

        self.assertTrue(result["processed"])
        self.assertEqual(result["row_count"], 431)
        self.assertEqual(repository.succeeded[0][0], "job-1")
        self.assertEqual(repository.failed, [])

    def test_worker_check_exposes_import_job_handler_and_route(self) -> None:
        stdout = StringIO()
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://fin_ops:secret@127.0.0.1:5432/fin_ops",
                "FIN_OPS_QUEUE_BACKEND": "rabbitmq",
                "RABBITMQ_URL": "amqp://rabbitmq.internal",
            },
            clear=True,
        ), redirect_stdout(stdout):
            exit_code = worker_app.main(["--check", "--enable-import-job-processing"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["worker_kind"], "import-job")
        self.assertEqual(payload["event_types"], [IMPORT_PROCESS_REQUESTED_EVENT])
        self.assertEqual(payload["handlers"], ["import.fact.changed", IMPORT_PROCESS_REQUESTED_EVENT])
        self.assertEqual(
            payload["rabbitmq_event_routes"][IMPORT_PROCESS_REQUESTED_EVENT]["queue"],
            "finops.import.process.requested",
        )

    def test_worker_check_claims_import_fact_changed_in_postgres_mode(self) -> None:
        stdout = StringIO()
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://fin_ops:secret@127.0.0.1:5432/fin_ops",
                "FIN_OPS_QUEUE_BACKEND": "postgres",
            },
            clear=True,
        ), redirect_stdout(stdout):
            exit_code = worker_app.main(["--check", "--enable-import-job-processing"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["worker_kind"], "import-job")
        self.assertEqual(payload["event_types"], [IMPORT_PROCESS_REQUESTED_EVENT, "import.fact.changed"])
        self.assertEqual(payload["handlers"], ["import.fact.changed", IMPORT_PROCESS_REQUESTED_EVENT])

    def test_general_import_confirm_queues_import_job_in_rabbitmq_mode(self) -> None:
        app = build_application()
        queue = FakeRuntimeQueue()
        import_jobs = FakeApplicationImportJobRepository()
        app._runtime_repositories = SimpleNamespace(  # noqa: SLF001
            queue_repository=queue,
            queue_settings=SimpleNamespace(backend="rabbitmq"),
        )
        app._import_job_repository = import_jobs  # noqa: SLF001
        preview_response = app.handle_request(
            "POST",
            "/imports/preview",
            json.dumps(
                {
                    "batch_type": "output_invoice",
                    "source_name": "rabbitmq-confirm.json",
                    "imported_by": "user_finance_01",
                    "rows": [
                        {
                            "invoice_code": "033001",
                            "invoice_no": "9901",
                            "counterparty_name": "Queued Corp",
                            "amount": "150.00",
                            "invoice_date": "2026-03-26",
                            "invoice_status_from_source": "valid",
                        }
                    ],
                }
            ),
        )
        batch_id = json.loads(preview_response.body)["batch"]["id"]

        with patch.dict(os.environ, {"FIN_OPS_IMPORT_PROCESSING_BACKEND": "rabbitmq"}):
            confirm_response = app.handle_request("POST", "/imports/confirm", json.dumps({"batch_id": batch_id}))

        self.assertEqual(confirm_response.status_code, 202)
        payload = json.loads(confirm_response.body)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["import_job"]["import_job_id"], "app-import-job-1")
        self.assertEqual(import_jobs.created[0]["import_type"], "general_import.confirm")
        self.assertEqual(import_jobs.created[0]["idempotency_key"], f"general_import.confirm:{batch_id}")
        self.assertEqual(queue.enqueued[0]["event_type"], IMPORT_PROCESS_REQUESTED_EVENT)
        batch_response = app.handle_request("GET", f"/imports/batches/{batch_id}")
        self.assertNotEqual(json.loads(batch_response.body)["batch"]["status"], "completed")

    def test_application_import_processor_registry_runs_general_import_confirm(self) -> None:
        app = build_application()
        preview_response = app.handle_request(
            "POST",
            "/imports/preview",
            json.dumps(
                {
                    "batch_type": "output_invoice",
                    "source_name": "processor-confirm.json",
                    "imported_by": "user_finance_01",
                    "rows": [
                        {
                            "invoice_code": "033001",
                            "invoice_no": "9902",
                            "counterparty_name": "Processor Corp",
                            "amount": "150.00",
                            "invoice_date": "2026-03-26",
                            "invoice_status_from_source": "valid",
                        }
                    ],
                }
            ),
        )
        batch_id = json.loads(preview_response.body)["batch"]["id"]
        processors = app.build_import_job_processors()

        result = processors["general_import.confirm"](
            import_job(import_type="general_import.confirm", payload={"batch_id": batch_id})
        )

        self.assertEqual(result["batch"]["status"], "completed")
        batch_response = app.handle_request("GET", f"/imports/batches/{batch_id}")
        self.assertEqual(json.loads(batch_response.body)["batch"]["status"], "completed")


def _runtime_event():
    from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent

    return RuntimeQueueEvent(
        event_id="event-1",
        tenant_id="default",
        event_type=IMPORT_PROCESS_REQUESTED_EVENT,
        aggregate_type="import_job",
        aggregate_id="job-1",
        scope_type="import",
        scope_key="bank_transactions.import",
        dedupe_key="import.process.requested:default:job-1",
        payload={"import_job_id": "job-1"},
        attempts=1,
        status="processing",
        source_version=0,
    )


if __name__ == "__main__":
    unittest.main()
