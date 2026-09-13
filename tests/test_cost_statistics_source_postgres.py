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

    def test_relation_without_cost_members_is_not_a_detail_task(self):
        self.connection.execute("update app.workbench_pair_relations set row_ids=array['bank-1','bank-2'], row_types=array['bank','bank'] where case_id='cost-source-case'")
        with self.assertRaises(KeyError):
            self.service.get_task("cost-source-case", can_save=True)

    def test_mixed_status_partial_http_save_completion_and_withdrawal(self):
        from tests.app_test_support import build_local_state_application
        app = build_local_state_application()
        app._cost_statistics_api_routes._manual_allocation_service = self.service  # noqa: SLF001
        app._cost_statistics_api_routes._query_service = self.query  # noqa: SLF001
        path = "/api/cost-statistics/manual-allocations/cost-source-case"
        self.connection.execute("update app.oa_applications set workflow_status='in_progress' where row_id='oa-b'")
        task = json.loads(app.handle_request('GET', path).body)
        self.assertTrue(task['allows_partial'])
        self.assertEqual(task['waiting_oa_ids'], ['oa-b'])
        self.assertIsNone(task['source_allocations'])
        payload = self.payload()
        payload['allocations'] = [{'unit_id': 'oa:oa-a', 'amount': '600.00'}, {'unit_id': 'oa:oa-b', 'amount': '0.00'}]
        payload['source_allocations']['cost_lines'].pop()
        saved = app.handle_request('PUT', path, body=json.dumps(payload))
        self.assertEqual(saved.status_code, 200, saved.body)
        result = json.loads(saved.body)
        self.assertEqual(result['unallocated_amount'], '400.00')
        self.assertIn('oa_in_progress', result['pending_reasons'])
        for view in ('project', 'cost_tag', 'bank_account'):
            response = app.handle_request('GET', f'/api/cost-statistics/explorer?view={view}&scope=all')
            self.assertEqual(response.status_code, 200, response.body)
            self.assertEqual(json.loads(response.body)['summary']['total_amount'], '600.00')
        repeat = app.handle_request('PUT', path, body=json.dumps(payload))
        self.assertEqual(repeat.status_code, 409, repeat.body)
        self.connection.execute("update app.oa_applications set workflow_status='completed' where row_id='oa-b'")
        reloaded = json.loads(app.handle_request('GET', path).body)
        self.assertEqual(reloaded['waiting_oa_ids'], [])
        self.assertEqual(reloaded['source_allocations'], payload['source_allocations'])
        self.assertEqual(reloaded['unallocated_amount'], '400.00')
        completed_payload = self.payload()
        completed_payload['allocations'] = [{'unit_id': 'oa:oa-a', 'amount': '600.00'}, {'unit_id': 'oa:oa-b', 'amount': '400.00'}]
        response = app.handle_request('PUT', path, body=json.dumps(completed_payload))
        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(json.loads(response.body)['unallocated_amount'], '0.00')
        for view in ('project', 'cost_tag', 'bank_account'):
            response = app.handle_request('GET', f'/api/cost-statistics/explorer?view={view}&scope=all')
            self.assertEqual(json.loads(response.body)['summary']['total_amount'], '1000.00')
        # Current approval state is re-read even though it is not a financial identity change.
        self.connection.execute("update app.oa_applications set workflow_status='in_progress' where row_id='oa-b'")
        response = app.handle_request('GET', '/api/cost-statistics/explorer?view=project&scope=all')
        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(json.loads(response.body)['summary']['total_amount'], '600.00')
        self.connection.execute("update app.workbench_pair_relations set status='withdrawn',version=version+1 where case_id='cost-source-case'")
        response = app.handle_request('GET', '/api/cost-statistics/explorer?view=project&scope=all')
        self.assertEqual(json.loads(response.body)['summary']['total_amount'], '0.00')
        response = app.handle_request('PUT', path, body=json.dumps(completed_payload))
        self.assertEqual(response.status_code, 409, response.body)

    def test_mixed_status_reads_admission_fact_without_importing_it_as_completed(self):
        from fin_ops_platform.services.postgres_repositories.oa_pending_payment_admission import PostgresOaPendingPaymentAdmissionRepository
        self.connection.execute("delete from app.oa_applications where row_id='oa-b'")
        PostgresOaPendingPaymentAdmissionRepository(self.connection).replace_scope(scope_key='2026-08', records=[{
            'id': 'oa-b', 'apply_type': '支付申请', 'workflow_status': 'in_progress', 'amount': '400.00',
            'project_name': '测试项目', 'expense_type': '原OA分类', 'expense_content': '测试采购', 'applicant': '测试申请人',
            'month': '2026-08', 'section': 'unmatched', 'case_id': None, 'counterparty_name': '供应商',
            'reason': '测试采购', 'relation_code': 'unmatched', 'relation_label': '未配对', 'relation_tone': 'warning',
        }])
        task = self.service.get_task('cost-source-case', can_save=True)
        self.assertEqual({u['oa_id']: u['cost_eligible'] for u in task['units']}, {'oa-a': True, 'oa-b': False})
        pending = self.service.list_tasks(cursor=None, page_size=20, status='pending', query=None, can_save=True)
        self.assertEqual(len(pending['items']), 1)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.oa_applications")['n'], 1)

    def test_pending_oa_cannot_be_saved_or_use_its_explicit_source(self):
        self.connection.execute("update app.oa_applications set workflow_status='in_progress' where row_id='oa-b'")
        payload = self.payload()
        payload['allocations'] = [{'unit_id': 'oa:oa-a', 'amount': '600.00'}, {'unit_id': 'oa:oa-b', 'amount': '400.00'}]
        with self.assertRaises(CostStatisticsManualAllocationValidationError):
            self.save(payload)
        self.connection.execute("update app.bank_transactions set raw_payload=jsonb_build_object('source_oa_row_id','oa-b') where legacy_mongo_id='bank-2'")
        payload = self.payload()
        payload['allocations'] = [{'unit_id': 'oa:oa-a', 'amount': '600.00'}, {'unit_id': 'oa:oa-b', 'amount': '0.00'}]
        payload['source_allocations']['cost_lines'].pop()
        with self.assertRaises(CostStatisticsManualAllocationValidationError):
            self.save(payload)
        self.assertEqual(self.connection.fetch_one('select count(*) as n from app.cost_statistics_manual_allocations')['n'], 0)

    def test_formal_history_display_is_current_and_independent_of_cost_save(self):
        current = {"case_id":"cost-source-case", "row_ids":["oa-a","oa-b","bank-1","bank-2"], "row_types":["oa","oa","bank","bank"]}
        prior = [{"case_id":"old-a", "row_ids":["oa-a","bank-2"], "row_types":["oa","bank"]},
                 {"case_id":"old-b", "row_ids":["oa-b","bank-1"], "row_types":["oa","bank"]}]
        history = {"operation_type":"confirm_link", "after_relations":[current], "before_relations":prior}
        self.connection.execute("insert into app.workbench_pair_relation_history(case_id,event_type,raw_payload) values (%s,'confirm_link',%s::jsonb)", ("cost-source-case",json.dumps(history)))
        task = self.service.get_task("cost-source-case",can_save=True)
        expected = [{"unit_ids":["oa:oa-a"],"bank_transaction_ids":["bank-2"],"sources_excluded":False},
                    {"unit_ids":["oa:oa-b"],"bank_transaction_ids":["bank-1"],"sources_excluded":False}]
        self.assertEqual(task["relation_display_groups"],expected)
        self.assertIsNone(task["source_allocations"])
        self.assertEqual(self.save(self.payload())["relation_display_groups"],expected)
        self.assertEqual(self.service.get_task("cost-source-case",can_save=True)["relation_display_groups"],expected)
        old_payload=self.payload()
        self.connection.execute("update app.workbench_pair_relations set status='cancelled',version=version+1 where case_id='cost-source-case'")
        with self.assertRaises(KeyError):
            self.service.get_task("cost-source-case",can_save=True)
        with self.assertRaises(CostStatisticsManualAllocationConflictError):
            self.save(old_payload)

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

    def test_duplicate_amount_history_prefill_http_save_reload_and_cancel(self):
        # Equal OA and bank amounts are ambiguous until the current merge history
        # supplies the two original OA/bank relations.
        self.connection.execute("update app.oa_applications set amount=500,normalized_payload=jsonb_set(normalized_payload,'{amount}','\"500.00\"'::jsonb)")
        self.assertIsNone(self.service.get_task("cost-source-case", can_save=True)["suggested_source_allocations"])
        current = {"case_id":"cost-source-case", "row_ids":["oa-a","oa-b","bank-1","bank-2"], "row_types":["oa","oa","bank","bank"]}
        prior = [{"case_id":"old-a", "row_ids":["oa-a","bank-2"], "row_types":["oa","bank"]},
                 {"case_id":"old-b", "row_ids":["oa-b","bank-1"], "row_types":["oa","bank"]}]
        history = {"operation_type":"confirm_link", "after_relations":[current], "before_relations":prior}
        self.connection.execute("insert into app.workbench_pair_relation_history(case_id,event_type,raw_payload) values (%s,'confirm_link',%s::jsonb)", ("cost-source-case",json.dumps(history)))
        from tests.app_test_support import build_local_state_application
        app = build_local_state_application()
        app._cost_statistics_api_routes._manual_allocation_service = self.service  # noqa: SLF001
        app._cost_statistics_api_routes._query_service = self.query  # noqa: SLF001
        path = '/api/cost-statistics/manual-allocations/cost-source-case'
        response = app.handle_request('GET', path)
        self.assertEqual(response.status_code, 200)
        task = json.loads(response.body)
        suggestion = task['suggested_source_allocations']
        self.assertEqual(suggestion['cost_lines'], [
            {'unit_id':'oa:oa-a','bank_transaction_id':'bank-2','amount':'500.00'},
            {'unit_id':'oa:oa-b','bank_transaction_id':'bank-1','amount':'500.00'},
        ])
        self.assertEqual(task['status'], 'pending')
        self.assertIsNone(task['source_allocations'])
        self.assertEqual(self.connection.fetch_one('select count(*) as n from app.cost_statistics_manual_allocations')['n'], 0)
        for block, line in zip(task['relation_display_groups'], suggestion['cost_lines'], strict=True):
            self.assertEqual(block['unit_ids'], [line['unit_id']])
            self.assertEqual(block['bank_transaction_ids'], [line['bank_transaction_id']])
        payload = {**self.payload(), 'allocations':task['allocations'], 'source_allocations':suggestion}
        response = app.handle_request('PUT', path, body=json.dumps(payload))
        self.assertEqual(response.status_code, 200, response.body)
        reloaded = json.loads(app.handle_request('GET', path).body)
        self.assertEqual(reloaded['source_allocations'], suggestion)
        self.assertIsNone(reloaded['suggested_source_allocations'])
        self.assertEqual(self.connection.fetch_one("select payload from audit.events where action='cost_statistics.manual_allocation.save'")['payload']['source_allocations'], suggestion)
        for view in ('project','cost_tag','bank_account'):
            response = app.handle_request('GET', f'/api/cost-statistics/explorer?view={view}&scope=all&page_size=20')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.body)['summary']['total_amount'], '1000.00')
        self.connection.execute("update app.workbench_pair_relations set status='cancelled',version=version+1 where case_id='cost-source-case'")
        self.assertEqual(app.handle_request('GET', path).status_code, 404)
        self.assertEqual(app.handle_request('PUT', path, body=json.dumps(payload)).status_code, 409)

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

    def manual_payload(self):
        with self.connection.transaction() as tx:
            tx.execute("select set_config('fin_ops.correction_reason', 'isolated supplemental cost fixture', true)")
            tx.execute("update app.bank_transactions set amount=1192,signed_amount=-1192 where legacy_mongo_id='bank-1'")
            tx.execute("update app.workbench_pair_relations set row_ids=array['oa-a','oa-b','bank-1'],row_types=array['oa','oa','bank']")
            tx.execute("""update app.app_settings set settings_payload=settings_payload || %s::jsonb""", (json.dumps({"bank_transaction_tags":{"definitions":[{"code":"manual-fee","label":"服务费","path":["费用","服务费"],"output_primary_label":"费用","output_sub_label":"服务费","status":"active","rules":{}}]}}),))
        task = self.service.get_task('cost-source-case', can_save=True)
        self.assertEqual(task['manual_options']['projects'], [{'id':'','name':'测试项目'}])
        suggestion = task['suggested_source_allocations']
        self.assertEqual([r['amount'] for r in suggestion['cost_lines']], ['600.00','400.00'])
        self.assertEqual(task['status'], 'pending')
        identity = 'manual:00000000-0000-4000-8000-000000000001'
        item = {'unit_id':identity,'project_name':'测试项目','expense_content':'人工补充测试费用','cost_tag_code':'manual-fee'}
        return {**self.payload(), 'manual_items':[item],
                'allocations':[{'unit_id':'oa:oa-a','amount':'600.00'},{'unit_id':'oa:oa-b','amount':'400.00'},{'unit_id':identity,'amount':'192.00'}],
                'source_allocations':{**suggestion,'cost_lines':[*suggestion['cost_lines'],{'unit_id':identity,'bank_transaction_id':'bank-1','amount':'192.00'}]}}

    def test_manual_tag_archived_after_read_rejects_new_item_and_preserves_saved_history(self):
        payload = self.manual_payload()
        self.connection.execute("update app.app_settings set settings_payload=jsonb_set(settings_payload, '{bank_transaction_tags,definitions,0,status}', '\"archived\"'::jsonb)")
        with self.assertRaises(CostStatisticsManualAllocationValidationError):
            self.save(payload)
        self.assertEqual(self.service.get_task('cost-source-case', can_save=True)['version'], 0)
        self.connection.execute("update app.app_settings set settings_payload=jsonb_set(settings_payload, '{bank_transaction_tags,definitions,0,status}', '\"active\"'::jsonb)")
        saved = self.save(payload)
        self.connection.execute("update app.app_settings set settings_payload=jsonb_set(settings_payload, '{bank_transaction_tags,definitions,0,status}', '\"archived\"'::jsonb)")
        task = self.service.get_task('cost-source-case', can_save=True)
        self.assertNotIn('manual-fee', [tag['code'] for tag in task['manual_options']['tags']])
        self.assertEqual(task['manual_items'], saved['manual_items'])

    def test_manual_cost_http_save_reload_views_export_and_fact_isolation(self):
        from tests.app_test_support import build_local_state_application
        payload = self.manual_payload()
        facts_before = self.connection.fetch_all('select row_id,normalized_payload from app.oa_applications order by row_id')
        relation_before = self.connection.fetch_one('select row_ids,row_types,version from app.workbench_pair_relations')
        banks_before = self.connection.fetch_all('select id,amount,signed_amount,raw_payload from app.bank_transactions order by id')
        app = build_local_state_application()
        app._cost_statistics_api_routes._manual_allocation_service = self.service  # noqa: SLF001
        app._cost_statistics_api_routes._query_service = self.query  # noqa: SLF001
        path='/api/cost-statistics/manual-allocations/cost-source-case'
        response=app.handle_request('PUT',path,body=json.dumps(payload))
        self.assertEqual(response.status_code,200,response.body)
        saved=json.loads(response.body)
        self.assertEqual(saved['manual_items'][0]['project_name'],'测试项目')
        self.assertEqual(saved['oa_total'],'1000.00')
        self.assertEqual(saved['net_outflow_total'],'1192.00')
        reloaded=json.loads(app.handle_request('GET',path).body)
        self.assertEqual(reloaded['manual_items'],saved['manual_items'])
        self.assertEqual(reloaded['source_allocations'],payload['source_allocations'])
        for view in ('project','cost_tag','bank_account'):
            page=self.query.get_explorer_page(scope='all',view=view,filters={},cursor=None,page_size=20)
            self.assertEqual(page['summary']['total_amount'],'1192.00')
            details_page=self.query.get_explorer_page(scope='all',view=view,filters={'project_name':'测试项目','bank_account_label':self.repository.load_relation_snapshot('cost-source-case')['bank_rows'][0]['payment_account_label'], 'bank_tag_primary_key':'label:费用','bank_tag_sub_key':'label:服务费'},cursor=None,page_size=20)
            manual=next(r for r in details_page['rows'] if r['row_kind']=='manual_allocation')
            self.assertEqual(manual['amount'],'192.00')
            self.assertEqual(manual['bank_tag_sub_label'],'服务费')
            self.assertEqual(manual['transaction_id'],'bank-1')
            response=app.handle_request('GET',f"/api/cost-statistics/allocations/{manual['allocation_id']}?scope=all&view={view}")
            self.assertEqual(response.status_code,200,response.body)
            detail=json.loads(response.body)
            self.assertEqual(detail['kind'],'manual_allocation')
            self.assertIsNone(detail['allocation']['oa_original_amount'])
            self.assertEqual(detail['allocation']['oa_id'],'')
            self.assertEqual(detail['reconciliation']['difference'],'192.00')
        response=app.handle_request('GET','/api/cost-statistics/export-preview?month=2026-08&view=project&project_name=测试项目')
        self.assertEqual(response.status_code,200,response.body)
        self.assertIn('人工补充测试费用',response.body)
        self.assertIn('人工补充',response.body)
        for status in ('pending','allocated'):
            tasks=self.service.list_tasks(cursor=None,page_size=20,status=status,query='人工补充测试费用',can_save=True)
            if tasks['items']:
                self.assertEqual(tasks['items'][0]['relation_case_id'],'cost-source-case')
                break
        else:
            self.fail('manual cost content must be searchable')
        self.assertEqual(facts_before,self.connection.fetch_all('select row_id,normalized_payload from app.oa_applications order by row_id'))
        self.assertEqual(relation_before,self.connection.fetch_one('select row_ids,row_types,version from app.workbench_pair_relations'))
        self.assertEqual(banks_before,self.connection.fetch_all('select id,amount,signed_amount,raw_payload from app.bank_transactions order by id'))
        audit=self.connection.fetch_one("select payload from audit.events where action='cost_statistics.manual_allocation.save'")['payload']
        self.assertEqual(audit['manual_items'],saved['manual_items'])
        # Existing write permission remains authoritative for manual costs too.
        app._cost_statistics_api_routes._resolve_write_session=lambda headers:(None,app._json_response(403,{'error':'forbidden'}))
        self.assertEqual(app.handle_request('PUT',path,body=json.dumps(payload)).status_code,403)

    def test_manual_cost_invalid_metadata_sources_and_amounts_are_atomic(self):
        from copy import deepcopy
        good=self.manual_payload()
        for field,value in [('project_name','missing'),('cost_tag_code','missing'),('expense_content',''),('unit_id','oa:fake')]:
            payload=deepcopy(good);payload['manual_items'][0][field]=value
            with self.subTest(field=field), self.assertRaises(CostStatisticsManualAllocationValidationError):
                self.save(payload)
        for amount in ('0.00','-1.00','192.001','193.00'):
            payload=deepcopy(good);payload['source_allocations']['cost_lines'][-1]['amount']=amount
            with self.subTest(amount=amount), self.assertRaises(CostStatisticsManualAllocationValidationError):
                self.save(payload)
        payload=deepcopy(good);payload['source_allocations']['cost_lines'][-1]['bank_transaction_id']='bank-2'
        with self.assertRaises(CostStatisticsManualAllocationValidationError): self.save(payload)
        payload=deepcopy(good);payload['manual_items']*=2
        with self.assertRaises(CostStatisticsManualAllocationValidationError): self.save(payload)
        with patch.object(PostgresOperationsAuditRepository,'append_operation_event',side_effect=RuntimeError('audit failure')):
            with self.assertRaisesRegex(RuntimeError,'audit failure'): self.save(good)
        self.assertEqual(self.connection.fetch_one('select count(*) as n from app.cost_statistics_manual_allocations')['n'],0)

    def test_manual_cost_edit_delete_concurrency_scope_and_relation_lifecycle(self):
        from copy import deepcopy
        payload=self.manual_payload()
        saved=self.save(payload)
        with self.assertRaises(CostStatisticsManualAllocationConflictError): self.save(payload)
        edited=deepcopy(payload);edited['expected_version']=saved['version'];edited['manual_items'][0]['expense_content']='修改后的成本'
        edited_saved=self.save(edited)
        old_client=deepcopy(edited);old_client['expected_version']=edited_saved['version'];del old_client['manual_items']
        with self.assertRaises(CostStatisticsManualAllocationConflictError): self.save(old_client)
        scope=self.scope_service()
        scope.update_project_cost_scope({'expected_version':1,'selected_tag_codes':[]},actor_id='test')
        self.assertEqual(self.query.get_explorer_page(scope='all',view='project',filters={},cursor=None,page_size=20)['summary']['total_amount'],'0.00')
        scope.update_project_cost_scope({'expected_version':2,'selected_tag_codes':['uncategorized']},actor_id='test')
        restored=self.service.get_task('cost-source-case',can_save=True)
        self.assertEqual(restored['manual_items'][0]['expense_content'],'修改后的成本')
        deleted=deepcopy(edited);deleted.update(expected_version=restored['version'],scope_version=restored['scope_version'],manual_items=[],non_cost_amount='192.00',non_cost_reason='测试排除用途')
        deleted['allocations']=deleted['allocations'][:2]
        deleted['source_allocations']['cost_lines']=deleted['source_allocations']['cost_lines'][:2]
        deleted['source_allocations']['non_cost_lines']=[{'bank_transaction_id':'bank-1','amount':'192.00'}]
        self.save(deleted)
        self.assertEqual(self.service.get_task('cost-source-case',can_save=True)['manual_items'],[])
        self.assertEqual(self.query.get_explorer_page(scope='all',view='project',filters={},cursor=None,page_size=20)['summary']['total_amount'],'1000.00')
        self.connection.execute("update app.workbench_pair_relations set status='cancelled',version=version+1")
        self.assertEqual(self.query.get_explorer_page(scope='all',view='project',filters={},cursor=None,page_size=20)['summary']['total_amount'],'0.00')

    def test_manual_cost_scoped_edit_retains_other_source_metadata(self):
        from copy import deepcopy
        payload=self.manual_payload()
        with self.connection.transaction() as tx:
            tx.execute("select set_config('fin_ops.correction_reason', 'isolated split manual fixture', true)")
            tx.execute("update app.bank_transactions set amount=692,signed_amount=-692 where legacy_mongo_id='bank-1'")
            tx.execute("update app.workbench_pair_relations set row_ids=array['oa-a','oa-b','bank-1','bank-2'],row_types=array['oa','oa','bank','bank']")
        task=self.service.get_task('cost-source-case',can_save=True)
        first=payload['manual_items'][0]['unit_id']
        second='manual:00000000-0000-4000-8000-000000000002'
        payload.update(source_fingerprint=task['source_fingerprint'])
        payload['manual_items'].append({**payload['manual_items'][0],'unit_id':second,'expense_content':'第二笔补充'})
        payload['allocations']=[{'unit_id':u,'amount':a} for u,a in [('oa:oa-a','600.00'),('oa:oa-b','400.00'),(first,'92.00'),(second,'100.00')]]
        payload['source_allocations']['cost_lines']=[{'unit_id':u,'bank_transaction_id':b,'amount':a} for u,b,a in [('oa:oa-a','bank-1','600.00'),('oa:oa-b','bank-2','400.00'),(first,'bank-1','92.00'),(second,'bank-2','100.00')]]
        self.save(payload)
        self.exclude_second_source()
        current=self.service.get_task('cost-source-case',can_save=True)
        self.assertEqual([m['unit_id'] for m in current['manual_items']],[first])
        edit=deepcopy(payload)
        edit.update(expected_version=current['version'],scope_version=current['scope_version'],manual_items=[],allocations=[{'unit_id':'oa:oa-a','amount':'600.00'}],non_cost_amount='92.00',non_cost_reason='当前来源不计成本')
        edit['source_allocations']={'cost_lines':[payload['source_allocations']['cost_lines'][0]],'refund_links':[],'non_cost_lines':[{'bank_transaction_id':'bank-1','amount':'92.00'}]}
        self.save(edit)
        stored=PostgresCostStatisticsManualAllocationRepository(self.connection).list_by_case_ids(['cost-source-case'])['cost-source-case']
        self.assertEqual([m['unit_id'] for m in stored['manual_items']],[second])
        self.scope_service().update_project_cost_scope({'expected_version':1,'selected_tag_codes':['uncategorized','internal_transfer']},actor_id='test')
        restored=self.service.get_task('cost-source-case',can_save=True)
        self.assertEqual([m['unit_id'] for m in restored['manual_items']],[second])
        self.assertEqual(self.query.get_explorer_page(scope='all',view='project',filters={},cursor=None,page_size=20)['summary']['total_amount'],'1100.00')

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
