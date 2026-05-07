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

    def test_bank_invoice_exact_amount_uses_matching_engine_compatibility_code_for_same_counterparty(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[],
            bank_rows=[bank_row("bank-001", "100.00", counterparty_name="客户A", direction="inflow")],
            invoice_rows=[invoice_row("invoice-001", "100.00", buyer_name="客户A", invoice_type="销项发票")],
        )

        candidate = find_candidate(candidates, "exact_counterparty_amount_one_to_one")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["candidate_type"], "bank_invoice")

    def test_salary_personal_auto_match(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[],
            bank_rows=[bank_row("bank-salary", "9.00", counterparty_name="李四", summary="5月工资", direction="outflow")],
            invoice_rows=[],
        )

        candidate = find_candidate(candidates, "salary_personal_auto_match")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertEqual(candidate["bank_row_ids"], ["bank-salary"])

    def test_internal_transfer_pair_matches_opposite_bank_directions_within_window(self) -> None:
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

        candidate = find_candidate(candidates, "internal_transfer_pair")
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["confidence"], "high")
        self.assertCountEqual(candidate["bank_row_ids"], ["bank-out", "bank-in"])

    def test_oa_invoice_offset_auto_match_uses_configured_applicant_and_attachment_link(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[oa_row("oa-offset", "600.00", applicant_name="张三", counterparty_name="物业公司")],
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
            settings={"offset_applicant_names": ["张三"]},
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

        self.assertIsNotNone(find_candidate(candidates, "same_counterparty_many_invoices_one_transaction"))
        self.assertIsNotNone(find_candidate(candidates, "same_counterparty_one_invoice_many_transactions"))
        self.assertIsNotNone(find_candidate(candidates, "same_counterparty_partial_amount_match"))
        no_confident = [candidate for candidate in candidates if candidate["rule_code"] == "no_confident_match"]
        self.assertTrue(any(candidate["bank_row_ids"] == ["bank-unmatched"] for candidate in no_confident))
        self.assertTrue(any(candidate["invoice_row_ids"] == ["invoice-unmatched"] for candidate in no_confident))

    def test_conflicting_auto_closed_candidates_are_marked_conflict(self) -> None:
        candidates = self.rules.generate_candidates(
            "2026-05",
            oa_rows=[],
            bank_rows=[bank_row("bank-001", "100.00", counterparty_name="李四", summary="5月工资")],
            invoice_rows=[invoice_row("invoice-001", "100.00", seller_name="李四")],
        )

        auto_claiming_candidates = [
            candidate
            for candidate in candidates
            if candidate["rule_code"] in {"exact_counterparty_amount_one_to_one", "salary_personal_auto_match"}
        ]
        self.assertEqual(len(auto_claiming_candidates), 2)
        self.assertTrue(all(candidate["status"] == "conflict" for candidate in auto_claiming_candidates))
        self.assertTrue(all(candidate["conflict_candidate_keys"] for candidate in auto_claiming_candidates))

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


def oa_row(
    row_id: str,
    amount: str,
    *,
    counterparty_name: str = "供应商A",
    applicant_name: str = "申请人",
    expense_items: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "amount": amount,
        "apply_type": "付款申请",
        "counterparty_name": counterparty_name,
        "applicant_name": applicant_name,
        "expense_items": expense_items or [],
        "pay_receive_time": "2026-05-03",
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
    source_kind: str | None = None,
    oa_row_id: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": row_id,
        "type": "invoice",
        "amount": amount,
        "total_with_tax": amount,
        "seller_name": seller_name,
        "buyer_name": buyer_name,
        "invoice_type": invoice_type,
        "issue_date": "2026-05-03",
    }
    if source_kind is not None:
        row["source_kind"] = source_kind
    if oa_row_id is not None:
        row["oa_row_id"] = oa_row_id
    return row


if __name__ == "__main__":
    unittest.main()
