from __future__ import annotations

import unittest
from dataclasses import replace

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import InputInvoiceUsageCanonicalQueryService
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord
from fin_ops_platform.services.oa_pending_payment_query_service import OaPendingPaymentQueryService
from fin_ops_platform.services.pending_invoice_canonical_query import (
    PendingInvoiceCanonicalQueryService,
    PostgresPendingInvoiceCanonicalRepository,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    PostgresInputInvoiceUsageQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_query import (
    PostgresOaPendingPaymentQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentSourceSnapshotRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandService

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database
from tests.test_invoice_usage_collection_postgres_integration import _UnexpectedPaymentRulesProvider
from tests.test_oa_pending_payment_postgres_integration import _in_progress_record


class EtcRelationPageReadsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        PostgresOaPendingPaymentSourceSnapshotRepository(
            self.connection, relation_command_service_for_transaction=lambda tx: WorkbenchRelationCommandService(
                relation_repository=PostgresWorkbenchRelationRepository(tx)),
        ).commit_authoritative_snapshot(scope_key='2026-05', tenant_id='default', projection_records=[],
            admission_records=[replace(_in_progress_record(), amount='47.00')], payment_statuses={'flow-in-progress-1':OAPaymentStatusRecord(flow_id='flow-in-progress-1',pay_status=0)})
        self.connection.execute("""insert into app.bank_transactions(
            legacy_mongo_id, account_no, txn_direction, counterparty_name_raw, amount, signed_amount,
            txn_date, txn_month, status) values ('etc-bank', '8106', 'outflow', 'ETC还款', 47, -47,
            '2026-05-20','2026-05-01','pending')""")
        self.connection.execute("""insert into app.etc_business_batches(business_batch_id,status,scope_month,
            invoice_count,total_amount,raw_payload) values ('business-47','oa_submitted','2026-05-01',47,47,
            '{"normalized_payload":{"external_etc_batch_id":"external-47"}}')""")
        self.connection.execute("""insert into app.etc_invoices(etc_invoice_id,business_batch_id,status,invoice_no,
            invoice_date,seller_name,amount,total_with_tax)
            select 'etc-'||n,'business-47','submitted','NO-'||n,'2026-05-01','高速公路',1,1 from generate_series(1,47) n""")
        self.connection.execute("""insert into app.invoices(legacy_mongo_id,invoice_type,invoice_no,invoice_date,
            invoice_month,seller_name,buyer_name,amount,signed_amount,total_with_tax,status,etc_invoice_id)
            select 'inv-'||n,'input','NO-'||n,'2026-05-01','2026-05-01','高速公路','测试公司',1,1,1,'pending','etc-'||n
            from generate_series(1,47) n""")
        self.connection.execute("""insert into app.workbench_pair_relations(case_id,relation_mode,status,row_ids,row_types)
            values ('CASE-ETC','batch_accounting','active',
            array['oa-in-progress-1','etc-bank','etc-summary-external-47','inv-1'], array['oa','bank','invoice','invoice'])""")
        self.connection.execute("""update app.workbench_pair_relations set raw_payload=jsonb_build_object('normalized_payload',
            jsonb_build_object('case_id',case_id,'status',status,'relation_mode',relation_mode,'row_ids',row_ids,'row_types',row_types))""")

    def tearDown(self):
        self.connection.close()
        truncate_test_database(self.database_url)

    def test_all_pages_resolve_same_47_members_without_multiplying_payment(self):
        oa = OaPendingPaymentQueryService(repository=PostgresOaPendingPaymentQueryRepository(self.connection))
        rows = oa.rows({'view_mode':['in_progress']}, tenant_id='default')['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['invoice']['relationCount'], 47)
        self.assertEqual(rows[0]['bankTransaction']['paidTotal'], '47.00')
        detail = oa.relation_details(rows[0]['id'], kind='invoice', tenant_id='default')
        self.assertEqual(detail["relationCount"], 47)
        pending = PendingInvoiceCanonicalQueryService(repository=PostgresPendingInvoiceCanonicalRepository(self.connection))
        row = pending.rows({'direction':['expense'],'filter':['all']})['rows'][0]
        self.assertEqual(row['input_invoices']['relation_count'], 47)
        self.assertEqual(len(pending.relation_detail('etc-bank',direction='expense',kind='invoice')['sections']),47)
        usage = InputInvoiceUsageCanonicalQueryService(repository=PostgresInputInvoiceUsageQueryRepository(self.connection),
            row_assembler=InputInvoiceUsageQueryService(import_service=ImportNormalizationService(), payment_rules_provider=_UnexpectedPaymentRulesProvider()))
        payload = usage.rows({'keyword':['NO-47']})
        self.assertEqual(len(payload['rows']), 1)
        self.assertEqual(payload['rows'][0]['oa']['relationCount'], 1)
        self.assertEqual(payload['rows'][0]['bankTransactions']['relationCount'], 1)
        self.assertEqual(self.connection.fetch_one("select row_ids from app.workbench_pair_relations where case_id='CASE-ETC'")['row_ids'],
            ['oa-in-progress-1','etc-bank','etc-summary-external-47','inv-1'])

    def test_deleted_invoice_and_withdrawn_relation_are_not_reintroduced(self):
        self.connection.execute("update app.invoices set status='deleted' where legacy_mongo_id='inv-47'")
        oa = OaPendingPaymentQueryService(repository=PostgresOaPendingPaymentQueryRepository(self.connection))
        self.assertEqual(oa.rows({'view_mode':['in_progress']},tenant_id='default')['rows'][0]['invoice']['relationCount'],46)
        self.connection.execute("update app.workbench_pair_relations set status='withdrawn' where case_id='CASE-ETC'")
        self.assertEqual(oa.rows({'view_mode':['in_progress']},tenant_id='default')['rows'][0]['invoice']['relationCount'],0)
