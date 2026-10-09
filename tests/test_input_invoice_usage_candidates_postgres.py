"""Invoice counts and reverse pagination share canonical relation facts."""
from __future__ import annotations

import unittest
import json
from uuid import uuid4

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import InputInvoiceUsageCanonicalQueryService
from fin_ops_platform.services.input_invoice_usage_payment_rules import AppSettingsInputInvoiceUsagePaymentRulesProvider
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    PostgresInputInvoiceUsageQueryRepository,
)

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

    def test_hierarchy_counts_stay_complete_and_unpaid_excludes_unused(self):
        self.invoices(4)
        self.bank("paid-bank", 10)
        self.oa("unpaid-oa", 10)
        self.relation("used-paid", ["candidate-1", "paid-bank"], ["invoice", "bank"])
        self.relation("used-unpaid", ["candidate-2", "unpaid-oa"], ["invoice", "oa"])
        # An invoice-only relation remains unused, even when a rule matches it.
        self.relation("unused-pair", ["candidate-3", "candidate-4"], ["invoice", "invoice"])
        expected = self.service.list_rows()["classification"]
        self.assertEqual(expected["all"]["count"], 4)
        self.assertEqual(expected["used"]["count"], 2)
        self.assertEqual(expected["unused"]["count"], 2)
        self.assertEqual({group["id"]: group["count"] for group in expected["groups"]}, {"paid": 1, "unpaid": 1})
        for status, count in (("used", 2), ("unused", 2)):
            filters = [{"field": "usage_status", "operator": "in", "values": [status]}]
            selected = self.service.list_rows(filters=filters, page_size=1)
            self.assertEqual(selected["classification"], expected)
            self.assertEqual(selected["summary"]["invoiceCount"], count)
            self.assertEqual(self.service.export_page(filters=filters)["summary"]["invoiceCount"], count)
        keyword = self.service.list_rows(keyword="CAND-3")["classification"]
        self.assertEqual(keyword["unused"]["count"], 2)
        self.assertEqual(keyword["used"]["count"], 0)
        self.assertEqual(sum(group["count"] for group in keyword["groups"]), 0)

    def test_net_payment_current_facts_drive_rows_filters_export_and_rules(self):
        self.invoices(3, 1015)
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated net payment fixture'")
            tx.execute("update app.invoices set total_with_tax=-1015, amount=-1015, signed_amount=-1015 where legacy_mongo_id='candidate-2'")
        self.oa('oa-net', 1015)
        self.bank('out', 1050)
        self.bank('refund', 35)
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated refund fixture'")
            tx.execute("update app.bank_transactions set txn_direction='inflow', signed_amount=35 where legacy_mongo_id='refund'")
        self.relation('net', ['candidate-1', 'candidate-2', 'candidate-3', 'oa-net', 'out', 'refund'], ['invoice'] * 3 + ['oa', 'bank', 'bank'])
        self.connection.execute("update app.workbench_pair_relations set amount_check=jsonb_build_object('status','mismatch') where case_id='net'")
        before = self.connection.fetch_one("select amount_check from app.workbench_pair_relations where case_id='net'")
        payload = self.service.list_rows()
        row = payload['rows'][0]
        self.assertEqual(row['invoice']['totalWithTax'], '1015.00')
        self.assertEqual(row['paymentStatus']['code'], 'paid')
        self.assertEqual(row['bankTransactions']['netOutflow'], '1015.00')
        self.assertEqual(row['bankTransactions']['original_amount'], '1085.00')
        self.assertEqual(row['bankTransactions']['netDirectionLabel'], '净支出')
        self.assertEqual(row['bankTransactions']['relationCount'], 2)
        self.assertEqual({r['amount'] for r in row['bankTransactions']['summaries']}, {'1050.00', '35.00'})
        children = payload['classification']['groups'][0]['children']
        self.assertNotIn('category:pending', [c['id'] for c in children])
        self.assertEqual(next(c['count'] for c in children if c['id'] == 'category:paid'), 3)
        snapshot = self.repository.load_page(page=1, page_size=20, keyword=None, invoice_date_from=None, invoice_date_to=None, month=None, filters=[], sort_field="invoice_date", sort_direction="desc")
        self.assertEqual(snapshot.groups[0]['payment_facts']['payment_comparison'], 'equal')
        self.assertTrue(snapshot.groups[0]['payment_facts']['has_bank'])
        for field, operator, value in [('payment_status', 'in', ['paid']), ('bank_amount', 'equals', '1015'), ('bank_direction', 'in', ['outflow'])]:
            filters = [{'field': field, 'operator': operator, 'values' if operator == 'in' else 'value': value}]
            selected = self.service.list_rows(filters=filters)
            self.assertEqual(selected['summary']['invoiceCount'], 3)
            self.assertEqual(self.service.export_page(filters=filters)['rows'], selected['rows'])
        self.assertEqual(self.connection.fetch_one("select amount_check from app.workbench_pair_relations where case_id='net'"), before)
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated refund refresh fixture'")
            tx.execute("update app.bank_transactions set amount=1050, signed_amount=1050 where legacy_mongo_id='refund'")
        refreshed = self.service.list_rows()['rows'][0]
        self.assertEqual(refreshed['bankTransactions']['netAmount'], '0.00')
        self.assertEqual(refreshed['bankTransactions']['netDirectionLabel'], '收支相抵')
        self.assertEqual(refreshed['paymentStatus']['code'], 'invoice_greater_payment')

    def test_multi_applicant_rule_drives_canonical_rows_filters_and_summary(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from fin_ops_platform.services.postgres_state_store import PostgresStateStore
        self.invoices(3)
        for index, name in enumerate(["黄  亮", "周洁莹", "其他人"], 1):
            identity = f"oa-{index}"
            self.oa(identity, 10)
            self.connection.execute("update app.oa_applications set applicant=%s, normalized_payload=normalized_payload || %s::jsonb where row_id=%s",
                                    (name, json.dumps({"applicant": name}), identity))
            self.relation(f"case-{index}", [f"candidate-{index}", identity], ["invoice", "oa"])
        with TemporaryDirectory() as directory:
            store = PostgresStateStore(data_dir=Path(directory), connection=self.connection)
            provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=store, transaction_factory=self.connection.transaction)
            provider.update_payment_status_rules({"expectedVersion": 1, "idempotencyKey": "multi-db", "rules": [
                {"id": "multi", "statusCode": "offset", "label": "冲", "enabled": True,
                 "conditions": {"hasOa": True, "hasBank": False, "applicantNames": ["黄 亮", "周洁莹"]}},
                {"id": "waiting", "statusCode": "waiting_payment", "label": "未关联流水", "enabled": True,
                 "conditions": {"hasOa": True, "hasBank": False}}
            ]}, actor_id="test")
            result = self.service.list_rows(filters=[{"field": "payment_status", "operator": "in", "values": ["offset"]}])
            self.assertEqual(result["pagination"]["total"], 2)
            self.assertEqual(result["summary"]["totalWithTax"], "20.00")
            self.assertEqual({r["paymentStatus"]["code"] for r in result["rows"]}, {"offset"})
            unpaid = self.service.list_rows(filters=[{"field": "payment_group", "operator": "in", "values": ["unpaid"]},
                                                   {"field": "payment_status", "operator": "in", "values": ["waiting_payment"]}])
            self.assertEqual(unpaid["pagination"]["total"], 1)
            self.assertEqual(unpaid["summary"]["totalWithTax"], "10.00")
            self.assertEqual(unpaid["rows"][0]["paymentStatus"]["code"], "waiting_payment")

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
        self.assertEqual(len(ids),207)
        self.assertEqual(len(set(ids)),207)
        self.assertEqual(first['pagination']['total'],207)
        self.assertNotIn('relationCounts', first)
        unused_filter = [{'field': 'usage_status', 'operator': 'in', 'values': ['unused']}]
        unused = self.service.list_rows(page=1, page_size=200, filters=unused_filter)
        unused_next = self.service.list_rows(page=2, page_size=200, filters=unused_filter)
        self.assertEqual(set(ids), {r['invoiceId'] for r in unused['rows'] + unused_next['rows']})
        self.assertEqual(first['summary']['invoiceCount'], unused['summary']['invoiceCount'])
        self.assertEqual(first['summary']['totalWithTax'], unused['summary']['totalWithTax'])
        self.assertEqual(first['summary']['totalWithTax'], '2070.00')
        self.assertTrue(all(row['usageStatus'] == 'unused' for row in first['rows']))
        self.assertTrue(all('usageStatus' not in row for row in unused['rows']))
        exact=self.service.candidate_rows_by_invoice_ids(['candidate-208','candidate-209', 'candidate-211', 'candidate-213', 'missing'])
        self.assertEqual({r['invoiceId'] for r in exact['rows']},{'candidate-208','candidate-209','candidate-211','candidate-213'})
        self.assertTrue(all(row['usageStatus'] == 'used' for row in exact['rows']))
        self.assertNotIn('missing', {row['invoiceId'] for row in exact['rows']})
        empty=self.service.candidate_rows({'page':['99']})
        self.assertEqual(empty['rows'],[])
        self.assertEqual(empty['pagination']['total'],207)

    def test_aggregate_bank_evidence_cannot_be_replaced_by_one_equal_transaction(self):
        self.invoices(1)
        self.oa('oa',10)
        self.bank('bank-a',10)
        self.bank('bank-b',10)
        self.relation('mismatch',['candidate-1','oa','bank-a','bank-b'],['invoice','oa','bank','bank'])
        result=self.service.list_rows(filters=[{'field':'payment_status','operator':'in','values':['invoice_less_payment']}])
        self.assertEqual(result['summary']['invoiceCount'],1)
        self.assertEqual(result['rows'][0]['paymentStatus']['code'],'invoice_less_payment')
        self.assertEqual(result['rows'][0]['bankTransactions']['amount'],'20.00')
        paid=self.service.list_rows(filters=[{'field':'payment_status','operator':'in','values':['paid']}])
        self.assertEqual(paid['rows'],[])
        self.assertEqual(paid['summary']['invoiceCount'],0)

    def test_missing_bank_member_prevents_partial_evidence_being_classified_as_paid(self):
        self.invoices(1)
        self.bank('known-bank', 10)
        self.relation('incomplete', ['candidate-1', 'known-bank', 'missing-bank'], ['invoice', 'bank', 'bank'])
        result = self.service.list_rows()
        self.assertEqual(result['classification']['used']['count'], 1)
        self.assertEqual(result['rows'][0]['paymentStatus']['code'], 'unclassified')

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
        pool = self.service.candidate_rows({})
        self.assertEqual(pool['summary']['invoiceCount'], 0)
        self.assertEqual(pool['rows'], [])
        exact = self.service.candidate_rows_by_invoice_ids(['candidate-1'])
        self.assertEqual(exact['rows'][0]['bankRelationStatus'], 'linked')
        self.assertEqual(exact['rows'][0]['usageStatus'], 'used')
        self.assertEqual(exact['rows'][0]['bankTransactions']['relationCount'], 0)

    def test_candidate_scope_preserves_dates_search_and_filters_but_replaces_classification(self):
        self.invoices(4)
        self.bank('bank-only')
        self.relation('bank-case', ['candidate-4', 'bank-only'], ['invoice', 'bank'])
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated candidate scope fixture'")
            tx.execute("update app.invoices set invoice_date='2026-08-01', invoice_month='2026-08-01' where legacy_mongo_id='candidate-3'")
        month_only = self.service.candidate_rows({'month': ['2026-09']})
        self.assertEqual({row['invoiceId'] for row in month_only['rows']}, {'candidate-1', 'candidate-2'})
        self.assertEqual(month_only['summary']['invoiceCount'], 2)
        self.assertEqual(month_only['summary']['totalWithTax'], '20.00')
        previous_month = self.service.candidate_rows({'month': ['2026-08']})
        self.assertEqual([row['invoiceId'] for row in previous_month['rows']], ['candidate-3'])
        previous_main = self.service.list_rows(month='2026-08', filters=[{'field': 'usage_status', 'operator': 'in', 'values': ['unused']}])
        self.assertEqual(previous_month['summary']['invoiceCount'], previous_main['summary']['invoiceCount'])
        self.assertEqual(previous_month['summary']['totalWithTax'], previous_main['summary']['totalWithTax'])
        filters = [
            {'field': 'seller_name', 'operator': 'in', 'values': ['测试销方']},
            {'field': 'usage_status', 'operator': 'in', 'values': ['used']},
            {'field': 'payment_group', 'operator': 'in', 'values': ['paid']},
            {'field': 'payment_status', 'operator': 'in', 'values': ['paid']},
        ]
        scope = {'month': ['2026-09'], 'invoice_date_from': ['2026-09-01'], 'invoice_date_to': ['2026-09-30'],
                 'keyword': ['CAND-'], 'filters': [json.dumps(filters)], 'page_size': ['1']}
        first = self.service.candidate_rows(scope)
        second = self.service.candidate_rows({**scope, 'page': ['2']})
        self.assertEqual(first['pagination']['total'], 2)
        self.assertEqual(first['summary']['totalWithTax'], '20.00')
        self.assertEqual({row['invoiceId'] for row in first['rows'] + second['rows']}, {'candidate-1', 'candidate-2'})
        main = self.service.list_rows(month='2026-09', keyword='CAND-', invoice_date_from='2026-09-01',
            invoice_date_to='2026-09-30', filters=[filters[0], {'field': 'usage_status', 'operator': 'in', 'values': ['unused']}])
        self.assertEqual(first['summary']['invoiceCount'], main['summary']['invoiceCount'])
        self.assertEqual(first['summary']['totalWithTax'], main['summary']['totalWithTax'])
        contradictory = self.service.candidate_rows({'filters': [json.dumps([{'field': 'oa_relation', 'operator': 'in', 'values': ['linked']}])]})
        self.assertEqual(contradictory['pagination']['total'], 0)
        self.assertEqual(contradictory['rows'], [])

    def test_multiple_relations_and_duplicate_members_do_not_admit_used_invoice_until_all_withdrawn(self):
        self.invoices(2)
        self.relation('bank-link', ['candidate-1', 'candidate-1', 'missing-bank'], ['invoice', 'invoice', 'bank'])
        self.relation('oa-link', ['candidate-1', 'missing-oa'], ['invoice', 'oa'])
        def candidate_ids():
            result = self.service.candidate_rows({})
            return [row['invoiceId'] for row in result['rows']]
        self.assertEqual(candidate_ids(), ['candidate-2'])
        self.connection.execute("update app.workbench_pair_relations set status='withdrawn' where case_id='bank-link'")
        self.assertEqual(candidate_ids(), ['candidate-2'])
        self.connection.execute("update app.workbench_pair_relations set status='withdrawn' where case_id='oa-link'")
        self.assertEqual(set(candidate_ids()), {'candidate-1', 'candidate-2'})
        self.assertEqual(self.service.candidate_rows({})['summary']['totalWithTax'], '20.00')

    def test_zero_amount_requires_actual_members_not_historical_matched_flag(self):
        self.invoices(1, amount=0)
        snapshot = self.repository.load_page(page=1, page_size=50, keyword=None, invoice_date_from=None, invoice_date_to=None, month=None, filters=[], sort_field="invoice_date", sort_direction="desc")
        facts = snapshot.groups[0]["payment_facts"]
        self.assertFalse(facts["has_bank"])
        self.assertFalse(facts["has_oa"])
        unused = self.service.list_rows()
        self.assertEqual(unused["rows"][0]["paymentStatus"]["code"], "waiting_payment")
        self.assertEqual(unused["classification"]["unused"]["count"], 1)
        self.assertEqual(unused["classification"]["groups"][0]["count"], 0)
        self.oa('zero-oa', 0)
        self.bank('zero-bank', 0)
        self.relation('zero-case', ['candidate-1','zero-oa','zero-bank'], ['invoice','oa','bank'])
        self.connection.execute("update app.workbench_pair_relations set amount_check='{\"matched\":false}'::jsonb")
        snapshot = self.repository.load_page(page=1, page_size=50, keyword=None, invoice_date_from=None, invoice_date_to=None, month=None, filters=[], sort_field="invoice_date", sort_direction="desc")
        self.assertTrue(snapshot.groups[0]["payment_facts"]["has_bank"])
        self.assertTrue(snapshot.groups[0]["payment_facts"]["has_oa"])
        self.assertEqual(snapshot.groups[0]["payment_facts"]["payment_comparison"], "equal")
        self.assertEqual(self.service.list_rows()["rows"][0]["paymentStatus"]["code"], "paid")
        self.connection.execute("update app.workbench_pair_relations set amount_check='{\"matched\":true}'::jsonb")
        snapshot = self.repository.load_page(page=1, page_size=50, keyword=None, invoice_date_from=None, invoice_date_to=None, month=None, filters=[], sort_field="invoice_date", sort_direction="desc")
        self.assertEqual(snapshot.groups[0]["payment_facts"]["payment_comparison"], "equal")
        self.assertEqual(self.service.list_rows()["rows"][0]["paymentStatus"]["code"], "paid")

    def test_candidates_reject_invalid_page_and_scope_filters(self):
        from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageError
        for query in ({'page':['0']},{'page_size':['201']},{'month':['invalid']},{'filters':[json.dumps([{'field':'invented','operator':'in','values':['x']}])]}):
            with self.assertRaises(InputInvoiceUsageError):
                self.service.candidate_rows(query)
