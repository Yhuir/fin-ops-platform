from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_details_canonical_query import (
    BankDetailsCanonicalQueryService,
    PostgresBankDetailsCanonicalQueryRepository,
)
from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.runtime_paths import default_data_dir
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class BankDetailsPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )

    def tearDown(self) -> None:
        truncate_test_database(self.database_url)

    def test_page_executes_narrow_materialization_with_canonical_rule(self) -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, trade_time, summary,
                raw_payload, status
            ) values (
                'bank-narrow-1', '6222000011118106', 'outflow', '材料供应商',
                118, -118, '2026-07-31', '2026-07-01',
                '2026-07-31 10:00:00', '材料款',
                '{"normalized_payload":{"imported_bank_name":"建设银行","imported_bank_last4":"8106"}}'::jsonb,
                'active'
            )
            """
        )
        PostgresStateStore(
            data_dir=default_data_dir(),
            connection=self.connection,
        ).save_app_settings(
            {
                "bank_transaction_tags": {
                    "version": 1,
                    "definitions": [
                        {
                            "code": "materials",
                            "label": "材料费",
                            "status": "active",
                            "source": "custom",
                            "direction": "expense",
                            "priority": 2,
                            "sort_order": 1,
                            "output_primary_label": "货款",
                            "output_sub_label": "材料费",
                            "account_scope": {"type": "any", "values": []},
                            "rules": {
                                "match_fields": ["summary_text"],
                                "contains_any": ["材料款"],
                                "contains_all": [],
                                "exact_any": [],
                                "regex_any": [],
                                "none_of": [],
                            },
                        }
                    ],
                }
            }
        )

        payload = BankDetailsCanonicalQueryService(
            PostgresBankDetailsCanonicalQueryRepository(self.connection)
        ).transactions_payload(
            account_key=None,
            date_from="2026-07-01",
            date_to="2026-07-31",
            keyword=None,
            category_code=None,
            category_primary_label=None,
            category_sub_label=None,
            category_third_label=None,
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        [row] = payload["rows"]
        self.assertEqual(row["id"], "bank-narrow-1")
        self.assertEqual(row["effective_category_code"], "materials")
        self.assertEqual(row["bank_name"], "建设银行")
        self.assertEqual(row["account_last4"], "8106")

        filtered_payload = BankDetailsCanonicalQueryService(
            PostgresBankDetailsCanonicalQueryRepository(self.connection)
        ).transactions_payload(
            account_key=None,
            date_from="2026-07-01",
            date_to="2026-07-31",
            keyword="材料费",
            category_code="materials",
            category_primary_label="货款",
            category_sub_label="材料费",
            category_third_label=None,
            page=1,
            page_size=50,
        )

        self.assertEqual(filtered_payload["pagination"]["total"], 1)
        self.assertEqual(filtered_payload["category_counts"]["materials"], 1)
        [filtered_row] = filtered_payload["rows"]
        self.assertEqual(filtered_row["id"], "bank-narrow-1")
        self.assertEqual(filtered_row["summary"], "材料款")


if __name__ == "__main__":
    unittest.main()
