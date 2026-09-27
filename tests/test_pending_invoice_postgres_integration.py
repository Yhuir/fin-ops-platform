from __future__ import annotations

import json
import unittest

from fin_ops_platform.services.pending_invoice_canonical_query import (
    PendingInvoiceCanonicalQueryService,
    PostgresPendingInvoiceCanonicalRepository,
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


class PendingInvoicePostgresIntegrationTests(unittest.TestCase):
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
        self.connection.close()
        truncate_test_database(self.database_url)

    def test_parent_counts_invoice_dedup_self_excluding_facets_and_relation_withdrawal(self) -> None:
        for identity, direction in (("expense-a", "outflow"), ("expense-b", "outflow"),
                                    ("expense-c", "outflow"), ("income-a", "inflow")):
            self.connection.execute("""
                insert into app.bank_transactions(legacy_mongo_id, account_no, txn_direction,
                    counterparty_name_raw, amount, signed_amount, txn_date, txn_month, status)
                values (%s, '8106', %s, '统一查询客户', 100, %s, '2026-09-28', '2026-09-01', 'active')
            """, (identity, direction, -100 if direction == "outflow" else 100))
        for index in range(3):
            self.connection.execute("""
                insert into app.invoices(legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                    invoice_month, seller_name, amount, signed_amount, total_with_tax, status)
                values (%s, 'input', %s, '2026-09-28', '2026-09-01', '统一查询客户', 50, 50, 50, 'active')
            """, (f"inv-{index}", f"INV-{index}"))
        query = PendingInvoiceCanonicalQueryService(repository=PostgresPendingInvoiceCanonicalRepository(self.connection))
        request = {"direction": ["all"], "filter": ["all"], "include_statistics": ["false"], "page_size": ["1"]}
        before = query.rows(request)
        self.assertEqual(before["acquisition_summary"]["bank_count"], 4)
        self.assertEqual(before["acquisition_summary"]["status_counts"]["paid_pending_invoice"], 3)
        self.connection.execute("""
            insert into app.workbench_pair_relations(case_id, relation_mode, status, month_scope, row_ids, row_types)
            values ('counts-case', 'manual_confirmed', 'active', '2026-09-01',
                array['expense-a','expense-b','inv-0','inv-1','inv-2'], array['bank','bank','invoice','invoice','invoice'])
        """)
        linked = query.rows(request)
        self.assertEqual(linked["acquisition_summary"]["bank_count"], 4)
        self.assertEqual(linked["acquisition_summary"]["invoice_count"], 3)
        self.assertEqual(linked["acquisition_summary"]["status_counts"]["paid_invoiced"], 2)
        self.assertEqual(sum(linked["acquisition_summary"]["status_counts"].values()), 4)
        self.assertEqual(linked["pagination"]["total"], 3)  # two banks may fold to one display row
        for direction, expected in (("all", 4), ("expense", 3), ("income", 1)):
            result = query.rows({**request, "direction": [direction]})
            self.assertEqual(result["summary"]["source_summary"]["bank_transaction_rows"], 4)
            self.assertEqual(sum(result["acquisition_summary"]["status_counts"].values()), expected)
        filtered_request = {**request, "direction": ["expense"], "filters": [json.dumps([
            {"field": "status_code", "operator": "in", "values": ["paid_invoiced"]}])]}
        filtered = query.rows(filtered_request)
        self.assertEqual(filtered["acquisition_summary"]["bank_count"], 2)
        self.assertEqual(filtered["acquisition_summary"]["invoice_count"], 3)
        self.assertEqual(sum(filtered["acquisition_summary"]["status_counts"].values()), 3)
        self.assertEqual(filtered["rows"][0]["bank_transactions"]["original_transaction_count"], 2)
        self.assertEqual(filtered["rows"][0]["bank_transactions"]["original_amount"], "200.00")
        empty = query.rows({**request, "keyword": ["不存在的客户"]})
        self.assertEqual(empty["acquisition_summary"]["bank_count"], 0)
        self.assertEqual(empty["acquisition_summary"]["invoice_count"], 0)
        self.assertTrue(all(value == 0 for value in empty["acquisition_summary"]["status_counts"].values()))
        self.connection.execute("update app.workbench_pair_relations set status='withdrawn' where case_id='counts-case'")
        restored = query.rows(request)
        self.assertEqual(restored["acquisition_summary"], before["acquisition_summary"])
        self.assertEqual(query.rows(filtered_request)["pagination"]["total"], 0)

    def test_excluded_relation_members_remain_visible_in_their_own_status(self) -> None:
        settings = {
            "access_control_version": 1, "page_access_accounts": [],
            "bank_transaction_tags": {"definitions": [
                {"code": "principal", "label": "本金", "status": "active", "direction": "expense",
                 "output_primary_label": "外部往来款付款", "output_sub_label": "归还借款", "rules": {}},
            ]},
            "pending_invoice_tag_groups": {"no_invoice_required": ["principal"]},
        }
        self.connection.execute("insert into app.app_settings(settings_key,settings_payload) values ('app_settings',%s::jsonb)",
                                (json.dumps(settings),))
        identities = ["principal-a", "principal-b", "fee-a", "fee-b"]
        for identity in identities:
            self.connection.execute("""
                insert into app.bank_transactions(legacy_mongo_id, account_no, txn_direction,
                    counterparty_name_raw, amount, signed_amount, txn_date, txn_month, status)
                values (%s, '8106', 'outflow', '关系成员客户', 100, -100, '2026-09-28', '2026-09-01', 'active')
            """, (identity,))
        self.connection.execute("""insert into app.bank_transaction_categories
            (bank_transaction_id,legacy_transaction_id,category,source,status,raw_payload)
            select id,legacy_mongo_id,'principal','manual','active','{"manual_assignment":true}'::jsonb
            from app.bank_transactions where legacy_mongo_id like 'principal-%%'""")
        self.connection.execute("""
            insert into app.workbench_pair_relations(case_id, relation_mode, status, month_scope, row_ids, row_types)
            values ('mixed-case', 'manual_confirmed', 'active', '2026-09-01', %s::text[], array['bank','bank','bank','bank'])
        """, (identities,))
        query = PendingInvoiceCanonicalQueryService(repository=PostgresPendingInvoiceCanonicalRepository(self.connection))
        for status, expected in (("no_invoice_required", {"principal-a", "principal-b"}),
                                 ("paid_pending_invoice", {"fee-a", "fee-b"})):
            request = {"direction": ["all"], "include_statistics": ["false"], "page_size": ["1"],
                       "filters": [json.dumps([{"field": "status_code", "operator": "in", "values": [status]}])]}
            first = query.rows(request)
            self.assertEqual(first["acquisition_summary"]["bank_count"], 2)
            observed = set()
            for page in range(1, first["pagination"]["total"] + 1):
                for row in query.rows({**request, "page": [str(page)]})["rows"]:
                    group = row["bank_transactions"]
                    banks = group["summaries"] if group["has_multiple"] else [group["primary"]]
                    self.assertEqual(row["invoice_acquisition_status"]["code"], status)
                    observed.update(bank["parent_row_id"] for bank in banks)
            self.assertEqual(observed, expected)

    def test_source_drawers_read_actual_fields_without_operational_defaults(self) -> None:
        self.connection.execute("""
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, trade_time, balance, status, raw_payload
            ) values ('source-bank', '001234', 'outflow', '源文件户名',
                      100, -100, '2026-09-27', '2026-09-01', '2026-09-27 00:00:00', 0, 'pending',
                      '{"normalized_payload":{"status":"pending","currency":"CNY","booked_date":"2026-09-28"}}')
        """)
        self.connection.execute("""
            insert into app.invoices(legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, seller_name, amount, signed_amount, tax_amount, total_with_tax, status, raw_payload)
            values ('source-invoice', 'input', 'SOURCE-001', '2026-09-27', '2026-09-01',
                    '文件销方', 100, 100, 0, null, 'pending',
                    '{"normalized_payload":{"invoice_status_from_source":"正常"}}')
        """)
        service = PendingInvoiceCanonicalQueryService(repository=PostgresPendingInvoiceCanonicalRepository(self.connection))
        bank = service.bank_transaction_detail('source-bank')
        fields = {field['label']: field['value'] for field in bank['sections'][0]['fields']}
        self.assertEqual(fields['交易日期'], '2026-09-27')
        self.assertEqual(fields['入账日期'], '2026-09-28')
        self.assertEqual(fields['余额'], '0.00')
        self.assertEqual(fields['账号'], '001234')
        self.assertNotIn('状态', fields)
        self.assertNotIn('交易时间', fields)
        self.assertNotIn('币种', fields)
        invoice = service.invoice_detail('source-invoice')
        fields = {field['label']: field['value'] for field in invoice['sections'][0]['fields']}
        self.assertEqual(fields['税额'], '0.00')
        self.assertEqual(fields['发票状态'], '正常')
        self.assertNotIn('价税合计', fields)
        # A source read must not change the operational lifecycle used by other pages.
        self.assertEqual(self.connection.fetch_one(
            "select status from app.bank_transactions where legacy_mongo_id='source-bank'"
        )['status'], 'pending')

    def test_page_reuses_compiled_bank_category_rules(self) -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, trade_time, summary, status
            ) values (
                'pending-compiled-1', '6222000011118106', 'outflow', '材料供应商',
                118, -118, '2026-07-31', '2026-07-01',
                '2026-07-31 10:00:00', '材料款', 'pending'
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
                                "match_fields": [
                                    "detail_text",
                                    "note_text",
                                    "purpose_text",
                                    "summary_text",
                                ],
                                "contains_any": ["材料款"],
                                "contains_all": [],
                                "exact_any": [],
                                "regex_any": [],
                                "none_of": ["退款"],
                            },
                        }
                    ],
                }
            }
        )

        payload = PendingInvoiceCanonicalQueryService(
            repository=PostgresPendingInvoiceCanonicalRepository(self.connection)
        ).rows(
            {
                "direction": ["expense"],
                "filter": ["all"],
                "include_statistics": ["false"],
            }
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(
            payload["summary"],
            {
                "total_rows": 1,
                "missing_invoice_rows": 1,
                "create_invoice_available_rows": 1,
                "source_summary": {
                    "bank_transaction_rows": 1,
                    "expense_rows": 1,
                    "income_rows": 0,
                    "current_direction_rows": 1,
                    "excluded_direction_rows": 0,
                },
            },
        )
        self.assertIsNone(payload["statistics"])
        [row] = payload["rows"]
        self.assertEqual(row["id"], "pending-compiled-1")
        self.assertEqual(
            row["bank_transactions"]["primary"]["effective_tag_code"],
            "materials",
        )

    def test_page_resolves_relation_invoice_by_legacy_or_canonical_identity(self) -> None:
        for suffix in ("legacy", "canonical"):
            self.connection.execute(
                """
                insert into app.bank_transactions(
                    legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                    amount, signed_amount, txn_date, txn_month, trade_time, status
                ) values (%s, '6222000011118106', 'outflow', %s, 118, -118,
                          '2026-07-31', '2026-07-01', '2026-07-31 10:00:00', 'active')
                """,
                (f"pending-bank-{suffix}", f"供应商-{suffix}"),
            )
        invoice_ids: dict[str, str] = {}
        for suffix in ("legacy", "canonical"):
            row = self.connection.fetch_one(
                """
                insert into app.invoices(
                    legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                    seller_name, buyer_name, amount, signed_amount, total_with_tax, status
                ) values (%s, 'input', %s, '2026-07-31', '2026-07-01',
                          %s, '云南溯源科技有限公司', 100, 100, 118, 'active')
                returning id::text as id
                """,
                (
                    f"pending-invoice-{suffix}",
                    f"INV-{suffix}",
                    f"供应商-{suffix}",
                ),
            )
            invoice_ids[suffix] = str((row or {}).get("id") or "")
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types
            ) values
                ('CASE-PENDING-LEGACY', 'manual_confirmed', 'active', '2026-07-01',
                 array['pending-bank-legacy', 'pending-invoice-legacy'], array['bank', 'invoice']),
                ('CASE-PENDING-CANONICAL', 'manual_confirmed', 'active', '2026-07-01',
                 array['pending-bank-canonical', %s], array['bank', 'invoice'])
            """,
            (invoice_ids["canonical"],),
        )

        payload = PendingInvoiceCanonicalQueryService(
            repository=PostgresPendingInvoiceCanonicalRepository(self.connection)
        ).rows(
            {
                "direction": ["expense"],
                "filter": ["all"],
                "include_statistics": ["false"],
            }
        )

        rows = {row["id"]: row for row in payload["rows"]}
        self.assertEqual(
            rows["pending-bank-legacy"]["input_invoices"]["primary"]["id"],
            "pending-invoice-legacy",
        )
        self.assertEqual(
            rows["pending-bank-canonical"]["input_invoices"]["primary"]["id"],
            "pending-invoice-canonical",
        )


if __name__ == "__main__":
    unittest.main()
