import unittest
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

from fin_ops_platform.services.bank_split_cost_migration_service import BankSplitCostMigrationService
from fin_ops_platform.services.bank_transaction_split_relation_service import BankTransactionSplitRelationService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.cost_statistics_manual_allocation import (
    PostgresCostStatisticsManualAllocationRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_query import (
    PostgresOaPendingPaymentQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_formal_relation import (
    PostgresWorkbenchFormalRelationFactRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class BankSplitRelationsPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = require_postgres_test_database_url()
        apply_test_migrations(url)
        cls.connection = PostgresConnection(PostgresSettings(database_url=url, pool_enabled=False))

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_transaction_rebinds_members_revokes_cost_and_records_durable_event(self):
        self._run(False)

    def test_failed_transaction_preserves_relation_cost_and_has_no_split(self):
        self._run(True)

    def test_cost_migration_revokes_decision_without_changing_relation_and_is_idempotent(self):
        case = "test-cost-migration-" + str(uuid4())
        relation = {"case_id": case, "status": "active", "relation_mode": "manual_confirmed", "version": 4,
                    "month_scope": "2026-09", "row_ids": ["principal", "fee"], "row_types": ["bank", "bank"], "special_metadata": {"keep": True}}
        service = BankSplitCostMigrationService(
            allocation_repository_factory=PostgresCostStatisticsManualAllocationRepository,
            settings_snapshot_provider=lambda tx: {},
            effective_category_rows=lambda tx, **kwargs: {"principal": {"turnover_role": "external_turnover"}, "fee": {"turnover_role": ""}},
        )
        try:
            with self.connection.transaction() as tx:
                PostgresWorkbenchRelationRepository(tx).save_workbench_pair_relation_delta({"pair_relations": {case: relation}}, changed_case_ids=[case], emit_payment_status_reconcile=False)
                tx.execute("insert into app.cost_statistics_manual_allocations(relation_case_id,relation_version,source_fingerprint,oa_total,gross_outflow_total,wrong_payment_refund_total,net_outflow_total,unit_allocations,oa_amount_locks,created_by,updated_by) values (%s,4,%s,10,110,0,110,'[]','{}','test','test')", (case, "a" * 64))
            with self.assertRaisesRegex(RuntimeError, "rollback migration"):
                with self.connection.transaction() as tx:
                    report = service.run(tx, actor_id="tester", apply=True)
                    self.assertEqual(report["revoked_case_ids"], [case])
                    raise RuntimeError("rollback migration")
            with self.connection.transaction() as tx:
                self.assertIn(case, PostgresCostStatisticsManualAllocationRepository(tx).list_by_case_ids([case]))
                self.assertEqual(PostgresWorkbenchRelationRepository(tx).load_active_workbench_pair_relation_by_case_id(case)["version"], 4)
                report = service.run(tx, actor_id="tester", apply=True)
                self.assertEqual(report["mixed_case_ids"], [case])
                current = PostgresWorkbenchRelationRepository(tx).load_active_workbench_pair_relation_by_case_id(case)
                self.assertEqual(current["version"], 4)
                self.assertEqual(current["special_metadata"]["keep"], True)
                self.assertNotIn("bank_split_requires_cost_confirmation", current["special_metadata"])
                retired = PostgresCostStatisticsManualAllocationRepository(tx).list_by_case_ids([case])[case]
                self.assertEqual(retired["decision_mode"], "automatic")
                self.assertEqual(retired["version"], 2)
                self.assertEqual(service.run(tx, actor_id="tester", apply=True)["affected_count"], 0)
        finally:
            truncate_test_database(require_postgres_test_database_url())

    def _run(self, fail):
        parent = str(uuid4())
        parts = [{'id': str(uuid4()), 'category_code': 'loan', 'amount': '1000000.00'},
                 {'id': str(uuid4()), 'category_code': 'interest', 'amount': '1497.22'}]
        case = 'test-split-' + parent
        published = []
        source = {'transaction_id': parent, 'canonical_transaction_id': parent, 'amount': '1001497.22', 'parts': [], 'version': 0}
        after = {**source, 'parts': parts, 'version': 1}
        relation = {'case_id': case, 'status': 'active', 'relation_mode': 'manual_confirmed', 'version': 1,
                    'month_scope': '2026-09', 'row_ids': ['oa-test', parent], 'row_types': ['oa', 'bank'], 'special_metadata': {}}
        service = BankTransactionSplitRelationService(
            relation_repository_factory=PostgresWorkbenchRelationRepository,
            allocation_repository_factory=PostgresCostStatisticsManualAllocationRepository,
            batch_repository_factory=PostgresWorkbenchRepository,
            settings_snapshot_provider=lambda tx: {'paired_policy': {'version': 1, 'requirements_by_tag_code': {}}},
            effective_category_rows=lambda tx, settings, transaction_ids: {part['id']: {'effective_category_code': part['category_code']} for part in parts},
            turnover_split_migrator=lambda transaction, **kwargs: {},
            relation_delta_publisher=lambda *args, **kwargs: published.append(deepcopy(args)))
        try:
            with self.connection.transaction() as tx:
                tx.execute("insert into app.bank_transactions(id,account_no,txn_direction,counterparty_name_raw,amount,signed_amount,status,txn_date,txn_month) values (%s::uuid,'test','outflow','test',1001497.22,-1001497.22,'active','2026-09-23','2026-09-01')", (parent,))
                PostgresWorkbenchRelationRepository(tx).save_workbench_pair_relation_delta({'pair_relations': {case: relation}}, changed_case_ids=[case], emit_payment_status_reconcile=False)
                tx.execute("insert into app.cost_statistics_manual_allocations(relation_case_id,relation_version,source_fingerprint,oa_total,gross_outflow_total,wrong_payment_refund_total,net_outflow_total,unit_allocations,oa_amount_locks,created_by,updated_by) values (%s,1,%s,1497.22,1001497.22,0,1001497.22,'[]','{}','test','test')", (case, 'a' * 64))
                batch = {'batch_id': case, 'status': 'submitted', 'status_bucket': 'submitted',
                         'version': 1, 'scope_month': '2026-09', 'total_amount': '1001497.22',
                         'bank_transaction_ids': [parent], 'source_versions': {'proof': 'original'}}
                tx.execute('insert into app.bank_flow_rule_batches(batch_id,status,version,bank_transaction_ids,raw_payload) values (%s,\'submitted\',1,%s,%s)', (case, [parent], jsonb({'normalized_payload': batch})))
            try:
                with self.connection.transaction() as tx:
                    tx.execute('insert into app.bank_transaction_split_sets(bank_transaction_id,version,updated_by) values (%s::uuid,1,\'test\')', (parent,))
                    for position, part in enumerate(parts):
                        tx.execute('insert into app.bank_transaction_split_items(id,bank_transaction_id,category_code,amount,position) values (%s::uuid,%s::uuid,%s,%s,%s)', (part['id'], parent, part['category_code'], part['amount'], position))
                    result = service.apply(tx, before=source, after=after, actor_id='test')
                    self.assertFalse(published)
                    self.assertEqual(PostgresWorkbenchRelationRepository(tx).lock_canonical_relation_members([part['id'] for part in parts], row_types=['bank', 'bank']), [])
                    if fail:
                        raise RuntimeError('force rollback')
                service.after_commit(result)
            except RuntimeError:
                if not fail:
                    raise
            current = self.connection.fetch_one('select row_ids,version from app.workbench_pair_relations where case_id=%s', (case,))
            allocation = self.connection.fetch_one('select decision_mode, version from app.cost_statistics_manual_allocations where relation_case_id=%s', (case,))
            raw = self.connection.fetch_one('select amount from app.bank_transactions where id=%s::uuid', (parent,))
            self.assertEqual(raw['amount'], Decimal('1001497.22'))
            self.assertEqual(current['row_ids'], relation['row_ids'] if fail else ['oa-test', *[part['id'] for part in parts]])
            self.assertEqual(allocation['decision_mode'], 'manual' if fail else 'automatic')
            self.assertEqual(allocation['version'], 1 if fail else 2)
            self.assertEqual(len(published), 0 if fail else 1)
            batch = self.connection.fetch_one('select status,bank_transaction_ids,raw_payload from app.bank_flow_rule_batches where batch_id=%s', (case,))
            self.assertEqual(batch['status'], 'submitted' if fail else 'stale')
            self.assertEqual(batch['bank_transaction_ids'], [parent])
            self.assertEqual(batch['raw_payload']['normalized_payload']['source_versions'], {'proof': 'original'})
            if not fail:
                self.assertEqual(self.connection.fetch_one('select count(*) as n from audit.events where object_id=%s', (case,))['n'], 1)
                self.assertGreater(self.connection.fetch_one("select count(*) as n from job.outbox_events where payload->>'relation_case_id'=%s", (case,))['n'], 0)
                members = [part['id'] for part in parts]
                owner = PostgresWorkbenchRelationRepository(self.connection)
                self.assertEqual(set(owner.resolve_current_bank_unit_ids([parent])), set(members))
                self.assertEqual(owner.resolve_current_bank_unit_ids([members[1]]), [members[1]])
                reader = PostgresOaPendingPaymentQueryRepository(self.connection)
                self.assertEqual(reader.bank_transactions_for_command([members[1]])[0].amount, Decimal('1497.22'))
                self.assertEqual(reader.bank_transactions_for_command([parent]), [])
                facts = PostgresWorkbenchFormalRelationFactRepository(self.connection).load_batch(['2026-09'])
                child_facts = [fact for fact in facts.facts if fact.row_id in members]
                self.assertEqual({fact.canonical_object_identity for fact in child_facts}, set(members))
                self.assertEqual({fact.amount_minor for fact in child_facts}, {100000000, 149722})
        finally:
            truncate_test_database(require_postgres_test_database_url())
