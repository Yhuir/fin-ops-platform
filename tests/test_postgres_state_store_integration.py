from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.postgres import migrate
from fin_ops_platform.services.etc_reconciliation_models import SourceFileKind
from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
from fin_ops_platform.services.etc_service import (
    EtcBatch,
    EtcBusinessBatch,
    EtcImportBatch,
    EtcInvoice,
    EtcInvoiceStatus,
    EtcService,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.import_file_service import FileImportPreviewItem, FileImportService, FileImportSession
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.tax_certified_import_service import (
    TaxCertifiedImportBatch,
    TaxCertifiedImportPreviewFile,
    TaxCertifiedImportService,
    TaxCertifiedImportSession,
    TaxCertifiedInvoiceRecord,
)

from postgres_test_utils import apply_test_migrations, fetch_scalar, require_postgres_test_database_url, truncate_test_database


class PostgresStateStoreIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self._temp_dir = TemporaryDirectory()
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.store = PostgresStateStore(data_dir=Path(self._temp_dir.name), connection=self.connection)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_migrations_health_summary_and_transaction_rollback(self) -> None:
        versions = fetch_scalar(self.database_url, "select string_agg(version, ',' order by version) from public.schema_migrations;")
        expected_versions = [migration.version for migration in migrate.discover_migrations()]
        self.assertEqual(versions.split(","), expected_versions)

        health = self.connection.health_summary()
        self.assertEqual(health["postgres_status"], "ready")
        self.assertGreaterEqual(health["postgres_schema_version"], 8)
        self.assertNotIn("url", str(health).lower())
        self.assertNotIn("password", str(health).lower())

        with self.connection.transaction() as transaction:
            transaction.execute(
                "insert into app.app_settings(settings_key, settings_payload, raw_payload) values (%s, '{}'::jsonb, '{}'::jsonb)",
                ("tx-commit",),
            )
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.app_settings where settings_key = 'tx-commit';"), "1")

        with self.assertRaises(RuntimeError):
            with self.connection.transaction() as transaction:
                transaction.execute(
                    "insert into app.app_settings(settings_key, settings_payload, raw_payload) values (%s, '{}'::jsonb, '{}'::jsonb)",
                    ("tx-rollback",),
                )
                raise RuntimeError("force rollback")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.app_settings where settings_key = 'tx-rollback';"), "0")

    def test_workbench_all_groups_use_exact_generation_stats_and_fail_closed_when_missing(self) -> None:
        self.store.save_workbench_read_models(
            {
                "read_models": {
                    scope_key: {
                        "scope_key": scope_key,
                        "payload": {"paired": {"groups": []}, "unpaired": {"groups": []}},
                        "source_versions": {"source_version": index},
                    }
                    for index, scope_key in enumerate(("2026-04", "2026-05"), start=1)
                }
            },
            changed_scope_keys={"2026-04", "2026-05"},
        )
        repository = PostgresReadModelRepository(self.connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="paired",
            page=1,
            page_size=50,
            detail_level="summary",
        )

        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page["total"], 0)
        self.assertEqual(page["row_counts"], {"oa": 0, "bank": 0, "invoice": 0, "rows": 0})
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from read_model.workbench_generation_stats where scope_key = 'all';",
            ),
            "2",
        )

        with self.connection.transaction() as transaction:
            transaction.execute("delete from read_model.workbench_generation_stats where scope_key = 'all'")

        self.assertIsNone(
            repository.get_workbench_groups_page(
                scope_key="all",
                zone="paired",
                page=1,
                page_size=50,
                detail_level="summary",
            )
        )

    def test_bank_flow_rule_batch_page_uses_sql_pagination_and_aggregate_summary(self) -> None:
        source_versions = {"schema_version": "bank-flow-test-v1", "bank_rows": "3"}
        self.store.save_bank_flow_rule_batches(
            {
                "batches": {
                    "bank-flow-batch-draft": {
                        "batch_id": "bank-flow-batch-draft",
                        "relation_mode": "bank_flow_rule_batch",
                        "scope_month": "2026-05",
                        "batch_type": "bank_fee",
                        "status": "unsubmitted",
                        "status_bucket": "unsubmitted",
                        "account_key": "ccb:8106",
                        "total_amount": "10.00",
                        "row_count": 1,
                        "source_versions": source_versions,
                    },
                    "bank-flow-batch-submitted": {
                        "batch_id": "bank-flow-batch-submitted",
                        "relation_mode": "bank_flow_rule_batch",
                        "scope_month": "2026-05",
                        "batch_type": "bank_fee",
                        "status": "submitted",
                        "status_bucket": "submitted",
                        "account_key": "ccb:8106",
                        "total_amount": "20.00",
                        "row_count": 1,
                        "source_versions": source_versions,
                    },
                    "bank-flow-batch-withdrawn": {
                        "batch_id": "bank-flow-batch-withdrawn",
                        "relation_mode": "bank_flow_rule_batch",
                        "scope_month": "2026-05",
                        "batch_type": "project_payment",
                        "status": "withdrawn",
                        "status_bucket": "withdrawn",
                        "account_key": "ccb:8106",
                        "total_amount": "30.00",
                        "row_count": 1,
                        "source_versions": source_versions,
                    },
                }
            }
        )
        with self.connection.transaction() as transaction:
            for scope_key in ("all", "2026-05"):
                transaction.execute(
                    """
                    insert into read_model.app_status_readiness(
                        tenant_id, read_model_key, scope_type, scope_key, status, source_versions
                    ) values ('default', 'bank_flow_rule_batch', 'bank_flow_rule_batch', %s, 'fresh', %s::jsonb)
                    """,
                    (scope_key, json.dumps(source_versions)),
                )

        repository = PostgresReadModelRepository(self.connection)
        page = repository.read_bank_flow_rule_batch_page(
            {"month": "2026-05", "account_key": "ccb:8106"},
            summary_filters={"month": "2026-05", "account_key": "ccb:8106"},
            page=1,
            page_size=2,
        )

        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page["total"], 3)
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(page["source_versions_summary"]["read_model_status"], "fresh")
        aggregates = {
            (row["batch_type"], row["presented_status"]): (int(row["batch_count"]), row["total_amount"])
            for row in page["aggregates"]
        }
        self.assertEqual(
            aggregates,
            {
                ("bank_fee", "draft"): (1, "10.000000"),
                ("bank_fee", "submitted"): (1, "20.000000"),
                ("project_payment", "withdrawn"): (1, "30.000000"),
            },
        )

    def test_formal_table_writes_for_settings_jobs_workbench_and_read_models(self) -> None:
        self.store.save_app_settings({"admin_usernames": ["admin"], "manual_projects": []})
        self.store.save_pending_invoice_commands(
            {
                "cmd-1": {
                    "request_id": "cmd-1",
                    "request_key": "manual-pending-invoice:bank-1:expense:digest",
                    "status": "failed_recoverable",
                    "status_history": ["started", "invoice_created", "failed_recoverable"],
                    "invoice_id": "invoice-1",
                    "relation_case_id": "case-1",
                    "error": "boom",
                    "last_successful_status": "invoice_created",
                    "created_at": "2026-05-20T10:00:00+00:00",
                    "updated_at": "2026-05-20T10:01:00+00:00",
                }
            }
        )
        self.store.save_background_jobs(
            {
                "job-1": {
                    "job_type": "workbench_rebuild",
                    "status": "running",
                    "owner_id": "tester",
                    "affected_months": ["2026-03"],
                    "progress": {"current": 1, "total": 3},
                }
            }
        )
        self.store.save_app_health_alerts({"records": {"alert-1": {"kind": "postgres", "severity": "warning", "status": "active"}}})
        self.store.save_workbench_pair_relations(
            {
                "pair_relations": {
                    "case-1": {
                        "relation_mode": "manual",
                        "status": "active",
                        "version": 2,
                        "month_scope": "2026-03",
                        "row_ids": ["bank-1", "invoice-1"],
                        "row_types": ["bank", "invoice"],
                    }
                },
                "pair_relation_history": [
                    {"operation_id": "pair-op-1", "case_id": "case-1", "event_type": "created", "actor_id": "tester"}
                ],
            }
        )
        self.store.save_no_oa_bank_batches(
            {
                "batches": {
                    "batch-1": {
                        "status": "draft",
                        "status_bucket": "draft",
                        "version": 1,
                        "scope_month": "2026-03",
                        "account_key": "acct-1",
                        "total_amount": "125.50",
                        "bank_transaction_ids": ["bank-1"],
                    }
                },
                "audit_log": [
                    {"operation_id": "no-oa-op-1", "batch_id": "batch-1", "event_type": "created", "actor_id": "tester"}
                ],
            }
        )
        self.store.save_workbench_read_models(
            {
                "read_models": {
                    "2026-03": {
                        "scope_month": "2026-03",
                        "source_versions": {"pair_relation_snapshot_version": 1},
                        "rows": [{"id": "row-1"}],
                    }
                }
            }
        )
        self.store.save_bank_transaction_categories(
            {
                "categories": {"bank-1": {"category": "fee", "source": "manual", "confidence": "1", "version": 1}},
                "audit_log": [
                    {"operation_id": "category-op-1", "transaction_id": "bank-1", "event_type": "category_updated"}
                ],
            }
        )
        self.store.save_bank_transaction_categories(
            {
                "categories": {"bank-1": {"category": "fee", "source": "manual", "confidence": "1", "version": 2}},
                "audit_log": [
                    {"operation_id": "category-op-1", "transaction_id": "bank-1", "event_type": "category_updated"}
                ],
            }
        )
        self.store.save_turnover_relations(
            {
                "relations": {
                    "turnover-1": {
                        "bank_transaction_ids": ["bank-1"],
                        "status": "active",
                        "relation_type": "revenue",
                        "scope_month": "2026-03",
                        "amount": "125.50",
                    }
                },
                "audit_log": [{"operation_id": "turnover-op-1", "relation_id": "turnover-1", "event_type": "created"}],
            }
        )
        self.store.save_turnover_ledger_extras({"extras": {"ledger-1": {"scope_month": "2026-03", "note": "checked"}}})
        self.store.save_tax_offset_read_models(
            {"read_models": {"tax-2026-03": {"scope_month": "2026-03", "entries": [{"id": "entry-1"}]}}}
        )

        expected_counts = {
            "app.app_settings": 1,
            "job.background_jobs": 1,
            "audit.app_health_alerts": 1,
            "app.workbench_pair_relations": 1,
            "app.workbench_pair_relation_history": 1,
            "app.no_oa_bank_batches": 1,
            "app.no_oa_bank_batch_events": 1,
            "read_model.workbench_snapshots": 1,
            "app.bank_transaction_categories": 1,
            "app.bank_transaction_category_events": 1,
            "app.turnover_relations": 1,
            "app.turnover_relation_events": 1,
            "app.turnover_ledger_extras": 1,
            "read_model.tax_offset_read_models": 1,
            "app.pending_invoice_manual_invoice_commands": 1,
        }
        for table, minimum_count in expected_counts.items():
            with self.subTest(table=table):
                self.assertGreaterEqual(int(fetch_scalar(self.database_url, f"select count(*) from {table};")), minimum_count)

        loaded_turnover = self.store.load_turnover_relations()
        self.assertIsInstance(loaded_turnover["relations"], list)
        self.assertEqual(loaded_turnover["relations"][0]["relation_id"], "turnover-1")

        loaded_commands = self.store.load()["pending_invoice_commands"]
        self.assertEqual(loaded_commands["cmd-1"]["status"], "failed_recoverable")
        self.assertEqual(loaded_commands["cmd-1"]["last_successful_status"], "invoice_created")

        self.store.save_pending_invoice_commands({})
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.pending_invoice_manual_invoice_commands;"), "0")

    def test_import_file_metadata_writes_file_object_and_import_file(self) -> None:
        stored_path = self.store.store_import_file(
            session_id="session-1",
            file_id="file-1",
            file_name="bank.xlsx",
            content=b"file-bytes",
        )

        self.assertEqual(self.store.read_import_file(stored_path), b"file-bytes")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.file_objects where legacy_mongo_id = 'file-1';"), "1")
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from app.import_files where legacy_mongo_id = 'file-1' and file_object_id is not null;",
            ),
            "1",
        )
        self.assertTrue(self.store.import_file_exists("file-1"))
        self.assertEqual(self.store.delete_import_files([stored_path, stored_path]), 1)
        self.assertEqual(fetch_scalar(self.database_url, "select status from app.import_files where legacy_mongo_id = 'file-1';"), "deleted")

    def test_imports_and_file_imports_round_trip_through_formal_tables(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="input.xlsx",
            imported_by="tester",
            rows=[
                {
                    "counterparty_name": "供应商A",
                    "invoice_no": "INV-001",
                    "invoice_date": "2026-03-01",
                    "amount": "100.00",
                    "tax_amount": "6.00",
                    "total_with_tax": "106.00",
                }
            ],
        )
        import_service.confirm_import(preview.batch.id)
        file_service = FileImportService.from_snapshot(
            import_service,
            {
                "session_counter": 1,
                "file_counter": 1,
                "sessions": {
                    "session_1": FileImportSession(
                        id="session_1",
                        imported_by="tester",
                        file_count=1,
                        status="confirmed",
                        files=[
                            FileImportPreviewItem(
                                id="file_1",
                                file_name="input.xlsx",
                                template_code="invoice_export",
                                batch_type=BatchType.INPUT_INVOICE,
                                status="confirmed",
                                message="",
                                row_count=1,
                                success_count=1,
                                batch_id=preview.batch.id,
                                stored_file_path="/tmp/input.xlsx",
                            )
                        ],
                    )
                },
            },
        )

        self.store.save({"imports": import_service.snapshot(), "file_imports": file_service.snapshot()})

        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.import_batches;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.import_batch_rows;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.invoices;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.import_files;"), "1")

        loaded = self.store.load()
        loaded_import_service = ImportNormalizationService.from_snapshot(loaded["imports"])
        loaded_file_service = FileImportService.from_snapshot(loaded_import_service, loaded["file_imports"])

        self.assertEqual(loaded_import_service.list_invoices()[0].invoice_no, "INV-001")
        self.assertEqual(loaded_import_service.list_invoices()[0].source_batch_id, preview.batch.id)
        loaded_session = loaded_file_service.snapshot()["sessions"]["session_1"]
        self.assertEqual(loaded_session.files[0].batch_id, preview.batch.id)

    def test_tax_certified_imports_round_trip_through_formal_tables(self) -> None:
        imported_at = datetime(2026, 1, 20, tzinfo=UTC)
        record = TaxCertifiedInvoiceRecord(
            id="cert-record-1",
            unique_key="cert-key-1",
            month="2026-01",
            source_file_name="certified.xlsx",
            source_row_number=3,
            taxpayer_tax_no="915300007194052520",
            taxpayer_name="云南溯源科技有限公司",
            digital_invoice_no="DINV-001",
            invoice_code="CODE-001",
            invoice_no="NO-001",
            issue_date="2026-01-05",
            seller_tax_no="SELLER-TAX",
            seller_name="供应商A",
            amount="100.00",
            tax_amount="6.00",
            deductible_tax_amount="6.00",
            selection_status="已认证",
            invoice_status="正常",
            selection_time="2026-01-20 10:00:00",
            imported_at=imported_at,
        )
        preview_file = TaxCertifiedImportPreviewFile(
            id="tax-certified-file-0001",
            file_name="certified.xlsx",
            month="2026-01",
            recognized_count=1,
            invalid_count=0,
            rows=[record],
        )
        session = TaxCertifiedImportSession(
            id="tax-certified-session-0001",
            imported_by="tester",
            file_count=1,
            status="confirmed",
            files=[preview_file],
            created_at=imported_at,
        )
        batch = TaxCertifiedImportBatch(
            id="tax-certified-batch-0001",
            session_id=session.id,
            imported_by="tester",
            file_count=1,
            months=["2026-01"],
            persisted_record_count=1,
            created_at=imported_at,
        )

        self.store.save_tax_certified_imports(
            {
                "session_counter": 1,
                "file_counter": 1,
                "batch_counter": 1,
                "sessions": {session.id: session},
                "batches": {batch.id: batch},
                "records": {record.unique_key: record},
            }
        )

        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.tax_certified_import_sessions;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.tax_certified_import_batches;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.tax_certified_import_records;"), "1")

        reloaded_service = TaxCertifiedImportService(state_store=self.store)
        records = reloaded_service.list_records_for_month("2026-01")

        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], TaxCertifiedInvoiceRecord)
        self.assertEqual(records[0].invoice_no, "NO-001")
        self.assertEqual(reloaded_service.get_session(session.id).files[0].rows[0].unique_key, "cert-key-1")

    def test_etc_state_round_trip_through_formal_tables(self) -> None:
        now = datetime(2026, 3, 8, tzinfo=UTC)
        invoice = EtcInvoice(
            id="etc_invoice_0001",
            invoice_number="ETC001",
            issue_date="2026-03-08",
            passage_start_date="2026-03-08",
            passage_end_date="2026-03-08",
            plate_number="云ADA0381",
            vehicle_type="一型客车",
            seller_name="云南高速公路联网收费管理有限公司",
            seller_tax_no="915300007194052520",
            buyer_name="云南溯源科技有限公司",
            buyer_tax_no="915300007194052521",
            amount_without_tax=Decimal("97.09"),
            tax_amount=Decimal("2.91"),
            total_amount=Decimal("100.00"),
            tax_rate="3%",
            zip_source_name="etc.zip",
            xml_file_path="/tmp/etc.xml",
            xml_file_hash="xml-sha",
            pdf_file_path="/tmp/etc.pdf",
            pdf_file_hash="pdf-sha",
            status=EtcInvoiceStatus.UNSUBMITTED,
            import_batch_id="etc_import_batch_0001",
            current_batch_id="etc_batch_0001",
            created_at=now,
            updated_at=now,
        )
        import_batch = EtcImportBatch(
            id="etc_import_batch_0001",
            source_names=["etc.zip"],
            invoice_ids=[invoice.id],
            invoice_count=1,
            total_amount=Decimal("100.00"),
            issue_date_start="2026-03-08",
            issue_date_end="2026-03-08",
            created_at=now,
            updated_at=now,
        )
        submission_batch = EtcBatch(
            id="etc_batch_0001",
            etc_batch_id="ETC-BATCH-001",
            invoice_ids=[invoice.id],
            invoice_count=1,
            total_amount=Decimal("100.00"),
            issue_start_date="2026-03-08",
            issue_end_date="2026-03-08",
            created_at=now,
        )
        business_batch = EtcBusinessBatch(
            business_batch_id="etc_business_batch_0001",
            task_id="ETC-RECON-000001",
            invoice_ids=[invoice.id],
            import_batch_ids=[import_batch.id],
            submission_batch_id=submission_batch.id,
            created_at=now,
            updated_at=now,
        )

        self.store.save_etc_state(
            {
                "invoice_counter": 1,
                "batch_counter": 1,
                "import_batch_counter": 1,
                "business_batch_counter": 1,
                "batch_day_counters": {"2026-03-08": 1},
                "invoices": {invoice.id: invoice},
                "invoice_numbers": {invoice.invoice_number: invoice.id},
                "batches": {submission_batch.id: submission_batch},
                "import_batches": {import_batch.id: import_batch},
                "business_batches": {business_batch.business_batch_id: business_batch},
            }
        )

        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.etc_invoices;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.etc_import_batches;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.etc_submission_batches;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.etc_business_batches;"), "1")

        reloaded_service = EtcService(state_store=self.store)
        invoices, total, _ = reloaded_service.list_invoices()
        self.assertEqual(total, 1)
        self.assertIsInstance(invoices[0], EtcInvoice)
        self.assertEqual(invoices[0].invoice_number, "ETC001")
        self.assertEqual(invoices[0].total_amount, Decimal("100.00"))
        self.assertEqual(reloaded_service.list_import_batches()[0].id, import_batch.id)
        self.assertEqual(reloaded_service.get_business_batch(business_batch.business_batch_id).task_id, "ETC-RECON-000001")

    def test_etc_reconciliation_and_historical_etc_round_trip_through_formal_tables(self) -> None:
        reconciliation = EtcReconciliationTaskService(state_store=self.store)
        task = reconciliation.create_task(title="2026-03 ETC", created_by="tester")
        source_file = reconciliation.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket.pdf",
            content_type="application/pdf",
            content=b"ticket-root",
            created_by="tester",
        )

        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.etc_reconciliation_tasks;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.etc_reconciliation_files;"), "1")

        reloaded_reconciliation = EtcReconciliationTaskService(state_store=self.store)
        reloaded_task = reloaded_reconciliation.get_task(task.task_id)
        self.assertEqual(reloaded_task.title, "2026-03 ETC")
        self.assertEqual(reloaded_task.source_files[0].file_id, source_file.file_id)

        bundle = self.store.save_historical_etc_repair_bundle(
            bundle_id="ETC-HIST-TEST",
            file_name="historical.zip",
            content=b"historical-zip",
            metadata={"label": "2026年3月", "case_id": "case-1", "oa_amount": "100.00"},
        )
        parsed_seed = self.store.save_historical_etc_repair_parsed_seed(
            bundle_id="ETC-HIST-TEST",
            parsed_seed={
                "label": "2026年3月",
                "case_id": "case-1",
                "external_batch_id": "ETC-HIST-TEST",
                "oa_row_id": "oa-1",
                "oa_amount": "100.00",
                "selected_invoice_numbers": ["ETC001"],
                "invoice_records": [{"invoice_number": "ETC001", "total_amount": "100.00"}],
                "selected_invoice_records": [{"invoice_number": "ETC001", "total_amount": "100.00"}],
            },
        )
        self.store.save_historical_etc_repair_states(
            {"ETC-HIST-TEST": {"bundle_id": "ETC-HIST-TEST", "status": "ok", "message": "done", "version": 2}}
        )

        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.historical_etc_repair_bundles;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.historical_etc_repair_parsed_seeds;"), "1")
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.historical_etc_repair_states;"), "1")
        self.assertEqual(self.store.load_historical_etc_repair_bundle_metadata()["ETC-HIST-TEST"]["sha256"], bundle["sha256"])
        self.assertEqual(
            self.store.load_historical_etc_repair_parsed_seed("ETC-HIST-TEST")["selected_invoice_numbers"],
            parsed_seed["selected_invoice_numbers"],
        )
        self.assertEqual(self.store.load_historical_etc_repair_states()["ETC-HIST-TEST"]["status"], "ok")

    def test_timestamp_repair_restores_mixed_historical_and_current_task_lists(self) -> None:
        historical_created_at = datetime(2026, 1, 14, 8, 0, tzinfo=UTC)
        historical_updated_at = datetime(2026, 7, 12, 8, 0, tzinfo=UTC)
        current_created_at = datetime(2026, 7, 14, 1, 0, tzinfo=UTC)
        current_updated_at = datetime(2026, 7, 14, 1, 5, tzinfo=UTC)
        with self.connection.transaction() as transaction:
            transaction.execute(
                """
                insert into app.etc_reconciliation_tasks(
                    task_id, status, result_summary, version, raw_payload, created_at, updated_at
                )
                values (%s, 'imported', '{}'::jsonb, 1, %s::jsonb, %s, %s)
                """,
                (
                    "ETC-RECON-HIST-20260114",
                    json.dumps(
                        {
                            "normalized_payload": {
                                "task_id": "ETC-RECON-HIST-20260114",
                                "status": "imported",
                                "version": 1,
                                "title": "历史ETC批次 2026-01",
                            }
                        }
                    ),
                    historical_created_at,
                    historical_updated_at,
                ),
            )
            transaction.execute(
                """
                insert into app.etc_reconciliation_tasks(
                    task_id, status, result_summary, version, raw_payload, created_at, updated_at
                )
                values (%s, 'ready_for_import', '{}'::jsonb, 1, %s::jsonb, %s, %s)
                """,
                (
                    "ETC-RECON-000001",
                    json.dumps(
                        {
                            "normalized_payload": {
                                "task_id": "ETC-RECON-000001",
                                "status": "ready_for_import",
                                "version": 1,
                                "title": "新建ETC批次",
                                "created_at": current_created_at.isoformat(),
                                "updated_at": current_updated_at.isoformat(),
                            }
                        }
                    ),
                    current_created_at,
                    current_updated_at,
                ),
            )

        migration_sql = (
            Path("backend/src/fin_ops_platform/postgres/migrations/0103_etc_reconciliation_task_timestamps.sql")
            .read_text(encoding="utf-8")
        )
        migrate.run_psql(self.database_url, sql=migration_sql)
        migrate.run_psql(self.database_url, sql=migration_sql)

        reconciliation = EtcReconciliationTaskService(state_store=self.store)
        self.assertEqual(
            [task.task_id for task in reconciliation.list_tasks()],
            ["ETC-RECON-000001", "ETC-RECON-HIST-20260114"],
        )
        self.assertEqual(
            [task.task_id for task in reconciliation.list_ready_for_import_tasks()],
            ["ETC-RECON-000001"],
        )
        historical_task = reconciliation.get_task("ETC-RECON-HIST-20260114")
        self.assertEqual(historical_task.created_at, historical_created_at)
        self.assertEqual(historical_task.updated_at, historical_updated_at)
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select
                    (raw_payload->'normalized_payload'->>'created_at')::timestamptz = created_at
                    and (raw_payload->'normalized_payload'->>'updated_at')::timestamptz = updated_at
                from app.etc_reconciliation_tasks
                where task_id = 'ETC-RECON-HIST-20260114';
                """,
            ),
            "t",
        )


    def test_save_no_oa_bank_batches_replaces_absent_read_model_rows(self) -> None:
        self.store.save_no_oa_bank_batches(
            {
                "batches": {
                    "old-conflict": {
                        "batch_id": "old-conflict",
                        "batch_type": "internal_transfer",
                        "status": "conflict",
                        "status_bucket": "unsubmitted",
                        "version": 1,
                        "scope_month": "2026-04",
                        "account_key": "",
                        "row_ids": ["transfer-in", "transfer-out"],
                        "row_count": 2,
                        "total_amount": "4000.00",
                    }
                }
            }
        )

        self.store.save_no_oa_bank_batches(
            {
                "batches": {
                    "submitted-internal-transfer": {
                        "batch_id": "submitted-internal-transfer",
                        "batch_type": "internal_transfer",
                        "status": "submitted",
                        "status_bucket": "submitted",
                        "version": 2,
                        "scope_month": "2026-04",
                        "account_key": "",
                        "row_ids": ["transfer-in", "transfer-out"],
                        "row_count": 2,
                        "total_amount": "4000.00",
                        "relation_case_id": "submitted-internal-transfer",
                    }
                }
            }
        )

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from app.no_oa_bank_batches where batch_id = 'old-conflict';",
            ),
            "0",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from read_model.no_oa_bank_batch_rows where batch_id = 'old-conflict';",
            ),
            "0",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select string_agg(batch_id, ',' order by batch_id) from read_model.no_oa_bank_batch_rows;",
            ),
            "submitted-internal-transfer",
        )


if __name__ == "__main__":
    unittest.main()
