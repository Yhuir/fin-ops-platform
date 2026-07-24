from __future__ import annotations

import json
import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
    BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
    PostgresBankReadModelRepository,
)
from tests.postgres_test_utils import (
    apply_test_migrations,
    apply_test_migrations_through,
    require_postgres_test_database_url,
    reset_test_database,
    truncate_test_database,
)


class BankDetailFreshnessPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self.repository = PostgresBankReadModelRepository(self.connection)

    def test_0124_backfills_matching_scope_but_leaves_row_count_mismatch_stale(
        self,
    ) -> None:
        reset_test_database(self.database_url)
        apply_test_migrations_through(self.database_url, "0123")
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        bank_updated_at = self._insert_bank_transaction(
            legacy_mongo_id="bank-july",
            txn_date="2026-07-10",
            updated_at="2026-07-24 01:00:00+00",
        )
        self.connection.execute(
            """
            insert into read_model.bank_detail_scopes(
                scope_key,
                scope_month,
                schema_version,
                status,
                row_count,
                source_versions
            )
            values
                ('2026-07', '2026-07-01', %s, 'fresh', 1, '{}'::jsonb),
                ('2026-08', '2026-08-01', %s, 'fresh', 7, '{}'::jsonb)
            """,
            (
                BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
            ),
        )

        apply_test_migrations_through(self.database_url, "0124")

        rows = self.connection.fetch_all(
            """
            select scope_key, source_versions
            from read_model.bank_detail_scopes
            order by scope_key
            """
        )
        self.assertEqual(
            rows[0]["source_versions"],
            {
                "bank_transactions_context_row_count": 1,
                "bank_transactions_updated_at": bank_updated_at,
            },
        )
        self.assertEqual(rows[1]["source_versions"], {})

    def test_canonical_bank_update_invalidates_previously_fresh_scope(self) -> None:
        bank_updated_at = self._insert_bank_transaction(
            legacy_mongo_id="bank-july",
            txn_date="2026-07-10",
            updated_at="2026-07-24 01:00:00+00",
        )
        self._insert_fresh_scope(
            scope_key="2026-07",
            row_count=1,
            context_row_count=1,
            bank_transactions_updated_at=bank_updated_at,
        )

        self.assertEqual(
            self.repository.bank_detail_scope_summary(
                scope_keys=["2026-07"]
            )["read_model_status"],
            "fresh",
        )

        self.connection.execute(
            """
            update app.bank_transactions
            set summary = 'canonical fact changed',
                updated_at = '2026-07-24 01:00:01+00'::timestamptz
            where legacy_mongo_id = 'bank-july'
            """
        )

        self.assertEqual(
            self.repository.bank_detail_scope_summary(
                scope_keys=["2026-07"]
            )["read_model_status"],
            "stale",
        )

    def test_adjacent_auto_category_context_change_invalidates_exact_month_scope(self) -> None:
        bank_updated_at = self._insert_bank_transaction(
            legacy_mongo_id="bank-july",
            txn_date="2026-07-10",
            updated_at="2026-07-24 01:00:00+00",
        )
        self._insert_fresh_scope(
            scope_key="2026-07",
            row_count=1,
            context_row_count=1,
            bank_transactions_updated_at=bank_updated_at,
        )

        self._insert_bank_transaction(
            legacy_mongo_id="bank-june-context",
            txn_date="2026-06-30",
            updated_at="2026-07-24 01:00:00+00",
        )

        summary = self.repository.bank_detail_scope_summary(scope_keys=["2026-07"])

        self.assertEqual(summary["read_model_status"], "stale")
        self.assertEqual(
            summary["read_model_scope_signatures"]["2026-07"]["row_count"],
            1,
        )

    def _insert_bank_transaction(
        self,
        *,
        legacy_mongo_id: str,
        txn_date: str,
        updated_at: str,
    ) -> str:
        row = self.connection.fetch_one(
            """
            insert into app.bank_transactions(
                legacy_mongo_id,
                account_no,
                txn_direction,
                counterparty_name_raw,
                amount,
                signed_amount,
                txn_date,
                txn_month,
                status,
                updated_at
            )
            values (
                %s,
                '6222',
                'outflow',
                '测试对手方',
                100,
                -100,
                %s::date,
                date_trunc('month', %s::date)::date,
                'active',
                %s::timestamptz
            )
            returning updated_at::text as updated_at
            """,
            (legacy_mongo_id, txn_date, txn_date, updated_at),
        )
        return str((row or {})["updated_at"])

    def _insert_fresh_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        context_row_count: int,
        bank_transactions_updated_at: str,
    ) -> None:
        source_versions = {
            "bank_transaction_category_source_signature": (
                BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE
            ),
            "bank_transactions_context_row_count": context_row_count,
            "bank_transactions_updated_at": bank_transactions_updated_at,
            "workbench_relation_source_versions": {
                "source": "workbench_pair_relations",
                "scope_key": scope_key,
                "relation_count": 0,
                "relation_updated_at": "",
            },
        }
        self.connection.execute(
            """
            insert into read_model.bank_detail_scopes(
                tenant_id,
                scope_type,
                scope_key,
                scope_month,
                schema_version,
                status,
                row_count,
                source_version,
                source_versions,
                raw_payload
            )
            values (
                'default',
                'bank_detail',
                %s,
                (%s || '-01')::date,
                %s,
                'fresh',
                %s,
                1,
                %s::jsonb,
                '{"statistics": {
                    "transaction_count": 1,
                    "expense_transaction_count": 1,
                    "income_transaction_count": 0,
                    "classified_transaction_count": 0,
                    "unclassified_transaction_count": 1,
                    "linked_transaction_count": 0,
                    "unlinked_transaction_count": 1
                }}'::jsonb
            )
            """,
            (
                scope_key,
                scope_key,
                BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                row_count,
                json.dumps(source_versions),
            ),
        )
