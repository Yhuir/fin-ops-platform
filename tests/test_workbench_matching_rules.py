import unittest

from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_matching_rules import MAX_SUM_MATCH_CANDIDATES, WorkbenchMatchingRules


class WorkbenchMatchingRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = WorkbenchMatchingRules()

    def test_oa_bank_exact_amount_without_invoice_is_incomplete(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-001", "100.00", counterparty_name="供应商A")],
            bank_rows=[bank_row("bank-001", "100.00", counterparty_name="供应商A")],
            invoice_rows=[],
        )

        candidate = find_candidate(candidates, "oa_bank_exact_amount")
        self.assertEqual(candidate["status"], "incomplete")
        self.assertEqual(candidate["confidence"], "medium")
        self.assertEqual(candidate["candidate_type"], "oa_bank")
        self.assertEqual(candidate["oa_row_ids"], ["oa-001"])
        self.assertEqual(candidate["bank_row_ids"], ["bank-001"])
        self.assertEqual(candidate["invoice_row_ids"], [])
        no_confident_bank = [
            item
            for item in candidates
            if item["rule_code"] == "no_confident_match" and item["bank_row_ids"] == ["bank-001"]
        ]
        self.assertEqual(len(no_confident_bank), 1)
        self.assertEqual(no_confident_bank[0]["status"], "needs_review")

    def test_oa_bank_exact_amount_rejects_amount_only_generic_batch_reimbursement(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-01",
            oa_rows=[
                oa_row(
                    "oa-hurong-350",
                    "350.00",
                    counterparty_name="",
                    applicant_name="胡瑢",
                    apply_type="日常报销",
                    project_name="玉溪卷烟厂复烤车间技术升级改造项目-配电监控系统建设（第2次采购）",
                    reason="玉溪德力西买材料；玉溪卓达买工具和材料",
                    pay_receive_time="2026-01-04",
                )
            ],
            bank_rows=[
                bank_row(
                    "bank-batch-350",
                    "350.00",
                    counterparty_name="批量账务集中处理",
                    summary="报销",
                    trade_time="2026-01-20 10:40:01",
                )
            ],
            invoice_rows=[],
        )

        self.assertIsNone(find_candidate_by_rows(candidates, "oa_bank_exact_amount", ["oa-hurong-350", "bank-batch-350"]))

    def test_daily_reimbursement_applicant_matching_bank_counterparty_generates_incomplete_candidate(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-01",
            oa_rows=[
                oa_row(
                    "oa-tian-196",
                    "196.00",
                    counterparty_name="",
                    applicant_name="田孟维",
                    apply_type="日常报销",
                    reason="日常报销",
                    pay_receive_time="2026-01-10",
                )
            ],
            bank_rows=[
                bank_row(
                    "bank-tian-196",
                    "196.00",
                    counterparty_name="田孟维",
                    summary="报销",
                    trade_time="2026-01-11 09:00:00",
                )
            ],
            invoice_rows=[],
        )

        candidate = find_candidate_by_rows(candidates, "oa_bank_exact_amount", ["oa-tian-196", "bank-tian-196"])
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["status"], "incomplete")
        self.assertEqual(candidate["confidence"], "medium")
        self.assertEqual(
            candidate["special_metadata"]["evidence"]["strong"],
            ["daily_reimbursement_applicant_counterparty_match"],
        )

    def test_payment_application_matching_counterparty_generates_candidate(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-01",
            oa_rows=[
                oa_row(
                    "oa-payment-500",
                    "500.00",
                    counterparty_name="云南设备供应商有限公司",
                    apply_type="付款申请",
                    pay_receive_time="2026-01-10",
                )
            ],
            bank_rows=[
                bank_row(
                    "bank-payment-500",
                    "500.00",
                    counterparty_name="云南设备供应商有限公司",
                    summary="货款",
                    trade_time="2026-01-11 09:00:00",
                )
            ],
            invoice_rows=[],
        )

        candidate = find_candidate_by_rows(candidates, "oa_bank_exact_amount", ["oa-payment-500", "bank-payment-500"])
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["status"], "incomplete")
        self.assertEqual(candidate["confidence"], "medium")
        self.assertEqual(candidate["special_metadata"]["evidence"]["strong"], ["counterparty_match"])

    def test_oa_one_to_many_bank_exact_sum_generates_incomplete_candidate(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-04",
            oa_rows=[
                oa_row(
                    "oa-dali-prepay",
                    "88050.00",
                    counterparty_name="云南辰飞机电工程有限公司",
                    applicant_name="樊相芳",
                    project_name="大理卷烟厂余热综合利用项目",
                    reason="申请支付大理烟厂余热回收项目空气源热泵15%预付款（88050元）",
                    pay_receive_time="2026-04-23",
                )
            ],
            bank_rows=[
                bank_row(
                    "bank-jh-64996",
                    "64996.69",
                    counterparty_name="云南辰飞机电工程有限公司",
                    summary="货款",
                    trade_time="2026-04-23 15:28:56",
                ),
                bank_row(
                    "bank-gd-23053",
                    "23053.31",
                    counterparty_name="云南辰飞机电工程有限公司",
                    summary="",
                    trade_time="2026-04-23 11:18:17",
                ),
            ],
            invoice_rows=[],
        )

        candidate = find_candidate(candidates, "oa_bank_exact_sum")
        self.assertEqual(candidate["status"], "incomplete")
        self.assertEqual(candidate["confidence"], "medium")
        self.assertEqual(candidate["candidate_type"], "oa_bank")
        self.assertEqual(candidate["amount"], "88050.00")
        self.assertEqual(candidate["oa_row_ids"], ["oa-dali-prepay"])
        self.assertCountEqual(candidate["bank_row_ids"], ["bank-jh-64996", "bank-gd-23053"])
        self.assertEqual(candidate["invoice_row_ids"], [])
        self.assertEqual(candidate["special_metadata"]["evidence"]["target_amount"], "88050.00")
        self.assertEqual(candidate["special_metadata"]["evidence"]["bank_total"], "88050.00")
        self.assertEqual(candidate["special_metadata"]["evidence"]["bank_count"], 2)

    def test_oa_bank_exact_sum_requires_unique_combination(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-04",
            oa_rows=[oa_row("oa-ambiguous-sum", "300.00", counterparty_name="供应商A")],
            bank_rows=[
                bank_row("bank-100", "100.00", counterparty_name="供应商A"),
                bank_row("bank-200", "200.00", counterparty_name="供应商A"),
                bank_row("bank-150-a", "150.00", counterparty_name="供应商A"),
                bank_row("bank-150-b", "150.00", counterparty_name="供应商A"),
            ],
            invoice_rows=[],
        )

        self.assertIsNone(find_optional_candidate(candidates, "oa_bank_exact_sum"))

    def test_oa_bank_exact_sum_does_not_claim_same_bank_group_for_multiple_oas(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-04",
            oa_rows=[
                oa_row("oa-competing-a", "300.00", counterparty_name="供应商A"),
                oa_row("oa-competing-b", "300.00", counterparty_name="供应商A"),
            ],
            bank_rows=[
                bank_row("bank-120", "120.00", counterparty_name="供应商A"),
                bank_row("bank-180", "180.00", counterparty_name="供应商A"),
            ],
            invoice_rows=[],
        )

        self.assertIsNone(find_optional_candidate(candidates, "oa_bank_exact_sum"))

    def test_oa_bank_exact_sum_requires_every_bank_to_have_oa_bank_evidence(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-04",
            oa_rows=[oa_row("oa-evidence-sum", "300.00", counterparty_name="供应商A")],
            bank_rows=[
                bank_row("bank-evidence-ok", "120.00", counterparty_name="供应商A"),
                bank_row(
                    "bank-evidence-missing",
                    "180.00",
                    counterparty_name="无关公司",
                    summary="完全无关",
                    remark="无业务线索",
                ),
            ],
            invoice_rows=[],
        )

        self.assertIsNone(find_optional_candidate(candidates, "oa_bank_exact_sum"))

    def test_oa_bank_exact_sum_rejects_generic_technology_token_only(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-02",
            oa_rows=[
                oa_row(
                    "oa-loan-interest",
                    "600.00",
                    counterparty_name="中国光大银行",
                    project_name="云南溯源科技",
                    reason="光大新一期贷款一季度利息",
                )
            ],
            bank_rows=[
                bank_row(
                    "bank-service-a",
                    "300.00",
                    counterparty_name="中科视拓（南京）科技有限公司",
                    summary="服务费（ADL00823854）",
                ),
                bank_row(
                    "bank-service-b",
                    "300.00",
                    counterparty_name="中科视拓（南京）科技有限公司",
                    summary="服务费（ADL00823854）",
                ),
            ],
            invoice_rows=[],
        )

        self.assertIsNone(find_optional_candidate(candidates, "oa_bank_exact_sum"))

    def test_oa_bank_exact_amount_takes_priority_over_bank_sum(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-04",
            oa_rows=[oa_row("oa-exact-priority", "300.00", counterparty_name="供应商A")],
            bank_rows=[
                bank_row("bank-exact", "300.00", counterparty_name="供应商A"),
                bank_row("bank-split-120", "120.00", counterparty_name="供应商A"),
                bank_row("bank-split-180", "180.00", counterparty_name="供应商A"),
            ],
            invoice_rows=[],
        )

        exact_candidate = find_candidate_by_rows(candidates, "oa_bank_exact_amount", ["oa-exact-priority", "bank-exact"])
        self.assertIsNotNone(exact_candidate)
        self.assertIsNone(find_optional_candidate(candidates, "oa_bank_exact_sum"))

    def test_oa_bank_exact_amount_does_not_randomly_choose_when_one_oa_has_tied_banks(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-01",
            oa_rows=[
                oa_row(
                    "oa-tied-banks",
                    "196.00",
                    counterparty_name="",
                    applicant_name="田孟维",
                    apply_type="日常报销",
                )
            ],
            bank_rows=[
                bank_row("bank-tied-a", "196.00", counterparty_name="田孟维", summary="报销"),
                bank_row("bank-tied-b", "196.00", counterparty_name="田孟维", summary="报销"),
            ],
            invoice_rows=[],
        )

        self.assertEqual(
            [
                candidate
                for candidate in candidates
                if candidate["rule_code"] == "oa_bank_exact_amount"
                and candidate["oa_row_ids"] == ["oa-tied-banks"]
            ],
            [],
        )

    def test_oa_bank_exact_amount_does_not_randomly_choose_when_one_bank_has_tied_oas(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-01",
            oa_rows=[
                oa_row(
                    "oa-tied-a",
                    "196.00",
                    counterparty_name="",
                    applicant_name="田孟维",
                    apply_type="日常报销",
                ),
                oa_row(
                    "oa-tied-b",
                    "196.00",
                    counterparty_name="",
                    applicant_name="田孟维",
                    apply_type="日常报销",
                ),
            ],
            bank_rows=[bank_row("bank-tied-oa", "196.00", counterparty_name="田孟维", summary="报销")],
            invoice_rows=[],
        )

        self.assertEqual(
            [
                candidate
                for candidate in candidates
                if candidate["rule_code"] == "oa_bank_exact_amount"
                and candidate["bank_row_ids"] == ["bank-tied-oa"]
            ],
            [],
        )

    def test_oa_multi_invoice_exact_sum_is_generic_and_incomplete_without_bank(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-meeting", "300.00", counterparty_name="会务服务有限公司")],
            bank_rows=[],
            invoice_rows=[
                invoice_row("invoice-meeting-001", "120.00", seller_name="会务服务有限公司"),
                invoice_row("invoice-meeting-002", "180.00", seller_name="会务服务有限公司"),
            ],
        )

        candidate = find_candidate(candidates, "oa_multi_invoice_exact_sum")
        self.assertEqual(candidate["status"], "incomplete")
        self.assertEqual(candidate["confidence"], "medium")
        self.assertEqual(candidate["candidate_type"], "oa_invoice")
        self.assertCountEqual(candidate["invoice_row_ids"], ["invoice-meeting-001", "invoice-meeting-002"])

    def test_oa_attachment_invoices_auto_close_tian_style_when_bank_evidence_is_credible(self) -> None:
        invoice_oa_70 = invoice_row(
            "invoice-oa-70",
            "66.04",
            seller_name="加油站A",
            source_kind="oa_attachment_invoice",
            derived_from_oa_id="oa-tian-196",
            invoice_no="INV-ATT-70",
            total_with_tax="70.00",
        )
        invoice_oa_126 = invoice_row(
            "invoice-oa-126",
            "124.75",
            seller_name="加油站B",
            source_kind="oa_attachment_invoice",
            derived_from_oa_id="oa-tian-196",
            invoice_no="INV-ATT-126",
            total_with_tax="126.00",
        )
        manual_duplicate_70 = invoice_row(
            "invoice-manual-70",
            "66.04",
            seller_name="加油站A",
            source_kind="manual_invoice",
            invoice_no="INV-ATT-70",
            total_with_tax="70.00",
        )
        manual_duplicate_126 = invoice_row(
            "invoice-manual-126",
            "124.75",
            seller_name="加油站B",
            source_kind="manual_invoice",
            invoice_no="INV-ATT-126",
            total_with_tax="126.00",
        )

        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[
                oa_row(
                    "oa-tian-196",
                    "196.00",
                    counterparty_name="",
                    applicant_name="田孟维",
                    apply_type="日常报销",
                    reason="加油费报销",
                    pay_receive_time="2026-05-02",
                )
            ],
            bank_rows=[
                bank_row(
                    "bank-tian-196",
                    "196.00",
                    counterparty_name="田孟维",
                    summary="报销",
                    trade_time="2026-05-03 09:00:00",
                )
            ],
            invoice_rows=[invoice_oa_70, invoice_oa_126, manual_duplicate_70, manual_duplicate_126],
        )

        candidate = find_candidate(candidates, "oa_attachment_invoice_source_link")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["candidate_type"], "oa_bank_invoice")
        self.assertEqual(candidate["amount"], "196.00")
        self.assertEqual(candidate["oa_row_ids"], ["oa-tian-196"])
        self.assertEqual(candidate["bank_row_ids"], ["bank-tian-196"])
        self.assertCountEqual(candidate["invoice_row_ids"], ["invoice-oa-70", "invoice-oa-126"])
        self.assertEqual(
            sorted(candidate["row_ids"]),
            ["bank-tian-196", "invoice-oa-126", "invoice-oa-70", "oa-tian-196"],
        )
        self.assertNotIn("invoice-manual-70", candidate["row_ids"])
        self.assertNotIn("invoice-manual-126", candidate["row_ids"])

    def test_oa_attachment_invoices_do_not_auto_close_with_unrelated_same_amount_bank(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[
                oa_row(
                    "oa-attach-unrelated-bank",
                    "196.00",
                    counterparty_name="",
                    applicant_name="田孟维",
                    apply_type="日常报销",
                    reason="加油费报销",
                    pay_receive_time="2026-05-02",
                )
            ],
            bank_rows=[
                bank_row(
                    "bank-unrelated-196",
                    "196.00",
                    counterparty_name="无关收款人",
                    summary="转账",
                    trade_time="2026-05-03 09:00:00",
                )
            ],
            invoice_rows=[
                invoice_row(
                    "invoice-oa-unrelated-70",
                    "66.04",
                    seller_name="加油站A",
                    source_kind="oa_attachment_invoice",
                    derived_from_oa_id="oa-attach-unrelated-bank",
                    total_with_tax="70.00",
                ),
                invoice_row(
                    "invoice-oa-unrelated-126",
                    "124.75",
                    seller_name="加油站B",
                    source_kind="oa_attachment_invoice",
                    derived_from_oa_id="oa-attach-unrelated-bank",
                    total_with_tax="126.00",
                ),
            ],
        )

        candidate = find_candidate(candidates, "oa_attachment_invoice_source_link")
        self.assertEqual(candidate["status"], "incomplete")
        self.assertEqual(candidate["candidate_type"], "oa_invoice")
        self.assertEqual(candidate["bank_row_ids"], [])
        self.assertCountEqual(
            candidate["invoice_row_ids"],
            ["invoice-oa-unrelated-70", "invoice-oa-unrelated-126"],
        )

    def test_oa_attachment_invoices_without_bank_generate_incomplete_candidate(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-exp-no-bank", "196.00", counterparty_name="")],
            bank_rows=[],
            invoice_rows=[
                invoice_row(
                    "invoice-oa-no-bank-70",
                    "66.04",
                    seller_name="附件票供应商A",
                    source_kind="oa_attachment_invoice",
                    derived_from_oa_id="oa-exp-no-bank",
                    total_with_tax="70.00",
                ),
                invoice_row(
                    "invoice-oa-no-bank-126",
                    "124.75",
                    seller_name="附件票供应商B",
                    source_kind="oa_attachment_invoice",
                    derived_from_oa_id="oa-exp-no-bank",
                    total_with_tax="126.00",
                ),
            ],
        )

        candidate = find_candidate(candidates, "oa_attachment_invoice_source_link")
        self.assertEqual(candidate["status"], "incomplete")
        self.assertNotEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["candidate_type"], "oa_invoice")
        self.assertEqual(candidate["bank_row_ids"], [])
        self.assertCountEqual(
            candidate["invoice_row_ids"],
            ["invoice-oa-no-bank-70", "invoice-oa-no-bank-126"],
        )

    def test_payment_receipt_attachment_rows_do_not_enter_invoice_matching_rules(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-payment-only", "248.00", counterparty_name="胡瑢", apply_type="日常报销")],
            bank_rows=[bank_row("bank-payment-only", "248.00", counterparty_name="胡瑢")],
            invoice_rows=[
                invoice_row(
                    "payment-receipt-248",
                    "248.00",
                    seller_name="胡瑢",
                    source_kind="oa_attachment_payment_receipt",
                    derived_from_oa_id="oa-payment-only",
                    total_with_tax="248.00",
                )
            ],
        )

        self.assertFalse(
            any("payment-receipt-248" in candidate["row_ids"] for candidate in candidates)
        )
        self.assertFalse(
            any(candidate["rule_code"] == "oa_attachment_invoice_source_link" for candidate in candidates)
        )

    def test_oa_attachment_invoices_with_amount_delta_auto_close_when_credible_bank_closes_oa_amount(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-03",
            oa_rows=[
                oa_row(
                    "oa-tian-318",
                    "318.00",
                    counterparty_name="",
                    applicant_name="田孟维",
                    apply_type="日常报销",
                    project_name="大理卷烟厂余热综合利用项目",
                    reason="餐费，刘总已知",
                    pay_receive_time="2026-03-17",
                )
            ],
            bank_rows=[
                bank_row(
                    "bank-tian-318",
                    "318.00",
                    counterparty_name="田孟维",
                    summary="代收付",
                    trade_time="2026-04-03 14:30:01",
                )
            ],
            invoice_rows=[
                invoice_row(
                    "invoice-oa-174",
                    "172.28",
                    seller_name="附件票供应商A",
                    source_kind="oa_attachment_invoice",
                    derived_from_oa_id="oa-tian-318",
                    total_with_tax="174.00",
                ),
                invoice_row(
                    "invoice-oa-145",
                    "143.56",
                    seller_name="附件票供应商B",
                    source_kind="oa_attachment_invoice",
                    derived_from_oa_id="oa-tian-318",
                    total_with_tax="145.00",
                ),
            ],
        )

        candidate = find_candidate(candidates, "oa_attachment_invoice_source_link")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["candidate_type"], "oa_bank_invoice")
        self.assertEqual(candidate["amount"], "318.00")
        self.assertEqual(candidate["amount_delta"], "1.00")
        self.assertEqual(candidate["oa_row_ids"], ["oa-tian-318"])
        self.assertEqual(candidate["bank_row_ids"], ["bank-tian-318"])
        self.assertCountEqual(candidate["invoice_row_ids"], ["invoice-oa-174", "invoice-oa-145"])

    def test_generic_oa_multi_invoice_rules_exclude_oa_attachment_invoice_subsets(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-02",
            oa_rows=[
                oa_row(
                    "oa-offset-800",
                    "800.00",
                    applicant_name="周洁莹",
                    counterparty_name="云南溯源科技",
                    apply_type="日常报销",
                )
            ],
            bank_rows=[
                bank_row(
                    "bank-offset-800",
                    "800.00",
                    counterparty_name="云南溯源科技",
                )
            ],
            invoice_rows=[
                invoice_row(
                    "invoice-oa-offset-300",
                    "300.00",
                    seller_name="云南溯源科技",
                    source_kind="oa_attachment_invoice",
                    derived_from_oa_id="oa-offset-800",
                    total_with_tax="300.00",
                ),
                invoice_row(
                    "invoice-oa-offset-500",
                    "500.00",
                    seller_name="云南溯源科技",
                    source_kind="oa_attachment_invoice",
                    derived_from_oa_id="oa-offset-800",
                    total_with_tax="500.00",
                ),
                invoice_row(
                    "invoice-oa-offset-extra",
                    "30.00",
                    seller_name="云南溯源科技",
                    source_kind="oa_attachment_invoice",
                    derived_from_oa_id="oa-offset-800",
                    total_with_tax="30.00",
                ),
            ],
            settings={"offset_applicant_names": []},
        )

        candidate = find_candidate(candidates, "oa_attachment_invoice_source_link")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["candidate_type"], "oa_bank_invoice")
        self.assertEqual(candidate["amount_delta"], "30.00")
        self.assertCountEqual(
            candidate["invoice_row_ids"],
            ["invoice-oa-offset-300", "invoice-oa-offset-500", "invoice-oa-offset-extra"],
        )
        self.assertIsNone(find_optional_candidate(candidates, "oa_multi_invoice_exact_sum"))
        self.assertIsNone(find_optional_candidate(candidates, "oa_bank_multi_invoice_exact_sum"))

    def test_invoice_matching_amount_prefers_total_with_tax_for_imported_invoices(self) -> None:
        invoice_a = invoice_row("invoice-tax-a", "100.00", seller_name="设备供应商")
        invoice_a["total_with_tax"] = "112.00"
        invoice_b = invoice_row("invoice-tax-b", "200.00", seller_name="设备供应商")
        invoice_b["total_with_tax"] = "188.00"

        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-tax", "300.00", counterparty_name="设备供应商")],
            bank_rows=[],
            invoice_rows=[invoice_a, invoice_b],
        )

        candidate = find_candidate(candidates, "oa_multi_invoice_exact_sum")
        self.assertEqual(candidate["amount"], "300.00")
        self.assertCountEqual(candidate["invoice_row_ids"], ["invoice-tax-a", "invoice-tax-b"])

    def test_oa_multi_invoice_exact_sum_allows_empty_oa_counterparty_when_subset_is_unique(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-travel", "300.00", counterparty_name="")],
            bank_rows=[],
            invoice_rows=[
                invoice_row("invoice-hotel", "120.00", seller_name="酒店有限公司"),
                invoice_row("invoice-flight", "180.00", seller_name="票务有限公司"),
                invoice_row("invoice-food", "90.00", seller_name="餐饮有限公司"),
            ],
        )

        candidate = find_candidate(candidates, "oa_multi_invoice_exact_sum")
        self.assertEqual(candidate["oa_row_ids"], ["oa-travel"])
        self.assertCountEqual(candidate["invoice_row_ids"], ["invoice-hotel", "invoice-flight"])

    def test_oa_multi_invoice_exact_sum_is_bounded_for_many_compatible_rows(self) -> None:
        invoice_rows = [
            invoice_row(f"invoice-noise-{index:03d}", "1.00", seller_name=f"供应商{index:03d}")
            for index in range(160)
        ]

        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-large", "300.00", counterparty_name="")],
            bank_rows=[],
            invoice_rows=invoice_rows,
        )

        self.assertIsNone(find_optional_candidate(candidates, "oa_multi_invoice_exact_sum"))

    def test_sum_match_candidate_cap_records_skipped_summary_without_candidates(self) -> None:
        invoice_rows = [
            invoice_row(f"invoice-cap-{index:03d}", "1.00", seller_name="供应商A")
            for index in range(MAX_SUM_MATCH_CANDIDATES + 1)
        ]

        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-cap", "3.00", counterparty_name="供应商A")],
            bank_rows=[],
            invoice_rows=invoice_rows,
        )

        self.assertIsNone(find_optional_candidate(candidates, "oa_multi_invoice_exact_sum"))
        summary = self.rules.last_summary()
        self.assertEqual(summary["skipped_rule_count"], 1)
        self.assertEqual(summary["skipped_rules"][0]["rule_code"], "oa_multi_invoice_exact_sum")
        self.assertEqual(summary["skipped_rules"][0]["reason"], "sum_match_candidate_cap_exceeded")

    def test_oa_bank_multi_invoice_ambiguous_sum_does_not_auto_close(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-ambiguous", "300.00", counterparty_name="供应商A")],
            bank_rows=[bank_row("bank-ambiguous", "300.00", counterparty_name="供应商A")],
            invoice_rows=[
                invoice_row("invoice-100", "100.00", seller_name="供应商A"),
                invoice_row("invoice-200", "200.00", seller_name="供应商A"),
                invoice_row("invoice-150-a", "150.00", seller_name="供应商A"),
                invoice_row("invoice-150-b", "150.00", seller_name="供应商A"),
            ],
        )

        self.assertIsNone(find_optional_candidate(candidates, "oa_bank_multi_invoice_exact_sum"))

    def test_oa_bank_multi_invoice_exact_sum_auto_closes_when_loop_matches(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-001", "300.00", counterparty_name="设备供应商")],
            bank_rows=[bank_row("bank-001", "300.00", counterparty_name="设备供应商")],
            invoice_rows=[
                invoice_row("invoice-001", "120.00", seller_name="设备供应商"),
                invoice_row("invoice-002", "180.00", seller_name="设备供应商"),
            ],
        )

        candidate = find_candidate(candidates, "oa_bank_multi_invoice_exact_sum")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["candidate_type"], "oa_bank_invoice")

    def test_oa_child_item_matches_invoice_and_keeps_whole_oa_row(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[
                oa_row(
                    "oa-items",
                    "300.00",
                    counterparty_name="",
                    expense_items=[
                        {"id": "item-hotel", "amount": "120.00", "name": "住宿"},
                        {"id": "item-flight", "amount": "180.00", "name": "机票"},
                    ],
                )
            ],
            bank_rows=[],
            invoice_rows=[invoice_row("invoice-hotel", "120.00", seller_name="酒店有限公司")],
        )

        candidate = find_candidate(candidates, "oa_item_invoice_exact_amount")
        self.assertEqual(candidate["oa_row_ids"], ["oa-items"])
        self.assertEqual(candidate["invoice_row_ids"], ["invoice-hotel"])
        self.assertIn("item-level", candidate["explanation"])
        self.assertIn("item-hotel", candidate["explanation"])

    def test_bank_invoice_exact_amount_uses_free_matching_engine_code_for_same_counterparty(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[],
            bank_rows=[bank_row("bank-001", "100.00", counterparty_name="客户A", direction="inflow")],
            invoice_rows=[invoice_row("invoice-001", "100.00", buyer_name="客户A", invoice_type="销项发票")],
        )

        candidate = find_candidate(candidates, "bank_invoice_exact_amount")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["candidate_type"], "bank_invoice")

    def test_legacy_candidates_use_free_engine_for_income_bank_output_invoice(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-02",
            oa_rows=[],
            bank_rows=[
                bank_row(
                    "bank-ccb-8106",
                    "13440.00",
                    counterparty_name="北京长征高科技有限公司",
                    direction="inflow",
                    account_no="53001905038050548106",
                    account_name="云南溯源科技有限公司建设银行基本户",
                    trade_time="2026-02-11 11:49:39",
                )
            ],
            invoice_rows=[
                invoice_row(
                    "invoice-output-052520",
                    "13440.00",
                    seller_name="云南溯源科技有限公司",
                    buyer_name="北京长征高科技有限公司",
                    invoice_type="销项发票",
                    issue_date="2026-02-11",
                    total_with_tax="13440.00",
                )
            ],
        )

        candidate = find_candidate(candidates, "bank_invoice_exact_amount")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["candidate_type"], "bank_invoice")
        self.assertEqual(candidate["bank_row_ids"], ["bank-ccb-8106"])
        self.assertEqual(candidate["invoice_row_ids"], ["invoice-output-052520"])
        self.assertEqual(candidate["special_metadata"]["workbench_reconciliation_decision"]["match_shape"], "bank_invoice")

    def test_legacy_candidates_auto_close_income_bank_output_invoice_sum(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-02",
            oa_rows=[],
            bank_rows=[
                bank_row(
                    "bank-ccb-26880",
                    "26880.00",
                    counterparty_name="北京长征高科技有限公司",
                    direction="inflow",
                    trade_time="2026-02-11 11:49:39",
                )
            ],
            invoice_rows=[
                invoice_row(
                    "invoice-output-001",
                    "13440.00",
                    seller_name="云南溯源科技有限公司",
                    buyer_name="北京长征高科技有限公司",
                    invoice_type="销项发票",
                    issue_date="2026-02-11",
                    total_with_tax="13440.00",
                ),
                invoice_row(
                    "invoice-output-002",
                    "13440.00",
                    seller_name="云南溯源科技有限公司",
                    buyer_name="北京长征高科技有限公司",
                    invoice_type="销项发票",
                    issue_date="2026-02-11",
                    total_with_tax="13440.00",
                ),
            ],
        )

        candidate = find_candidate(candidates, "bank_invoice_exact_sum")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["bank_row_ids"], ["bank-ccb-26880"])
        self.assertEqual(candidate["invoice_row_ids"], ["invoice-output-001", "invoice-output-002"])
        self.assertEqual(candidate["amount"], "26880.00")

    def test_bank_invoice_exact_amount_does_not_create_amount_only_review_candidate(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                bank_row("bank-different-counterparty", "100.00", counterparty_name="供应商A"),
                bank_row("bank-missing-counterparty", "100.00", counterparty_name=""),
                bank_row("bank-amount-only", "100.00", counterparty_name=""),
            ],
            invoice_rows=[
                invoice_row("invoice-different-counterparty", "100.00", seller_name="供应商B"),
                invoice_row("invoice-missing-counterparty", "100.00", seller_name=""),
                invoice_row("invoice-amount-only", "100.00", seller_name=""),
            ],
        )

        disallowed_pairs = [
            ("bank-different-counterparty", "invoice-different-counterparty"),
            ("bank-missing-counterparty", "invoice-missing-counterparty"),
            ("bank-amount-only", "invoice-amount-only"),
        ]
        review_candidates = [
            candidate
            for candidate in candidates
            if candidate["rule_code"] == "bank_invoice_exact_amount" and candidate["status"] == "needs_review"
        ]
        for bank_id, invoice_id in disallowed_pairs:
            self.assertFalse(
                any(bank_id in candidate["bank_row_ids"] and invoice_id in candidate["invoice_row_ids"] for candidate in review_candidates),
                f"unexpected amount-only review candidate for {bank_id} and {invoice_id}",
            )

    def test_bank_invoice_exact_amount_rejects_real_mismatched_counterparty_regression(self) -> None:
        invoice = invoice_row(
            "invoice-zijin-2000",
            "2000.00",
            seller_name="紫金财产保险股份有限公司云南分公司",
            invoice_type="进项发票",
            total_with_tax="2000.00",
        )
        invoice["issue_date"] = "2026-01-20"

        candidates = self.rules.generate_candidates(
            "2026-04",
            oa_rows=[],
            bank_rows=[
                bank_row(
                    "bank-sugaomei-2000",
                    "2000.00",
                    counterparty_name="江阴市溯高美电气有限公司",
                    direction="outflow",
                    trade_time="2026-04-23 00:00:00",
                )
            ],
            invoice_rows=[invoice],
        )

        self.assertEqual(
            [
                candidate
                for candidate in candidates
                if candidate["rule_code"] == "bank_invoice_exact_amount"
                and candidate["status"] == "needs_review"
                and candidate["bank_row_ids"] == ["bank-sugaomei-2000"]
                and candidate["invoice_row_ids"] == ["invoice-zijin-2000"]
            ],
            [],
        )

    def test_salary_personal_text_no_longer_creates_workbench_special_candidate(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[],
            bank_rows=[bank_row("bank-salary", "9.00", counterparty_name="李四", summary="5月工资", direction="outflow")],
            invoice_rows=[],
        )

        self.assertFalse(any(candidate["rule_code"] == "salary_personal_auto_match" for candidate in candidates))
        self.assertTrue(any(candidate["rule_code"] == "no_confident_match" for candidate in candidates))

    def test_internal_transfer_pair_no_longer_creates_workbench_special_candidate(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                bank_row(
                    "bank-out",
                    "50000.00",
                    counterparty_name="云南溯源科技有限公司",
                    direction="outflow",
                    account_no="62220001",
                    account_name="云南溯源科技有限公司建设银行基本户",
                    trade_time="2026-05-02 09:00:00",
                ),
                bank_row(
                    "bank-in",
                    "50000.00",
                    counterparty_name="云南溯源科技有限公司",
                    direction="inflow",
                    account_no="62220002",
                    account_name="云南溯源科技有限公司招商银行一般户",
                    trade_time="2026-05-02 10:00:00",
                ),
            ],
            invoice_rows=[],
        )

        self.assertFalse(any(candidate["rule_code"] == "internal_transfer_pair" for candidate in candidates))
        no_confident = [candidate for candidate in candidates if candidate["rule_code"] == "no_confident_match"]
        self.assertCountEqual([candidate["bank_row_ids"][0] for candidate in no_confident], ["bank-out", "bank-in"])

    def test_oa_invoice_offset_auto_match_uses_configured_applicant_and_attachment_link(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-offset", "600.00", applicant_name="周洁莹", counterparty_name="物业公司")],
            bank_rows=[],
            invoice_rows=[
                invoice_row(
                    "invoice-offset",
                    "600.00",
                    seller_name="物业公司",
                    source_kind="oa_attachment_invoice",
                    oa_row_id="oa-offset",
                )
            ],
            settings={"offset_applicant_names": ["周洁莹"]},
        )

        candidate = find_candidate(candidates, "oa_invoice_offset_auto_match")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["source_versions"]["offset_display_tag"], "冲")
        self.assertIn("冲", candidate["explanation"])

    def test_matching_engine_compatibility_rules_are_generated(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                bank_row("bank-many-invoices", "300.00", counterparty_name="供应商A"),
                bank_row("bank-partial", "80.00", counterparty_name="供应商B"),
                bank_row("bank-unmatched", "45.00", counterparty_name="供应商C"),
                bank_row("bank-split-001", "40.00", counterparty_name="客户D", direction="inflow"),
                bank_row("bank-split-002", "60.00", counterparty_name="客户D", direction="inflow"),
            ],
            invoice_rows=[
                invoice_row("invoice-many-001", "120.00", seller_name="供应商A"),
                invoice_row("invoice-many-002", "180.00", seller_name="供应商A"),
                invoice_row("invoice-partial", "100.00", seller_name="供应商B"),
                invoice_row("invoice-split", "100.00", buyer_name="客户D", invoice_type="销项发票"),
                invoice_row("invoice-unmatched", "33.00", seller_name="供应商E"),
            ],
        )

        bank_invoice_sum = find_candidate(candidates, "bank_invoice_exact_sum")
        self.assertEqual(bank_invoice_sum["status"], "auto_closed")
        self.assertIsNotNone(find_candidate(candidates, "same_counterparty_one_invoice_many_transactions"))
        self.assertIsNotNone(find_candidate(candidates, "same_counterparty_partial_amount_match"))
        no_confident = [candidate for candidate in candidates if candidate["rule_code"] == "no_confident_match"]
        self.assertTrue(any(candidate["bank_row_ids"] == ["bank-unmatched"] for candidate in no_confident))
        self.assertTrue(any(candidate["invoice_row_ids"] == ["invoice-unmatched"] for candidate in no_confident))

    def test_salary_text_does_not_join_auto_closed_conflicts_after_special_rule_removal(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[],
            bank_rows=[bank_row("bank-001", "100.00", counterparty_name="李四", summary="5月工资")],
            invoice_rows=[invoice_row("invoice-001", "100.00", seller_name="李四")],
        )

        auto_claiming_candidates = [
            candidate
            for candidate in candidates
            if candidate["rule_code"] in {"bank_invoice_exact_amount", "salary_personal_auto_match"}
        ]
        self.assertEqual(len(auto_claiming_candidates), 1)
        by_rule_code = {candidate["rule_code"]: candidate for candidate in auto_claiming_candidates}
        self.assertEqual(by_rule_code["bank_invoice_exact_amount"]["status"], "auto_closed")
        self.assertNotIn("salary_personal_auto_match", by_rule_code)

    def test_every_candidate_can_be_upserted(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-001", "300.00", counterparty_name="供应商A")],
            bank_rows=[bank_row("bank-001", "300.00", counterparty_name="供应商A")],
            invoice_rows=[
                invoice_row("invoice-001", "120.00", seller_name="供应商A"),
                invoice_row("invoice-002", "180.00", seller_name="供应商A"),
            ],
            source_versions={"oa": "sync-001", "bank": "import-001", "invoice": "import-002"},
        )
        service = WorkbenchCandidateMatchService()

        upserted = [service.upsert_candidate(candidate) for candidate in candidates]

        self.assertEqual(len(upserted), len(candidates))
        self.assertTrue(all(candidate["candidate_key"].startswith("candidate:") for candidate in upserted))


def find_candidate(candidates: list[dict[str, object]], rule_code: str) -> dict[str, object]:
    matches = [candidate for candidate in candidates if candidate["rule_code"] == rule_code]
    if not matches:
        raise AssertionError(f"missing candidate for rule {rule_code}; got {[item['rule_code'] for item in candidates]}")
    return matches[0]


def find_optional_candidate(candidates: list[dict[str, object]], rule_code: str) -> dict[str, object] | None:
    matches = [candidate for candidate in candidates if candidate["rule_code"] == rule_code]
    return matches[0] if matches else None


def find_candidate_by_rows(
    candidates: list[dict[str, object]],
    rule_code: str,
    row_ids: list[str],
) -> dict[str, object] | None:
    expected = sorted(row_ids)
    matches = [
        candidate
        for candidate in candidates
        if candidate["rule_code"] == rule_code and sorted(candidate["row_ids"]) == expected
    ]
    return matches[0] if matches else None


def oa_row(
    row_id: str,
    amount: str,
    *,
    counterparty_name: str = "供应商A",
    applicant_name: str = "申请人",
    apply_type: str = "付款申请",
    project_name: str = "",
    reason: str = "",
    pay_receive_time: str = "2026-05-03",
    expense_items: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "amount": amount,
        "apply_type": apply_type,
        "counterparty_name": counterparty_name,
        "applicant_name": applicant_name,
        "applicant": applicant_name,
        "project_name": project_name,
        "reason": reason,
        "expense_items": expense_items or [],
        "pay_receive_time": pay_receive_time,
    }


def bank_row(
    row_id: str,
    amount: str,
    *,
    counterparty_name: str = "供应商A",
    direction: str = "outflow",
    summary: str = "",
    remark: str = "",
    account_no: str = "62220001",
    account_name: str = "云南溯源科技有限公司建设银行基本户",
    trade_time: str = "2026-05-03 09:00:00",
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "debit_amount": amount if direction == "outflow" else "",
        "credit_amount": amount if direction == "inflow" else "",
        "counterparty_name": counterparty_name,
        "summary": summary,
        "remark": remark,
        "account_no": account_no,
        "account_name": account_name,
        "trade_time": trade_time,
        "pay_receive_time": trade_time,
    }


def invoice_row(
    row_id: str,
    amount: str,
    *,
    seller_name: str = "供应商A",
    buyer_name: str = "云南溯源科技有限公司",
    invoice_type: str = "进项发票",
    issue_date: str = "2026-05-03",
    source_kind: str | None = None,
    oa_row_id: str | None = None,
    derived_from_oa_id: str | None = None,
    invoice_no: str | None = None,
    total_with_tax: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": row_id,
        "type": "invoice",
        "amount": amount,
        "total_with_tax": total_with_tax if total_with_tax is not None else amount,
        "seller_name": seller_name,
        "buyer_name": buyer_name,
        "invoice_type": invoice_type,
        "issue_date": issue_date,
    }
    if source_kind is not None:
        row["source_kind"] = source_kind
    if oa_row_id is not None:
        row["oa_row_id"] = oa_row_id
    if derived_from_oa_id is not None:
        row["derived_from_oa_id"] = derived_from_oa_id
    if invoice_no is not None:
        row["invoice_no"] = invoice_no
    return row


if __name__ == "__main__":
    unittest.main()
