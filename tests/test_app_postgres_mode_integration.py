from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.import_audit_repair_service import build_import_audit_repair_plan
from fin_ops_platform.services.import_file_service import UploadedImportFile
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    apply_import_audit_repair,
    load_import_audit_repair_snapshot,
)

from postgres_test_utils import apply_test_migrations, fetch_scalar, require_postgres_test_database_url, truncate_test_database
from tests.app_test_support import seed_confirmed_import
from tests.mock_import_files import INVOICE_JAN, PINGAN_JAN


@contextmanager
def postgres_app_env(database_url: str):
    updates = {
        "FIN_OPS_APP_STORAGE_BACKEND": "postgres",
        "FIN_OPS_POSTGRES_DATABASE_URL": database_url,
        "FIN_OPS_TEST_DEFAULT_AUTH": "1",
        "FIN_OPS_DISABLE_STARTUP_HISTORICAL_ETC_REPAIR": "1",
        "FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED": "0",
        "FIN_OPS_POSTGRES_POOL_ENABLED": "0",
        "FIN_OPS_POSTGRES_READ_POOL_ENABLED": "0",
    }
    removed = {
        "FIN_OPS_OA_MONGO_URI",
        "FIN_OPS_OA_MONGO_DATABASE",
        "FIN_OPS_OA_MONGO_COLLECTION",
        "FIN_OPS_STATE_MONGO_URI",
        "FIN_OPS_STATE_MONGO_DATABASE",
    }
    previous_removed = {key: os.environ.get(key) for key in removed}
    with patch.dict(os.environ, updates, clear=False):
        for key in removed:
            os.environ.pop(key, None)
        try:
            yield
        finally:
            for key, value in previous_removed.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class AppPostgresModeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self._temp_dir = TemporaryDirectory()

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def _build_app(self):
        with postgres_app_env(self.database_url):
            return build_application(data_dir=Path(self._temp_dir.name))

    def test_readiness_session_and_app_health_are_secret_safe(self) -> None:
        app = self._build_app()

        readiness = app.readiness_summary()
        storage = readiness["storage"]
        self.assertEqual(storage["backend"], "postgres")
        self.assertEqual(storage["mode"], "postgres")
        self.assertEqual(storage["postgres_status"], "ready")
        self.assertGreaterEqual(storage["postgres_schema_version"], 8)
        self.assertNotIn("url", str(readiness).lower())
        self.assertNotIn("password", str(readiness).lower())

        public_health = app.handle_request("GET", "/health")
        self.assertEqual(public_health.status_code, 200)

        session_response = app.handle_request("GET", "/api/session/me")
        session_payload = json.loads(session_response.body)
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_payload["user"]["username"], "test_finops_user")
        self.assertTrue(session_payload["can_access_app"])

        app_health_response = app.handle_request("GET", "/api/app-health")
        app_health_payload = json.loads(app_health_response.body)
        self.assertEqual(app_health_response.status_code, 200)
        self.assertEqual(app_health_payload["status"], "blocked")
        self.assertIn("dependencies", app_health_payload)
        self.assertEqual(app_health_payload["dependencies"]["oa_sync"]["status"], "unavailable")
        self.assertEqual(app_health_payload["dependencies"]["oa_mongo"]["status"], "unavailable")
        self.assertNotIn("postgresql://", json.dumps(app_health_payload).lower())

    def test_stale_preview_delta_does_not_downgrade_confirmed_import(self) -> None:
        stale_api = self._build_app()
        invoice_session = stale_api._file_import_service.preview_files(  # noqa: SLF001
            imported_by="user_finance_01",
            uploads=[UploadedImportFile(file_name=INVOICE_JAN.name, content=INVOICE_JAN.content)],
        )
        stale_api._persist_import_preview_delta(invoice_session.id)  # noqa: SLF001
        invoice_file = invoice_session.files[0]
        invoice_batch_id = invoice_file.preview_batch_id

        worker_api = self._build_app()
        confirmed_session = worker_api._file_import_service.confirm_session(  # noqa: SLF001
            session_id=invoice_session.id,
            selected_file_ids=[invoice_file.id],
        )
        worker_api._state_store.save_import_delta(  # noqa: SLF001
            worker_api._file_import_service.confirmed_session_persistence_payload(  # noqa: SLF001
                session_id=confirmed_session.id,
                selected_file_ids=[invoice_file.id],
            )
        )

        stale_bank_session = stale_api._file_import_service.preview_files(  # noqa: SLF001
            imported_by="user_finance_01",
            uploads=[UploadedImportFile(file_name=PINGAN_JAN.name, content=PINGAN_JAN.content)],
        )
        stale_api._persist_import_preview_delta(stale_bank_session.id)  # noqa: SLF001

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                f"select status from app.import_batches where legacy_mongo_id = '{invoice_batch_id}';",
            ),
            "completed",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                f"select status from app.import_files where legacy_mongo_id = '{invoice_file.id}';",
            ),
            "confirmed",
        )
        stale_api.shutdown_background_jobs()
        worker_api.shutdown_background_jobs()

    def test_controlled_import_repair_restores_only_exact_downgraded_lifecycle(self) -> None:
        app = self._build_app()
        session = app._file_import_service.preview_files(  # noqa: SLF001
            imported_by="user_finance_01",
            uploads=[UploadedImportFile(file_name=INVOICE_JAN.name, content=INVOICE_JAN.content)],
        )
        app._persist_import_preview_delta(session.id)  # noqa: SLF001
        file = session.files[0]
        batch_id = str(file.preview_batch_id)
        confirmed = app._file_import_service.confirm_session(  # noqa: SLF001
            session_id=session.id,
            selected_file_ids=[file.id],
        )
        app._state_store.save_import_delta(  # noqa: SLF001
            app._file_import_service.confirmed_session_persistence_payload(  # noqa: SLF001
                session_id=confirmed.id,
                selected_file_ids=[file.id],
            )
        )
        connection = app._state_store._connection  # noqa: SLF001
        connection.execute(
            """
            insert into job.import_jobs(
                import_type, import_session_id, status, stage, payload, result_payload, finished_at
            ) values (
                'file_import.confirm', %s, 'succeeded', 'succeeded', %s::jsonb, %s::jsonb, now()
            )
            """,
            (
                session.id,
                json.dumps({"session_id": session.id, "selected_file_ids": [file.id]}),
                json.dumps({"selected": 1, "confirmed": 1}),
            ),
        )
        connection.execute(
            """
            update app.import_batches
            set status = 'pending',
                raw_payload = jsonb_set(raw_payload, '{normalized_payload,status}', '"pending"'::jsonb)
            where legacy_mongo_id = %s
            """,
            (batch_id,),
        )
        connection.execute(
            """
            update app.import_files
            set status = 'preview_ready',
                raw_payload = jsonb_set(
                    jsonb_set(
                        jsonb_set(raw_payload, '{normalized_payload,status}', '"preview_ready"'::jsonb),
                        '{normalized_payload,batch_id}', 'null'::jsonb
                    ),
                    '{normalized_payload,session_status}', '"preview_ready"'::jsonb
                )
            where legacy_mongo_id = %s
            """,
            (file.id,),
        )

        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level serializable")
            plan = build_import_audit_repair_plan(
                load_import_audit_repair_snapshot(
                    transaction,
                    lifecycle_batch_id=batch_id,
                    lifecycle_file_id=file.id,
                )
            )
            self.assertEqual(len(plan["lifecycle_repairs"]), 1)
            apply_import_audit_repair(transaction, plan)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                f"select status from app.import_batches where legacy_mongo_id = '{batch_id}';",
            ),
            "completed",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                f"select status from app.import_files where legacy_mongo_id = '{file.id}';",
            ),
            "confirmed",
        )
        with connection.transaction() as transaction:
            terminal_plan = build_import_audit_repair_plan(
                load_import_audit_repair_snapshot(
                    transaction,
                    lifecycle_batch_id=batch_id,
                    lifecycle_file_id=file.id,
                )
            )
        self.assertEqual(terminal_plan["lifecycle_repairs"], [])
        app.shutdown_background_jobs()

    def test_workbench_settings_round_trip_survives_app_rebuild(self) -> None:
        app = self._build_app()
        create_response = app.handle_request(
            "POST",
            "/api/workbench/settings/projects",
            body=json.dumps(
                {
                    "actor_id": "test_finops_user",
                    "project_code": "stage06-project",
                    "project_name": "阶段06测试项目",
                }
            ),
        )
        self.assertEqual(create_response.status_code, 200, create_response.body)

        rebuilt_app = self._build_app()
        settings_response = rebuilt_app.handle_request("GET", "/api/workbench/settings")
        settings_payload = json.loads(settings_response.body)

        self.assertEqual(settings_response.status_code, 200)
        serialized = json.dumps(settings_payload, ensure_ascii=False)
        self.assertIn("阶段06测试项目", serialized)
        self.assertNotIn("password", serialized.lower())
        self.assertNotIn("postgresql://", serialized.lower())

    def test_import_preview_confirm_persists_to_postgres_formal_tables(self) -> None:
        app = self._build_app()
        with patch.object(app, "_run_workbench_auto_matching_for_scopes", return_value=None):
            preview, confirmed_batch = seed_confirmed_import(
                app,
                batch_type=BatchType.INPUT_INVOICE,
                source_name="stage07-input.json",
                imported_by="test_finops_user",
                rows=[
                    {
                        "counterparty_name": "供应商A",
                        "invoice_no": "INV-STAGE07-001",
                        "invoice_date": "2026-03-01",
                        "amount": "100.00",
                        "tax_amount": "6.00",
                        "total_with_tax": "106.00",
                    }
                ],
            )
        batch_id = preview.id
        self.assertEqual(confirmed_batch.status.value, "completed")
        app._persist_confirmed_import_delta_with_read_model_invalidation(
            import_state_payload={
                "imports": app._import_service.persistence_snapshot_for_batches([batch_id]),
            },
            invalidate_cost_statistics=False,
        )

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                f"select status from app.import_batches where legacy_mongo_id = '{batch_id}';",
            ),
            "completed",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                f"select linked_object_type from app.import_batch_rows where legacy_batch_id = '{batch_id}';",
            ),
            "invoice",
        )
        self.assertEqual(
            fetch_scalar(self.database_url, "select count(*) from app.invoices where invoice_no = 'INV-STAGE07-001';"),
            "1",
        )

    def test_pending_invoice_attach_existing_command_log_persists_to_formal_postgres_table(self) -> None:
        app = self._build_app()
        transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Postgres Recoverable")
        invoice_id = self._create_input_invoice(
            app,
            seller_name="Vendor Postgres Recoverable",
            invoice_no="PG-ATTACH-RECOVER",
        )
        payload = {"invoice_id": invoice_id}
        preview_response = app.handle_request(
            "POST",
            f"/api/pending-invoices/rows/{transaction_id}/attach-existing-invoice/preview",
            body=json.dumps(payload),
        )
        preview = json.loads(preview_response.body)
        self.assertEqual(preview_response.status_code, 200, preview_response.body)
        app._pending_invoice_application_service._fault_injector = (
            lambda phase, _command: (_ for _ in ()).throw(RuntimeError("boom"))
            if phase == "after_relation_created"
            else None
        )

        with self.assertRaises(RuntimeError):
            app.handle_request(
                "POST",
                f"/api/pending-invoices/rows/{transaction_id}/attach-existing-invoice",
                body=json.dumps({**payload, "preview_id": preview["preview_id"], "request_id": "pg-recoverable"}),
            )

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from app.pending_invoice_manual_invoice_commands where command_id = 'pg-recoverable';",
            ),
            "1",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select status from app.pending_invoice_manual_invoice_commands where command_id = 'pg-recoverable';",
            ),
            "failed_recoverable",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select last_successful_status from app.pending_invoice_manual_invoice_commands "
                "where command_id = 'pg-recoverable';",
            ),
            "relation_created",
        )

    def test_bank_auto_tag_rules_and_pending_invoice_rules_round_trip_through_their_owners(self) -> None:
        app = self._build_app()
        auto_rules = app._app_settings_service.get_bank_auto_tag_rules_payload()
        active_rules = [
            {**rule, "direction": "expense"} if rule["code"] == "fee" else rule
            for rule in auto_rules["active_rules"]
        ]
        auto_rules_response = app.handle_request(
            "PUT",
            "/api/bank-details/auto-tag-rules",
            body=json.dumps({
                "expected_version": auto_rules["version"],
                "active_rules": active_rules,
                "archived_rules": auto_rules["archived_rules"],
            }),
        )
        self.assertEqual(auto_rules_response.status_code, 200, auto_rules_response.body)

        pending_rules = app._app_settings_service.get_pending_invoice_settings_payload()
        pending_rules_response = app.handle_request(
            "PUT",
            "/api/pending-invoices/rules",
            body=json.dumps({
                "version": pending_rules["pending_invoice_tag_groups"]["version"],
                "groups": {
                    "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                    "no_invoice_required": {"tag_codes": ["salary"]},
                },
            }),
        )
        self.assertEqual(pending_rules_response.status_code, 200, pending_rules_response.body)

        rebuilt_app = self._build_app()
        reloaded_auto_rules = rebuilt_app._app_settings_service.get_bank_auto_tag_rules_payload()
        reloaded_pending_rules = rebuilt_app._app_settings_service.get_pending_invoice_settings_payload()
        self.assertEqual(next(rule for rule in reloaded_auto_rules["active_rules"] if rule["code"] == "fee")["direction"], "expense")
        self.assertEqual(
            reloaded_pending_rules["pending_invoice_tag_groups"]["groups"]["bank_statement_as_invoice"]["tag_codes"],
            ["fee"],
        )

    def test_bank_flow_rule_save_is_noop_or_single_scope_refresh_in_postgres(self) -> None:
        app = self._build_app()
        current = app._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload()

        noop_response = app.handle_request(
            "PUT",
            "/api/bank-flow-rule-batches/tag-rules",
            body=json.dumps({"expected_version": current["version"], "rules": current["rules"]}),
        )
        noop_payload = json.loads(noop_response.body)

        self.assertEqual(noop_response.status_code, 200, noop_response.body)
        self.assertEqual(noop_payload["version"], current["version"])
        self.assertEqual(app._audit_service.as_dicts(), [])
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from job.read_model_dirty_scopes "
                "where scope_type = 'bank_flow_rule_batch' and scope_key = 'all';",
            ),
            "0",
        )

        changed_rules = [
            {**rule, "requires_invoice": not bool(rule["requires_invoice"])}
            if rule["tag_code"] == current["rules"][0]["tag_code"]
            else rule
            for rule in current["rules"]
        ]
        changed_response = app.handle_request(
            "PUT",
            "/api/bank-flow-rule-batches/tag-rules",
            body=json.dumps({"expected_version": current["version"], "rules": changed_rules}),
        )
        changed_payload = json.loads(changed_response.body)

        self.assertEqual(changed_response.status_code, 200, changed_response.body)
        self.assertEqual(changed_payload["version"], current["version"] + 1)
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from job.read_model_dirty_scopes "
                "where scope_type = 'bank_flow_rule_batch' and scope_key = 'all';",
            ),
            "1",
        )
        self.assertEqual(
            [event["action"] for event in app._audit_service.as_dicts()],
            ["bank_flow_rule_batch_tag_rules_updated"],
        )

    @staticmethod
    def _create_bank_transaction(app: object, *, counterparty_name: str, credit: bool = False) -> str:
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="postgres-pending-invoice-bank.json",
            imported_by="api-test",
            rows=[
                {
                    "account_no": "622200001234",
                    "txn_date": "2026-05-20",
                    "trade_time": "2026-05-20 10:00:00",
                    "counterparty_name": counterparty_name,
                    "debit_amount": "" if credit else "118.00",
                    "credit_amount": "118.00" if credit else "",
                    "bank_serial_no": f"SERIAL-{counterparty_name}",
                    "selected_bank_name": "工商银行",
                    "selected_bank_last4": "1234",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        app._persist_state()
        return str(preview.row_results[0].linked_object_id)

    @staticmethod
    def _create_input_invoice(app: object, *, seller_name: str, invoice_no: str) -> str:
        preview = app._import_service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="postgres-pending-invoice-input.json",
            imported_by="api-test",
            rows=[
                {
                    "counterparty_name": seller_name,
                    "seller_name": seller_name,
                    "invoice_no": invoice_no,
                    "invoice_date": "2026-05-20",
                    "amount": "111.32",
                    "tax_amount": "6.68",
                    "total_with_tax": "118.00",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        app._persist_state()
        return str(preview.row_results[0].linked_object_id)


if __name__ == "__main__":
    unittest.main()
