import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fin_ops_platform.services.cost_statistics_canonical_repository import PostgresCostStatisticsCanonicalRepository
from fin_ops_platform.services.cost_statistics_manual_allocation_service import (
    CostStatisticsManualAllocationConflictError,
    CostStatisticsManualAllocationService,
    CostStatisticsManualAllocationValidationError,
)
from fin_ops_platform.services.cost_statistics_query_service import CostStatisticsQueryService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.cost_statistics_manual_allocation import (
    PostgresCostStatisticsManualAllocationRepository,
)
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class CostSourcePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.addCleanup(truncate_test_database, self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.repository = PostgresCostStatisticsCanonicalRepository(self.connection)
        self.service = CostStatisticsManualAllocationService(canonical_repository=self.repository,
            allocation_repository=PostgresCostStatisticsManualAllocationRepository(self.connection), write_connection=self.connection)
        self.query = CostStatisticsQueryService(canonical_repository=self.repository)
        from tests.test_bank_same_time_ordering_postgres import BankSameTimeOrderingPostgresTests
        for bank_id, date, account in (("bank-1", "2026-08-01", "622200008106"), ("bank-2", "2026-09-01", "622200009486")):
            BankSameTimeOrderingPostgresTests.add_transaction(self, bank_id, signed_amount="-500.00", balance="1000.00", trade_time=date + " 12:00:00+08", txn_date=date, account_no=account)
        for oa_id, amount in (("oa-a", "600.00"), ("oa-b", "400.00")):
            self.connection.execute("""insert into app.oa_applications
                (oa_source_id, form_id, form_type, row_id, status, workflow_status, applicant,
                 application_date, scope_month, approved_at, project_name, amount, currency, normalized_payload, raw_payload)
                values (%s,%s,'支付申请',%s,'active','completed','测试申请人','2026-08-01','2026-08-01',
                        '2026-08-01 10:00:00+08','测试项目',%s,'CNY',%s::jsonb,'{}'::jsonb)""",
                (oa_id, oa_id, oa_id, amount, json.dumps({"id": oa_id, "project_name": "测试项目", "amount": amount, "expense_type": "原OA分类", "expense_content": "测试采购"})))
        self.connection.execute("""insert into app.workbench_pair_relations
            (case_id, version, relation_mode, row_ids, row_types, month_scope, status, raw_payload)
            values ('cost-source-case',1,'manual_confirmed',%s::text[],%s::text[],'2026-08-01','active','{}'::jsonb)""",
            (["oa-a", "oa-b", "bank-1", "bank-2"], ["oa", "oa", "bank", "bank"]))

    def test_prefill_reads_explicit_references_without_writing_then_saves(self):
        with self.connection.transaction() as writer:
            writer.execute("select set_config('fin_ops.correction_reason', 'isolated prefill evidence fixture', true)")
            for bank, oa, amount in (("bank-1", "oa-a", "600.00"), ("bank-2", "oa-b", "400.00")):
                writer.execute("""update app.bank_transactions set amount=%s,
                    signed_amount=-%s::numeric, raw_payload=jsonb_build_object('source_oa_row_id',%s::text)
                    where legacy_mongo_id=%s""", (amount, amount, oa, bank))
        before = self.service.list_tasks(cursor=None, page_size=20, status="pending", query=None, can_save=True)
        task = self.service.get_task("cost-source-case", can_save=True)
        self.assertEqual(task["status"], "pending")
        self.assertIsNone(task["source_allocations"])
        self.assertEqual(len(task["suggested_source_allocations"]["cost_lines"]), 2)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.cost_statistics_manual_allocations")["n"], 0)
        after = self.service.list_tasks(cursor=None, page_size=20, status="pending", query=None, can_save=True)
        self.assertEqual(before, after)
        self.assertNotIn("suggested_source_allocations", after["items"][0])
        payload = self.payload()
        payload["source_allocations"] = task["suggested_source_allocations"]
        saved = self.save(payload)
        self.assertEqual(saved["version"], 1)
        reloaded = self.service.get_task("cost-source-case", can_save=True)
        self.assertEqual(reloaded["source_allocations"], payload["source_allocations"])
        self.assertIsNone(reloaded["suggested_source_allocations"])

    def test_equal_amount_alignment_without_explicit_reference_has_no_suggestion(self):
        with self.connection.transaction() as writer:
            writer.execute("select set_config('fin_ops.correction_reason', 'isolated amount-only fixture', true)")
            writer.execute("""update app.bank_transactions set
                amount=case legacy_mongo_id when 'bank-1' then 600 else 400 end,
                signed_amount=case legacy_mongo_id when 'bank-1' then -600 else -400 end
                where legacy_mongo_id in ('bank-1','bank-2')""")
        task = self.service.get_task("cost-source-case", can_save=True)
        self.assertIsNone(task["suggested_source_allocations"])
        self.assertEqual(task["status"], "pending")

    def payload(self):
        task = self.service.get_task("cost-source-case", can_save=True)
        return {"relation_case_id": task["relation_case_id"], "expected_version": task["version"],
                "source_fingerprint": task["source_fingerprint"], "allocations": task["allocations"],
                "non_cost_amount": "0.00", "non_cost_reason": "", "source_allocations": {
                    "cost_lines": [{"unit_id": "oa:oa-a", "bank_transaction_id": "bank-1", "amount": "500.00"},
                                   {"unit_id": "oa:oa-a", "bank_transaction_id": "bank-2", "amount": "100.00"},
                                   {"unit_id": "oa:oa-b", "bank_transaction_id": "bank-2", "amount": "400.00"}],
                    "refund_links": [], "non_cost_lines": []}}

    def save(self, payload):
        return self.service.save("cost-source-case", payload, actor={"id": "cost-test-actor"})

    def test_save_audit_and_cross_month_read_closure(self):
        payload = self.payload()
        saved = self.save(payload)
        self.assertEqual(saved["version"], 1)
        self.assertEqual(saved["source_allocations"], payload["source_allocations"])
        reloaded = self.service.get_task("cost-source-case", can_save=True)
        self.assertEqual(reloaded["source_allocations"], saved["source_allocations"])
        self.assertEqual(reloaded["status"], saved["status"])
        audit = self.connection.fetch_one("select payload from audit.events where action='cost_statistics.manual_allocation.save'")
        self.assertEqual(audit["payload"]["source_allocations"], payload["source_allocations"])
        for view in ("project", "bank_account", "cost_tag"):
            for month in ("2026-08", "2026-09"):
                for include_statistics in (True, False):
                    page = self.query.get_explorer_page(scope=month, view=view, filters={}, cursor=None, page_size=20, include_statistics=include_statistics)
                    self.assertEqual(page["summary"]["total_amount"], "500.00")
        tasks = self.service.list_tasks(cursor=None, page_size=20, status=saved["status"], query=None, can_save=True)
        self.assertNotIn("bank_events", tasks["items"][0])
        self.assertNotIn("source_allocations", tasks["items"][0])

    def test_editable_source_totals_save_without_changing_original_oa_amount(self):
        # The table derives 600/400 from its source rows; the original OA remains 700/400.
        self.connection.execute("""update app.oa_applications set amount=700,
            normalized_payload=jsonb_set(normalized_payload,'{amount}','"700.00"'::jsonb)
            where oa_source_id='oa-a'""")
        task = self.service.get_task("cost-source-case", can_save=True)
        self.assertFalse(task["amounts_fixed"])
        payload = self.payload()
        payload["allocations"] = [{"unit_id": "oa:oa-a", "amount": "600.00"},
                                  {"unit_id": "oa:oa-b", "amount": "400.00"}]
        from tests.app_test_support import build_local_state_application
        app = build_local_state_application()
        # Keep the real HTTP mapping/session boundary; use this test's real PG services.
        app._cost_statistics_api_routes._manual_allocation_service = self.service  # noqa: SLF001
        app._cost_statistics_api_routes._query_service = self.query  # noqa: SLF001
        path = "/api/cost-statistics/manual-allocations/cost-source-case"
        response = app.handle_request("PUT", path, body=json.dumps(payload))
        self.assertEqual(response.status_code, 200, response.body)
        saved = json.loads(response.body)
        self.assertEqual(saved["allocations"], payload["allocations"])
        response = app.handle_request("GET", path)
        self.assertEqual(response.status_code, 200)
        reread = json.loads(response.body)
        self.assertEqual(reread["source_allocations"], payload["source_allocations"])
        self.assertEqual(next(unit for unit in reread["units"] if unit["unit_id"] == "oa:oa-a")["oa_original_amount"], "700.00")
        for view in ("project", "cost_tag", "bank_account"):
            for month in ("2026-08", "2026-09"):
                response = app.handle_request("GET", f"/api/cost-statistics/explorer?view={view}&scope={month}&page_size=20")
                self.assertEqual(response.status_code, 200, response.body)
                page = json.loads(response.body)
                self.assertEqual(page["summary"]["total_amount"], "500.00")

    def test_audit_failure_rolls_back_the_allocation(self):
        payload = self.payload()
        with patch.object(PostgresOperationsAuditRepository, "append_operation_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                self.save(payload)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.cost_statistics_manual_allocations")["n"], 0)

    def test_two_concurrent_saves_commit_only_one_decision(self):
        payload = self.payload()
        def attempt():
            try:
                return self.save(payload)["version"]
            except CostStatisticsManualAllocationConflictError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: attempt(), range(2)))
        self.assertCountEqual(outcomes, [1, "conflict"])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from audit.events where action='cost_statistics.manual_allocation.save'")["n"], 1)

    def test_source_amount_update_cannot_be_half_read(self):
        payload = self.payload()
        with self.connection.transaction() as source_writer:
            source_writer.execute("select set_config('fin_ops.correction_reason', 'isolated cost source concurrency test', true)")
            source_writer.execute("update app.bank_transactions set amount=550, signed_amount=-550 where legacy_mongo_id='bank-1'")
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(self.save, payload)
                with self.assertRaises(CostStatisticsManualAllocationConflictError):
                    result.result(timeout=5)
        with self.assertRaises(CostStatisticsManualAllocationConflictError):
            self.save(payload)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.cost_statistics_manual_allocations")["n"], 0)

    def test_concurrent_relation_withdraw_cannot_commit_a_cost_decision(self):
        payload = self.payload()
        with self.connection.transaction() as relation_writer:
            relation_writer.execute("update app.workbench_pair_relations set status='withdrawn', version=version+1 where case_id='cost-source-case'")
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(CostStatisticsManualAllocationConflictError):
                    pool.submit(self.save, payload).result(timeout=5)
        with self.assertRaises(CostStatisticsManualAllocationConflictError):
            self.save(payload)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.cost_statistics_manual_allocations")["n"], 0)

    def test_targeted_detail_and_save_reject_duplicate_owners(self):
        from fin_ops_platform.services.cost_statistics_policy import CostStatisticsAllocationConflictError
        payload = self.payload()
        self.connection.execute("""insert into app.workbench_pair_relations
            (case_id,version,relation_mode,row_ids,row_types,month_scope,status,raw_payload)
            values ('duplicate-cost-case',1,'manual_confirmed',array['oa-a','bank-1'],array['oa','bank'],'2026-08-01','active','{}'::jsonb)""")
        with self.assertRaises(CostStatisticsAllocationConflictError):
            self.service.get_task("cost-source-case", can_save=True)
        with self.assertRaises(CostStatisticsAllocationConflictError):
            self.query.get_allocation_detail("relation:cost-source-case:unit:oa:oa-a", view="project", scope="all")
        with self.assertRaises(CostStatisticsAllocationConflictError):
            self.save(payload)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.cost_statistics_manual_allocations")["n"], 0)

    def test_invalid_source_and_changed_unit_target_do_not_write(self):
        payload = self.payload()
        payload["source_allocations"]["cost_lines"][0]["bank_transaction_id"] = "outside"
        with self.assertRaises(CostStatisticsManualAllocationValidationError):
            self.save(payload)
        payload = self.payload()
        payload["allocations"] = [{"unit_id": "oa:oa-a", "amount": "500.00"}, {"unit_id": "oa:oa-b", "amount": "500.00"}]
        with self.assertRaises(CostStatisticsManualAllocationValidationError):
            self.save(payload)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.cost_statistics_manual_allocations")["n"], 0)
