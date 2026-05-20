from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fin_ops_platform.services.postgres_connection import redact_database_url

from postgres_test_utils import assert_safe_test_database_url, discover_stage06_migrations, require_postgres_test_database_url


class PostgresTestUtilsTests(unittest.TestCase):
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

        self.assertEqual([item.version for item in migrations], [f"{number:04d}" for number in range(1, 9)])


if __name__ == "__main__":
    unittest.main()
