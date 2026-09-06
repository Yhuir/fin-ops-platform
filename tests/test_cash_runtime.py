from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from fin_ops_platform.app.cash_runtime import CashRuntime, cash_postgres_settings
from fin_ops_platform.services.cash_domain import CashError
from fin_ops_platform.services.postgres_repositories.cash_runtime_identity import assert_cash_runtime_identity


class CashRuntimeTests(unittest.TestCase):
    def test_source_initialization_failure_closes_cash_pool(self):
        with patch.dict("os.environ", {"FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://ordinary:p@localhost/test"}), \
             patch("fin_ops_platform.app.cash_runtime.cash_postgres_settings"), \
             patch("fin_ops_platform.app.cash_runtime.PostgresConnection") as connection, \
             patch("fin_ops_platform.app.cash_runtime.assert_cash_runtime_identity"), \
             patch("fin_ops_platform.app.cash_runtime.load_mongo_oa_settings", side_effect=ValueError("configuration")):
            with self.assertRaises(ValueError):
                CashRuntime(None)
            connection.return_value.close.assert_called_once()

    def test_same_database_distinct_identity_and_bounded_pool(self):
        with patch.dict("os.environ", {
            "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://ordinary:p@localhost:5432/test",
            "FIN_OPS_CASH_POSTGRES_DATABASE_URL": "postgresql://cash:p@localhost:5432/test",
        }):
            settings = cash_postgres_settings()
        self.assertEqual(settings.pool_max_size, 2)
        self.assertEqual(settings.pool_max_waiting, 8)
        self.assertTrue(settings.pool_enabled)

    def test_missing_other_database_or_shared_user_rejected_without_dsn_leak(self):
        for cash in ("", "postgresql://cash:secret@other:5432/test", "postgresql://cash:secret@localhost:5432/other",
                     "postgresql://ordinary:secret@localhost:5432/test", "invalid secret dsn",
                     "postgresql://cash:secret@localhost/test?options=-c%20role%3Dordinary",
                     "service=secret user=cash", "dbname=test user=cash",
                     "host=localhost,other dbname=test user=cash"):
            with self.subTest(cash=cash), patch.dict("os.environ", {
                "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://ordinary:p@localhost:5432/test",
                "FIN_OPS_CASH_POSTGRES_DATABASE_URL": cash,
            }):
                with self.assertRaises(CashError) as caught:
                    cash_postgres_settings()
                self.assertEqual(caught.exception.status, 503)
                self.assertNotIn("secret", str(caught.exception))

    def test_default_postgres_port_is_the_same_endpoint(self):
        with patch.dict("os.environ", {
            "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://ordinary:p@localhost:5432/test",
            "FIN_OPS_CASH_POSTGRES_DATABASE_URL": "postgresql://cash:p@localhost/test",
        }):
            self.assertEqual(cash_postgres_settings().pool_max_size, 2)

    def test_effective_privileges_fail_closed(self):
        clean = dict(privileged=False, ordinary_member=False, cash_usage=True,
                     cash_ddl=False, database_ddl=False, inherited_roles=False, cash_owner=False,
                     ordinary_access=False, writable_tables=10)
        connection = Mock()
        connection.fetch_one.return_value = clean
        assert_cash_runtime_identity(connection, "ordinary")
        for key in ("privileged", "ordinary_member", "cash_ddl", "database_ddl", "inherited_roles", "cash_owner", "ordinary_access"):
            with self.subTest(key=key):
                connection.fetch_one.return_value = {**clean, key: True}
                with self.assertRaises(CashError):
                    assert_cash_runtime_identity(connection, "ordinary")


if __name__ == "__main__":
    unittest.main()
