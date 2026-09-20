import json
import unittest
from unittest.mock import patch

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_repositories.workbench_formal_relation import (
    PostgresWorkbenchFormalRelationFactRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_idempotency import PostgresWorkbenchIdempotencyRepository
from fin_ops_platform.services.postgres_repositories.workbench_page_query import PostgresWorkbenchPageQueryRepository
from fin_ops_platform.services.runtime_worker_handlers import WorkbenchMatchingWorkerFactory
from fin_ops_platform.services.workbench_free_matching_engine import WorkbenchFreeMatchingEngine
from fin_ops_platform.services.workbench_matching_orchestrator import WorkbenchMatchingOrchestrator
from fin_ops_platform.services.workbench_uow import WorkbenchWriteUnitOfWork

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class EtcFormalMatchingPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.addCleanup(truncate_test_database, self.database_url)
        self.facts = PostgresWorkbenchFormalRelationFactRepository(self.connection)
        self.orchestrator = WorkbenchMatchingOrchestrator(
            fact_repository=self.facts, matcher=WorkbenchFreeMatchingEngine(),
            relation_uow=WorkbenchWriteUnitOfWork(
                connection=self.connection,
                repository_factory=WorkbenchMatchingWorkerFactory._workbench_uow_repository_factory,
                idempotency_store=PostgresWorkbenchIdempotencyRepository(self.connection),
            ), bank_flow_rule_tag_rules_payload=lambda: {'rules': []},
        )
        self.paths = [f'/fileManager/2026/09/15/invoice-{i}.pdf' for i in range(47)]
        payload = {'id': 'oa-etc-source', 'apply_type': '支付申请', 'counterparty_name': '刘树刚',
                   'workflow_status': 'in_progress', 'amount': '1711.33',
                   'detail_fields': {'申请日期': '2026-09-15'}, 'source_attachment_paths': self.paths}
        self.connection.execute('''insert into app.oa_pending_payment_admissions
            (tenant_id, scope_key, oa_id, workflow_status, applicant, project_name, project_name_display,
             amount, source_signature, source_payload, raw_payload)
            values ('default','2026-09','oa-etc-source','in_progress','申请人','项目','项目',1711.33,'sig',%s::jsonb,'{}')''', (json.dumps(payload),))
        self.batch_payload = {'business_batch_id': 'batch-source', 'external_etc_batch_id': 'etc-source',
                         'status': 'manually_marked_submitted', 'version': 1,
                         'oa_draft_id': 'draft-different-from-formal-id', 'oa_attachment_paths': self.paths,
                         'invoice_ids': [f'etc-invoice-{i}' for i in range(47)]}
        self.connection.execute('''insert into app.etc_business_batches
            (business_batch_id,status,scope_month,invoice_count,total_amount,raw_payload)
            values ('batch-source','manually_marked_submitted','2026-07-01',47,1711.33,%s::jsonb)''',
            (json.dumps({'normalized_payload': self.batch_payload}),))
        for i in range(47):
            amount = '55.33' if i == 46 else '36'
            self.connection.execute('''insert into app.etc_invoices
                (etc_invoice_id,business_batch_id,status,invoice_no,invoice_date,seller_name,amount,tax_amount,total_with_tax,raw_payload)
                values (%s,'batch-source','submitted',%s,'2026-07-31','公路公司',%s,0,%s,'{}')''',
                (f'etc-invoice-{i}', f'ETC-NO-{i}', amount, amount))

    def add_bank(self):
        self.connection.execute('''insert into app.bank_transactions
            (legacy_mongo_id,account_no,account_name,txn_direction,counterparty_name_raw,normalized_counterparty_name,
             amount,signed_amount,txn_date,txn_month,status,currency,summary,remark,raw_payload)
            values ('txn-etc-source','8106','公司','outflow','刘树刚','刘树刚',1711.33,-1711.33,
                    '2026-09-14','2026-09-01','active','CNY','电子转账','ETC还款','{}')''')

    def run_match(self, request_id='test-etc'):
        return self.orchestrator.run(changed_scope_months=['2026-09'], reason='test', request_id=request_id)

    def test_attachment_source_creates_case_then_bank_extends_same_case_and_get_is_paired(self):
        candidates = self.facts.load_etc_batch_link_candidates(['2026-09'])
        self.assertEqual(len(candidates), 1)
        result = self.run_match()
        self.assertEqual(result['created_relation_count'], 1)
        initial = self.connection.fetch_one("select case_id,row_ids,row_types from app.workbench_pair_relations where status='active'")
        self.assertEqual(set(initial['row_types']), {'oa', 'invoice'})
        self.add_bank()
        result = self.run_match('late-bank')
        self.assertEqual(result['extended_relation_count'], 1)
        current = self.connection.fetch_one("select case_id,row_ids,row_types,version from app.workbench_pair_relations where status='active'")
        self.assertEqual(initial['case_id'], current['case_id'])
        self.assertEqual(set(current['row_ids']), {'oa-etc-source','txn-etc-source','etc-summary-etc-source'})
        page = PostgresWorkbenchPageQueryRepository(self.connection, tenant_id='default').get_workbench_initial_page(scope_key='2026-09')
        self.assertEqual(page['paired']['total'], 1)
        self.assertEqual(page['unpaired']['total'], 0)
        group = page['paired']['groups'][0]
        self.assertEqual(group['oa_rows'][0]['workflow_status'], 'in_progress')
        batch = self.connection.fetch_one("select raw_payload from app.etc_business_batches where business_batch_id='batch-source'")
        self.assertEqual(batch['raw_payload']['normalized_payload']['oa_row_id'], 'oa-etc-source')
        replay = self.run_match('replay')
        self.assertEqual(replay['created_relation_count'], 0)
        self.assertEqual(replay['extended_relation_count'], 0)
        unchanged = self.connection.fetch_one("select version from app.workbench_pair_relations where status='active'")
        self.assertEqual(unchanged['version'], current['version'])
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.invoices')['n'], 0)

    def test_pending_oa_main_and_historical_reads_have_identical_fact_contract(self):
        self.connection.execute("""update app.oa_pending_payment_admissions
            set source_payload = source_payload || %s::jsonb""", (json.dumps({
                'workflow_no': 'OA-PAY-SOURCE-20260915', 'project_id': 'PROJECT-ETC', 'currency': '',
            }),))
        candidates = self.facts.load_etc_batch_link_candidates(['2026-09'])
        current = self.facts.load_batch(['2026-09'], etc_batch_link_candidates=candidates)
        historical = self.facts.load_batch(['2026-07'], etc_batch_link_candidates=candidates)
        oa = next(fact for fact in current.facts if fact.row_type == 'oa')
        self.assertEqual(oa, next(fact for fact in historical.facts if fact.row_type == 'oa'))
        self.assertEqual(oa.currency, 'CNY')
        self.assertIn(('business_reference', 'oapaysource20260915'), oa.evidence_keys)
        self.assertIn(('project_reference', 'projectetc'), oa.evidence_keys)
        self.add_bank()
        self.assertEqual(self.run_match()['created_relation_count'], 1)

    def test_audit_failure_rolls_back_relation_and_source_binding(self):
        self.add_bank()
        original = PostgresOpsTaxEtcRepository.bind_etc_oa_sources
        def failed_binding(repository, links, *, actor_id):
            original(repository, links, actor_id=actor_id)
            raise RuntimeError('source audit unavailable')
        with patch.object(PostgresOpsTaxEtcRepository, 'bind_etc_oa_sources', failed_binding):
            with self.assertRaisesRegex(RuntimeError, 'source audit unavailable'):
                self.run_match('fail')
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.workbench_pair_relations')['n'], 0)
        batch = self.connection.fetch_one("select raw_payload from app.etc_business_batches where business_batch_id='batch-source'")
        self.assertNotIn('oa_source_binding', batch['raw_payload']['normalized_payload'])
        result = self.run_match('retry')
        self.assertEqual(result['created_relation_count'], 1)

    def test_partial_attachment_overlap_cannot_authorize_source(self):
        self.connection.execute("update app.oa_pending_payment_admissions set source_payload=jsonb_set(source_payload,'{source_attachment_paths}',%s::jsonb)", (json.dumps(self.paths[:-1]),))
        self.assertEqual(self.facts.load_etc_batch_link_candidates(['2026-09']), [])

    def test_submission_dirty_scopes_commit_atomically_and_stale_version_writes_nothing(self):
        repository = PostgresOpsTaxEtcRepository(self.connection)
        payload = {**self.batch_payload, 'version': 2, 'created_at': '2026-09-15T00:00:00Z', 'invoice_ids': []}
        snapshot = {'business_batches': {'batch-source': payload}}
        self.assertFalse(repository.save_etc_oa_draft_attempt(snapshot, business_batch_id='batch-source', expected_version=99))
        self.assertEqual(self.connection.fetch_one('select count(*) n from job.workbench_matching_dirty_scopes')['n'], 0)
        self.assertTrue(repository.save_etc_oa_draft_attempt(snapshot, business_batch_id='batch-source', expected_version=1))
        dirty = self.connection.fetch_all("select to_char(scope_month, 'YYYY-MM') as scope_key from job.workbench_matching_dirty_scopes")
        self.assertEqual([row['scope_key'] for row in dirty], ['2026-09'])
        self.assertEqual(self.connection.fetch_one("select version from app.etc_business_batches where business_batch_id='batch-source'")['version'], 2)

    def test_facts_changed_between_plan_and_commit_roll_back_all_writes(self):
        original = self.orchestrator._matcher.plan_relations
        def plan_then_change(*args, **kwargs):
            result = original(*args, **kwargs)
            self.connection.execute("update app.oa_pending_payment_admissions set amount=1800, updated_at=clock_timestamp()")
            return result
        with patch.object(self.orchestrator._matcher, 'plan_relations', plan_then_change):
            with self.assertRaisesRegex(ValueError, 'facts changed'):
                self.run_match('stale')
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.workbench_pair_relations')['n'], 0)
        self.assertEqual(self.connection.fetch_one('select version from app.etc_business_batches')['version'], 1)

    def test_multiple_source_batches_share_case_without_overwriting_metadata(self):
        second = {**self.batch_payload, 'business_batch_id': 'batch-second', 'external_etc_batch_id': 'etc-second',
                  'oa_attachment_paths': [self.paths[0]]}
        self.connection.execute('''insert into app.etc_business_batches
            (business_batch_id,status,scope_month,invoice_count,total_amount,raw_payload)
            values ('batch-second','manually_marked_submitted','2026-07-01',1,36,%s::jsonb)''',
            (json.dumps({'normalized_payload': second}),))
        self.connection.execute("""insert into app.etc_invoices
            (etc_invoice_id,business_batch_id,status,invoice_no,invoice_date,seller_name,amount,tax_amount,total_with_tax,raw_payload)
            values ('second-invoice','batch-second','submitted','SECOND-NO','2026-07-31','公路公司',36,0,36,'{}')""")
        self.run_match('two-batches')
        relation = self.connection.fetch_one("select row_ids,special_metadata from app.workbench_pair_relations where status='active'")
        self.assertEqual(set(relation['row_ids']), {'oa-etc-source','etc-summary-etc-source','etc-summary-etc-second'})
        self.assertEqual({item['external_etc_batch_id'] for item in relation['special_metadata']['etc_batch_links']}, {'etc-source','etc-second'})
        self.add_bank()
        self.run_match('two-batches-bank')
        relation = self.connection.fetch_one("select row_ids,special_metadata from app.workbench_pair_relations where status='active'")
        self.assertEqual(len(relation['row_ids']), 4)
        self.assertEqual(len(relation['special_metadata']['etc_batch_links']), 2)
        page = PostgresWorkbenchPageQueryRepository(self.connection, tenant_id='default').get_workbench_initial_page(scope_key='2026-09')
        self.assertEqual(page['paired']['total'], 0)  # The additional batch creates a real invoice amount difference.
        group = page['unpaired']['groups'][0]
        expected_ids = {'etc-summary-etc-source', 'etc-summary-etc-second'}
        self.assertEqual({row['id'] for row in group['invoice_rows']}, expected_ids)
        detail = PostgresWorkbenchPageQueryRepository(self.connection, tenant_id='default').get_workbench_group_detail(
            scope_key='2026-09', zone='unpaired', group_id=group['group_id'], detail_key=group['detail_key'],
        )
        self.assertEqual({row['id'] for row in detail['group']['invoice_rows']}, expected_ids)

    def test_dirty_queue_failure_rolls_back_submitted_owner_write(self):
        from fin_ops_platform.services.postgres_repositories.workbench_matching_queue import (
            PostgresWorkbenchMatchingQueueRepository,
        )
        snapshot = {'business_batches': {'batch-source': {**self.batch_payload, 'version': 2, 'created_at': '2026-09-15', 'invoice_ids': []}}}
        with patch.object(PostgresWorkbenchMatchingQueueRepository, 'mark_workbench_matching_dirty_scopes_in_transaction', side_effect=RuntimeError('queue unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'queue unavailable'):
                PostgresOpsTaxEtcRepository(self.connection).save_etc_oa_draft_attempt(snapshot, business_batch_id='batch-source', expected_version=1)
        self.assertEqual(self.connection.fetch_one('select version from app.etc_business_batches')['version'], 1)
        self.assertEqual(self.connection.fetch_one('select count(*) n from job.workbench_matching_dirty_scopes')['n'], 0)

    def test_concurrent_matchers_create_one_relation_and_one_source_audit(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2)
        original = self.orchestrator._matcher.plan_relations
        def concurrent_plan(*args, **kwargs):
            result = original(*args, **kwargs)
            barrier.wait(timeout=10)
            return result
        with patch.object(self.orchestrator._matcher, 'plan_relations', concurrent_plan), ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.run_match, ['parallel-1', 'parallel-2']))
        self.assertEqual(results[0]['relation_ids'], results[1]['relation_ids'])
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.workbench_pair_relation_history')['n'], 1)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.workbench_pair_relations where status='active'")['n'], 1)
        batch = self.connection.fetch_one('select audit_events from app.etc_business_batches')
        self.assertEqual(len([event for event in batch['audit_events'] if event['event_type']=='oa_source_bound']), 1)
