from __future__ import annotations

from datetime import date
import random
from typing import Literal
import unittest

from fin_ops_platform.services.workbench_free_matching_engine import (
    ActiveFormalRelationAnchor,
    FormalRelationFact,
    FormalRelationFactBatch,
    FormalRelationReference,
    FormalRelationSearchLimits,
    WorkbenchFreeMatchingEngine,
    relation_fingerprint,
)
from tests.workbench_deterministic_relation_fixtures import (
    YUNNAN_LIFU_CASE_ID,
    YUNNAN_LIFU_INVOICE_NO,
    omitted_thirteen_invoice_fixture,
    yunnan_lifu_520_fixture,
)


def fact(
    row_type: str,
    identity: str,
    amount_minor: int,
    *,
    fact_date: date = date(2026, 5, 1),
    currency: str = "CNY",
    direction: str = "expenditure",
    evidence: tuple[tuple[str, str], ...] = (("counterparty", "供应商A"),),
    references: tuple[FormalRelationReference, ...] = (),
    reversal_key: tuple[str, ...] | None = None,
    reversal_polarity: Literal["blue", "red"] | None = None,
) -> FormalRelationFact:
    return FormalRelationFact(
        row_type=row_type,
        canonical_object_identity=identity,
        row_id=identity,
        amount_minor=amount_minor,
        currency=currency,
        direction=direction,
        fact_date=fact_date,
        evidence_keys=evidence,
        references=references,
        source_version=f"source:{identity}",
        reversal_key=reversal_key,
        reversal_polarity=reversal_polarity,
    )


def batch(*facts: FormalRelationFact, withdrawals: frozenset[str] = frozenset()) -> FormalRelationFactBatch:
    return FormalRelationFactBatch(
        facts=tuple(facts),
        withdrawal_fingerprints=withdrawals,
        affected_scopes=("2026-05", "all"),
        source_versions=(("fixture", "v1"),),
    )


class WorkbenchFreeMatchingEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = WorkbenchFreeMatchingEngine()

    def test_exact_unique_output_reversal_creates_formal_relation(self) -> None:
        key = ("SELLER", "BUYER", "CNY", "9805000", "9250000", "555000", "0.06")
        blue = fact(
            "invoice",
            "blue-invoice",
            9_805_000,
            fact_date=date(2026, 6, 1),
            direction="income",
            reversal_key=key,
            reversal_polarity="blue",
        )
        red = fact(
            "invoice",
            "red-invoice",
            9_805_000,
            fact_date=date(2026, 6, 29),
            direction="income",
            reversal_key=key,
            reversal_polarity="red",
        )

        result = self.engine.plan_relations(batch(blue, red))

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].relation_mode, "output_invoice_reversal")
        self.assertEqual(result.plans[0].rule_code, "output_invoice_exact_reversal")

    def test_ambiguous_output_reversal_is_not_auto_matched(self) -> None:
        key = ("SELLER", "BUYER", "CNY", "9805000", "9250000", "555000", "0.06")
        blue = fact(
            "invoice",
            "blue-invoice",
            9_805_000,
            direction="income",
            reversal_key=key,
            reversal_polarity="blue",
        )
        red_one = fact(
            "invoice",
            "red-one",
            9_805_000,
            direction="income",
            reversal_key=key,
            reversal_polarity="red",
        )
        red_two = fact(
            "invoice",
            "red-two",
            9_805_000,
            direction="income",
            reversal_key=key,
            reversal_polarity="red",
        )

        result = self.engine.plan_relations(batch(blue, red_one, red_two))

        self.assertEqual(result.plans, ())
        self.assertEqual(
            dict(result.blocked_reason_counts)["ambiguous_output_invoice_reversal"],
            1,
        )

    def test_520_fixture_is_preserved_active_without_recreation(self) -> None:
        fixture = yunnan_lifu_520_fixture()

        result = self.engine.plan_relations(fixture)

        self.assertEqual(result.plans, ())
        self.assertEqual(result.preserved_active_count, 1)
        self.assertEqual(fixture.active_relations[0].case_id, YUNNAN_LIFU_CASE_ID)
        self.assertEqual(fixture.facts[1].evidence_keys[1], ("invoice_number", YUNNAN_LIFU_INVOICE_NO))

    def test_thirteen_omitted_invoice_fixture_is_exact_and_stays_unpaired(self) -> None:
        fixture = omitted_thirteen_invoice_fixture()

        result = self.engine.plan_relations(fixture)

        self.assertEqual(len(fixture.facts), 13)
        self.assertEqual(sum(item.amount_minor for item in fixture.facts), 170_949)
        self.assertEqual(result.plans, ())

    def test_explicit_direct_reference_matches_across_all_retained_history(self) -> None:
        invoice = fact(
            "invoice",
            "invoice-history",
            52_000,
            fact_date=date(2020, 1, 1),
            evidence=(),
        )
        oa = fact(
            "oa",
            "oa-current",
            1,
            fact_date=date(2026, 5, 1),
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="canonical_source",
                    value="oa-current:invoice-history",
                    target_row_type="invoice",
                    target_identity="invoice-history",
                ),
            ),
        )

        result = self.engine.plan_relations(batch(oa, invoice))

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].rule_code, "explicit_unique_reference")
        self.assertEqual(result.plans[0].amount_minor, 0)
        self.assertEqual(result.plans[0].scope_keys, ("2020-01", "2026-05"))

    def test_attachment_source_plan_preserves_exact_typed_binding(self) -> None:
        oa = fact("oa", "oa-exp-2206", 41_300, evidence=())
        invoice = fact(
            "invoice",
            "inv_imported_0058",
            6_000,
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="attachment_source",
                    value="derived_from_oa_id:oa-exp-2206",
                    target_row_type="oa",
                    target_identity="oa-exp-2206",
                ),
            ),
        )

        result = self.engine.plan_relations(batch(oa, invoice))

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(
            result.plans[0].oa_attachment_bindings,
            (("oa-exp-2206", "inv_imported_0058"),),
        )

    def test_plan_uses_all_only_when_member_months_are_unknown(self) -> None:
        invoice = fact(
            "invoice",
            "invoice-undated",
            52_000,
            fact_date=None,
            evidence=(),
        )
        oa = fact(
            "oa",
            "oa-undated",
            1,
            fact_date=None,
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="canonical_source",
                    value="oa-undated:invoice-undated",
                    target_row_type="invoice",
                    target_identity="invoice-undated",
                ),
            ),
        )

        result = self.engine.plan_relations(batch(oa, invoice))

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].scope_keys, ("all",))

    def test_composite_evidence_accepts_365_days_and_rejects_366(self) -> None:
        oa = fact("oa", "oa-window", 10_000, fact_date=date(2025, 5, 1))
        invoice_365 = fact("invoice", "invoice-365", 10_000, fact_date=date(2026, 5, 1))
        invoice_366 = fact("invoice", "invoice-366", 10_000, fact_date=date(2026, 5, 2))

        accepted = self.engine.plan_relations(batch(oa, invoice_365))
        rejected = self.engine.plan_relations(batch(oa, invoice_366))

        self.assertEqual(len(accepted.plans), 1)
        self.assertEqual(rejected.plans, ())

    def test_employee_reimbursement_evidence_uses_thirty_day_window(self) -> None:
        evidence = (("employee_reimbursement_payee", "樊祖芳"),)
        oa = fact("oa", "oa-employee", 74_706, fact_date=date(2026, 7, 1), evidence=evidence)
        bank_30 = fact("bank", "bank-30", 74_706, fact_date=date(2026, 7, 31), evidence=evidence)
        bank_31 = fact("bank", "bank-31", 74_706, fact_date=date(2026, 8, 1), evidence=evidence)

        accepted = self.engine.plan_relations(batch(oa, bank_30))
        rejected = self.engine.plan_relations(batch(oa, bank_31))

        self.assertEqual(len(accepted.plans), 1)
        self.assertEqual(rejected.plans, ())

    def test_more_than_six_members_can_form_one_unique_three_pane_closure(self) -> None:
        facts = (
            fact("oa", "oa-11", 1_100),
            fact("oa", "oa-22", 2_200),
            fact("oa", "oa-33", 3_300),
            fact("oa", "oa-44", 4_400),
            fact("bank", "bank-50", 5_000),
            fact("bank", "bank-60", 6_000),
            fact("invoice", "invoice-110", 11_000),
        )

        result = self.engine.plan_relations(batch(*facts))

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(len(result.plans[0].member_keys), 7)
        self.assertEqual(result.plans[0].amount_minor, 11_000)

    def test_arbitrary_two_by_two_by_two_exact_closure_is_supported(self) -> None:
        facts = (
            fact("oa", "oa-40", 4_000),
            fact("oa", "oa-60", 6_000),
            fact("bank", "bank-30", 3_000),
            fact("bank", "bank-70", 7_000),
            fact("invoice", "invoice-20", 2_000),
            fact("invoice", "invoice-80", 8_000),
        )

        result = self.engine.plan_relations(batch(*facts))

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].amount_minor, 10_000)
        self.assertEqual(set(result.plans[0].row_types), {"oa", "bank", "invoice"})

    def test_same_amount_competing_rows_are_ambiguous_and_create_nothing(self) -> None:
        fixture = batch(
            fact("oa", "oa-ambiguous", 10_000),
            fact("bank", "bank-a", 10_000),
            fact("bank", "bank-b", 10_000),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(result.plans, ())
        self.assertEqual(result.ambiguous_component_count, 1)

    def test_overlap_between_exact_single_and_exact_sum_is_ambiguous(self) -> None:
        fixture = batch(
            fact("oa", "oa-overlap", 10_000),
            fact("invoice", "invoice-exact", 10_000),
            fact("invoice", "invoice-part-a", 4_000),
            fact("invoice", "invoice-part-b", 6_000),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(result.plans, ())
        self.assertEqual(result.ambiguous_component_count, 1)

    def test_currency_direction_and_amount_only_are_fail_closed(self) -> None:
        currency_mismatch = batch(
            fact("oa", "oa-cny", 10_000, currency="CNY"),
            fact("invoice", "invoice-usd", 10_000, currency="USD"),
        )
        direction_mismatch = batch(
            fact("bank", "bank-out", 10_000, direction="expenditure"),
            fact("invoice", "invoice-in", 10_000, direction="income"),
        )
        amount_only = batch(
            fact("oa", "oa-amount", 10_000, evidence=()),
            fact("invoice", "invoice-amount", 10_000, evidence=()),
        )

        self.assertEqual(self.engine.plan_relations(currency_mismatch).plans, ())
        self.assertEqual(self.engine.plan_relations(direction_mismatch).plans, ())
        self.assertEqual(self.engine.plan_relations(amount_only).plans, ())

    def test_fuzzy_or_date_evidence_is_not_an_allowed_strong_key(self) -> None:
        with self.assertRaises(ValueError):
            fact("oa", "oa-fuzzy", 10_000, evidence=(("fuzzy", "供应商"),))
        with self.assertRaises(ValueError):
            fact("oa", "oa-date", 10_000, evidence=(("date", "2026-05-01"),))

    def test_duplicate_shared_reference_is_not_treated_as_unique(self) -> None:
        reference = FormalRelationReference(kind="order_reference", value="ORDER-1")
        fixture = batch(
            fact("oa", "oa-ref", 10_000, evidence=(), references=(reference,)),
            fact("bank", "bank-ref-a", 10_000, evidence=(), references=(reference,)),
            fact("bank", "bank-ref-b", 10_000, evidence=(), references=(reference,)),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(result.plans, ())

    def test_negative_refund_requires_direct_unique_original_reference(self) -> None:
        generic = batch(
            fact("bank", "bank-refund", -10_000),
            fact("invoice", "invoice-red", -10_000),
        )
        invoice = fact("invoice", "invoice-original", -10_000, evidence=())
        bank = fact(
            "bank",
            "bank-original",
            -10_000,
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="original_reference",
                    value="refund-original-1",
                    target_row_type="invoice",
                    target_identity="invoice-original",
                    original=True,
                ),
            ),
        )

        self.assertEqual(self.engine.plan_relations(generic).plans, ())
        explicit = self.engine.plan_relations(batch(bank, invoice))
        self.assertEqual(len(explicit.plans), 1)
        self.assertEqual(explicit.plans[0].rule_code, "explicit_unique_reference")

    def test_each_resource_budget_fails_closed_without_partial_plan(self) -> None:
        fixture = batch(fact("oa", "oa-budget", 10_000), fact("invoice", "invoice-budget", 10_000))
        limits = (
            FormalRelationSearchLimits(max_search_states=0),
            FormalRelationSearchLimits(max_working_bytes=0),
            FormalRelationSearchLimits(max_deadline_states=0),
        )

        for limit in limits:
            with self.subTest(limit=limit):
                result = self.engine.plan_relations(fixture, limit)
                self.assertEqual(result.plans, ())
                self.assertEqual(result.resource_limited_component_count, 1)

    def test_large_unrelated_fact_pool_does_not_exhaust_budget_before_explicit_relation(self) -> None:
        oa = fact("oa", "oa-exp-2206", 41_300, evidence=())
        invoice = fact(
            "invoice",
            "inv_imported_0058",
            6_000,
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="attachment_source",
                    value="derived_from_oa_id:oa-exp-2206",
                    target_row_type="oa",
                    target_identity="oa-exp-2206",
                ),
            ),
        )
        unrelated = tuple(
            fact(
                "bank",
                f"bank-unrelated-{index:04d}",
                10_000 + index,
                evidence=(("business_reference", f"UNIQUE-{index:04d}"),),
            )
            for index in range(700)
        )

        result = self.engine.plan_relations(batch(oa, invoice, *unrelated))

        self.assertEqual(result.resource_limited_component_count, 0)
        self.assertEqual(len(result.plans), 1)
        self.assertEqual(
            result.plans[0].oa_attachment_bindings,
            (("oa-exp-2206", "inv_imported_0058"),),
        )

    def test_input_order_does_not_change_plan_or_fingerprint(self) -> None:
        facts = [
            fact("oa", "oa-order", 10_000),
            fact("bank", "bank-order", 10_000),
            fact("invoice", "invoice-order", 10_000),
        ]
        expected = self.engine.plan_relations(batch(*facts)).plans

        for seed in range(10):
            shuffled = list(facts)
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(self.engine.plan_relations(batch(*shuffled)).plans, expected)

    def test_exact_typed_withdrawal_blocks_recreation_but_subset_and_row_type_do_not(self) -> None:
        oa = fact("oa", "shared-id", 10_000)
        invoice = fact("invoice", "invoice-withdraw", 10_000)
        exact = relation_fingerprint((oa.member_key, invoice.member_key))
        subset_or_wrong_type = relation_fingerprint((("bank", "shared-id"), invoice.member_key))

        blocked = self.engine.plan_relations(batch(oa, invoice, withdrawals=frozenset({exact})))
        allowed = self.engine.plan_relations(batch(oa, invoice, withdrawals=frozenset({subset_or_wrong_type})))

        self.assertEqual(blocked.plans, ())
        self.assertEqual(len(allowed.plans), 1)

    def test_legacy_withdrawal_cannot_suppress_immutable_oa_attachment_ownership(self) -> None:
        oa = fact("oa", "oa-exp-2206", 41_300, evidence=())
        invoice_amounts = (3_300, 3_300, 6_000, 14_500, 14_200)
        invoices = tuple(
            fact(
                "invoice",
                f"invoice-attachment-{index}",
                amount,
                evidence=(),
                references=(
                    FormalRelationReference(
                        kind="attachment_source",
                        value=f"derived_from_oa_id:oa-exp-2206:item:{index}",
                        target_row_type="oa",
                        target_identity="oa-exp-2206",
                    ),
                ),
            )
            for index, amount in enumerate(invoice_amounts)
        )
        exact = relation_fingerprint((oa.member_key, *(invoice.member_key for invoice in invoices)))

        result = self.engine.plan_relations(
            batch(oa, *invoices, withdrawals=frozenset({exact}))
        )

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].rule_code, "explicit_unique_reference")
        self.assertEqual(
            result.plans[0].oa_attachment_bindings,
            tuple(("oa-exp-2206", invoice.row_id) for invoice in invoices),
        )

    def test_explicit_reference_can_extend_one_active_relation_without_renaming_it(self) -> None:
        oa = fact("oa", "oa-active", 10_000)
        invoice = fact("invoice", "invoice-active", 10_000)
        bank = fact(
            "bank",
            "bank-extension",
            10_000,
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="canonical_source",
                    value="bank-to-oa",
                    target_row_type="oa",
                    target_identity="oa-active",
                ),
            ),
        )
        fixture = FormalRelationFactBatch(
            facts=(oa, invoice, bank),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="case:decision:historical-active",
                    member_keys=(oa.member_key, invoice.member_key),
                ),
            ),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].case_id, "case:decision:historical-active")
        self.assertEqual(result.plans[0].target_case_id, "case:decision:historical-active")
        self.assertEqual(len(result.plans[0].member_keys), 3)

    def test_active_oa_bank_relation_accepts_every_attachment_invoice_despite_rounding_delta(self) -> None:
        oa = fact("oa", "oa-exp-2321", 107_987, evidence=())
        bank = fact("bank", "bank-107987", 107_987, evidence=())
        invoice_amounts = (14_500, 14_500, 48_200, 1_800, 29_000)
        invoices = tuple(
            fact(
                "invoice",
                f"invoice-attachment-{index}",
                amount,
                evidence=(),
                references=(
                    FormalRelationReference(
                        kind="attachment_source",
                        value=f"oa-exp-2321:item:{0 if index < 2 else index - 1}",
                        target_row_type="oa",
                        target_identity="oa-exp-2321",
                    ),
                ),
            )
            for index, amount in enumerate(invoice_amounts)
        )
        fixture = FormalRelationFactBatch(
            facts=(oa, bank, *invoices),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="case:CASE-AUTO-0096",
                    member_keys=(oa.member_key, bank.member_key),
                ),
            ),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(len(result.plans), 1)
        plan = result.plans[0]
        self.assertEqual(plan.target_case_id, "case:CASE-AUTO-0096")
        self.assertEqual(len(plan.member_keys), 7)
        self.assertEqual(plan.amount_minor, 0)
        self.assertEqual(
            plan.oa_attachment_bindings,
            tuple(("oa-exp-2321", invoice.row_id) for invoice in invoices),
        )

    def test_employee_reimbursement_bank_completes_existing_oa_invoice_relation(self) -> None:
        employee_evidence = (("employee_reimbursement_payee", "樊祖芳"),)
        oa = fact(
            "oa",
            "oa-exp-2363",
            74_706,
            fact_date=date(2026, 7, 17),
            evidence=employee_evidence,
        )
        invoices = tuple(
            fact(
                "invoice",
                f"invoice-74706-{index}",
                amount,
                evidence=(),
                references=(
                    FormalRelationReference(
                        kind="attachment_source",
                        value=f"oa-exp-2363:item:{index}",
                        target_row_type="oa",
                        target_identity="oa-exp-2363",
                    ),
                ),
            )
            for index, amount in enumerate((30_287, 22_937, 20_743))
        )
        bank = fact(
            "bank",
            "txn_imported_1061",
            74_706,
            fact_date=date(2026, 8, 3),
            evidence=employee_evidence,
        )
        noisy_oas = tuple(
            fact(
                "oa",
                f"unpaired-employee-oa-{index}",
                10_000 + index,
                fact_date=date(2026, 8, 3),
                evidence=employee_evidence,
            )
            for index in range(20)
        )
        wrong_bank = fact(
            "bank",
            "txn_imported_wrong_amount",
            13_600,
            fact_date=date(2026, 8, 3),
            evidence=employee_evidence,
        )
        fixture = FormalRelationFactBatch(
            facts=(oa, bank, wrong_bank, *invoices, *noisy_oas),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="CASE-AUTO-0076EC3CA6BA0F837824",
                    member_keys=(oa.member_key, *(invoice.member_key for invoice in invoices)),
                ),
            ),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(len(result.plans), 1)
        plan = result.plans[0]
        self.assertEqual(plan.target_case_id, "CASE-AUTO-0076EC3CA6BA0F837824")
        self.assertEqual(plan.case_id, "CASE-AUTO-0076EC3CA6BA0F837824")
        self.assertEqual(plan.rule_code, "strong_evidence_exact_extension")
        self.assertEqual(plan.amount_minor, 0)
        self.assertEqual(set(plan.row_types), {"oa", "bank", "invoice"})
        self.assertIn(bank.member_key, plan.member_keys)
        self.assertNotIn(wrong_bank.member_key, plan.member_keys)
        self.assertEqual(result.resource_limited_component_count, 1)

    def test_active_extension_resource_limit_does_not_discard_independent_exact_case(self) -> None:
        dense_evidence = (("employee_reimbursement_payee", "高密度候选"),)
        dense_oa = fact("oa", "oa-dense", 100_000, evidence=dense_evidence)
        dense_invoice = fact("invoice", "invoice-dense", 100_000, evidence=dense_evidence)
        dense_banks = tuple(
            fact("bank", f"bank-dense-{index}", index + 1, evidence=dense_evidence)
            for index in range(18)
        )

        target_evidence = (("employee_reimbursement_payee", "樊祖芳"),)
        target_oa = fact("oa", "oa-target", 74_706, evidence=target_evidence)
        target_invoice = fact("invoice", "invoice-target", 74_706, evidence=target_evidence)
        target_bank = fact("bank", "bank-target", 74_706, evidence=target_evidence)
        fixture = FormalRelationFactBatch(
            facts=(
                dense_oa,
                dense_invoice,
                *dense_banks,
                target_oa,
                target_invoice,
                target_bank,
            ),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="case:000-dense",
                    member_keys=(dense_oa.member_key, dense_invoice.member_key),
                ),
                ActiveFormalRelationAnchor(
                    case_id="case:999-target",
                    member_keys=(target_oa.member_key, target_invoice.member_key),
                ),
            ),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].target_case_id, "case:999-target")
        self.assertIn(target_bank.member_key, result.plans[0].member_keys)
        self.assertGreaterEqual(result.resource_limited_component_count, 1)

    def test_same_row_type_noise_does_not_consume_cross_pane_edge_budget(self) -> None:
        evidence = (("employee_reimbursement_payee", "樊祖芳"),)
        target_oa = fact("oa", "oa-target-noise", 74_706, evidence=evidence)
        target_invoice = fact(
            "invoice",
            "invoice-target-noise",
            74_706,
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="attachment_source",
                    value="oa-target-noise:item:0",
                    target_row_type="oa",
                    target_identity="oa-target-noise",
                ),
            ),
        )
        target_bank = fact("bank", "bank-target-noise", 74_706, evidence=evidence)
        noisy_oas = tuple(
            fact("oa", f"oa-same-type-noise-{index}", 100_000 + index, evidence=evidence)
            for index in range(700)
        )
        fixture = FormalRelationFactBatch(
            facts=(target_oa, target_invoice, target_bank, *noisy_oas),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="case:target-noise",
                    member_keys=(target_oa.member_key, target_invoice.member_key),
                ),
            ),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].target_case_id, "case:target-noise")
        self.assertIn(target_bank.member_key, result.plans[0].member_keys)

    def test_active_extension_preserves_exact_sum_with_multiple_missing_pane_rows(self) -> None:
        evidence = (("employee_reimbursement_payee", "樊祖芳"),)
        oa = fact("oa", "oa-active-many-banks", 10_000, evidence=evidence)
        invoice = fact(
            "invoice",
            "invoice-active-many-banks",
            10_000,
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="attachment_source",
                    value="oa-active-many-banks:item:0",
                    target_row_type="oa",
                    target_identity="oa-active-many-banks",
                ),
            ),
        )
        bank_a = fact("bank", "bank-active-many-a", 3_000, evidence=evidence)
        bank_b = fact("bank", "bank-active-many-b", 7_000, evidence=evidence)
        fixture = FormalRelationFactBatch(
            facts=(oa, invoice, bank_a, bank_b),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="case:active-many-banks",
                    member_keys=(oa.member_key, invoice.member_key),
                ),
            ),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(
            set(result.plans[0].member_keys),
            {oa.member_key, invoice.member_key, bank_a.member_key, bank_b.member_key},
        )

    def test_active_extension_rejects_new_pane_that_matches_no_anchor_total(self) -> None:
        employee_evidence = (("employee_reimbursement_payee", "樊祖芳"),)
        oa = fact("oa", "oa-active-mismatch", 74_706, evidence=employee_evidence)
        invoice = fact(
            "invoice",
            "invoice-active-mismatch",
            73_967,
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="attachment_source",
                    value="oa-active-mismatch:item:0",
                    target_row_type="oa",
                    target_identity="oa-active-mismatch",
                ),
            ),
        )
        bank = fact("bank", "bank-active-mismatch", 74_705, evidence=employee_evidence)
        fixture = FormalRelationFactBatch(
            facts=(oa, invoice, bank),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="case:mismatch",
                    member_keys=(oa.member_key, invoice.member_key),
                ),
            ),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(result.plans, ())

    def test_composite_extension_is_fail_closed_for_ambiguous_or_complete_relations(self) -> None:
        evidence = (("employee_reimbursement_payee", "樊祖芳"),)
        oa = fact("oa", "oa-active-ambiguous", 74_706, evidence=evidence)
        invoice = fact("invoice", "invoice-active-ambiguous", 74_706, evidence=evidence)
        bank_a = fact("bank", "bank-active-a", 74_706, evidence=evidence)
        bank_b = fact("bank", "bank-active-b", 74_706, evidence=evidence)
        incomplete = FormalRelationFactBatch(
            facts=(oa, invoice, bank_a, bank_b),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="case:incomplete",
                    member_keys=(oa.member_key, invoice.member_key),
                ),
            ),
        )

        ambiguous = self.engine.plan_relations(incomplete)

        self.assertEqual(ambiguous.plans, ())
        self.assertGreaterEqual(ambiguous.ambiguous_component_count, 1)

        complete = FormalRelationFactBatch(
            facts=(oa, invoice, bank_a, bank_b),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="case:complete",
                    member_keys=(oa.member_key, invoice.member_key, bank_a.member_key),
                ),
            ),
        )

        preserved = self.engine.plan_relations(complete)

        self.assertEqual(preserved.plans, ())
        self.assertEqual(preserved.preserved_active_count, 1)

    def test_exact_withdrawal_blocks_composite_active_extension(self) -> None:
        evidence = (("employee_reimbursement_payee", "樊祖芳"),)
        oa = fact("oa", "oa-active-withdrawn", 74_706, evidence=evidence)
        invoice = fact("invoice", "invoice-active-withdrawn", 74_706, evidence=evidence)
        bank = fact("bank", "bank-active-withdrawn", 74_706, evidence=evidence)
        full_members = (oa.member_key, invoice.member_key, bank.member_key)
        fixture = FormalRelationFactBatch(
            facts=(oa, invoice, bank),
            active_relations=(
                ActiveFormalRelationAnchor(
                    case_id="case:withdrawn-extension",
                    member_keys=(oa.member_key, invoice.member_key),
                ),
            ),
            withdrawal_fingerprints=frozenset({relation_fingerprint(full_members)}),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(result.plans, ())

    def test_composite_active_extension_rejects_cross_case_member_overlap(self) -> None:
        evidence = (("employee_reimbursement_payee", "樊祖芳"),)
        oa_a = fact("oa", "oa-overlap-a", 74_706, evidence=evidence)
        invoice_a = fact("invoice", "invoice-overlap-a", 74_706, evidence=evidence)
        oa_b = fact("oa", "oa-overlap-b", 74_706, evidence=evidence)
        invoice_b = fact("invoice", "invoice-overlap-b", 74_706, evidence=evidence)
        bank = fact("bank", "bank-overlap", 74_706, evidence=evidence)
        fixture = FormalRelationFactBatch(
            facts=(oa_a, invoice_a, oa_b, invoice_b, bank),
            active_relations=(
                ActiveFormalRelationAnchor("case:overlap-a", (oa_a.member_key, invoice_a.member_key)),
                ActiveFormalRelationAnchor("case:overlap-b", (oa_b.member_key, invoice_b.member_key)),
            ),
        )

        result = self.engine.plan_relations(fixture)

        self.assertEqual(result.plans, ())
        self.assertEqual(result.ambiguous_component_count, 2)


if __name__ == "__main__":
    unittest.main()
