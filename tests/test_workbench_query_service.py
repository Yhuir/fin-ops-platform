import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService


class MutableOAAdapter:
    def __init__(self, seed_data: dict[str, list[OAApplicationRecord]]) -> None:
        self._seed_data = seed_data

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        return list(self._seed_data.get(month, []))


class RowIdLookupOAAdapter:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self._records_by_id = {record.id: record for record in records}
        self.list_all_called = False

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        return [record for record in self._records_by_id.values() if record.month == month]

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        self.list_all_called = True
        raise AssertionError("row-id lookup should not fall back to full OA sync")

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        return [self._records_by_id[row_id] for row_id in row_ids if row_id in self._records_by_id]


class AttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-attach-202603-001"
        self.month = "2026-03"
        self.section = "unpaired"
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


class AggregatedAttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-exp-exp-agg-001"
        self.month = "2026-03"
        self.section = "unpaired"
        self.case_id = None
        self.applicant = "刘际涛"
        self.project_name = "玉烟维护项目；云南溯源科技"
        self.apply_type = "日常报销"
        self.amount = "1549.00"
        self.counterparty_name = ""
        self.reason = "设备材料；邮寄费用"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "材料费；运费/邮费/杂费"
        self.expense_content = "设备材料；邮寄费用"
        self.detail_fields = {
            "OA单号": "OA-AGG-001",
            "申请日期": "2026-03-28",
        }
        self.expense_items = [
            {
                "row_index": "0",
                "project_name": "玉烟维护项目",
                "amount": "1000.00",
                "expense_type": "材料费",
                "expense_content": "设备材料",
                "reimbursement_date": "2026-03-27",
            },
            {
                "row_index": "1",
                "project_name": "云南溯源科技",
                "amount": "500.00",
                "expense_type": "运费/邮费/杂费",
                "expense_content": "邮寄费用",
                "reimbursement_date": "2026-03-28",
            },
        ]
        self.amount_source = "header"
        self.amount_mismatch = {
            "header_amount": "1549.00",
            "detail_sum": "1500.00",
            "difference": "49.00",
        }
        self.attachment_invoices = [
            {
                "invoice_no": "40512344",
                "seller_name": "智能工厂设备商",
                "seller_tax_no": "91530100678728169X",
                "buyer_name": "云南溯源科技有限公司",
                "buyer_tax_no": "915300007194052520",
                "issue_date": "2026-03-27",
                "amount": "1000.00",
                "total_with_tax": "1000.00",
                "invoice_type": "进项发票",
                "attachment_name": "设备发票.pdf",
                "source_expense_row_index": "0",
            },
            {
                "invoice_no": "40512345",
                "seller_name": "顺丰速运有限公司",
                "seller_tax_no": "9144030071526726XG",
                "buyer_name": "云南溯源科技有限公司",
                "buyer_tax_no": "915300007194052520",
                "issue_date": "2026-03-28",
                "amount": "500.00",
                "total_with_tax": "500.00",
                "invoice_type": "进项发票",
                "attachment_name": "邮寄发票.pdf",
            },
        ]
        self.attachment_file_count = 2


class MultiProjectDisplayRecord:
    def __init__(self) -> None:
        self.id = "oa-exp-display-001"
        self.month = "2026-03"
        self.section = "unpaired"
        self.case_id = None
        self.applicant = "刘际涛"
        self.project_name = "玉烟维护项目；云南溯源科技"
        self.project_name_display = "多个项目"
        self.project_names = ["玉烟维护项目", "云南溯源科技"]
        self.apply_type = "日常报销"
        self.amount = "1500.00"
        self.counterparty_name = ""
        self.reason = "设备材料；邮寄费用"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "材料费；运费/邮费/杂费"
        self.expense_content = "设备材料；邮寄费用"
        self.detail_fields = {
            "OA单号": "OA-DISPLAY-001",
            "申请日期": "2026-03-28",
            "项目名称汇总": "玉烟维护项目；云南溯源科技",
        }
        self.expense_items = [
            {
                "row_index": "0",
                "project_name": "玉烟维护项目",
                "amount": "1000.00",
                "expense_type": "材料费",
                "expense_content": "设备材料",
                "reimbursement_date": "2026-03-27",
            },
            {
                "row_index": "1",
                "project_name": "云南溯源科技",
                "amount": "500.00",
                "expense_type": "运费/邮费/杂费",
                "expense_content": "邮寄费用",
                "reimbursement_date": "2026-03-28",
            },
        ]


class MultiProjectDisplayOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [MultiProjectDisplayRecord()]


class AggregatedAttachmentOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [AggregatedAttachmentRecord()]


class SourceBoundAttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-exp-hurong-248"
        self.month = "2026-03"
        self.section = "unpaired"
        self.case_id = None
        self.applicant = "胡瑢"
        self.project_name = "2024-2026年度红塔集团工作证管理系统维护项目"
        self.apply_type = "日常报销"
        self.amount = "248.00"
        self.counterparty_name = ""
        self.reason = "工作证管理系统维护项目报销"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "项目费用"
        self.expense_content = "工作证维护费用"
        self.detail_fields = {
            "OA单号": "OA-HR-248",
            "申请日期": "2026-03-04",
        }
        self.expense_items = [
            {
                "row_index": "0",
                "expense_item_id": "oa-exp-hurong-248:item:0:maint",
                "amount": "196.00",
                "expense_content": "付款项1",
            },
            {
                "row_index": "1",
                "expense_item_id": "oa-exp-hurong-248:item:1:service",
                "amount": "52.00",
                "expense_content": "付款项2",
            },
        ]
        self.attachment_invoices = [
            {
                "invoice_no": "24800001",
                "seller_name": "红塔供应商A",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-04",
                "amount": "100.00",
                "total_with_tax": "100.00",
                "invoice_type": "进项发票",
                "source_expense_row_index": "0",
                "source_expense_item_id": "oa-exp-hurong-248:item:0:maint",
                "source_attachment_key": "oa-exp-hurong-248:item:0:att:a",
                "source_attachment_name": "付款项1-发票A.pdf",
                "attachment_name": "旧展示名A.pdf",
            },
            {
                "invoice_no": "24800002",
                "seller_name": "红塔供应商B",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-04",
                "amount": "96.00",
                "total_with_tax": "96.00",
                "invoice_type": "进项发票",
                "source_expense_row_index": "0",
                "source_expense_item_id": "oa-exp-hurong-248:item:0:maint",
                "source_attachment_key": "oa-exp-hurong-248:item:0:att:b",
                "source_attachment_name": "付款项1-发票B.pdf",
            },
            {
                "invoice_no": "24800003",
                "seller_name": "红塔供应商C",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-04",
                "amount": "52.00",
                "total_with_tax": "52.00",
                "invoice_type": "进项发票",
                "source_expense_row_index": "1",
                "source_expense_item_id": "oa-exp-hurong-248:item:1:service",
                "source_attachment_key": "oa-exp-hurong-248:item:1:att:c",
                "source_attachment_name": "付款项2-发票C.pdf",
                "attachment_name": "付款项2-发票C.pdf",
            },
        ]
        self.attachment_file_count = 3


class SingleSourceAttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-exp-hurong-292"
        self.month = "2026-03"
        self.section = "unpaired"
        self.case_id = None
        self.applicant = "胡瑢"
        self.project_name = "红云红河烟草能源管理运维项目"
        self.apply_type = "日常报销"
        self.amount = "292.00"
        self.counterparty_name = ""
        self.reason = "能源管理运维项目报销"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "项目费用"
        self.expense_content = "能源管理运维费用"
        self.detail_fields = {
            "OA单号": "OA-HR-292",
            "申请日期": "2026-03-24",
            "明细行号": "0",
        }
        source_invoice = {
            "invoice_no": "29200001",
            "seller_name": "能源运维供应商",
            "buyer_name": "云南溯源科技有限公司",
            "issue_date": "2026-03-24",
            "amount": "292.00",
            "total_with_tax": "292.00",
            "invoice_type": "进项发票",
            "source_expense_row_index": "0",
            "source_expense_item_id": "oa-exp-hurong-292:item:0:energy",
            "source_attachment_key": "oa-exp-hurong-292:item:0:att:only",
            "source_attachment_name": "能源管理运维发票.pdf",
            "attachment_name": "能源管理运维发票.pdf",
        }
        self.expense_items = [
            {
                "row_index": "0",
                "expense_item_id": "oa-exp-hurong-292:item:0:energy",
                "amount": "292.00",
                "attachment_invoices": [dict(source_invoice)],
            }
        ]
        self.attachment_invoices = [source_invoice]
        self.attachment_file_count = 1


class SourceBoundAttachmentOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [SourceBoundAttachmentRecord(), SingleSourceAttachmentRecord()]


class EvidenceAttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-evidence-2035"
        self.month = "2026-03"
        self.section = "unpaired"
        self.case_id = None
        self.applicant = "胡瑢"
        self.project_name = "工作证管理系统维护项目"
        self.apply_type = "日常报销"
        self.amount = "248.00"
        self.counterparty_name = ""
        self.reason = "OA 2035 附件凭证"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "项目费用"
        self.expense_content = "过路费；加油费"
        self.detail_fields = {
            "OA单号": "OA-2035",
            "申请日期": "2026-03-04",
        }
        self.attachment_evidences = [
            {
                "evidence_id": "ev-invoice-25",
                "evidence_type": "machine_invoice",
                "document_kind": "云南通用机打发票",
                "invoice_no": "53000125",
                "seller_name": "云南高速公路联网收费有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-04",
                "amount": "25.00",
                "total_with_tax": "25.00",
                "tax_amount": "0.00",
                "source_expense_row_index": "0",
                "source_expense_item_id": "oa-evidence-2035:item:0:toll",
                "source_attachment_key": "oa-evidence-2035:item:0:att:invoice",
                "source_attachment_name": "过路费发票合图.jpg",
            },
            {
                "evidence_id": "ev-payment-25",
                "evidence_type": "payment_receipt",
                "document_kind": "微信支付凭证",
                "merchant_name": "云南高速公路联网收费有限公司",
                "paid_at": "2026-03-04 09:20:00",
                "transaction_no": "wx-toll-25",
                "payment_method": "微信",
                "amount": "25.00",
                "source_expense_row_index": "0",
                "source_expense_item_id": "oa-evidence-2035:item:0:toll",
                "source_attachment_key": "oa-evidence-2035:item:0:att:payment-25",
                "source_attachment_name": "微信付款凭证25.jpg",
            },
            {
                "evidence_id": "ev-unknown",
                "evidence_type": "unknown",
                "document_kind": "未知附件",
                "amount": "",
                "source_expense_row_index": "1",
                "source_expense_item_id": "oa-evidence-2035:item:1:fuel",
                "source_attachment_key": "oa-evidence-2035:item:1:att:unknown",
                "source_attachment_name": "无法识别附件.png",
            },
        ]
        self.attachment_invoices = []
        self.attachment_file_count = 3


class EvidenceAttachmentOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [EvidenceAttachmentRecord()]


class AttachmentAwareOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [AttachmentRecord()]


class UnparsedAttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-unparsed-202603-001"
        self.month = "2026-03"
        self.section = "unpaired"
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


class EtcBatchRecord:
    def __init__(self) -> None:
        self.id = "oa-etc-202605-001"
        self.month = "2026-05"
        self.section = "unpaired"
        self.case_id = None
        self.applicant = "刘际涛"
        self.project_name = "云南溯源科技"
        self.apply_type = "支付申请"
        self.amount = "53.84"
        self.counterparty_name = "云南高速通行费"
        self.reason = "ETC批量提交\netc_batch_id=etc_20260503_001"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "车辆使用费"
        self.expense_content = self.reason
        self.detail_fields = {"OA单号": "OA-ETC-001", "申请日期": "2026-05-03"}
        self.attachment_invoices = []
        self.attachment_file_count = 0
        self.source = "etc_batch"
        self.etc_batch_id = "etc_20260503_001"
        self.tags = ["ETC批量提交"]


class EtcBatchOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-05":
            return []
        return [EtcBatchRecord()]


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
    def test_unpaired_invoice_rows_include_ignore_action(self) -> None:
        service = WorkbenchQueryService()

        payload = service.get_workbench("2026-03")
        invoice_row = payload["unpaired"]["invoice"][0]

        self.assertIn("ignore", invoice_row["available_actions"])

    def test_get_oa_row_record_uses_row_id_lookup_without_full_sync_for_all_hint(self) -> None:
        adapter = RowIdLookupOAAdapter(
            [
                OAApplicationRecord(
                    id="oa-real-lookup-001",
                    month="2026-03",
                    section="unpaired",
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
        )
        service = WorkbenchQueryService(oa_adapter=adapter, seed_demo_rows=False)

        row_record = service.get_row_record("oa-real-lookup-001", month_hint="all")

        self.assertEqual(row_record["applicant"], "刘际涛")
        self.assertFalse(adapter.list_all_called)

    def test_refreshes_oa_rows_for_month_and_preserves_manual_relation_state(self) -> None:
        adapter = MutableOAAdapter(
            {
                "2026-03": [
                    OAApplicationRecord(
                        id="oa-real-001",
                        month="2026-03",
                        section="unpaired",
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
        oa_row = first_payload["unpaired"]["oa"][0]
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
                section="unpaired",
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

    def test_attachment_invoices_publish_invoice_rows_and_stay_on_oa_detail(self) -> None:
        service = WorkbenchQueryService(oa_adapter=AttachmentAwareOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_row = payload["unpaired"]["oa"][0]
        attachment_invoice_rows = [
            row
            for row in payload["unpaired"]["invoice"]
            if row.get("detail_fields", {}).get("来源OA单号") == "OA-ATT-001"
        ]
        self.assertEqual(len(attachment_invoice_rows), 1)
        self.assertEqual(attachment_invoice_rows[0]["source_kind"], "oa_attachment_invoice")
        self.assertEqual(attachment_invoice_rows[0]["invoice_no"], "40512344")
        self.assertEqual(attachment_invoice_rows[0]["source_links"][0]["derived_from_oa_id"], oa_row["id"])
        self.assertIsNone(oa_row["case_id"])

        oa_detail = service.get_row_detail(oa_row["id"])
        self.assertEqual(oa_detail["detail_fields"]["附件发票数量"], "1")
        self.assertIn("40512344", oa_detail["detail_fields"]["附件发票摘要"])

    def test_aggregated_expense_claim_row_exposes_detail_fields_tags_and_multiple_attachment_invoices(self) -> None:
        service = WorkbenchQueryService(oa_adapter=AggregatedAttachmentOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_rows = [row for row in payload["unpaired"]["oa"] if row["id"] == "oa-exp-exp-agg-001"]
        self.assertEqual(len(oa_rows), 1)
        oa_row = oa_rows[0]
        attachment_invoice_rows = [
            row
            for row in payload["unpaired"]["invoice"]
            if row.get("derived_from_oa_id") == oa_row["id"]
        ]
        self.assertEqual(
            sorted(row["invoice_no"] for row in attachment_invoice_rows),
            ["40512344", "40512345"],
        )
        self.assertTrue(all(row["source_kind"] == "oa_attachment_invoice" for row in attachment_invoice_rows))
        self.assertIsNone(oa_row["case_id"])
        self.assertIn("多明细", oa_row["tags"])
        self.assertIn("金额差异", oa_row["tags"])
        self.assertEqual(oa_row["amount"], "1549.00")
        self.assertEqual(oa_row["reconciliation_amount"], "1500.00")
        self.assertEqual(oa_row["amount_source"], "header")
        self.assertEqual(
            oa_row["amount_mismatch"],
            {"header_amount": "1549.00", "detail_sum": "1500.00", "difference": "49.00"},
        )

        detail_fields = oa_row["detail_fields"]
        self.assertEqual(detail_fields["金额来源"], "主表总金额")
        self.assertEqual(detail_fields["明细数量"], "2")
        self.assertEqual(detail_fields["明细金额合计"], "1500.00")
        self.assertEqual(detail_fields["金额差异"], "主表总金额 1549.00；明细合计 1500.00；差异 49.00")
        self.assertEqual(detail_fields["费用内容摘要"], "设备材料；邮寄费用")
        self.assertEqual(detail_fields["附件发票数量"], "2")
        self.assertIn("40512344", detail_fields["附件发票摘要"])

    def test_source_bound_attachment_invoice_rows_publish_with_source_context(self) -> None:
        service = WorkbenchQueryService(oa_adapter=SourceBoundAttachmentOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_rows = [row for row in payload["unpaired"]["oa"] if row["id"] == "oa-exp-hurong-248"]
        self.assertEqual(len(oa_rows), 1)
        invoice_rows = [
            row
            for row in payload["unpaired"]["invoice"]
            if row.get("derived_from_oa_id") == "oa-exp-hurong-248"
        ]
        self.assertEqual(
            sorted(row["invoice_no"] for row in invoice_rows),
            ["24800001", "24800002", "24800003"],
        )
        first_invoice = next(row for row in invoice_rows if row["invoice_no"] == "24800001")
        self.assertEqual(first_invoice["source_expense_item_id"], "oa-exp-hurong-248:item:0:maint")
        self.assertEqual(first_invoice["source_attachment_key"], "oa-exp-hurong-248:item:0:att:a")
        self.assertEqual(first_invoice["source_attachment_name"], "付款项1-发票A.pdf")
        self.assertEqual(oa_rows[0]["detail_fields"]["附件发票数量"], "3")
        self.assertIn("24800003", oa_rows[0]["detail_fields"]["附件发票摘要"])

    def test_attachment_evidences_update_oa_detail_without_formal_invoice_projection(self) -> None:
        service = WorkbenchQueryService(oa_adapter=EvidenceAttachmentOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_row = next(row for row in payload["unpaired"]["oa"] if row["id"] == "oa-evidence-2035")
        self.assertEqual(oa_row["detail_fields"]["附件发票数量"], "1")
        self.assertEqual(oa_row["detail_fields"]["付款凭证数量"], "1")

        evidence_rows = [
            row
            for row in payload["unpaired"]["invoice"]
            if row.get("derived_from_oa_id") == "oa-evidence-2035"
        ]
        self.assertEqual(len(evidence_rows), 1)
        self.assertEqual(evidence_rows[0]["invoice_no"], "53000125")
        self.assertEqual(evidence_rows[0]["evidence_type"], "machine_invoice")
        self.assertEqual(evidence_rows[0]["document_kind"], "云南通用机打发票")
        self.assertIn("53000125", oa_row["detail_fields"]["附件发票摘要"])

    def test_single_source_attachment_invoice_publishes_once_from_expense_item_copy(self) -> None:
        service = WorkbenchQueryService(oa_adapter=SourceBoundAttachmentOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_rows = [row for row in payload["unpaired"]["oa"] if row["id"] == "oa-exp-hurong-292"]
        self.assertEqual(len(oa_rows), 1)
        invoice_rows = [
            row
            for row in payload["unpaired"]["invoice"]
            if row.get("derived_from_oa_id") == "oa-exp-hurong-292"
        ]
        self.assertEqual(len(invoice_rows), 1)
        self.assertEqual(invoice_rows[0]["invoice_no"], "29200001")
        self.assertEqual(invoice_rows[0]["source_expense_item_id"], "oa-exp-hurong-292:item:0:energy")
        self.assertEqual(invoice_rows[0]["source_attachment_key"], "oa-exp-hurong-292:item:0:att:only")
        self.assertEqual(oa_rows[0]["detail_fields"]["附件发票数量"], "1")
        self.assertIn("29200001", oa_rows[0]["detail_fields"]["附件发票摘要"])

    def test_oa_row_uses_project_display_without_polluting_real_project_summary(self) -> None:
        service = WorkbenchQueryService(oa_adapter=MultiProjectDisplayOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_row = next(row for row in payload["unpaired"]["oa"] if row["id"] == "oa-exp-display-001")
        self.assertEqual(oa_row["project_name"], "玉烟维护项目；云南溯源科技")
        self.assertEqual(oa_row["project_name_display"], "多个项目")
        self.assertEqual(oa_row["project_names"], ["玉烟维护项目", "云南溯源科技"])
        self.assertEqual(oa_row["summary_fields"]["项目名称"], "多个项目")
        self.assertEqual(oa_row["detail_fields"]["项目名称汇总"], "玉烟维护项目；云南溯源科技")
        self.assertEqual(oa_row["detail_fields"]["项目名称列表"], ["玉烟维护项目", "云南溯源科技"])

    def test_unparsed_attachment_oa_row_gets_unparsed_invoice_tag(self) -> None:
        service = WorkbenchQueryService(oa_adapter=UnparsedAttachmentOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_row = payload["unpaired"]["oa"][0]
        self.assertIn("未解析发票", oa_row["tags"])
        self.assertEqual(oa_row["detail_fields"]["附件发票数量"], "0")
        self.assertEqual(oa_row["detail_fields"]["附件发票识别情况"], "已解析 0 / 2")

    def test_payment_receipt_only_oa_row_does_not_get_unparsed_invoice_tag(self) -> None:
        record = UnparsedAttachmentRecord()
        record.attachment_evidences = [
            {
                "evidence_type": "payment_receipt",
                "document_kind": "wechat_etc_payment",
                "amount": "23.00",
                "source_attachment_key": "payment-1",
                "source_attachment_name": "微信支付凭证.jpg",
            }
        ]
        record.attachment_artifacts = [
            {
                "parse_status": "parsed",
                "document_kind": "wechat_etc_payment",
                "source_attachment_key": "payment-1",
                "source_attachment_name": "微信支付凭证.jpg",
            }
        ]
        class PaymentReceiptOnlyOAAdapter:
            def list_application_records(self, month: str) -> list[object]:
                return [record] if month == "2026-03" else []

        service = WorkbenchQueryService(oa_adapter=PaymentReceiptOnlyOAAdapter())

        payload = service.get_workbench("2026-03")

        oa_row = payload["unpaired"]["oa"][0]
        self.assertNotIn("未解析发票", oa_row["tags"])
        self.assertEqual(oa_row["detail_fields"]["附件发票数量"], "0")
        self.assertEqual(oa_row["detail_fields"]["付款凭证数量"], "1")

    def test_etc_batch_oa_row_keeps_source_and_waits_only_for_bank(self) -> None:
        service = WorkbenchQueryService(oa_adapter=EtcBatchOAAdapter())

        payload = service.get_workbench("2026-05")

        oa_row = payload["unpaired"]["oa"][0]
        self.assertEqual(oa_row["source"], "etc_batch")
        self.assertEqual(oa_row["etc_batch_id"], "etc_20260503_001")
        self.assertEqual(oa_row["etcBatchId"], "etc_20260503_001")
        self.assertIn("ETC批量提交", oa_row["tags"])
        self.assertEqual(oa_row["oa_bank_relation"]["label"], "待找流水")
        self.assertNotIn("待找发票", oa_row["tags"])

    def test_all_workbench_prefers_bulk_oa_read_when_adapter_supports_it(self) -> None:
        adapter = BulkOAAdapter(
            [
                OAApplicationRecord(
                    id="oa-bulk-202603-001",
                    month="2026-03",
                    section="unpaired",
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
                    section="unpaired",
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

if __name__ == "__main__":
    unittest.main()
