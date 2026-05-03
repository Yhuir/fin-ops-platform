import unittest

from fin_ops_platform.services.workbench_candidate_grouping import WorkbenchCandidateGroupingService


class WorkbenchCandidateGroupingTests(unittest.TestCase):
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


def group_ids(groups: list[dict[str, object]], key: str) -> list[list[str]]:
    return [[row["id"] for row in group[key]] for group in groups]


if __name__ == "__main__":
    unittest.main()
