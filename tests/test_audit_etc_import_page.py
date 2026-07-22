from __future__ import annotations

import unittest
import json

from fin_ops_platform.services.postgres_repositories import etc_import_page_audit
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database
from tests.test_audit_etc_tickets_read_model_tool import FakeConnection as EtcTicketsFakeConnection


class FakeConnection(EtcTicketsFakeConnection):
    def __init__(self) -> None:
        super().__init__()
        task_payload = self.tasks[0]["raw_payload"]["normalized_payload"]
        self.tasks[0]["status"] = "ready_for_import"
        self.tasks[0]["version"] = 3
        self.tasks[0]["result_summary"] = {"confirmed_item_set_hash": "confirmed-hash"}
        task_payload.update(
            {
                "status": "ready_for_import",
                "version": 3,
                "confirmed_item_set_hash": "confirmed-hash",
                "zip_preview_generation": 2,
            }
        )
        audit = {
            "original_count": 1,
            "unique_count": 1,
            "duplicate_count": 0,
            "duplicate_in_file_count": 0,
            "duplicate_across_files_count": 0,
            "existing_duplicate_count": 0,
            "importable_count": 1,
            "update_count": 0,
            "merge_count": 0,
            "suspected_duplicate_count": 0,
            "error_count": 0,
            "confirmable_count": 1,
            "skipped_count": 0,
        }
        preview_result = {
            "imported": 1,
            "duplicatesSkipped": 0,
            "attachmentsCompleted": 0,
            "failed": 0,
            "summary": {"imported": 1, "duplicatesSkipped": 0, "attachmentsCompleted": 0, "failed": 0},
            "audit": audit,
            "items": [
                {
                    "fileName": "ETC001.xml",
                    "invoiceNumber": "ETC001",
                    "status": "imported",
                    "filterStatus": "included",
                    "requirementId": "req-1",
                }
            ],
        }
        reconciliation_filter = {
            "taskId": "task-1",
            "taskVersion": 3,
            "confirmedItemSetHash": "confirmed-hash",
            "allowedInvoiceNumbers": ["ETC001"],
            "items": [
                {
                    "fileName": "ETC001.xml",
                    "invoiceNumber": "ETC001",
                    "filterStatus": "included",
                    "requirementId": "req-1",
                    "message": "",
                }
            ],
            "blockingIssues": [],
        }
        preview_files = [{"fileName": "input.zip", "audit": audit}]
        self.session_files = [
            {
                "session_id": "session-1",
                "file_id": "etc-import-0001",
                "ordinal": 0,
                "file_object_id": "object-1",
                "original_filename": "input.zip",
                "sha256": "zip-hash",
                "size_bytes": 120,
                "object_sha256": "zip-hash",
                "object_size_bytes": 120,
                "file_object_registered": True,
                "raw_payload": {
                    "normalized_payload": {
                        "file_id": "etc-import-0001",
                        "file_name": "input.zip",
                        "ordinal": 0,
                        "file_object_id": "object-1",
                        "stored_file_path": "minio://bucket/input.zip",
                        "sha256": "zip-hash",
                        "size_bytes": 120,
                    }
                },
            }
        ]
        session = {
            "session_id": "session-1",
            "audit_contract_revision": etc_import_page_audit.ETC_IMPORT_AUDIT_CONTRACT_REVISION,
            "status": "preview_ready",
            "task_id": "task-1",
            "task_version": 3,
            "zip_preview_generation": 2,
            "confirmed_item_set_hash": "confirmed-hash",
            "preview_fingerprint": "",
            "preview_summary": audit,
            "last_error": None,
            "created_at": "2026-07-11T00:00:00+00:00",
            "updated_at": "2026-07-11T00:00:00+00:00",
        }
        session_payload = {
            **session,
            "preview_result": preview_result,
            "preview_audit": audit,
            "preview_files": preview_files,
            "reconciliation_filter": reconciliation_filter,
        }
        session["raw_payload"] = {"normalized_payload": session_payload}
        session["preview_fingerprint"] = etc_import_page_audit._stored_preview_fingerprint(
            row=session,
            files=self.session_files,
            preview_result=preview_result,
            reconciliation_filter=reconciliation_filter,
        )
        session_payload["preview_fingerprint"] = session["preview_fingerprint"]
        self.sessions = [session]
        self.outbox: list[dict[str, object]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        if "from app.etc_import_session_files" in sql:
            return [dict(row) for row in self.session_files]
        if "from app.etc_import_sessions session" in sql:
            return [dict(row) for row in self.sessions]
        if "from job.outbox_events" in sql:
            return [dict(row) for row in self.outbox]
        return super().fetch_all(sql, params)


class EtcImportPageAuditTests(unittest.TestCase):
    def test_succeeded_session_accepts_later_closed_task_state(self) -> None:
        facts = {
            "tasks": [{"task_id": "task-1", "status": "closed", "raw_payload": {}}],
            "batches": [
                {
                    "business_batch_id": "business-batch-1",
                    "raw_payload": {"normalized_payload": {"import_attempts": [{"session_id": "session-1"}]}},
                }
            ],
            "import_batches": [
                {
                    "batch_id": "import-batch-1",
                    "raw_payload": {
                        "normalized_payload": {"source_session_id": "session-1", "invoice_ids": []}
                    },
                }
            ],
            "invoices": [],
        }
        succeeded_issues = etc_import_page_audit._session_task_edge_issues(
            sessions=[{"session_id": "session-1", "task_id": "task-1", "status": "succeeded"}],
            facts=facts,
        )

        self.assertNotIn(
            "etc_import_terminal_task_status_mismatch",
            {issue.code for issue in succeeded_issues},
        )

        partial_issues = etc_import_page_audit._session_task_edge_issues(
            sessions=[{"session_id": "session-1", "task_id": "task-1", "status": "partial_success"}],
            facts=facts,
        )
        self.assertIn(
            "etc_import_terminal_task_status_mismatch",
            {issue.code for issue in partial_issues},
        )

    def test_failed_session_and_job_are_non_blocking_only_after_formal_task_completion(self) -> None:
        connection = FakeConnection()
        connection.tasks[0]["status"] = "imported"
        connection.tasks[0]["raw_payload"]["normalized_payload"]["status"] = "imported"
        connection.sessions[0]["status"] = "failed"
        connection.sessions[0]["last_error"] = "worker acknowledgement failed"
        session_payload = connection.sessions[0]["raw_payload"]["normalized_payload"]
        session_payload["status"] = "failed"
        session_payload["last_error"] = "worker acknowledgement failed"
        connection.import_jobs = [
            {
                "job_id": "job-1",
                "import_session_id": "session-1",
                "status": "failed",
                "attempt_count": 1,
                "max_attempts": 5,
                "task_status": "imported",
            }
        ]

        report = etc_import_page_audit.audit_etc_import_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["summary"]["covered_session_count"], 1)
        self.assertIn(
            "etc_import_session_failure_covered",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_failed_session_remains_blocking_without_formal_task_completion(self) -> None:
        connection = FakeConnection()
        connection.sessions[0]["status"] = "failed"
        connection.sessions[0]["raw_payload"]["normalized_payload"]["status"] = "failed"

        report = etc_import_page_audit.audit_etc_import_page(connection)

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertIn(
            "etc_import_session_terminal_failure",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_clean_registered_preview_passes(self) -> None:
        report = etc_import_page_audit.audit_etc_import_page(FakeConnection())

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(
            report["audit_status"],
            {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        )
        self.assertEqual(report["audit_contract"]["read_model_tables"], [])

    def test_legacy_session_is_non_blocking_but_explicitly_unproven(self) -> None:
        connection = FakeConnection()
        connection.sessions[0]["audit_contract_revision"] = None

        report = etc_import_page_audit.audit_etc_import_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertIn(
            "etc_import_legacy_session_provenance_unproven",
            report["summary"]["issue_sample_counts_by_code"],
        )
        self.assertEqual(report["summary"]["strict_contract_session_count"], 0)
        self.assertEqual(report["summary"]["legacy_session_count"], 1)

    def test_archive_hash_drift_fails_closed(self) -> None:
        connection = FakeConnection()
        connection.session_files[0]["object_sha256"] = "wrong"

        report = etc_import_page_audit.audit_etc_import_page(connection)

        self.assertIn("etc_import_file_object_field_mismatch", report["summary"]["issue_sample_counts_by_code"])

    def test_preview_requirement_edge_omission_fails_closed(self) -> None:
        connection = FakeConnection()
        payload = connection.sessions[0]["raw_payload"]["normalized_payload"]
        payload["preview_result"]["items"] = []

        report = etc_import_page_audit.audit_etc_import_page(connection)

        codes = report["summary"]["issue_sample_counts_by_code"]
        self.assertIn("etc_import_preview_requirement_edge_mismatch", codes)
        self.assertIn("etc_import_session_fingerprint_mismatch", codes)

    def test_active_job_and_outbox_block_freshness_and_queue(self) -> None:
        connection = FakeConnection()
        connection.import_jobs = [
            {
                "job_id": "job-1",
                "import_session_id": "session-1",
                "status": "pending",
                "attempt_count": 0,
                "max_attempts": 5,
            }
        ]
        connection.outbox = [
            {
                "event_id": "event-1",
                "aggregate_id": "job-1",
                "status": "pending",
                "attempt_count": 0,
                "max_attempts": 5,
            }
        ]

        report = etc_import_page_audit.audit_etc_import_page(connection)

        self.assertEqual(report["audit_status"]["integrity"], "pass")
        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "backlog")


class EtcImportPageAuditPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self._seed_clean_preview()

    def _seed_clean_preview(self) -> None:
        fixture = FakeConnection()
        task = fixture.tasks[0]
        session = fixture.sessions[0]
        file_row = fixture.session_files[0]
        self.connection.execute(
            """
            insert into app.etc_reconciliation_tasks(
                legacy_mongo_id, task_id, status, scope_month, result_summary, version, raw_payload
            ) values ('task-1', 'task-1', 'ready_for_import', '2026-07-01', %s::jsonb, 3, %s::jsonb)
            """,
            (json.dumps(task["result_summary"]), json.dumps(task["raw_payload"])),
        )
        self.connection.execute(
            """
            insert into app.file_objects(
                id, legacy_mongo_id, storage_backend, storage_uri, bucket_name, object_key,
                filename, sha256, size_bytes, migration_status, uploaded_at
            ) values (
                '00000000-0000-0000-0000-000000000201', 'object-1', 'minio',
                'minio://bucket/input.zip', 'bucket', 'objects/etc/input.zip', 'input.zip',
                'zip-hash', 120, 'verified', now()
            )
            """
        )
        self.connection.execute(
            """
            insert into app.etc_import_sessions(
                id, legacy_mongo_id, session_id, status, imported_by, imported_at,
                task_id, task_version, zip_preview_generation, confirmed_item_set_hash,
                preview_fingerprint, preview_summary, raw_payload
            ) values (
                '00000000-0000-0000-0000-000000000202', 'session-1', 'session-1',
                'preview_ready', null, now(), 'task-1', 3, 2, 'confirmed-hash',
                %s, %s::jsonb, %s::jsonb
            )
            """,
            (
                session["preview_fingerprint"],
                json.dumps(session["preview_summary"]),
                json.dumps(session["raw_payload"]),
            ),
        )
        self.connection.execute(
            """
            insert into app.etc_import_session_files(
                id, session_id, file_id, ordinal, file_object_id, original_filename,
                sha256, size_bytes, raw_payload
            ) values (
                '00000000-0000-0000-0000-000000000203',
                '00000000-0000-0000-0000-000000000202', 'etc-import-0001', 0,
                '00000000-0000-0000-0000-000000000201', 'input.zip', 'zip-hash', 120, %s::jsonb
            )
            """,
            (json.dumps(file_row["raw_payload"]),),
        )

    def _audit(self) -> dict[str, object]:
        return etc_import_page_audit.audit_etc_import_page(self.connection)

    def test_full_migration_clean_and_destructive_fail_closed_proof(self) -> None:
        clean = self._audit()
        self.assertEqual(clean["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertTrue(clean["audit_contract"]["database_snapshot"])

        self.connection.execute(
            "update app.file_objects set sha256 = 'wrong' where id = '00000000-0000-0000-0000-000000000201'"
        )
        hash_drift = self._audit()
        self.assertIn("etc_import_file_object_field_mismatch", hash_drift["summary"]["issue_sample_counts_by_code"])
        self.connection.execute(
            "update app.file_objects set sha256 = 'zip-hash' where id = '00000000-0000-0000-0000-000000000201'"
        )

        payload = FakeConnection().sessions[0]["raw_payload"]["normalized_payload"]
        payload["preview_result"]["items"] = []
        self.connection.execute(
            "update app.etc_import_sessions set raw_payload = %s::jsonb where session_id = 'session-1'",
            (json.dumps({"normalized_payload": payload}),),
        )
        relation_omission = self._audit()
        self.assertIn(
            "etc_import_preview_requirement_edge_mismatch",
            relation_omission["summary"]["issue_sample_counts_by_code"],
        )


if __name__ == "__main__":
    unittest.main()
