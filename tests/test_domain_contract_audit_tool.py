from __future__ import annotations

import io
import json
import os
from urllib.parse import parse_qs, urlsplit
from unittest import mock
import unittest

from fin_ops_platform.tools import domain_contract_audit


class FakeConnection:
    def __init__(self, counts: dict[str, int] | None = None) -> None:
        self.counts = counts or {}
        self.queries: list[str] = []

    def fetch_one(self, sql: str) -> dict[str, int]:
        self.queries.append(sql)
        return {
            column: self.counts.get(contract, 0)
            for contract, column in domain_contract_audit._CONTRACT_COLUMNS.items()
        }


class DomainContractAuditToolTests(unittest.TestCase):
    def test_zero_violations_passes_with_every_contract_count(self) -> None:
        connection = FakeConnection()
        stdout = io.StringIO()

        exit_code = domain_contract_audit.main(connection=connection, stdout=stdout)

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertEqual(
            set(report["contracts"]),
            set(domain_contract_audit._CONTRACT_COLUMNS),
        )
        self.assertTrue(all(count == 0 for count in report["contracts"].values()))
        self.assertEqual(len(connection.queries), 1)
        self.assertIn("from app.invoices", connection.queries[0])
        self.assertIn("from app.bank_transactions", connection.queries[0])
        self.assertIn("from app.workbench_pair_relations", connection.queries[0])
        self.assertIn("from job.background_jobs", connection.queries[0])
        self.assertIn("from job.outbox_events", connection.queries[0])
        lowered_sql = connection.queries[0].lower()
        for mutation in ("insert ", "update ", "delete ", "alter ", "drop ", "truncate "):
            self.assertNotIn(mutation, lowered_sql)

    def test_any_violation_is_blocking_without_business_samples(self) -> None:
        connection = FakeConnection(
            {
                "invoices.invoice_date_month": 2,
                "workbench_pair_relations.row_cardinality": 1,
                "outbox_events.attempt_count_mirror": 1,
            }
        )
        stdout = io.StringIO()

        exit_code = domain_contract_audit.main(connection=connection, stdout=stdout)

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "issues_found")
        self.assertEqual(report["summary"]["blocking_issue_count"], 4)
        self.assertNotIn("samples", report)
        self.assertNotIn("rows", report)

    def test_missing_postgres_configuration_is_json_and_exit_two(self) -> None:
        stdout = io.StringIO()
        missing_env = {
            "FIN_OPS_POSTGRES_DATABASE_URL": "",
            "DATABASE_URL": "",
        }

        with mock.patch.dict(os.environ, missing_env, clear=False):
            exit_code = domain_contract_audit.main(stdout=stdout)

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "configuration_missing")
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertTrue(report["read_only"])

    def test_runtime_connection_uses_primary_dsn_read_only_and_sixty_second_timeout(self) -> None:
        settings = domain_contract_audit.PostgresSettings(
            database_url="postgresql://readonly:secret@db.example/fin_ops?sslmode=require"
        )
        connection = mock.Mock()

        with (
            mock.patch.object(
                domain_contract_audit.PostgresSettings,
                "from_env",
                return_value=settings,
            ),
            mock.patch.object(
                domain_contract_audit,
                "PostgresConnection",
                return_value=connection,
            ) as connection_type,
        ):
            result = domain_contract_audit._connection_from_env()

        self.assertIs(result, connection)
        actual_settings = connection_type.call_args.args[0]
        query = parse_qs(urlsplit(actual_settings.database_url).query)
        self.assertEqual(query["sslmode"], ["require"])
        self.assertIn(
            "-c default_transaction_read_only=on",
            query["options"][0],
        )
        connection.set_statement_timeout_ms.assert_called_once_with(60_000)

    def test_read_only_connection_option_is_idempotent(self) -> None:
        settings = domain_contract_audit.PostgresSettings(
            database_url=(
                "postgresql://readonly:secret@db.example/fin_ops"
                "?options=-c+default_transaction_read_only%3Don"
            )
        )

        result = domain_contract_audit._force_read_only(settings)

        options = parse_qs(urlsplit(result.database_url).query)["options"][0]
        self.assertEqual(options.count("-c default_transaction_read_only=on"), 1)


if __name__ == "__main__":
    unittest.main()
