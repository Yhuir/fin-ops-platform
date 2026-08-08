from decimal import Decimal
import unittest
from unittest.mock import patch

from fin_ops_platform.domain.enums import BatchType, InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BankTransactionAutoCategoryService,
)
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.bank_transaction_effective_category_provider import (
    BankTransactionEffectiveCategoryProvider,
)
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.live_workbench_service import LiveWorkbenchService
from fin_ops_platform.services.matching import MatchingEngineService


class StaticCategoryProvider:
    def __init__(self, categories_by_transaction_id: dict[str, dict[str, str]]) -> None:
        self.categories_by_transaction_id = categories_by_transaction_id

    def bulk_get(self, transaction_ids: list[str]) -> dict[str, dict[str, str]]:
        return {
            transaction_id: self.categories_by_transaction_id[transaction_id]
            for transaction_id in transaction_ids
            if transaction_id in self.categories_by_transaction_id
        }


class PagedFactRepository:
    def __init__(self, invoices: list[Invoice], transactions: list[BankTransaction]) -> None:
        self.invoices = invoices
        self.transactions = transactions
        self.invoice_calls: list[dict[str, object]] = []
        self.transaction_calls: list[dict[str, object]] = []

    def list_invoices_page(self, *, page: int = 1, page_size: int = 100, month: str | None = None, **_: object) -> tuple[list[Invoice], int]:
        self.invoice_calls.append({"page": page, "page_size": page_size, "month": month})
        rows = [
            invoice
            for invoice in self.invoices
            if month in (None, "", "all") or (invoice.invoice_date or "").startswith(str(month))
        ]
        start = (page - 1) * page_size
        return rows[start:start + page_size], len(rows)

    def list_bank_transactions_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        date_from: str | None = None,
        date_to: str | None = None,
        **_: object,
    ) -> tuple[list[BankTransaction], int]:
        self.transaction_calls.append({"page": page, "page_size": page_size, "date_from": date_from, "date_to": date_to})
        rows = [
            transaction
            for transaction in self.transactions
            if (date_from is None or (transaction.txn_date or "") >= date_from)
            and (date_to is None or (transaction.txn_date or "") <= date_to)
        ]
        start = (page - 1) * page_size
        return rows[start:start + page_size], len(rows)


class LiveWorkbenchServiceTests(unittest.TestCase):
    def _effective_category_provider(
        self,
        import_service: ImportNormalizationService,
    ) -> tuple[BankTransactionCategoryService, BankTransactionEffectiveCategoryProvider]:
        transaction_ids = {transaction.id for transaction in import_service.list_transactions()}
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in transaction_ids,
        )
        return (
            category_service,
            BankTransactionEffectiveCategoryProvider(
                category_service=category_service,
                auto_category_service=BankTransactionAutoCategoryService(),
            ),
        )

    def test_workbench_reads_month_scoped_rows_from_sql_fact_repository_without_snapshot_imports(self) -> None:
        counterparty = Counterparty(
            id="cp-sql-001",
            name="真实 SQL 供应商",
            normalized_name="真实 SQL 供应商",
            counterparty_type="supplier",
        )
        invoice = Invoice(
            id="sql-invoice-202603",
            invoice_type=InvoiceType.INPUT,
            invoice_no="SQL-INV-001",
            counterparty=counterparty,
            amount=Decimal("123.45"),
            signed_amount=Decimal("123.45"),
            invoice_date="2026-03-18",
            seller_name="真实 SQL 供应商",
            buyer_name="云南溯源科技有限公司",
            workbench_visibility="visible",
        )
        transaction = BankTransaction(
            id="sql-bank-202603",
            account_no="622200001234",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="真实 SQL 供应商",
            amount=Decimal("123.45"),
            signed_amount=Decimal("-123.45"),
            txn_date="2026-03-19",
            trade_time="2026-03-19 09:30:00",
            source_batch_id="batch-sql",
        )
        repository = PagedFactRepository([invoice], [transaction])
        import_service = ImportNormalizationService(fact_repository=repository)

        service = LiveWorkbenchService(import_service, MatchingEngineService(import_service))
        payload = service.get_workbench("2026-03")

        self.assertEqual([row["id"] for row in payload["unpaired"]["invoice"]], ["sql-invoice-202603"])
        self.assertEqual([row["id"] for row in payload["unpaired"]["bank"]], ["sql-bank-202603"])
        self.assertEqual(payload["summary"]["invoice_count"], 1)
        self.assertEqual(payload["summary"]["bank_count"], 1)
        self.assertEqual(repository.invoice_calls[0]["month"], "2026-03")
        self.assertEqual(repository.transaction_calls[0]["date_from"], "2026-03-01")

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
        invoice_row = payload["unpaired"]["invoice"][0]

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
                    "trade_time": "2026-03-27 08:00:00",
                    "counterparty_name": "Workbench API Client",
                    "credit_amount": "150.00",
                    "debit_amount": "",
                    "bank_serial_no": "SERIAL-DEMO-001",
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
                    "trade_time": "2026-03-28 09:15:00",
                    "pay_receive_time": "2026-03-28 09:15:00",
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
        bank_rows = payload["unpaired"]["bank"]

        self.assertEqual(len(bank_rows), 1)
        self.assertEqual(bank_rows[0]["counterparty_name"], "真实供应商")
        self.assertEqual(bank_rows[0]["trade_time"], "2026-03-28 09:15:00")

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
        invoice_rows = {row["id"]: row for row in payload["unpaired"]["invoice"]}

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

    def test_bank_rows_include_manual_category_and_historical_text_field_fallbacks(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="category-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220008",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-20",
                    "trade_time": "2026-03-20 12:15:00",
                    "pay_receive_time": "2026-03-20 12:15:00",
                    "counterparty_name": "外部往来客户",
                    "debit_amount": "",
                    "credit_amount": "600.00",
                    "summary": "电子转账",
                    "remark": "代购公车款",
                },
            ],
        )
        import_service.confirm_import(preview.id)
        transaction_id = import_service.list_transactions()[0].id

        service = LiveWorkbenchService(
            import_service,
            MatchingEngineService(import_service),
            category_provider=StaticCategoryProvider(
                {
                    transaction_id: {
                        "category_code": "borrow_in_company_pending_repayment",
                        "category_label": "公司暂借款：待还款",
                        "source": "manual",
                    }
                }
            ),
        )

        payload = service.get_workbench("2026-03")
        bank_row = payload["unpaired"]["bank"][0]

        self.assertEqual(bank_row["category_code"], "borrow_in_company_pending_repayment")
        self.assertEqual(bank_row["category_label"], "公司暂借款：待还款")
        self.assertEqual(bank_row["category_source"], "manual")
        self.assertIn("公司暂借款：待还款", bank_row["tags"])
        self.assertEqual(
            bank_row["bank_text_fields"],
            [
                {"label": "摘要", "value": "电子转账"},
                {"label": "备注", "value": "代购公车款"},
            ],
        )
        detail = service.get_row_detail(transaction_id)
        self.assertEqual(detail["detail_fields"]["摘要"], "电子转账")
        self.assertEqual(detail["detail_fields"]["备注"], "代购公车款")

    def test_bank_rows_include_auto_effective_category_tags(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="auto-fee-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220009",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-21",
                    "trade_time": "2026-03-21 12:15:00",
                    "pay_receive_time": "2026-03-21 12:15:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "10.00",
                    "credit_amount": "",
                    "summary": "网银手续费",
                },
            ],
        )
        import_service.confirm_import(preview.id)
        _, provider = self._effective_category_provider(import_service)

        service = LiveWorkbenchService(
            import_service,
            MatchingEngineService(import_service),
            category_provider=provider,
        )

        bank_row = service.get_workbench("2026-03")["unpaired"]["bank"][0]

        self.assertEqual(bank_row["category_code"], "fee")
        self.assertEqual(bank_row["category_label"], "手续费")
        self.assertEqual(bank_row["category_primary_label"], "费用")
        self.assertEqual(bank_row["category_sub_label"], "手续费")
        self.assertEqual(bank_row["category_label_path"], ["费用", "手续费"])
        self.assertEqual(bank_row["category_source"], "auto")
        self.assertIn("费用", bank_row["tags"])
        self.assertIn("手续费", bank_row["tags"])

    def test_bank_rows_non_assignment_manual_history_does_not_override_auto_effective_category(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="manual-over-auto-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220010",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-22",
                    "trade_time": "2026-03-22 12:15:00",
                    "pay_receive_time": "2026-03-22 12:15:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "10.00",
                    "credit_amount": "",
                    "summary": "网银手续费",
                },
            ],
        )
        import_service.confirm_import(preview.id)
        transaction_id = import_service.list_transactions()[0].id
        category_service, provider = self._effective_category_provider(import_service)
        category_service.apply_updates(
            [
                {
                    "transaction_id": transaction_id,
                    "category_code": "bonus",
                    "expected_version": 0,
                }
            ],
            actor="YNSYLP005",
        )

        service = LiveWorkbenchService(
            import_service,
            MatchingEngineService(import_service),
            category_provider=provider,
        )

        bank_row = service.get_workbench("2026-03")["unpaired"]["bank"][0]

        self.assertEqual(bank_row["category_code"], "fee")
        self.assertEqual(bank_row["category_label"], "手续费")
        self.assertEqual(bank_row["category_source"], "auto")
        self.assertIn("手续费", bank_row["tags"])
        self.assertNotIn("奖金", bank_row["tags"])

    def test_bank_rows_manual_clear_history_does_not_suppress_auto_effective_category(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="manual-clear-auto-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220011",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-23",
                    "trade_time": "2026-03-23 12:15:00",
                    "pay_receive_time": "2026-03-23 12:15:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "10.00",
                    "credit_amount": "",
                    "summary": "网银手续费",
                },
            ],
        )
        import_service.confirm_import(preview.id)
        transaction_id = import_service.list_transactions()[0].id
        category_service, provider = self._effective_category_provider(import_service)
        category_service.apply_updates(
            [{"transaction_id": transaction_id, "category_code": None, "expected_version": 0}],
            actor="YNSYLP005",
        )

        service = LiveWorkbenchService(
            import_service,
            MatchingEngineService(import_service),
            category_provider=provider,
        )

        bank_row = service.get_workbench("2026-03")["unpaired"]["bank"][0]

        self.assertEqual(bank_row["category_code"], "fee")
        self.assertEqual(bank_row["category_label"], "手续费")
        self.assertEqual(bank_row["category_source"], "auto")
        self.assertIn("手续费", bank_row["tags"])

    def test_bank_rows_include_auto_internal_transfer_effective_category(self) -> None:
        import_service = ImportNormalizationService()
        preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="auto-internal-transfer-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-24",
                    "trade_time": "2026-03-24 09:15:00",
                    "pay_receive_time": "2026-03-24 09:15:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "50000.00",
                    "credit_amount": "",
                    "summary": "内部往来支出",
                },
                {
                    "account_no": "62220002",
                    "account_name": "云南溯源科技有限公司招商银行一般户",
                    "txn_date": "2026-03-24",
                    "trade_time": "2026-03-24 10:02:00",
                    "pay_receive_time": "2026-03-24 10:02:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "",
                    "credit_amount": "50000.00",
                    "summary": "内部往来收入",
                },
            ],
        )
        import_service.confirm_import(preview.id)
        _, provider = self._effective_category_provider(import_service)

        service = LiveWorkbenchService(
            import_service,
            MatchingEngineService(import_service),
            category_provider=provider,
        )

        bank_rows = service.get_workbench("2026-03")["unpaired"]["bank"]

        self.assertEqual(len(bank_rows), 2)
        for bank_row in bank_rows:
            self.assertEqual(bank_row["category_code"], "internal_transfer")
            self.assertEqual(bank_row["category_label"], "内部往来款")
            self.assertEqual(bank_row["category_source"], "auto")
            self.assertIn("内部往来款", bank_row["tags"])

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
        bank_row = payload["unpaired"]["bank"][0]

        self.assertEqual(bank_row["payment_account_label"], "建设银行 基本户 8826")
        detail_row = service.get_row_detail(bank_row["id"])
        self.assertEqual(detail_row["summary_fields"]["支付账户"], "建设银行 基本户 8826")


if __name__ == "__main__":
    unittest.main()
