"""Invoice counts and reverse pagination share canonical relation facts."""
from __future__ import annotations

import unittest
from uuid import uuid4

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import InputInvoiceUsageCanonicalQueryService
from fin_ops_platform.services.input_invoice_usage_payment_rules import AppSettingsInputInvoiceUsagePaymentRulesProvider
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import PostgresInputInvoiceUsageQueryRepository

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class InputInvoiceCandidatesPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.addCleanup(truncate_test_database, self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.repository = PostgresInputInvoiceUsageQueryRepository(self.connection)
        self.service = InputInvoiceUsageCanonicalQueryService(
            repository=self.repository,
            row_assembler=InputInvoiceUsageQueryService(import_service=ImportNormalizationService(),
                payment_rules_provider=AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=None)),
        )

    def invoices(self, count, amount=10):
        self.connection.execute("""insert into app.invoices
            (legacy_mongo_id,invoice_type,invoice_no,invoice_date,invoice_month,seller_name,
             amount,signed_amount,tax_amount,total_with_tax,status)
            select 'candidate-'||n, 'input','CAND-'||n,'2026-09-01','2026-09-01','测试销方',%s,%s,0,%s,'pending'
            from generate_series(1,%s) n""", (amount,amount,amount,count))

    def bank(self, identity, amount=30):
        self.connection.execute("""insert into app.bank_transactions
            (id,legacy_mongo_id,account_no,txn_direction,counterparty_name_raw,amount,signed_amount,txn_date,txn_month,status)
            values (%s::uuid,%s,'test','outflow','测试销方',%s,%s,'2026-09-01','2026-09-01','pending')""",
            (str(uuid4()),identity,amount,-amount))

    def oa(self, identity, amount=20):
        self.connection.execute("""insert into app.oa_applications
            (oa_source_id,form_id,form_type,row_id,status,workflow_status,applicant,scope_month,amount,normalized_payload)
            values (%s,'2','支付申请',%s,'active','completed','真实申请人','2026-09-01',%s,
            jsonb_build_object('id',%s::text,'amount',%s::text,'applicant','真实申请人'))""", (identity,identity,amount,identity,str(amount)))

    def relation(self, case, ids, types):
        self.connection.execute("""insert into app.workbench_pair_relations
            (case_id,relation_mode,status,row_ids,row_types,month_scope,amount_check,raw_payload)
            values (%s,'manual_confirmed','active',%s::text[],%s::text[],'2026-09-01','{"matched":true}',
            jsonb_build_object('normalized_payload',jsonb_build_object('case_id',%s::text,'row_ids',%s::text[],
            'row_types',%s::text[],'relation_mode','manual_confirmed','status','active','amount_check','{"matched":true}'::jsonb)))""",
            (case,ids,types,case,ids,types))

    def test_full_pool_counts_members_not_groups_and_filters_before_pagination(self):
        self.invoices(213)
        self.bank('bank-only')
        self.relation('bank-only-case',['candidate-208','candidate-209','candidate-210','bank-only'],['invoice']*3+['bank'])
        self.oa('oa-paid')
        self.bank('bank-paid',20)
        self.relation('paid-case',['candidate-211','candidate-212','oa-paid','bank-paid'],['invoice','invoice','oa','bank'])
        self.oa('oa-unpaid',10)
        self.relation('unpaid-case',['candidate-213','oa-unpaid'],['invoice','oa'])
        main = self.service.rows({'page_size':['200']})
        counts = {o['value']:o['count'] for f in main['filterOptions'] if f['field']=='relation_status' for o in f['options']}
        self.assertEqual(counts,{'no_oa':210,'oa_no_bank':1,'oa_bank':2})
        self.assertEqual(main['summary']['invoiceCount'],213)
        first=self.service.candidate_rows({'page_size':['200']})
        second=self.service.candidate_rows({'page_size':['200'],'page':['2']})
        ids=[r['invoiceId'] for r in first['rows']+second['rows']]
        self.assertEqual(len(ids),210)
        self.assertEqual(len(set(ids)),210)
        self.assertEqual(first['pagination']['total'],210)
        self.assertEqual(first['relationCounts'],{'all':210,'linked':3,'unlinked':207})
        linked=self.service.candidate_rows({'bank_relation':['linked']})
        self.assertEqual({r['invoiceId'] for r in linked['rows']},{'candidate-208','candidate-209','candidate-210'})
        self.assertEqual(linked['summary']['totalWithTax'],'30.00')
        self.assertEqual(linked['relationCounts'],first['relationCounts'])
        exact=self.service.candidate_rows_by_invoice_ids(['candidate-208','candidate-209'])
        self.assertEqual({r['invoiceId'] for r in exact['rows']},{'candidate-208','candidate-209'})
        empty=self.service.candidate_rows({'page':['99']})
        self.assertEqual(empty['rows'],[])
        self.assertEqual(empty['pagination']['total'],210)
        self.assertEqual(self.repository.load_applicant_names(),['真实申请人'])

    def test_aggregate_bank_evidence_cannot_be_replaced_by_one_equal_transaction(self):
        self.invoices(1)
        self.oa('oa',10)
        self.bank('bank-a',10)
        self.bank('bank-b',10)
        self.relation('mismatch',['candidate-1','oa','bank-a','bank-b'],['invoice','oa','bank','bank'])
        result=self.service.list_rows(filters=[{'field':'payment_status','operator':'in','values':['pending']}])
        self.assertEqual(result['summary']['invoiceCount'],1)
        self.assertEqual(result['rows'][0]['paymentStatus']['code'],'pending')
        paid=self.service.list_rows(filters=[{'field':'payment_status','operator':'in','values':['paid']}])
        self.assertEqual(paid['rows'],[])
        self.assertEqual(paid['summary']['invoiceCount'],0)

    def test_missing_oa_detail_does_not_turn_an_existing_relation_into_a_candidate(self):
        self.invoices(1)
        self.relation('missing-source', ['candidate-1', 'oa-unavailable'], ['invoice', 'oa'])
        pool = self.service.candidate_rows({})
        self.assertEqual(pool['summary']['invoiceCount'], 0)
        main = self.service.list_rows(filters=[{'field':'relation_status','operator':'in','values':['oa_no_bank']}])
        self.assertEqual(main['summary']['invoiceCount'], 1)

    def test_missing_bank_detail_still_has_formal_bank_relation(self):
        self.invoices(1)
        self.relation('missing-bank', ['candidate-1', 'bank-unavailable'], ['invoice', 'bank'])
        pool = self.service.candidate_rows({'bank_relation':['linked']})
        self.assertEqual(pool['summary']['invoiceCount'], 1)
        self.assertEqual(pool['rows'][0]['bankRelationStatus'], 'linked')
        self.assertEqual(pool['rows'][0]['bankTransactions']['relationCount'], 0)
        exact = self.service.candidate_rows_by_invoice_ids(['candidate-1'])
        self.assertEqual(exact['rows'][0]['bankRelationStatus'], 'linked')

    def test_zero_amount_without_matched_evidence_is_not_a_match(self):
        self.invoices(1, amount=0)
        snapshot = self.repository.load_page(page=1, page_size=50, keyword=None, invoice_date_from=None, invoice_date_to=None, month=None, filters=[], sort_field="invoice_date", sort_direction="desc")
        facts = snapshot.groups[0]["payment_facts"]
        self.assertFalse(facts["fully_matched"])
        self.assertFalse(facts["invoice_oa_amount_matched"])
        self.oa('zero-oa', 0)
        self.bank('zero-bank', 0)
        self.relation('zero-case', ['candidate-1','zero-oa','zero-bank'], ['invoice','oa','bank'])
        self.connection.execute("update app.workbench_pair_relations set amount_check='{\"matched\":false}'::jsonb")
        snapshot = self.repository.load_page(page=1, page_size=50, keyword=None, invoice_date_from=None, invoice_date_to=None, month=None, filters=[], sort_field="invoice_date", sort_direction="desc")
        self.assertFalse(snapshot.groups[0]["payment_facts"]["fully_matched"])
        self.assertFalse(snapshot.groups[0]["payment_facts"]["invoice_oa_amount_matched"])
        self.connection.execute("update app.workbench_pair_relations set amount_check='{\"matched\":true}'::jsonb")
        snapshot = self.repository.load_page(page=1, page_size=50, keyword=None, invoice_date_from=None, invoice_date_to=None, month=None, filters=[], sort_field="invoice_date", sort_direction="desc")
        self.assertTrue(snapshot.groups[0]["payment_facts"]["fully_matched"])
        self.assertTrue(snapshot.groups[0]["payment_facts"]["invoice_oa_amount_matched"])

    def test_candidates_reject_invalid_page_and_bank_filter(self):
        from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageError
        for query in ({'page':['0']},{'page_size':['201']},{'bank_relation':['invented']}):
            with self.assertRaises(InputInvoiceUsageError):
                self.service.candidate_rows(query)
