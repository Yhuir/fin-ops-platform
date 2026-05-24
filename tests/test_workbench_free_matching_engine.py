from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from fin_ops_platform.services.workbench_free_matching_engine import WorkbenchFreeMatchingEngine
from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DISPLAY_STATE_OPEN,
    DISPLAY_STATE_PAIRED,
    MATCH_DOMAIN_FREE,
    WARNING_INVOICE_AMOUNT_MISMATCH,
)


def oa(row_id: str, amount: str, *, month: str = "2026-03", reason: str = "星河项目 杭州ABC广告") -> dict[str, object]:
    return {
        "row_id": row_id,
        "amount": amount,
        "direction": "expenditure",
        "month": month,
        "applicant": "张三",
        "project_name": "星河项目",
        "reason": reason,
    }


def bank(
    row_id: str,
    amount: str,
    *,
    month: str = "2026-03",
    counterparty: str = "杭州ABC广告有限公司",
    direction: str = "expenditure",
) -> dict[str, object]:
    return {
        "row_id": row_id,
        "amount": amount,
        "direction": direction,
        "trade_month": month,
        "counterparty": counterparty,
        "summary": "星河项目付款",
        "remark": "张三报销",
    }


def invoice(
    row_id: str,
    amount: str,
    *,
    month: str = "2026-03",
    seller_name: str = "杭州ABC广告有限公司",
    source_oa_row_id: str | None = None,
    source_kind: str = "invoice_import",
) -> dict[str, object]:
    row: dict[str, object] = {
        "row_id": row_id,
        "amount": amount,
        "direction": "expenditure",
        "invoice_month": month,
        "seller_name": seller_name,
        "source_kind": source_kind,
    }
    if source_oa_row_id:
        row["source_oa_row_id"] = source_oa_row_id
    return row


class WorkbenchFreeMatchingEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = WorkbenchFreeMatchingEngine()

    def test_exact_oa_bank_invoice_one_to_one_in_five_month_window_is_paired(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [oa("oa-1", "1200.00", month="2026-01")],
            [bank("bk-1", "1200.00", month="2026-03")],
            [invoice("iv-1", "1200.00", month="2026-05")],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.decision_status, DECISION_STATUS_PAIRED)
        self.assertEqual(decision.match_domain, MATCH_DOMAIN_FREE)
        self.assertEqual(decision.match_shape, "oa_bank_invoice")
        self.assertEqual(decision.row_ids, ("oa-1", "bk-1", "iv-1"))
        self.assertEqual(decision.scope_month, "2026-03")
        self.assertTrue(decision.payment_amount_closed)
        self.assertTrue(decision.invoice_amount_closed)

    def test_oa_bank_multiple_invoices_unique_exact_sum_is_paired(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [oa("oa-1", "1200.00")],
            [bank("bk-1", "1200.00")],
            [
                invoice("iv-1", "700.00"),
                invoice("iv-2", "500.00"),
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.match_shape, "oa_bank_invoice")
        self.assertEqual(decision.row_ids, ("oa-1", "bk-1", "iv-1", "iv-2"))
        self.assertEqual(decision.invoice_row_ids, ("iv-1", "iv-2"))
        self.assertTrue(decision.invoice_amount_closed)

    def test_oa_attachment_invoices_pair_with_bank_and_warn_when_invoice_sum_differs(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [oa("oa-1", "1200.00")],
            [bank("bk-1", "1200.00")],
            [
                invoice("iv-1", "700.00", source_oa_row_id="oa-1", source_kind="oa_attachment_invoice"),
                invoice("iv-2", "400.00", source_oa_row_id="oa-1", source_kind="oa_attachment_invoice"),
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.rule_code, "oa_attachment_invoice_with_bank")
        self.assertTrue(decision.payment_amount_closed)
        self.assertFalse(decision.invoice_amount_closed)
        self.assertEqual([warning.code for warning in decision.warnings], [WARNING_INVOICE_AMOUNT_MISMATCH])

    def test_oa_bank_and_oa_invoice_evidence_upgrade_to_single_three_way_decision(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [oa("oa-1", "1200.00")],
            [bank("bk-1", "1200.00", counterparty="张三")],
            [invoice("iv-1", "1200.00", seller_name="杭州ABC广告有限公司")],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.match_shape, "oa_bank_invoice")
        self.assertEqual(decision.row_ids, ("oa-1", "bk-1", "iv-1"))
        self.assertNotIn("oa_bank", {item.match_shape for item in decisions})
        self.assertNotIn("oa_invoice", {item.match_shape for item in decisions})
        self.assertEqual(decision.evidence["three_way_evidence"], "bridged_by_oa")

    def test_competing_adjacent_month_invoice_keeps_affected_rows_open(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [oa("oa-1", "1200.00")],
            [bank("bk-1", "1200.00")],
            [
                invoice("iv-1", "1200.00", month="2026-02"),
                invoice("iv-2", "1200.00", month="2026-04"),
            ],
        )

        self.assertEqual({decision.display_state for decision in decisions}, {DISPLAY_STATE_OPEN})
        self.assertEqual({decision.decision_status for decision in decisions}, {DECISION_STATUS_OPEN})
        self.assertEqual({decision.row_ids for decision in decisions}, {("oa-1",), ("bk-1",), ("iv-1",), ("iv-2",)})
        blockers = [blocker["code"] for decision in decisions for blocker in decision.blockers]
        self.assertIn("multiple_three_way_candidates", blockers)

    def test_income_rows_are_ignored_by_free_matching(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [oa("oa-1", "1200.00")],
            [bank("bk-income", "1200.00", direction="income")],
            [invoice("iv-1", "800.00")],
        )

        self.assertEqual(decisions, [])

    def test_two_way_fallback_runs_only_after_three_way_cannot_uniquely_form(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [oa("oa-1", "1200.00")],
            [bank("bk-1", "1200.00")],
            [invoice("iv-1", "800.00")],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.match_shape, "oa_bank")
        self.assertEqual(decision.row_ids, ("oa-1", "bk-1"))
        self.assertTrue(decision.payment_amount_closed)
        self.assertIsNone(decision.invoice_amount_closed)

    def test_generate_decisions_does_not_mutate_input_rows(self) -> None:
        oa_rows = [oa("oa-1", "1200.00")]
        bank_rows = [bank("bk-1", "1200.00")]
        invoice_rows = [invoice("iv-1", "1200.00")]
        before = deepcopy((oa_rows, bank_rows, invoice_rows))

        self.engine.generate_decisions("2026-03", oa_rows, bank_rows, invoice_rows)

        self.assertEqual((oa_rows, bank_rows, invoice_rows), before)

    def test_real_workbench_row_shapes_infer_expenditure_direction_and_amounts(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [
                {
                    "id": "oa-exp-1994",
                    "type": "oa",
                    "amount": "6,000.00",
                    "apply_type": "付款申请",
                    "pay_receive_time": "2026-03-18",
                    "applicant": "张三",
                    "project_name": "星河项目",
                    "reason": "杭州ABC广告投放",
                }
            ],
            [
                {
                    "id": "bk-o-1",
                    "type": "bank",
                    "debit_amount": "6,000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-20 09:15",
                    "counterparty_name": "杭州ABC广告有限公司",
                    "summary": "星河项目付款",
                    "remark": "张三报销",
                }
            ],
            [
                {
                    "id": "iv-o-1",
                    "type": "invoice",
                    "invoice_type": "进项专票",
                    "total_with_tax": "6,000.00",
                    "invoice_date": "2026-03-19",
                    "seller_name": "杭州ABC广告有限公司",
                }
            ],
        )

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].match_shape, "oa_bank_invoice")
        self.assertEqual(decisions[0].row_ids, ("oa-exp-1994", "bk-o-1", "iv-o-1"))

    def test_oa_counterparty_name_can_bridge_plain_oa_bank_invoice_match(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [
                {
                    "id": "oa-exp-1995",
                    "type": "oa",
                    "amount": "6,000.00",
                    "apply_type": "付款申请",
                    "pay_receive_time": "2026-03-18",
                    "counterparty_name": "杭州ABC广告有限公司",
                    "reason": "服务费尾款",
                }
            ],
            [
                {
                    "id": "bk-o-2",
                    "type": "bank",
                    "debit_amount": "6,000.00",
                    "pay_receive_time": "2026-03-20 09:15",
                    "counterparty_name": "杭州ABC广告有限公司",
                    "summary": "服务费",
                }
            ],
            [
                {
                    "id": "iv-o-2",
                    "type": "invoice",
                    "invoice_type": "进项专票",
                    "total_with_tax": "6,000.00",
                    "issue_date": "2026-03-19",
                    "seller_name": "杭州ABC广告有限公司",
                }
            ],
        )

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].match_shape, "oa_bank_invoice")
        self.assertEqual(decisions[0].row_ids, ("oa-exp-1995", "bk-o-2", "iv-o-2"))

    def test_oa_attachment_invoice_parent_can_come_from_derived_id_or_row_id(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [oa("oa-exp-1994", "1200.00")],
            [bank("bk-o-1", "1200.00")],
            [
                {
                    "id": "oa-att-inv-oa-exp-1994-1",
                    "type": "invoice",
                    "source_kind": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-exp-1994",
                    "total_with_tax": "700.00",
                    "invoice_date": "2026-03-19",
                    "seller_name": "杭州ABC广告有限公司",
                },
                {
                    "id": "oa-att-inv-oa-exp-1994-2",
                    "type": "invoice",
                    "source_kind": "oa_attachment_invoice",
                    "total_with_tax": "400.00",
                    "invoice_date": "2026-03-19",
                    "seller_name": "杭州ABC广告有限公司",
                },
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.rule_code, "oa_attachment_invoice_with_bank")
        self.assertFalse(decision.invoice_amount_closed)
        self.assertEqual([warning.code for warning in decision.warnings], [WARNING_INVOICE_AMOUNT_MISMATCH])
        self.assertEqual(
            decision.invoice_row_ids,
            ("oa-att-inv-oa-exp-1994-1", "oa-att-inv-oa-exp-1994-2"),
        )

    def test_generate_decisions_only_returns_decisions_owned_by_dirty_scope(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-02",
            [oa("oa-1", "1200.00", month="2026-02")],
            [bank("bk-1", "1200.00", month="2026-03")],
            [invoice("iv-1", "1200.00", month="2026-03")],
        )

        self.assertEqual(decisions, [])

    def test_three_way_conflict_does_not_drop_unrelated_unique_pairing(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [
                oa("oa-conflict", "1200.00"),
                oa("oa-unique", "800.00", reason="星河项目 上海测试服务"),
            ],
            [
                bank("bk-conflict", "1200.00"),
                bank("bk-unique", "800.00", counterparty="上海测试服务有限公司"),
            ],
            [
                invoice("iv-conflict-a", "1200.00", month="2026-02"),
                invoice("iv-conflict-b", "1200.00", month="2026-04"),
                invoice("iv-unique", "800.00", seller_name="上海测试服务有限公司"),
            ],
        )

        paired = [decision for decision in decisions if decision.display_state == DISPLAY_STATE_PAIRED]
        open_decisions = [decision for decision in decisions if decision.display_state == DISPLAY_STATE_OPEN]

        self.assertEqual({decision.row_ids for decision in paired}, {("oa-unique", "bk-unique", "iv-unique")})
        self.assertEqual(
            {decision.row_ids for decision in open_decisions},
            {("oa-conflict",), ("bk-conflict",), ("iv-conflict-a",), ("iv-conflict-b",)},
        )

    def test_two_way_fallback_can_return_disjoint_oa_bank_and_oa_invoice_pairs(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [
                oa("oa-bank", "1200.00"),
                oa("oa-invoice", "800.00", reason="星河项目 上海测试服务"),
            ],
            [bank("bk-bank", "1200.00")],
            [invoice("iv-invoice", "800.00", seller_name="上海测试服务有限公司")],
        )

        self.assertEqual(
            {decision.match_shape: decision.row_ids for decision in decisions},
            {
                "oa_bank": ("oa-bank", "bk-bank"),
                "oa_invoice": ("oa-invoice", "iv-invoice"),
            },
        )


if __name__ == "__main__":
    unittest.main()
