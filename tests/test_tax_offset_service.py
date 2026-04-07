import unittest
from decimal import Decimal

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.tax_certified_import_service import TaxCertifiedInvoiceRecord
from fin_ops_platform.services.tax_offset_service import TaxOffsetService


class TaxOffsetServiceTests(unittest.TestCase):
    def test_month_payload_builds_real_input_plan_from_imported_input_invoices(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="real-input-plan.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "255020000001",
                    "digital_invoice_no": "25502000000145098656",
                    "invoice_no": "45098656",
                    "counterparty_name": "重庆高新技术产业开发区国家税务局",
                    "seller_tax_no": "91500226MA60KH3C0Q",
                    "seller_name": "重庆高新技术产业开发区国家税务局",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_date": "2026-01-02",
                    "amount": "6000.00",
                    "tax_amount": "180.00",
                    "total_with_tax": "6180.00",
                    "tax_rate": "3%",
                    "invoice_kind": "进项普票",
                    "risk_level": "低",
                    "invoice_status_from_source": "正常",
                }
            ],
        )
        import_service.confirm_import(preview.id)
        service = TaxOffsetService(
            import_service=import_service,
            certified_records_loader=lambda month: [],
        )

        payload = service.get_month_payload("2026-01")

        self.assertEqual(len(payload["output_items"]), 0)
        self.assertEqual(len(payload["input_plan_items"]), 1)
        self.assertEqual(payload["input_plan_items"][0]["invoice_no"], "25502000000145098656")
        self.assertEqual(payload["input_plan_items"][0]["digital_invoice_no"], "25502000000145098656")
        self.assertEqual(payload["input_plan_items"][0]["seller_name"], "重庆高新技术产业开发区国家税务局")
        self.assertEqual(payload["input_plan_items"][0]["invoice_type"], "进项普票")
        self.assertEqual(payload["input_plan_items"][0]["tax_rate"], "3%")
        self.assertEqual(payload["default_selected_input_ids"], [payload["input_plan_items"][0]["id"]])

    def test_month_payload_uses_real_certified_records_to_lock_matching_plan_and_split_outside_plan(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="real-input-plan.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "255020000001",
                    "digital_invoice_no": "2550200000011203490",
                    "invoice_no": "11203490",
                    "counterparty_name": "设备供应商",
                    "seller_tax_no": "91530000DEVICE001",
                    "seller_name": "设备供应商",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_date": "2026-03-22",
                    "amount": "96000.00",
                    "tax_amount": "12480.00",
                    "total_with_tax": "108480.00",
                    "tax_rate": "13%",
                    "invoice_kind": "进项专票",
                    "risk_level": "低",
                    "invoice_status_from_source": "正常",
                }
            ],
        )
        import_service.confirm_import(preview.id)
        service = TaxOffsetService(
            import_service=import_service,
            certified_records_loader=lambda month: [
                TaxCertifiedInvoiceRecord(
                    id="cert-001",
                    unique_key="digital:cert-001",
                    month=month,
                    source_file_name="certified.xlsx",
                    source_row_number=4,
                    taxpayer_tax_no="915300007194052520",
                    taxpayer_name="云南溯源科技有限公司",
                    digital_invoice_no="2550200000011203490",
                    invoice_code="255020000001",
                    invoice_no="11203490",
                    issue_date="2026-03-22",
                    seller_tax_no="91530000DEVICE001",
                    seller_name="设备供应商",
                    amount="96000.00",
                    tax_amount="12480.00",
                    deductible_tax_amount="12480.00",
                    selection_status="已勾选",
                    invoice_status="正常",
                    selection_time="2026-04-01 09:00:00",
                ),
                TaxCertifiedInvoiceRecord(
                    id="cert-099",
                    unique_key="invoice:255020000009:11203999",
                    month=month,
                    source_file_name="certified.xlsx",
                    source_row_number=5,
                    taxpayer_tax_no="915300007194052520",
                    taxpayer_name="云南溯源科技有限公司",
                    digital_invoice_no="25502000000911203999",
                    invoice_code="255020000009",
                    invoice_no="11203999",
                    issue_date="2026-03-28",
                    seller_tax_no="91530000PROPERTY99",
                    seller_name="物业服务商",
                    amount="12000.00",
                    tax_amount="1600.00",
                    deductible_tax_amount="1600.00",
                    selection_status="已勾选",
                    invoice_status="正常",
                    selection_time="2026-04-01 09:01:00",
                ),
            ]
        )

        payload = service.get_month_payload("2026-03")

        self.assertIn("input_plan_items", payload)
        self.assertIn("certified_items", payload)
        self.assertIn("certified_matched_rows", payload)
        self.assertIn("certified_outside_plan_rows", payload)
        self.assertIn("locked_certified_input_ids", payload)
        self.assertEqual(payload["locked_certified_input_ids"], [payload["input_plan_items"][0]["id"]])
        self.assertEqual(len(payload["certified_outside_plan_rows"]), 1)
        self.assertEqual(payload["summary"]["certified_input_tax"], "14,080.00")

    def test_calculate_uses_real_certified_records_even_when_not_selected(self) -> None:
        service = TaxOffsetService(
            certified_records_loader=lambda month: [
                TaxCertifiedInvoiceRecord(
                    id="cert-001",
                    unique_key="digital:cert-001",
                    month=month,
                    source_file_name="certified.xlsx",
                    source_row_number=4,
                    taxpayer_tax_no="915300007194052520",
                    taxpayer_name="云南溯源科技有限公司",
                    digital_invoice_no="2550200000011203490",
                    invoice_code="255020000001",
                    invoice_no="11203490",
                    issue_date="2026-03-22",
                    seller_tax_no="91530000DEVICE001",
                    seller_name="设备供应商",
                    amount="96000.00",
                    tax_amount="12480.00",
                    deductible_tax_amount="12480.00",
                    selection_status="已勾选",
                    invoice_status="正常",
                    selection_time="2026-04-01 09:00:00",
                ),
                TaxCertifiedInvoiceRecord(
                    id="cert-099",
                    unique_key="invoice:255020000009:11203999",
                    month=month,
                    source_file_name="certified.xlsx",
                    source_row_number=5,
                    taxpayer_tax_no="915300007194052520",
                    taxpayer_name="云南溯源科技有限公司",
                    digital_invoice_no="25502000000911203999",
                    invoice_code="255020000009",
                    invoice_no="11203999",
                    issue_date="2026-03-28",
                    seller_tax_no="91530000PROPERTY99",
                    seller_name="物业服务商",
                    amount="12000.00",
                    tax_amount="1600.00",
                    deductible_tax_amount="1600.00",
                    selection_status="已勾选",
                    invoice_status="正常",
                    selection_time="2026-04-01 09:01:00",
                ),
            ]
        )

        result = service.calculate(
            month="2026-03",
            selected_output_ids=[],
            selected_input_ids=[],
        )

        self.assertEqual(result["summary"]["output_tax"], "41,600.00")
        self.assertEqual(result["summary"]["input_tax"], "14,080.00")
        self.assertEqual(result["summary"]["planned_input_tax"], "0.00")
        self.assertEqual(result["summary"]["certified_input_tax"], "14,080.00")
        self.assertEqual(result["summary"]["deductible_tax"], "14,080.00")
        self.assertEqual(result["summary"]["result_label"], "本月应纳税额")
        self.assertEqual(result["summary"]["result_amount"], "27,520.00")

    def test_match_certified_to_plan_supports_digital_invoice_then_code_number_then_fallback(self) -> None:
        service = TaxOffsetService(
            month_data={
                "2026-05": {
                    "output_items": [],
                    "input_plan_items": [
                        {
                            "id": "ti-1",
                            "seller_name": "甲供应商",
                            "seller_tax_no": "91530000AAA000001",
                            "issue_date": "2026-05-08",
                            "invoice_code": "255020000001",
                            "digital_invoice_no": "25502000000112345678",
                            "invoice_no": "12345678",
                            "tax_amount": "120.00",
                            "total_with_tax": "1,120.00",
                            "risk_level": "低",
                        },
                        {
                            "id": "ti-2",
                            "seller_name": "乙供应商",
                            "seller_tax_no": "91530000BBB000002",
                            "issue_date": "2026-05-09",
                            "invoice_code": "255020000002",
                            "invoice_no": "87654321",
                            "tax_amount": "88.00",
                            "total_with_tax": "888.00",
                            "risk_level": "低",
                        },
                        {
                            "id": "ti-3",
                            "seller_name": "丙供应商",
                            "seller_tax_no": "91530000CCC000003",
                            "issue_date": "2026-05-10",
                            "invoice_no": "00000001",
                            "tax_amount": "66.00",
                            "total_with_tax": "666.00",
                            "risk_level": "低",
                        },
                    ],
                }
            },
            certified_records_loader=lambda month: [
                TaxCertifiedInvoiceRecord(
                    id="cert-a",
                    unique_key="digital:25502000000112345678",
                    month=month,
                    source_file_name="certified.xlsx",
                    source_row_number=4,
                    taxpayer_tax_no="915300007194052520",
                    taxpayer_name="云南溯源科技有限公司",
                    digital_invoice_no="25502000000112345678",
                    invoice_code="255020000001",
                    invoice_no="12345678",
                    issue_date="2026-05-08",
                    seller_tax_no="91530000AAA000001",
                    seller_name="甲供应商",
                    amount="1000.00",
                    tax_amount="120.00",
                    deductible_tax_amount="120.00",
                    selection_status="已勾选",
                    invoice_status="正常",
                    selection_time="2026-06-01 09:00:00",
                ),
                TaxCertifiedInvoiceRecord(
                    id="cert-b",
                    unique_key="invoice:255020000002:87654321",
                    month=month,
                    source_file_name="certified.xlsx",
                    source_row_number=5,
                    taxpayer_tax_no="915300007194052520",
                    taxpayer_name="云南溯源科技有限公司",
                    digital_invoice_no=None,
                    invoice_code="255020000002",
                    invoice_no="87654321",
                    issue_date="2026-05-09",
                    seller_tax_no="91530000BBB000002",
                    seller_name="乙供应商",
                    amount="800.00",
                    tax_amount="88.00",
                    deductible_tax_amount="88.00",
                    selection_status="已勾选",
                    invoice_status="正常",
                    selection_time="2026-06-01 09:01:00",
                ),
                TaxCertifiedInvoiceRecord(
                    id="cert-c",
                    unique_key="fallback:91530000CCC000003:2026-05-10:66.00",
                    month=month,
                    source_file_name="certified.xlsx",
                    source_row_number=6,
                    taxpayer_tax_no="915300007194052520",
                    taxpayer_name="云南溯源科技有限公司",
                    digital_invoice_no=None,
                    invoice_code=None,
                    invoice_no=None,
                    issue_date="2026-05-10",
                    seller_tax_no="91530000CCC000003",
                    seller_name="丙供应商",
                    amount="600.00",
                    tax_amount="66.00",
                    deductible_tax_amount="66.00",
                    selection_status="已勾选",
                    invoice_status="正常",
                    selection_time="2026-06-01 09:02:00",
                ),
            ],
        )

        payload = service.get_month_payload("2026-05")

        self.assertEqual(payload["locked_certified_input_ids"], ["ti-1", "ti-2", "ti-3"])
        self.assertEqual(len(payload["certified_outside_plan_rows"]), 0)


if __name__ == "__main__":
    unittest.main()
