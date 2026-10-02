import json
import unittest
from pathlib import Path

from fin_ops_platform.postgres import migrate
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url


class SettingsRetirementPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def test_migration_removes_only_two_keys_and_is_idempotent(self):
        connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(connection.close)
        payload = {
            "completed_project_ids": ["manual-project"], "oa_invoice_offset": {"applicant_names": ["历史申请人"]},
            "manual_projects": [{"id": "manual-project", "project_name": "保留项目"}],
            "synced_projects": [{"id": "oa-project"}], "pending_invoice_tag_groups": {"version": 9},
            "pending_output_invoice_tag_groups": {"version": 4}, "bank_account_mappings": [{"last4": "1234"}],
            "page_access_accounts": [], "access_control_version": 1, "unrelated": {"keep": True},
        }
        connection.execute("delete from app.app_settings where settings_key = %s", ("app_settings",))
        connection.execute("insert into app.app_settings(settings_key, settings_payload, raw_payload, version) values (%s, %s::jsonb, %s::jsonb, 7)", ("app_settings", json.dumps(payload), json.dumps({"normalized_payload": payload, "other": "preserve"})))
        sql = Path("backend/src/fin_ops_platform/postgres/migrations/0184_remove_retired_settings.sql").read_text()
        migrate.run_psql(self.database_url, sql=sql)
        row = connection.fetch_one("select settings_payload, raw_payload, version, updated_at from app.app_settings where settings_key = %s", ("app_settings",))
        expected = {key: value for key, value in payload.items() if key not in {"completed_project_ids", "oa_invoice_offset"}}
        self.assertEqual(row["settings_payload"], expected)
        self.assertEqual(row["raw_payload"], {"normalized_payload": expected, "other": "preserve"})
        self.assertEqual(row["version"], 8)
        migrate.run_psql(self.database_url, sql=sql)
        self.assertEqual(connection.fetch_one("select settings_payload, raw_payload, version, updated_at from app.app_settings where settings_key = %s", ("app_settings",)), row)
