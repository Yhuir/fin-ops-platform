"""Bank split facts must reach classification, costs and invoice reads without changing cash facts."""
import json
import unittest
from decimal import Decimal
from uuid import uuid4

from fin_ops_platform.services.bank_details_canonical_query import (
    BankDetailsCanonicalQueryService,
    PostgresBankDetailsCanonicalQueryRepository,
)
from fin_ops_platform.services.cost_statistics_canonical_repository import PostgresCostStatisticsCanonicalRepository
from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy
from fin_ops_platform.services.pending_invoice_canonical_query import (
    PendingInvoiceCanonicalQueryService,
    PostgresPendingInvoiceCanonicalRepository,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class BankSplitConsumersPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.addCleanup(truncate_test_database, self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.parent, self.principal, self.interest = str(uuid4()), str(uuid4()), str(uuid4())
        self.settings = {
            "access_control_version": 1, "page_access_accounts": [],
            "bank_transaction_tags": {"definitions": [
                {"code": "principal-custom", "label": "本金", "path": ["外部往来款付款", "归还借款"],
                 "status": "active", "direction": "expense", "output_primary_label": "外部往来款付款", "output_sub_label": "归还借款",
                 "turnover_role": "external_turnover", "turnover_action_type": "repaid", "turnover_family": "bank", "output_third_label": "银行往来", "rules": {}},
                {"code": "interest-custom", "label": "利息", "path": ["费用", "利息"],
                 "status": "active", "direction": "expense", "output_primary_label": "费用", "output_sub_label": "利息", "rules": {}},
            ]},
            "pending_invoice_tag_groups": {"no_invoice_required": ["principal-custom"]},
            "cost_statistics_project_cost_scope": {"version": 1, "selected_tag_codes": ["interest-custom"]},
        }
        self.connection.execute("insert into app.app_settings(settings_key,settings_payload) values ('app_settings',%s::jsonb)", (json.dumps(self.settings),))
        self.connection.execute("""insert into app.bank_transactions
          (id,legacy_mongo_id,account_no,txn_direction,counterparty_name_raw,amount,signed_amount,balance,
           txn_date,txn_month,trade_time,status,currency,raw_payload)
          values (%s::uuid,'bank-parent','622200008106','outflow','银行',1001497.22,-1001497.22,123.45,
                  '2026-04-29','2026-04-01','2026-04-29 11:25:53+08','active','CNY','{}'::jsonb)""", (self.parent,))
        self.connection.execute("insert into app.bank_transaction_split_sets(bank_transaction_id,version,updated_by) values (%s::uuid,1,'test')", (self.parent,))
        self.connection.execute("""insert into app.bank_transaction_split_items(id,bank_transaction_id,category_code,amount,position)
          values (%s::uuid,%s::uuid,'principal-custom',1000000.00,0),(%s::uuid,%s::uuid,'interest-custom',1497.22,1)""", (self.principal,self.parent,self.interest,self.parent))
        self.connection.execute("""insert into app.oa_applications
          (oa_source_id,form_id,form_type,row_id,status,workflow_status,applicant,application_date,scope_month,
           approved_at,project_name,amount,currency,normalized_payload,raw_payload)
          values ('oa-interest','oa-interest','支付申请','oa-interest','active','completed','测试申请人',
                  '2026-04-29','2026-04-01','2026-04-29 10:00:00+08','测试项目',1497.22,'CNY',
                  '{"id":"oa-interest","project_name":"测试项目","amount":"1497.22","expense_type":"费用","expense_content":"利息"}'::jsonb,'{}'::jsonb)""")
        self.connection.execute("""insert into app.workbench_pair_relations
          (case_id,relation_mode,status,row_ids,row_types,month_scope,special_metadata)
          values ('split-case','manual_confirmed','active',%s::text[],array['oa','bank','bank'],'2026-04-01',
                  '{"bank_split_requires_cost_confirmation":true}'::jsonb)""", (["oa-interest",self.principal,self.interest],))

    def test_turnover_extra_identity_migrates_with_principal_child(self):
        from fin_ops_platform.services.postgres_repositories.turnover_bank_split import (
            PostgresTurnoverBankSplitRepository,
        )
        from fin_ops_platform.services.turnover_relation_service import TurnoverRelationService
        old_relation = TurnoverRelationService._relation_id(status="unclosed", source="system", row_ids=["bank-parent"])
        new_relation = TurnoverRelationService._relation_id(status="unclosed", source="system", row_ids=[self.principal])
        self.connection.execute("insert into app.turnover_ledger_extras(ledger_key,extra_payload) values (%s,%s::jsonb)",
            (old_relation, json.dumps({"relation_id": old_relation, "note":"保留备注", "interest_rate_type":"annual", "interest_rate_value":"0.05"})))
        before = {"transaction_id":"bank-parent", "canonical_transaction_id":self.parent,
            "amount":"1001497.22", "category_code":"principal-custom", "direction":"outflow", "parts":[]}
        after = {**before,"parts":[{"id":self.principal,"category_code":"principal-custom","amount":"1000000.00"},
            {"id":self.interest,"category_code":"interest-custom","amount":"1497.22"}]}
        with self.connection.transaction() as tx:
            result = PostgresTurnoverBankSplitRepository(tx).apply(before=before,after=after,actor_id="test")
        self.assertEqual(result["migrated_extras"], [{"before":old_relation,"after":new_relation}])
        extra = self.connection.fetch_one("select ledger_key,extra_payload from app.turnover_ledger_extras")
        self.assertEqual(extra["ledger_key"],new_relation)
        self.assertEqual(extra["extra_payload"]["note"],"保留备注")
        self.assertEqual(extra["extra_payload"]["interest_rate_value"],"0.05")
        event = self.connection.fetch_one("select event_type from app.turnover_relation_events")
        self.assertEqual(event["event_type"], "bank_split_extra_migrated")
        from fin_ops_platform.services.turnover_ledger_query_service import TurnoverLedgerQueryService
        detail = TurnoverLedgerQueryService(connection=self.connection).get_relation_detail(new_relation)
        self.assertEqual(detail["bank_rows"][0]["id"], "bank-parent")
        self.assertEqual(detail["bank_rows"][0]["amount"], "1001497.22")

    def test_turnover_extra_conflict_rolls_back_without_overwriting_either_owner(self):
        from fin_ops_platform.services.bank_transaction_split_service import BankTransactionSplitError
        from fin_ops_platform.services.postgres_repositories.turnover_bank_split import (
            PostgresTurnoverBankSplitRepository,
        )
        from fin_ops_platform.services.turnover_relation_service import TurnoverRelationService
        old_id = TurnoverRelationService._relation_id(status="unclosed", source="system", row_ids=["bank-parent"])
        new_id = TurnoverRelationService._relation_id(status="unclosed", source="system", row_ids=[self.principal])
        for ledger_key in (old_id,new_id):
            self.connection.execute("insert into app.turnover_ledger_extras(ledger_key,extra_payload) values (%s,%s::jsonb)",
                (ledger_key,json.dumps({"relation_id":ledger_key,"note":ledger_key})))
        before = {"transaction_id":"bank-parent", "canonical_transaction_id":self.parent,
            "amount":"1001497.22", "category_code":"principal-custom", "direction":"outflow", "parts":[]}
        after = {**before,"parts":[{"id":self.principal,"category_code":"principal-custom","amount":"1000000.00"},
            {"id":self.interest,"category_code":"interest-custom","amount":"1497.22"}]}
        with self.assertRaises(BankTransactionSplitError) as error, self.connection.transaction() as tx:
            PostgresTurnoverBankSplitRepository(tx).apply(before=before,after=after,actor_id="test")
        self.assertEqual(error.exception.code, "turnover_split_extra_conflict")
        extras = self.connection.fetch_all("select ledger_key,extra_payload from app.turnover_ledger_extras")
        self.assertEqual(len(extras),2)
        self.assertTrue(all(row["extra_payload"]["note"] == row["ledger_key"] for row in extras))

    def test_cost_detail_uses_parent_cash_amount_for_child_identity(self):
        from fin_ops_platform.services.cost_statistics_query_service import CostStatisticsQueryService
        service = CostStatisticsQueryService(canonical_repository=PostgresCostStatisticsCanonicalRepository(self.connection))
        detail = service.get_bank_transaction_detail(self.interest, view="time", scope="all")
        self.assertEqual(detail["bank_transaction"]["id"], "bank-parent")
        self.assertEqual(detail["bank_transaction"]["bank_transaction_unit_id"], self.interest)
        self.assertEqual(detail["bank_transaction"]["amount"], "1001497.22")

    def test_purpose_view_and_category_preserve_bank_financial_fact(self):
        rows = self.connection.fetch_all("select * from app.bank_transaction_units order by split_position")
        self.assertEqual([str(row['id']) for row in rows], [self.principal,self.interest])
        self.assertEqual(sum(row['amount'] for row in rows), Decimal('1001497.22'))
        self.assertEqual(sum(row['signed_amount'] for row in rows), Decimal('-1001497.22'))
        with self.connection.transaction() as tx:
            categories = PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows(tx,settings=self.settings,transaction_ids=[self.principal,self.interest])
        self.assertEqual(categories[self.principal]['turnover_role'],'external_turnover')
        self.assertEqual(categories[self.interest]['effective_category_code'],'interest-custom')
        original = self.connection.fetch_one('select amount,balance from app.bank_transactions where id=%s::uuid',(self.parent,))
        self.assertEqual(original, {'amount':Decimal('1001497.22'),'balance':Decimal('123.45')})

    def test_parent_list_filters_child_tag_without_extra_rows(self):
        query = BankDetailsCanonicalQueryService(repository=PostgresBankDetailsCanonicalQueryRepository(self.connection))
        payload = query.transactions_payload(account_key=None,date_from=None,date_to=None,keyword=None,
            category_code='interest-custom',category_primary_label=None,category_sub_label=None,category_third_label=None,page=1,page_size=10)
        self.assertEqual(payload['pagination']['total'],1)
        self.assertEqual(len(payload['rows']),1)
        self.assertEqual(len(payload['rows'][0]['bank_split_parts']),2)
        self.assertEqual(payload['rows'][0]['id'],'bank-parent')

    def test_cost_only_receives_interest_and_requires_manual_confirmation(self):
        policy = CostStatisticsPolicy(PostgresCostStatisticsCanonicalRepository(self.connection).load_snapshot())
        self.assertEqual(policy.serialized_cost_rows,[])
        self.assertEqual(len(policy.manual_allocation_tasks),1)
        task = policy.manual_allocation_tasks[0]
        self.assertEqual(task['net_outflow_total'],'1497.22')
        self.assertEqual([row['transaction_id'] for row in task['bank_events']],[self.interest])
        self.assertIsNone(task['source_allocations'])

    def test_pending_invoice_query_and_detail_accept_child_identity(self):
        query = PendingInvoiceCanonicalQueryService(repository=PostgresPendingInvoiceCanonicalRepository(self.connection))
        payload = query.rows({'direction':['expense'],'filter':['all'],'page':['1'],'page_size':['50']})
        self.assertEqual(len(payload['rows']), 1)
        self.assertEqual(payload['rows'][0]['bank_transactions']['payment_summary']['paid_total'], '1497.22')
        bank = payload['rows'][0]['bank_transactions']['primary']
        self.assertEqual(bank['bank_transaction_id'], 'bank-parent')
        self.assertEqual(bank['parent_amount'], '1001497.22')
        self.assertEqual(bank['bank_split_version'], 1)
        self.assertEqual({part['id'] for part in bank['bank_split_parts']}, {self.principal,self.interest})
        self.assertEqual(bank['bank_split_parts'][1]['category_path'], ['费用', '利息'])
        for bank_summary in payload['rows'][0]['bank_transactions']['summaries']:
            self.assertEqual(bank_summary['bank_transaction_id'], 'bank-parent')
            self.assertEqual(bank_summary['bank_split_version'], 1)

        detail = query.bank_transaction_detail(self.interest)
        self.assertEqual(detail['sections'][0]['bank_transaction_id'],'bank-parent')
        relation = query.relation_detail(self.interest,direction='expense',kind='bank')
        self.assertEqual(len(relation['sections']),1)
        self.assertEqual(relation['sections'][0]['bank_transaction_id'],'bank-parent')

    def test_pending_child_command_uses_canonical_units_and_replays_idempotently(self):
        from fin_ops_platform.services.imports import ImportNormalizationService
        from fin_ops_platform.services.pending_invoice_service import (
            PendingInvoiceApplicationService,
            PendingInvoiceError,
        )
        from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
        with self.connection.transaction() as tx:
            tx.execute("set local fin_ops.correction_reason='isolated test income fixture'")
            tx.execute("update app.bank_transactions set txn_direction='inflow',signed_amount=amount,status='pending' where id=%s::uuid", (self.parent,))
        reader = PostgresCoreRepository(self.connection).list_bank_transaction_units_by_ids
        reads = []
        def units(ids):
            reads.append(list(ids))
            return reader(ids)
        service = PendingInvoiceApplicationService(import_service=ImportNormalizationService(),bank_units_by_ids=units)
        payload = {'request_id':'child-status','status_code':'income_no_invoice_required'}
        result = service.confirm_income_status_override(transaction_id=self.interest,payload=payload,actor_id='test')
        self.assertEqual(result['transaction_id'],self.interest)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(service.command_store['child-status']['income_status_override']['transaction_id'],self.interest)
        self.assertEqual(service.confirm_income_status_override(transaction_id=self.interest,payload=payload,actor_id='test'),result)
        self.assertEqual(reads,[[self.interest],[self.interest]])
        with self.assertRaises(PendingInvoiceError) as error:
            service.confirm_income_status_override(transaction_id='missing',payload=payload,actor_id='test')
        self.assertEqual(error.exception.status_code,404)

    def test_import_withdrawal_waits_for_relation_lock_before_parent_and_rejects_changed_children(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event

        from fin_ops_platform.services.postgres_repositories.bank_import_withdrawal import (
            BankImportWithdrawalStateChanged,
            PostgresBankImportWithdrawalRepository,
        )
        from fin_ops_platform.services.postgres_repositories.workbench_relation import (
            PostgresWorkbenchRelationRepository,
        )
        batch = str(uuid4())
        self.connection.execute("insert into app.import_batches(id,batch_type,source_name,imported_by,status,imported_at) values(%s::uuid,'bank_transaction','test','test','completed',now())", (batch,))
        self.connection.execute("update app.bank_transactions set source_batch_id=%s::uuid where id=%s::uuid", (batch,self.parent))
        self.connection.execute("insert into app.import_batch_rows(import_batch_id,row_no,source_record_type,decision,linked_object_type,linked_object_id) values(%s::uuid,1,'bank','created','bank_transaction','bank-parent')", (batch,))
        observed = Event()
        class WatchingRepository(PostgresBankImportWithdrawalRepository):
            def _created_transaction_rows(inner,batch_uuid,batch_id,*,for_update):
                rows = super()._created_transaction_rows(batch_uuid,batch_id,for_update=for_update)
                if not for_update:
                    observed.set()
                return rows
        def withdraw_read():
            with self.connection.transaction() as tx:
                tx.execute("set local lock_timeout='3s'")
                return WatchingRepository(tx).created_transactions(batch,batch)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.connection.transaction() as tx:
                tx.execute("set local lock_timeout='2s'")
                PostgresWorkbenchRelationRepository(tx).acquire_relation_member_locks(
                    ['bank-parent',self.parent,self.principal,self.interest],row_types=['bank']*4,case_ids=['split-case'])
                future = pool.submit(withdraw_read)
                self.assertTrue(observed.wait(2))
                tx.fetch_one("select id from app.bank_transactions where id=%s::uuid for update", (self.parent,))
                tx.execute("update app.bank_transaction_split_items set id=%s::uuid where id=%s::uuid", (str(uuid4()),self.interest))
            with self.assertRaises(BankImportWithdrawalStateChanged):
                future.result(timeout=4)
        self.assertEqual(self.connection.fetch_one("select count(*) as count from app.bank_transactions")['count'],1)
