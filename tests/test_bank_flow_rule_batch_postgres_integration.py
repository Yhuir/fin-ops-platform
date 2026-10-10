from __future__ import annotations

import json
import unittest

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE
from fin_ops_platform.services.bank_flow_rule_batch_application_service import BankFlowRuleBatchApplicationService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.bank_flow_rule_batch_canonical_query import (
    BankFlowRuleBatchCanonicalQueryRepository,
)
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class BankFlowRuleBatchPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.addCleanup(truncate_test_database, self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        settings = AppSettingsService.normalize_settings_payload({})
        settings["bank_flow_rule_batch_tag_rules"] = {
            "version": 1,
            "requirements_by_tag_code": {
                code: {"requires_oa": False, "requires_invoice": False}
                for code in ("fee", "salary", "tax_payment", "internal_transfer")
            },
        }
        self.connection.execute(
            "insert into app.app_settings(settings_key, version, settings_payload) values ('app_settings', 1, %s::jsonb)",
            (json.dumps(settings),),
        )
        self.service = object.__new__(BankFlowRuleBatchApplicationService)
        self.service._query_repository = BankFlowRuleBatchCanonicalQueryRepository(self.connection)

    def _insert_bank(self, identity: str, account_no: str, trade_time: str, code: str, *, direction: str = "outflow") -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, trade_time, status, raw_payload
            ) values (%s, %s, %s, 'Synthetic counterparty', 100, %s, %s::date,
                      date_trunc('month', %s::timestamp)::date, %s::timestamptz, 'active', %s::jsonb)
            """,
            (identity, account_no, direction, 100 if direction == "inflow" else -100,
             trade_time[:10], trade_time, f"{trade_time}+08:00",
             json.dumps({"normalized_payload": {"imported_bank_name": "建设银行", "imported_bank_last4": account_no[-4:]}})),
        )
        self.connection.execute(
            """insert into app.bank_transaction_category_confirmations(
                legacy_transaction_id, category_code, status, confirmed_by
            ) values (%s, %s, 'active', 'synthetic-test')""",
            (identity, code),
        )

    def test_type_set_filters_before_pagination_and_keeps_month_summary(self) -> None:
        for identity, account, month, code in (
            ("fee-a", "622200008106", "2026-05", "fee"),
            ("salary-a", "622200008106", "2026-05", "salary"),
            ("fee-b", "622200006386", "2026-05", "fee"),
            ("tax-a", "622200008106", "2026-05", "tax_payment"),
            ("fee-june", "622200008106", "2026-06", "fee"),
        ):
            self._insert_bank(identity, account, f"{month}-04T10:20:00", code)
        query = {"month": ["2026-05"], "bucket": ["unsubmitted"],
                 "type": ["fee", "salary", "fee"], "page_size": ["1"]}
        pages = [self.service.list_batches_payload({**query, "page": [str(page)]}) for page in range(1, 5)]
        self.assertEqual([page["pagination"]["total"] for page in pages], [3, 3, 3, 3])
        batches = [batch for page in pages for batch in page["batches"]]
        self.assertCountEqual([batch["row_ids"] for batch in batches], [["fee-a"], ["salary-a"], ["fee-b"]])
        self.assertEqual(pages[0]["summary"]["draft_row_count"], 4)
        self.assertEqual(pages[0]["summary"], pages[-1]["summary"])
        self.assertEqual(pages[-1]["batches"], [])

    def test_historical_type_is_queryable_without_an_active_tag_definition(self) -> None:
        self._insert_bank("historical-bank", "622200008106", "2026-05-04T10:20:00", "fee")
        payload = {"batch_id": "archived-batch", "batch_type": "archived_fee", "row_ids": ["historical-bank"],
                   "row_count": 1, "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE}
        self.connection.execute(
            """insert into app.bank_flow_rule_batches(
                batch_id, status, status_bucket, version, scope_month, total_amount, bank_transaction_ids, raw_payload
            ) values ('archived-batch', 'withdrawn', 'withdrawn', 2, '2026-05-01', 100,
                      array['historical-bank'], %s::jsonb)""",
            (json.dumps({"normalized_payload": payload}),),
        )
        result = self.service.list_batches_payload({"month": ["2026-05"], "bucket": ["withdrawn"],
            "type": ["archived_fee", "salary"], "page": ["1"], "page_size": ["50"]})
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["batches"][0]["batch_id"], "archived-batch")
        self.assertEqual(result["batches"][0]["batch_type"], "archived_fee")
        empty = self.service.list_batches_payload({"month": ["2026-05"], "bucket": ["withdrawn"],
            "type": ["nonexistent_code"], "page": ["1"], "page_size": ["50"]})
        self.assertEqual(empty["pagination"]["total"], 0)
        self.assertEqual(empty["batches"], [])
        self.assertEqual(empty["summary"], result["summary"])

    def test_type_set_preserves_cross_month_internal_transfer_pair(self) -> None:
        self._insert_bank("transfer-out", "622200008106", "2026-05-31T23:30:00", "internal_transfer")
        self._insert_bank("transfer-in", "622200006386", "2026-06-01T00:30:00", "internal_transfer", direction="inflow")
        result = self.service.list_batches_payload({"month": ["2026-05"], "bucket": ["unsubmitted"],
            "type": ["internal_transfer", "fee"], "page": ["1"], "page_size": ["50"]})
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["batches"][0]["scope_month"], "2026-05")
        self.assertCountEqual(result["batches"][0]["row_ids"], ["transfer-out", "transfer-in"])
        self.assertEqual(result["batches"][0]["total_amount"], "100.00")

    def test_compact_relation_source_preserves_occupancy_and_formal_detail(self) -> None:
        for identity in ("occupied-bank", "submitted-bank", "fresh-bank"):
            self._insert_bank(identity, "622200008106", "2026-05-04T10:20:00", "fee")
        large_evidence = {"details": ["Synthetic evidence" * 512 for _ in range(32)]}
        for case_id, relation_mode, row_id in (
            ("other-owner", "manual_confirmed", "occupied-bank"),
            ("submitted-batch", BANK_FLOW_RULE_BATCH_RELATION_MODE, "submitted-bank"),
        ):
            self.connection.execute(
                """
                insert into app.workbench_pair_relations(
                    case_id, relation_mode, status, row_ids, row_types, month_scope,
                    note, amount_check, special_metadata, created_by
                ) values (%s, %s, 'active', array[%s], array['bank'], '2026-05-01',
                          %s, %s::jsonb, %s::jsonb, 'synthetic-test')
                """,
                (case_id, relation_mode, row_id, "Synthetic note" * 512,
                 json.dumps(large_evidence), json.dumps(large_evidence)),
            )
        batch_evidence = {"source": "selected_transaction_ids", "retained_proof": "formal-proof"}
        batch_payload = {
            "batch_id": "submitted-batch", "batch_type": "fee", "row_ids": ["submitted-bank"],
            "row_count": 1, "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
            "relation_case_id": "submitted-batch", "evidence": batch_evidence,
            "row_tag_snapshot": {
                "submitted-bank": {"category_code": "fee", "category_label": "Original fee label"},
            },
        }
        self.connection.execute(
            """
            insert into app.bank_flow_rule_batches(
                batch_id, status, status_bucket, version, scope_month, total_amount,
                bank_transaction_ids, submitted_by, submitted_at, raw_payload
            ) values ('submitted-batch', 'submitted', 'submitted', 2, '2026-05-01', 100,
                      array['submitted-bank'], 'synthetic-test', '2026-05-04T10:25:00+08:00', %s::jsonb)
            """,
            (json.dumps({"normalized_payload": batch_payload}),),
        )
        event_payload = {"amount_check": large_evidence, "special_metadata": large_evidence}
        self.connection.execute(
            """
            insert into app.bank_flow_rule_batch_events(batch_id, event_type, actor_id, payload)
            values ('submitted-batch', 'submit', 'synthetic-test', %s::jsonb)
            """,
            (json.dumps(event_payload),),
        )

        source = self.service._query_repository.read_page({"month": "2026-05"})
        self.assertEqual(len(source["active_relations"]), 2)
        for relation in source["active_relations"]:
            self.assertEqual(set(relation), {"case_id", "relation_mode", "status", "row_ids", "row_types"})
        self.assertCountEqual(
            [relation["row_ids"] for relation in source["active_relations"]],
            [["occupied-bank"], ["submitted-bank"]],
        )
        unsubmitted = self.service.list_batches_payload({"month": ["2026-05"], "bucket": ["unsubmitted"]})
        self.assertEqual([batch["row_ids"] for batch in unsubmitted["batches"]], [["fresh-bank"]])
        self.assertEqual(unsubmitted["summary"]["draft_row_count"], 1)
        self.assertEqual(unsubmitted["summary"]["submitted_row_count"], 1)
        submitted = self.service.list_batches_payload({"month": ["2026-05"], "bucket": ["submitted"]})
        self.assertEqual([batch["batch_id"] for batch in submitted["batches"]], ["submitted-batch"])
        self.assertTrue(submitted["batches"][0]["can_withdraw"])
        self.assertEqual(submitted["batches"][0]["evidence"], batch_evidence)
        self.assertEqual(submitted["summary"], unsubmitted["summary"])

        detail = self.service.detail_payload("submitted-batch", view="formal")
        self.assertTrue(detail["batch"]["can_withdraw"])
        self.assertEqual(detail["batch"]["evidence"], batch_evidence)
        self.assertEqual([row["id"] for row in detail["rows"]], ["submitted-bank"])
        self.assertEqual(detail["rows"][0]["relation_case_ids"], ["submitted-batch"])
        self.assertEqual(detail["rows"][0]["category_label"], "Original fee label")
        self.assertEqual(detail["events"][0]["event_type"], "submit")
        self.assertEqual(detail["events"][0]["payload"], event_payload)
        persisted = self.connection.fetch_one(
            "select note, amount_check, special_metadata from app.workbench_pair_relations where case_id = 'submitted-batch'"
        )
        self.assertEqual(persisted["note"], "Synthetic note" * 512)
        self.assertEqual(persisted["amount_check"], large_evidence)
        self.assertEqual(persisted["special_metadata"], large_evidence)
