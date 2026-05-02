import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService


class MutableOAAdapter:
    def __init__(self, seed_data: dict[str, list[OAApplicationRecord]]) -> None:
        self._seed_data = seed_data

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        return list(self._seed_data.get(month, []))


class AttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-attach-202603-001"
        self.month = "2026-03"
        self.section = "open"
        self.case_id = None
        self.applicant = "刘际涛"
        self.project_name = "玉烟维护项目"
        self.apply_type = "日常报销"
        self.amount = "58,000.00"
        self.counterparty_name = "智能工厂设备商"
        self.reason = "设备尾款报销"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "设备货款及材料费"
        self.expense_content = "设备尾款报销"
        self.detail_fields = {
            "OA单号": "OA-ATT-001",
            "申请日期": "2026-03-28",
            "明细行号": "0",
        }
        self.attachment_invoices = [
            {
                "invoice_code": "053002200111",
                "invoice_no": "40512344",
                "seller_tax_no": "91530100678728169X",
                "seller_name": "智能工厂设备商",
                "buyer_tax_no": "915300007194052520",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-28",
                "amount": "58,000.00",
                "tax_rate": "13%",
                "tax_amount": "6,673.45",
                "total_with_tax": "64,673.45",
                "invoice_type": "进项发票",
                "attachment_name": "设备发票.pdf",
                "invoice_kind": "增值税电子专用发票",
            }
        ]


class AttachmentAwareOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [AttachmentRecord()]


class UnparsedAttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-unparsed-202603-001"
        self.month = "2026-03"
        self.section = "open"
        self.case_id = None
        self.applicant = "胡瑢"
        self.project_name = "玉烟维护项目"
        self.apply_type = "日常报销"
        self.amount = "54.00"
        self.counterparty_name = ""
        self.reason = "高速过路费"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "车辆使用费"
        self.expense_content = "高速过路费"
        self.detail_fields = {
            "OA单号": "OA-UNPARSED-001",
            "申请日期": "2026-03-28",
            "明细行号": "0",
        }
        self.attachment_invoices = []
        self.attachment_file_count = 2


class UnparsedAttachmentOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [UnparsedAttachmentRecord()]


class BulkOAAdapter:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self._records = records
        self.bulk_call_count = 0
        self.month_call_count = 0

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        self.bulk_call_count += 1
        return list(self._records)

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        self.month_call_count += 1
        raise AssertionError("bulk adapter should not fall back to per-month reads")


class WorkbenchQueryServiceTests(unittest.TestCase):
    def test_open_invoice_rows_include_ignore_action(self) -> None:
        service = WorkbenchQueryService()

        payload = service.get_workbench("2026-03")
        invoice_row = payload["open"]["invoice"][0]

        self.assertIn("ignore", invoice_row["available_actions"])

    def test_refreshes_oa_rows_for_month_and_preserves_manual_relation_state(self) -> None:
        adapter = MutableOAAdapter(
            {
                "2026-03": [
                    OAApplicationRecord(
                        id="oa-real-001",
                        month="2026-03",
                        section="open",
                        case_id=None,
                        applicant="刘际涛",
                        project_name="云南溯源科技",
                        apply_type="支付申请",
                        amount="199",
                        counterparty_name="中国电信股份有限公司昆明分公司",
                        reason="托收电话费及宽带",
                        relation_code="pending_match",
                        relation_label="待找流水与发票",
                        relation_tone="warn",
                    )
                ]
            }
        )
        service = WorkbenchQueryService(oa_adapter=adapter)

        first_payload = service.get_workbench("2026-03")
        oa_row = first_payload["open"]["oa"][0]
        self.assertEqual(oa_row["applicant"], "刘际涛")
        self.assertEqual(oa_row["amount"], "199")

        row_record = service.get_row_record("oa-real-001")
        row_record["case_id"] = "CASE-MANUAL-001"
        row_record["oa_bank_relation"] = {"code": "fully_linked", "label": "完全关联", "tone": "success"}
        row_record["_section"] = "paired"
        row_record["available_actions"] = service.available_actions("oa", "paired")

        adapter._seed_data["2026-03"] = [
            OAApplicationRecord(
                id="oa-real-001",
                month="2026-03",
                section="open",
                case_id=None,
                applicant="刘际涛-更新",
                project_name="云南溯源科技",
                apply_type="支付申请",
                amount="299",
                counterparty_name="中国电信股份有限公司昆明分公司",
                reason="托收电话费及宽带-更新",
                relation_code="pending_match",
                relation_label="待找流水与发票",
                relation_tone="warn",
            )
        ]

        refreshed_payload = service.get_workbench("2026-03")
        refreshed_row = refreshed_payload["paired"]["oa"][0]
        self.assertEqual(refreshed_row["applicant"], "刘际涛-更新")
        self.assertEqual(refreshed_row["amount"], "299")
        self.assertEqual(refreshed_row["case_id"], "CASE-MANUAL-001")
        self.assertEqual(refreshed_row["oa_bank_relation"]["code"], "fully_linked")

    def test_attachment_invoices_become_invoice_rows_and_oa_detail_contains_summary(self) -> None:
        service = WorkbenchQueryService(oa_adapter=AttachmentAwareOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_row = payload["open"]["oa"][0]
        attachment_invoice_rows = [
            row
            for row in payload["open"]["invoice"]
            if row.get("detail_fields", {}).get("来源OA单号") == "OA-ATT-001"
        ]
        self.assertEqual(len(attachment_invoice_rows), 1)
        invoice_row = attachment_invoice_rows[0]
        self.assertIsNotNone(oa_row["case_id"])
        self.assertEqual(invoice_row["case_id"], oa_row["case_id"])
        self.assertEqual(invoice_row["invoice_type"], "进项发票")
        self.assertEqual(invoice_row["seller_name"], "智能工厂设备商")
        self.assertEqual(invoice_row["detail_fields"]["附件文件名"], "设备发票.pdf")

        oa_detail = service.get_row_detail(oa_row["id"])
        invoice_detail = service.get_row_detail(invoice_row["id"])
        self.assertEqual(oa_detail["detail_fields"]["附件发票数量"], "1")
        self.assertIn("40512344", oa_detail["detail_fields"]["附件发票摘要"])
        self.assertEqual(invoice_detail["detail_fields"]["来源OA单号"], "OA-ATT-001")
        self.assertEqual(invoice_detail["detail_fields"]["发票号码"], "40512344")

    def test_unparsed_attachment_oa_row_gets_unparsed_invoice_tag(self) -> None:
        service = WorkbenchQueryService(oa_adapter=UnparsedAttachmentOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_row = payload["open"]["oa"][0]
        self.assertIn("未解析发票", oa_row["tags"])
        self.assertEqual(oa_row["detail_fields"]["附件发票数量"], "0")
        self.assertEqual(oa_row["detail_fields"]["附件发票识别情况"], "已解析 0 / 2")

    def test_all_workbench_prefers_bulk_oa_read_when_adapter_supports_it(self) -> None:
        adapter = BulkOAAdapter(
            [
                OAApplicationRecord(
                    id="oa-bulk-202603-001",
                    month="2026-03",
                    section="open",
                    case_id=None,
                    applicant="刘际涛",
                    project_name="云南溯源科技",
                    apply_type="支付申请",
                    amount="199",
                    counterparty_name="中国电信股份有限公司昆明分公司",
                    reason="托收电话费及宽带",
                    relation_code="pending_match",
                    relation_label="待找流水与发票",
                    relation_tone="warn",
                ),
                OAApplicationRecord(
                    id="oa-bulk-202604-001",
                    month="2026-04",
                    section="open",
                    case_id=None,
                    applicant="樊祖芳",
                    project_name="大理卷烟厂余热综合利用项目",
                    apply_type="支付申请",
                    amount="88050",
                    counterparty_name="云南辰飞机电工程有限公司",
                    reason="空气源热泵预付款",
                    relation_code="pending_match",
                    relation_label="待找流水与发票",
                    relation_tone="warn",
                ),
            ]
        )
        service = WorkbenchQueryService(oa_adapter=adapter)

        payload = service.get_workbench("all")

        self.assertEqual(payload["summary"]["oa_count"], 2)
        self.assertEqual(adapter.bulk_call_count, 1)
        self.assertEqual(adapter.month_call_count, 0)

    def test_attachment_invoice_issue_month_rows_reuse_bulk_oa_sync_result(self) -> None:
        adapter = BulkOAAdapter(
            [
                OAApplicationRecord(
                    id="oa-bulk-202602-001",
                    month="2026-02",
                    section="open",
                    case_id=None,
                    applicant="周洁莹",
                    project_name="云南溯源科技",
                    apply_type="日常报销",
                    amount="200.00",
                    counterparty_name="",
                    reason="汽油费",
                    relation_code="pending_match",
                    relation_label="待找流水与发票",
                    relation_tone="warn",
                    attachment_invoices=[
                        {
                            "invoice_no": "15312761",
                            "invoice_code": "053002200111",
                            "seller_name": "云南中油严家山交通服务有限公司",
                            "seller_tax_no": "91530000709708479E",
                            "buyer_name": "云南溯源科技有限公司",
                            "buyer_tax_no": "530111199504054424",
                            "issue_date": "2026-03-24",
                            "tax_rate": "13%",
                            "tax_amount": "23.01",
                            "total_with_tax": "200.00",
                            "amount": "176.99",
                            "invoice_type": "进项发票",
                            "attachment_name": "20240424-汽油费-200.jpg",
                        }
                    ],
                )
            ]
        )
        service = WorkbenchQueryService(oa_adapter=adapter)

        first_rows = service.list_attachment_invoice_rows_by_issue_month("2026-03")
        second_rows = service.list_attachment_invoice_rows_by_issue_month("2026-03")

        self.assertEqual(len(first_rows), 1)
        self.assertEqual(first_rows[0]["detail_fields"]["发票号码"], "15312761")
        self.assertEqual(first_rows[0]["amount"], "176.99")
        self.assertEqual(first_rows[0]["total_with_tax"], "200.00")
        self.assertEqual(len(second_rows), 1)
        self.assertEqual(adapter.bulk_call_count, 1)
        self.assertEqual(adapter.month_call_count, 0)
        self.assertEqual(len(second_rows), 1)
        self.assertEqual(adapter.bulk_call_count, 1)
        self.assertEqual(adapter.month_call_count, 0)


if __name__ == "__main__":
    unittest.main()
