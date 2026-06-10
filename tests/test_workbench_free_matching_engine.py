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


def output_invoice(
    row_id: str,
    amount: str,
    *,
    month: str = "2026-02",
    buyer_name: str = "北京长征高科技有限公司",
    buyer_tax_no: str | None = None,
    invoice_no: str | None = None,
    issue_date: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": row_id,
        "type": "invoice",
        "invoice_type": "销项发票",
        "total_with_tax": amount,
        "issue_date": issue_date or f"{month}-20",
        "seller_name": "云南溯源科技有限公司",
        "buyer_name": buyer_name,
    }
    if buyer_tax_no is not None:
        row["buyer_tax_no"] = buyer_tax_no
    if invoice_no is not None:
        row["invoice_no"] = invoice_no
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

    def test_single_exact_invoice_takes_priority_over_multi_invoice_sum_for_same_payment(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [oa("oa-1", "1200.00")],
            [bank("bk-1", "1200.00")],
            [
                invoice("iv-exact", "1200.00"),
                invoice("iv-part-1", "700.00"),
                invoice("iv-part-2", "500.00"),
            ],
        )

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decisions[0].row_ids, ("oa-1", "bk-1", "iv-exact"))

    def test_multiple_oa_bank_pairs_sum_to_single_invoice_is_paired(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [
                oa(
                    "oa-maintenance",
                    "9414.30",
                    reason="昭通卷烟厂能源集中监控平台系统维护采购项目",
                ),
                oa(
                    "oa-goods",
                    "21966.70",
                    reason="昭通卷烟厂能源集中监控平台系统维护采购项目",
                ),
            ],
            [
                bank(
                    "bk-maintenance",
                    "9414.30",
                    counterparty="北京标志卓信科技有限公司",
                ),
                bank(
                    "bk-goods",
                    "21966.70",
                    counterparty="北京标志卓信科技有限公司",
                ),
            ],
            [
                invoice(
                    "iv-combined",
                    "31381.00",
                    seller_name="北京标志卓信科技有限公司",
                ),
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.match_shape, "oa_bank_invoice")
        self.assertEqual(decision.rule_code, "oa_bank_pairs_single_invoice_exact_sum")
        self.assertEqual(
            decision.row_ids,
            ("oa-goods", "oa-maintenance", "bk-goods", "bk-maintenance", "iv-combined"),
        )
        self.assertEqual(decision.oa_row_ids, ("oa-goods", "oa-maintenance"))
        self.assertEqual(decision.bank_row_ids, ("bk-goods", "bk-maintenance"))
        self.assertEqual(decision.invoice_row_ids, ("iv-combined",))
        self.assertTrue(decision.payment_amount_closed)
        self.assertTrue(decision.invoice_amount_closed)

    def test_multiple_payment_single_invoice_search_is_bounded_for_many_vendor_pairs(self) -> None:
        oa_rows = [
            oa("oa-maintenance", "9414.30", reason="昭通卷烟厂能源集中监控平台系统维护采购项目"),
            oa("oa-goods", "21966.70", reason="昭通卷烟厂能源集中监控平台系统维护采购项目"),
        ]
        bank_rows = [
            bank("bk-maintenance", "9414.30", counterparty="北京标志卓信科技有限公司"),
            bank("bk-goods", "21966.70", counterparty="北京标志卓信科技有限公司"),
        ]
        for index in range(1, 41):
            amount = f"{100 + index}.00"
            oa_rows.append(
                oa(
                    f"oa-extra-{index}",
                    amount,
                    reason="昭通卷烟厂能源集中监控平台系统维护采购项目 北京标志卓信科技有限公司",
                )
            )
            bank_rows.append(bank(f"bk-extra-{index}", amount, counterparty="北京标志卓信科技有限公司"))

        decisions = self.engine.generate_decisions(
            "2026-03",
            oa_rows,
            bank_rows,
            [invoice("iv-combined", "31381.00", seller_name="北京标志卓信科技有限公司")],
        )

        paired = [decision for decision in decisions if decision.rule_code == "oa_bank_pairs_single_invoice_exact_sum"]
        self.assertEqual(len(paired), 1)
        self.assertEqual(
            paired[0].row_ids,
            ("oa-goods", "oa-maintenance", "bk-goods", "bk-maintenance", "iv-combined"),
        )

    def test_multiple_oa_bank_pairs_do_not_pick_one_when_single_invoice_sum_is_ambiguous(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [
                oa("oa-a", "100.00", reason="星河项目 供应商A"),
                oa("oa-b", "200.00", reason="星河项目 供应商A"),
            ],
            [
                bank("bk-a", "100.00", counterparty="供应商A"),
                bank("bk-b", "200.00", counterparty="供应商A"),
            ],
            [
                invoice("iv-a", "300.00", seller_name="供应商A"),
                invoice("iv-b", "300.00", seller_name="供应商A"),
            ],
        )

        self.assertEqual({decision.display_state for decision in decisions}, {DISPLAY_STATE_OPEN})
        self.assertEqual({decision.decision_status for decision in decisions}, {DECISION_STATUS_OPEN})
        self.assertIn("multiple_three_way_candidates", {b["code"] for d in decisions for b in d.blockers})

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
        self.assertEqual({decision.row_ids for decision in decisions}, {("oa-1",), ("bk-1",)})
        blockers = [blocker["code"] for decision in decisions for blocker in decision.blockers]
        self.assertIn("multiple_three_way_candidates", blockers)

    def test_income_bank_and_output_invoice_exact_counterparty_amount_is_paired(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-02",
            [],
            [
                bank(
                    "txn-income-13440",
                    "13440.00",
                    month="2026-02",
                    counterparty="北京长征高科技有限公司",
                    direction="income",
                )
            ],
            [output_invoice("inv-output-13440", "13440.00")],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.decision_status, DECISION_STATUS_PAIRED)
        self.assertEqual(decision.match_shape, "bank_invoice")
        self.assertEqual(decision.rule_code, "bank_invoice_exact_amount")
        self.assertEqual(decision.row_ids, ("txn-income-13440", "inv-output-13440"))
        self.assertEqual(decision.bank_row_ids, ("txn-income-13440",))
        self.assertEqual(decision.invoice_row_ids, ("inv-output-13440",))
        self.assertEqual(decision.scope_month, "2026-02")
        self.assertEqual(decision.direction, "income")
        self.assertTrue(decision.payment_amount_closed)
        self.assertTrue(decision.invoice_amount_closed)
        self.assertEqual(decision.evidence["amount_relation"], "single_exact_amount")
        self.assertTrue(decision.evidence["subject_evidence"])

    def test_income_bank_invoice_requires_bank_counterparty_not_summary_only(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-02",
            [],
            [
                {
                    "id": "txn-income-summary-only",
                    "type": "bank",
                    "direction": "income",
                    "trade_month": "2026-02",
                    "amount": "13440.00",
                    "counterparty_name": "",
                    "summary": "收到北京长征高科技有限公司外协款",
                    "remark": "北京长征高科技有限公司",
                }
            ],
            [output_invoice("inv-output-summary-only", "13440.00")],
        )

        self.assertEqual(decisions, [])

    def test_income_bank_matches_multiple_output_invoices_by_exact_sum(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-02",
            [],
            [
                bank(
                    "txn-income-26880",
                    "26880.00",
                    month="2026-02",
                    counterparty="北京长征高科技有限公司",
                    direction="income",
                )
            ],
            [
                output_invoice("inv-output-13440-a", "13440.00", invoice_no="FP-A"),
                output_invoice("inv-output-13440-b", "13440.00", invoice_no="FP-B"),
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.match_shape, "bank_invoice")
        self.assertEqual(decision.rule_code, "bank_invoice_exact_sum")
        self.assertEqual(decision.bank_row_ids, ("txn-income-26880",))
        self.assertEqual(decision.invoice_row_ids, ("inv-output-13440-a", "inv-output-13440-b"))
        self.assertEqual(decision.row_ids, ("txn-income-26880", "inv-output-13440-a", "inv-output-13440-b"))
        self.assertTrue(decision.payment_amount_closed)
        self.assertTrue(decision.invoice_amount_closed)
        self.assertEqual(decision.evidence["amount_relation"], "invoice_sum_exact_amount")

    def test_income_bank_selects_unique_invoice_by_invoice_number_in_remark(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-02",
            [],
            [
                {
                    "id": "txn-income-13440",
                    "type": "bank",
                    "direction": "income",
                    "trade_month": "2026-02",
                    "amount": "13440.00",
                    "counterparty_name": "北京长征高科技有限公司",
                    "summary": "外协收入",
                    "remark": "回款 发票 FP-B",
                }
            ],
            [
                output_invoice("inv-output-13440-a", "13440.00", invoice_no="FP-A"),
                output_invoice("inv-output-13440-b", "13440.00", invoice_no="FP-B"),
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.rule_code, "bank_invoice_exact_amount")
        self.assertEqual(decision.invoice_row_ids, ("inv-output-13440-b",))
        self.assertEqual(decision.evidence["selected_invoice_row_id"], "inv-output-13440-b")
        self.assertGreater(decision.evidence["score"], 0)
        self.assertIn("invoice_number", {item["kind"] for item in decision.evidence["supporting_evidence"]})

    def test_income_bank_same_score_candidates_remain_open_with_structured_blocker(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-02",
            [],
            [
                bank(
                    "txn-income-13440",
                    "13440.00",
                    month="2026-02",
                    counterparty="北京长征高科技有限公司",
                    direction="income",
                )
            ],
            [
                output_invoice("inv-output-13440-a", "13440.00", issue_date="2026-02-20"),
                output_invoice("inv-output-13440-b", "13440.00", issue_date="2026-02-20"),
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual({decision.display_state for decision in decisions}, {DISPLAY_STATE_OPEN})
        self.assertEqual(decision.match_shape, "bank_invoice")
        self.assertEqual(decision.row_ids, ("txn-income-13440", "inv-output-13440-a", "inv-output-13440-b"))
        self.assertEqual(decision.bank_row_ids, ("txn-income-13440",))
        self.assertEqual(decision.invoice_row_ids, ("inv-output-13440-a", "inv-output-13440-b"))
        self.assertEqual({blocker["code"] for blocker in decision.blockers}, {"same_score_bank_invoice_candidates"})
        self.assertEqual(decision.blockers[0]["amount_relation"], "single_exact_amount")
        self.assertIn("evidence_summary", decision.blockers[0])

    def test_income_bank_summary_buyer_name_supports_scoring_after_subject_match(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-02",
            [],
            [
                {
                    "id": "txn-income-13440",
                    "type": "bank",
                    "direction": "income",
                    "trade_month": "2026-02",
                    "amount": "13440.00",
                    "counterparty_name": "北京长征高科技有限公司",
                    "summary": "北京长征高科技有限公司 外协收入",
                    "remark": "",
                }
            ],
            [
                output_invoice("inv-output-13440-a", "13440.00", buyer_name="北京长征高科技有限公司"),
                output_invoice("inv-output-13440-b", "13440.00", buyer_name="北京长征高科技有限公司二部"),
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.invoice_row_ids, ("inv-output-13440-a",))
        self.assertIn("buyer_name_in_bank_text", {item["kind"] for item in decision.evidence["supporting_evidence"]})

    def test_income_bank_invoice_sum_multiple_combinations_remain_open(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-02",
            [],
            [
                bank(
                    "txn-income-26880",
                    "26880.00",
                    month="2026-02",
                    counterparty="北京长征高科技有限公司",
                    direction="income",
                )
            ],
            [
                output_invoice("inv-output-a1", "13440.00"),
                output_invoice("inv-output-a2", "13440.00"),
                output_invoice("inv-output-b1", "10000.00"),
                output_invoice("inv-output-b2", "16880.00"),
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_OPEN)
        self.assertEqual(decision.rule_code, "bank_invoice_conflict")
        self.assertEqual({blocker["code"] for blocker in decision.blockers}, {"multiple_bank_invoice_sum_candidates"})
        self.assertEqual(decision.blockers[0]["amount_relation"], "invoice_sum_exact_amount")

    def test_income_bank_invoice_tax_no_subject_evidence_scores_above_name_only(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-02",
            [],
            [
                {
                    "id": "txn-income-13440",
                    "type": "bank",
                    "direction": "income",
                    "trade_month": "2026-02",
                    "amount": "13440.00",
                    "counterparty_name": "北京长征高科技有限公司",
                    "counterparty_tax_no": "91110106102126771H",
                    "summary": "外协收入",
                }
            ],
            [
                output_invoice("inv-output-name-only", "13440.00", buyer_name="北京长征高科技有限公司"),
                output_invoice(
                    "inv-output-tax",
                    "13440.00",
                    buyer_name="北京长征高科技有限公司",
                    buyer_tax_no="91110106102126771H",
                ),
            ],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.invoice_row_ids, ("inv-output-tax",))
        self.assertIn("tax_no", {item["kind"] for item in decision.evidence["subject_evidence"]})

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

    def test_single_oa_multiple_bank_transactions_exact_sum_is_paired(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-04",
            [
                {
                    "row_id": "oa-dali-prepay",
                    "amount": "88050.00",
                    "direction": "expenditure",
                    "month": "2026-04",
                    "applicant": "樊相芳",
                    "project_name": "大理卷烟厂余热综合利用项目",
                    "reason": "申请支付大理烟厂余热回收项目空气源热泵15%预付款（88050元）",
                    "counterparty_name": "云南辰飞机电工程有限公司",
                }
            ],
            [
                bank(
                    "bk-jh-64996",
                    "64996.69",
                    month="2026-04",
                    counterparty="云南辰飞机电工程有限公司",
                ),
                bank(
                    "bk-gd-23053",
                    "23053.31",
                    month="2026-04",
                    counterparty="云南辰飞机电工程有限公司",
                ),
            ],
            [],
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.display_state, DISPLAY_STATE_PAIRED)
        self.assertEqual(decision.decision_status, DECISION_STATUS_PAIRED)
        self.assertEqual(decision.match_shape, "oa_bank")
        self.assertEqual(decision.rule_code, "oa_bank_exact_sum")
        self.assertEqual(decision.row_ids, ("oa-dali-prepay", "bk-gd-23053", "bk-jh-64996"))
        self.assertEqual(decision.oa_row_ids, ("oa-dali-prepay",))
        self.assertEqual(decision.bank_row_ids, ("bk-gd-23053", "bk-jh-64996"))
        self.assertTrue(decision.payment_amount_closed)
        self.assertIsNone(decision.invoice_amount_closed)
        self.assertEqual(decision.evidence["amount_relation"], "bank_sum_exact_amount")
        self.assertEqual(decision.evidence["bank_count"], 2)

    def test_single_oa_multiple_bank_transactions_ambiguous_sum_does_not_auto_pair(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-04",
            [oa("oa-ambiguous-sum", "300.00", month="2026-04", reason="星河项目 供应商A")],
            [
                bank("bk-100", "100.00", month="2026-04", counterparty="供应商A"),
                bank("bk-200", "200.00", month="2026-04", counterparty="供应商A"),
                bank("bk-150-a", "150.00", month="2026-04", counterparty="供应商A"),
                bank("bk-150-b", "150.00", month="2026-04", counterparty="供应商A"),
            ],
            [],
        )

        self.assertFalse(any(decision.rule_code == "oa_bank_exact_sum" for decision in decisions))
        self.assertFalse(
            any(
                decision.match_shape == "oa_bank"
                and decision.display_state == DISPLAY_STATE_PAIRED
                for decision in decisions
            )
        )

    def test_single_oa_multiple_bank_transactions_shared_by_multiple_oas_does_not_auto_pair(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-04",
            [
                oa("oa-competing-a", "300.00", month="2026-04", reason="星河项目 供应商A"),
                oa("oa-competing-b", "300.00", month="2026-04", reason="星河项目 供应商A"),
            ],
            [
                bank("bk-120", "120.00", month="2026-04", counterparty="供应商A"),
                bank("bk-180", "180.00", month="2026-04", counterparty="供应商A"),
            ],
            [],
        )

        self.assertFalse(any(decision.rule_code == "oa_bank_exact_sum" for decision in decisions))

    def test_single_oa_multiple_bank_transactions_require_each_bank_evidence(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-04",
            [oa("oa-evidence-sum", "300.00", month="2026-04", reason="星河项目 供应商A")],
            [
                bank("bk-evidence-ok", "120.00", month="2026-04", counterparty="供应商A"),
                {
                    "row_id": "bk-evidence-missing",
                    "amount": "180.00",
                    "direction": "expenditure",
                    "trade_month": "2026-04",
                    "counterparty": "无关公司",
                    "summary": "完全无关",
                    "remark": "无业务线索",
                },
            ],
            [],
        )

        self.assertFalse(any(decision.rule_code == "oa_bank_exact_sum" for decision in decisions))

    def test_single_oa_bank_exact_amount_takes_priority_over_bank_sum(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-04",
            [oa("oa-exact-priority", "300.00", month="2026-04", reason="星河项目 供应商A")],
            [
                bank("bk-exact", "300.00", month="2026-04", counterparty="供应商A"),
                bank("bk-split-120", "120.00", month="2026-04", counterparty="供应商A"),
                bank("bk-split-180", "180.00", month="2026-04", counterparty="供应商A"),
            ],
            [],
        )

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].rule_code, "oa_bank_exact_amount")
        self.assertEqual(decisions[0].row_ids, ("oa-exact-priority", "bk-exact"))
        self.assertFalse(any(decision.rule_code == "oa_bank_exact_sum" for decision in decisions))

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

    def test_real_oa_row_shape_can_use_detail_application_date_as_month(self) -> None:
        decisions = self.engine.generate_decisions(
            "2026-03",
            [
                {
                    "id": "oa-pay-2065",
                    "type": "oa",
                    "amount": "5200",
                    "apply_type": "支付申请",
                    "counterparty_name": "云南力科知识产权有限公司",
                    "project_name": "云南溯源科技",
                    "reason": "实用新型专利转让费（两件）",
                    "detail_fields": {"申请日期": "2026-03-27"},
                }
            ],
            [
                {
                    "id": "txn_imported_1415",
                    "type": "bank",
                    "debit_amount": "5,200.00",
                    "trade_time": "2026-03-27 15:01:48",
                    "counterparty_name": "云南力科知识产权有限公司",
                    "remark": "实用新型专利转让费",
                }
            ],
            [
                {
                    "id": "inv_imported_1502",
                    "type": "invoice",
                    "invoice_type": "进项发票",
                    "total_with_tax": "5,200.00",
                    "issue_date": "2026-03-27",
                    "seller_name": "云南力科知识产权有限公司",
                }
            ],
        )

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].rule_code, "oa_bank_invoice_exact_amount")
        self.assertEqual(decisions[0].row_ids, ("oa-pay-2065", "txn_imported_1415", "inv_imported_1502"))

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

    def test_conflict_open_invoice_decisions_are_owned_by_invoice_month_not_dirty_scope(self) -> None:
        rows = (
            [oa("oa-1", "1200.00")],
            [bank("bk-1", "1200.00")],
            [
                invoice("iv-1", "1200.00", month="2026-02"),
                invoice("iv-2", "1200.00", month="2026-04"),
            ],
        )

        feb_decisions = self.engine.generate_decisions("2026-02", *rows)
        mar_decisions = self.engine.generate_decisions("2026-03", *rows)

        feb_invoice_decisions = [decision for decision in feb_decisions if decision.invoice_row_ids]
        mar_invoice_decisions = [decision for decision in mar_decisions if decision.invoice_row_ids]
        self.assertEqual({decision.row_ids for decision in feb_invoice_decisions}, {("iv-1",)})
        self.assertEqual({decision.scope_month for decision in feb_invoice_decisions}, {"2026-02"})
        self.assertEqual({decision.row_ids for decision in mar_invoice_decisions}, set())

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
            {("oa-conflict",), ("bk-conflict",)},
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
