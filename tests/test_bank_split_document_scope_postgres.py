"""Document comparisons share split-purpose scope in SQL and hydrated rows."""
import unittest
from decimal import Decimal

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import InputInvoiceUsageCanonicalQueryService
from fin_ops_platform.services.input_invoice_usage_payment_rules import AppSettingsInputInvoiceUsagePaymentRulesProvider
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.oa_pending_payment_query_service import OaPendingPaymentQueryService
from fin_ops_platform.services.output_invoice_collection_canonical_query_service import (
    OutputInvoiceCollectionCanonicalQueryService,
)
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    PostgresInputInvoiceUsageQueryRepository,
    PostgresOutputInvoiceCollectionQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_query import (
    PostgresOaPendingPaymentQueryRepository,
)

from tests import test_bank_split_consumers_postgres as fixtures
from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url


class BankSplitDocumentScopePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        fixtures.BankSplitConsumersPostgresTests.setUp(self)
        self.connection.execute("update app.bank_transactions set status='pending'")
        self.connection.execute("""update app.oa_applications set normalized_payload=normalized_payload ||
            '{"month":"2026-04","apply_type":"支付申请","workflow_status":"completed"}'::jsonb""")

    def document(self, amount='1497.22', invoice_type='input'):
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated split document fixture'")
            tx.execute("update app.oa_applications set amount=%s::numeric, normalized_payload=jsonb_set(normalized_payload,'{amount}',to_jsonb(%s::text))", (amount,amount))
            if invoice_type == 'output':
                tx.execute("update app.bank_transactions set txn_direction='inflow',signed_amount=amount")
            tx.execute("""insert into app.invoices(legacy_mongo_id,invoice_type,invoice_no,invoice_date,invoice_month,
                       seller_name,buyer_name,amount,signed_amount,tax_amount,total_with_tax,status)
                       values('invoice-scope',%s,'SCOPE-001','2026-04-29','2026-04-01','提供方','购买方',%s,%s,0,%s,'pending')""",
                       (invoice_type,amount,amount,amount))
            tx.execute("""update app.workbench_pair_relations set row_ids=array_append(row_ids,'invoice-scope'),
                       row_types=array_append(row_types,'invoice'),amount_check='{"matched":false}'::jsonb""")

    def sync_relation_fixture(self):
        self.connection.execute("""update app.workbench_pair_relations relation set raw_payload=jsonb_build_object(
            'normalized_payload',jsonb_build_object('case_id',case_id,'row_ids',row_ids,'row_types',row_types,
            'relation_mode',relation_mode,'status',status,'version',version,'amount_check',amount_check,
            'special_metadata',special_metadata))""")

    def oa_page(self):
        self.sync_relation_fixture()
        return OaPendingPaymentQueryService(repository=PostgresOaPendingPaymentQueryRepository(self.connection)).rows(
            {'month':['2026-04'],'page':['1'],'page_size':['20']}, tenant_id='default')

    def invoice_page(self, invoice_type='input'):
        self.sync_relation_fixture()
        if invoice_type == 'input':
            service = InputInvoiceUsageCanonicalQueryService(repository=PostgresInputInvoiceUsageQueryRepository(self.connection),
                row_assembler=InputInvoiceUsageQueryService(import_service=ImportNormalizationService(), payment_rules_provider=AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=None)))
        else:
            service = OutputInvoiceCollectionCanonicalQueryService(repository=PostgresOutputInvoiceCollectionQueryRepository(self.connection),
                row_assembler=OutputInvoiceCollectionQueryService(import_service=ImportNormalizationService()))
        return service.list_rows(page=1,page_size=20,month='2026-04',**({'include_statistics':False} if invoice_type == 'input' else {}))

    def test_interest_oa_and_input_invoice_use_current_unique_purpose_despite_old_mismatch(self):
        self.document()
        oa = self.oa_page()
        self.assertEqual(oa['summary']['bankPaidTotal'],'1497.22')
        self.assertEqual(oa['rows'][0]['bankTransaction']['paidTotal'],'1497.22')
        invoice = self.invoice_page()
        self.assertEqual(invoice['rows'][0]['bankTransactions']['amount'],'1497.22')
        self.assertEqual(invoice['rows'][0]['paymentStatus']['code'],'paid')
        self.assertEqual(self.connection.fetch_one("select amount_check from app.workbench_pair_relations")['amount_check'],{'matched':False})

    def test_principal_document_uses_principal_bucket_instead_of_deleting_it(self):
        self.document('1000000.00')
        oa = self.oa_page()
        self.assertEqual(oa['summary']['bankPaidTotal'],'1000000.00')
        self.assertEqual(oa['rows'][0]['bankTransaction']['paidTotal'],'1000000.00')
        invoice = self.invoice_page()
        self.assertEqual(invoice['rows'][0]['bankTransactions']['amount'],'1000000.00')
        self.assertEqual(invoice['rows'][0]['paymentStatus']['code'],'paid')

    def test_output_collection_uses_unique_interest_bucket(self):
        self.document(invoice_type='output')
        invoice = self.invoice_page('output')
        self.assertEqual(invoice['rows'][0]['bankTransactions']['receivedTotal'],'1497.22')
        self.assertEqual(invoice['summary']['collectedAmount'],'1497.22')

    def test_unmatched_target_keeps_entire_evidence_and_pending_status(self):
        self.document('2000.00')
        oa = self.oa_page()
        self.assertEqual(oa['summary']['bankPaidTotal'],'1001497.22')
        self.assertEqual(oa['rows'][0]['bankTransaction']['paidTotal'],'1001497.22')
        invoice = self.invoice_page()
        self.assertEqual(invoice['rows'][0]['bankTransactions']['amount'],'1001497.22')
        self.assertEqual(invoice['rows'][0]['paymentStatus']['code'],'pending')

    def test_equal_buckets_do_not_choose_principal_or_interest(self):
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated equal bucket fixture'")
            tx.execute("update app.bank_transactions set amount=2994.44,signed_amount=-2994.44")
            tx.execute("update app.bank_transaction_split_items set amount=1497.22")
        self.document()
        self.assertEqual(self.oa_page()['rows'][0]['bankTransaction']['paidTotal'],'2994.44')
        invoice = self.invoice_page()
        self.assertEqual(invoice['rows'][0]['bankTransactions']['amount'],'2994.44')
        self.assertEqual(invoice['rows'][0]['paymentStatus']['code'],'pending')

    def test_mixed_direction_does_not_narrow_document_comparison(self):
        self.document()
        self.connection.execute("""insert into app.bank_transactions(legacy_mongo_id,account_no,txn_direction,
            counterparty_name_raw,amount,signed_amount,txn_date,txn_month,status) values
            ('bank-income','test','inflow','test',1,1,'2026-04-29','2026-04-01','pending')""")
        self.connection.execute("update app.workbench_pair_relations set row_ids=array_append(row_ids,'bank-income'),row_types=array_append(row_types,'bank')")
        oa = self.oa_page()
        self.assertEqual(oa['summary']['bankPaidTotal'],'1001497.22')
        self.assertEqual(oa['rows'][0]['bankTransaction']['paidTotal'],'1001497.22')
        self.assertEqual(self.invoice_page()['rows'][0]['paymentStatus']['code'],'pending')

    def test_unsplit_sibling_is_not_hidden_by_an_interest_bucket_match(self):
        self.document()
        self.connection.execute("""insert into app.bank_transactions(legacy_mongo_id,account_no,txn_direction,
            counterparty_name_raw,amount,signed_amount,txn_date,txn_month,status) values
            ('bank-extra','test','outflow','test',1,-1,'2026-04-29','2026-04-01','pending')""")
        self.connection.execute("update app.workbench_pair_relations set row_ids=array_append(row_ids,'bank-extra'),row_types=array_append(row_types,'bank')")
        oa = self.oa_page()
        self.assertEqual(Decimal(oa['summary']['bankPaidTotal']),Decimal('1001498.22'))
        self.assertEqual(oa['rows'][0]['bankTransaction']['paidTotal'],'1001498.22')
        invoice = self.invoice_page()
        self.assertEqual(invoice['rows'][0]['bankTransactions']['amount'],'1001498.22')
        self.assertEqual(invoice['rows'][0]['paymentStatus']['code'],'pending')

    def test_old_matched_flag_cannot_hide_mixed_direction_even_when_absolute_total_matches(self):
        self.document('1001498.22')
        self.connection.execute("""insert into app.bank_transactions(legacy_mongo_id,account_no,txn_direction,
            counterparty_name_raw,amount,signed_amount,txn_date,txn_month,status) values
            ('bank-income','test','inflow','test',1,1,'2026-04-29','2026-04-01','pending')""")
        self.connection.execute("""update app.workbench_pair_relations set row_ids=array_append(row_ids,'bank-income'),
            row_types=array_append(row_types,'bank'),amount_check='{"matched":true}'::jsonb""")
        invoice = self.invoice_page()
        self.assertEqual(invoice['rows'][0]['bankTransactions']['amount'],'1001498.22')
        self.assertEqual(invoice['rows'][0]['paymentStatus']['code'],'pending')

    def test_distinct_invoice_lines_in_disjoint_cases_share_group_comparison(self):
        self.document('1497.22')
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated distinct invoice line fixture'")
            tx.execute("update app.invoices set digital_invoice_no='26372000000458116231'")
            tx.execute("""insert into app.invoices(legacy_mongo_id,invoice_type,invoice_no,digital_invoice_no,
                invoice_date,invoice_month,seller_name,buyer_name,amount,signed_amount,tax_amount,total_with_tax,status)
                values ('invoice-scope-line-2','input','SCOPE-002','26372000000458116231',
                '2026-04-29','2026-04-01','提供方','购买方',100,100,0,100,'pending')""")
            tx.execute("""insert into app.oa_applications(oa_source_id,form_id,form_type,row_id,status,workflow_status,
                applicant,application_date,scope_month,approved_at,project_name,amount,currency,normalized_payload)
                values ('oa-second','oa-second','支付申请','oa-second','active','completed','测试申请人',
                '2026-04-29','2026-04-01','2026-04-29 10:00:00+08','测试项目',100,'CNY',
                '{"id":"oa-second","amount":"100.00","project_name":"测试项目","workflow_status":"completed"}'::jsonb)""")
            parent = tx.fetch_one("""insert into app.bank_transactions(legacy_mongo_id,account_no,txn_direction,
                counterparty_name_raw,amount,signed_amount,txn_date,txn_month,status)
                values('bank-second','test','outflow','test',1100,-1100,'2026-04-29','2026-04-01','pending') returning id""")['id']
            tx.execute("insert into app.bank_transaction_split_sets(bank_transaction_id,version,updated_by) values(%s,1,'test')",(parent,))
            parts = tx.fetch_all("""insert into app.bank_transaction_split_items(id,bank_transaction_id,category_code,amount,position)
                values(gen_random_uuid(),%s,'principal-custom',1000,0),(gen_random_uuid(),%s,'interest-custom',100,1) returning id""",(parent,parent))
            tx.execute("""insert into app.workbench_pair_relations(case_id,relation_mode,status,row_ids,row_types,month_scope,amount_check)
                values('second-case','manual_confirmed','active',%s::text[],array['oa','invoice','bank','bank'],
                '2026-04-01','{"matched":false}'::jsonb)""",(['oa-second','invoice-scope-line-2',*[str(row['id']) for row in parts]],))
        # No invoice, bank, or OA member is shared between these valid formal cases.
        self.assertEqual(self.connection.fetch_all("""select member from app.workbench_pair_relations,
            unnest(row_ids) member group by member having count(*)>1"""),[])
        invoice = self.invoice_page()
        self.assertEqual(invoice['pagination']['total'],1)
        self.assertEqual(invoice['rows'][0]['invoice']['lineItemCount'],2)
        self.assertEqual(invoice['rows'][0]['bankTransactions']['amount'],'1597.22')
        self.assertEqual(invoice['rows'][0]['paymentStatus']['code'],'paid')
        # A separate unsplit case matching the group total must not conceal the split case's evidence.
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated mixed group fixture'")
            tx.execute("delete from app.bank_transaction_split_sets where bank_transaction_id=%s",(parent,))
            tx.execute("update app.bank_transactions set amount=1597.22,signed_amount=-1597.22 where id=%s",(parent,))
            tx.execute("update app.oa_applications set amount=1597.22,normalized_payload=jsonb_set(normalized_payload,'{amount}','\"1597.22\"'::jsonb) where oa_source_id='oa-second'")
            tx.execute("""update app.workbench_pair_relations set row_ids=array['oa-second','invoice-scope-line-2','bank-second'],
                row_types=array['oa','invoice','bank'],amount_check='{"matched":true}'::jsonb where case_id='second-case'""")
        self.assertEqual(self.invoice_page()['rows'][0]['paymentStatus']['code'],'pending')

    def test_pending_invoice_candidate_query_and_write_preview_share_document_scope(self):
        from types import SimpleNamespace

        from fin_ops_platform.services.pending_invoice_canonical_query import (
            PendingInvoiceCanonicalQueryService,
            PostgresPendingInvoiceCanonicalRepository,
        )
        from fin_ops_platform.services.pending_invoice_service import (
            PendingInvoiceApplicationService,
            PendingInvoiceQueryService,
        )
        from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository

        self.document()
        self.sync_relation_fixture()
        core = PostgresCoreRepository(self.connection)
        imports = ImportNormalizationService(existing_invoices=core.list_invoices_page()[0])
        reader = SimpleNamespace(active_relations_for_row_ids=lambda ids: [row['raw_payload']['normalized_payload']
            for row in self.connection.fetch_all("select raw_payload from app.workbench_pair_relations where row_ids && %s::text[]",(ids,))])
        application = PendingInvoiceApplicationService(import_service=imports,
            bank_units_by_ids=core.list_bank_transaction_units_by_ids,relation_command_service=reader)
        query = PendingInvoiceQueryService(import_service=imports,bank_units_by_ids=core.list_bank_transaction_units_by_ids,
            category_service=None,app_settings_provider=lambda:self.settings,relation_reader=reader)
        canonical = PendingInvoiceCanonicalQueryService(repository=PostgresPendingInvoiceCanonicalRepository(self.connection))
        for amount in ('1497.22','1000000.00','2000.00'):
            with self.subTest(amount=amount):
                with self.connection.transaction() as tx:
                    tx.execute("set local fin_ops.correction_reason='isolated pending comparison fixture'")
                    tx.execute("update app.invoices set total_with_tax=%s,amount=%s,signed_amount=%s",(amount,amount,amount))
                invoice = imports.get_invoice('invoice-scope')
                invoice.total_with_tax = Decimal(amount)
                expected = amount if amount != '2000.00' else '1001497.22'
                candidate = canonical.invoice_candidates({'transaction_id':[self.interest],'page':['1'],'page_size':['20']})
                self.assertEqual(candidate['rows'][0]['paid_total'],expected)
                preview = application.preview_attach_existing_invoice(transaction_id=self.interest,payload={'invoice_id':'invoice-scope'})
                self.assertEqual(preview['payment_impact']['paid_total_before'],expected)
                context = query._canonical_relation_context_row(self.interest)
                summary = query._payment_summary_from_relation_context(context,[{'total_with_tax':amount}])
                self.assertEqual(summary['paid_total'],expected)
                self.assertEqual(sum(Decimal(row['debit_amount']) for row in query._payment_rows_from_relation_context(context)),Decimal(expected))
