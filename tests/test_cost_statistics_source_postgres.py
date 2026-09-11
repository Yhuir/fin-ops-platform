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
        self.connection.execute("""insert into app.app_settings (settings_key,settings_payload) values
            ('app_settings', %s::jsonb)""", (json.dumps({"access_control_version":1,"page_access_accounts":[],"bank_transaction_tags": {},
                "cost_statistics_project_cost_scope": {"version": 1, "selected_tag_codes": ["uncategorized"]}}),))
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

    def test_unique_amount_alignment_without_reference_offers_pending_suggestion(self):
        with self.connection.transaction() as writer:
            writer.execute("select set_config('fin_ops.correction_reason', 'isolated amount-only fixture', true)")
            writer.execute("""update app.bank_transactions set
                amount=case legacy_mongo_id when 'bank-1' then 600 else 400 end,
                signed_amount=case legacy_mongo_id when 'bank-1' then -600 else -400 end
                where legacy_mongo_id in ('bank-1','bank-2')""")
        task = self.service.get_task("cost-source-case", can_save=True)
        self.assertEqual(len(task["suggested_source_allocations"]["cost_lines"]), 2)
        self.assertEqual(task["status"], "pending")

    def test_screenshot_prefill_http_save_reload_and_three_statistics_views(self):
        from tests.test_bank_same_time_ordering_postgres import BankSameTimeOrderingPostgresTests
        with self.connection.transaction() as writer:
            writer.execute("select set_config('fin_ops.correction_reason', 'isolated screenshot prefill fixture', true)")
            for bank, amount in [('bank-1', '64996.69'), ('bank-2', '23053.31')]:
                writer.execute("update app.bank_transactions set amount=%s,signed_amount=-%s::numeric where legacy_mongo_id=%s", (amount, amount, bank))
            for oa, amount in [('oa-a', '88050.00'), ('oa-b', '29350.00')]:
                writer.execute("update app.oa_applications set amount=%s,normalized_payload=jsonb_set(normalized_payload,'{amount}',to_jsonb(%s::text)) where row_id=%s", (amount, amount, oa))
        for bank, amount in [('bank-3', '29350.00'), ('bank-4', '469600.00')]:
            BankSameTimeOrderingPostgresTests.add_transaction(self, bank, signed_amount='-' + amount, balance='1000.00', trade_time='2026-09-01 12:00:00+08', txn_date='2026-09-01', account_no='622200009486')
        self.connection.execute("""insert into app.oa_applications
            (oa_source_id,form_id,form_type,row_id,status,workflow_status,applicant,application_date,scope_month,approved_at,project_name,amount,currency,normalized_payload,raw_payload)
            select 'oa-c','oa-c',form_type,'oa-c',status,workflow_status,applicant,application_date,scope_month,approved_at,project_name,469600,currency,
                jsonb_set(jsonb_set(normalized_payload,'{id}','"oa-c"'::jsonb),'{amount}','"469600.00"'::jsonb),raw_payload
            from app.oa_applications where row_id='oa-a'""")
        self.connection.execute("""update app.workbench_pair_relations set
            row_ids=array['oa-a','oa-b','oa-c','bank-1','bank-2','bank-3','bank-4'],
            row_types=array['oa','oa','oa','bank','bank','bank','bank'] where case_id='cost-source-case'""")
        from tests.app_test_support import build_local_state_application
        app = build_local_state_application()
        app._cost_statistics_api_routes._manual_allocation_service = self.service  # noqa: SLF001
        app._cost_statistics_api_routes._query_service = self.query  # noqa: SLF001
        path = '/api/cost-statistics/manual-allocations/cost-source-case'
        response = app.handle_request('GET', path)
        self.assertEqual(response.status_code, 200, response.body)
        task = json.loads(response.body)
        expected = {('oa:oa-a', 'bank-1', '64996.69'), ('oa:oa-a', 'bank-2', '23053.31'),
                    ('oa:oa-b', 'bank-3', '29350.00'), ('oa:oa-c', 'bank-4', '469600.00')}
        suggestion = task['suggested_source_allocations']
        self.assertEqual({(r['unit_id'], r['bank_transaction_id'], r['amount']) for r in suggestion['cost_lines']}, expected)
        self.assertEqual(task['status'], 'pending')
        self.assertIsNone(task['source_allocations'])
        self.assertEqual(self.connection.fetch_one('select count(*) as n from app.cost_statistics_manual_allocations')['n'], 0)
        payload = {**self.payload(), 'allocations': task['allocations'], 'source_allocations': suggestion}
        response = app.handle_request('PUT', path, body=json.dumps(payload))
        self.assertEqual(response.status_code, 200, response.body)
        saved = json.loads(response.body)
        self.assertEqual(saved['version'], 1)
        # Missing classifications may keep the saved decision pending; never invent tags.
        self.assertIsNone(saved['suggested_source_allocations'])
        reloaded = json.loads(app.handle_request('GET', path).body)
        self.assertEqual(reloaded['source_allocations'], suggestion)
        self.assertIsNone(reloaded['suggested_source_allocations'])
        audit = self.connection.fetch_one("select payload from audit.events where action='cost_statistics.manual_allocation.save'")
        self.assertEqual(audit['payload']['source_allocations'], suggestion)
        for view in ('project', 'bank_account', 'cost_tag'):
            for month, amount in [('all', '587000.00'), ('2026-08', '64996.69'), ('2026-09', '522003.31')]:
                response = app.handle_request('GET', f'/api/cost-statistics/explorer?view={view}&scope={month}&page_size=20')
                self.assertEqual(response.status_code, 200, response.body)
                self.assertEqual(json.loads(response.body)['summary']['total_amount'], amount)

    def scope_service(self):
        from pathlib import Path

        from fin_ops_platform.services.app_settings_service import AppSettingsService
        from fin_ops_platform.services.postgres_state_store import PostgresStateStore

        from tests.app_test_support import build_local_state_application
        app = build_local_state_application()
        return AppSettingsService(PostgresStateStore(data_dir=Path("/tmp"), connection=self.connection),
            app._project_costing_service)

    def test_scope_save_empty_restore_audit_cas_and_original_flows(self):
        from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
        service = self.scope_service()
        self.save(self.payload())
        original = self.service.get_task("cost-source-case", can_save=True)
        raw_before = self.query.get_explorer_page(scope="all", view="time", filters={}, cursor=None, page_size=20)
        result = service.update_project_cost_scope({"expected_version": 1, "selected_tag_codes": []}, actor_id="cost-test")
        self.assertEqual((result["version"], result["changed"]), (2, True))
        for view in ("project", "cost_tag", "bank_account"):
            self.assertEqual(self.query.get_explorer_page(scope="all", view=view, filters={}, cursor=None, page_size=20)["summary"]["total_amount"], "0.00")
        self.assertEqual(self.service.list_tasks(cursor=None,page_size=20,status="pending",query=None,can_save=True)["counts"], {"pending":0,"allocated":0})
        self.assertIsNone(self.service.get_task("cost-source-case", can_save=True)["source_allocations"])
        self.assertEqual(PostgresCostStatisticsManualAllocationRepository(self.connection).list_by_case_ids(["cost-source-case"])["cost-source-case"]["source_allocations"], original["source_allocations"])
        self.assertEqual(self.query.get_explorer_page(scope="all", view="time", filters={}, cursor=None, page_size=20), raw_before)
        result = self.scope_service().update_project_cost_scope({"expected_version": 2, "selected_tag_codes": []}, actor_id="cost-test")
        self.assertFalse(result["changed"])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from audit.events where action='cost_statistics.project_cost_scope.save'")["n"], 1)
        with self.assertRaises(AppSettingsValidationError):
            service.update_project_cost_scope({"expected_version":1,"selected_tag_codes":["uncategorized"]},actor_id="cost-test")
        result = service.update_project_cost_scope({"expected_version":2,"selected_tag_codes":["uncategorized"]},actor_id="cost-test")
        self.assertEqual(result["version"],3)
        self.assertEqual(self.query.get_explorer_page(scope="all",view="project",filters={},cursor=None,page_size=20)["summary"]["total_amount"],"1000.00")
        with patch.object(PostgresOperationsAuditRepository, "append_operation_event", side_effect=RuntimeError("audit failure")):
            with self.assertRaisesRegex(RuntimeError,"audit failure"):
                service.update_project_cost_scope({"expected_version":3,"selected_tag_codes":[]},actor_id="cost-test")
        self.assertEqual(service.get_project_cost_scope(can_save=True)["version"],3)

    def test_scope_version_invalidates_cost_cursor_and_empty_export(self):
        self.save(self.payload())
        filters={"project_name":"测试项目","bank_tag_primary_key":"pending:tag","bank_tag_sub_key":"pending:tag"}
        page=self.query.get_explorer_page(scope="all",view="project",filters=filters,cursor=None,page_size=1)
        self.assertIsNotNone(page["next_cursor"])
        self.scope_service().update_project_cost_scope({"expected_version":1,"selected_tag_codes":[]},actor_id="cost-test")
        with self.assertRaises(ValueError):
            self.query.get_explorer_page(scope="all",view="project",filters=filters,cursor=page["next_cursor"],page_size=1)
        preview=self.query.get_export_preview(view="project",month="all",project_names=["测试项目"])
        self.assertEqual(preview["summary"]["row_count"],0)

    def test_scope_http_contract_and_concurrent_writes(self):
        from fin_ops_platform.services.app_settings_service import AppSettingsValidationError

        from tests.app_test_support import build_local_state_application
        app = build_local_state_application()
        app._cost_statistics_api_routes._app_settings_service = self.scope_service()
        path = "/api/cost-statistics/project-cost-scope"
        response = app.handle_request("GET",path)
        self.assertEqual(response.status_code,200,response.body)
        current = json.loads(response.body)
        self.assertTrue(current["can_save"])
        self.assertIn("internal_transfer",{tag["code"] for tag in current["available_tags"]})
        for payload in ({"expected_version":True,"selected_tag_codes":[]},
                        {"expected_version":1,"selected_tag_codes":["unknown-code"]},
                        {"expected_version":1,"selected_tag_codes":["uncategorized","uncategorized"]}):
            response=app.handle_request("PUT",path,body=json.dumps(payload))
            self.assertEqual(response.status_code,400,response.body)
            self.assertEqual(json.loads(response.body)["error"],"invalid_project_cost_scope")
        def write(codes):
            try:
                return self.scope_service().update_project_cost_scope({"expected_version":1,"selected_tag_codes":codes},actor_id="test")["version"]
            except AppSettingsValidationError as exc:
                return exc.error_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(write,[[],["internal_transfer"]]))
        self.assertCountEqual(results,[2,"project_cost_scope_version_conflict"])
        response=app.handle_request("PUT",path,body=json.dumps({"expected_version":1,"selected_tag_codes":[]}))
        self.assertEqual(response.status_code,409,response.body)
        self.assertEqual(json.loads(response.body)["error"],"project_cost_scope_version_conflict")
        app._cost_statistics_api_routes._resolve_write_session=lambda headers:(None,app._json_response(403,{"error":"forbidden"}))
        self.assertFalse(json.loads(app.handle_request("GET",path).body)["can_save"])
        self.assertEqual(app.handle_request("PUT",path,body=json.dumps({"expected_version":2,"selected_tag_codes":[]})).status_code,403)

    def test_scope_migration_and_generic_settings_writers_preserve_empty_choice(self):
        from pathlib import Path

        from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
        service = self.scope_service()
        old = self.connection.fetch_one("select settings_payload from app.app_settings")["settings_payload"]
        service.update_project_cost_scope({"expected_version":1,"selected_tag_codes":[]},actor_id="cost-test")
        repo = PostgresOpsTaxEtcRepository(self.connection)
        repo.save_settings("app_settings", {**old,"completed_project_ids":["p1"]})
        with self.connection.transaction() as tx:
            repo.replace_normalized_app_settings_in_transaction(old, transaction=tx)
            tx.execute(Path("backend/src/fin_ops_platform/postgres/migrations/0170_cost_statistics_project_cost_scope.sql").read_text())
        self.assertEqual(service.get_project_cost_scope(can_save=True)["selected_tag_codes"],[])
        row = self.connection.fetch_one("select settings_payload,raw_payload from app.app_settings")
        self.assertEqual(row["settings_payload"],row["raw_payload"]["normalized_payload"])

    def test_internal_transfer_projection_has_primary_without_fake_sub_label(self):
        self.connection.execute("""insert into app.bank_transaction_categories
            (bank_transaction_id, legacy_transaction_id, category, source, status, raw_payload)
            select id,legacy_mongo_id,'internal_transfer','manual','active','{"manual_assignment":true}'::jsonb
            from app.bank_transactions where legacy_mongo_id='bank-1'""")
        rows = self.repository.load_relation_snapshot("cost-source-case")["bank_rows"]
        row = next(row for row in rows if row["id"] == "bank-1")
        self.assertEqual(row["bank_tag_code"],"internal_transfer")
        self.assertEqual(row["bank_tag_primary_label"],"内部往来款")
        self.assertEqual(row["bank_tag_sub_label"],"")
        self.assertEqual(row["bank_tag_label_path"],["内部往来款"])

    def exclude_second_source(self):
        self.connection.execute("""insert into app.bank_transaction_categories
            (bank_transaction_id,legacy_transaction_id,category,source,status,raw_payload)
            select id,legacy_mongo_id,'internal_transfer','manual','active','{"manual_assignment":true}'::jsonb
            from app.bank_transactions where legacy_mongo_id='bank-2'""")

    def test_manual_scope_version_http_contract_rejects_invalid_and_stale_versions(self):
        from tests.app_test_support import build_local_state_application
        app = build_local_state_application()
        app._cost_statistics_api_routes._manual_allocation_service = self.service  # noqa: SLF001
        path = "/api/cost-statistics/manual-allocations/cost-source-case"
        payload = self.payload()
        for value in (None, True, 0, "1"):
            invalid = {**payload, "scope_version": value}
            response = app.handle_request("PUT",path,body=json.dumps(invalid))
            self.assertEqual(response.status_code,400)
            self.assertEqual(json.loads(response.body)["error"],"invalid_cost_statistics_manual_allocation")
        self.scope_service().update_project_cost_scope({"expected_version":1,"selected_tag_codes":[]},actor_id="cost-test")
        response = app.handle_request("PUT",path,body=json.dumps(payload))
        self.assertEqual(response.status_code,409)
        self.assertEqual(json.loads(response.body)["error"],"cost_statistics_manual_allocation_conflict")
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.cost_statistics_manual_allocations")["n"],0)

    def test_legacy_unknown_sources_cannot_be_overwritten_by_a_scoped_save(self):
        self.save(self.payload())
        self.connection.execute("update app.cost_statistics_manual_allocations set source_allocations=null")
        self.exclude_second_source()
        payload = self.current_payload()
        payload["allocations"] = [{"unit_id":"oa:oa-a","amount":"500.00"},{"unit_id":"oa:oa-b","amount":"0.00"}]
        payload["source_allocations"] = {"cost_lines":[{"unit_id":"oa:oa-a","bank_transaction_id":"bank-1","amount":"500.00"}],"refund_links":[],"non_cost_lines":[]}
        with self.assertRaisesRegex(CostStatisticsManualAllocationValidationError,"历史分配缺少逐笔来源"):
            self.save(payload)
        record = PostgresCostStatisticsManualAllocationRepository(self.connection).list_by_case_ids(["cost-source-case"])["cost-source-case"]
        self.assertEqual(record["version"],1)
        self.assertEqual(record["net_outflow_total"],"1000.00")

    def current_payload(self):
        task = self.service.get_task("cost-source-case", can_save=True)
        return {"relation_case_id": task["relation_case_id"], "expected_version": task["version"],
                "scope_version": task["scope_version"], "source_fingerprint": task["source_fingerprint"],
                "allocations": task["allocations"], "source_allocations": task["source_allocations"],
                "non_cost_amount": task["non_cost_amount"], "non_cost_reason": task["non_cost_reason"]}

    def test_scoped_save_retains_outside_history_then_reenable_restores(self):
        original = self.save(self.payload())
        self.exclude_second_source()
        task = self.service.get_task("cost-source-case", can_save=True)
        self.assertEqual([e["transaction_id"] for e in task["bank_events"]], ["bank-1"])
        self.assertEqual([u["unit_id"] for u in task["units"]], ["oa:oa-a"])
        self.assertEqual(task["net_outflow_total"], "500.00")
        self.save(self.current_payload())
        stored = PostgresCostStatisticsManualAllocationRepository(self.connection).list_by_case_ids(["cost-source-case"])["cost-source-case"]
        self.assertCountEqual(stored["source_allocations"]["cost_lines"], original["source_allocations"]["cost_lines"])
        self.scope_service().update_project_cost_scope({"expected_version":1,"selected_tag_codes":["uncategorized","internal_transfer"]},actor_id="cost-test")
        restored = self.service.get_task("cost-source-case", can_save=True)
        self.assertEqual(restored["status"], original["status"])
        self.assertEqual(restored["pending_reasons"], original["pending_reasons"])
        self.assertCountEqual(restored["source_allocations"]["cost_lines"], original["source_allocations"]["cost_lines"])
        for view in ("project","cost_tag","bank_account"):
            self.assertEqual(self.query.get_explorer_page(scope="all",view=view,filters={},cursor=None,page_size=20)["summary"]["total_amount"], "1000.00")

    def test_first_scoped_save_keeps_known_cost_after_reenable_requires_new_source(self):
        self.exclude_second_source()
        payload = self.current_payload()
        payload["allocations"] = [{"unit_id":"oa:oa-a","amount":"500.00"},{"unit_id":"oa:oa-b","amount":"0.00"}]
        payload["source_allocations"] = {"cost_lines":[{"unit_id":"oa:oa-a","bank_transaction_id":"bank-1","amount":"500.00"}],"refund_links":[],"non_cost_lines":[]}
        self.save(payload)
        self.scope_service().update_project_cost_scope({"expected_version":1,"selected_tag_codes":["uncategorized","internal_transfer"]},actor_id="cost-test")
        task = self.service.get_task("cost-source-case", can_save=True)
        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["pending_reasons"], ["source_required"])
        self.assertEqual(len(task["bank_events"]), 2)
        self.assertEqual(self.query.get_explorer_page(scope="all",view="project",filters={},cursor=None,page_size=20)["summary"]["total_amount"], "500.00")

    def test_scope_version_conflict_rejects_old_draft_without_write(self):
        payload = self.payload()
        self.scope_service().update_project_cost_scope({"expected_version":1,"selected_tag_codes":[]},actor_id="cost-test")
        with self.assertRaisesRegex(CostStatisticsManualAllocationConflictError,"范围已变化"):
            self.save(payload)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.cost_statistics_manual_allocations")["n"],0)

    def test_forged_outside_source_is_rejected_and_scope_merge_rolls_back_with_audit(self):
        self.save(self.payload())
        self.exclude_second_source()
        payload = self.current_payload()
        payload["source_allocations"]["cost_lines"][0]["bank_transaction_id"] = "bank-2"
        with self.assertRaises(CostStatisticsManualAllocationValidationError):
            self.save(payload)
        payload = self.current_payload()
        with patch.object(PostgresOperationsAuditRepository,"append_operation_event",side_effect=RuntimeError("audit failure")):
            with self.assertRaisesRegex(RuntimeError,"audit failure"):
                self.save(payload)
        self.assertEqual(self.service.get_task("cost-source-case",can_save=True)["version"],1)

    def payload(self):
        task = self.service.get_task("cost-source-case", can_save=True)
        return {"relation_case_id": task["relation_case_id"], "expected_version": task["version"],
                "source_fingerprint": task["source_fingerprint"], "scope_version": task["scope_version"], "allocations": task["allocations"],
                "non_cost_amount": "0.00", "non_cost_reason": "", "source_allocations": {
                    "cost_lines": [{"unit_id": "oa:oa-a", "bank_transaction_id": "bank-1", "amount": "500.00"},
                                   {"unit_id": "oa:oa-a", "bank_transaction_id": "bank-2", "amount": "100.00"},
                                   {"unit_id": "oa:oa-b", "bank_transaction_id": "bank-2", "amount": "400.00"}],
                    "refund_links": [], "non_cost_lines": []}}

    def save(self, payload):
        return self.service.save("cost-source-case", payload, actor={"id": "cost-test-actor"})

    def test_missing_approval_time_keeps_manual_save_and_payment_year_reads(self):
        self.connection.execute("""update app.oa_applications set approved_at=null,
            application_date='2025-12-20', scope_month='2025-12-01'""")
        payload = self.payload()
        saved = self.save(payload)
        self.assertEqual(saved["source_allocations"], payload["source_allocations"])
        snapshot = self.repository.load_snapshot(scope_kind="year", scope_value="2026")
        from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy
        rows = CostStatisticsPolicy(snapshot).serialized_cost_rows
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["oa_completed_at"] for row in rows}, {""})
        for view in ("project", "bank_account", "cost_tag"):
            for scope, amount in (("year:2025", "0.00"), ("year:2026", "1000.00"),
                                  ("2026-08", "500.00"), ("2026-09", "500.00")):
                page = self.query.get_explorer_page(scope=scope, view=view, filters={}, cursor=None, page_size=20)
                self.assertEqual(page["summary"]["total_amount"], amount)
        detail = self.query.get_allocation_detail(allocation_id=rows[0]["allocation_id"], view="project", scope="year:2026")
        self.assertEqual(detail["allocation"]["oa_completed_at"], "")
        self.assertEqual(detail["allocation"]["amount"], rows[0]["amount"])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.oa_applications where approved_at is not null")["n"], 0)

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
