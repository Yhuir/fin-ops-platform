from decimal import Decimal
import unittest

from openpyxl import Workbook

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.project_detail_export_service import ProjectDetailExportService


class ProjectDetailExportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.import_service = ImportNormalizationService(
            existing_transactions=[
                BankTransaction(
                    id="txn-export-001",
                    account_no="62220001",
                    txn_direction=TransactionDirection.OUTFLOW,
                    counterparty_name_raw="昆明设备供应商",
                    amount=Decimal("1000.00"),
                    signed_amount=Decimal("-1000.00"),
                    txn_date="2026-03-10",
                    trade_time="2026-03-10 21:27:55",
                    pay_receive_time="2026-03-10 21:27:55",
                    summary="设备采购",
                    remark="设备采购款",
                ),
                BankTransaction(
                    id="txn-export-002",
                    account_no="62220002",
                    txn_direction=TransactionDirection.OUTFLOW,
                    counterparty_name_raw="昆明物流服务商",
                    amount=Decimal("80.00"),
                    signed_amount=Decimal("-80.00"),
                    txn_date="2026-03-12",
                    trade_time="2026-03-12 08:00:00",
                    pay_receive_time="2026-03-12 08:00:00",
                    summary="邮寄费",
                    remark="已处理异常",
                ),
            ]
        )
        self.grouped_payload = {
            "month": "2026-03",
            "summary": {},
            "paired": {
                "groups": [
                    {
                        "group_id": "case:normal",
                        "group_type": "manual_confirmed",
                        "oa_rows": [
                            {
                                "id": "oa-export-001",
                                "type": "oa",
                                "project_name": "云南溯源科技",
                                "expense_type": "设备货款及材料费",
                                "expense_content": "PLC 模块采购",
                                "amount": "1000.00",
                                "applicant": "刘际涛",
                                "detail_fields": {"OA单号": "OA-001"},
                                "handled_exception": False,
                            }
                        ],
                        "bank_rows": [
                            {
                                "id": "txn-export-001",
                                "type": "bank",
                                "trade_time": "2026-03-10 21:27:55",
                                "counterparty_name": "昆明设备供应商",
                                "payment_account_label": "工商银行 账户 0001",
                                "remark": "设备采购款",
                                "invoice_relation": {"label": "已关联OA"},
                                "handled_exception": False,
                            }
                        ],
                        "invoice_rows": [
                            {
                                "id": "inv-export-001",
                                "type": "invoice",
                                "seller_name": "昆明设备供应商",
                                "buyer_name": "云南溯源科技有限公司",
                                "amount": "885.00",
                                "tax_amount": "115.00",
                                "invoice_bank_relation": {"label": "已关联流水"},
                                "detail_fields": {"发票号码": "INV-001"},
                                "handled_exception": False,
                            }
                        ],
                    }
                ]
            },
            "open": {
                "groups": [
                    {
                        "group_id": "temp:exception",
                        "group_type": "candidate",
                        "oa_rows": [
                            {
                                "id": "oa-export-002",
                                "type": "oa",
                                "project_name": "云南溯源科技",
                                "expense_type": "运费/邮费/杂费",
                                "expense_content": "邮寄费用",
                                "amount": "80.00",
                                "applicant": "刘际涛",
                                "detail_fields": {"OA单号": "OA-002"},
                                "oa_bank_relation": {"label": "无对应流水（还没付钱）"},
                                "handled_exception": True,
                            }
                        ],
                        "bank_rows": [
                            {
                                "id": "txn-export-002",
                                "type": "bank",
                                "trade_time": "2026-03-12 08:00:00",
                                "counterparty_name": "昆明物流服务商",
                                "payment_account_label": "工商银行 账户 0002",
                                "remark": "已处理异常",
                                "invoice_relation": {"label": "无对应OA（补手续费）"},
                                "handled_exception": True,
                            }
                        ],
                        "invoice_rows": [],
                    }
                ]
            },
        }
        self.raw_payload = {
            "month": "2026-03",
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-export-ignored",
                        "type": "oa",
                        "project_name": "云南溯源科技",
                        "expense_type": "其他",
                        "expense_content": "暂不处理",
                        "amount": "50.00",
                        "oa_bank_relation": {"label": "待找流水与发票"},
                        "ignored": True,
                    }
                ],
                "bank": [],
                "invoice": [],
            },
        }

    def test_build_project_export_payload_separates_normal_exception_and_ignored_sections(self) -> None:
        service = ProjectDetailExportService(
            self.import_service,
            grouped_workbench_loader=lambda month: self.grouped_payload,
            raw_workbench_loader=lambda month: self.raw_payload,
        )

        payload = service.build_export_payload(month="2026-03", project_name="云南溯源科技")

        self.assertEqual(payload["project_name"], "云南溯源科技")
        self.assertEqual(payload["summary"]["total_amount"], "1,000.00")
        self.assertEqual(payload["summary"]["transaction_count"], 1)
        self.assertEqual(payload["summary"]["exception_count"], 2)
        self.assertEqual(payload["summary"]["ignored_count"], 1)
        self.assertEqual(payload["expense_type_rows"][0]["expense_type"], "设备货款及材料费")
        self.assertEqual(payload["expense_content_rows"][0]["expense_content"], "PLC 模块采购")
        self.assertEqual(payload["transaction_rows"][0]["transaction_id"], "txn-export-001")
        self.assertEqual(payload["oa_rows"][0]["oa_form_no"], "OA-001")
        self.assertEqual(payload["invoice_rows"][0]["invoice_no"], "INV-001")
        self.assertEqual(payload["exception_rows"][0]["status_label"], "无对应流水（还没付钱）")
        self.assertEqual(payload["ignored_rows"][0]["record_id"], "oa-export-ignored")

    def test_build_workbook_creates_expected_sheets(self) -> None:
        service = ProjectDetailExportService(
            self.import_service,
            grouped_workbench_loader=lambda month: self.grouped_payload,
            raw_workbench_loader=lambda month: self.raw_payload,
        )

        payload = service.build_export_payload(month="2026-03", project_name="云南溯源科技")
        workbook = service.build_workbook(payload)

        self.assertIsInstance(workbook, Workbook)
        self.assertEqual(
            workbook.sheetnames,
            [
                "导出说明",
                "项目汇总",
                "按费用类型汇总",
                "按费用内容汇总",
                "流水明细",
                "OA关联明细",
                "发票关联明细",
                "异常与未闭环",
            ],
        )


if __name__ == "__main__":
    unittest.main()
