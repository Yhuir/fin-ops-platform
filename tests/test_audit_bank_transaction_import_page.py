from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import unittest

from fin_ops_platform.services.postgres_repositories import bank_transaction_import_page_audit
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class FakeConnection:
    def __init__(self) -> None:
        audit = bank_transaction_import_page_audit._zero_audit_counts()
        audit.update(
            {
                "original_count": 1,
                "unique_count": 1,
                "importable_count": 1,
                "confirmable_count": 1,
            }
        )
        self.files = [
            {
                "file_id": "file-1",
                "session_id": "session-1",
                "file_object_id": "object-1",
                "stored_file_path": "s3://bucket/imports/file-1.xlsx",
                "original_filename": "bank.xlsx",
                "template_kind": "bank_history_detail",
                "status": "confirmed",
                "uploaded_by": "operator",
                "storage_backend": "s3",
                "storage_uri": "s3://bucket/imports/file-1.xlsx",
                "object_key": "imports/file-1.xlsx",
                "sha256": "a" * 64,
                "size_bytes": 128,
                "audit_contract_revision": bank_transaction_import_page_audit.IMPORT_AUDIT_CONTRACT_REVISION,
                "raw_payload": {
                    "normalized_payload": {
                        "id": "file-1",
                        "session_id": "session-1",
                        "file_name": "bank.xlsx",
                        "stored_file_path": "s3://bucket/imports/file-1.xlsx",
                        "template_code": "bank_history_detail",
                        "batch_type": "bank_transaction",
                        "status": "confirmed",
                        "preview_batch_id": "batch-1",
                        "batch_id": "batch-1",
                        "file_count": 1,
                        "audit": audit,
                        "session_audit": audit,
                    }
                },
            }
        ]
        self.batches = [
            {
                "batch_id": "batch-1",
                "batch_type": "bank_transaction",
                "source_name": "bank.xlsx",
                "imported_by": "operator",
                "row_count": 1,
                "success_count": 1,
                "error_count": 0,
                "duplicate_count": 0,
                "suspected_duplicate_count": 0,
                "updated_count": 0,
                "status": "completed",
                "raw_payload": {
                    "normalized_payload": {
                        "id": "batch-1",
                        "batch_type": "bank_transaction",
                        "source_name": "bank.xlsx",
                        "imported_by": "operator",
                        "row_count": 1,
                        "success_count": 1,
                        "error_count": 0,
                        "duplicate_count": 0,
                        "suspected_duplicate_count": 0,
                        "updated_count": 0,
                        "status": "completed",
                    }
                },
            }
        ]
        self.rows = [
            {
                "row_id": "row-1",
                "batch_id": "batch-1",
                "row_no": 1,
                "source_record_type": "bank_transaction",
                "source_unique_key": "bank:key:1",
                "data_fingerprint": "fingerprint-1",
                "decision": "created",
                "decision_reason": "new",
                "linked_object_type": "bank_transaction",
                "linked_object_id": "txn-1",
                "identity_kind": "stable",
                "account_no": "62220001",
                "trade_time": "2026-07-01T10:00:00Z",
                "direction": "outflow",
                "amount": "100.00",
                "counterparty_name": "供应商",
                "raw_payload": {
                    "normalized_payload": {
                        "id": "row-1",
                        "row_no": 1,
                        "source_record_type": "bank_transaction",
                        "source_unique_key": "bank:key:1",
                        "data_fingerprint": "fingerprint-1",
                        "decision": "created",
                        "decision_reason": "new",
                        "linked_object_type": "bank_transaction",
                        "linked_object_id": "txn-1",
                        "identity_kind": "stable",
                        "account_no": "62220001",
                        "trade_time": "2026-07-01T10:00:00Z",
                        "direction": "outflow",
                        "amount": "100.00",
                        "counterparty_name": "供应商",
                    }
                },
            }
        ]
        self.transactions = [
            {
                "transaction_id": "txn-1",
                "batch_id": "batch-1",
                "account_no": "62220001",
                "txn_direction": "outflow",
                "counterparty_name_raw": "供应商",
                "amount": "100.00",
                "trade_time": "2026-07-01T10:00:00Z",
                "source_unique_key": "bank:key:1",
                "data_fingerprint": "fingerprint-1",
            }
        ]
        self.jobs = [
            {
                "job_id": "job-1",
                "import_session_id": "session-1",
                "status": "succeeded",
                "stage": "succeeded",
                "attempt_count": 1,
                "max_attempts": 5,
                "payload": {"session_id": "session-1", "selected_file_ids": ["file-1"]},
                "result_payload": {"session": {"files": [{"id": "file-1", "batch_id": "batch-1"}]}},
            }
        ]
        self.outbox: list[dict[str, object]] = []
        self.executed: list[str] = []

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append(sql)
        if sql.startswith("set transaction"):
            return 0
        if sql == "select set_config('statement_timeout', %s, true)":
            if params != ("60000",):
                raise AssertionError(f"Unexpected Audit statement timeout params: {params}")
            return 0
        raise AssertionError("Bank import Audit must be read-only")

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        if "from app.import_files" in sql:
            return deepcopy(self.files)
        if "from app.import_batches" in sql and "app.import_batch_rows" not in sql:
            return deepcopy(self.batches)
        if "from app.import_batch_rows" in sql:
            return deepcopy(self.rows)
        if "from app.bank_transactions" in sql:
            return deepcopy(self.transactions)
        if "from job.import_jobs" in sql:
            return deepcopy(self.jobs)
        if "from job.outbox_events" in sql:
            return deepcopy(self.outbox)
        raise AssertionError(sql)


class BankTransactionImportPageAuditTests(unittest.TestCase):
    def test_clean_file_session_batch_transaction_and_job_chain_passes(self) -> None:
        connection = FakeConnection()

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertTrue(report["audit_contract"]["database_snapshot"])
        self.assertEqual(
            connection.executed,
            [
                "set transaction isolation level repeatable read read only",
                "select set_config('statement_timeout', %s, true)",
            ],
        )

    def test_legacy_file_is_non_blocking_but_explicitly_unproven(self) -> None:
        connection = FakeConnection()
        connection.files[0]["audit_contract_revision"] = None

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertIn(
            "bank_import_legacy_provenance_unproven",
            report["summary"]["issue_sample_counts_by_code"],
        )
        self.assertEqual(report["summary"]["strict_contract_file_count"], 0)
        self.assertEqual(report["summary"]["legacy_file_count"], 1)

    def test_invoice_job_and_outbox_do_not_pollute_bank_page_queue(self) -> None:
        connection = FakeConnection()
        connection.jobs.append(
            {
                "job_id": "invoice-job",
                "import_session_id": "invoice-session",
                "status": "processing",
                "stage": "confirming",
                "attempt_count": 1,
                "max_attempts": 5,
                "payload": {"session_id": "invoice-session", "selected_file_ids": ["invoice-file"]},
                "result_payload": {},
            }
        )
        connection.outbox.append(
            {
                "event_id": "invoice-event",
                "aggregate_id": "invoice-job",
                "status": "pending",
                "last_error": None,
            }
        )

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        self.assertEqual(report["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertEqual(report["summary"]["bank_import_job_count"], 1)

    def test_unified_repository_dispatch_adds_registered_contract(self) -> None:
        report = PostgresOperationsAuditRepository(FakeConnection()).audit_page(
            page_key="imports.bank-transactions",
            tenant_id="default",
            sample_limit=20,
        )

        self.assertEqual(report["page_key"], "imports.bank-transactions")
        self.assertEqual(report["audit_contract"]["contract_revision"], "page-audit-contract.v27")
        self.assertEqual(report["audit_contract"]["registered_read_model_keys"], [])
        self.assertFalse(report["audit_contract"]["relation_proof_required"])

    def test_missing_canonical_transaction_is_blocking_in_both_directions(self) -> None:
        connection = FakeConnection()
        connection.transactions = []

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        codes = report["summary"]["issue_sample_counts_by_code"]
        self.assertIn("bank_import_row_transaction_orphan", codes)

    def test_duplicate_decision_can_reference_canonical_transaction_owned_by_older_batch(self) -> None:
        connection = FakeConnection()
        audit = bank_transaction_import_page_audit._zero_audit_counts()
        audit.update(
            {
                "original_count": 1,
                "unique_count": 1,
                "existing_duplicate_count": 1,
                "skipped_count": 1,
            }
        )
        connection.files[0]["raw_payload"]["normalized_payload"]["audit"] = audit
        connection.files[0]["raw_payload"]["normalized_payload"]["session_audit"] = audit
        connection.batches[0].update({"success_count": 0, "duplicate_count": 1})
        connection.batches[0]["raw_payload"]["normalized_payload"].update(
            {"success_count": 0, "duplicate_count": 1}
        )
        connection.rows[0].update(
            {
                "decision": "duplicate_skipped",
                "decision_reason": "existing",
                "linked_object_id": "txn-old",
            }
        )
        connection.rows[0]["raw_payload"]["normalized_payload"].update(
            {
                "decision": "duplicate_skipped",
                "decision_reason": "existing",
                "linked_object_id": "txn-old",
            }
        )
        connection.transactions[0].update({"transaction_id": "txn-old", "batch_id": "batch-old"})

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        self.assertEqual(report["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertEqual(report["summary"]["bank_import_owned_transaction_count"], 0)
        self.assertEqual(report["summary"]["bank_import_referenced_transaction_count"], 1)

    def test_batch_counts_are_recomputed_from_all_rows(self) -> None:
        connection = FakeConnection()
        connection.batches[0]["success_count"] = 2
        connection.batches[0]["raw_payload"]["normalized_payload"]["success_count"] = 2

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        self.assertIn("bank_import_batch_decision_count_mismatch", report["summary"]["issue_sample_counts_by_code"])

    def test_file_hash_registration_must_be_complete(self) -> None:
        connection = FakeConnection()
        connection.files[0]["sha256"] = None

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        self.assertIn("bank_import_file_hash_registration_incomplete", report["summary"]["issue_sample_counts_by_code"])

    def test_transaction_field_drift_is_blocking(self) -> None:
        connection = FakeConnection()
        connection.transactions[0]["amount"] = "99.99"

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        self.assertIn("bank_import_transaction_field_mismatch", report["summary"]["issue_sample_counts_by_code"])

    def test_active_job_and_outbox_block_freshness_and_queue(self) -> None:
        connection = FakeConnection()
        connection.jobs[0].update({"status": "processing", "stage": "confirming"})
        connection.outbox = [
            {
                "event_id": "event-1",
                "aggregate_id": "job-1",
                "status": "pending",
                "last_error": None,
            }
        ]

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        self.assertEqual(report["audit_status"]["integrity"], "pass")
        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "backlog")

    def test_retryable_failed_job_exposes_admin_safe_retry_coordinates(self) -> None:
        connection = FakeConnection()
        connection.jobs[0].update(
            {
                "status": "failed",
                "stage": "processor_failed",
                "attempt_count": 1,
                "max_attempts": 5,
                "last_error": "fixture processor failure",
            }
        )

        report = bank_transaction_import_page_audit.audit_bank_transaction_import_page(connection)

        issue = next(item for item in report["issues"] if item["code"] == "page_runtime_queue_not_drained")
        self.assertEqual(
            issue["details"],
            {
                "status": "failed",
                "stage": "processor_failed",
                "attempt_count": 1,
                "max_attempts": 5,
                "last_error": "fixture processor failure",
                "session_id": "session-1",
                "selected_file_ids": ["file-1"],
            },
        )


class BankTransactionImportPageAuditPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self._seed_clean_fixture()

    def _audit(self) -> dict[str, object]:
        return bank_transaction_import_page_audit.audit_bank_transaction_import_page(self.connection)

    def _seed_clean_fixture(self) -> None:
        audit = bank_transaction_import_page_audit._zero_audit_counts()
        audit.update(
            {
                "original_count": 1,
                "unique_count": 1,
                "importable_count": 1,
                "confirmable_count": 1,
            }
        )
        batch_payload = {
            "id": "batch-1",
            "batch_type": "bank_transaction",
            "source_name": "bank.xlsx",
            "imported_by": "operator",
            "row_count": 1,
            "success_count": 1,
            "error_count": 0,
            "duplicate_count": 0,
            "suspected_duplicate_count": 0,
            "updated_count": 0,
            "status": "completed",
        }
        row_payload = {
            "id": "row-1",
            "row_no": 1,
            "source_record_type": "bank_transaction",
            "source_unique_key": "bank:key:1",
            "data_fingerprint": "fingerprint-1",
            "decision": "created",
            "decision_reason": "new",
            "linked_object_type": "bank_transaction",
            "linked_object_id": "txn-1",
            "identity_kind": "stable",
            "account_no": "62220001",
            "trade_time": "2026-07-01T10:00:00Z",
            "direction": "outflow",
            "amount": "100.00",
            "counterparty_name": "供应商",
        }
        file_payload = {
            "id": "file-1",
            "session_id": "session-1",
            "file_name": "bank.xlsx",
            "stored_file_path": "s3://bucket/imports/file-1.xlsx",
            "template_code": "bank_history_detail",
            "batch_type": "bank_transaction",
            "status": "confirmed",
            "preview_batch_id": "batch-1",
            "batch_id": "batch-1",
            "file_count": 1,
            "audit": audit,
            "session_audit": audit,
        }
        self.connection.execute(
            """
            insert into app.import_batches(
                id, legacy_mongo_id, batch_type, source_name, imported_by, row_count,
                success_count, error_count, duplicate_count, suspected_duplicate_count,
                updated_count, status, imported_at, raw_payload
            ) values (
                '00000000-0000-0000-0000-000000000001', 'batch-1',
                'bank_transaction', 'bank.xlsx', 'operator', 1, 1, 0, 0, 0, 0,
                'completed', '2026-07-01T10:01:00Z', %s::jsonb
            )
            """,
            (json.dumps({"normalized_payload": batch_payload}),),
        )
        self.connection.execute(
            """
            insert into app.file_objects(
                id, legacy_mongo_id, storage_backend, storage_uri, object_key,
                filename, sha256, size_bytes, content_type, uploaded_at
            ) values (
                '00000000-0000-0000-0000-000000000003', 'object-1', 's3',
                's3://bucket/imports/file-1.xlsx', 'imports/file-1.xlsx', 'bank.xlsx',
                %s, 128, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '2026-07-01T09:59:00Z'
            )
            """,
            ("a" * 64,),
        )
        self.connection.execute(
            """
            insert into app.import_files(
                id, legacy_mongo_id, file_object_id, session_id,
                stored_file_path, original_filename, template_kind, status,
                uploaded_by, uploaded_at, raw_payload
            ) values (
                '00000000-0000-0000-0000-000000000004', 'file-1',
                '00000000-0000-0000-0000-000000000003', 'session-1',
                's3://bucket/imports/file-1.xlsx', 'bank.xlsx', 'bank_history_detail',
                'confirmed', 'operator', '2026-07-01T10:00:00Z', %s::jsonb
            )
            """,
            (json.dumps({"normalized_payload": file_payload}),),
        )
        self.connection.execute(
            """
            insert into app.import_batch_rows(
                id, legacy_mongo_id, import_batch_id, legacy_batch_id, row_no,
                source_record_type, source_unique_key, data_fingerprint, decision,
                decision_reason, linked_object_type, linked_object_id, identity_kind,
                account_no, trade_time, direction, amount, counterparty_name, raw_payload
            ) values (
                '00000000-0000-0000-0000-000000000002', 'row-1',
                '00000000-0000-0000-0000-000000000001', 'batch-1', 1,
                'bank_transaction', 'bank:key:1', 'fingerprint-1', 'created', 'new',
                'bank_transaction', 'txn-1', 'stable', '62220001',
                '2026-07-01T10:00:00Z', 'outflow', 100.00, '供应商', %s::jsonb
            )
            """,
            (json.dumps({"normalized_payload": row_payload}),),
        )
        self.connection.execute(
            """
            insert into app.bank_transactions(
                id, legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, bank_serial_no, source_unique_key, data_fingerprint,
                source_batch_id, legacy_source_batch_id, status
            ) values (
                '00000000-0000-0000-0000-000000000005', 'txn-1', '62220001',
                '测试账户', 'outflow', '供应商', 100.00, -100.00, '2026-07-01',
                '2026-07-01', '2026-07-01T10:00:00Z', 'serial-1', 'bank:key:1',
                'fingerprint-1', '00000000-0000-0000-0000-000000000001',
                'batch-1', 'active'
            )
            """
        )
        self.connection.execute(
            """
            insert into job.import_jobs(
                id, tenant_id, import_type, import_session_id, idempotency_key,
                status, stage, attempt_count, max_attempts, payload, result_payload,
                created_by, finished_at
            ) values (
                '00000000-0000-0000-0000-000000000006', 'default',
                'file_import.confirm', 'session-1', 'file_import.confirm:session-1:file-1',
                'succeeded', 'succeeded', 1, 5, %s::jsonb, %s::jsonb, 'operator', now()
            )
            """,
            (
                json.dumps({"session_id": "session-1", "selected_file_ids": ["file-1"]}),
                json.dumps({"session": {"files": [{"id": "file-1", "batch_id": "batch-1"}]}}),
            ),
        )

    def test_full_migration_clean_and_destructive_fail_closed_proof(self) -> None:
        clean = self._audit()
        self.assertEqual(clean["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertTrue(clean["audit_contract"]["database_snapshot"])

        self.connection.execute(
            "update app.bank_transactions set amount = 99.99 where legacy_mongo_id = 'txn-1'"
        )
        drift = self._audit()
        self.assertIn("bank_import_transaction_field_mismatch", drift["summary"]["issue_sample_counts_by_code"])
        self.connection.execute(
            "update app.bank_transactions set amount = 100.00 where legacy_mongo_id = 'txn-1'"
        )

        self.connection.execute("update app.file_objects set sha256 = null where legacy_mongo_id = 'object-1'")
        missing_hash = self._audit()
        self.assertIn(
            "bank_import_file_hash_registration_incomplete",
            missing_hash["summary"]["issue_sample_counts_by_code"],
        )
        self.connection.execute(
            "update app.file_objects set sha256 = %s where legacy_mongo_id = 'object-1'",
            ("a" * 64,),
        )

        self.connection.execute("delete from app.bank_transactions where legacy_mongo_id = 'txn-1'")
        missing_transaction = self._audit()
        self.assertIn(
            "bank_import_row_transaction_orphan",
            missing_transaction["summary"]["issue_sample_counts_by_code"],
        )
        self.connection.execute(
            """
            insert into app.bank_transactions(
                id, legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, bank_serial_no, source_unique_key, data_fingerprint,
                source_batch_id, legacy_source_batch_id, status
            ) values (
                '00000000-0000-0000-0000-000000000005', 'txn-1', '62220001',
                '测试账户', 'outflow', '供应商', 100.00, -100.00, '2026-07-01',
                '2026-07-01', '2026-07-01T10:00:00Z', 'serial-1', 'bank:key:1',
                'fingerprint-1', '00000000-0000-0000-0000-000000000001',
                'batch-1', 'active'
            )
            """
        )

        self.connection.execute(
            """
            update job.import_jobs
            set status = 'processing', stage = 'confirming', finished_at = null
            where id = '00000000-0000-0000-0000-000000000006'
            """
        )
        self.connection.execute(
            """
            insert into job.outbox_events(
                id, tenant_id, event_type, aggregate_type, aggregate_id, status,
                dedupe_key, payload
            ) values (
                '00000000-0000-0000-0000-000000000007', 'default',
                'import.process.requested', 'import_job',
                '00000000-0000-0000-0000-000000000006', 'pending',
                'import.process.requested:test:bank', '{}'::jsonb
            )
            """
        )
        active_queue = self._audit()
        self.assertEqual(active_queue["audit_status"]["integrity"], "pass")
        self.assertEqual(active_queue["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(active_queue["audit_status"]["queue"], "backlog")

        self.connection.execute(
            """
            update job.import_jobs
            set status = 'failed', stage = 'failed', attempt_count = max_attempts,
                last_error = 'fixture terminal failure'
            where id = '00000000-0000-0000-0000-000000000006'
            """
        )
        self.connection.execute(
            """
            update job.outbox_events
            set status = 'dead_lettered', last_error = 'fixture dead letter'
            where id = '00000000-0000-0000-0000-000000000007'
            """
        )
        terminal_failure = self._audit()
        codes = terminal_failure["summary"]["issue_sample_counts_by_code"]
        self.assertIn("bank_import_job_terminal_failure", codes)
        self.assertIn("bank_import_outbox_terminal_failure", codes)

    def test_naive_china_trade_time_is_compared_as_the_same_instant_and_real_drift_blocks(self) -> None:
        self.connection.execute(
            """
            update app.import_batch_rows
            set raw_payload = jsonb_set(
                raw_payload,
                '{normalized_payload,trade_time}',
                to_jsonb('2026-07-01 18:00:00'::text)
            )
            where legacy_mongo_id = 'row-1'
            """
        )

        equivalent_instant = self._audit()
        self.assertNotIn(
            "bank_import_row_formal_payload_mismatch",
            equivalent_instant["summary"]["issue_sample_counts_by_code"],
        )
        self.assertEqual(
            equivalent_instant["audit_status"],
            {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        )

        self.connection.execute(
            """
            update app.import_batch_rows
            set raw_payload = jsonb_set(
                raw_payload,
                '{normalized_payload,trade_time}',
                to_jsonb('2026-07-01 18:00:01'::text)
            )
            where legacy_mongo_id = 'row-1'
            """
        )

        drift = self._audit()
        self.assertIn(
            "bank_import_row_formal_payload_mismatch",
            drift["summary"]["issue_sample_counts_by_code"],
        )


if __name__ == "__main__":
    unittest.main()
