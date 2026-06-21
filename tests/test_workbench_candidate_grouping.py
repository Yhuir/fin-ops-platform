import unittest

from fin_ops_platform.services.workbench_candidate_grouping import WorkbenchCandidateGroupingService


class WorkbenchCandidateGroupingTests(unittest.TestCase):
    def test_no_oa_bank_batch_group_collapses_to_summary_and_preserves_bank_rows(self) -> None:
        service = WorkbenchCandidateGroupingService()
        batch_id = "no_oa_batch_fee_001"
        payload = service.group_payload(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                no_oa_bank_row(
                    "bk-no-oa-fee-001",
                    batch_id=batch_id,
                    debit_amount="50.00",
                    remark="手续费明细 A",
                    batch_version=2,
                ),
                no_oa_bank_row(
                    "bk-no-oa-fee-002",
                    batch_id=batch_id,
                    debit_amount="38.00",
                    remark="手续费明细 B",
                    batch_version=2,
                ),
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(group["display_mode"], "collapsed_summary")
        self.assertTrue(group["default_collapsed"])
        summary_row_id = f"no_oa_summary:{batch_id}"
        collapsed_bank_row_ids = [row["id"] for row in group["collapsed_rows"]["bank"]]
        self.assertEqual([row["id"] for row in group["bank_rows"]], [summary_row_id])
        self.assertCountEqual(
            collapsed_bank_row_ids,
            ["bk-no-oa-fee-001", "bk-no-oa-fee-002"],
        )
        self.assertNotIn(summary_row_id, collapsed_bank_row_ids)

        summary_row = group["summary_row"]
        self.assertEqual(summary_row["id"], summary_row_id)
        self.assertEqual(summary_row["source_kind"], "no_oa_bank_batch_summary")
        self.assertEqual(summary_row["amount"], "88.00")
        self.assertIn("withdraw_no_oa_batch", summary_row["available_actions"])
        metadata = summary_row["special_metadata"]
        self.assertEqual(metadata["source_batch_id"], batch_id)
        self.assertEqual(metadata["batch_version"], 2)
        self.assertEqual(metadata["batch_type"], "fee")
        self.assertEqual(metadata["batch_label"], "手续费")
        self.assertEqual(metadata["row_count"], 2)
        self.assertEqual(metadata["total_amount"], "88.00")
        self.assertTrue(metadata["withdrawable"])

    def test_internal_transfer_no_oa_summary_uses_business_amount_not_bank_row_sum(self) -> None:
        service = WorkbenchCandidateGroupingService()
        batch_id = "no_oa_batch_internal_001"
        special_metadata = {
            "source": "no_oa_bank_batch",
            "source_batch_id": batch_id,
            "batch_type": "internal_transfer",
            "batch_label": "内部往来款",
            "total_amount": "13000.00",
            "withdrawable": True,
            "relation_mode": "no_oa_bank_batch",
            "display_tags": ["免OA", "内部往来款"],
        }
        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-transfer-income",
                    "type": "bank",
                    "case_id": batch_id,
                    "relation_mode": "no_oa_bank_batch",
                    "trade_time": "2026-03-19 11:15:00",
                    "debit_amount": "",
                    "credit_amount": "13000.00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "invoice_relation": {"code": "no_oa_bank_batch", "label": "已匹配：内部往来款", "tone": "success"},
                    "display_tags": ["免OA", "内部往来款"],
                    "special_metadata": special_metadata,
                },
                {
                    "id": "bk-transfer-expense",
                    "type": "bank",
                    "case_id": batch_id,
                    "relation_mode": "no_oa_bank_batch",
                    "trade_time": "2026-03-19 11:16:00",
                    "debit_amount": "13000.00",
                    "credit_amount": "",
                    "counterparty_name": "云南溯源科技有限公司",
                    "invoice_relation": {"code": "no_oa_bank_batch", "label": "已匹配：内部往来款", "tone": "success"},
                    "display_tags": ["免OA", "内部往来款"],
                    "special_metadata": special_metadata,
                },
            ],
            invoice_rows=[],
        )

        group = payload["paired"]["groups"][0]
        self.assertEqual(group["display_mode"], "collapsed_summary")
        self.assertEqual(group["summary_row"]["amount"], "13000.00")
        self.assertEqual(group["summary_row"]["debit_amount"], "13000.00")
        self.assertEqual(group["summary_row"]["special_metadata"]["total_amount"], "13000.00")
        self.assertCountEqual(
            [row["id"] for row in group["collapsed_rows"]["bank"]],
            ["bk-transfer-income", "bk-transfer-expense"],
        )

    def test_single_row_no_oa_bank_batch_stays_as_regular_bank_row(self) -> None:
        service = WorkbenchCandidateGroupingService()
        batch_id = "no_oa_batch_fee_single"
        payload = service.group_payload(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                no_oa_bank_row(
                    "bk-no-oa-fee-single",
                    batch_id=batch_id,
                    debit_amount="12.00",
                    remark="单条手续费",
                    batch_version=2,
                ),
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["relation_mode"], "no_oa_bank_batch")
        self.assertNotEqual(group.get("display_mode"), "collapsed_summary")
        self.assertNotIn("collapsed_rows", group)
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-no-oa-fee-single"])
        self.assertEqual(group["bank_rows"][0]["special_metadata"]["source_batch_id"], batch_id)

    def test_mixed_no_oa_and_manual_relation_group_does_not_collapse(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[
                {
                    "id": "oa-manual-001",
                    "type": "oa",
                    "case_id": "CASE-MIXED-NO-OA",
                    "amount": "20.00",
                    "counterparty_name": "手工供应商",
                    "oa_bank_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                }
            ],
            bank_rows=[
                no_oa_bank_row(
                    "bk-no-oa-mixed-001",
                    batch_id="no_oa_batch_mixed_001",
                    case_id="CASE-MIXED-NO-OA",
                    debit_amount="12.00",
                    remark="免OA明细",
                ),
                {
                    "id": "bk-manual-001",
                    "type": "bank",
                    "case_id": "CASE-MIXED-NO-OA",
                    "debit_amount": "20.00",
                    "credit_amount": "",
                    "counterparty_name": "手工供应商",
                    "invoice_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                },
            ],
            invoice_rows=[
                {
                    "id": "iv-manual-001",
                    "type": "invoice",
                    "case_id": "CASE-MIXED-NO-OA",
                    "amount": "20.00",
                    "seller_name": "手工供应商",
                    "invoice_bank_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        group = payload["paired"]["groups"][0]
        self.assertNotEqual(group.get("display_mode"), "collapsed_summary")
        self.assertNotIn("collapsed_rows", group)
        self.assertCountEqual([row["id"] for row in group["bank_rows"]], ["bk-no-oa-mixed-001", "bk-manual-001"])

    def test_no_oa_bank_rows_from_different_batches_do_not_collapse_together(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                no_oa_bank_row(
                    "bk-no-oa-batch-a",
                    batch_id="no_oa_batch_fee_a",
                    case_id="CASE-NO-OA-DIFFERENT-BATCHES",
                    debit_amount="12.00",
                    remark="批次 A",
                ),
                no_oa_bank_row(
                    "bk-no-oa-batch-b",
                    batch_id="no_oa_batch_fee_b",
                    case_id="CASE-NO-OA-DIFFERENT-BATCHES",
                    debit_amount="13.00",
                    remark="批次 B",
                ),
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        group = payload["paired"]["groups"][0]
        self.assertNotEqual(group.get("display_mode"), "collapsed_summary")
        self.assertNotIn("collapsed_rows", group)
        self.assertCountEqual([row["id"] for row in group["bank_rows"]], ["bk-no-oa-batch-a", "bk-no-oa-batch-b"])

    def test_open_exception_case_stays_open_and_candidate_does_not_promote_it(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[
                {
                    "id": "oa-open-case-001",
                    "type": "oa",
                    "case_id": "WEX-OPEN-001",
                    "exception_case_id": "WEX-OPEN-001",
                    "projection_version": "exception_projection_v1",
                    "case_status": "open",
                    "amount": "120.00",
                    "counterparty_name": "云上客户",
                    "oa_bank_relation": {"code": "wait_input_invoice", "label": "等待进项发票", "tone": "danger"},
                    "handled_exception": True,
                }
            ],
            bank_rows=[
                {
                    "id": "bk-open-case-candidate-001",
                    "type": "bank",
                    "case_id": "candidate:open-case-match",
                    "debit_amount": "120.00",
                    "credit_amount": "",
                    "counterparty_name": "云上客户",
                    "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-open-case-candidate-001",
                    "type": "invoice",
                    "case_id": "candidate:open-case-match",
                    "amount": "120.00",
                    "issue_date": "2026-05-11",
                    "seller_name": "云上客户",
                    "buyer_name": "杭州溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        open_case_group = next(group for group in payload["open"]["groups"] if group["group_id"] == "case:WEX-OPEN-001")
        self.assertEqual(open_case_group["group_type"], "open_exception")
        self.assertEqual([row["id"] for row in open_case_group["oa_rows"]], ["oa-open-case-001"])
        self.assertIn(
            "bk-open-case-candidate-001",
            [row["id"] for row in flatten_groups(payload["open"]["groups"], "bank")],
        )

    def test_closed_case_relation_projection_groups_as_processed_exception(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[
                {
                    "id": "oa-closed-001",
                    "type": "oa",
                    "case_id": "WEX-CLOSED-001",
                    "exception_case_id": "WEX-CLOSED-001",
                    "projection_version": "exception_projection_v1",
                    "projection_kind": "pair_relation",
                    "case_status": "closed",
                    "relation_mode": "expense_closed",
                    "amount": "120.00",
                    "counterparty_name": "云上客户",
                    "oa_bank_relation": {"code": "expense_closed", "label": "已处理：支出闭环", "tone": "success"},
                    "display_tags": ["支出闭环"],
                }
            ],
            bank_rows=[
                {
                    "id": "bk-closed-001",
                    "type": "bank",
                    "case_id": "WEX-CLOSED-001",
                    "exception_case_id": "WEX-CLOSED-001",
                    "projection_version": "exception_projection_v1",
                    "projection_kind": "pair_relation",
                    "case_status": "closed",
                    "relation_mode": "expense_closed",
                    "debit_amount": "120.00",
                    "credit_amount": "",
                    "counterparty_name": "云上客户",
                    "invoice_relation": {"code": "expense_closed", "label": "已处理：支出闭环", "tone": "success"},
                    "display_tags": ["支出闭环"],
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["group_id"], "case:WEX-CLOSED-001")
        self.assertEqual(group["group_type"], "processed_exception")
        self.assertEqual(group["relation_mode"], "expense_closed")
        self.assertEqual(group["display_tags"], ["支出闭环"])

    def test_oa_exempt_relation_uses_projection_metadata_for_display_tags(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-oa-exempt-001",
                    "type": "bank",
                    "case_id": "WEX-OA-EXEMPT-001",
                    "exception_case_id": "WEX-OA-EXEMPT-001",
                    "projection_version": "exception_projection_v1",
                    "projection_kind": "pair_relation",
                    "case_status": "closed",
                    "relation_mode": "oa_exempt",
                    "debit_amount": "120.00",
                    "credit_amount": "",
                    "counterparty_name": "张三",
                    "invoice_relation": {"code": "oa_exempt", "label": "已处理：免 OA", "tone": "success"},
                    "display_tags": ["自动免OA", "工资"],
                    "tags": ["自动免OA", "工资"],
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["group_type"], "processed_exception")
        self.assertEqual(group["relation_mode"], "oa_exempt")
        self.assertEqual(group["display_tags"], ["自动免OA", "工资"])
        self.assertEqual(group["bank_rows"][0]["invoice_relation"]["code"], "oa_exempt")

    def test_legacy_override_exception_still_displays_in_open_section(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-legacy-exception-001",
                    "type": "bank",
                    "case_id": "WEX-LEGACY-001",
                    "exception_case_id": "WEX-LEGACY-001",
                    "debit_amount": "99.00",
                    "credit_amount": "",
                    "counterparty_name": "旧供应商",
                    "invoice_relation": {"code": "bank_missing_oa_fee", "label": "费用类银行流水缺OA", "tone": "danger"},
                    "handled_exception": True,
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["exception_count"], 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_id"], "case:WEX-LEGACY-001")
        self.assertEqual(group["group_type"], "legacy_exception")
        self.assertEqual(group["bank_rows"][0]["invoice_relation"]["code"], "bank_missing_oa_fee")

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

    def test_oa_attachment_source_groups_248_oa_with_three_attachment_invoices_open(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                oa_row(
                    "oa-hurong-248",
                    amount="248.00",
                    counterparty_name="胡瑢",
                    apply_type="日常报销",
                )
            ],
            bank_rows=[],
            invoice_rows=[
                oa_attachment_invoice_row(
                    "iv-hurong-100",
                    derived_from_oa_id="oa-hurong-248",
                    amount="94.34",
                    total_with_tax="100.00",
                    seller_name="昆明差旅服务有限公司",
                ),
                oa_attachment_invoice_row(
                    "iv-hurong-96",
                    derived_from_oa_id="oa-hurong-248",
                    amount="90.57",
                    total_with_tax="96.00",
                    seller_name="云南餐饮服务有限公司",
                ),
                oa_attachment_invoice_row(
                    "iv-hurong-52",
                    derived_from_oa_id="oa-hurong-248",
                    amount="49.06",
                    total_with_tax="52.00",
                    seller_name="昆明票务有限公司",
                ),
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        self.assertEqual(payload["paired"]["groups"], [])
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_type"], "source_linked")
        self.assertEqual(group["match_confidence"], "high")
        self.assertEqual(group["reason"], "oa_attachment_source_relation")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-hurong-248"])
        self.assertEqual(group["bank_rows"], [])
        self.assertCountEqual(
            [row["id"] for row in group["invoice_rows"]],
            ["iv-hurong-100", "iv-hurong-96", "iv-hurong-52"],
        )

    def test_oa_attachment_source_groups_292_oa_with_single_attachment_invoice_open(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                oa_row(
                    "oa-hurong-292",
                    amount="292.00",
                    counterparty_name="",
                    apply_type="日常报销",
                )
            ],
            bank_rows=[],
            invoice_rows=[
                oa_attachment_invoice_row(
                    "iv-hurong-292",
                    derived_from_oa_id="oa-hurong-292",
                    amount="275.47",
                    total_with_tax="292.00",
                    seller_name="云南中油严家山交通服务有限公司",
                )
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_id"], "source:oa_attachment:oa-hurong-292")
        self.assertEqual(group["group_type"], "source_linked")
        self.assertEqual(group["reason"], "oa_attachment_source_relation")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-hurong-292"])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["iv-hurong-292"])

    def test_oa_attachment_source_group_matches_expense_item_to_parent_oa(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                oa_row(
                    "oa-exp-1968",
                    amount="952.21",
                    counterparty_name="刘晓宇",
                    apply_type="日常报销",
                )
            ],
            bank_rows=[],
            invoice_rows=[
                oa_attachment_invoice_row(
                    "oa-att-inv-oa-exp-1968-item-4",
                    derived_from_oa_id="oa-exp-1968:item:4:de54f988bd66",
                    amount="400.00",
                    total_with_tax="400.00",
                    seller_name="中国联合网络通信有限公司昆明市分公司",
                )
            ],
        )

        group = next(group for group in payload["open"]["groups"] if group["reason"] == "oa_attachment_source_relation")
        self.assertEqual(group["group_id"], "source:oa_attachment:oa-exp-1968")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-exp-1968"])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["oa-att-inv-oa-exp-1968-item-4"])

    def test_oa_attachment_source_group_excludes_payment_and_unknown_evidence_from_invoice_rows(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                oa_row(
                    "oa-hurong-2035",
                    amount="248.00",
                    counterparty_name="胡瑢",
                    apply_type="日常报销",
                )
            ],
            bank_rows=[
                {
                    "id": "bank-hurong-2035",
                    "type": "bank",
                    "case_id": None,
                    "debit_amount": "248.00",
                    "credit_amount": "",
                    "counterparty_name": "胡瑢",
                    "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
                }
            ],
            invoice_rows=[
                oa_attachment_invoice_row(
                    "iv-hurong-2035",
                    derived_from_oa_id="oa-hurong-2035",
                    amount="248.00",
                    total_with_tax="248.00",
                    seller_name="云南高速公路联网收费有限公司",
                ),
                oa_attachment_evidence_row(
                    "pay-hurong-2035",
                    source_kind="oa_attachment_payment_receipt",
                    derived_from_oa_id="oa-hurong-2035",
                    amount="248.00",
                ),
                oa_attachment_evidence_row(
                    "unknown-hurong-2035",
                    source_kind="oa_attachment_unknown",
                    derived_from_oa_id="oa-hurong-2035",
                    amount="",
                ),
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        source_group = next(group for group in payload["open"]["groups"] if group["reason"] == "oa_attachment_source_relation")
        self.assertEqual(source_group["group_type"], "source_linked")
        self.assertEqual([row["id"] for row in source_group["oa_rows"]], ["oa-hurong-2035"])
        self.assertEqual([row["id"] for row in source_group["invoice_rows"]], ["iv-hurong-2035"])
        all_invoice_ids = [
            row["id"]
            for section in ("paired", "open")
            for group in payload[section]["groups"]
            for row in group["invoice_rows"]
        ]
        self.assertNotIn("pay-hurong-2035", all_invoice_ids)
        self.assertNotIn("unknown-hurong-2035", all_invoice_ids)

    def test_oa_attachment_invoice_stays_standalone_when_source_oa_is_missing(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[],
            invoice_rows=[
                oa_attachment_invoice_row(
                    "iv-orphan-001",
                    derived_from_oa_id="oa-missing",
                    amount="100.00",
                    total_with_tax="106.00",
                    seller_name="孤立供应商",
                )
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        group = payload["open"]["groups"][0]
        self.assertNotEqual(group["reason"], "oa_attachment_source_relation")
        self.assertEqual(group["oa_rows"], [])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["iv-orphan-001"])

    def test_oa_attachment_invoice_joins_parent_oa_group_after_candidate_grouping(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-parent-952",
                    "type": "oa",
                    "case_id": "CASE-PARENT-952",
                    "apply_type": "日常报销",
                    "amount": "952.00",
                    "counterparty_name": "云南溯源科技",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-parent-952",
                    "type": "bank",
                    "case_id": "CASE-PARENT-952",
                    "trade_time": "2026-03-25 14:22",
                    "debit_amount": "952.00",
                    "credit_amount": "",
                    "counterparty_name": "云南溯源科技",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
            invoice_rows=[
                oa_attachment_invoice_row(
                    "iv-parent-952",
                    derived_from_oa_id="oa-parent-952",
                    amount="215.00",
                    total_with_tax="215.00",
                    seller_name="玉溪卷烟厂",
                )
            ],
        )

        source_group = next(
            group
            for group in payload["open"]["groups"]
            if "iv-parent-952" in [row["id"] for row in group["invoice_rows"]]
        )
        self.assertEqual(source_group["reason"], "oa_attachment_source_relation")
        self.assertEqual([row["id"] for row in source_group["oa_rows"]], ["oa-parent-952"])
        self.assertEqual([row["id"] for row in source_group["bank_rows"]], ["bk-parent-952"])
        self.assertEqual([row["id"] for row in source_group["invoice_rows"]], ["iv-parent-952"])

    def test_oa_attachment_invoice_with_manual_case_id_is_not_taken_by_source_group(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[oa_row("oa-manual-source", amount="100.00", counterparty_name="人工供应商")],
            bank_rows=[],
            invoice_rows=[
                oa_attachment_invoice_row(
                    "iv-manual-owned",
                    derived_from_oa_id="oa-manual-source",
                    amount="100.00",
                    total_with_tax="100.00",
                    seller_name="人工供应商",
                    case_id="CASE-MANUAL-ATTACHMENT",
                )
            ],
        )

        self.assertFalse(
            any(group["reason"] == "oa_attachment_source_relation" for group in payload["open"]["groups"])
        )
        case_group = next(group for group in payload["open"]["groups"] if group["group_id"] == "case:CASE-MANUAL-ATTACHMENT")
        self.assertEqual([row["id"] for row in case_group["invoice_rows"]], ["iv-manual-owned"])
        self.assertIn("oa-manual-source", [row["id"] for row in flatten_groups(payload["open"]["groups"], "oa")])

    def test_ignored_oa_attachment_invoice_does_not_enter_source_group(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[oa_row("oa-ignored-source", amount="248.00", counterparty_name="胡瑢")],
            bank_rows=[],
            invoice_rows=[
                oa_attachment_invoice_row(
                    "iv-ignored-attachment",
                    derived_from_oa_id="oa-ignored-source",
                    amount="94.34",
                    total_with_tax="100.00",
                    seller_name="昆明差旅服务有限公司",
                    ignored=True,
                )
            ],
        )

        self.assertFalse(
            any(group["reason"] == "oa_attachment_source_relation" for group in payload["open"]["groups"])
        )
        self.assertCountEqual(group_ids(payload["open"]["groups"], "oa_rows"), [["oa-ignored-source"], []])
        self.assertCountEqual(group_ids(payload["open"]["groups"], "invoice_rows"), [[], ["iv-ignored-attachment"]])

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

    def test_candidate_case_oa_attachment_invoices_still_join_source_oa_group(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-tian",
                    "type": "oa",
                    "case_id": "candidate:tian",
                    "apply_type": "支付申请",
                    "amount": "196.00",
                    "counterparty_name": "田女士",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-tian",
                    "type": "bank",
                    "case_id": "candidate:tian",
                    "trade_time": "2026-03-25 14:22",
                    "debit_amount": "196.00",
                    "credit_amount": "",
                    "counterparty_name": "田女士",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-tian-70",
                    "type": "invoice",
                    "case_id": "candidate:tian-invoice-70",
                    "source_kind": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-tian",
                    "amount": "66.04",
                    "total_with_tax": "70.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "田女士",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
                {
                    "id": "iv-tian-126",
                    "type": "invoice",
                    "case_id": "candidate:tian-invoice-126",
                    "source_kind": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-tian",
                    "amount": "124.75",
                    "total_with_tax": "126.00",
                    "issue_date": "2026-03-26",
                    "seller_name": "田女士",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 2)
        source_group = next(
            group
            for group in payload["open"]["groups"]
            if group["reason"] == "oa_attachment_source_relation"
        )
        self.assertEqual(source_group["group_type"], "source_linked")
        self.assertEqual(source_group["match_confidence"], "high")
        self.assertEqual([row["id"] for row in source_group["oa_rows"]], ["oa-tian"])
        self.assertEqual(source_group["bank_rows"], [])
        self.assertCountEqual(
            [row["id"] for row in source_group["invoice_rows"]],
            ["iv-tian-70", "iv-tian-126"],
        )
        bank_group = next(group for group in payload["open"]["groups"] if group["bank_rows"])
        self.assertEqual([row["id"] for row in bank_group["bank_rows"]], ["bk-tian"])
        self.assertEqual(bank_group["oa_rows"], [])
        self.assertEqual(bank_group["invoice_rows"], [])

    def test_does_not_attach_non_candidate_oa_attachment_invoice_to_candidate_source_group(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-02",
            oa_rows=[
                {
                    "id": "oa-zhou-offset",
                    "type": "oa",
                    "case_id": "candidate:offset-800",
                    "apply_type": "日常报销",
                    "amount": "800.00",
                    "counterparty_name": "云南溯源科技",
                    "oa_bank_relation": {"code": "oa_invoice_offset_auto_match", "label": "冲", "tone": "success"},
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "iv-offset-selected",
                    "type": "invoice",
                    "case_id": "candidate:offset-800",
                    "source_kind": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-zhou-offset",
                    "amount": "800.00",
                    "total_with_tax": "800.00",
                    "issue_date": "2026-02-09",
                    "seller_name": "云南溯源科技",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {
                        "code": "oa_invoice_offset_auto_match",
                        "label": "冲",
                        "tone": "success",
                    },
                },
                {
                    "id": "iv-offset-extra",
                    "type": "invoice",
                    "case_id": None,
                    "source_kind": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-zhou-offset",
                    "amount": "30.00",
                    "total_with_tax": "30.00",
                    "issue_date": "2026-02-09",
                    "seller_name": "云南溯源科技",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                },
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        paired_group = payload["paired"]["groups"][0]
        self.assertEqual([row["id"] for row in paired_group["oa_rows"]], ["oa-zhou-offset"])
        self.assertCountEqual(
            [row["id"] for row in paired_group["invoice_rows"]],
            ["iv-offset-selected", "iv-offset-extra"],
        )
        self.assertNotIn(
            "iv-offset-extra",
            [row["id"] for row in flatten_groups(payload["open"]["groups"], "invoice")],
        )

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

    def test_splits_cross_counterparty_bank_invoice_candidate_case_group(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-jiangyin-2000",
                    "type": "bank",
                    "case_id": "candidate:dirty-cross-counterparty",
                    "debit_amount": "2000.00",
                    "credit_amount": "",
                    "counterparty_name": "江阴服务有限公司",
                    "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-zijin-2000",
                    "type": "invoice",
                    "case_id": "candidate:dirty-cross-counterparty",
                    "amount": "2000.00",
                    "issue_date": "2026-05-06",
                    "seller_name": "紫金科技有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 2)
        self.assertCountEqual(group_ids(payload["open"]["groups"], "bank_rows"), [["bk-jiangyin-2000"], []])
        self.assertCountEqual(group_ids(payload["open"]["groups"], "invoice_rows"), [[], ["iv-zijin-2000"]])

    def test_keeps_same_counterparty_bank_invoice_candidate_case_group_together(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-same-counterparty-2000",
                    "type": "bank",
                    "case_id": "candidate:same-counterparty",
                    "debit_amount": "2000.00",
                    "credit_amount": "",
                    "counterparty_name": "同主体服务有限公司",
                    "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-same-counterparty-2000",
                    "type": "invoice",
                    "case_id": "candidate:same-counterparty",
                    "amount": "2000.00",
                    "issue_date": "2026-05-06",
                    "seller_name": "同主体服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_type"], "candidate")
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-same-counterparty-2000"])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["iv-same-counterparty-2000"])

    def test_splits_unmatched_rows_out_of_candidate_case_without_losing_exact_pair(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[
                {
                    "id": "oa-fuel-2000",
                    "type": "oa",
                    "case_id": "candidate:mixed-context",
                    "apply_type": "支付申请",
                    "amount": "2000.00",
                    "pay_receive_time": "2026-05-06",
                    "counterparty_name": "中国石油云南昆明销售分公司",
                    "oa_bank_relation": {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-fuel-2000",
                    "type": "bank",
                    "case_id": "candidate:mixed-context",
                    "debit_amount": "2000.00",
                    "credit_amount": "",
                    "trade_time": "2026-05-06 09:30",
                    "counterparty_name": "中国石油云南昆明销售分公司",
                    "invoice_relation": {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-express-32",
                    "type": "invoice",
                    "case_id": "candidate:mixed-context",
                    "amount": "32.90",
                    "total_with_tax": "32.90",
                    "issue_date": "2026-05-06",
                    "seller_name": "云南顺丰速运有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 2)
        self.assertCountEqual(group_ids(payload["open"]["groups"], "oa_rows"), [["oa-fuel-2000"], []])
        self.assertCountEqual(group_ids(payload["open"]["groups"], "bank_rows"), [["bk-fuel-2000"], []])
        self.assertCountEqual(group_ids(payload["open"]["groups"], "invoice_rows"), [[], ["iv-express-32"]])

    def test_does_not_group_open_rows_by_fuzzy_amount_bucket(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-fuzzy-2040",
                    "type": "bank",
                    "case_id": None,
                    "debit_amount": "2040.00",
                    "credit_amount": "",
                    "trade_time": "2026-05-06 09:30",
                    "counterparty_name": "同主体服务有限公司",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
            invoice_rows=[
                {
                    "id": "iv-fuzzy-2000",
                    "type": "invoice",
                    "case_id": None,
                    "amount": "2000.00",
                    "total_with_tax": "2000.00",
                    "issue_date": "2026-05-06",
                    "seller_name": "同主体服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                }
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 2)
        self.assertCountEqual(group_ids(payload["open"]["groups"], "bank_rows"), [["bk-fuzzy-2040"], []])
        self.assertCountEqual(group_ids(payload["open"]["groups"], "invoice_rows"), [[], ["iv-fuzzy-2000"]])

    def test_keeps_oa_bank_candidate_group_when_bank_counterparty_is_payee_prefix(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-02",
            oa_rows=[
                {
                    "id": "oa-lodging-1090",
                    "type": "oa",
                    "case_id": "candidate:lodging-agent",
                    "apply_type": "支付申请",
                    "amount": "1090.00",
                    "counterparty_name": "安雨超（代收红塔区友余宾馆住宿费）",
                    "pay_receive_time": "2026-02-02",
                    "oa_bank_relation": {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"},
                }
            ],
            bank_rows=[
                {
                    "id": "bk-lodging-1090",
                    "type": "bank",
                    "case_id": "candidate:lodging-agent",
                    "debit_amount": "1090.00",
                    "credit_amount": "",
                    "counterparty_name": "安雨超",
                    "trade_time": "2026-02-04 15:10:44",
                    "invoice_relation": {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"},
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_type"], "candidate")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-lodging-1090"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bk-lodging-1090"])

    def test_keeps_same_counterparty_oa_multi_invoice_sum_candidate_case_group_together(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-05",
            oa_rows=[
                {
                    "id": "oa-meeting-300",
                    "type": "oa",
                    "case_id": "candidate:oa-invoice-sum",
                    "apply_type": "付款申请",
                    "amount": "300.00",
                    "counterparty_name": "会务服务有限公司",
                    "oa_bank_relation": {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"},
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "iv-meeting-120",
                    "type": "invoice",
                    "case_id": "candidate:oa-invoice-sum",
                    "amount": "120.00",
                    "total_with_tax": "120.00",
                    "seller_name": "会务服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"},
                },
                {
                    "id": "iv-meeting-180",
                    "type": "invoice",
                    "case_id": "candidate:oa-invoice-sum",
                    "amount": "180.00",
                    "total_with_tax": "180.00",
                    "seller_name": "会务服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"},
                },
            ],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["open_count"], 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_type"], "candidate")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-meeting-300"])
        self.assertCountEqual(
            [row["id"] for row in group["invoice_rows"]],
            ["iv-meeting-120", "iv-meeting-180"],
        )

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

    def test_keeps_no_oa_bank_batch_relation_rows_in_paired_case_group(self) -> None:
        service = WorkbenchCandidateGroupingService()
        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bk-transfer-001",
                    "type": "bank",
                    "case_id": "no_oa_batch_internal_001",
                    "relation_mode": "no_oa_bank_batch",
                    "trade_time": "2026-03-19 11:15:00",
                    "debit_amount": "",
                    "credit_amount": "13000.00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "invoice_relation": {"code": "no_oa_bank_batch", "label": "已匹配：内部往来款", "tone": "success"},
                    "display_tags": ["免OA", "内部往来款"],
                    "available_actions": ["detail"],
                },
                {
                    "id": "bk-transfer-002",
                    "type": "bank",
                    "case_id": "no_oa_batch_internal_001",
                    "relation_mode": "no_oa_bank_batch",
                    "trade_time": "2026-03-19 11:16:00",
                    "debit_amount": "13000.00",
                    "credit_amount": "",
                    "counterparty_name": "云南溯源科技有限公司",
                    "invoice_relation": {"code": "no_oa_bank_batch", "label": "已匹配：内部往来款", "tone": "success"},
                    "display_tags": ["免OA", "内部往来款"],
                    "available_actions": ["detail"],
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["open_count"], 0)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(group["display_tags"], ["免OA", "内部往来款"])
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


def no_oa_bank_row(
    row_id: str,
    *,
    batch_id: str,
    debit_amount: str,
    remark: str,
    batch_version: int | None = None,
    case_id: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": "no_oa_bank_batch",
        "source_batch_id": batch_id,
        "batch_type": "fee",
        "batch_label": "手续费",
        "withdrawable": True,
        "relation_mode": "no_oa_bank_batch",
        "display_tags": ["免OA", "手续费"],
    }
    if batch_version is not None:
        metadata["batch_version"] = batch_version
    return {
        "id": row_id,
        "type": "bank",
        "case_id": case_id or batch_id,
        "relation_mode": "no_oa_bank_batch",
        "trade_time": "2026-05-03 10:00:00",
        "debit_amount": debit_amount,
        "credit_amount": "",
        "counterparty_name": "建设银行",
        "payment_account_label": "建设银行 8106",
        "remark": remark,
        "detail_fields": {"企业流水号": f"SERIAL-{row_id}"},
        "bank_text_fields": {"备注": remark},
        "invoice_relation": {"code": "no_oa_bank_batch", "label": "已匹配：手续费", "tone": "success"},
        "tags": ["免OA", "手续费"],
        "display_tags": ["免OA", "手续费"],
        "special_metadata": metadata,
    }


def oa_row(
    row_id: str,
    *,
    amount: str,
    counterparty_name: str,
    apply_type: str = "支付申请",
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "case_id": None,
        "apply_type": apply_type,
        "amount": amount,
        "counterparty_name": counterparty_name,
        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
    }


def oa_attachment_invoice_row(
    row_id: str,
    *,
    derived_from_oa_id: str,
    amount: str,
    total_with_tax: str,
    seller_name: str,
    case_id: str | None = None,
    ignored: bool = False,
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": row_id,
        "type": "invoice",
        "case_id": case_id,
        "source_kind": "oa_attachment_invoice",
        "derived_from_oa_id": derived_from_oa_id,
        "amount": amount,
        "total_with_tax": total_with_tax,
        "issue_date": "2026-03-24",
        "seller_name": seller_name,
        "buyer_name": "云南溯源科技有限公司",
        "invoice_type": "进项发票",
        "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
    }
    if ignored:
        row["ignored"] = True
    return row


def oa_attachment_evidence_row(
    row_id: str,
    *,
    source_kind: str,
    derived_from_oa_id: str,
    amount: str,
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "invoice",
        "case_id": None,
        "source_kind": source_kind,
        "derived_from_oa_id": derived_from_oa_id,
        "amount": amount,
        "total_with_tax": amount,
        "issue_date": "2026-03-24",
        "seller_name": "",
        "buyer_name": "",
        "invoice_type": "附件凭证",
        "invoice_bank_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
    }


if __name__ == "__main__":
    unittest.main()
