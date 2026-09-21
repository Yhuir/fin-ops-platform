from __future__ import annotations

import json
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.app import worker as worker_app
from fin_ops_platform.services.import_job_queue import (
    ImportJob,
    ImportJobIdempotencyConflict,
    ImportJobRepository,
    ImportJobWorker,
)
from fin_ops_platform.services.runtime_worker_handlers import (
    ImportRuntimeProcessorFactory,
    _input_invoice_usage_scope_keys_for_import_file_session,
    _output_invoice_collection_scope_keys_for_import_file_session,
    _tax_offset_scope_keys_for_import_file_session,
)

from tests.app_test_support import build_local_state_application as build_application
from tests.mock_import_files import CERTIFIED_JAN, MockImportFile


def build_multipart_payload(
    *,
    imported_by: str,
    files: list[MockImportFile],
) -> tuple[bytes, dict[str, str]]:
    boundary = "----finops-import-job-tax-certified-boundary"
    chunks: list[bytes] = []

    def add_text(name: str, value: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    def add_file(name: str, file: MockImportFile) -> None:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{file.name}"\r\n'
                "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(file.content)
        chunks.append(b"\r\n")

    add_text("imported_by", imported_by)
    for file in files:
        add_file("files", file)
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


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


def job_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "import_job_id": "job-1",
        "tenant_id": "default",
        "import_type": "bank_transactions.import",
        "import_session_id": "session-1",
        "source_file_id": "file-1",
        "idempotency_key": "bank_transactions.import:session-1",
        "request_fingerprint": "fingerprint-1",
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
        request_fingerprint=str(overrides.get("request_fingerprint", "fingerprint-1")),
        status=str(overrides.get("status", "pending")),
        stage=str(overrides.get("stage", "queued")),
        priority=str(overrides.get("priority", "normal")),
        attempt_count=int(overrides.get("attempt_count", 0)),
        max_attempts=int(overrides.get("max_attempts", 5)),
        last_error=None,
        payload=overrides.get("payload", {"session_id": "session-1"}),
        result_payload=overrides.get("result_payload", {}),
        raw_payload=overrides.get("raw_payload", {}),
        created_by=str(overrides.get("created_by", "operator")),
        trace_id="trace-1",
    )


class ImportJobRepositoryTests(unittest.TestCase):
    def test_runtime_import_processor_configures_object_storage_for_durable_archives(self) -> None:
        connection = object()
        repository = object()
        state_store = object()
        settings = SimpleNamespace(enabled=True)
        factory = ImportRuntimeProcessorFactory(data_dir="/tmp/finops-test", connection=connection)

        with (
            patch(
                "fin_ops_platform.services.object_storage.ObjectStorageSettings.from_env",
                return_value=settings,
            ) as settings_from_env,
            patch(
                "fin_ops_platform.services.object_storage.S3ObjectStorageRepository",
                return_value=repository,
            ) as repository_type,
            patch(
                "fin_ops_platform.services.postgres_state_store.PostgresStateStore",
                return_value=state_store,
            ) as state_store_type,
        ):
            result = factory._state_store()  # noqa: SLF001

        self.assertIs(result, state_store)
        settings_from_env.assert_called_once_with()
        repository_type.assert_called_once_with(settings)
        state_store_type.assert_called_once_with(
            data_dir="/tmp/finops-test",
            connection=connection,
            object_storage_repository=repository,
        )

    def test_runtime_import_processor_reloads_durable_state_after_worker_bootstrap(self) -> None:
        factory = ImportRuntimeProcessorFactory(data_dir="/tmp/finops-test", connection=object())
        generations: list[int] = []

        def build_current_processors(**kwargs):
            generation = len(generations) + 1
            generations.append(generation)
            return {"file_import.confirm": lambda _job: {"generation": generation}}

        with patch.object(
            factory,
            "_build_processors_from_durable_state",
            side_effect=build_current_processors,
        ) as builder:
            processors = factory.build_processors()

            self.assertEqual(builder.call_count, 0)
            self.assertEqual(processors["file_import.confirm"](import_job()), {"generation": 1})
            self.assertEqual(processors["file_import.confirm"](import_job()), {"generation": 2})

        self.assertEqual(generations, [1, 2])

    def test_runtime_import_processor_retries_and_persists_current_file_preview(self) -> None:
        state_store = SimpleNamespace(save_import_delta=unittest.mock.Mock())
        session = SimpleNamespace(id="session-1", status="preview_ready")
        file_import_service = SimpleNamespace(
            retry_session_files=unittest.mock.Mock(return_value=session),
            preview_session_persistence_payload=unittest.mock.Mock(return_value={"file_imports": {}}),
        )
        factory = ImportRuntimeProcessorFactory(data_dir="/tmp/finops-test", connection=object())

        with patch.object(
            factory,
            "_build_file_import_services_from_durable_state",
            return_value=(state_store, object(), file_import_service),
        ):
            result = factory.retry_file_import_preview(
                session_id="session-1",
                selected_file_ids=["file-1"],
            )

        file_import_service.retry_session_files.assert_called_once_with(
            session_id="session-1",
            selected_file_ids=["file-1"],
        )
        state_store.save_import_delta.assert_called_once_with({"file_imports": {}})
        self.assertEqual(result["selected_file_count"], 1)

    def test_postgres_import_processing_backend_uses_durable_queue_and_inline_is_rejected(self) -> None:
        app = build_application()
        app._runtime_repositories = SimpleNamespace(  # noqa: SLF001
            queue_repository=FakeRuntimeQueue(),
            queue_settings=SimpleNamespace(backend="postgres"),
        )

        with patch.dict(os.environ, {"FIN_OPS_IMPORT_PROCESSING_BACKEND": "postgres"}):
            self.assertEqual(app._import_processing_backend(), "postgres")  # noqa: SLF001

        with patch.dict(os.environ, {"FIN_OPS_IMPORT_PROCESSING_BACKEND": "inline"}):
            with self.assertRaisesRegex(RuntimeError, "must be postgres"):
                app._import_processing_backend()  # noqa: SLF001

    def test_invoice_relation_scope_helpers_split_input_and_output_file_months(self) -> None:
        session = SimpleNamespace(
            files=[
                SimpleNamespace(
                    id="file-input",
                    status="confirmed",
                    batch_type="input_invoice",
                    normalized_rows=[{"invoice_date": "2026-05-02"}],
                ),
                SimpleNamespace(
                    id="file-output",
                    status="confirmed",
                    batch_type="output_invoice",
                    normalized_rows=[{"invoice_date": "2026-06-03"}],
                ),
            ]
        )

        self.assertEqual(
            _input_invoice_usage_scope_keys_for_import_file_session(
                session,
                ["file-input", "file-output"],
            ),
            ["2026-05"],
        )
        self.assertEqual(
            _output_invoice_collection_scope_keys_for_import_file_session(
                session,
                ["file-input", "file-output"],
            ),
            ["2026-06"],
        )

    def test_tax_offset_scope_helpers_ignore_bank_transaction_files(self) -> None:
        session = SimpleNamespace(
            files=[
                SimpleNamespace(
                    id="file-bank",
                    status="confirmed",
                    batch_type="bank_transaction",
                    normalized_rows=[{"trade_time": "2026-05-02 10:00:00"}],
                ),
                SimpleNamespace(
                    id="file-input",
                    status="confirmed",
                    batch_type="input_invoice",
                    normalized_rows=[{"invoice_date": "2026-06-03"}],
                ),
            ]
        )

        self.assertEqual(
            _tax_offset_scope_keys_for_import_file_session(
                session,
                ["file-bank", "file-input"],
            ),
            ["2026-06"],
        )

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

    def test_create_or_get_job_rejects_same_key_with_different_request(self) -> None:
        repository = ImportJobRepository(FakeConnection(FakeTransaction(rows=[None])))

        with self.assertRaises(ImportJobIdempotencyConflict):
            repository.create_or_get_job(
                import_type="bank_transactions.import",
                import_session_id="session-2",
                idempotency_key="bank_transactions.import:shared-key",
                payload={"session_id": "session-2"},
            )

    def test_create_replay_does_not_mutate_existing_job_payload_or_status(self):
        transaction = FakeTransaction(rows=[job_row(status="pending", stage="commit")])
        repository = ImportJobRepository(FakeConnection(transaction))
        repository.create_or_get_job(import_type="file_import.confirm", idempotency_key="same", payload={})
        sql = " ".join(transaction.calls[0][1].lower().split())
        self.assertIn("do update set updated_at=job.import_jobs.updated_at", sql)
        self.assertNotIn("then excluded.payload", sql)

    def test_worker_check_reports_direct_import_queue_without_outbox_handler(self) -> None:
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
        self.assertEqual(payload["event_types"], [])
        self.assertEqual(payload["handlers"], [])
        self.assertEqual(payload["import_queue"], "job.import_jobs")
        self.assertEqual(len(payload["import_processors"]), 4)

    def test_tax_confirm_rejects_foreign_preview_before_claiming_idempotency_key(self) -> None:
        from fin_ops_platform.services.tax_certified_import_service import UploadedCertifiedImportFile
        app = build_application()
        self.addCleanup(app.close)
        session = app._tax_certified_import_service.preview_files(imported_by="other-owner", uploads=[
            UploadedCertifiedImportFile(file_name=CERTIFIED_JAN.name, content=CERTIFIED_JAN.content)])
        repository = FakeApplicationImportJobRepository()
        app._import_job_repository = repository
        response = app.handle_request('POST','/api/tax-offset/certified-import/confirm',json.dumps({'session_id':session.id}))
        self.assertEqual(response.status_code,404)
        self.assertEqual(json.loads(response.body)['error'],'tax_certified_import_session_not_found')
        self.assertEqual(repository.created,[])

    def test_tax_certified_import_confirm_queue_result_can_be_polled(self) -> None:
        app = build_application()
        queue = FakeRuntimeQueue()
        import_jobs = FakeApplicationImportJobRepository()
        app._runtime_repositories = SimpleNamespace(  # noqa: SLF001
            queue_repository=queue,
            queue_settings=SimpleNamespace(backend="postgres"),
        )
        app._import_job_repository = import_jobs  # noqa: SLF001
        preview_body, preview_headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[CERTIFIED_JAN],
        )
        preview_response = app.handle_request(
            "POST",
            "/api/tax-offset/certified-import/preview",
            body=preview_body,
            headers=preview_headers,
        )
        session_id = json.loads(preview_response.body)["session"]["id"]

        with patch.dict(os.environ, {"FIN_OPS_IMPORT_PROCESSING_BACKEND": "postgres"}):
            confirm_response = app.handle_request(
                "POST",
                "/api/tax-offset/certified-import/confirm",
                json.dumps({"session_id": session_id}),
            )

        self.assertEqual(confirm_response.status_code, 202)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["status"], "queued")
        self.assertEqual(confirm_payload["import_job"]["import_type"], "tax_certified_import.confirm")
        self.assertEqual(import_jobs.created[0]["idempotency_key"], f"tax_certified_import.confirm:{session_id}")
        self.assertEqual(queue.enqueued, [])

        batch_payload = {
            "id": "tax-certified-batch-1",
            "session_id": session_id,
            "imported_by": "user_finance_01",
            "file_count": 1,
            "months": ["2026-01"],
            "persisted_record_count": 2,
        }
        app._import_job_repository = SimpleNamespace(  # noqa: SLF001
            get_job=lambda import_job_id: import_job(
                import_job_id=import_job_id, created_by=import_jobs.created[0]["created_by"],
                import_type="tax_certified_import.confirm",
                import_session_id=session_id,
                status="succeeded",
                stage="succeeded",
                result_payload={"success": True, "batch": batch_payload},
            )
        )

        status_response = app.handle_request(
            "GET",
            f"/api/tax-offset/certified-import/jobs/{confirm_payload['import_job']['import_job_id']}",
        )

        self.assertEqual(status_response.status_code, 200)
        status_payload = json.loads(status_response.body)
        self.assertEqual(status_payload["import_job"]["status"], "succeeded")
        self.assertEqual(status_payload["import_job"]["result_payload"]["batch"]["persisted_record_count"], 2)

if __name__ == "__main__":
    unittest.main()
