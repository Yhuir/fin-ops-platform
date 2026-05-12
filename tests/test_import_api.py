import json
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.import_file_service import parse_pingan_rows
from fin_ops_platform.services.imports import ImportNormalizationService


class ImportApiTests(unittest.TestCase):
    def test_bank_file_parser_preserves_original_text_columns(self) -> None:
        rows = [
            [
                "交易时间",
                "账号",
                "收入",
                "支出",
                "账户余额",
                "对方户名",
                "对方账号",
                "对方账号开户行",
                "摘要",
                "交易流水号",
                "核心唯一流水号",
                "交易用途",
                "币种",
            ],
            [
                "2026-01-03 09:12:00",
                "1100000000000093",
                "",
                "6180.00",
                "12000.00",
                "重庆高新技术产业开发区国家税务局",
                "500000000000001",
                "重庆银行",
                "服务费摘要",
                "PINGAN-001",
                "PINGAN-CORE-001",
                "代付服务费",
                "CNY",
            ],
        ]

        parsed = parse_pingan_rows(rows)

        self.assertEqual(
            parsed[0]["bank_text_fields"],
            [
                {"label": "摘要", "value": "服务费摘要"},
                {"label": "交易用途", "value": "代付服务费"},
            ],
        )

    def test_bank_transaction_import_preserves_text_fields_without_changing_identity(self) -> None:
        import_service = ImportNormalizationService()
        first_preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-text-fields.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "6222000000006386",
                    "txn_date": "2026-03-28",
                    "trade_time": "2026-03-28 09:15:00",
                    "counterparty_name": "云南供应商有限公司",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "summary": "电子转账",
                    "remark": "银行备注",
                    "bank_text_fields": [
                        {"label": "摘要", "value": "电子转账"},
                        {"label": "备注", "value": "银行备注"},
                        {"label": "用途", "value": "采购款"},
                        {"label": "交易用途", "value": "代付货款"},
                        {"label": "客户附言", "value": "客户留言"},
                        {"label": "附言", "value": "柜台附言"},
                    ],
                }
            ],
        )

        first_key = first_preview.normalized_rows[0]["source_unique_key"]
        import_service.confirm_import(first_preview.id)
        transaction = import_service.list_transactions()[0]

        self.assertEqual(
            transaction.bank_text_fields,
            [
                {"label": "摘要", "value": "电子转账"},
                {"label": "备注", "value": "银行备注"},
                {"label": "用途", "value": "采购款"},
                {"label": "交易用途", "value": "代付货款"},
                {"label": "客户附言", "value": "客户留言"},
                {"label": "附言", "value": "柜台附言"},
            ],
        )

        duplicate_preview = import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-text-fields-reimport.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "6222000000006386",
                    "txn_date": "2026-03-28",
                    "trade_time": "2026-03-28 09:15:00",
                    "counterparty_name": "云南供应商有限公司",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "summary": "换一个摘要",
                    "remark": "换一个备注",
                    "bank_text_fields": [
                        {"label": "摘要", "value": "换一个摘要"},
                        {"label": "备注", "value": "换一个备注"},
                    ],
                }
            ],
        )

        self.assertEqual(duplicate_preview.normalized_rows[0]["source_unique_key"], first_key)
        self.assertEqual(duplicate_preview.row_results[0].decision.value, "duplicate_skipped")

    def test_preview_confirm_and_fetch_batch_round_trip(self) -> None:
        app = build_application()

        preview_response = app.handle_request(
            "POST",
            "/imports/preview",
            json.dumps(
                {
                    "batch_type": "output_invoice",
                    "source_name": "api-output-demo.json",
                    "imported_by": "user_finance_01",
                    "rows": [
                        {
                            "invoice_code": "033001",
                            "invoice_no": "9801",
                            "counterparty_name": "API Corp",
                            "amount": "150.00",
                            "invoice_date": "2026-03-26",
                            "invoice_status_from_source": "valid",
                        },
                        {
                            "invoice_code": "033001",
                            "invoice_no": "9802",
                            "counterparty_name": "Broken Corp",
                            "amount": "oops",
                            "invoice_date": "2026-03-26",
                        },
                    ],
                }
            ),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["batch"]["row_count"], 2)
        self.assertEqual(preview_payload["batch"]["success_count"], 1)
        self.assertEqual(preview_payload["row_results"][1]["decision"], "error")

        with patch.object(app, "_run_workbench_auto_matching_for_scopes", return_value=None) as auto_match:
            confirm_response = app.handle_request(
                "POST",
                "/imports/confirm",
                json.dumps({"batch_id": preview_payload["batch"]["id"]}),
            )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["batch"]["status"], "completed_with_errors")
        import_confirm_calls = [
            call_args
            for call_args in auto_match.call_args_list
            if call_args.kwargs.get("reason") == "import_confirm"
        ]
        self.assertEqual(len(import_confirm_calls), 1)
        self.assertEqual(import_confirm_calls[0].args[0], ["2026-02", "2026-03", "2026-04"])

        batch_response = app.handle_request(
            "GET",
            f"/imports/batches/{preview_payload['batch']['id']}",
        )
        self.assertEqual(batch_response.status_code, 200)
        batch_payload = json.loads(batch_response.body)
        self.assertEqual(batch_payload["batch"]["source_name"], "api-output-demo.json")
        self.assertEqual(len(batch_payload["row_results"]), 2)


if __name__ == "__main__":
    unittest.main()
