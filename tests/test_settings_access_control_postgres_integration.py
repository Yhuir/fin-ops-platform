from __future__ import annotations

import json
from pathlib import Path
import unittest

from fin_ops_platform.postgres import migrate
from tests.postgres_test_utils import (
    apply_test_migrations_through,
    fetch_scalar,
    require_postgres_test_database_url,
    reset_test_database,
)


class SettingsAccessControlPostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        reset_test_database(self.database_url)
        apply_test_migrations_through(self.database_url, "0132")

    def tearDown(self) -> None:
        reset_test_database(self.database_url)

    def test_0133_repairs_0132_order_and_enforces_exact_acl_shape(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            delete from app.app_settings where settings_key = 'app_settings';
            insert into app.app_settings(
                settings_key, version, settings_payload, raw_payload
            ) values (
                'app_settings',
                1,
                '{
                    "allowed_usernames":["FULL001","READ001","YNSYLP005"],
                    "readonly_export_usernames":["READ001"],
                    "admin_usernames":["YNSYLP005"],
                    "full_access_usernames":["FULL001"],
                    "access_control_version":2
                }'::jsonb,
                '{
                    "normalized_payload":{
                        "allowed_usernames":["FULL001","READ001","YNSYLP005"],
                        "readonly_export_usernames":["READ001"],
                        "admin_usernames":["YNSYLP005"],
                        "full_access_usernames":["FULL001"],
                        "access_control_version":2
                    }
                }'::jsonb
            );
            """,
        )

        apply_test_migrations_through(self.database_url, "0133")

        repaired = json.loads(
            fetch_scalar(
                self.database_url,
                """
                select settings_payload::text
                from app.app_settings
                where settings_key = 'app_settings';
                """,
            )
        )
        self.assertEqual(
            repaired["allowed_usernames"],
            ["YNSYLP005", "FULL001", "READ001"],
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select (raw_payload->'normalized_payload' = settings_payload)::text
                from app.app_settings
                where settings_key = 'app_settings';
                """,
            ),
            "true",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select count(*)
                from audit.events
                where actor_id = 'migration:0133'
                  and event_type = 'settings.access_control.canonical_order_repaired';
                """,
            ),
            "1",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select convalidated::text
                from pg_constraint
                where conrelid = 'app.app_settings'::regclass
                  and conname = 'app_settings_access_control_canonical_order_guard';
                """,
            ),
            "true",
        )

        migration_sql = (
            Path(
                "backend/src/fin_ops_platform/postgres/migrations/"
                "0133_settings_access_control_canonical_order.sql"
            ).read_text(encoding="utf-8")
        )
        migrate.run_psql(self.database_url, sql=migration_sql)
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from audit.events where actor_id = 'migration:0133';",
            ),
            "1",
        )

        invalid_payloads = (
            {
                **repaired,
                "allowed_usernames": ["FULL001", "YNSYLP005", "READ001"],
            },
            {
                **repaired,
                "allowed_usernames": ["YNSYLP005", "full001", "READ001"],
            },
            {
                **repaired,
                "full_access_usernames": ["FULL001", "FULL001"],
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(migrate.MigrationError):
                encoded = json.dumps(payload, ensure_ascii=False)
                migrate.run_psql(
                    self.database_url,
                    sql=f"""
                    update app.app_settings
                    set settings_payload = $json${encoded}$json$::jsonb,
                        raw_payload = jsonb_set(
                            raw_payload,
                            '{{normalized_payload}}',
                            $json${encoded}$json$::jsonb,
                            true
                        )
                    where settings_key = 'app_settings';
                    """,
                )
