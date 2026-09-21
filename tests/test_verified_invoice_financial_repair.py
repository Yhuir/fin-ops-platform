from __future__ import annotations

import unittest
from copy import deepcopy
from decimal import Decimal

from fin_ops_platform.services.invoice_header_fact_repair_service import build_verified_financial_repair_plan
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    apply_verified_financial_repair,
    load_verified_financial_repair_snapshot,
)

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


def sample():
    invoice = dict(invoice_id='repair-1', invoice_type='input', invoice_code='053002400111',
                   invoice_no='23195398', digital_invoice_no=None, invoice_date='2026-01-13',
                   amount='0.33', signed_amount='0.33', tax_amount='3.67', total_with_tax='4.00',
                   tax_rate='9%', raw_payload={'normalized_payload': {'source_links':[{'source_id':'preserved'}]}})
    fact = dict(invoice, amount='3.67', tax_amount='0.33')
    source = dict(file_id='source-1', filename='tax.xlsx', sha256='a'*64, rows=[fact])
    cache = dict(source_attachment_key='cache-1', parser_version='old', invoices=[invoice])
    return invoice, source, cache


class VerifiedFinancialRepairTests(unittest.TestCase):
    def build(self, invoice=None, source=None, cache=None):
        base = sample()
        return build_verified_financial_repair_plan([invoice or base[0]], invoice_ids=['repair-1'],
            sources=[source or base[1]], cache_rows=[cache or base[2]])

    def test_swapped_fields_fixed_without_changing_identity_relations_or_total(self):
        plan = self.build()
        update = plan['updates'][0]
        self.assertEqual((update['amount'], update['tax_amount'], update['total_with_tax']), ('3.67','0.33','4.00'))
        self.assertEqual(update['identity_key'], '053002400111:23195398')
        self.assertEqual(update['raw_payload']['normalized_payload']['source_links'], [{'source_id':'preserved'}])
        self.assertEqual(plan['invalidate_cache_keys'], ['cache-1'])

    def test_missing_tax_is_not_zero_and_conflicting_originals_are_rejected(self):
        invoice, source, cache = sample()
        source['rows'][0]['tax_amount'] = None
        with self.assertRaisesRegex(ValueError, 'explicit financial'):
            self.build(source=source)
        invoice, source, cache = sample()
        other = deepcopy(source)
        other['rows'][0].update(amount='2.00', tax_amount='2.00')
        with self.assertRaisesRegex(ValueError, 'disagree'):
            build_verified_financial_repair_plan([invoice], invoice_ids=['repair-1'], sources=[source,other],cache_rows=[])

    def test_missing_target_date_or_total_changes_fail(self):
        invoice, source, cache = sample()
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            build_verified_financial_repair_plan([], invoice_ids=['repair-1'],sources=[source],cache_rows=[])
        source['rows'][0]['invoice_date']='2026-01-14'
        with self.assertRaisesRegex(ValueError, 'date/type'):
            self.build(source=source)
        source['rows'][0].update(invoice_date='2026-01-13',amount='4.67',total_with_tax='5.00')
        with self.assertRaisesRegex(ValueError, 'total'):
            self.build(source=source)

    def test_second_run_is_zero_and_changed_snapshot_changes_fingerprint(self):
        invoice, source, cache = sample()
        first=self.build()
        invoice.update(amount='3.67',signed_amount='3.67',tax_amount='0.33',raw_payload=first['updates'][0]['raw_payload'])
        again=build_verified_financial_repair_plan([invoice],invoice_ids=['repair-1'],sources=[source],cache_rows=[])
        self.assertEqual(again['updates'],[])
        self.assertEqual(again['invalidate_cache_keys'],[])
        self.assertNotEqual(first['source_fingerprint'],again['source_fingerprint'])


class VerifiedFinancialRepairPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url=require_postgres_test_database_url()
        apply_test_migrations(cls.url)

    def setUp(self):
        truncate_test_database(self.url)
        self.connection=PostgresConnection(PostgresSettings(database_url=self.url))
        self.addCleanup(self.connection.close)
        self.connection.execute("""insert into app.invoices(legacy_mongo_id,invoice_type,invoice_code,
            invoice_no,invoice_date,invoice_month,amount,signed_amount,tax_amount,total_with_tax,status,source_unique_key,source_links)
            values ('repair-1','input','053002400111','23195398','2026-01-13','2026-01-01',0.33,0.33,3.67,4,'pending',
                '053002400111:23195398','[{"source_id":"preserved"}]')""")
        self.connection.execute("""insert into app.oa_attachment_invoice_cache(source_attachment_key,parser_version,
            cache_schema_version,parsed_at,invoices) values ('cache-1','old','old',now(),
            '[{"invoice_code":"053002400111","invoice_no":"23195398","amount":"0.33","tax_amount":"3.67"}]')""")

    def plan(self, tx):
        return build_verified_financial_repair_plan(**load_verified_financial_repair_snapshot(tx,['repair-1']),
            invoice_ids=['repair-1'],sources=[sample()[1]])

    def test_transaction_rollback_cas_and_second_run_zero(self):
        with self.assertRaisesRegex(RuntimeError,'injected'):
            with self.connection.transaction() as tx:
                apply_verified_financial_repair(tx,self.plan(tx),operator_id='tester',reason='verified tax header')
                raise RuntimeError('injected')
        before=load_verified_financial_repair_snapshot(self.connection,['repair-1'])
        self.assertEqual(before['snapshot'][0]['amount'],Decimal('0.33'))
        self.assertEqual(len(before['cache_rows']),1)
        with self.connection.transaction() as tx:
            result=apply_verified_financial_repair(tx,self.plan(tx),operator_id='tester',reason='verified tax header')
        self.assertEqual(result,{'written_invoice_count':1,'invalidated_cache_count':1})
        current=self.connection.fetch_one("select amount,tax_amount,source_links from app.invoices where legacy_mongo_id='repair-1'")
        self.assertEqual(current['source_links'],[{'source_id':'preserved'}])
        self.assertEqual(current['tax_amount'],Decimal('0.33'))
        self.assertEqual(self.plan(self.connection)['updates'],[])
        self.assertEqual(self.plan(self.connection)['invalidate_cache_keys'],[])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.financial_fact_corrections where entity_type='invoices'")['n'],1)

    def test_existing_cli_verifies_original_and_commits_audited_repair_idempotently(self):
        import hashlib
        import io
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        from openpyxl import Workbook
        from fin_ops_platform.tools import import_audit_repair_ops as cli

        workbook=Workbook()
        workbook.active.title='发票基础信息'
        workbook.active.append(['发票代码','发票号码','开票日期','金额','税额','价税合计','销方识别号','购买方名称'])
        workbook.active.append(['053002400111','23195398','2026-01-13','3.67','0.33','4.00','seller','buyer'])
        stream=io.BytesIO()
        workbook.save(stream)
        content=stream.getvalue()
        base=['--repair-invoice-financial-source','source-1','--invoice-id','repair-1']
        source={'sha256':hashlib.sha256(content).hexdigest(),'stored_file_path':'source','original_filename':'tax.xlsx'}
        def run(args):
            output=io.StringIO()
            with patch.object(cli.PostgresSettings,'from_env',return_value=PostgresSettings(database_url=self.url)), \
                 patch.object(cli,'load_import_source_file',return_value=source), \
                 patch.object(cli,'_build_bank_repair_state_store',return_value=SimpleNamespace(read_import_file=lambda path:content)):
                self.assertEqual(cli.main(base+args,stdout=output),0)
            return json.loads(output.getvalue())
        plan=run(['--dry-run'])
        self.assertEqual(plan['update_count'],1)
        self.assertEqual(plan['updates'][0]['before']['tax_amount'],'3.670000')
        with self.assertRaisesRegex(RuntimeError,'changed after dry-run'):
            run(['--execute','--expected-fingerprint','stale','--operator-id','tester','--reason','verified original'])
        result=run(['--execute','--expected-fingerprint',plan['source_fingerprint'],'--operator-id','tester','--reason','verified original'])
        self.assertEqual(result['completion']['written_invoice_count'],1)
        self.assertEqual(run(['--dry-run'])['update_count'],0)
        self.assertEqual(self.connection.fetch_one("select count(*) n from audit.events where action='invoice_financial_source_repair'")['n'],1)
        source['sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'checksum differs'):
            run(['--dry-run'])
