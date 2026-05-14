import json
import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService


def flatten_groups(groups: list[dict[str, object]], row_type: str) -> list[dict[str, object]]:
    return [
        row
        for group in groups
        for row in group[f"{row_type}_rows"]
    ]


class NoOaBankBatchWorkbenchIntegrationTests(unittest.TestCase):
    def test_salary_auto_candidate_does_not_create_active_relation_before_batch_submit(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
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
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        salary_row_id = app._import_service.list_transactions()[0].id

        response = app.handle_request("GET", "/api/workbench?month=all")
        payload = json.loads(response.body)
        auto_results = app._live_workbench_service.list_auto_pair_candidates("all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual([row["id"] for row in flatten_groups(payload["open"]["groups"], "bank")], [salary_row_id])
        self.assertEqual(len(auto_results), 1)
        self.assertEqual(auto_results[0].rule_code, "salary_personal_auto_match")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id(salary_row_id))

    def test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
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
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        salary_row_id = app._import_service.list_transactions()[0].id
        bank_rows = app._live_workbench_service.get_workbench("all")["open"]["bank"]
        service = NoOaBankBatchService(pair_relation_service=app._workbench_pair_relation_service)
        batch = service.build_batches(
            bank_rows,
            {salary_row_id: {"category_code": "salary", "source": "auto"}},
            [],
            {},
        )[0]

        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="确认工资")
        app._invalidate_workbench_read_models()
        paired_response = app.handle_request("GET", "/api/workbench?month=all")
        paired_payload = json.loads(paired_response.body)
        paired_row = flatten_groups(paired_payload["paired"]["groups"], "bank")[0]

        self.assertEqual(paired_payload["summary"]["paired_count"], 1)
        self.assertEqual(paired_row["id"], salary_row_id)
        self.assertEqual(paired_row["invoice_relation"]["code"], "no_oa_bank_batch")
        self.assertEqual(paired_row["invoice_relation"]["label"], "已匹配：工资")
        self.assertEqual(paired_row["special_metadata"]["source_batch_id"], submitted["batch_id"])
        self.assertIn("免OA", paired_row["tags"])
        self.assertIn("工资", paired_row["tags"])

        service.withdraw_batch(submitted["batch_id"], actor="finance-user", expected_version=2, reason="误提交")
        app._invalidate_workbench_read_models()
        open_response = app.handle_request("GET", "/api/workbench?month=all")
        open_payload = json.loads(open_response.body)

        self.assertEqual(open_payload["summary"]["paired_count"], 0)
        self.assertEqual([row["id"] for row in flatten_groups(open_payload["open"]["groups"], "bank")], [salary_row_id])

    def test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
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
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        bank_rows = app._live_workbench_service.get_workbench("all")["open"]["bank"]
        service = NoOaBankBatchService(pair_relation_service=app._workbench_pair_relation_service)
        batch = service.build_batches(
            bank_rows,
            {row_id: {"category_code": "internal_transfer", "source": "auto"} for row_id in row_ids},
            [],
            {},
        )[0]

        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="确认内部往来")
        app._invalidate_workbench_read_models()
        paired_payload = json.loads(app.handle_request("GET", "/api/workbench?month=all").body)
        paired_group = paired_payload["paired"]["groups"][0]

        self.assertEqual(paired_payload["summary"]["paired_count"], 1)
        self.assertEqual(paired_group["relation_mode"], "no_oa_bank_batch")
        self.assertCountEqual([row["id"] for row in paired_group["bank_rows"]], row_ids)
        self.assertTrue(all(row["invoice_relation"]["label"] == "已匹配：内部往来款" for row in paired_group["bank_rows"]))

        service.withdraw_batch(submitted["batch_id"], actor="finance-user", expected_version=2, reason="误提交")
        app._invalidate_workbench_read_models()
        open_payload = json.loads(app.handle_request("GET", "/api/workbench?month=all").body)

        self.assertEqual(open_payload["summary"]["paired_count"], 0)
        self.assertCountEqual([row["id"] for row in flatten_groups(open_payload["open"]["groups"], "bank")], row_ids)

    def test_historical_salary_and_internal_transfer_relations_still_display(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="historical-special-relations.xlsx",
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
        app._import_service.confirm_import(preview.id)
        salary_row_id, *transfer_row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._workbench_pair_relation_service.create_active_relation(
            case_id="salary_auto_history",
            row_ids=[salary_row_id],
            row_types=["bank"],
            relation_mode="salary_personal_auto_match",
            created_by="system_auto_match",
            month_scope="2026-02",
        )
        app._workbench_pair_relation_service.create_active_relation(
            case_id="internal_transfer_history",
            row_ids=transfer_row_ids,
            row_types=["bank", "bank"],
            relation_mode="internal_transfer_pair",
            created_by="system_auto_match",
            month_scope="2026-02",
        )

        payload = json.loads(app.handle_request("GET", "/api/workbench?month=all").body)
        paired_rows = flatten_groups(payload["paired"]["groups"], "bank")
        rows_by_id = {row["id"]: row for row in paired_rows}

        self.assertEqual(payload["summary"]["paired_count"], 2)
        self.assertEqual(rows_by_id[salary_row_id]["invoice_relation"]["label"], "已匹配：工资")
        self.assertTrue(all(rows_by_id[row_id]["invoice_relation"]["label"] == "已匹配：内部往来款" for row_id in transfer_row_ids))


if __name__ == "__main__":
    unittest.main()
