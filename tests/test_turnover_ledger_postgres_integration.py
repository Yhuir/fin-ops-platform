from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.bank_transaction_category import (
    PostgresBankTransactionCategoryRepository,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.runtime_paths import default_data_dir
from fin_ops_platform.services.turnover_ledger_query_service import (
    TurnoverLedgerQueryService,
)
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
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )

    def tearDown(self) -> None:
        truncate_test_database(self.database_url)

    def test_direct_query_ignores_retired_projection_rows(self) -> None:
        self.connection.execute(
            """
            insert into read_model.turnover_ledger_rows(
                relation_id, scope_month, family, status, source_versions, payload
            ) values (
                'retired-projection-row', '2026-04-01', 'personal', 'suggested', '{}'::jsonb,
                '{"relation_id":"retired-projection-row","cash_closure_linked":true}'::jsonb
            )
            """
        )

        payload = TurnoverLedgerQueryService(connection=self.connection).list_ledger(
            view="grouped"
        )

        self.assertEqual(payload["groups"], [])
        self.assertEqual(payload["pagination"]["total"], 0)
        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("source_versions", payload)

    def test_direct_query_reads_bank_categories_and_pair_relations_from_one_canonical_snapshot(
        self,
    ) -> None:
        row_ids = ["turnover-income-140000", "turnover-expense-140000"]
        category_records = (
            {
                "category_code": "external_rule_personal_borrow",
                "category_label": "个人往来：待还款",
                "category_primary_label": "外部往来款收款",
                "category_sub_label": "借入款",
                "category_third_label": "个人往来",
                "category_label_path": ["外部往来款收款", "借入款", "个人往来"],
                "turnover_role": "external_turnover",
                "turnover_action_type": "pending_repayment",
                "turnover_family": "personal",
                "manual_assignment": True,
                "category_version": 1,
            },
            {
                "category_code": "external_rule_personal_repaid",
                "category_label": "个人往来：已还款",
                "category_primary_label": "外部往来款付款",
                "category_sub_label": "归还借款",
                "category_third_label": "个人往来",
                "category_label_path": ["外部往来款付款", "归还借款", "个人往来"],
                "turnover_role": "external_turnover",
                "turnover_action_type": "repaid",
                "turnover_family": "personal",
                "manual_assignment": True,
                "category_version": 1,
            },
        )
        with self.connection.transaction() as transaction:
            transaction.execute(
                """
                insert into app.bank_transactions(
                    legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                    amount, signed_amount, txn_date, txn_month, trade_time, status
                ) values
                    (%s, '6222000011118106', 'inflow', '直接读取集成测试',
                     140000, 140000, '2026-04-16', '2026-04-01', '2026-04-16 07:56:25', 'pending'),
                    (%s, '6222000011118106', 'outflow', '直接读取集成测试',
                     140000, -140000, '2026-06-23', '2026-06-01', '2026-06-23 09:31:54', 'pending')
                """,
                tuple(row_ids),
            )
            category_repository = PostgresBankTransactionCategoryRepository(
                self.connection
            )
            for row_id, category_record in zip(
                row_ids,
                category_records,
                strict=True,
            ):
                category_repository.apply_mutation(
                    transaction=transaction,
                    transaction_id=row_id,
                    mutation_type="manual_assign",
                    record=category_record,
                    actor_id="turnover-direct-read-integration",
                    action="bank_detail_category_manually_assigned",
                    metadata={"test_owned": True},
                )

        state_store = PostgresStateStore(
            data_dir=default_data_dir(),
            connection=self.connection,
        )
        state_store.save_app_settings(
            {
                "bank_transaction_tags": {
                    "version": 1,
                    "definitions": [
                        {
                            "code": record["category_code"],
                            "label": record["category_label"],
                            "path": record["category_label_path"],
                            "source": "custom",
                            "status": "active",
                            "output_primary_label": record["category_primary_label"],
                            "output_sub_label": record["category_sub_label"],
                            "turnover_role": record["turnover_role"],
                            "turnover_action_type": record["turnover_action_type"],
                            "direction": "any",
                            "account_scope": {"type": "any", "values": []},
                            "rules": {
                                "match_fields": ["all_text"],
                                "contains_any": [
                                    f"integration-only-{record['category_code']}"
                                ],
                                "contains_all": [],
                                "exact_any": [],
                                "regex_any": [],
                                "none_of": [],
                            },
                        }
                        for record in category_records
                    ],
                },
                "turnover_ledger_tag_selection": {
                    "version": 1,
                    "selected_tag_codes": [
                        record["category_code"] for record in category_records
                    ],
                }
            }
        )
        state_store.save_workbench_pair_relations(
            {
                "pair_relations": {
                    "turnover:test-direct-read": {
                        "case_id": "turnover:test-direct-read",
                        "relation_mode": "turnover_manual_closure",
                        "status": "active",
                        "month_scope": "2026-06",
                        "row_ids": row_ids,
                        "row_types": ["bank", "bank"],
                        "amount_check": {
                            "balanced": True,
                            "difference": "0.00",
                        },
                    }
                },
                "audit_log": [],
            }
        )

        payload = TurnoverLedgerQueryService(connection=self.connection).list_ledger(
            view="grouped",
            family="personal",
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        [group] = payload["groups"]
        self.assertTrue(group["cash_closure_linked"])
        self.assertEqual(
            group["cash_closure_case_id"],
            "turnover:test-direct-read",
        )
        self.assertEqual(
            {
                flow["source_bank_row_id"]: flow["cash_closure_linked"]
                for flow in group["flow_rows"]
            },
            {
                "turnover-income-140000": True,
                "turnover-expense-140000": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
