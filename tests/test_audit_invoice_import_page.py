from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import unittest

from fin_ops_platform.services.postgres_repositories import invoice_import_page_audit
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class FakeConnection:
    def __init__(self) -> None:
        audit = invoice_import_page_audit._zero_audit_counts()
        audit.update(
            {
                "original_count": 1,
                "unique_count": 1,
                "importable_count": 1,
                "confirmable_count": 1,
            }
        )
        normalized_row = {
            "counterparty_name": "供应商甲",
            "invoice_code": "253000000001",
            "invoice_no": "00000001",
            "digital_invoice_no": "25300000000100000001",
            "invoice_status_from_source": "正常",
            "seller_tax_no": "915300000000000001",
            "seller_name": "供应商甲",
            "buyer_tax_no": "915300007194052520",
            "buyer_name": "云南溯源科技有限公司",
            "invoice_date": "2026-07-01",
            "amount": "100.00",
            "signed_amount": "100.00",
            "tax_rate": "13%",
            "tax_amount": "13.00",
            "total_with_tax": "113.00",
            "source_unique_key": "25300000000100000001",
            "data_fingerprint": "invoice-fingerprint-1",
            "invoice_type": "input",
        }
        self.files = [
            {
                "file_id": "file-1",
                "session_id": "session-1",
                "file_object_id": "object-1",
                "stored_file_path": "s3://bucket/imports/invoice-1.xlsx",
                "original_filename": "invoice.xlsx",
                "template_kind": "invoice_export",
                "status": "confirmed",
                "uploaded_by": "operator",
                "storage_backend": "s3",
                "storage_uri": "s3://bucket/imports/invoice-1.xlsx",
                "object_key": "imports/invoice-1.xlsx",
                "sha256": "a" * 64,
                "size_bytes": 256,
                "audit_contract_revision": invoice_import_page_audit.IMPORT_AUDIT_CONTRACT_REVISION,
                "raw_payload": {
                    "normalized_payload": {
                        "id": "file-1",
                        "session_id": "session-1",
                        "file_name": "invoice.xlsx",
                        "stored_file_path": "s3://bucket/imports/invoice-1.xlsx",
                        "template_code": "invoice_export",
                        "batch_type": "input_invoice",
                        "status": "confirmed",
                        "preview_batch_id": "batch-1",
                        "batch_id": "batch-1",
                        "audit": audit,
                        "session_audit": audit,
                    }
                },
            }
        ]
        self.batches = [
            {
                "batch_id": "batch-1",
                "batch_type": "input_invoice",
                "source_name": "invoice.xlsx",
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
                        "batch_type": "input_invoice",
                        "source_name": "invoice.xlsx",
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
                "source_record_type": "invoice",
                "source_unique_key": "25300000000100000001",
                "data_fingerprint": "invoice-fingerprint-1",
                "decision": "created",
                "decision_reason": "new",
                "linked_object_type": "invoice",
                "linked_object_id": "invoice-1",
                "identity_kind": None,
                "raw_payload": {
                    "normalized_payload": {
                        "id": "row-1",
                        "row_no": 1,
                        "source_record_type": "invoice",
                        "source_unique_key": "25300000000100000001",
                        "data_fingerprint": "invoice-fingerprint-1",
                        "decision": "created",
                        "decision_reason": "new",
                        "linked_object_type": "invoice",
                        "linked_object_id": "invoice-1",
                        "identity_kind": None,
                        "normalized_row": normalized_row,
                    }
                },
            }
        ]
        self.invoices = [
            {
                "invoice_id": "invoice-1",
                "invoice_type": "input",
                "invoice_no": "25300000000100000001",
                "invoice_code": "253000000001",
                "digital_invoice_no": "25300000000100000001",
                "source_unique_key": "25300000000100000001",
                "data_fingerprint": None,
                "invoice_date": "2026-07-01",
                "counterparty_name": "供应商甲",
                "seller_name": "供应商甲",
                "seller_tax_no": "915300000000000001",
                "buyer_name": "云南溯源科技有限公司",
                "buyer_tax_no": "915300007194052520",
                "amount": "100.00",
                "signed_amount": "100.00",
                "tax_rate": "13%",
                "tax_amount": "13.00",
                "total_with_tax": "113.00",
                "source_batch_id": "batch-1",
                "status": "pending",
                "source_links": [
                    {
                        "source_type": "manual_invoice_import",
                        "source_id": "25300000000100000001",
                        "batch_id": "batch-1",
                        "created_at": "2026-07-01T10:01:00+00:00",
                    }
                ],
                "raw_payload": {
                    "normalized_payload": {
                        "invoice_type": "input",
                        "invoice_no": "25300000000100000001",
                        "invoice_code": "253000000001",
                        "digital_invoice_no": "25300000000100000001",
                        "source_unique_key": "25300000000100000001",
                        "data_fingerprint": None,
                        "invoice_date": "2026-07-01",
                        "counterparty_name": "供应商甲",
                        "seller_name": "供应商甲",
                        "seller_tax_no": "915300000000000001",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052520",
                        "amount": "100.00",
                        "signed_amount": "100.00",
                        "tax_rate": "13%",
                        "tax_amount": "13.00",
                        "total_with_tax": "113.00",
                        "invoice_status_from_source": "正常",
                        "source_links": [
                            {
                                "source_type": "manual_invoice_import",
                                "source_id": "25300000000100000001",
                                "batch_id": "batch-1",
                                "created_at": "2026-07-01T10:01:00+00:00",
                            }
                        ],
                    }
                },
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
                "result_payload": {"confirmed": 1},
            },
            {
                "job_id": "bank-job",
                "import_session_id": "bank-session",
                "status": "processing",
                "stage": "confirming",
                "attempt_count": 1,
                "max_attempts": 5,
                "payload": {"session_id": "bank-session", "selected_file_ids": ["bank-file"]},
                "result_payload": {},
            },
        ]
        self.outbox = [
            {"event_id": "bank-event", "aggregate_id": "bank-job", "status": "pending", "last_error": None}
        ]
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
        raise AssertionError("Invoice import Audit must be read-only")

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        if "from app.import_files" in sql:
            return deepcopy(self.files)
        if "from app.import_batches" in sql and "app.import_batch_rows" not in sql:
            return deepcopy(self.batches)
        if "from app.import_batch_rows" in sql:
            return deepcopy(self.rows)
        if "from app.invoices" in sql:
            return deepcopy(self.invoices)
        if "from job.import_jobs" in sql:
            return deepcopy(self.jobs)
        if "from job.outbox_events" in sql:
            return deepcopy(self.outbox)
        raise AssertionError(sql)


class InvoiceImportPageAuditTests(unittest.TestCase):
    def test_logical_manual_entry_does_not_fabricate_a_physical_file_object(self) -> None:
        connection = FakeConnection()
        file_row = connection.files[0]
        file_payload = file_row["raw_payload"]["normalized_payload"]
        file_row.update(
            {
                "file_object_id": None,
                "stored_file_path": "",
                "original_filename": "发票录入",
                "template_kind": "manual_invoice_entry",
                "status": "reverted",
                "storage_uri": None,
                "sha256": None,
                "size_bytes": None,
            }
        )
        file_payload.update(
            {
                "file_name": "发票录入",
                "stored_file_path": "",
                "template_code": "manual_invoice_entry",
                "status": "reverted",
            }
        )
        connection.batches[0]["status"] = "reverted"
        connection.batches[0]["raw_payload"]["normalized_payload"]["status"] = "reverted"

        issues = invoice_import_page_audit._file_issues(
            connection.files,
            connection.files,
            connection.batches,
        )
        issue_codes = {issue.code for issue in issues}

        self.assertNotIn("invoice_import_file_object_missing", issue_codes)
        self.assertNotIn("invoice_import_file_hash_registration_incomplete", issue_codes)

    def test_distinct_line_components_are_compared_as_one_invoice_total(self) -> None:
        connection = FakeConnection()
        first = connection.rows[0]
        first_normalized = first["raw_payload"]["normalized_payload"]["normalized_row"]
        first_normalized.update(
            {
                "taxable_item_name": "服务",
                "amount": "39.58",
                "signed_amount": "39.58",
                "tax_amount": "5.15",
                "total_with_tax": "44.73",
            }
        )
        second = deepcopy(first)
        second["row_id"] = "row-2"
        second["row_no"] = 2
        second_normalized = second["raw_payload"]["normalized_payload"]["normalized_row"]
        second_normalized.update(
            {
                "taxable_item_name": "折扣",
                "amount": "-1.77",
                "signed_amount": "-1.77",
                "tax_amount": "-0.23",
                "total_with_tax": "-2.00",
            }
        )
        invoice = connection.invoices[0]
        invoice.update({"amount": "37.81", "signed_amount": "37.81", "tax_amount": "4.92", "total_with_tax": "42.73"})

        issues = invoice_import_page_audit._invoice_component_field_issues(
            [first, second],
            invoice,
            batch_type="input_invoice",
        )

        self.assertEqual(issues, [])

    def test_identical_duplicate_lines_are_not_added_to_canonical_invoice_total(self) -> None:
        connection = FakeConnection()
        first = connection.rows[0]
        second = deepcopy(first)
        second["row_id"] = "row-2"
        second["row_no"] = 2

        issues = invoice_import_page_audit._invoice_component_field_issues(
            [first, second],
            connection.invoices[0],
            batch_type="input_invoice",
        )

        self.assertEqual(issues, [])

    def test_clean_direct_canonical_chain_passes_and_other_page_queue_is_ignored(self) -> None:
        connection = FakeConnection()

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertTrue(report["audit_contract"]["database_snapshot"])
        self.assertEqual(report["summary"]["invoice_import_job_count"], 1)

    def test_formally_reverted_preview_batch_is_not_reported_as_invalid(self) -> None:
        connection = FakeConnection()
        connection.files[0]["status"] = "reverted"
        connection.files[0]["raw_payload"]["normalized_payload"].update(
            {"status": "reverted", "session_status": "reverted", "batch_id": None}
        )
        connection.batches[0]["status"] = "reverted"
        connection.batches[0]["raw_payload"]["normalized_payload"]["status"] = "reverted"
        connection.rows = []
        connection.invoices = []
        connection.jobs = []
        connection.outbox = []
        batch = connection.batches[0]
        batch.update(
            {
                "row_count": 0,
                "success_count": 0,
                "error_count": 0,
                "duplicate_count": 0,
                "suspected_duplicate_count": 0,
                "updated_count": 0,
            }
        )
        batch["raw_payload"]["normalized_payload"].update(
            {
                "row_count": 0,
                "success_count": 0,
                "error_count": 0,
                "duplicate_count": 0,
                "suspected_duplicate_count": 0,
                "updated_count": 0,
            }
        )

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertNotIn(
            "invoice_import_batch_status_invalid",
            report["summary"]["issue_sample_counts_by_code"],
        )
        self.assertNotIn(
            "invoice_import_batch_formal_payload_mismatch",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_legacy_file_is_non_blocking_but_explicitly_unproven(self) -> None:
        connection = FakeConnection()
        connection.files[0]["audit_contract_revision"] = None

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertIn(
            "invoice_import_legacy_provenance_unproven",
            report["summary"]["issue_sample_counts_by_code"],
        )
        self.assertEqual(report["summary"]["strict_contract_file_count"], 0)
        self.assertEqual(report["summary"]["legacy_file_count"], 1)

    def test_formal_invoice_may_retain_a_known_legacy_batch_source_link(self) -> None:
        connection = FakeConnection()
        legacy_file = deepcopy(connection.files[0])
        legacy_file.update(
            {
                "file_id": "legacy-file-1",
                "session_id": "legacy-session-1",
                "audit_contract_revision": None,
            }
        )
        legacy_file_payload = legacy_file["raw_payload"]["normalized_payload"]
        legacy_file_payload.update(
            {
                "id": "legacy-file-1",
                "session_id": "legacy-session-1",
                "preview_batch_id": "legacy-batch-1",
                "batch_id": "legacy-batch-1",
            }
        )
        legacy_batch = deepcopy(connection.batches[0])
        legacy_batch["batch_id"] = "legacy-batch-1"
        legacy_batch["raw_payload"]["normalized_payload"]["id"] = "legacy-batch-1"
        connection.files.append(legacy_file)
        connection.batches.append(legacy_batch)
        legacy_source_link = {
            "source_type": "manual_invoice_import",
            "source_id": "legacy-source-1",
            "batch_id": "legacy-batch-1",
            "created_at": "2026-06-01T10:01:00+00:00",
        }
        connection.invoices[0]["source_links"].append(legacy_source_link)
        connection.invoices[0]["raw_payload"]["normalized_payload"]["source_links"].append(
            deepcopy(legacy_source_link)
        )

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertEqual(report["overall_status"], "pass", report)
        codes = report["summary"]["issue_sample_counts_by_code"]
        self.assertIn("invoice_import_legacy_provenance_unproven", codes)
        self.assertNotIn("invoice_import_source_link_batch_orphan", codes)
        self.assertNotIn("invoice_import_manual_source_link_orphan", codes)

    def test_formal_invoice_source_link_to_unknown_batch_still_fails_closed(self) -> None:
        connection = FakeConnection()
        unknown_source_link = {
            "source_type": "manual_invoice_import",
            "source_id": "unknown-source-1",
            "batch_id": "missing-batch-1",
            "created_at": "2026-06-01T10:01:00+00:00",
        }
        connection.invoices[0]["source_links"].append(unknown_source_link)
        connection.invoices[0]["raw_payload"]["normalized_payload"]["source_links"].append(
            deepcopy(unknown_source_link)
        )

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertIn(
            "invoice_import_source_link_batch_orphan",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_formal_invoice_may_retain_exact_etc_import_source_owner(self) -> None:
        connection = FakeConnection()
        connection.invoices[0]["source_batch_id"] = "etc_import_batch_0018"
        etc_source_link = {
            "source_type": "etc_invoice_import",
            "source_id": "etc_invoice_0018",
            "batch_id": "etc_import_batch_0018",
            "created_at": "2026-07-01T10:02:00+00:00",
        }
        connection.invoices[0]["source_links"].append(etc_source_link)
        connection.invoices[0]["raw_payload"]["normalized_payload"]["source_links"].append(
            deepcopy(etc_source_link)
        )

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertEqual(report["overall_status"], "pass", report)
        self.assertNotIn(
            "invoice_import_source_batch_not_in_manual_links",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_formal_invoice_unknown_source_owner_still_fails_closed(self) -> None:
        connection = FakeConnection()
        connection.invoices[0]["source_batch_id"] = "unregistered-owner"

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertIn(
            "invoice_import_source_batch_not_in_manual_links",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_formal_invoice_source_link_to_non_invoice_batch_still_fails_closed(self) -> None:
        connection = FakeConnection()
        non_invoice_batch = deepcopy(connection.batches[0])
        non_invoice_batch.update({"batch_id": "bank-batch-1", "batch_type": "bank_transaction"})
        non_invoice_batch_payload = non_invoice_batch["raw_payload"]["normalized_payload"]
        non_invoice_batch_payload.update({"id": "bank-batch-1", "batch_type": "bank_transaction"})
        connection.batches.append(non_invoice_batch)
        invalid_source_link = {
            "source_type": "manual_invoice_import",
            "source_id": "bank-source-1",
            "batch_id": "bank-batch-1",
            "created_at": "2026-06-01T10:01:00+00:00",
        }
        connection.invoices[0]["source_links"].append(invalid_source_link)
        connection.invoices[0]["raw_payload"]["normalized_payload"]["source_links"].append(
            deepcopy(invalid_source_link)
        )

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertIn(
            "invoice_import_source_link_batch_orphan",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_dispatch_registers_zero_read_model_relation_nonconsumer_contract(self) -> None:
        report = PostgresOperationsAuditRepository(FakeConnection()).audit_page(
            page_key="imports.invoices",
            tenant_id="default",
            sample_limit=20,
        )

        self.assertEqual(report["audit_contract"]["contract_revision"], "page-audit-contract.v28")
        self.assertEqual(report["audit_contract"]["registered_read_model_keys"], [])
        self.assertFalse(report["audit_contract"]["relation_proof_required"])

    def test_missing_invoice_and_missing_source_link_fail_closed(self) -> None:
        connection = FakeConnection()
        connection.invoices = []

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertIn("invoice_import_row_invoice_orphan", report["summary"]["issue_sample_counts_by_code"])

        connection = FakeConnection()
        connection.invoices[0]["source_links"] = []
        missing_link = invoice_import_page_audit.audit_invoice_import_page(connection)
        self.assertIn("invoice_import_manual_source_link_missing", missing_link["summary"]["issue_sample_counts_by_code"])

    def test_critical_field_drift_and_batch_count_drift_fail_closed(self) -> None:
        connection = FakeConnection()
        connection.invoices[0]["amount"] = "99.00"
        connection.batches[0]["success_count"] = 2
        connection.batches[0]["raw_payload"]["normalized_payload"]["success_count"] = 2

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        codes = report["summary"]["issue_sample_counts_by_code"]
        self.assertIn("invoice_import_invoice_field_mismatch", codes)
        self.assertIn("invoice_import_batch_decision_count_mismatch", codes)

    def test_owned_active_job_and_outbox_block_freshness_and_queue_only(self) -> None:
        connection = FakeConnection()
        connection.jobs[0].update({"status": "processing", "stage": "confirming"})
        connection.outbox.append(
            {"event_id": "event-1", "aggregate_id": "job-1", "status": "pending", "last_error": None}
        )

        report = invoice_import_page_audit.audit_invoice_import_page(connection)

        self.assertEqual(report["audit_status"]["integrity"], "pass")
        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "backlog")


class InvoiceImportPageAuditPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self._seed_clean_fixture()

    def _audit(self) -> dict[str, object]:
        return invoice_import_page_audit.audit_invoice_import_page(self.connection)

    def _seed_clean_fixture(self) -> None:
        fixture = FakeConnection()
        batch_payload = fixture.batches[0]["raw_payload"]
        file_payload = fixture.files[0]["raw_payload"]
        row_payload = fixture.rows[0]["raw_payload"]
        invoice_payload = fixture.invoices[0]["raw_payload"]
        self.connection.execute(
            """
            insert into app.import_batches(
                id, legacy_mongo_id, batch_type, source_name, imported_by, row_count,
                success_count, error_count, duplicate_count, suspected_duplicate_count,
                updated_count, status, imported_at, raw_payload
            ) values (
                '00000000-0000-0000-0000-000000000101', 'batch-1',
                'input_invoice', 'invoice.xlsx', 'operator', 1, 1, 0, 0, 0, 0,
                'completed', '2026-07-01T10:01:00Z', %s::jsonb
            )
            """,
            (json.dumps(batch_payload),),
        )
        self.connection.execute(
            """
            insert into app.file_objects(
                id, legacy_mongo_id, storage_backend, storage_uri, object_key,
                filename, sha256, size_bytes, content_type, uploaded_at
            ) values (
                '00000000-0000-0000-0000-000000000103', 'object-1', 's3',
                's3://bucket/imports/invoice-1.xlsx', 'imports/invoice-1.xlsx', 'invoice.xlsx',
                %s, 256, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '2026-07-01T09:59:00Z'
            )
            """,
            ("a" * 64,),
        )
        self.connection.execute(
            """
            insert into app.import_files(
                id, legacy_mongo_id, file_object_id, session_id, stored_file_path,
                original_filename, template_kind, status, uploaded_by, uploaded_at, raw_payload
            ) values (
                '00000000-0000-0000-0000-000000000104', 'file-1',
                '00000000-0000-0000-0000-000000000103', 'session-1',
                's3://bucket/imports/invoice-1.xlsx', 'invoice.xlsx', 'invoice_export',
                'confirmed', 'operator', '2026-07-01T10:00:00Z', %s::jsonb
            )
            """,
            (json.dumps(file_payload),),
        )
        self.connection.execute(
            """
            insert into app.import_batch_rows(
                id, legacy_mongo_id, import_batch_id, legacy_batch_id, row_no,
                source_record_type, source_unique_key, data_fingerprint, decision,
                decision_reason, linked_object_type, linked_object_id, identity_kind, raw_payload
            ) values (
                '00000000-0000-0000-0000-000000000102', 'row-1',
                '00000000-0000-0000-0000-000000000101', 'batch-1', 1,
                'invoice', '25300000000100000001', 'invoice-fingerprint-1', 'created',
                'new', 'invoice', 'invoice-1', null, %s::jsonb
            )
            """,
            (json.dumps(row_payload),),
        )
        self.connection.execute(
            """
            insert into app.invoices(
                id, legacy_mongo_id, invoice_type, invoice_no, invoice_code, digital_invoice_no,
                source_unique_key, data_fingerprint, invoice_date, invoice_month, counterparty_name,
                seller_name, seller_tax_no, buyer_name, buyer_tax_no, amount, signed_amount,
                tax_rate, tax_amount, total_with_tax, source_batch_id, legacy_source_batch_id,
                status, source_links, raw_payload
            ) values (
                '00000000-0000-0000-0000-000000000105', 'invoice-1', 'input',
                '25300000000100000001', '253000000001', '25300000000100000001',
                '25300000000100000001', null, '2026-07-01', '2026-07-01', '供应商甲',
                '供应商甲', '915300000000000001', '云南溯源科技有限公司',
                '915300007194052520', 100.00, 100.00, '13%%', 13.00, 113.00,
                '00000000-0000-0000-0000-000000000101', 'batch-1', 'pending',
                %s::jsonb, %s::jsonb
            )
            """,
            (
                json.dumps(fixture.invoices[0]["source_links"]),
                json.dumps(invoice_payload),
            ),
        )
        self.connection.execute(
            """
            insert into job.import_jobs(
                id, tenant_id, import_type, import_session_id, idempotency_key,
                status, stage, attempt_count, max_attempts, payload, result_payload,
                created_by, finished_at
            ) values (
                '00000000-0000-0000-0000-000000000106', 'default',
                'file_import.confirm', 'session-1', 'file_import.confirm:session-1:file-1',
                'succeeded', 'succeeded', 1, 5, %s::jsonb, %s::jsonb, 'operator', now()
            )
            """,
            (
                json.dumps({"session_id": "session-1", "selected_file_ids": ["file-1"]}),
                json.dumps({"confirmed": 1}),
            ),
        )

    def test_full_migration_clean_and_destructive_fail_closed_proof(self) -> None:
        clean = self._audit()
        self.assertEqual(clean["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertTrue(clean["audit_contract"]["database_snapshot"])

        with self.connection.transaction() as transaction:
            transaction.execute("select set_config('fin_ops.correction_reason', '审计测试构造金额偏差', true)")
            transaction.execute("select set_config('fin_ops.actor_id', 'test-suite', true)")
            transaction.execute("update app.invoices set amount = 99.00 where legacy_mongo_id = 'invoice-1'")
        drift = self._audit()
        self.assertIn("invoice_import_invoice_field_mismatch", drift["summary"]["issue_sample_counts_by_code"])
        with self.connection.transaction() as transaction:
            transaction.execute("select set_config('fin_ops.correction_reason', '审计测试恢复金额', true)")
            transaction.execute("select set_config('fin_ops.actor_id', 'test-suite', true)")
            transaction.execute("update app.invoices set amount = 100.00 where legacy_mongo_id = 'invoice-1'")

        self.connection.execute("update app.invoices set source_links = '[]'::jsonb where legacy_mongo_id = 'invoice-1'")
        missing_link = self._audit()
        self.assertIn("invoice_import_manual_source_link_missing", missing_link["summary"]["issue_sample_counts_by_code"])
        self.connection.execute(
            "update app.invoices set source_links = %s::jsonb where legacy_mongo_id = 'invoice-1'",
            (json.dumps(FakeConnection().invoices[0]["source_links"]),),
        )

        self.connection.execute("update app.file_objects set sha256 = null where legacy_mongo_id = 'object-1'")
        missing_hash = self._audit()
        self.assertIn("invoice_import_file_hash_registration_incomplete", missing_hash["summary"]["issue_sample_counts_by_code"])
        self.connection.execute(
            "update app.file_objects set sha256 = %s where legacy_mongo_id = 'object-1'",
            ("a" * 64,),
        )

        self.connection.execute(
            """
            update job.import_jobs
            set status = 'processing', stage = 'confirming', finished_at = null
            where id = '00000000-0000-0000-0000-000000000106'
            """
        )
        self.connection.execute(
            """
            insert into job.outbox_events(
                id, tenant_id, event_type, aggregate_type, aggregate_id, status, dedupe_key, payload
            ) values (
                '00000000-0000-0000-0000-000000000107', 'default',
                'import.process.requested', 'import_job',
                '00000000-0000-0000-0000-000000000106', 'pending',
                'import.process.requested:test:invoice', '{}'::jsonb
            )
            """
        )
        active = self._audit()
        self.assertEqual(active["audit_status"]["integrity"], "pass")
        self.assertEqual(active["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(active["audit_status"]["queue"], "backlog")


if __name__ == "__main__":
    unittest.main()
