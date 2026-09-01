from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from psycopg.errors import ObjectNotInPrerequisiteState

from fin_ops_platform.postgres import migrate
from fin_ops_platform.domain.enums import BatchType, ImportDecision
from fin_ops_platform.domain.models import ImportedBatchRowResult
from fin_ops_platform.services.etc_reconciliation_models import (
    EtcReconciliationTaskStatus,
    SourceFileKind,
)
from fin_ops_platform.services.background_job_service import BackgroundJobService
from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
from fin_ops_platform.services.etc_service import (
    EtcBatch,
    EtcBusinessBatch,
    EtcImportBatch,
    EtcInvoice,
    EtcInvoiceStatus,
    EtcService,
)
from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.bank_transaction_category import (
    PostgresBankTransactionCategoryRepository,
)
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.state_store_protocol import SettingsAccessControlCommitOutcomeUnknown
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

    def test_financial_fact_changes_require_reason_and_leave_append_only_before_after_history(self) -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                id, legacy_mongo_id, account_no, txn_direction, amount, signed_amount,
                txn_date, txn_month, source_unique_key, data_fingerprint, status
            ) values (
                '00000000-0000-0000-0000-000000000901', 'guarded-bank-1', '62220001',
                'outflow', 100.00, -100.00, '2026-08-09', '2026-08-01',
                'guarded-bank-key-1', 'guarded-bank-fingerprint-1', 'active'
            )
            """
        )

        with self.assertRaisesRegex(ObjectNotInPrerequisiteState, "requires fin_ops.correction_reason"):
            self.connection.execute(
                "update app.bank_transactions set amount = 200.00 where legacy_mongo_id = 'guarded-bank-1'"
            )

        self.connection.execute(
            "update app.bank_transactions set status = 'reviewed' where legacy_mongo_id = 'guarded-bank-1'"
        )
        with self.connection.transaction() as transaction:
            transaction.execute("select set_config('fin_ops.actor_id', 'YNSYLP005', true)")
            transaction.execute("select set_config('fin_ops.correction_reason', '银行回单修正', true)")
            transaction.execute(
                """
                update app.bank_transactions
                set amount = 200.00, signed_amount = -200.00
                where legacy_mongo_id = 'guarded-bank-1'
                """
            )

        correction = self.connection.fetch_one(
            """
            select actor_id, reason, before_value, after_value
            from app.financial_fact_corrections
            where entity_id = 'guarded-bank-1'
            """
        )
        self.assertIsNotNone(correction)
        assert correction is not None
        self.assertEqual(correction["actor_id"], "YNSYLP005")
        self.assertEqual(correction["reason"], "银行回单修正")
        self.assertEqual(str(correction["before_value"]["amount"]), "100.00")
        self.assertEqual(str(correction["after_value"]["amount"]), "200.00")

        with self.assertRaisesRegex(ObjectNotInPrerequisiteState, "append-only"):
            self.connection.execute(
                "update audit.events set outcome = 'failed' where event_type = 'financial_fact.corrected'"
            )

    def test_settings_acl_commit_lost_ack_reconciles_under_fresh_lock(self) -> None:
        self.store.save_app_settings({"manual_projects": []})
        base_connection = self.connection

        class LostAckConnection:
            def __init__(self) -> None:
                self.lost_ack_emitted = False

            def __getattr__(self, name: str):
                return getattr(base_connection, name)

            @contextmanager
            def connection(self):
                with base_connection.connection() as raw_connection:
                    owner = self

                    class RawProxy:
                        def __init__(self) -> None:
                            self.commit_count = 0

                        def __getattr__(self, name: str):
                            return getattr(raw_connection, name)

                        def commit(self) -> None:
                            self.commit_count += 1
                            raw_connection.commit()
                            if self.commit_count == 2 and not owner.lost_ack_emitted:
                                owner.lost_ack_emitted = True
                                raise ConnectionError("synthetic commit acknowledgement loss")

                    yield RawProxy()

        lost_ack_store = PostgresStateStore(
            data_dir=Path(self._temp_dir.name),
            connection=LostAckConnection(),
        )
        mutation_id = "integration-lost-ack"
        with self.assertRaises(SettingsAccessControlCommitOutcomeUnknown):
            with lost_ack_store.begin_settings_acl_critical_section(1) as critical_section:
                critical_section.commit(
                    {
                        "allowed_usernames": ["YNSYLP005", "FULL001"],
                        "readonly_export_usernames": [],
                        "admin_usernames": ["YNSYLP005"],
                        "full_access_usernames": ["FULL001"],
                    },
                    {"mutation_id": mutation_id, "actor_id": "YNSYLP005", "request_id": "integration"},
                )

        recovery = lost_ack_store.recover_settings_acl_commit(mutation_id)
        self.assertTrue(recovery["audit_present"])
        self.assertEqual(recovery["access_control"]["access_control_version"], 2)
        self.assertEqual(recovery["access_control"]["full_access_usernames"], ["FULL001"])

    def test_manual_category_clear_executes_json_update_and_returns_to_unmatched_fact(self) -> None:
        repository = PostgresBankTransactionCategoryRepository(self.connection)
        transaction_id = "bank-manual-clear"
        with self.connection.transaction() as transaction:
            transaction.execute(
                """
                insert into app.bank_transactions(
                    legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                    amount, signed_amount, txn_date, txn_month, status
                ) values (%s, %s, %s, %s, %s, %s, %s::date, %s::date, 'active')
                """,
                (
                    transaction_id,
                    "62220002",
                    "inflow",
                    "人工撤销集成测试",
                    "100.00",
                    "100.00",
                    "2026-02-03",
                    "2026-02-01",
                ),
            )
            repository.apply_mutation(
                transaction=transaction,
                transaction_id=transaction_id,
                mutation_type="manual_assign",
                record={"category_code": "borrow_in", "manual_assignment": True, "category_version": 1},
                actor_id="integration-test",
                action="bank_detail_category_manually_assigned",
                metadata={"integration_test": True},
            )
            result = repository.apply_mutation(
                transaction=transaction,
                transaction_id=transaction_id,
                mutation_type="manual_clear",
                record={"category_version": 2},
                actor_id="integration-test",
                action="bank_detail_category_manual_assignment_cleared",
                metadata={"integration_test": True},
            )

        self.assertTrue(result["changed"])
        persisted = self.connection.fetch_one(
            """
            select category.status, category.version,
                   category.raw_payload #>> '{normalized_payload,category_code}' as category_code,
                   category.raw_payload #>> '{normalized_payload,updated_by}' as updated_by
            from app.bank_transaction_categories category
            join app.bank_transactions bank on bank.id = category.bank_transaction_id
            where bank.legacy_mongo_id = %s
            """,
            (transaction_id,),
        )
        self.assertEqual(
            persisted,
            {
                "status": "cleared",
                "version": 2,
                "category_code": None,
                "updated_by": "integration-test",
            },
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from app.bank_transaction_categories where legacy_transaction_id = 'bank-manual-clear' and status = 'active';",
            ),
            "0",
        )

    def test_turnover_relation_change_preserves_unrelated_relation_and_audit_history(self) -> None:
        repository = PostgresWorkbenchRepository(self.connection)
        repository.save_turnover_relations(
            {
                "relations": {
                    "relation-a": {
                        "relation_id": "relation-a",
                        "bank_transaction_ids": ["bank-a"],
                        "status": "confirmed",
                        "scope_month": "2026-03",
                        "version": 1,
                    },
                    "relation-b": {
                        "relation_id": "relation-b",
                        "bank_transaction_ids": ["bank-b"],
                        "status": "confirmed",
                        "scope_month": "2026-04",
                        "version": 1,
                    },
                },
                "audit_log": [
                    {"operation_id": "create-a", "relation_id": "relation-a", "action": "confirm_relation"},
                    {"operation_id": "create-b", "relation_id": "relation-b", "action": "confirm_relation"},
                ],
            }
        )

        repository.save_turnover_relation_change(
            relation={
                "relation_id": "relation-a",
                "bank_transaction_ids": ["bank-a"],
                "status": "withdrawn",
                "scope_month": "2026-03",
                "version": 2,
            },
            audit_event={
                "operation_id": "withdraw-a",
                "relation_id": "relation-a",
                "action": "withdraw_relation",
            },
        )

        loaded = repository.load_turnover_relations()
        relations = {row["relation_id"]: row for row in loaded["relations"]}
        self.assertEqual(relations["relation-a"]["status"], "withdrawn")
        self.assertEqual(relations["relation-b"]["status"], "confirmed")
        audit_operations = {row.get("operation_id") for row in loaded["audit_log"]}
        self.assertEqual(audit_operations, {"create-a", "create-b", "withdraw-a"})

    def test_idempotent_background_job_retry_is_atomic_and_reuses_job_id(self) -> None:
        service = BackgroundJobService(self.store)
        first, first_activated = service.create_or_get_idempotent_job_with_created(
            job_type="file_import",
            label="导入 银行流水",
            owner_user_id="integration-user",
            idempotency_key="file_import_session:integration-session:file-1",
            source={"session_id": "integration-session", "selected_file_ids": ["file-1"]},
        )
        service.fail_job(first.job_id, "导入失败。", "queue unavailable")

        retried, retry_activated = service.create_or_get_idempotent_job_with_created(
            job_type="file_import",
            label="导入 银行流水",
            owner_user_id="integration-user",
            idempotency_key="file_import_session:integration-session:file-1",
            source={"session_id": "integration-session", "selected_file_ids": ["file-1"]},
        )

        self.assertTrue(first_activated)
        self.assertTrue(retry_activated)
        self.assertEqual(retried.job_id, first.job_id)
        self.assertEqual(retried.status, "queued")
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from job.background_jobs where idempotency_key = 'file_import_session:integration-session:file-1';",
            ),
            "1",
        )
        fingerprint_row = self.connection.fetch_one(
            "select request_fingerprint from job.background_jobs where job_id = %s",
            (first.job_id,),
        )
        self.assertTrue(str(fingerprint_row.get("request_fingerprint") or ""))

    def test_background_job_progress_repairs_stale_raw_job_id_without_replaying_history(self) -> None:
        service = BackgroundJobService(self.store)
        job = service.create_or_get_idempotent_job(
            job_type="file_import",
            label="导入 银行流水",
            owner_user_id="integration-user",
            idempotency_key="file_import_session:stale-raw:file-1",
            source={"session_id": "stale-raw", "selected_file_ids": ["file-1"]},
        )
        self.connection.execute(
            """
            update job.background_jobs
            set raw_payload = jsonb_set(raw_payload, '{normalized_payload,job_id}', to_jsonb(%s::text), true)
            where job_id = %s
            """,
            ("job_stale_legacy_id", job.job_id),
        )

        started = service.start_job(job.job_id)

        self.assertEqual(started.job_id, job.job_id)
        self.assertEqual(started.status, "running")
        row = self.connection.fetch_one(
            """
            select job_id, status, raw_payload #>> '{normalized_payload,job_id}' as raw_job_id
            from job.background_jobs
            where owner_id = %s and job_type = %s and idempotency_key = %s
            """,
            ("integration-user", "file_import", "file_import_session:stale-raw:file-1"),
        )
        self.assertEqual(row["job_id"], job.job_id)
        self.assertEqual(row["raw_job_id"], job.job_id)
        self.assertEqual(row["status"], "running")

    def test_formal_table_writes_for_settings_jobs_workbench_and_read_models(self) -> None:
        self.store.save_app_settings({"manual_projects": []})
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
        self.store.save_background_job(
                {
                    "job_id": "job-1",
                    "job_type": "workbench_rebuild",
                    "status": "running",
                    "owner_id": "tester",
                    "affected_months": ["2026-03"],
                    "progress": {"current": 1, "total": 3},
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
        with self.connection.transaction() as transaction:
            transaction.execute(
                """
                insert into app.bank_transactions(
                    legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                    amount, signed_amount, txn_date, txn_month, status
                ) values (%s, %s, %s, %s, %s, %s, %s::date, %s::date, 'active')
                """,
                ("bank-1", "62220001", "outflow", "测试供应商", "125.50", "-125.50", "2026-03-01", "2026-03-01"),
            )
            PostgresBankTransactionCategoryRepository(self.connection).apply_mutation(
                transaction=transaction,
                transaction_id="bank-1",
                mutation_type="manual_assign",
                record={"category_code": "fee", "manual_assignment": True},
                actor_id="integration-test",
                action="bank_detail_category_manually_assigned",
                metadata={"integration_test": True},
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

        expected_counts = {
            "app.app_settings": 1,
            "job.background_jobs": 1,
            "audit.app_health_alerts": 1,
            "app.workbench_pair_relations": 1,
            "app.workbench_pair_relation_history": 1,
            "app.no_oa_bank_batches": 1,
            "app.no_oa_bank_batch_events": 1,
            "app.bank_transaction_categories": 1,
            "app.bank_transaction_category_events": 1,
            "app.turnover_relations": 1,
            "app.turnover_relation_events": 1,
            "app.turnover_ledger_extras": 1,
            "app.pending_invoice_manual_invoice_commands": 1,
        }
        for table, minimum_count in expected_counts.items():
            with self.subTest(table=table):
                self.assertGreaterEqual(int(fetch_scalar(self.database_url, f"select count(*) from {table};")), minimum_count)

        loaded_turnover = self.store.load_turnover_relations()
        self.assertIsInstance(loaded_turnover["relations"], list)
        self.assertEqual(loaded_turnover["relations"][0]["relation_id"], "turnover-1")

        loaded_commands = self.store.load_pending_invoice_commands()
        self.assertEqual(loaded_commands["cmd-1"]["status"], "failed_recoverable")
        self.assertEqual(loaded_commands["cmd-1"]["last_successful_status"], "invoice_created")

        self.store.save_pending_invoice_commands({})
        self.assertEqual(fetch_scalar(self.database_url, "select count(*) from app.pending_invoice_manual_invoice_commands;"), "0")

    def test_workbench_relation_long_history_batch_is_persisted_with_relation_ids(self) -> None:
        histories = [
            {
                "operation_id": f"operation-{index}",
                "case_id": "case-long-history",
                "event_type": "updated",
                "actor_id": "integration-test",
                "occurred_at": "2026-07-20T00:00:00+00:00",
                "before_payload": {"version": index},
                "after_payload": {"version": index + 1},
            }
            for index in range(25)
        ]

        self.store.save_workbench_pair_relations(
            {
                "pair_relations": {
                    "case-long-history": {
                        "case_id": "case-long-history",
                        "relation_mode": "turnover_manual_closure",
                        "status": "active",
                        "version": 25,
                        "month_scope": "2026-07",
                        "row_ids": ["bank-long-history"],
                        "row_types": ["bank"],
                    }
                },
                "pair_relation_history": histories,
            }
        )

        persisted = self.connection.fetch_one(
            """
            select
                count(*)::integer as count,
                count(relation_id)::integer as relation_id_count,
                min(event_type) as event_type
            from app.workbench_pair_relation_history
            where case_id = %s
            """,
            ("case-long-history",),
        )
        self.assertEqual(
            persisted,
            {
                "count": len(histories),
                "relation_id_count": len(histories),
                "event_type": "updated",
            },
        )

    def test_workbench_relation_reloaded_multi_case_history_is_persisted_once_per_case(self) -> None:
        shared_history = {
            "operation_id": "shared-operation",
            "operation_type": "replace_link",
            "before_relations": [{"case_id": "case-before"}],
            "after_relations": [{"case_id": "case-after"}],
            "created_by": "integration-test",
            "created_at": "2026-07-21T00:00:00+00:00",
        }

        self.store.save_workbench_pair_relations(
            {
                "pair_relations": {
                    "case-before": {
                        "case_id": "case-before",
                        "relation_mode": "manual_confirmed",
                        "status": "cancelled",
                        "month_scope": "2026-07",
                        "row_ids": ["bank-shared"],
                        "row_types": ["bank"],
                    },
                    "case-after": {
                        "case_id": "case-after",
                        "relation_mode": "manual_confirmed",
                        "status": "active",
                        "month_scope": "2026-07",
                        "row_ids": ["bank-shared", "oa-shared"],
                        "row_types": ["bank", "oa"],
                    },
                },
                "pair_relation_history": [dict(shared_history), dict(shared_history)],
            },
            changed_case_ids={"case-before", "case-after"},
        )

        persisted = self.connection.fetch_one(
            """
            select
                count(*)::integer as count,
                count(distinct case_id)::integer as case_count,
                count(distinct id)::integer as event_id_count
            from app.workbench_pair_relation_history
            where case_id = any(%s::text[])
            """,
            (["case-before", "case-after"],),
        )
        self.assertEqual(
            persisted,
            {"count": 2, "case_count": 2, "event_id_count": 2},
        )

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

    def test_bank_reset_records_retryable_file_cleanup_intent_on_current_schema(
        self,
    ) -> None:
        missing_path = str(Path(self._temp_dir.name) / "already-missing.xlsx")
        self.connection.execute(
            """
            insert into app.import_files(
                legacy_mongo_id, session_id, stored_file_path, original_filename,
                status, raw_payload
            )
            values (%s, %s, %s, %s, 'confirmed', %s::jsonb)
            """,
            (
                "bank-reset-file",
                "bank-reset-session",
                missing_path,
                "bank.xlsx",
                json.dumps(
                    {
                        "normalized_payload": {
                            "id": "bank-reset-file",
                            "batch_type": "bank_transaction",
                        }
                    }
                ),
            ),
        )

        reset_result = self.store.reset_bank_transaction_data()

        self.assertEqual(reset_result["file_import_files"], 1)
        self.assertEqual(reset_result["stored_import_file_paths"], [missing_path])
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select status from app.import_files where legacy_mongo_id = 'bank-reset-file';",
            ),
            "deleting",
        )
        self.assertEqual(self.store.delete_import_files([missing_path]), 1)
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select status from app.import_files where legacy_mongo_id = 'bank-reset-file';",
            ),
            "deleted",
        )

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

    def test_import_batch_row_owner_conflict_rolls_back_whole_batch(self) -> None:
        repository = PostgresCoreRepository(self.connection)

        def row(row_id: str, batch_id: str, row_no: int) -> ImportedBatchRowResult:
            return ImportedBatchRowResult(
                id=row_id,
                batch_id=batch_id,
                row_no=row_no,
                source_record_type="invoice",
                source_unique_key=f"invoice-key-{row_no}",
                data_fingerprint=None,
                decision=ImportDecision.CREATED,
                decision_reason="new",
            )

        def insert_batch(transaction, batch_id: str) -> None:
            transaction.execute(
                """
                insert into app.import_batches(
                    legacy_mongo_id, batch_type, source_name, imported_by, status, imported_at, raw_payload
                ) values (%s, 'input_invoice', 'input.xlsx', 'tester', 'pending', now(), '{}'::jsonb)
                """,
                (batch_id,),
            )

        shared_row_id = "batch-row-shared-owner"
        with self.connection.transaction() as transaction:
            insert_batch(transaction, "batch-owner-a")
            repository._save_batch_rows(
                transaction,
                "batch-owner-a",
                [row(shared_row_id, "batch-owner-a", 1)],
                [{"invoice_no": "INV-A"}],
            )

        with self.connection.transaction() as transaction:
            repository._save_batch_rows(
                transaction,
                "batch-owner-a",
                [row(shared_row_id, "batch-owner-a", 1)],
                [{"invoice_no": "INV-A"}],
            )

        with self.assertRaisesRegex(RuntimeError, "refusing to re-parent"):
            with self.connection.transaction() as transaction:
                insert_batch(transaction, "batch-owner-b")
                repository._save_batch_rows(
                    transaction,
                    "batch-owner-b",
                    [
                        row("batch-row-new-before-conflict", "batch-owner-b", 1),
                        row(shared_row_id, "batch-owner-b", 2),
                    ],
                    [{"invoice_no": "INV-B-1"}, {"invoice_no": "INV-B-2"}],
                )

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from app.import_batches where legacy_mongo_id in ('batch-owner-a', 'batch-owner-b');",
            ),
            "1",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from app.import_batch_rows where legacy_mongo_id in ('batch-row-shared-owner', 'batch-row-new-before-conflict');",
            ),
            "1",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select legacy_batch_id from app.import_batch_rows where legacy_mongo_id = 'batch-row-shared-owner';",
            ),
            "batch-owner-a",
        )

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
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select invoice_count from app.etc_business_batches where business_batch_id = 'etc_business_batch_0001';",
            ),
            "1",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select total_amount from app.etc_business_batches where business_batch_id = 'etc_business_batch_0001';",
            ),
            "100.00",
        )

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
            [
                task.task_id
                for task in reconciliation.list_import_task_summaries()
                if task.status == EtcReconciliationTaskStatus.READY_FOR_IMPORT
            ],
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
if __name__ == "__main__":
    unittest.main()
