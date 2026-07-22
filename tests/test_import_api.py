import json
import unittest

from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.import_file_service import parse_ccb_rows, parse_cmbc_rows, parse_icbc_rows, parse_pingan_rows
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

    def test_bank_file_parsers_preserve_real_excel_text_field_contracts(self) -> None:
        icbc_rows = [
            ["[HISTORYDETAIL]"],
            ["凭证号", "交易时间", "对方单位", "对方账号", "转入金额", "转出金额", "余额", "用途", "摘要", "附言"],
            ["ICBC-001", "2026-04-16 11:09:16", "供应商A", "1001", "", "4000.00", "7907.36", "本公司税户", "本公司税户", "18841483"],
        ]
        ccb_rows = [
            ["账号", "账户名称", "交易时间", "借方发生额（支取）", "贷方发生额（收入）", "余额", "币种", "对方户名", "对方账号", "对方开户机构", "记账日期", "摘要", "备注", "账户明细编号-交易流水号"],
            ["53001905038050548106", "云南溯源科技有限公司", "20260410 17:07:09", "40737.33", "0", "407812.09", "人民币元", "供应商B", "2001", "开户行", "20260410", "电子转账", "工资", "13523"],
        ]
        cmbc_rows = [
            ["账户名称:", "云南溯源科技有限公司"],
            ["账号:", "641979486"],
            ["币种:", "人民币"],
            ["交易时间", "交易流水号", "借方发生额", "贷方发生额", "账户余额", "凭证号", "客户附言", "对方账号", "对方账号名称", "对方开户行"],
            ["2026-04-13 10:05:43", "CMBC-001", "65000.00", "", "8189.46", "9800000000041", "本公司帐户", "2502014019350006386", "云南溯源科技有限公司", "中国工商银行总行清算中心"],
        ]

        icbc = parse_icbc_rows(icbc_rows)[0]
        ccb = parse_ccb_rows(ccb_rows)[0]
        cmbc = parse_cmbc_rows(cmbc_rows)[0]

        self.assertEqual(
            icbc["bank_text_fields"],
            [
                {"label": "摘要", "value": "本公司税户"},
                {"label": "用途", "value": "本公司税户"},
                {"label": "附言", "value": "18841483"},
            ],
        )
        self.assertEqual(
            ccb["bank_text_fields"],
            [
                {"label": "摘要", "value": "电子转账"},
                {"label": "备注", "value": "工资"},
            ],
        )
        self.assertIsNone(cmbc["summary"])
        self.assertEqual(cmbc["remark"], "本公司帐户")
        self.assertEqual(cmbc["bank_text_fields"], [{"label": "客户附言", "value": "本公司帐户"}])

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

        preview = app._import_service.preview_import(
            batch_type=BatchType.OUTPUT_INVOICE,
            source_name="api-output-demo.json",
            imported_by="user_finance_01",
            rows=[
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
        )

        self.assertEqual(preview.batch.row_count, 2)
        self.assertEqual(preview.batch.success_count, 1)
        self.assertEqual(preview.row_results[1].decision.value, "error")

        confirmed_batch = app._import_service.confirm_import(preview.id)
        app._state_store.save_import_delta(  # noqa: SLF001
            {
                "imports": app._import_service.persistence_snapshot_for_batches([preview.id])  # noqa: SLF001
            }
        )
        self.assertEqual(confirmed_batch.status.value, "completed_with_errors")

        batch_response = app.handle_request(
            "GET",
            f"/imports/batches/{preview.id}",
        )
        self.assertEqual(batch_response.status_code, 200)
        batch_payload = json.loads(batch_response.body)
        self.assertEqual(batch_payload["batch"]["source_name"], "api-output-demo.json")
        self.assertEqual(len(batch_payload["row_results"]), 2)

    def test_legacy_json_import_write_routes_are_removed(self) -> None:
        app = build_application()

        for path in ("/imports/preview", "/imports/confirm"):
            response = app.handle_request("POST", path, json.dumps({}))
            self.assertEqual(response.status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
