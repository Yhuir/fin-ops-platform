from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class TurnoverLedgerPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.repository = PostgresReadModelRepository(self.connection)
        self.source_versions = {"turnover_ledger_schema_version": "2026-07-turnover-ledger-v7"}

    def test_list_uses_sql_summary_direction_and_bounded_page_with_normalized_payload_only(self) -> None:
        rows = [
            {
                "relation_id": "turnover-personal-in",
                "first_transaction_at": "2026-03-20",
                "family": "personal",
                "status": "suggested",
                "business_type": "borrow_in",
                "pending_repayment_amount": "1,000.00",
                "repaid_amount": "200.00",
                "pending_collection_amount": "0.00",
                "collected_amount": "0.00",
                "closed_amount": "0.00",
                "source_versions": self.source_versions,
            },
            {
                "relation_id": "turnover-company-out",
                "first_transaction_at": "2026-02-10",
                "family": "company",
                "status": "confirmed",
                "business_type": "borrow_out",
                "principal_amount": "600.00",
                "settled_amount": "100.00",
                "balance_amount": "500.00",
                "source_versions": self.source_versions,
            },
            {
                "relation_id": "turnover-bank-out",
                "first_transaction_at": "2026-01-05",
                "family": "bank",
                "status": "conflict",
                "business_type": "business_receivable",
                "pending_repayment_amount": "0.00",
                "repaid_amount": "0.00",
                "pending_collection_amount": "300.00",
                "collected_amount": "50.00",
                "closed_amount": "0.00",
                "source_versions": self.source_versions,
            },
        ]
        self.repository.save_turnover_ledger_rows({"rows": rows}, scope_key="all")

        payload = self.repository.list_turnover_ledger_view(page=1, page_size=2, scope_key="all")

        self.assertIsInstance(payload, dict)
        assert isinstance(payload, dict)
        self.assertEqual(payload["summary"]["pending_repayment_amount"], "1000.00")
        self.assertEqual(payload["summary"]["repaid_amount"], "200.00")
        self.assertEqual(payload["summary"]["pending_collection_amount"], "800.00")
        self.assertEqual(payload["summary"]["collected_amount"], "150.00")
        self.assertEqual(payload["summary"]["suggested_count"], 1)
        self.assertEqual(payload["summary"]["conflict_count"], 1)
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 2, "total": 3})
        self.assertEqual(
            [row["relation_id"] for row in payload["rows"]],
            ["turnover-personal-in", "turnover-company-out"],
        )
        self.assertEqual(payload["source_versions"], self.source_versions)
        self.assertEqual(payload["refresh_status"], "fresh")
        personal = next(item for item in payload["family_summaries"] if item["family"] == "personal")
        company = next(item for item in payload["family_summaries"] if item["family"] == "company")
        self.assertEqual(personal["pending_amount"], "1000.00")
        self.assertEqual(company["pending_amount"], "500.00")

        borrow_in = self.repository.list_turnover_ledger_view(direction="borrow_in", scope_key="all")
        borrow_out = self.repository.list_turnover_ledger_view(direction="borrow_out", scope_key="all")
        empty = self.repository.list_turnover_ledger_view(family="business", scope_key="all")
        self.assertEqual(borrow_in["pagination"]["total"], 1)
        self.assertEqual([row["relation_id"] for row in borrow_in["rows"]], ["turnover-personal-in"])
        self.assertEqual(borrow_out["pagination"]["total"], 2)
        self.assertEqual(empty["pagination"]["total"], 0)
        self.assertEqual(empty["rows"], [])
        self.assertEqual(empty["source_versions"], self.source_versions)

        stored = self.connection.fetch_all(
            "select payload, raw_payload from read_model.turnover_ledger_rows order by relation_id"
        )
        self.assertTrue(all(isinstance(row["payload"], dict) and row["payload"] for row in stored))
        self.assertTrue(all(row["raw_payload"] == {} for row in stored))

    def test_all_scope_aggregates_child_dirty_status_and_failed_takes_precedence(self) -> None:
        self.repository.save_turnover_ledger_rows(
            {
                "rows": [
                    {
                        "relation_id": "turnover-dirty",
                        "first_transaction_at": "2026-03-20",
                        "family": "personal",
                        "status": "suggested",
                        "business_type": "borrow_in",
                        "balance_amount": "10.00",
                        "source_versions": self.source_versions,
                    }
                ]
            },
            scope_key="all",
        )
        self.connection.execute(
            """
            insert into job.read_model_dirty_scopes(
                tenant_id, scope_type, scope_key, source_version, status
            ) values
                ('default', 'turnover_ledger', '2026-03', 1, 'processing'),
                ('default', 'turnover_ledger', '2026-04', 1, 'pending')
            """
        )

        refreshing = self.repository.list_turnover_ledger_view(scope_key="all")
        self.assertEqual(refreshing["refresh_status"], "refreshing")
        self.assertEqual(self.repository.list_turnover_ledger_view(scope_key="2026-03")["refresh_status"], "refreshing")

        self.connection.execute(
            """
            insert into job.read_model_dirty_scopes(
                tenant_id, scope_type, scope_key, source_version, status
            ) values ('default', 'turnover_ledger', '2026-05', 1, 'failed')
            """
        )
        stale = self.repository.list_turnover_ledger_view(scope_key="all")
        self.assertEqual(stale["refresh_status"], "stale")

    def test_mixed_source_versions_are_proved_without_loading_every_payload(self) -> None:
        self.repository.save_turnover_ledger_rows(
            {
                "rows": [
                    {
                        "relation_id": "turnover-version-old",
                        "first_transaction_at": "2026-01-01",
                        "family": "personal",
                        "status": "suggested",
                        "business_type": "borrow_in",
                        "balance_amount": "10.00",
                        "source_versions": {"turnover_ledger_schema_version": "old"},
                    },
                    {
                        "relation_id": "turnover-version-new",
                        "first_transaction_at": "2026-02-01",
                        "family": "company",
                        "status": "suggested",
                        "business_type": "borrow_out",
                        "balance_amount": "20.00",
                        "source_versions": self.source_versions,
                    },
                ]
            },
            scope_key="all",
        )

        payload = self.repository.list_turnover_ledger_view(scope_key="all")

        self.assertEqual(payload["source_versions"], {})
        self.assertTrue(payload["source_versions_mixed"])

    def test_relation_source_bundle_returns_rows_and_version_from_one_canonical_scope(self) -> None:
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types, raw_payload
            ) values
                (
                    'case-target', 'turnover_manual_closure', 'active', '2026-03-01',
                    array['txn-target', 'txn-peer'], array['bank', 'bank'],
                    '{"normalized_payload":{"relation_source":"manual"}}'::jsonb
                ),
                (
                    'case-same-month', 'manual_confirmed', 'active', '2026-03-01',
                    array['txn-other'], array['bank'], '{}'::jsonb
                ),
                (
                    'case-withdrawn', 'turnover_manual_closure', 'withdrawn', '2026-03-01',
                    array['txn-target'], array['bank'], '{}'::jsonb
                )
            """
        )

        bundle = self.repository.workbench_relation_source_bundle_from_source(
            scope_key="2026-03",
            row_ids=["txn-target"],
        )

        self.assertEqual([row["case_id"] for row in bundle["rows"]], ["case-target"])
        self.assertEqual(bundle["rows"][0]["row_ids"], ["txn-target", "txn-peer"])
        self.assertEqual(
            bundle["source_versions"],
            {
                "source": "workbench_pair_relations",
                "scope_key": "2026-03",
                "relation_count": 2,
                "relation_updated_at": bundle["source_versions"]["relation_updated_at"],
            },
        )
        self.assertTrue(bundle["source_versions"]["relation_updated_at"])

    def test_relation_delta_updates_only_overlapping_payload_and_keeps_scope_versions_uniform(self) -> None:
        original_versions = {"turnover_ledger_schema_version": "v7", "relation_revision": "before"}
        next_versions = {"turnover_ledger_schema_version": "v7", "relation_revision": "after"}
        self.repository.save_turnover_ledger_rows(
            {
                "rows": [
                    {
                        "relation_id": "turnover-target",
                        "first_transaction_at": "2026-03-01",
                        "bank_row_ids": ["bank-target"],
                        "cash_closure_linked": False,
                        "source_versions": original_versions,
                    },
                    {
                        "relation_id": "turnover-untouched",
                        "first_transaction_at": "2026-03-02",
                        "bank_row_ids": ["bank-untouched"],
                        "cash_closure_linked": False,
                        "source_versions": original_versions,
                    },
                ]
            },
            scope_key="2026-03",
        )

        delta = self.repository.load_turnover_ledger_relation_delta(
            scope_key="2026-03",
            row_ids=["bank-target"],
        )
        self.assertTrue(delta["scope_exists"])
        self.assertFalse(delta["source_versions_mixed"])
        self.assertEqual([row["relation_id"] for row in delta["rows"]], ["turnover-target"])

        target = dict(delta["rows"][0])
        target["cash_closure_linked"] = True
        target["source_versions"] = next_versions
        self.repository.save_turnover_ledger_relation_delta(
            {"rows": [target], "source_versions": next_versions},
            scope_key="2026-03",
        )

        stored = self.connection.fetch_all(
            """
            select relation_id, source_versions, payload
            from read_model.turnover_ledger_rows
            where scope_month = '2026-03-01'::date
            order by relation_id
            """
        )
        self.assertEqual(len(stored), 2)
        self.assertTrue(next(row for row in stored if row["relation_id"] == "turnover-target")["payload"]["cash_closure_linked"])
        self.assertFalse(
            next(row for row in stored if row["relation_id"] == "turnover-untouched")["payload"]["cash_closure_linked"]
        )
        self.assertTrue(all(row["source_versions"] == next_versions for row in stored))
        self.assertTrue(all(row["payload"]["source_versions"] == next_versions for row in stored))


if __name__ == "__main__":
    unittest.main()
