import unittest

from fin_ops_platform.services.workbench_candidate_grouping import WorkbenchCandidateGroupingService


class WorkbenchCandidateGroupingTests(unittest.TestCase):
    def test_groups_aggregated_oa_with_manual_imported_invoice_sum(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "all",
            oa_rows=[
                {
                    "id": "oa-exp-1994",
                    "type": "oa",
                    "case_id": None,
                    "apply_type": "日常报销",
                    "amount": "1549.00",
                    "counterparty_name": "上海会务服务有限公司",
                    "expense_type": "会议服务",
                    "expense_content": "会场租赁；资料印刷",
                    "reason": "季度客户会议",
                    "_month": "2026-02",
                    "_detail_fields": {
                        "申请日期": "2026-02-02",
                        "明细数量": "1",
                        "费用内容摘要": "会场租赁；资料印刷",
                    },
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "iv-meeting-001",
                    "type": "invoice",
                    "case_id": None,
                    "source_kind": None,
                    "amount": "971.70",
                    "total_with_tax": "1000.00",
                    "issue_date": "2026-01-31",
                    "seller_name": "上海会务服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-meeting-002",
                    "type": "invoice",
                    "case_id": None,
                    "source_kind": None,
                    "amount": "531.07",
                    "total_with_tax": "549.00",
                    "issue_date": "2026-01-30",
                    "seller_name": "上海会务服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-other-month",
                    "type": "invoice",
                    "case_id": None,
                    "source_kind": None,
                    "amount": "971.70",
                    "total_with_tax": "1000.00",
                    "issue_date": "2026-03-01",
                    "seller_name": "上海会务服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 2)
        group = next(
            group
            for group in payload["open"]["groups"]
            if group["reason"] == "aggregated_oa_multi_invoice_sum_candidate"
        )
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-exp-1994"])
        self.assertCountEqual([row["id"] for row in group["invoice_rows"]], ["iv-meeting-001", "iv-meeting-002"])

    def test_groups_aggregated_oa_with_empty_counterparty_when_invoice_subset_is_unique(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-04",
            oa_rows=[
                {
                    "id": "oa-travel-001",
                    "type": "oa",
                    "case_id": None,
                    "apply_type": "日常报销",
                    "amount": "300.00",
                    "counterparty_name": "",
                    "_month": "2026-04",
                    "expense_items": [{"amount": "120.00"}, {"amount": "180.00"}],
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "iv-travel-001",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "120.00",
                    "issue_date": "2026-04-08",
                    "seller_name": "昆明酒店有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-travel-002",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "180.00",
                    "issue_date": "2026-04-09",
                    "seller_name": "昆明票务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-travel-003",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "90.00",
                    "issue_date": "2026-04-10",
                    "seller_name": "昆明餐饮有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
            ],
        )

        groups = [
            group
            for group in payload["open"]["groups"]
            if group["reason"] == "aggregated_oa_multi_invoice_sum_candidate"
        ]
        self.assertEqual(len(groups), 1)
        self.assertEqual([row["id"] for row in groups[0]["oa_rows"]], ["oa-travel-001"])
        self.assertCountEqual([row["id"] for row in groups[0]["invoice_rows"]], ["iv-travel-001", "iv-travel-002"])

    def test_skips_aggregated_oa_when_multiple_invoice_subsets_match_amount(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-04",
            oa_rows=[
                {
                    "id": "oa-services-001",
                    "type": "oa",
                    "case_id": None,
                    "amount": "300.00",
                    "counterparty_name": "杭州服务有限公司",
                    "_month": "2026-04",
                    "_detail_fields": {"明细数量": "3"},
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "iv-services-100",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "100.00",
                    "issue_date": "2026-04-08",
                    "seller_name": "杭州服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-services-200",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "200.00",
                    "issue_date": "2026-04-09",
                    "seller_name": "杭州服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-services-300",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "300.00",
                    "issue_date": "2026-04-10",
                    "seller_name": "杭州服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
            ],
        )

        self.assertFalse(
            any(group["reason"] == "aggregated_oa_multi_invoice_sum_candidate" for group in payload["open"]["groups"])
        )

    def test_skips_conflicting_aggregated_oa_matches_that_share_invoice_rows(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-04",
            oa_rows=[
                {
                    "id": "oa-conflict-001",
                    "type": "oa",
                    "case_id": None,
                    "amount": "300.00",
                    "counterparty_name": "共享供应商有限公司",
                    "_month": "2026-04",
                    "_detail_fields": {"明细数量": "2"},
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                },
                {
                    "id": "oa-conflict-002",
                    "type": "oa",
                    "case_id": None,
                    "amount": "300.00",
                    "counterparty_name": "共享供应商有限公司",
                    "_month": "2026-04",
                    "_detail_fields": {"明细数量": "2"},
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                },
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "iv-conflict-001",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "120.00",
                    "issue_date": "2026-04-08",
                    "seller_name": "共享供应商有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-conflict-002",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "180.00",
                    "issue_date": "2026-04-09",
                    "seller_name": "共享供应商有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
            ],
        )

        self.assertFalse(
            any(group["reason"] == "aggregated_oa_multi_invoice_sum_candidate" for group in payload["open"]["groups"])
        )
        self.assertEqual(payload["summary"]["open_count"], 3)

    def test_oa_attachment_invoice_uses_total_with_tax_for_amount_matching(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-001",
                    "type": "oa",
                    "case_id": None,
                    "amount": "200.00",
                    "counterparty_name": "云南中油严家山交通服务有限公司",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "iv-oa-att-001",
                    "type": "invoice",
                    "case_id": None,
                    "source_kind": "oa_attachment_invoice",
                    "amount": "176.99",
                    "total_with_tax": "200.00",
                    "issue_date": "2026-03-24",
                    "seller_name": "云南中油严家山交通服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["open_count"], 1)
        self.assertEqual(len(payload["open"]["groups"]), 1)
        group = payload["open"]["groups"][0]
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-001"])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["iv-oa-att-001"])

    def test_promotes_unique_three_way_chain_to_paired_group(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-001",
                    "type": "oa",
                    "case_id": None,
                    "amount": "150.00",
                    "counterparty_name": "华东设备供应商",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-001",
                    "type": "bank",
                    "case_id": None,
                    "trade_time": "2026-03-25 14:22",
                    "debit_amount": "150.00",
                    "credit_amount": "",
                    "counterparty_name": "华东设备供应商",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-001",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "150.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "华东设备供应商",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["open_count"], 0)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["group_type"], "auto_closed")
        self.assertEqual(group["match_confidence"], "high")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-001"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-001"])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["iv-001"])

    def test_manual_confirmed_pair_relation_takes_precedence_over_automatic_candidate_shape(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-manual-001",
                    "type": "oa",
                    "case_id": "CASE-MANUAL-001",
                    "amount": "150.00",
                    "counterparty_name": "手工确认供应商",
                    "oa_bank_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                },
            ],
            bank_rows=[
                {
                    "id": "bk-manual-001",
                    "type": "bank",
                    "case_id": "CASE-MANUAL-001",
                    "trade_time": "2026-03-25 14:22",
                    "debit_amount": "150.00",
                    "credit_amount": "",
                    "counterparty_name": "手工确认供应商",
                    "invoice_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                },
            ],
            invoice_rows=[
                {
                    "id": "iv-manual-001",
                    "type": "invoice",
                    "case_id": "CASE-MANUAL-001",
                    "amount": "150.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "手工确认供应商",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                },
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["open_count"], 0)
        manual_group = payload["paired"]["groups"][0]
        self.assertEqual(manual_group["group_id"], "case:CASE-MANUAL-001")
        self.assertEqual(manual_group["group_type"], "manual_confirmed")
        self.assertEqual([row["id"] for row in manual_group["oa_rows"]], ["oa-manual-001"])
        self.assertEqual([row["id"] for row in manual_group["bank_rows"]], ["bk-manual-001"])
        self.assertEqual([row["id"] for row in manual_group["invoice_rows"]], ["iv-manual-001"])

    def test_promotes_oa_bank_with_multiple_attachment_invoices_when_amounts_close_loop(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-attach-001",
                    "type": "oa",
                    "case_id": "CASE-ATTACH-001",
                    "amount": "300.00",
                    "counterparty_name": "附件发票供应商",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-attach-001",
                    "type": "bank",
                    "case_id": "CASE-ATTACH-001",
                    "trade_time": "2026-03-25 14:22",
                    "debit_amount": "300.00",
                    "credit_amount": "",
                    "counterparty_name": "附件发票供应商",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-attach-001",
                    "type": "invoice",
                    "case_id": "CASE-ATTACH-001",
                    "source_kind": "oa_attachment_invoice",
                    "amount": "120.00",
                    "total_with_tax": "120.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "附件发票供应商",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-attach-002",
                    "type": "invoice",
                    "case_id": "CASE-ATTACH-001",
                    "source_kind": "oa_attachment_invoice",
                    "amount": "180.00",
                    "total_with_tax": "180.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "附件发票供应商",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["open_count"], 0)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["group_type"], "auto_closed")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-attach-001"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-attach-001"])
        self.assertCountEqual([row["id"] for row in group["invoice_rows"]], ["iv-attach-001", "iv-attach-002"])

    def test_keeps_oa_and_multiple_invoices_open_when_bank_transaction_is_missing(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-missing-bank-001",
                    "type": "oa",
                    "case_id": None,
                    "amount": "300.00",
                    "counterparty_name": "缺少流水供应商",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "iv-missing-bank-001",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "120.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "缺少流水供应商",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-missing-bank-002",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "180.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "缺少流水供应商",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertGreaterEqual(payload["summary"]["open_count"], 1)
        open_ids = [row["id"] for row in flatten_groups(payload["open"]["groups"], "oa")]
        self.assertIn("oa-missing-bank-001", open_ids)

    def test_conflicting_three_way_candidate_combinations_do_not_appear_as_paired(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-conflict-001",
                    "type": "oa",
                    "case_id": None,
                    "amount": "150.00",
                    "counterparty_name": "冲突供应商",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                },
                {
                    "id": "oa-conflict-002",
                    "type": "oa",
                    "case_id": None,
                    "amount": "150.00",
                    "counterparty_name": "冲突供应商",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                },
            ],
            bank_rows=[
                {
                    "id": "bk-conflict-001",
                    "type": "bank",
                    "case_id": None,
                    "trade_time": "2026-03-25 14:22",
                    "debit_amount": "150.00",
                    "credit_amount": "",
                    "counterparty_name": "冲突供应商",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-conflict-001",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "150.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "冲突供应商",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["paired"]["groups"], [])
        self.assertIn("bk-conflict-001", [row["id"] for row in flatten_groups(payload["open"]["groups"], "bank")])

    def test_keeps_ambiguous_many_to_one_as_open_candidate_group(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-001",
                    "type": "oa",
                    "case_id": None,
                    "amount": "300.00",
                    "counterparty_name": "杭州设备商",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-001",
                    "type": "bank",
                    "case_id": None,
                    "debit_amount": "150.00",
                    "credit_amount": "",
                    "counterparty_name": "杭州设备商",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "bk-002",
                    "type": "bank",
                    "case_id": None,
                    "debit_amount": "150.00",
                    "credit_amount": "",
                    "counterparty_name": "杭州设备商",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        self.assertEqual(len(payload["open"]["groups"]), 1)
        ambiguous_group = payload["open"]["groups"][0]
        self.assertEqual(ambiguous_group["group_type"], "candidate")
        self.assertEqual([row["id"] for row in ambiguous_group["oa_rows"]], ["oa-001"])
        self.assertEqual(len(ambiguous_group["bank_rows"]), 2)
        self.assertEqual(group_ids(payload["open"]["groups"], "bank_rows"), [["bk-001", "bk-002"]])

    def test_promotes_case_less_oa_into_exact_three_way_paired_group(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-001",
                    "type": "oa",
                    "case_id": None,
                    "amount": "120.00",
                    "counterparty_name": "云上客户",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-001",
                    "type": "bank",
                    "case_id": "match_result_001",
                    "debit_amount": "120.00",
                    "credit_amount": "",
                    "counterparty_name": "云上客户",
                    "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-001",
                    "type": "invoice",
                    "case_id": "match_result_001",
                    "amount": "120.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "云上客户",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["open_count"], 0)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["group_type"], "auto_closed")
        self.assertEqual(group["match_confidence"], "high")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-001"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-001"])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["iv-001"])

    def test_keeps_exact_open_case_oa_bank_group_in_open_until_invoice_exists(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-001",
                    "type": "oa",
                    "case_id": None,
                    "apply_type": "支付申请",
                    "amount": "120.00",
                    "counterparty_name": "云上客户",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    "available_actions": ["detail", "confirm_link", "mark_exception"],
                }
            ],
            bank_rows=[
                {
                    "id": "bk-001",
                    "type": "bank",
                    "case_id": "match_result_001",
                    "debit_amount": "120.00",
                    "credit_amount": "",
                    "counterparty_name": "云上客户",
                    "invoice_relation": {"code": "manual_review", "label": "待人工核查", "tone": "danger"},
                    "available_actions": ["detail", "view_relation", "cancel_link", "handle_exception"],
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_type"], "candidate")
        self.assertEqual(group["match_confidence"], "medium")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-001"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-001"])

    def test_etc_batch_oa_bank_group_auto_closes_without_invoice(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[
                {
                    "id": "oa-etc-001",
                    "type": "oa",
                    "source": "etc_batch",
                    "etc_batch_id": "etc_20260503_001",
                    "tags": ["ETC批量提交"],
                    "case_id": None,
                    "apply_type": "支付申请",
                    "amount": "53.84",
                    "counterparty_name": "云南高速通行费",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水", "tone": "warn"},
                    "available_actions": ["detail", "confirm_link", "mark_exception"],
                }
            ],
            bank_rows=[
                {
                    "id": "bk-etc-001",
                    "type": "bank",
                    "case_id": None,
                    "trade_time": "2026-05-03 14:22",
                    "debit_amount": "53.84",
                    "credit_amount": "",
                    "counterparty_name": "云南高速通行费",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                    "available_actions": ["detail", "view_relation", "cancel_link", "handle_exception"],
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["open_count"], 0)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["group_type"], "auto_closed")
        self.assertEqual(group["oa_rows"][0]["oa_bank_relation"]["label"], "已关联流水")
        self.assertEqual(group["bank_rows"][0]["invoice_relation"]["label"], "已关联OA")
        self.assertEqual(group["invoice_rows"], [])

    def test_keeps_exact_open_case_bank_invoice_group_in_open_until_oa_exists(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-001",
                    "type": "bank",
                    "case_id": "match_result_001",
                    "debit_amount": "120.00",
                    "credit_amount": "",
                    "counterparty_name": "云上客户",
                    "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                    "available_actions": ["detail", "view_relation", "cancel_link", "handle_exception"],
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-001",
                    "type": "invoice",
                    "case_id": "match_result_001",
                    "amount": "120.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "云上客户",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                    "available_actions": ["detail", "confirm_link", "mark_exception"],
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_type"], "candidate")
        self.assertEqual(group["match_confidence"], "medium")
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-001"])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["iv-001"])

    def test_keeps_single_bank_salary_auto_match_in_paired_section(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-02",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-salary-001",
                    "type": "bank",
                    "case_id": "salary_auto_bk-salary-001",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "counterparty_name": "李四",
                    "invoice_relation": {"code": "salary_personal_auto_match", "label": "已匹配：工资", "tone": "success"},
                    "available_actions": ["detail"],
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["open_count"], 0)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["group_type"], "auto_closed")
        self.assertEqual(group["bank_rows"][0]["invoice_relation"]["code"], "salary_personal_auto_match")
        self.assertEqual(group["bank_rows"][0]["invoice_relation"]["label"], "已匹配：工资")

    def test_keeps_internal_transfer_pair_together_in_paired_section_only_when_both_bank_rows_exist(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-transfer-001",
                    "type": "bank",
                    "case_id": "internal_transfer_case_001",
                    "trade_time": "2026-03-19 11:15:00",
                    "debit_amount": "",
                    "credit_amount": "13000.00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "invoice_relation": {"code": "internal_transfer_pair", "label": "已匹配：内部往来款", "tone": "success"},
                    "available_actions": ["detail"],
                },
                {
                    "id": "bk-transfer-002",
                    "type": "bank",
                    "case_id": "internal_transfer_case_001",
                    "trade_time": "2026-03-19 11:16:00",
                    "debit_amount": "13000.00",
                    "credit_amount": "",
                    "counterparty_name": "云南溯源科技有限公司",
                    "invoice_relation": {"code": "internal_transfer_pair", "label": "已匹配：内部往来款", "tone": "success"},
                    "available_actions": ["detail"],
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["open_count"], 0)
        group = payload["paired"]["groups"][0]
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-transfer-001", "bk-transfer-002"])

    def test_demotes_single_sided_internal_transfer_row_back_to_open_section(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-transfer-001",
                    "type": "bank",
                    "case_id": "internal_transfer_case_001",
                    "trade_time": "2026-03-19 11:15:00",
                    "debit_amount": "",
                    "credit_amount": "13000.00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "invoice_relation": {"code": "internal_transfer_pair", "label": "已匹配：内部往来款", "tone": "success"},
                    "available_actions": ["detail"],
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        self.assertEqual(len(payload["paired"]["groups"]), 0)
        self.assertEqual(len(payload["open"]["groups"]), 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_type"], "candidate")
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-transfer-001"])

    def test_separates_same_counterparty_rows_when_amount_buckets_differ(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-001",
                    "type": "oa",
                    "case_id": None,
                    "amount": "1000.00",
                    "counterparty_name": "同一服务商",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                },
                {
                    "id": "oa-002",
                    "type": "oa",
                    "case_id": None,
                    "amount": "2000.00",
                    "counterparty_name": "同一服务商",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                },
            ],
            bank_rows=[],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["open_count"], 2)
        self.assertEqual(len(payload["open"]["groups"]), 2)
        self.assertCountEqual(group_ids(payload["open"]["groups"], "oa_rows"), [["oa-001"], ["oa-002"]])

    def test_demotes_existing_two_type_case_id_rows_back_to_open_section(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-001",
                    "type": "oa",
                    "case_id": "CASE-001",
                    "amount": "500.00",
                    "counterparty_name": "星云供应商",
                    "oa_bank_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-001",
                    "type": "bank",
                    "case_id": "CASE-001",
                    "debit_amount": "500.00",
                    "credit_amount": "",
                    "counterparty_name": "星云供应商",
                    "invoice_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_id"], "case:CASE-001")
        self.assertEqual(group["group_type"], "candidate")
        self.assertEqual(group["match_confidence"], "medium")

    def test_demotes_single_type_paired_invoice_group_back_to_open(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "iv-001",
                    "type": "invoice",
                    "case_id": "match_result_404",
                    "amount": "150.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "华东设备供应商",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "automatic_match", "label": "自动匹配", "tone": "success"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        self.assertEqual(len(payload["paired"]["groups"]), 0)
        self.assertEqual(len(payload["open"]["groups"]), 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_type"], "candidate")
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["iv-001"])

    def test_preserves_automatic_match_label_for_candidate_paired_groups(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-001",
                    "type": "oa",
                    "case_id": "auto-match-001",
                    "amount": "150.00",
                    "pay_receive_time": "2026-03-26",
                    "counterparty_name": "华东设备供应商",
                    "oa_bank_relation": {"code": "automatic_match", "label": "自动匹配", "tone": "success"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-001",
                    "type": "bank",
                    "case_id": "auto-match-001",
                    "debit_amount": "150.00",
                    "credit_amount": "",
                    "trade_time": "2026-03-26",
                    "counterparty_name": "华东设备供应商",
                    "invoice_relation": {"code": "automatic_match", "label": "自动匹配", "tone": "success"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-001",
                    "type": "invoice",
                    "case_id": "auto-match-001",
                    "amount": "150.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "华东设备供应商",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "automatic_match", "label": "自动匹配", "tone": "success"},
                }
            ],
        )

        group = payload["paired"]["groups"][0]
        self.assertEqual(group["bank_rows"][0]["invoice_relation"]["label"], "自动匹配")
        self.assertEqual(group["invoice_rows"][0]["invoice_bank_relation"]["label"], "自动匹配")


def group_ids(groups: list[dict[str, object]], key: str) -> list[list[str]]:
    return [[row["id"] for row in group[key]] for group in groups]


def flatten_groups(groups: list[dict[str, object]], row_type: str) -> list[dict[str, object]]:
    return [
        row
        for group in groups
        for row in group[f"{row_type}_rows"]
    ]


if __name__ == "__main__":
    unittest.main()
