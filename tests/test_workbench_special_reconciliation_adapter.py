from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DISPLAY_STATE_OPEN,
    DISPLAY_STATE_PAIRED,
    MATCH_DOMAIN_SPECIAL,
)
from fin_ops_platform.services.workbench_special_pair_rule_service import (
    CASH_TURNOVER_DETECTED,
    INTERNAL_TRANSFER_PAIR,
    OA_INVOICE_OFFSET_AUTO_MATCH,
    SALARY_PERSONAL_AUTO_MATCH,
)
from fin_ops_platform.services.workbench_special_reconciliation_adapter import (
    WorkbenchSpecialReconciliationAdapter,
)


EXTERNAL_TURNOVER_EVIDENCE = "external_turnover_evidence"


class WorkbenchSpecialReconciliationAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = WorkbenchSpecialReconciliationAdapter()

    def test_deterministic_internal_transfer_outputs_paired_special_decision(self) -> None:
        result = self.adapter.generate_decisions(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-out-001",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司建设银行账户",
                    "account_no": "62220001",
                    "debit_amount": "13000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
                {
                    "id": "bank-in-001",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司工商银行账户",
                    "account_no": "62220002",
                    "debit_amount": "",
                    "credit_amount": "13000.00",
                    "pay_receive_time": "2026-03-10 12:00:00",
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(len(result.decisions), 1)
        decision = result.decisions[0]
        self.assertEqual(decision.match_domain, MATCH_DOMAIN_SPECIAL)
        self.assertEqual(decision.rule_code, INTERNAL_TRANSFER_PAIR)
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.decision_status, DECISION_STATUS_PAIRED)
        self.assertEqual(decision.match_shape, "bank_bank")
        self.assertTrue(decision.payment_amount_closed)
        self.assertIsNone(decision.invoice_amount_closed)
        self.assertEqual(decision.bank_row_ids, ("bank-in-001", "bank-out-001"))
        self.assertEqual(result.claimed_row_ids_by_domain, {MATCH_DOMAIN_SPECIAL: {"bank-in-001", "bank-out-001"}})

    def test_salary_no_oa_batch_row_claims_special_domain_without_free_projection(self) -> None:
        result = self.adapter.generate_decisions(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-salary-001",
                    "debit_amount": "8500.00",
                    "credit_amount": "",
                    "summary": "工资",
                    "remark": "3月工资",
                    "counterparty_name": "张三",
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(len(result.decisions), 1)
        decision = result.decisions[0]
        self.assertEqual(decision.match_domain, MATCH_DOMAIN_SPECIAL)
        self.assertEqual(decision.rule_code, SALARY_PERSONAL_AUTO_MATCH)
        self.assertEqual(decision.display_state, DISPLAY_STATE_OPEN)
        self.assertEqual(decision.decision_status, DECISION_STATUS_OPEN)
        self.assertEqual(decision.match_shape, "single")
        self.assertEqual(decision.bank_row_ids, ("bank-salary-001",))
        self.assertEqual(result.claimed_row_ids_by_domain[MATCH_DOMAIN_SPECIAL], {"bank-salary-001"})

    def test_hint_only_external_and_cash_turnover_remain_open_but_claim_rows(self) -> None:
        result = self.adapter.generate_decisions(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-cash-001",
                    "debit_amount": "200.00",
                    "credit_amount": "",
                    "remark": "备用金",
                    "counterparty_name": "普通户名",
                },
                {
                    "id": "bank-external-001",
                    "category_code": "borrow_in_company_pending_repayment",
                    "category_label": "公司暂借款：待还款",
                    "debit_amount": "",
                    "credit_amount": "3000.00",
                    "remark": "外部借款",
                    "counterparty_name": "外部客户",
                },
            ],
            invoice_rows=[],
        )

        by_rule = {decision.rule_code: decision for decision in result.decisions}
        self.assertEqual(by_rule[CASH_TURNOVER_DETECTED].display_state, DISPLAY_STATE_OPEN)
        self.assertEqual(by_rule[CASH_TURNOVER_DETECTED].decision_status, DECISION_STATUS_OPEN)
        self.assertEqual(by_rule[EXTERNAL_TURNOVER_EVIDENCE].display_state, DISPLAY_STATE_OPEN)
        self.assertEqual(by_rule[EXTERNAL_TURNOVER_EVIDENCE].decision_status, DECISION_STATUS_OPEN)
        self.assertEqual(
            result.claimed_row_ids_by_domain[MATCH_DOMAIN_SPECIAL],
            {"bank-cash-001", "bank-external-001"},
        )

    def test_configured_oa_invoice_offset_outputs_paired_special_decision(self) -> None:
        result = self.adapter.generate_decisions(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-offset-001",
                    "applicant": "刘际涛",
                    "amount": "299.00",
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "invoice-offset-001",
                    "source_kind": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-offset-001",
                    "total_with_tax": "299.00",
                }
            ],
            settings={"offset_applicant_names": ["刘际涛"]},
        )

        self.assertEqual(len(result.decisions), 1)
        decision = result.decisions[0]
        self.assertEqual(decision.rule_code, OA_INVOICE_OFFSET_AUTO_MATCH)
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.decision_status, DECISION_STATUS_PAIRED)
        self.assertEqual(decision.match_shape, "oa_invoice")
        self.assertIsNone(decision.payment_amount_closed)
        self.assertTrue(decision.invoice_amount_closed)
        self.assertEqual(decision.oa_row_ids, ("oa-offset-001",))
        self.assertEqual(decision.invoice_row_ids, ("invoice-offset-001",))
        self.assertEqual(
            result.claimed_row_ids_by_domain[MATCH_DOMAIN_SPECIAL],
            {"oa-offset-001", "invoice-offset-001"},
        )

    def test_special_claim_beats_free_matching_for_same_row(self) -> None:
        special_candidate = {
            "scope_month": "2026-03",
            "rule_code": SALARY_PERSONAL_AUTO_MATCH,
            "status": "suppressed",
            "row_ids": ["bank-shared-001"],
            "oa_row_ids": [],
            "bank_row_ids": ["bank-shared-001"],
            "invoice_row_ids": [],
            "amount": "8500.00",
            "source_versions": {},
            "special_metadata": {"cost_policy": "normal", "no_oa_managed": True},
        }
        free_candidate = {
            "scope_month": "2026-03",
            "rule_code": "oa_bank_exact_amount",
            "status": "auto_closed",
            "row_ids": ["oa-free-001", "bank-shared-001"],
            "oa_row_ids": ["oa-free-001"],
            "bank_row_ids": ["bank-shared-001"],
            "invoice_row_ids": [],
            "amount": "8500.00",
            "source_versions": {},
        }

        adapted = self.adapter.adapt_candidates("2026-03", [special_candidate])
        remaining_free = self.adapter.exclude_claimed_free_candidates(
            [free_candidate],
            claimed_row_ids=adapted.claimed_row_ids_by_domain[MATCH_DOMAIN_SPECIAL],
        )

        self.assertEqual(remaining_free, [])
        self.assertEqual(adapted.claimed_row_ids_by_domain[MATCH_DOMAIN_SPECIAL], {"bank-shared-001"})


if __name__ == "__main__":
    unittest.main()
