from decimal import Decimal
import unittest
from unittest.mock import patch

from fin_ops_platform.domain.enums import BatchType, InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.live_workbench_service import LiveWorkbenchService
from fin_ops_platform.services.matching import MatchingEngineService


class LiveWorkbenchServiceTests(unittest.TestCase):
    def test_invoice_rows_expose_invoice_identity_fields_in_workbench_list(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="input-invoice.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "云南供应商有限公司",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        import_service.confirm_import(preview.id)

        service = LiveWorkbenchService(import_service, MatchingEngineService(import_service))
        payload = service.get_workbench("2026-03")
        invoice_row = payload["open"]["invoice"][0]

        self.assertEqual(invoice_row["invoice_code"], "033001")
        self.assertEqual(invoice_row["invoice_no"], "9001")
        self.assertEqual(invoice_row["digital_invoice_no"], "—")

    def test_workbench_hides_legacy_demo_bank_transactions(self) -> None:
        import_service = ImportNormalizationService()

        demo_preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank_transaction.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Workbench API Client",
                    "credit_amount": "150.00",
                    "debit_amount": "",
                    "summary": "api receipt",
                }
            ],
        )
        import_service.confirm_import(demo_preview.id)

        real_preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="historydetail14080.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220002",
                    "txn_date": "2026-03-28",
                    "trade_time": "2026-03-28 09:15",
                    "pay_receive_time": "2026-03-28 09:15",
                    "counterparty_name": "真实供应商",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-REAL-001",
                    "summary": "real payment",
                }
            ],
        )
        import_service.confirm_import(real_preview.id)

        service = LiveWorkbenchService(import_service, MatchingEngineService(import_service))
        payload = service.get_workbench("2026-03")
        bank_rows = payload["open"]["bank"]

        self.assertEqual(len(bank_rows), 1)
        self.assertEqual(bank_rows[0]["counterparty_name"], "真实供应商")
        self.assertEqual(bank_rows[0]["trade_time"], "2026-03-28 09:15")

    def test_invoice_rows_fill_missing_party_fields_from_company_identity_and_counterparty(self) -> None:
        known_company_invoice = Invoice(
            id="inv_known_company",
            invoice_type=InvoiceType.INPUT,
            invoice_no="KNOWN-001",
            counterparty=Counterparty(
                id="cp_vendor",
                name="云南供应商有限公司",
                normalized_name="云南供应商有限公司",
                counterparty_type="vendor",
                tax_no="91530100VENDOR0001",
            ),
            amount=Decimal("100.00"),
            signed_amount=Decimal("100.00"),
            invoice_date="2026-03-01",
            seller_tax_no="91530100VENDOR0001",
            seller_name="云南供应商有限公司",
            buyer_tax_no="915300007194052520",
            buyer_name="云南溯源科技有限公司",
        )
        sparse_output_invoice = Invoice(
            id="inv_sparse_output",
            invoice_type=InvoiceType.OUTPUT,
            invoice_no="OUT-001",
            counterparty=Counterparty(
                id="cp_client",
                name="云南客户有限公司",
                normalized_name="云南客户有限公司",
                counterparty_type="customer",
                tax_no="91530100CLIENT0001",
            ),
            amount=Decimal("150.00"),
            signed_amount=Decimal("150.00"),
            invoice_date="2026-03-26",
        )
        sparse_input_invoice = Invoice(
            id="inv_sparse_input",
            invoice_type=InvoiceType.INPUT,
            invoice_no="IN-001",
            counterparty=Counterparty(
                id="cp_service_vendor",
                name="云南服务商有限公司",
                normalized_name="云南服务商有限公司",
                counterparty_type="vendor",
                tax_no="91530100VENDOR0002",
            ),
            amount=Decimal("80.00"),
            signed_amount=Decimal("80.00"),
            invoice_date="2026-03-27",
        )

        import_service = ImportNormalizationService(
            existing_invoices=[known_company_invoice, sparse_output_invoice, sparse_input_invoice],
        )
        matching_service = MatchingEngineService(import_service)
        service = LiveWorkbenchService(import_service, matching_service)

        payload = service.get_workbench("2026-03")
        invoice_rows = {row["id"]: row for row in payload["open"]["invoice"]}

        output_row = invoice_rows["inv_sparse_output"]
        self.assertEqual(output_row["seller_tax_no"], "915300007194052520")
        self.assertEqual(output_row["seller_name"], "云南溯源科技有限公司")
        self.assertEqual(output_row["buyer_tax_no"], "91530100CLIENT0001")
        self.assertEqual(output_row["buyer_name"], "云南客户有限公司")

        input_row = invoice_rows["inv_sparse_input"]
        self.assertEqual(input_row["seller_tax_no"], "91530100VENDOR0002")
        self.assertEqual(input_row["seller_name"], "云南服务商有限公司")
        self.assertEqual(input_row["buyer_tax_no"], "915300007194052520")
        self.assertEqual(input_row["buyer_name"], "云南溯源科技有限公司")

        output_detail = service.get_row_detail("inv_sparse_output")
        self.assertEqual(output_detail["summary_fields"]["销方识别号"], "915300007194052520")
        self.assertEqual(output_detail["summary_fields"]["购方识别号"], "91530100CLIENT0001")
        self.assertEqual(output_detail["summary_fields"]["购买方名称"], "云南客户有限公司")
        self.assertEqual(output_detail["detail_fields"]["发票号码"], "OUT-001")
        self.assertIn("ignore", output_row["available_actions"])

    def test_get_rows_detail_uses_direct_lookup_without_rebuilding_cache(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="single-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-18",
                    "trade_time": "2026-03-18 10:00:00",
                    "pay_receive_time": "2026-03-18 10:00:00",
                    "counterparty_name": "测试对手方",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "summary": "测试单条明细",
                },
            ],
        )
        import_service.confirm_import(preview.id)
        transaction_id = import_service.list_transactions()[0].id

        service = LiveWorkbenchService(import_service, MatchingEngineService(import_service))
        with patch.object(service, "_rebuild_cache", side_effect=AssertionError("should not rebuild cache")):
            detail_rows = service.get_rows_detail([transaction_id])

        self.assertIn(transaction_id, detail_rows)
        self.assertEqual(detail_rows[transaction_id]["counterparty_name"], "测试对手方")

    def test_get_row_detail_uses_direct_lookup_without_rebuilding_cache(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="single-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220004",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-19",
                    "trade_time": "2026-03-19 11:15:46",
                    "pay_receive_time": "2026-03-19 11:15:46",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "13000.00",
                    "credit_amount": "",
                    "summary": "内部往来支出",
                },
            ],
        )
        import_service.confirm_import(preview.id)
        transaction_id = import_service.list_transactions()[0].id

        service = LiveWorkbenchService(import_service, MatchingEngineService(import_service))
        with patch.object(service, "_rebuild_cache", side_effect=AssertionError("should not rebuild cache")):
            detail = service.get_row_detail(transaction_id)

        self.assertEqual(detail["id"], transaction_id)
        self.assertEqual(detail["summary_fields"]["对方户名"], "云南溯源科技有限公司")

    def test_list_auto_pair_candidates_detects_internal_transfers_within_time_window(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="internal-transfer.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 09:15:00",
                    "pay_receive_time": "2026-02-03 09:15:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "50000.00",
                    "credit_amount": "",
                    "summary": "内部往来支出",
                },
                {
                    "account_no": "62220002",
                    "account_name": "云南溯源科技有限公司招商银行一般户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 10:02:00",
                    "pay_receive_time": "2026-02-03 10:02:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "",
                    "credit_amount": "50000.00",
                    "summary": "内部往来收入",
                },
            ],
        )
        import_service.confirm_import(preview.id)

        service = LiveWorkbenchService(import_service, MatchingEngineService(import_service))
        payload = service.get_workbench("all")
        auto_results = service.list_auto_pair_candidates("all")

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(len(payload["open"]["bank"]), 2)
        self.assertEqual(len(auto_results), 1)
        self.assertEqual(auto_results[0].rule_code, "internal_transfer_pair")
        self.assertEqual(len(auto_results[0].transaction_ids), 2)

    def test_list_auto_pair_candidates_detects_salary_transactions_for_personal_counterparties(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="salary-payment.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": "2026-02-28 17:08:00",
                    "pay_receive_time": "2026-02-28 17:08:00",
                    "counterparty_name": "李四",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "summary": "2月工资发放",
                    "remark": "工资",
                },
            ],
        )
        import_service.confirm_import(preview.id)

        service = LiveWorkbenchService(import_service, MatchingEngineService(import_service))
        payload = service.get_workbench("all")
        auto_results = service.list_auto_pair_candidates("all")

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(len(payload["open"]["bank"]), 1)
        self.assertEqual(payload["open"]["bank"][0]["counterparty_name"], "李四")
        self.assertEqual(len(auto_results), 1)
        self.assertEqual(auto_results[0].rule_code, "salary_personal_auto_match")
        self.assertEqual(auto_results[0].transaction_ids, [payload["open"]["bank"][0]["id"]])

    def test_selected_bank_mapping_controls_payment_account_label(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="selected-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220004",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-20",
                    "trade_time": "2026-03-20 11:15:46",
                    "pay_receive_time": "2026-03-20 11:15:46",
                    "counterparty_name": "云南服务商有限公司",
                    "debit_amount": "13000.00",
                    "credit_amount": "",
                    "summary": "服务费支出",
                    "selected_bank_name": "建设银行",
                    "selected_bank_last4": "8826",
                },
            ],
        )
        import_service.confirm_import(preview.id)

        service = LiveWorkbenchService(import_service, MatchingEngineService(import_service))
        payload = service.get_workbench("2026-03")
        bank_row = payload["open"]["bank"][0]

        self.assertEqual(bank_row["payment_account_label"], "建设银行 基本户 8826")
        detail_row = service.get_row_detail(bank_row["id"])
        self.assertEqual(detail_row["summary_fields"]["支付账户"], "建设银行 基本户 8826")


if __name__ == "__main__":
    unittest.main()
