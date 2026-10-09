"""Real SQL contracts for source drawers across page boundaries."""
import unittest

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import InputInvoiceUsageCanonicalQueryService
from fin_ops_platform.services.input_invoice_usage_payment_rules import AppSettingsInputInvoiceUsagePaymentRulesProvider
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.pending_invoice_canonical_query import (
    PendingInvoiceCanonicalQueryService,
    PostgresPendingInvoiceCanonicalRepository,
)
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    PostgresInputInvoiceUsageQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_query import PostgresWorkbenchPageQueryRepository
from fin_ops_platform.services.source_record_details import (
    invoice_source_detail,
    source_invoice_groups,
    workbench_source_row,
)

from tests import test_bank_split_document_scope_postgres as fixtures
from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url


class SharedSourceDetailsPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        fixtures.BankSplitDocumentScopePostgresTests.setUp(self)
        fixtures.BankSplitDocumentScopePostgresTests.document(self)
        fixtures.BankSplitDocumentScopePostgresTests.sync_relation_fixture(self)
        # This source-detail fixture includes the normalized fields written by OA sync.
        # The split-only fixture intentionally omits them because it tests amounts.
        self.connection.execute("""update app.oa_applications set normalized_payload=normalized_payload ||
            jsonb_build_object('applicant', applicant, 'detail_fields', jsonb_build_object(
                '申请日期', '2026-04-29', 'OA单号', '2403'))""")
        self.pending = PendingInvoiceCanonicalQueryService(repository=PostgresPendingInvoiceCanonicalRepository(self.connection))
        self.input = InputInvoiceUsageCanonicalQueryService(
            repository=PostgresInputInvoiceUsageQueryRepository(self.connection),
            row_assembler=InputInvoiceUsageQueryService(import_service=ImportNormalizationService(),
                payment_rules_provider=AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=None)))
        self.workbench = PostgresWorkbenchPageQueryRepository(self.connection, tenant_id='default')

    def test_split_children_open_one_original_bank_with_identical_fields_on_every_page(self):
        original = self.pending.bank_transaction_detail('bank-parent')['sections']
        child = self.pending.bank_transaction_detail(self.interest)['sections']
        self.assertEqual(child, original)
        relation = self.input.bank_transaction_detail(self.interest)['sections']
        self.assertEqual(relation, original)
        workbench = self.workbench.get_workbench_row_detail(scope_key='all', row_id=self.interest, row_type='bank')
        self.assertIsNotNone(workbench)
        self.assertEqual(workbench_source_row(workbench['row'])['source_sections'], original)
        self.assertEqual({section['document_id'] for section in relation}, {'bank-parent'})
        fields = {field['label']: field['value'] for section in relation for field in section['fields']}
        self.assertEqual(fields['支出金额'], '1001497.22')
        self.assertEqual(fields['余额'], '123.45')

    def test_relation_includes_actual_oa_fields_and_no_internal_identifiers(self):
        source = self.pending.oa_detail('oa-interest')['sections']
        relation = self.pending.oa_detail('oa-interest')['sections']
        self.assertEqual(relation, source)
        self.assertTrue(source)
        self.assertEqual({section['document_id'] for section in source}, {'oa-interest'})
        summary = source[0]['oa_navigation']
        self.assertEqual(set(summary), {'applicantName', 'amount', 'applicationDate', 'workflowNo'})
        self.assertEqual(summary, {'applicantName': '测试申请人', 'amount': '1497.22',
                                   'applicationDate': '2026-04-29', 'workflowNo': '2403'})
        self.assertTrue(all(section['oa_navigation'] == summary for section in relation))
        input_detail = self.input.oa_detail('oa-interest')['sections']
        self.assertEqual(input_detail[0]['oa_navigation'], summary)
        labels = {field['label'] for section in source for field in section['fields']}
        self.assertIn('申请人', labels)
        self.assertNotIn('Mongo文档ID', labels)

    def test_invoice_detail_expands_all_source_lines_not_only_selected_relation_member(self):
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated source detail fixture'")
            tx.execute("update app.invoices set digital_invoice_no='26532000000000000001', raw_payload='{\"normalized_payload\":{\"source_line_items\":[{\"taxable_item_name\":\"第一项\",\"quantity\":\"2\",\"amount\":\"100\",\"tax_amount\":\"0\",\"total_with_tax\":\"100\"}]}}'::jsonb")
            tx.execute("""insert into app.invoices(legacy_mongo_id,invoice_type,invoice_no,digital_invoice_no,invoice_date,
                invoice_month,seller_name,buyer_name,amount,signed_amount,tax_amount,total_with_tax,status,raw_payload)
                values('invoice-line-2','input','SCOPE-001','26532000000000000001','2026-04-29','2026-04-01',
                '提供方','购买方',10,10,0,10,'pending','{"normalized_payload":{"source_line_items":[{"taxable_item_name":"第二项","quantity":"0","amount":"10","tax_amount":"0","total_with_tax":"10"}]}}'::jsonb)""")
        source = self.pending.invoice_detail('invoice-scope')['sections']
        relation = self.input.invoice_detail('invoice-scope')['sections']
        self.assertEqual([(section['title'],section['fields']) for section in relation],
                         [(section['title'],section['fields']) for section in source])
        details = [section for section in source if section['title'].startswith('货物或应税劳务明细')]
        self.assertEqual(len(details), 2)
        self.assertEqual({field['value'] for section in details for field in section['fields'] if field['label']=='货物或应税劳务名称'}, {'第一项','第二项'})
        core = PostgresCoreRepository(self.connection)
        documents = source_invoice_groups(core.list_invoice_document_members(['invoice-scope']))
        self.assertEqual(len(documents), 1)
        projected = invoice_source_detail(documents[0])['sections']
        self.assertEqual(source[0]['invoice_navigation'], projected[0]['invoice_navigation'])
        self.assertEqual(source[0]['invoice_navigation']['counterpartyName'], '提供方')
        self.assertIsNone(source[0]['invoice_navigation']['totalWithTax'])
        # Canonical record and direct-query adapters produce the same document data.
        normalize = lambda sections: [(section['title'], section['fields']) for section in sections]
        self.assertEqual(normalize(source), normalize(projected))
        workbench = self.workbench.get_workbench_row_detail(scope_key='all', row_id='invoice-scope', row_type='invoice')
        self.assertEqual(normalize(workbench['row']['source_sections']), normalize(source))
