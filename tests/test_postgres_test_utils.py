from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, call, patch

from fin_ops_platform.services.postgres_connection import redact_database_url
from postgres_test_utils import (
    assert_safe_test_database_url,
    discover_stage06_migrations,
    require_postgres_test_database_url,
    reset_test_database,
    restore_current_test_database,
)


class PostgresTestUtilsTests(unittest.TestCase):
    def test_class_cleanup_runs_even_when_historical_setup_fails(self) -> None:
        restored = Mock()

        class BrokenMigrationFixture(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                cls.addClassCleanup(restored)
                raise RuntimeError("synthetic historical setup failure")

            def test_unreachable(self):
                self.fail("initialization must fail before this test")

        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(BrokenMigrationFixture).run(result)
        restored.assert_called_once_with()
        self.assertEqual(len(result.errors), 1)
        self.assertIn("synthetic historical setup failure", result.errors[0][1])

    def test_restore_current_schema_discards_fixture_before_migrating(self) -> None:
        database_url = "postgresql://user:pw@127.0.0.1/fin_ops_test"
        operations = Mock()
        with patch("postgres_test_utils.reset_test_database", operations.reset), patch(
            "postgres_test_utils.apply_test_migrations", operations.migrate
        ):
            restore_current_test_database(database_url)
        self.assertEqual(operations.mock_calls, [call.reset(database_url), call.migrate(database_url)])

    def test_restore_does_not_continue_after_reset_failure_or_hide_migration_failure(self) -> None:
        with patch("postgres_test_utils.reset_test_database", side_effect=RuntimeError("reset failed")), patch(
            "postgres_test_utils.apply_test_migrations"
        ) as migrate:
            with self.assertRaisesRegex(RuntimeError, "reset failed"):
                restore_current_test_database("postgresql://localhost/fin_ops_test")
            migrate.assert_not_called()
        with patch("postgres_test_utils.reset_test_database"), patch(
            "postgres_test_utils.apply_test_migrations", side_effect=RuntimeError("migration failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "migration failed"):
                restore_current_test_database("postgresql://localhost/fin_ops_test")

    def test_require_postgres_test_database_url_ignores_database_url(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pw@127.0.0.1/fin_ops_test"}, clear=True):
            with self.assertRaises(unittest.SkipTest):
                require_postgres_test_database_url()

    def test_safe_test_database_url_rejects_reserved_names(self) -> None:
        for database_name in ("fin_ops", "postgres", "template0", "template1"):
            with self.subTest(database_name=database_name):
                with self.assertRaisesRegex(AssertionError, database_name):
                    assert_safe_test_database_url(f"postgresql://user:pw@127.0.0.1/{database_name}")

    def test_safe_test_database_url_redacts_password_when_rejecting_non_test_name(self) -> None:
        database_url = "postgresql://user:secret@127.0.0.1/fin_ops_stage"

        with self.assertRaises(AssertionError) as error:
            assert_safe_test_database_url(database_url)

        self.assertIn(redact_database_url(database_url), str(error.exception))
        self.assertNotIn("secret", str(error.exception))

    def test_discover_stage06_migrations_is_pinned_to_current_set(self) -> None:
        migrations = discover_stage06_migrations()

        self.assertEqual([item.version for item in migrations], [f"{number:04d}" for number in range(1, 171)])

    def test_reset_test_database_requires_visibly_disposable_database_name_even_with_override(self) -> None:
        database_url = "postgresql://user:secret@127.0.0.1/fin_ops_stage"

        with patch.dict(os.environ, {"FIN_OPS_ALLOW_POSTGRES_TEST_DB": "1"}):
            with self.assertRaises(AssertionError) as error:
                reset_test_database(database_url)

        self.assertIn(redact_database_url(database_url), str(error.exception))
        self.assertNotIn("secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
