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

from postgres_test_utils import apply_test_migrations, fetch_scalar, require_postgres_test_database_url, truncate_test_database


@contextmanager
def postgres_app_env(database_url: str):
    updates = {
        "FIN_OPS_APP_STORAGE_BACKEND": "postgres",
        "FIN_OPS_POSTGRES_DATABASE_URL": database_url,
        "FIN_OPS_TEST_DEFAULT_AUTH": "1",
        "FIN_OPS_DISABLE_STARTUP_HISTORICAL_ETC_REPAIR": "1",
        "FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED": "0",
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
        self.assertIn(app_health_payload["status"], {"ok", "busy"})
        self.assertIn("dependencies", app_health_payload)

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

    def test_import_preview_confirm_persists_to_postgres_and_survives_rebuild(self) -> None:
        app = self._build_app()
        preview_response = app.handle_request(
            "POST",
            "/imports/preview",
            body=json.dumps(
                {
                    "batch_type": "input_invoice",
                    "source_name": "stage07-input.json",
                    "imported_by": "test_finops_user",
                    "rows": [
                        {
                            "counterparty_name": "供应商A",
                            "invoice_no": "INV-STAGE07-001",
                            "invoice_date": "2026-03-01",
                            "amount": "100.00",
                            "tax_amount": "6.00",
                            "total_with_tax": "106.00",
                        }
                    ],
                }
            ),
        )

        self.assertEqual(preview_response.status_code, 200, preview_response.body)
        preview_payload = json.loads(preview_response.body)
        batch_id = preview_payload["batch"]["id"]
        with patch.object(app, "_run_workbench_auto_matching_for_scopes", return_value=None):
            confirm_response = app.handle_request("POST", "/imports/confirm", body=json.dumps({"batch_id": batch_id}))

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["batch"]["status"], "completed")

        rebuilt_app = self._build_app()
        batch_response = rebuilt_app.handle_request("GET", f"/imports/batches/{batch_id}")
        batch_payload = json.loads(batch_response.body)

        self.assertEqual(batch_response.status_code, 200, batch_response.body)
        self.assertEqual(batch_payload["batch"]["id"], batch_id)
        self.assertEqual(batch_payload["row_results"][0]["linked_object_type"], "invoice")

        rebuilt_app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "summary": {"oa_count": 0, "bank_count": 1, "invoice_count": 0, "paired_count": 0, "open_count": 1, "exception_count": 0},
                "paired": {"groups": []},
                "open": {
                    "groups": [
                        {
                            "group_id": "case:no_oa_stage09",
                            "oa_rows": [],
                            "bank_rows": [
                                {
                                    "id": "bk-no-oa-stage09-001",
                                    "type": "bank",
                                    "source_kind": "no_oa_bank_batch_summary",
                                    "label": "免OA · 手续费",
                                    "counterparty_name": "阶段09无OA银行行",
                                    "amount": "88.00",
                                    "trade_time": "2026-03-01",
                                    "detail_fields": {"企业流水号": "NO-OA-STAGE09-SERIAL"},
                                }
                            ],
                            "invoice_rows": [],
                        }
                    ]
                },
            },
            generated_at="2026-03-02T00:00:00+00:00",
        )
        rebuilt_app._persist_workbench_read_models_best_effort(
            snapshot=rebuilt_app._workbench_read_model_service.snapshot_scope_keys(["2026-03"]),
            changed_scope_keys=["2026-03"],
            operation="stage09_search_smoke",
        )
        search_app = self._build_app()
        search_response = search_app.handle_request("GET", "/api/search?q=NO-OA-STAGE09-SERIAL&scope=bank&month=all")
        search_payload = json.loads(search_response.body)
        self.assertEqual(search_response.status_code, 200, search_response.body)
        self.assertGreaterEqual(search_payload["summary"]["total"], 1)
        self.assertIn("NO-OA-STAGE09-SERIAL", json.dumps(search_payload, ensure_ascii=False))

        invalid_search_response = search_app.handle_request("GET", "/api/search?q=NO-OA-STAGE09-SERIAL&scope=invalid&month=all")
        self.assertEqual(invalid_search_response.status_code, 400)
        self.assertEqual(json.loads(invalid_search_response.body)["error"], "invalid_search_request")

    def test_pending_invoice_command_log_persists_to_formal_postgres_table(self) -> None:
        app = self._build_app()
        transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Postgres Recoverable")
        payload = {
            "bank_transaction_id": transaction_id,
            "invoice_no": "PG-MAN-RECOVER",
            "issue_date": "2026-05-20",
            "total_with_tax": "118.00",
            "seller_name": "Vendor Postgres Recoverable",
            "buyer_name": "云南溯源科技有限公司",
        }
        preview = json.loads(
            app.handle_request(
                "POST",
                "/api/pending-invoices/manual-invoices/preview",
                body=json.dumps(payload),
            ).body
        )
        app._pending_invoice_application_service._fault_injector = (
            lambda phase, _command: (_ for _ in ()).throw(RuntimeError("boom"))
            if phase == "after_invoice_created"
            else None
        )

        with self.assertRaises(RuntimeError):
            app.handle_request(
                "POST",
                "/api/pending-invoices/manual-invoices",
                body=json.dumps({**payload, "preview_id": preview["preview_id"], "request_id": "pg-recoverable"}),
            )

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from app.pending_invoice_manual_invoice_commands where command_id = 'pg-recoverable';",
            ),
            "1",
        )
        rebuilt_app = self._build_app()
        command = rebuilt_app._pending_invoice_commands["pg-recoverable"]
        self.assertEqual(command["status"], "failed_recoverable")
        self.assertEqual(command["last_successful_status"], "invoice_created")

    def test_bank_transaction_tags_and_pending_invoice_tag_groups_round_trip_in_postgres_mode(self) -> None:
        app = self._build_app()
        settings = app._app_settings_service.get_settings_payload()

        update_response = app.handle_request(
            "POST",
            "/api/workbench/settings",
            body=json.dumps(
                {
                    "completed_project_ids": [],
                    "bank_account_mappings": settings["bank_account_mappings"],
                    "allowed_usernames": settings["access_control"]["allowed_usernames"],
                    "readonly_export_usernames": settings["access_control"]["readonly_export_usernames"],
                    "admin_usernames": settings["access_control"]["admin_usernames"],
                    "workbench_column_layouts": settings["workbench_column_layouts"],
                    "oa_retention": settings["oa_retention"],
                    "oa_import": settings["oa_import"],
                    "oa_invoice_offset": settings["oa_invoice_offset"],
                    "bank_transaction_tags": {
                        "version": settings["bank_transaction_tags"]["version"],
                        "definitions": [
                            {
                                "code": "custom_ads_invoice",
                                "label": "广告票",
                                "path": ["自定义", "广告"],
                                "source": "custom",
                                "status": "active",
                            }
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "version": 4,
                        "groups": {
                            "requires_invoice": {"tag_codes": ["custom_ads_invoice"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        },
                    },
                }
            ),
        )
        self.assertEqual(update_response.status_code, 200, update_response.body)

        rebuilt_app = self._build_app()
        get_response = rebuilt_app.handle_request("GET", "/api/workbench/settings")
        payload = json.loads(get_response.body)
        self.assertEqual(get_response.status_code, 200, get_response.body)
        definitions_by_code = {definition["code"]: definition for definition in payload["bank_transaction_tags"]["definitions"]}
        self.assertIn("custom_ads_invoice", definitions_by_code)
        self.assertEqual(payload["pending_invoice_tag_groups"]["groups"]["requires_invoice"]["tag_codes"], ["custom_ads_invoice"])

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


if __name__ == "__main__":
    unittest.main()
