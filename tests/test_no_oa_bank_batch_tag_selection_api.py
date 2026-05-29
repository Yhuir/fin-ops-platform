import json
import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType


def _json(response):
    return json.loads(response.body)


class NoOaBankBatchTagSelectionApiTests(unittest.TestCase):
    def test_tag_selection_starts_empty_and_controls_unsubmitted_candidates(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fee.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"}],
            actor="tester",
        )

        selection_response = app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection")
        selection_payload = _json(selection_response)
        empty_batches = _json(app.handle_request("GET", "/api/no-oa-bank-batches?bucket=unsubmitted"))

        self.assertEqual(selection_response.status_code, 200)
        self.assertEqual(selection_payload["selected_tag_codes"], [])
        self.assertIn("fee", [tag["code"] for tag in selection_payload["active_tags"]])
        self.assertEqual(empty_batches["batches"], [])

        save_response = app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({"expected_version": selection_payload["version"], "selected_tag_codes": ["fee"]}),
            headers={"Content-Type": "application/json"},
        )
        enabled_batches = _json(app.handle_request("GET", "/api/no-oa-bank-batches?bucket=unsubmitted"))

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(_json(save_response)["selected_tag_codes"], ["fee"])
        self.assertEqual([batch["batch_type"] for batch in enabled_batches["batches"]], ["fee"])

    def test_selected_row_submit_creates_one_batch_for_same_bank_subset(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fees.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                },
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-04",
                    "trade_time": "2026-05-04 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "18.20",
                    "credit_amount": "",
                    "summary": "账户管理手续费",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"} for row_id in row_ids],
            actor="tester",
        )
        version = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))["version"]
        app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({"expected_version": version, "selected_tag_codes": ["fee"]}),
            headers={"Content-Type": "application/json"},
        )

        response = app.handle_request(
            "POST",
            "/api/no-oa-bank-batches/submit-selection",
            body=json.dumps({"transaction_ids": [row_ids[0]], "note": "提交单条手续费"}),
            headers={"Content-Type": "application/json"},
        )
        payload = _json(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["batch"]["status"], "submitted")
        self.assertEqual(payload["batch"]["batch_type"], "fee")
        self.assertEqual(payload["batch"]["row_ids"], [row_ids[0]])
        self.assertEqual(payload["batch"]["row_count"], 1)
        self.assertEqual(payload["batch"]["total_amount"], "8.80")
        self.assertEqual(payload["results"], [{"batch_id": payload["batch"]["batch_id"], "status": "submitted"}])

        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_ids[0])
        self.assertIsNotNone(relation)
        self.assertEqual(relation["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(relation["row_ids"], [row_ids[0]])

    def test_selected_row_submit_rejects_cross_bank_selection(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fees-cross-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                },
                {
                    "account_no": "95599001",
                    "account_name": "云南溯源科技有限公司工商银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:30:00",
                    "counterparty_name": "工商银行",
                    "debit_amount": "9.90",
                    "credit_amount": "",
                    "summary": "网银手续费",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"} for row_id in row_ids],
            actor="tester",
        )
        version = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))["version"]
        app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({"expected_version": version, "selected_tag_codes": ["fee"]}),
            headers={"Content-Type": "application/json"},
        )

        response = app.handle_request(
            "POST",
            "/api/no-oa-bank-batches/submit-selection",
            body=json.dumps({"transaction_ids": row_ids}),
            headers={"Content-Type": "application/json"},
        )
        payload = _json(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "no_oa_bank_batch_selection_cross_bank")


if __name__ == "__main__":
    unittest.main()
