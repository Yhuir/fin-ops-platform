import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

from fin_ops_platform.services.input_invoice_usage_oa_reverse_service import (
    InputInvoiceUsageOaReverseBatch,
    InputInvoiceUsageOaReverseInvalidTransitionError,
    InputInvoiceUsageOaReverseService,
    InputInvoiceUsageOaReverseVersionConflictError,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.input_invoice_usage_oa_reverse import (
    PostgresInputInvoiceUsageOaReverseBatchRepository,
)

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class OaReverseOccupancyPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = require_postgres_test_database_url()
        apply_test_migrations(url)
        cls.connection = PostgresConnection(PostgresSettings(database_url=url, pool_enabled=False))

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def setUp(self):
        truncate_test_database(require_postgres_test_database_url())
        self.invoice = 'reverse-test-' + uuid4().hex
        self.connection.execute("""insert into app.invoices(legacy_mongo_id,invoice_type,invoice_no,
            amount,signed_amount,tax_amount,total_with_tax,status)
            values(%s,'input',%s,100,100,0,100,'pending')""", (self.invoice, self.invoice))
        self.repository = PostgresInputInvoiceUsageOaReverseBatchRepository(self.connection)

    def tearDown(self):
        truncate_test_database(require_postgres_test_database_url())

    def batch(self, suffix):
        return InputInvoiceUsageOaReverseBatch(
            batch_id='reverse-batch-' + suffix, status='draft', version=1,
            target_applicant_code='actual-user', target_applicant_name='真实申请人',
            invoice_ids=[self.invoice], preview_id='preview', preview_hash='hash',
            preview_summary={'totalWithTax': '100.00'}, invoice_display_rows=[],
            idempotency_key='reverse-key-' + suffix,
            audit_events=[{'eventType': 'oa_reverse_batch_created'}],
        )

    def test_concurrent_creators_lock_invoice_and_only_one_reserves_it(self):
        ready = Barrier(2)
        def create(suffix):
            ready.wait(timeout=5)
            try:
                self.repository.save_batch(self.batch(suffix))
                return 'created'
            except InputInvoiceUsageOaReverseInvalidTransitionError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create, ['first', 'second']))
        self.assertCountEqual(results, ['created', 'invoice_oa_reverse_occupied'])
        row = self.connection.fetch_one('select count(*) as count from app.input_invoice_usage_oa_reverse_batches')
        self.assertEqual(row['count'], 1)
        self.assertEqual(len(self.repository.invoice_occupancy([self.invoice])), 1)

    def test_release_allows_new_batch_and_failed_write_rolls_back(self):
        first = self.batch('first')
        self.repository.save_batch(first)
        self.repository.save_batch(first)
        with self.assertRaises(InputInvoiceUsageOaReverseInvalidTransitionError):
            self.repository.save_batch(self.batch('blocked'))
        self.assertIsNone(self.repository.get_batch('reverse-batch-blocked'))
        first.status = 'not_submitted'
        self.repository.save_batch(first)
        self.assertEqual(self.repository.invoice_occupancy([self.invoice]), {})
        second = self.batch('second')
        self.repository.save_batch(second)
        self.assertEqual(self.repository.invoice_occupancy([self.invoice])[self.invoice]['occupiedBatchId'], second.batch_id)

    def test_new_batch_rejects_an_oa_relation_committed_after_preview(self):
        self.connection.execute("""insert into app.workbench_pair_relations(case_id,relation_mode,status,row_ids,row_types)
            values('reverse-linked','manual_confirmed','active',%s,array['invoice','oa'])""", ([self.invoice, 'oa-test'],))
        with self.assertRaises(InputInvoiceUsageOaReverseInvalidTransitionError) as raised:
            self.repository.save_batch(self.batch('now-linked'))
        self.assertEqual(raised.exception.code, 'invalid_oa_reverse_selection')
        self.assertIsNone(self.repository.get_batch('reverse-batch-now-linked'))

    def test_transaction_failure_has_no_half_written_batch(self):
        batch = self.batch('failed')
        original = self.repository._save_batch
        def fail_after_write(tx, batch):
            original(tx, batch)
            raise RuntimeError('test rollback')
        self.repository._save_batch = fail_after_write
        with self.assertRaisesRegex(RuntimeError, 'test rollback'):
            self.repository.save_batch(batch)
        self.assertIsNone(self.repository.get_batch(batch.batch_id))
        self.assertEqual(self.repository.invoice_occupancy([self.invoice]), {})

    def service(self, client, *, loader_barrier=None):
        row = {
            'invoiceId': self.invoice, 'invoiceIdentityKey': 'identity:' + self.invoice,
            'invoice': {'invoiceNo': self.invoice, 'invoiceDate': '2026-09-28', 'sellerName': '供应商',
                        'sellerTaxNo': 'tax-test', 'totalWithTax': '100.00'},
            'usageStatus': 'unused', 'bankRelationStatus': 'unlinked', 'oa': {'relationCount': 0, 'summaries': []},
            'bankTransactions': {'relationCount': 0, 'summaries': []},
            'paymentStatus': {'code': 'pending', 'label': '待处理'},
        }
        def load(_ids):
            if loader_barrier is not None:
                loader_barrier.wait(timeout=5)
            return {'rows': [row]}
        service = InputInvoiceUsageOaReverseService(
            repository=self.repository, applicant_options_provider=lambda: [{'code': 'actual-user', 'name': '真实申请人'}],
            rows_by_invoice_ids_loader=load, oa_client=client,
        )
        batch = self.batch('claim')
        batch.invoice_display_rows = [service._invoice_display_row(row)]
        self.repository.save_batch(batch)
        return service, batch

    def test_same_batch_concurrent_requests_make_one_external_call(self):
        entered, finish = Event(), Event()
        calls = []
        class Client:
            def create_form_draft(self, **kwargs):
                calls.append(kwargs)
                entered.set()
                if not finish.wait(timeout=10):
                    raise RuntimeError('test client timed out')
                return 'oa-one', 'https://oa.example/one'
        service, batch = self.service(Client(), loader_barrier=Barrier(2))
        def create(key):
            try:
                return service.create_oa_draft(batch.batch_id, expected_version=1, idempotency_key=key, actor_id='tester')['status']
            except InputInvoiceUsageOaReverseVersionConflictError:
                return 'version_conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create, key) for key in ['first', 'second']]
            try:
                self.assertTrue(entered.wait(timeout=5))
                pending = service.staged_drafts()['items'][0]
                self.assertEqual(pending['draftRequestState'], 'requesting')
                self.assertFalse(pending['canRelease'])
                self.assertFalse(pending['canCreateDraft'])
                with self.assertRaises(InputInvoiceUsageOaReverseInvalidTransitionError):
                    service.manual_oa_status(batch.batch_id, decision='not_submitted', reason='cannot release while sending',
                                             expected_version=pending['version'], idempotency_key='release', actor_id='tester')
            finally:
                finish.set()
            results = [future.result(timeout=10) for future in futures]
        self.assertCountEqual(results, ['oa_draft_created', 'version_conflict'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(service.get_batch(batch.batch_id)['draftRequestState'], 'succeeded')

    def test_failed_external_outcome_visible_and_never_retried_before_manual_release(self):
        calls = []
        class Client:
            def create_form_draft(self, **kwargs):
                calls.append(kwargs)
                raise TimeoutError('OA response unknown')
        service, batch = self.service(Client())
        with self.assertRaises(InputInvoiceUsageOaReverseInvalidTransitionError):
            service.create_oa_draft(batch.batch_id, expected_version=1, idempotency_key='request', actor_id='tester')
        failed = service.staged_drafts()['items'][0]
        self.assertEqual(failed['status'], 'oa_draft_failed')
        self.assertEqual(failed['draftRequestState'], 'unknown')
        self.assertTrue(failed['canRelease'])
        self.assertFalse(failed['canCreateDraft'])
        self.assertIn('OA response unknown', failed['oaDetectionError'])
        with self.assertRaises(InputInvoiceUsageOaReverseInvalidTransitionError):
            service.create_oa_draft(batch.batch_id, expected_version=failed['version'], idempotency_key='new-request', actor_id='tester')
        self.assertEqual(len(calls), 1)
        released = service.manual_oa_status(batch.batch_id, decision='not_submitted', reason='已核实 OA 无单据并清理草稿',
                                           expected_version=failed['version'], idempotency_key='release', actor_id='tester')
        self.assertEqual(released['status'], 'not_submitted')
        self.assertEqual(self.repository.invoice_occupancy([self.invoice]), {})
        self.assertEqual(service.staged_drafts()['items'], [])
        self.assertEqual(self.repository.get_batch(batch.batch_id).audit_events[-1]['reason'], '已核实 OA 无单据并清理草稿')

    def test_expired_claim_requires_review_and_late_completion_cannot_restore_released_batch(self):
        service, batch = self.service(None)
        batch.version = 2
        batch.operation_idempotency['draft_request'] = 'expired-request'
        batch.oa_detection_status = 'draft_requesting'
        batch.oa_detection_payload['draftRequestReviewAfter'] = '2020-01-01T00:00:00Z'
        self.repository.claim_draft_creation(batch, expected_version=1)
        pending = service.get_batch(batch.batch_id)
        self.assertEqual(pending['draftRequestState'], 'unknown')
        self.assertTrue(pending['canRelease'])
        self.assertFalse(pending['canCreateDraft'])
        service.manual_oa_status(batch.batch_id, decision='not_submitted', reason='人工核实 OA 无单据',
                                 expected_version=2, idempotency_key='release', actor_id='tester')
        batch.version = 3
        batch.status = 'oa_draft_created'
        batch.oa_draft_id = 'late-oa-id'
        with self.assertRaises(InputInvoiceUsageOaReverseVersionConflictError):
            self.repository.save_batch(batch)
        self.assertEqual(self.repository.get_batch(batch.batch_id).status, 'not_submitted')
        self.assertEqual(self.repository.invoice_occupancy([self.invoice]), {})

    def test_bank_only_formal_relation_does_not_prevent_reservation(self):
        self.connection.execute("""insert into app.workbench_pair_relations(case_id,relation_mode,status,row_ids,row_types)
            values('reverse-bank-only','manual_confirmed','active',%s,array['invoice','bank'])""", ([self.invoice, 'bank-test'],))
        self.repository.save_batch(self.batch('bank-only'))
        self.assertEqual(self.repository.invoice_occupancy([self.invoice])[self.invoice]['occupiedBatchId'], 'reverse-batch-bank-only')

    def test_claim_rechecks_oa_relation_created_after_local_batch(self):
        batch = self.batch('newly-linked')
        self.repository.save_batch(batch)
        self.connection.execute("""insert into app.workbench_pair_relations(case_id,relation_mode,status,row_ids,row_types)
            values('oa-before-claim','manual_confirmed','active',%s,array['invoice','oa'])""", ([self.invoice, 'oa-test'],))
        batch.version = 2
        batch.operation_idempotency['draft_request'] = 'should-not-send'
        with self.assertRaises(InputInvoiceUsageOaReverseInvalidTransitionError) as raised:
            self.repository.claim_draft_creation(batch, expected_version=1)
        self.assertEqual(raised.exception.code, 'invalid_oa_reverse_selection')
        saved = self.repository.get_batch(batch.batch_id)
        self.assertEqual(saved.version, 1)
        self.assertNotIn('draft_request', saved.operation_idempotency)
