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


if __name__ == "__main__":
    unittest.main()
