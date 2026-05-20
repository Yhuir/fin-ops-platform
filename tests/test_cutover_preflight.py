from __future__ import annotations

from io import StringIO
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.services.cutover_preflight import (
    CutoverPreflightChecker,
    CutoverPreflightConfig,
    CutoverPreflightConfigurationError,
    redact_secret_values,
)
from fin_ops_platform.tools import verify_cutover_preflight


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.executed.append((sql, params))
        if "current_database()" in sql:
            return {
                "database": "fin_ops_test",
                "user": "readonly_user",
                "schema_version": "0007",
                "schema_migrations_exists": True,
            }
        raise AssertionError(f"unexpected fetch_one SQL: {sql}")

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.executed.append((sql, params))
        if "from information_schema.tables" in sql:
            return [{"table_schema": "public", "table_name": "schema_migrations"}]
        if "as table_name" in sql and "row_count" in sql:
            return [
                {"table_name": "import_batches", "row_count": 2},
                {"table_name": "import_batch_rows", "row_count": 3},
                {"table_name": "import_files", "row_count": 4},
                {"table_name": "invoices", "row_count": 5},
                {"table_name": "bank_transactions", "row_count": 6},
                {"table_name": "search_index_rows", "row_count": 7},
            ]
        raise AssertionError(f"unexpected fetch_all SQL: {sql}")

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        raise AssertionError("preflight checker must not execute write-capable SQL")


class ExplodingChecker:
    def run(self) -> dict[str, object]:
        raise RuntimeError("failed for postgresql://user:secret-password@db.example.com/fin_ops?sslmode=require")


class CutoverPreflightTests(unittest.TestCase):
    def test_checker_report_is_json_serializable_and_secret_safe(self) -> None:
        config = CutoverPreflightConfig(
            database_url="postgresql://finops:secret-password@db.example.com:5432/fin_ops?sslmode=require",
            database_url_env="FIN_OPS_POSTGRES_DATABASE_URL",
            app_storage_backend="postgres",
            require_backup_confirmation=False,
            backup_confirmed=False,
            no_production_writes=True,
        )
        report = CutoverPreflightChecker(config=config, connection=FakeConnection()).run()

        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertEqual(report["postgres"]["schema_version"], "0007")
        self.assertEqual(report["postgres"]["core_counts"]["invoices"], 5)
        self.assertEqual(report["postgres"]["schema_migrations_table"], "public.schema_migrations")
        self.assertEqual(report["guards"]["forbidden_actions"]["cutover"], "refused")
        self.assertEqual(report["guards"]["no_production_writes"], "enforced")
        self.assertIn("postgresql://finops:***@db.example.com:5432/fin_ops", encoded)
        self.assertNotIn("secret-password", encoded)
        self.assertNotIn("sslmode=require", encoded)

    def test_redacts_nested_secret_values(self) -> None:
        redacted = redact_secret_values(
            {
                "DATABASE_URL": "postgresql://user:secret@localhost/fin_ops",
                "plain_password": "super-secret",
                "nested": {"api_token": "token-value", "safe": "visible"},
            }
        )

        encoded = json.dumps(redacted, sort_keys=True)
        self.assertIn("visible", encoded)
        self.assertNotIn("secret@localhost", encoded)
        self.assertNotIn("super-secret", encoded)
        self.assertNotIn("token-value", encoded)

    def test_missing_database_url_error_mentions_env_without_secret(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(CutoverPreflightConfigurationError) as context:
                CutoverPreflightConfig.from_env(database_url_env="FIN_OPS_POSTGRES_DATABASE_URL")

        message = str(context.exception)
        self.assertIn("FIN_OPS_POSTGRES_DATABASE_URL", message)
        self.assertNotIn("postgres://", message)
        self.assertNotIn("password", message.lower())

    def test_cli_json_uses_injected_checker(self) -> None:
        stdout = StringIO()
        checker = verify_cutover_preflight.StaticChecker(
            {
                "status": "pass",
                "guards": {"no_production_writes": "enforced"},
                "postgres": {"database_url": "postgresql://user:***@localhost/fin_ops"},
            }
        )

        exit_code = verify_cutover_preflight.main(["--json"], stdout=stdout, checker=checker)

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "pass")
        self.assertNotIn("password", stdout.getvalue().lower())

    def test_cli_uses_sys_argv_when_argv_is_not_injected(self) -> None:
        stdout = StringIO()
        checker = verify_cutover_preflight.StaticChecker({"status": "pass"})

        with patch("sys.argv", ["verify_cutover_preflight", "--json"]):
            exit_code = verify_cutover_preflight.main(stdout=stdout, checker=checker)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), {"status": "pass"})

    def test_cli_rejects_cutover_and_write_flags(self) -> None:
        for forbidden_flag in ("--cutover", "--enable-dual-write", "--restart-service"):
            with self.subTest(flag=forbidden_flag):
                stdout = StringIO()
                stderr = StringIO()
                exit_code = verify_cutover_preflight.main([forbidden_flag], stdout=stdout, stderr=stderr)

                self.assertEqual(exit_code, 2)
                self.assertIn("refuses write or cutover action", stderr.getvalue())

    def test_cli_redacts_unexpected_checker_errors(self) -> None:
        stderr = StringIO()

        exit_code = verify_cutover_preflight.main(["--json"], stderr=stderr, checker=ExplodingChecker())

        self.assertEqual(exit_code, 1)
        self.assertIn("postgresql://user:***@db.example.com/fin_ops", stderr.getvalue())
        self.assertNotIn("secret-password", stderr.getvalue())
        self.assertNotIn("sslmode=require", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
