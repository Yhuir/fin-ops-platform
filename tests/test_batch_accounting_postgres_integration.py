from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.batch_accounting_service import BatchAccountingError, BatchAccountingService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.batch_accounting import PostgresBatchAccountingQueryRepository
from fin_ops_platform.services.postgres_repositories.settings_page_audit import audit_settings_page
from fin_ops_platform.tools import settings_normalization_ops
from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class BatchAccountingPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.repository = PostgresBatchAccountingQueryRepository(self.connection)
        self.service = BatchAccountingService(query_repository=self.repository)
        self._seed_canonical_facts()

    def test_retired_tag_normalization_preserves_settings_and_history_and_is_repeatable(self):
        payload = AppSettingsService.normalize_settings_payload(AppSettingsService.normalize_settings_payload({}))
        payload["batch_accounting_tag_selection"] = {"version": 3, "selected_tag_codes": ["fee"]}
        self.connection.execute(
            "insert into app.app_settings(settings_key,version,settings_payload,raw_payload) "
            "values ('app_settings',7,%s::jsonb,%s::jsonb)",
            (json.dumps(payload), json.dumps({"normalized_payload": payload})),
        )
        before_history = self.service.detail("CASE-BATCH-SUBMITTED")
        before_report = audit_settings_page(self.connection)
        self.assertIn("settings_payload_not_normalized", before_report["summary"]["issue_sample_counts_by_code"])

        def normalize(mode):
            output = StringIO()
            with patch.object(settings_normalization_ops.PostgresSettings, "from_env",
                              return_value=PostgresSettings(database_url=self.database_url, pool_enabled=False)):
                self.assertEqual(settings_normalization_ops.main([mode], stdout=output), 0)
            return json.loads(output.getvalue())

        plan = normalize("--dry-run")
        self.assertEqual(plan["changed_keys"], ["batch_accounting_tag_selection"])
        self.assertFalse(plan["written"])
        self.assertTrue(normalize("--execute")["written"])
        row = self.connection.fetch_one("select version,settings_payload,raw_payload from app.app_settings")
        expected = {key: value for key, value in payload.items() if key != "batch_accounting_tag_selection"}
        self.assertEqual(row["settings_payload"], expected)
        self.assertEqual(row["raw_payload"], {"normalized_payload": expected})
        self.assertEqual(row["version"], 8)
        self.assertEqual(audit_settings_page(self.connection)["overall_status"], "pass")
        self.assertEqual(self.service.detail("CASE-BATCH-SUBMITTED"), before_history)
        self.assertFalse(normalize("--execute")["written"])
        self.assertEqual(self.connection.fetch_one("select version,settings_payload,raw_payload from app.app_settings"), row)

    def _seed_canonical_facts(self) -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, status, raw_payload
            )
            values
                (
                    'txn-batch-unsubmitted', '6227000012348106', '云南溯源科技有限公司', 'outflow',
                    '批量账务集中处理', 1200, -1200, '2026-01-07', '2026-01-01',
                    '2026-01-07 15:54:00+08', 'active',
                    '{"normalized_payload":{"imported_bank_name":"建设银行","imported_bank_last4":"8106"}}'::jsonb
                ),
                (
                    'txn-batch-submitted', '6227000012348106', '云南溯源科技有限公司', 'outflow',
                    '批量账务集中处理', 800, -800, '2026-02-07', '2026-02-01',
                    '2026-02-07 15:54:00+08', 'active',
                    '{"normalized_payload":{"imported_bank_name":"建设银行","imported_bank_last4":"8106"}}'::jsonb
                ),
                (
                    'txn-batch-linked-other', '6227000012348106', '云南溯源科技有限公司', 'outflow',
                    '批量账务集中处理', 500, -500, '2026-03-07', '2026-03-01',
                    '2026-03-07 15:54:00+08', 'active',
                    '{"normalized_payload":{"imported_bank_name":"建设银行","imported_bank_last4":"8106"}}'::jsonb
                ),
                (
                    'txn-batch-income', '6227000012348106', '云南溯源科技有限公司', 'inflow',
                    '批量账务集中处理', 300, 300, '2026-04-07', '2026-04-01',
                    '2026-04-07 15:54:00+08', 'active',
                    '{"normalized_payload":{"imported_bank_name":"建设银行","imported_bank_last4":"8106"}}'::jsonb
                ),
                (
                    'txn-other-counterparty', '6227000012348106', '云南溯源科技有限公司', 'outflow',
                    '其他对方', 300, -300, '2026-05-07', '2026-05-01',
                    '2026-05-07 15:54:00+08', 'active',
                    '{"normalized_payload":{"imported_bank_name":"建设银行","imported_bank_last4":"8106"}}'::jsonb
                )
            """
        )
        self.connection.execute(
            """
            insert into app.bank_transaction_category_confirmations(
                legacy_transaction_id, category_code, status, confirmed_by
            )
            values
                ('txn-batch-unsubmitted', 'fee', 'active', 'integration-test'),
                ('txn-batch-submitted', 'fee', 'active', 'integration-test'),
                ('txn-batch-linked-other', 'fee', 'active', 'integration-test')
            """
        )
        self.connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            )
            values
                (
                    'oa-source-eligible', 'expense_claim', '日常报销', 'oa-batch-eligible',
                    'active', 'completed', '刘晨', '2025-12-31', '2025-12-01',
                    '品牌广告投放', 1200, 'CNY',
                    '{"apply_type":"日常报销","reason":"跨年日常报销","apply_time":"2025-12-31"}'::jsonb,
                    '{}'::jsonb
                ),
                (
                    'oa-source-invoice-only', 'expense_claim', '日常报销', 'oa-batch-invoice-only',
                    'active', 'completed', '王明', '2026-01-02', '2026-01-01',
                    '品牌广告投放', 100, 'CNY',
                    '{"apply_type":"日常报销","reason":"仅有发票关系"}'::jsonb, '{}'::jsonb
                ),
                (
                    'oa-source-bank-linked', 'expense_claim', '日常报销', 'oa-batch-bank-linked',
                    'active', 'completed', '赵敏', '2026-01-03', '2026-01-01',
                    '已关联项目', 500, 'CNY',
                    '{"apply_type":"日常报销","reason":"已关联流水"}'::jsonb, '{}'::jsonb
                ),
                (
                    'oa-source-progress', 'expense_claim', '日常报销', 'oa-batch-progress',
                    'active', 'in_progress', '未完成', '2026-01-04', '2026-01-01',
                    '未完成项目', 100, 'CNY',
                    '{"apply_type":"日常报销"}'::jsonb, '{}'::jsonb
                ),
                (
                    'oa-source-other', 'payment_request', '付款申请', 'oa-batch-other',
                    'active', 'completed', '其他', '2026-01-05', '2026-01-01',
                    '其他流程', 100, 'CNY',
                    '{"apply_type":"付款申请"}'::jsonb, '{}'::jsonb
                ),
                (
                    'oa-source-submitted', 'expense_claim', '日常报销', 'oa-batch-submitted',
                    'active', 'completed', '提交用户', '2026-02-01', '2026-02-01',
                    '已提交项目', 800, 'CNY',
                    '{"apply_type":"日常报销","reason":"已提交"}'::jsonb, '{}'::jsonb
                )
            """
        )
        self.connection.execute(
            """
            insert into app.oa_attachments(
                oa_application_id, oa_source_id, form_id, source_attachment_key,
                filename, normalized_payload, raw_payload
            )
            select id, row_id, form_id, 'attachment-batch-eligible', 'invoice.pdf',
                   '{}'::jsonb, '{}'::jsonb
            from app.oa_applications
            where row_id = 'oa-batch-eligible'
            """
        )
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, source_links, raw_payload
            )
            values
                (
                    'oa-att-inv-eligible', 'input_vat', 'INV-ELIGIBLE', '2025-12-30', '2025-12-01',
                    1200, 1200, 1200, 'pending',
                    '[{
                        "source_type":"oa_attachment_invoice",
                        "derived_from_oa_id":"oa-batch-eligible",
                        "source_attachment_key":"attachment-batch-eligible"
                    }]'::jsonb,
                    '{}'::jsonb
                ),
                (
                    'oa-att-inv-submitted', 'input_vat', 'INV-SUBMITTED', '2026-02-01', '2026-02-01',
                    800, 800, 800, 'pending',
                    '[{
                        "source_type":"oa_attachment_invoice",
                        "derived_from_oa_id":"oa-batch-submitted"
                    }]'::jsonb,
                    '{}'::jsonb
                )
            """
        )
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, note, amount_check, special_metadata
            )
            values
                (
                    'CASE-BATCH-SUBMITTED', 'batch_accounting', 'active', 3, '2026-02-01',
                    array['txn-batch-submitted','oa-batch-submitted','oa-att-inv-submitted'],
                    array['bank','oa','invoice'],
                    '已提交',
                    '{"status":"matched","bank_amount":"800.00","oa_amount":"800.00","amount_delta":"0.00"}'::jsonb,
                    '{
                        "source":"batch_accounting",
                        "bank_year":"2026",
                        "affected_scope_keys":["2026-02"]
                    }'::jsonb
                ),
                (
                    'CASE-OTHER-BANK', 'manual_confirmed', 'active', 1, '2026-03-01',
                    array['txn-batch-linked-other','oa-batch-bank-linked'],
                    array['bank','oa'], 'other', '{}'::jsonb, '{}'::jsonb
                ),
                (
                    'CASE-INVOICE-ONLY', 'existing_case', 'active', 1, '2026-01-01',
                    array['oa-batch-invoice-only','oa-att-inv-eligible'],
                    array['oa','invoice'], 'invoice only', '{}'::jsonb, '{}'::jsonb
                ),
                (
                    'CASE-BATCH-CANCELLED', 'batch_accounting', 'cancelled', 2, '2026-02-01',
                    array['txn-batch-unsubmitted','oa-batch-eligible'],
                    array['bank','oa'], 'cancelled', '{}'::jsonb,
                    '{"source":"batch_accounting","bank_year":"2026"}'::jsonb
                )
            """
        )

    def test_history_excludes_cancelled_and_other_modes_and_reads_complete_detail(self):
        payload = self.service.build_payload()
        self.assertEqual(payload["summary"], {"relation_count": 1, "transaction_count": 1, "bank_year": None})
        self.assertEqual([r["relation_id"] for r in payload["rows"]], ["CASE-BATCH-SUBMITTED"])
        self.assertEqual(payload["rows"][0]["bank_amount"], "800.00")
        detail = self.service.detail("CASE-BATCH-SUBMITTED")
        self.assertEqual(detail["bank_rows"][0]["bank_name"], "建设银行")
        self.assertEqual(detail["bank_rows"][0]["account_last4"], "8106")
        self.assertEqual([r["id"] for r in detail["oa_rows"]], ["oa-batch-submitted"])
        self.assertEqual([r["id"] for r in detail["invoice_rows"]], ["oa-att-inv-submitted"])
        self.assertEqual(detail["amount_delta"], "0.00")
        self.assertEqual(detail["missing_member_ids"], [])
        for relation_id in ("CASE-BATCH-CANCELLED", "CASE-OTHER-BANK", "missing"):
            with self.assertRaises(BatchAccountingError) as error:
                self.service.detail(relation_id)
            self.assertEqual(error.exception.code, "batch_accounting_relation_not_found")

    def test_year_filter_pagination_and_all_years(self):
        payload = self.service.build_payload(bank_year="2025")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["available_years"], ["2026"])
        self.assertEqual(payload["pagination"]["total"], 0)
        second = self.service.build_payload(bank_year="2026", page=2, page_size=1)
        self.assertEqual(second["rows"], [])
        self.assertEqual(second["pagination"]["total"], 1)

    def test_multi_bank_refund_amount_and_duplicate_members(self):
        self.connection.execute("""update app.workbench_pair_relations set
            row_ids=row_ids||array['txn-batch-income','txn-batch-submitted'],
            row_types=row_types||array['bank','bank'] where case_id='CASE-BATCH-SUBMITTED'""")
        payload = self.service.build_payload()
        self.assertEqual(payload["summary"]["transaction_count"], 2)
        self.assertEqual(payload["rows"][0]["bank_count"], 2)
        self.assertEqual(payload["rows"][0]["bank_amount"], "500.00")
        detail = self.service.detail("CASE-BATCH-SUBMITTED")
        self.assertEqual(len(detail["bank_rows"]), 2)
        self.assertEqual(detail["bank_amount"], "500.00")
        self.assertEqual(detail["amount_delta"], "-300.00")

    def test_missing_member_is_visible_without_synthetic_amount(self):
        self.connection.execute("""update app.workbench_pair_relations set
            row_ids=row_ids||array['missing-bank'],row_types=row_types||array['bank']
            where case_id='CASE-BATCH-SUBMITTED'""")
        payload = self.service.build_payload()
        self.assertIsNone(payload["rows"][0]["bank_amount"])
        detail = self.service.detail("CASE-BATCH-SUBMITTED")
        self.assertEqual(detail["missing_member_ids"], ["missing-bank"])
        self.assertIsNone(detail["bank_amount"])

    def test_canonical_reads_do_not_change_facts(self):
        before = self.connection.fetch_all(
            "select case_id,status,version,row_ids,note from app.workbench_pair_relations order by case_id"
        )
        self.service.build_payload()
        self.service.detail("CASE-BATCH-SUBMITTED")
        self.assertEqual(
            before,
            self.connection.fetch_all(
                "select case_id,status,version,row_ids,note from app.workbench_pair_relations order by case_id"
            ),
        )

    def test_account_pairs_are_kept_together_for_multi_bank_history(self):
        self.connection.execute("""insert into app.bank_transactions(
            legacy_mongo_id,account_no,account_name,txn_direction,counterparty_name_raw,
            amount,signed_amount,txn_date,txn_month,status,raw_payload)
            values ('txn-other-account','6227000000000001','company','outflow','乙',25,-25,
                '2025-12-31','2025-12-01','active',
                '{"normalized_payload":{"imported_bank_name":"农业银行","imported_bank_last4":"0001"}}')""")
        self.connection.execute("""update app.workbench_pair_relations set
            row_ids=row_ids||array['txn-other-account'],row_types=row_types||array['bank']
            where case_id='CASE-BATCH-SUBMITTED'""")
        payload = self.service.build_payload(bank_year="2025")
        row = payload["rows"][0]
        self.assertEqual(row["bank_amount"], "825.00")
        self.assertEqual(row["bank_count"], 2)
        self.assertEqual(
            row["bank_accounts"],
            [{"bank_name": "农业银行", "account_last4": "0001"}, {"bank_name": "建设银行", "account_last4": "8106"}],
        )
        self.assertEqual(payload["available_years"], ["2026", "2025"])
        self.assertEqual(payload["summary"]["transaction_count"], 2)

    def test_history_query_count_is_bounded(self):
        statements = []

        @contextmanager
        def transaction():
            with self.connection.transaction() as tx:

                def fetch_one(sql, params):
                    statements.append(sql)
                    return tx.fetch_one(sql, params)

                def fetch_all(sql, params):
                    statements.append(sql)
                    return tx.fetch_all(sql, params)

                yield SimpleNamespace(execute=tx.execute, fetch_one=fetch_one, fetch_all=fetch_all)

        repository = PostgresBatchAccountingQueryRepository(SimpleNamespace(transaction=transaction))
        service = BatchAccountingService(query_repository=repository)
        service.build_payload(page_size=200)
        self.assertEqual(len(statements), 1)
        service.detail("CASE-BATCH-SUBMITTED")
        self.assertEqual(len(statements), 3)
        self.assertFalse(any("app_settings" in sql or "candidate" in sql for sql in statements))

    def test_canonical_aliases_are_consistent_between_list_and_detail(self):
        self.connection.execute("""update app.workbench_pair_relations set
            row_types=array[' BANK_TRANSACTION ','OA_APPLICATION','INPUT_INVOICE']
            where case_id='CASE-BATCH-SUBMITTED'""")
        payload = self.service.build_payload(bank_year="2026")
        self.assertEqual(payload["rows"][0]["bank_count"], 1)
        self.assertEqual(payload["rows"][0]["oa_count"], 1)
        self.assertEqual(payload["summary"]["transaction_count"], 1)
        self.assertEqual(self.service.detail("CASE-BATCH-SUBMITTED")["missing_member_ids"], [])

    def test_etc_summary_uses_canonical_owner_and_keeps_missing_members_explicit(self):
        self.connection.execute("""insert into app.etc_business_batches(business_batch_id,status,scope_month,
            invoice_count,total_amount,raw_payload) values ('history-etc','oa_submitted','2026-02-01',1,800,
            '{"normalized_payload":{"external_etc_batch_id":"history/external"}}')""")
        self.connection.execute("""insert into app.etc_batch_invoice_links(business_batch_id,invoice_id,link_status,identity_key,link_source,confidence)
            select 'history-etc',id,'active','history-invoice','test','strict' from app.invoices where legacy_mongo_id='oa-att-inv-submitted'""")
        self.connection.execute("""update app.workbench_pair_relations set
            row_ids=array['txn-batch-submitted','oa-batch-submitted','etc-summary-history-external','etc-summary-missing'],
            row_types=array['bank','oa','etc_summary','invoice'] where case_id='CASE-BATCH-SUBMITTED'""")
        detail = self.service.detail("CASE-BATCH-SUBMITTED")
        self.assertEqual(detail["missing_member_ids"], ["etc-summary-missing"])
        summary = detail["invoice_rows"][0]
        self.assertEqual(summary["id"], "etc-summary-history-external")
        self.assertEqual(summary["total_with_tax"], "800.00")
        self.assertEqual([row["id"] for row in summary["etc_invoice_detail_rows"]], ["oa-att-inv-submitted"])
        self.assertEqual(summary["etc_invoice_detail_rows"][0]["invoice_no"], "INV-SUBMITTED")
        self.assertEqual(detail["bank_amount"], "800.00")
        with self.connection.transaction() as tx:
            tx.execute("select set_config('fin_ops.correction_reason','synthetic missing amount history test',true)")
            tx.execute(
                "update app.invoices set amount=null,total_with_tax=null where legacy_mongo_id='oa-att-inv-submitted'"
            )
        incomplete = self.service.detail("CASE-BATCH-SUBMITTED")["invoice_rows"][0]
        self.assertIsNone(incomplete["amount"])
        self.assertIsNone(incomplete["total_with_tax"])
        self.assertIsNone(incomplete["etc_invoice_detail_rows"][0]["amount"])
        self.assertIsNone(incomplete["etc_invoice_detail_rows"][0]["total_with_tax"])
