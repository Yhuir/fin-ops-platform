from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fin_ops_platform.app.cash_runtime import CashRuntime, cash_postgres_settings
from fin_ops_platform.services.cash_domain import CashError
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings

from tests.postgres_test_utils import apply_test_migrations, truncate_test_database


class CashRuntimeTests(unittest.TestCase):
    def test_source_initialization_failure_closes_cash_pool(self):
        with patch("fin_ops_platform.app.cash_runtime.PostgresConnection") as connection, \
             patch("fin_ops_platform.app.cash_runtime.cash_postgres_settings", return_value=Mock()), \
             patch("fin_ops_platform.app.cash_runtime.load_mongo_oa_settings", side_effect=ValueError("configuration")):
            with self.assertRaises(ValueError):
                CashRuntime(None)
            connection.return_value.close.assert_called_once()

    def test_existing_database_login_and_bounded_pool_are_used(self):
        url = "postgresql://ordinary:secret@localhost:5432/test"
        with patch.dict(os.environ, {"FIN_OPS_POSTGRES_DATABASE_URL": url}, clear=True):
            settings = cash_postgres_settings()
        self.assertEqual(settings.database_url, url)
        self.assertEqual((settings.pool_min_size, settings.pool_max_size, settings.pool_max_waiting), (1, 2, 8))
        self.assertEqual(settings.pool_acquire_timeout_seconds, 2)
        self.assertEqual(settings.statement_timeout_ms, 5000)
        self.assertEqual(settings.pool_name, "fin-ops-cash")
        self.assertTrue(settings.pool_enabled)

    def test_stricter_shared_limits_are_not_relaxed(self):
        with patch.dict(os.environ, {
            "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://ordinary:secret@localhost/test",
            "FIN_OPS_POSTGRES_POOL_MAX_SIZE": "1", "FIN_OPS_POSTGRES_POOL_MIN_SIZE": "1",
            "FIN_OPS_POSTGRES_POOL_MAX_WAITING": "3", "FIN_OPS_POSTGRES_STATEMENT_TIMEOUT_MS": "1000",
            "FIN_OPS_POSTGRES_POOL_ACQUIRE_TIMEOUT_SECONDS": "1", "FIN_OPS_POSTGRES_CONNECT_TIMEOUT_SECONDS": "2",
        }, clear=True):
            settings = cash_postgres_settings()
        self.assertEqual((settings.pool_max_size, settings.pool_max_waiting), (1, 3))
        self.assertEqual((settings.statement_timeout_ms, settings.pool_acquire_timeout_seconds,
                          settings.connect_timeout_seconds), (1000, 1, 2))

    def test_existing_database_url_alias_uses_the_shared_loader(self):
        url = "postgresql://ordinary:secret@localhost/test"
        with patch.dict(os.environ, {"DATABASE_URL": url}, clear=True):
            self.assertEqual(cash_postgres_settings().database_url, url)

    def test_removed_cash_override_cannot_redirect_the_module(self):
        url = "postgresql://ordinary:secret@localhost/test"
        with patch.dict(os.environ, {
            "FIN_OPS_POSTGRES_DATABASE_URL": url,
            "FIN_OPS_CASH_POSTGRES_DATABASE_URL": "postgresql://obsolete:secret@elsewhere/other",
        }, clear=True):
            self.assertEqual(cash_postgres_settings().database_url, url)

    def test_missing_or_invalid_shared_configuration_is_explicit_and_secret_safe(self):
        for env in ({}, {"FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://ordinary:secret@localhost/test",
                         "FIN_OPS_POSTGRES_POOL_MAX_SIZE": "invalid-secret"}):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                with self.assertRaises(CashError) as caught:
                    cash_postgres_settings()
                self.assertEqual(caught.exception.status, 503)
                self.assertEqual(caught.exception.code, "cash_dependency_unavailable")
                self.assertNotIn("secret", str(caught.exception))


@unittest.skipUnless(os.environ.get("FIN_OPS_CASH_TEST_DATABASE_URL"), "requires explicit isolated cash PostgreSQL test database")
class CashRuntimePostgresTests(unittest.TestCase):
    def test_shared_login_real_routes_create_read_delete_without_ordinary_data_changes(self):
        dsn = os.environ["FIN_OPS_CASH_TEST_DATABASE_URL"]
        ordinary = PostgresConnection(PostgresSettings(dsn, pool_enabled=False))
        self.addCleanup(ordinary.close)
        identity = ordinary.fetch_one("SELECT current_database() AS database, current_user AS role")
        if not identity["database"].startswith("fin_ops_cash_test_"):
            raise RuntimeError("Cash fixtures require an explicit fin_ops_cash_test_* database")
        apply_test_migrations(dsn)
        grants = ordinary.fetch_one("""SELECT count(*) AS tables,
            bool_and(has_table_privilege('fin_ops_app_runtime',c.oid,'SELECT')
                AND has_table_privilege('fin_ops_app_runtime',c.oid,'INSERT')
                AND has_table_privilege('fin_ops_app_runtime',c.oid,'UPDATE')
                AND has_table_privilege('fin_ops_app_runtime',c.oid,'DELETE')) AS dml
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='cash' AND c.relkind='r'""")
        self.assertEqual(grants, {"tables": 10, "dml": True})
        truncate_test_database(dsn)
        self.addCleanup(truncate_test_database, dsn)
        ordinary.execute("TRUNCATE cash.settlements,cash.items,cash.flows,cash.task_occurrences,cash.task_templates,cash.accounts,cash.categories,cash.bill_labels,cash.deleted_submission_ids")
        self.addCleanup(ordinary.execute, "TRUNCATE cash.settlements,cash.items,cash.flows,cash.task_occurrences,cash.task_templates,cash.accounts,cash.categories,cash.bill_labels,cash.deleted_submission_ids")
        account_id, category_id, flow_id = (str(uuid4()) for _ in range(3))
        ordinary.execute("""INSERT INTO app.bank_transactions(id,account_no,txn_direction,counterparty_name_raw,amount,signed_amount,txn_date,txn_month,status)
            VALUES (%s,'synthetic-account','outflow','Synthetic vendor',987654.32,-987654.32,'2026-01-15','2026-01-01','active')""", (flow_id,))
        before = ordinary.fetch_all("SELECT * FROM app.bank_transactions ORDER BY id")
        session = SimpleNamespace(can_admin_access=False, allowed_page_keys=frozenset({"cash"}), token="test-only",
                                  identity=SimpleNamespace(username="CASH_TEST", display_name="Synthetic operator"))
        with patch.dict(os.environ, {"FIN_OPS_POSTGRES_DATABASE_URL": dsn}), \
             patch("fin_ops_platform.app.cash_runtime.load_mongo_oa_settings", return_value=None):
            runtime = CashRuntime(None)
            self.addCleanup(runtime.close)
            self.assertEqual(runtime.connection.settings.database_url, ordinary.settings.database_url)
            self.assertEqual(runtime.connection.fetch_one("SELECT current_user AS role")["role"], identity["role"])
            routes = runtime.routes(session, lambda status, payload, headers: SimpleNamespace(status=status, payload=payload, headers=headers))

            def call(method, path, status, *, payload=None, query=None):
                response = routes.route(method, path, query or {}, json.dumps(payload) if payload is not None else None, session=session)
                self.assertEqual(response.status, status, response.payload)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                return response.payload

            call("POST", "/api/cash/settings/accounts", 201, payload={
                "id": account_id, "name": "Synthetic account", "kind": "cash",
                "opening_date": "2026-01-01", "opening_amount": "100.00",
            })
            call("POST", "/api/cash/settings/categories", 201, payload={
                "id": category_id, "name": "Synthetic receipt", "group": "receipt",
            })
            created = call("POST", "/api/cash/flows", 201, payload={
                "id": flow_id, "kind": "receipt", "amount": "12.30", "occurred_on": "2026-01-15",
                "to_account_id": account_id, "category_id": category_id,
                "project_mode": "selection", "content": "Synthetic runtime receipt",
            })
            self.assertEqual(created["flow"]["source_kind"], "manual")
            period = {"date_from": ["2026-01-01"], "date_to": ["2026-01-31"], "account_id": [account_id]}
            listed = call("GET", "/api/cash/flows", 200, query=period)
            self.assertEqual(listed["pagination"]["total"], 1)
            self.assertEqual([row["id"] for row in listed["rows"]], [flow_id])
            self.assertEqual(listed["summary"]["filtered_totals"]["income_amount"], "12.30")
            self.assertEqual(listed["summary"]["account_balances"][0]["ending_balance"], "112.30")
            removed = call("POST", f"/api/cash/flows/{flow_id}/delete", 200, payload={"expected_version": created["version"]})
            self.assertTrue(removed["deleted"])
            empty = call("GET", "/api/cash/flows", 200, query=period)
            self.assertEqual(empty["rows"], [])
            self.assertEqual(empty["summary"]["filtered_totals"]["income_amount"], "0.00")
            self.assertEqual(empty["summary"]["account_balances"][0]["ending_balance"], "100.00")
            self.assertEqual(ordinary.fetch_all("SELECT * FROM app.bank_transactions ORDER BY id"), before)


if __name__ == "__main__":
    unittest.main()
