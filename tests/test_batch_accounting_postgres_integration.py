from __future__ import annotations

from contextlib import contextmanager
import json
from time import perf_counter
from typing import Any, Iterator
import unittest

from fin_ops_platform.services.batch_accounting_service import BatchAccountingService
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

        self.assertEqual(len(unsubmitted_connection.transaction_instance.statements), 5)
        self.assertEqual(len(submitted_connection.transaction_instance.statements), 4)
        self.assertEqual(len(submission_connection.transaction_instance.statements), 4)
        for connection in (unsubmitted_connection, submitted_connection, submission_connection):
            statements = connection.transaction_instance.statements
            combined_sql = "\n".join(statements)
            self.assertEqual(statements[0], "set transaction isolation level repeatable read read only")
            self.assertNotIn("read_model.", combined_sql)
            self.assertNotIn("workbench_generations", combined_sql)
            self.assertIn("->>'imported_bank_name'", combined_sql)
            self.assertIn("->>'imported_bank_last4'", combined_sql)
            self.assertNotRegex(combined_sql, r"\b(?:bank|source)\.raw_payload\s*(?:,|\bas\b)")
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
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
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
