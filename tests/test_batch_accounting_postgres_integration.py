from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from time import perf_counter
from typing import Any, Iterator

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_details_canonical_query import (
    PostgresBankDetailsCanonicalQueryRepository,
    bank_category_classification_cte,
)
from fin_ops_platform.services.batch_accounting_service import BatchAccountingError, BatchAccountingService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.batch_accounting import (
    PostgresBatchAccountingQueryRepository,
)

from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class RecordingTransaction:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str, _params: tuple[Any, ...] | None = None) -> None:
        self.statements.append(sql)

    def fetch_one(self, sql: str, _params: tuple[Any, ...] | None = None) -> dict[str, int]:
        self.statements.append(sql)
        return {"unsubmitted_count": 0, "submitted_count": 0, "oa_count": 0}

    def fetch_all(self, sql: str, _params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        self.statements.append(sql)
        if "from app.oa_applications oa" in sql and "limit %s offset %s" in sql:
            return [{"id": "oa-batch-1"}]
        if "from app.workbench_pair_relations relation" in sql and "join lateral" in sql:
            return [
                {
                    "case_id": "CASE-BATCH-1",
                    "status": "active",
                    "relation_mode": "batch_accounting",
                    "row_ids": ["txn-batch-1", "oa-batch-1"],
                    "row_types": ["bank", "oa"],
                    "bank_row": {"id": "txn-batch-1"},
                }
            ]
        return []


class RecordingConnection:
    def __init__(self) -> None:
        self.transaction_instance = RecordingTransaction()

    @contextmanager
    def transaction(self) -> Iterator[RecordingTransaction]:
        yield self.transaction_instance


class BatchAccountingQueryCountTests(unittest.TestCase):
    def test_repository_uses_fixed_statement_counts_without_read_models(self) -> None:
        unsubmitted_connection = RecordingConnection()
        PostgresBatchAccountingQueryRepository(unsubmitted_connection).list_snapshot(
            bank_year="2026",
            bucket="unsubmitted",
            bank_page=1,
            bank_page_size=200,
            oa_page=1,
            oa_page_size=200,
        )
        submitted_connection = RecordingConnection()
        PostgresBatchAccountingQueryRepository(submitted_connection).list_snapshot(
            bank_year="2026",
            bucket="submitted",
            bank_page=1,
            bank_page_size=200,
            oa_page=1,
            oa_page_size=200,
        )
        submission_connection = RecordingConnection()
        PostgresBatchAccountingQueryRepository(submission_connection).load_submission_context(
            bank_year="2026",
            bank_row_id="txn-batch-1",
            oa_row_ids=["oa-batch-1"],
        )

        self.assertLessEqual(len(unsubmitted_connection.transaction_instance.statements), 5)
        self.assertLessEqual(len(submitted_connection.transaction_instance.statements), 5)
        self.assertLessEqual(len(submission_connection.transaction_instance.statements), 5)
        for connection in (unsubmitted_connection, submitted_connection, submission_connection):
            statements = connection.transaction_instance.statements
            combined_sql = "\n".join(statements)
            self.assertEqual(statements[0], "set transaction isolation level repeatable read read only")
            self.assertNotIn("read_model.", combined_sql)
            self.assertNotIn("workbench_generations", combined_sql)
            self.assertIn("->>'imported_bank_name'", combined_sql)
            self.assertIn("->>'imported_bank_last4'", combined_sql)
            self.assertNotIn(" as raw_payload", combined_sql.lower())
            self.assertNotIn("'raw_payload'", combined_sql)
            self.assertNotIn("'source_links', invoice.source_links", combined_sql)


class BatchAccountingPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.repository = PostgresBatchAccountingQueryRepository(self.connection)
        self._seed_canonical_facts()

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

    def _correct_bank(self, sql):
        with self.connection.transaction() as tx:
            tx.execute("select set_config('fin_ops.correction_reason','synthetic date range regression',true)")
            tx.execute(sql)

    def _bank_with_date(self, row_id, canonical_date, display_time):
        self.connection.execute(
            """insert into app.bank_transactions(
            legacy_mongo_id,account_no,account_name,txn_direction,counterparty_name_raw,
            amount,signed_amount,txn_date,txn_month,trade_time,status,raw_payload)
            select %s,account_no,account_name,txn_direction,counterparty_name_raw,
                amount,signed_amount,%s::date,date_trunc('month',%s::date)::date,%s::timestamptz,status,raw_payload
            from app.bank_transactions where legacy_mongo_id='txn-batch-unsubmitted'
            """,
            (row_id, canonical_date, canonical_date, display_time),
        )
        self.connection.execute(
            """insert into app.bank_transaction_category_confirmations(
            legacy_transaction_id,category_code,status,confirmed_by) values(%s,'fee','active','test')""",
            (row_id,),
        )

    def _page(self, year=None, bucket="unsubmitted", page=1, size=200):
        return self.repository.list_snapshot(
            bank_year=year, bucket=bucket, bank_page=page, bank_page_size=size, oa_page=1, oa_page_size=20
        )

    def test_all_years_sql_pages_unknown_dates_and_canonical_year(self):
        self._bank_with_date("old", "2024-01-01", "2024-01-01T00:00:00+08")
        self._bank_with_date("date-conflict", "2025-12-31", "2026-01-01T00:00:00+08")
        self._bank_with_date("unknown", None, None)
        first, second = self._page(size=2), self._page(page=2, size=2)
        self.assertEqual(first["summary"]["unsubmitted_count"], 4)
        self.assertEqual(second["summary"], first["summary"])
        self.assertEqual(
            [r["id"] for r in first["bank_rows"] + second["bank_rows"]],
            ["txn-batch-unsubmitted", "date-conflict", "old", "unknown"],
        )
        self.assertIsNone(second["bank_rows"][-1]["bank_year"])
        self.assertEqual(first["bank_rows"][1]["bank_year"], "2025")
        self.assertEqual(self._page("2026")["summary"]["unsubmitted_count"], 1)
        context = self.repository.load_submission_context(bank_year="2025", bank_row_id="date-conflict", oa_row_ids=[])
        self.assertEqual(context["bank_rows"][0]["bank_year"], "2025")
        self.assertEqual(BatchAccountingService._row_month(context["bank_rows"][0]), "2025-12")
        service = BatchAccountingService(query_repository=self.repository)
        with self.assertRaises(BatchAccountingError) as caught:
            service.submit(bank_year="2026", bank_row_id="unknown", oa_row_ids=["oa-batch-eligible"], actor="test")
        self.assertEqual(caught.exception.code, "invalid_batch_accounting_bank_row")

    def test_submitted_unknown_dates_remain_visible_in_all_without_guessed_year(self):
        self._correct_bank("""update app.bank_transactions set txn_date=null,txn_month=null,
            trade_time=null,pay_receive_time=null where legacy_mongo_id='txn-batch-submitted'""")
        payload = BatchAccountingService(query_repository=self.repository).build_payload(
            bank_year="all", bucket="submitted"
        )
        self.assertIsNone(payload["summary"]["bank_year"])
        self.assertEqual(payload["summary"]["submitted_count"], 1)
        self.assertIsNone(payload["bank_rows"][0]["bank_year"])
        self.assertTrue(payload["bank_rows"][0]["relation_id"])
        self.assertEqual(self._page("2026", "submitted")["summary"]["submitted_count"], 0)

    def test_candidate_relation_classifier_equals_existing_ids_and_preserves_peer_context(self):
        self._bank_with_date("unknown", None, None)
        # The shared classifier must retain counterpart rows outside the page-owned candidate CTE.
        self._correct_bank("""update app.bank_transactions set counterparty_name_raw='云南溯源科技有限公司',summary='本公司账户',amount=300,
            signed_amount=-300,txn_date='2026-04-07',txn_month='2026-04-01',trade_time='2026-04-07 15:54:00+08'
            where legacy_mongo_id='txn-batch-unsubmitted'""")
        self.connection.execute(
            "delete from app.bank_transaction_category_confirmations where legacy_transaction_id='txn-batch-unsubmitted'"
        )
        self._correct_bank("""update app.bank_transactions set counterparty_name_raw='云南溯源科技有限公司',
            account_no='different-account',summary='本公司账户' where legacy_mongo_id='txn-batch-income'""")
        settings = AppSettingsService.normalize_settings_payload({})
        with self.repository._snapshot_transaction() as tx:
            candidates = "comparison_candidates as (select coalesce(legacy_mongo_id,id::text) as row_id from app.bank_transactions where legacy_mongo_id=any(%s::text[]))"
            params = (["txn-batch-unsubmitted", "txn-batch-submitted", "txn-batch-linked-other", "unknown"],)
            ids = [
                row["row_id"]
                for row in tx.fetch_all(f"with {candidates} select row_id from comparison_candidates", params)
            ]
            expected = PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows(
                tx, settings=settings, transaction_ids=ids
            )
            sql, sql_params = bank_category_classification_cte(
                definitions=settings["bank_transaction_tags"]["definitions"],
                date_from=None,
                date_to=None,
                candidate_transaction_relation="comparison_candidates",
                defer_full_payload=True,
            )
            rows = tx.fetch_all(
                f"""with {candidates},{sql} select c.*,
                coalesce(nullif(case
                    when effective_category_source='manual_confirmation'
                        then confirmation_raw_payload->'normalized_payload'->>'turnover_role'
                    when effective_category_source in ('manual','turnover_ledger')
                        then manual_category_raw_payload->'normalized_payload'->>'turnover_role'
                end,''),effective_definition->>'turnover_role','') as turnover_role
                from classified_with_semantics c
                join comparison_candidates b on b.row_id=c.row_id""",
                (*params, *sql_params),
            )
        self.assertEqual(set(expected), {row["row_id"] for row in rows})
        for row in rows:
            for key, value in expected[row["row_id"]].items():
                if key != "effective_category_label_path":
                    self.assertEqual(row[key], value, (row["row_id"], key))
        self.assertEqual(expected["txn-batch-unsubmitted"]["effective_category_code"], "internal_transfer")
        self.assertIn("fee", self.repository.tag_rules_snapshot()["observed_tag_codes"])

    def test_all_years_scale_keeps_payload_bounded_after_sql_classification(self) -> None:
        self.connection.execute("""
            insert into app.bank_transactions(
                legacy_mongo_id,account_no,account_name,txn_direction,counterparty_name_raw,
                amount,signed_amount,txn_date,txn_month,trade_time,status,raw_payload)
            select 'scale-'||n,'scale-account','合成测试','outflow',
                case when n<=10000 then '批量账务集中处理' else '其他' end,
                n+100000,-n-100000,date '2020-01-01'+n%%2300,
                date_trunc('month',date '2020-01-01'+n%%2300)::date,
                (date '2020-01-01'+n%%2300)::timestamptz,'active','{}'::jsonb
            from generate_series(1,20000)n
        """)
        self.connection.execute("""
            insert into app.bank_transaction_category_confirmations(
                legacy_transaction_id,category_code,status,confirmed_by)
            select 'scale-'||n,case when n%%2=0 then 'fee' else 'travel' end,
                'active','synthetic' from generate_series(1,10000)n
        """)
        self.connection.execute('analyze app.bank_transactions')
        self.connection.execute('analyze app.bank_transaction_category_confirmations')
        first, deep, empty = self._page(), self._page(page=20), self._page(page=40)
        for payload in (first, deep, empty):
            self.assertEqual(payload["summary"]["unsubmitted_count"], 5001)
            self.assertEqual(payload["pagination"]["bank_rows"]["total"], 5001)
            self.assertLess(len(json.dumps(payload, default=str).encode()), 200_000)
        self.assertEqual(len(first["bank_rows"]), 200)
        self.assertEqual(len(deep["bank_rows"]), 200)
        self.assertEqual(empty["bank_rows"], [])
        self.assertTrue({row["id"] for row in first["bank_rows"]}.isdisjoint(
            row["id"] for row in deep["bank_rows"]
        ))
        self.assertTrue(all(row["tag_code"] == "fee" for row in deep["bank_rows"]))

    def test_unsubmitted_snapshot_filters_pages_and_links_canonical_attachment_invoice(self) -> None:
        started_at = perf_counter()
        payload = self.repository.list_snapshot(
            bank_year="2026",
            bucket="unsubmitted",
            bank_page=1,
            bank_page_size=1,
            oa_page=1,
            oa_page_size=20,
            oa_search="品牌",
        )
        duration_ms = (perf_counter() - started_at) * 1000

        self.assertEqual(payload["summary"]["unsubmitted_count"], 1)
        self.assertEqual(payload["summary"]["submitted_count"], 1)
        self.assertEqual([row["id"] for row in payload["bank_rows"]], ["txn-batch-unsubmitted"])
        self.assertEqual(payload["bank_rows"][0]["bank_name"], "建设银行")
        self.assertEqual(payload["bank_rows"][0]["account_last4"], "8106")
        self.assertEqual(payload["bank_rows"][0]["tag_code"], "fee")
        self.assertEqual(payload["bank_rows"][0]["tag_label"], "手续费")
        self.assertEqual(payload["tag_selection_version"], 1)
        self.assertNotEqual(payload["bank_rows"][0]["bank_name"], "云南溯源科技有限公司")
        self.assertEqual(
            [row["id"] for row in payload["oa_rows"]],
            ["oa-batch-invoice-only", "oa-batch-eligible"],
        )
        self.assertEqual(
            [(row["id"], row["source_oa_id"]) for row in payload["invoice_rows"]],
            [("oa-att-inv-eligible", "oa-batch-eligible")],
        )
        self.assertEqual(payload["pagination"]["bank_rows"]["total"], 1)
        self.assertEqual(payload["pagination"]["oa_rows"]["total"], 2)
        self.assertLess(duration_ms, 5_000)

    def test_submitted_snapshot_reads_active_batch_relation_and_canonical_members(self) -> None:
        payload = self.repository.list_snapshot(
            bank_year="2026",
            bucket="submitted",
            bank_page=1,
            bank_page_size=20,
            oa_page=1,
            oa_page_size=20,
        )

        self.assertEqual(payload["summary"]["submitted_count"], 1)
        self.assertEqual([row["case_id"] for row in payload["relations"]], ["CASE-BATCH-SUBMITTED"])
        self.assertEqual(payload["relations"][0]["bank_row"]["id"], "txn-batch-submitted")
        self.assertEqual(payload["relations"][0]["bank_row"]["bank_name"], "建设银行")
        self.assertEqual(payload["relations"][0]["bank_row"]["account_last4"], "8106")
        self.assertEqual(
            {(row["member_type"], row["id"]) for row in payload["member_rows"]},
            {("oa", "oa-batch-submitted"), ("invoice", "oa-att-inv-submitted")},
        )
        page_payload = BatchAccountingService(query_repository=self.repository).build_payload(
            bank_year="2026",
            bucket="submitted",
        )
        self.assertEqual(
            page_payload["relations_by_bank_row_id"]["txn-batch-submitted"]["invoice_rows"][0]["issue_date"],
            "2026-02-01",
        )
        json.dumps(page_payload)
        self.assertEqual(payload["pagination"]["bank_rows"]["total"], 1)

    def test_submission_context_is_narrow_and_cross_year_oa_is_allowed(self) -> None:
        payload = self.repository.load_submission_context(
            bank_year="2026",
            bank_row_id="txn-batch-unsubmitted",
            oa_row_ids=["oa-batch-eligible"],
        )

        self.assertEqual([row["id"] for row in payload["bank_rows"]], ["txn-batch-unsubmitted"])
        self.assertEqual(payload["bank_rows"][0]["bank_name"], "建设银行")
        self.assertEqual(payload["bank_rows"][0]["account_last4"], "8106")
        self.assertEqual([row["id"] for row in payload["oa_rows"]], ["oa-batch-eligible"])
        self.assertEqual([row["id"] for row in payload["invoice_rows"]], ["oa-att-inv-eligible"])


if __name__ == "__main__":
    unittest.main()
