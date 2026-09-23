"""Bank alias equality preserves the previous OR join's complete identity semantics."""
import unittest
from uuid import uuid4

from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import _fact_cte

from tests import test_bank_split_consumers_postgres as fixtures
from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url


class InvoiceBankAliasJoinPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        fixtures.BankSplitConsumersPostgresTests.setUp(self)

    def test_uuid_legacy_equal_collision_and_null_aliases_preserve_input_output_groups(self):
        bank_ids = [str(uuid4()) for _ in range(6)]
        aliases = [None, 'alias-legacy', bank_ids[2], 'alias-cross-first', bank_ids[3], None]
        for position, (bank_id, alias) in enumerate(zip(bank_ids, aliases, strict=True)):
            self.connection.execute("""insert into app.bank_transactions(id,legacy_mongo_id,account_no,
                txn_direction,counterparty_name_raw,amount,signed_amount,txn_date,txn_month,status)
                values(%s::uuid,%s,'alias-test','outflow','alias-test',%s,%s,'2026-04-29','2026-04-01','pending')""",
                (bank_id, alias, 11 + position, -(11 + position)))
        self.connection.execute("""insert into app.invoices(legacy_mongo_id,invoice_type,invoice_no,
            invoice_date,invoice_month,amount,signed_amount,total_with_tax,status)
            values('invoice-alias-test','input','ALIAS-001','2026-04-29','2026-04-01',1497.22,1497.22,1497.22,'pending')""")
        members = ['oa-interest','invoice-alias-test',self.principal,self.interest,
                   bank_ids[0],'alias-legacy',bank_ids[2],bank_ids[3],bank_ids[5]]
        self.connection.execute("update app.workbench_pair_relations set row_ids=%s::text[],row_types=%s::text[]",
            (members,['oa','invoice',*['bank']*(len(members)-2)]))
        expected = {self.principal,self.interest,bank_ids[0],'alias-legacy',bank_ids[2],
                    'alias-cross-first',bank_ids[3],bank_ids[5]}
        optimized_join = """            join app.bank_transaction_units bank on true
            join lateral (
                select distinct alias
                from (values (coalesce(bank.legacy_mongo_id, '')), (bank.id::text)) names(alias)
            ) bank_alias on bank_alias.alias = member.row_id"""
        reference_join = """            join app.bank_transaction_units bank
              on member.row_id in (coalesce(bank.legacy_mongo_id, ''), bank.id::text)"""
        # Empty formal members are forbidden; exercise the historical SQL behavior with a read-only VALUES input.
        with self.connection.transaction() as tx:
            tx.execute('set transaction read only')
            prefix = "with member(row_id) as(values('')) select bank.id from member "
            actual = tx.fetch_all(prefix+optimized_join+' order by bank.id')
            self.assertEqual(actual,tx.fetch_all(prefix+reference_join+' order by bank.id'))
            self.assertEqual({str(row['id']) for row in actual},{bank_ids[0],bank_ids[5]})
        for invoice_type in ('input','output'):

            for matched in ('true','false'):
                with self.subTest(invoice_type=invoice_type,matched=matched):
                    with self.connection.transaction() as tx:
                        tx.execute("set local fin_ops.correction_reason='isolated alias equivalence fixture'")
                        tx.execute('update app.invoices set invoice_type=%s',(invoice_type,))
                        tx.execute("update app.workbench_pair_relations set amount_check=jsonb_build_object('matched',%s::boolean)",(matched,))
                    optimized = _fact_cte(invoice_type=invoice_type,month=None,status_case="'pending'::text")
                    self.assertIn(optimized_join,optimized)
                    reference = optimized.replace(optimized_join,reference_join)
                    params = ('default',) if invoice_type=='input' else ()
                    with self.connection.transaction() as tx:
                        tx.execute('set transaction read only')
                        query = ' select bank_id,amount,amount_matched,is_split from raw_group_bank_rows order by bank_id'
                        actual = tx.fetch_all(optimized+query,params)
                        self.assertEqual(actual,tx.fetch_all(reference+query,params))
                        self.assertEqual({row['bank_id'] for row in actual},expected)
                        self.assertEqual(len(actual),len(expected))
                        self.assertEqual(sum(bool(row['is_split']) for row in actual),2)
                        self.assertTrue(all(row['amount_matched']==(matched=='true') for row in actual))
                        query = ' select * from final_rows order by group_key'
                        self.assertEqual(tx.fetch_all(optimized+query,params),tx.fetch_all(reference+query,params))
