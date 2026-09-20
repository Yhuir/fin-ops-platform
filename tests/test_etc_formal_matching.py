import unittest
from dataclasses import replace
from datetime import date, timedelta

from fin_ops_platform.services.postgres_repositories.workbench_formal_relation import (
    _bank_fact,
    _oa_fact,
)
from fin_ops_platform.services.workbench_free_matching_engine import (
    ActiveFormalRelationAnchor,
    FormalRelationFact,
    FormalRelationFactBatch,
    FormalRelationReference,
    FormalRelationSearchLimits,
    WorkbenchFreeMatchingEngine,
    relation_fingerprint,
)

from tests.test_workbench_formal_relation_repository import bank_row, oa_row


def sample_facts():
    oa = _oa_fact(oa_row(
        'oa-etc', amount='1711.33', applicant='申请人', fact_date=date(2026, 9, 15),
        payload={'apply_type': '支付申请', 'counterparty': '刘树刚'},
    ))
    raw_bank = bank_row('bank-etc', counterparty='刘树刚')
    raw_bank['project_id'] = None
    raw_bank.update(amount='1711.33', signed_amount='-1711.33', fact_date=date(2026, 9, 14))
    bank = _bank_fact(raw_bank)
    invoice = FormalRelationFact(
        row_type='invoice', canonical_object_identity='etc-summary-batch-1', row_id='etc-summary-batch-1',
        amount_minor=171133, currency='CNY', direction='expenditure', fact_date=date(2026, 7, 31),
        references=(FormalRelationReference('etc_batch_source', 'batch-1', 'oa', 'oa-etc'),),
    )
    return oa, bank, invoice


class EtcFormalMatchingTests(unittest.TestCase):
    def setUp(self):
        self.engine = WorkbenchFreeMatchingEngine()
        self.oa, self.bank, self.invoice = sample_facts()

    def plans(self, *facts, anchors=(), withdrawals=frozenset(), limits=None):
        return self.engine.plan_relations(FormalRelationFactBatch(
            facts=tuple(facts), active_relations=anchors, withdrawal_fingerprints=withdrawals,
        ), limits).plans

    def test_exact_source_creates_initial_group_without_bank(self):
        plans = self.plans(self.oa, self.invoice)
        self.assertEqual(len(plans), 1)
        self.assertEqual(set(plans[0].row_ids), {self.oa.row_id, self.invoice.row_id})
        self.assertIsNone(plans[0].target_case_id)

    def test_bank_already_present_and_late_bank_converge_to_same_case(self):
        source = self.plans(self.oa, self.invoice)[0]
        anchor = ActiveFormalRelationAnchor(source.case_id, source.member_keys)
        immediate = self.plans(self.oa, self.bank, self.invoice)[0]
        late = self.plans(self.oa, self.bank, self.invoice, anchors=(anchor,))[0]
        self.assertEqual(immediate.case_id, source.case_id)
        self.assertEqual(late.case_id, source.case_id)
        self.assertIsNone(immediate.target_case_id)
        self.assertEqual(late.target_case_id, source.case_id)
        self.assertEqual(set(immediate.row_types), {'oa', 'bank', 'invoice'})
        complete = ActiveFormalRelationAnchor(late.case_id, late.member_keys)
        self.assertEqual(self.plans(self.oa, self.bank, self.invoice, anchors=(complete,)), ())

    def test_ambiguous_bank_does_not_block_source(self):
        duplicate = replace(self.bank, canonical_object_identity='bank-2', row_id='bank-2')
        plans = self.plans(self.oa, self.bank, duplicate, self.invoice)
        self.assertEqual(len(plans), 1)
        self.assertEqual(set(plans[0].row_types), {'oa', 'invoice'})

    def test_resource_exhaustion_preserves_source(self):
        plans = self.plans(self.oa, self.invoice, limits=FormalRelationSearchLimits(max_search_states=0))
        self.assertEqual(len(plans), 1)
        self.assertEqual(set(plans[0].row_types), {'oa', 'invoice'})

    def test_source_amount_gap_uses_oa_payable_for_bank(self):
        invoice = replace(self.invoice, amount_minor=150000)
        good = self.plans(self.oa, self.bank, invoice)[0]
        wrong = self.plans(self.oa, replace(self.bank, amount_minor=150000), invoice)[0]
        self.assertIn('bank', good.row_types)
        self.assertNotIn('bank', wrong.row_types)
        self.assertEqual(invoice.amount_minor, 150000)

    def test_payee_does_not_use_applicant_and_short_name_window_is_30_days(self):
        self.assertIn(('payment_request_payee', '刘树刚'), self.oa.evidence_keys)
        self.assertNotIn(('payment_request_payee', '申请人'), self.oa.evidence_keys)
        late = replace(self.bank, fact_date=self.oa.fact_date + timedelta(days=31))
        self.assertNotIn('bank', self.plans(self.oa, late, self.invoice)[0].row_types)

    def test_wrong_direction_currency_or_explicit_account_excluded(self):
        for bank in (
            replace(self.bank, direction='income'), replace(self.bank, currency='USD'),
            replace(self.bank, counterparty_account='123456'),
        ):
            with self.subTest(bank=bank):
                oa = replace(self.oa, counterparty_account='654321')
                self.assertNotIn('bank', self.plans(oa, bank, self.invoice)[0].row_types)

    def test_withdrawn_bank_not_restored_but_source_is(self):
        rejected = relation_fingerprint((self.oa.member_key, self.bank.member_key, self.invoice.member_key))
        plans = self.plans(self.oa, self.bank, self.invoice, withdrawals=frozenset({rejected}))
        self.assertEqual(len(plans), 1)
        self.assertEqual(set(plans[0].row_types), {'oa', 'invoice'})

    def test_payment_adapter_preserves_registered_upload_references_without_ocr(self):
        from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, MongoOASettings
        adapter = MongoOAAdapter(settings=MongoOASettings(host='localhost', database='test'))
        document = {'_id': 'formal-document-not-draft', 'data': {
            'userName': '申请人', 'amount': '1711.33', 'cause': 'ETC还款',
            'applicationDate': '2026-09-15', 'beneficiary': '刘树刚',
            'processId': 'process-1', 'processStatus': '进行中',
            'field101': {'list': [{'name': 'invoice.pdf', 'response': {
                'extra': {'fileName': 'invoice.pdf', 'filePath': '/fileManager/exact.pdf'},
            }}]},
        }}
        record = adapter._build_payment_request_record(document, {}, respect_status_settings=False)
        self.assertEqual(record.source_attachment_paths, ['/fileManager/exact.pdf'])
        self.assertEqual(record.attachment_invoices, [])
        self.assertEqual(record.id, 'oa-pay-process-1')

    def test_etc_withdraw_preserves_source_and_blocks_pure_source_withdrawal(self):
        from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
        relation = {'case_id': 'case-etc', 'status': 'active', 'relation_mode': 'manual_confirmed',
                    'row_ids': ['oa-etc', 'bank-etc', 'etc-summary-batch-1'],
                    'row_types': ['oa', 'bank', 'invoice'],
                    'special_metadata': {'etc_batch_link': {'oa_row_id': 'oa-etc', 'external_etc_batch_id': 'batch-1'}}}
        service = WorkbenchPairRelationService(pair_relations={'case-etc': relation})
        preview = service.preview_withdraw_for_active_relation(relation)
        restored = preview['after_relations']
        self.assertEqual(len(restored), 1)
        self.assertEqual(set(restored[0]['row_ids']), {'oa-etc', 'etc-summary-batch-1'})
        self.assertEqual(restored[0]['special_metadata']['etc_batch_link']['external_etc_batch_id'], 'batch-1')
        self.assertTrue(service.is_immutable_oa_attachment_binding_relation(restored[0]))

    def test_proven_source_does_not_merge_existing_cases(self):
        other_oa = replace(self.oa, row_id='oa-other', canonical_object_identity='oa-other')
        other_inv = replace(self.invoice, row_id='inv-other', canonical_object_identity='inv-other', references=())
        anchors = (
            ActiveFormalRelationAnchor('case-1', (self.oa.member_key, other_inv.member_key)),
            ActiveFormalRelationAnchor('case-2', (other_oa.member_key, self.invoice.member_key)),
        )
        self.assertEqual(self.plans(self.oa, other_oa, self.invoice, other_inv, anchors=anchors), ())
