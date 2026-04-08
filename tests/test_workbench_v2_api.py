import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from fin_ops_platform.app.server import Application, build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService


class WorkbenchV2ApiTests(unittest.TestCase):
    def test_get_api_workbench_prefers_cached_read_model_when_available(self) -> None:
        app = build_application()
        cached_payload = {
            "month": "2026-03",
            "summary": {
                "oa_count": 99,
                "bank_count": 88,
                "invoice_count": 77,
                "paired_count": 1,
                "open_count": 0,
                "exception_count": 0,
            },
            "paired": {
                "groups": [
                    {
                        "group_id": "case:CACHE-202603-001",
                        "oa_rows": [{"id": "oa-cached-001", "type": "oa"}],
                        "bank_rows": [],
                        "invoice_rows": [],
                    }
                ]
            },
            "open": {"groups": []},
        }
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload=cached_payload,
            generated_at="2026-04-08T11:00:00+00:00",
        )

        with patch.object(app, "_build_raw_workbench_payload", side_effect=AssertionError("should not rebuild raw payload")):
            response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["summary"]["oa_count"], 99)
        self.assertEqual(payload["paired"]["groups"][0]["oa_rows"][0]["id"], "oa-cached-001")

    def test_get_api_workbench_persists_salary_auto_match_into_pair_relations(self) -> None:
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

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(flatten_groups(payload["paired"]["groups"], "bank")[0]["invoice_relation"]["label"], "已匹配：工资")
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(salary_row_id)
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "salary_personal_auto_match")
        self.assertEqual(relation["row_ids"], [salary_row_id])

    def test_get_api_workbench_persists_internal_transfer_auto_match_into_pair_relations(self) -> None:
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
        internal_transfer_row_ids = [transaction.id for transaction in app._import_service.list_transactions()]

        response = app.handle_request("GET", "/api/workbench?month=all")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 1)
        paired_bank_rows = flatten_groups(payload["paired"]["groups"], "bank")
        self.assertCountEqual([row["id"] for row in paired_bank_rows], internal_transfer_row_ids)
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(internal_transfer_row_ids[0])
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "internal_transfer_pair")
        self.assertCountEqual(relation["row_ids"], internal_transfer_row_ids)

    def test_get_api_workbench_ignored_prefers_cached_read_model_when_available(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="all",
            payload={
                "month": "all",
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": []},
            },
            ignored_rows=[
                {
                    "id": "bk-ignored-001",
                    "type": "bank",
                    "counterparty_name": "测试忽略流水",
                }
            ],
            generated_at="2026-04-08T12:00:00+00:00",
        )

        with patch.object(app, "_build_raw_workbench_payload", side_effect=AssertionError("should not rebuild raw payload")):
            response = app.handle_request("GET", "/api/workbench/ignored?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["month"], "all")
        self.assertEqual(payload["rows"][0]["id"], "bk-ignored-001")

    def test_merge_live_workbench_keeps_oa_rows_when_live_bank_invoice_exist(self) -> None:
        live_payload = {
            "month": "2026-03",
            "summary": {
                "oa_count": 0,
                "bank_count": 1,
                "invoice_count": 1,
                "paired_count": 0,
                "open_count": 2,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [],
                "bank": [
                    {
                        "id": "bk-live-001",
                        "type": "bank",
                        "case_id": "match_result_001",
                        "credit_amount": "120.00",
                        "counterparty_name": "云上客户",
                        "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                    }
                ],
                "invoice": [
                    {
                        "id": "iv-live-001",
                        "type": "invoice",
                        "case_id": "match_result_001",
                        "amount": "120.00",
                        "invoice_type": "销项发票",
                        "buyer_name": "云上客户",
                        "invoice_bank_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                    }
                ],
            },
        }
        oa_payload = WorkbenchQueryService().get_workbench("2026-03")

        merged = Application._merge_live_workbench_with_oa(live_payload, oa_payload)

        self.assertGreater(merged["summary"]["oa_count"], 0)
        self.assertGreaterEqual(len(merged["open"]["groups"]), 1)
        self.assertTrue(any(group["oa_rows"] for group in merged["open"]["groups"]))
        self.assertEqual(merged["summary"]["bank_count"], 1)
        self.assertEqual(merged["summary"]["invoice_count"], 1)

    def test_get_api_workbench_supports_two_seed_months(self) -> None:
        app = build_application()

        march_response = app.handle_request("GET", "/api/workbench?month=2026-03")
        self.assertEqual(march_response.status_code, 200)
        march_payload = json.loads(march_response.body)
        self.assertEqual(march_payload["month"], "2026-03")
        self.assertGreater(march_payload["summary"]["oa_count"], 0)
        self.assertGreater(len(all_groups(march_payload)), 0)
        self.assertTrue(any(group["oa_rows"] for group in all_groups(march_payload)))
        self.assertTrue(any(group["bank_rows"] for group in all_groups(march_payload)))
        self.assertTrue(any(group["invoice_rows"] for group in all_groups(march_payload)))

        april_response = app.handle_request("GET", "/api/workbench?month=2026-04")
        self.assertEqual(april_response.status_code, 200)
        april_payload = json.loads(april_response.body)
        self.assertEqual(april_payload["month"], "2026-04")
        self.assertNotEqual(
            flatten_groups(all_groups(march_payload), "oa")[0]["id"],
            flatten_groups(all_groups(april_payload), "oa")[0]["id"],
        )

    def test_get_api_workbench_supports_all_time_view(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/workbench?month=all")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)

        self.assertEqual(payload["month"], "all")
        oa_ids = [row["id"] for row in flatten_groups(all_groups(payload), "oa")]
        self.assertIn("oa-o-202603-001", oa_ids)
        self.assertIn("oa-o-202604-001", oa_ids)
        self.assertGreaterEqual(payload["summary"]["oa_count"], 5)

    def test_get_api_workbench_row_detail_supports_oa_bank_and_invoice(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row_id = flatten_groups(payload["open"]["groups"], "oa")[0]["id"]
        bank_row_id = flatten_groups(payload["open"]["groups"], "bank")[0]["id"]
        invoice_row_id = flatten_groups(payload["open"]["groups"], "invoice")[0]["id"]

        oa_detail = json.loads(app.handle_request("GET", f"/api/workbench/rows/{oa_row_id}").body)["row"]
        bank_detail = json.loads(app.handle_request("GET", f"/api/workbench/rows/{bank_row_id}").body)["row"]
        invoice_detail = json.loads(app.handle_request("GET", f"/api/workbench/rows/{invoice_row_id}").body)["row"]

        self.assertEqual(oa_detail["type"], "oa")
        self.assertIn("申请人", oa_detail["summary_fields"])
        self.assertIn("OA单号", oa_detail["detail_fields"])

        self.assertEqual(bank_detail["type"], "bank")
        self.assertIn("交易时间", bank_detail["summary_fields"])
        self.assertIn("账号", bank_detail["detail_fields"])

        self.assertEqual(invoice_detail["type"], "invoice")
        self.assertIn("购买方名称", invoice_detail["summary_fields"])
        self.assertIn("发票号码", invoice_detail["detail_fields"])

    def test_api_workbench_actions_return_unified_result_structure(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-API-202603-001",
                }
            ),
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertTrue(confirm_payload["success"])
        self.assertEqual(confirm_payload["action"], "confirm_link")
        self.assertCountEqual(
            confirm_payload["affected_row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )
        self.assertNotIn("updated_rows", confirm_payload)

        updated_workbench = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertIn(oa_row["id"], [row["id"] for row in flatten_groups(updated_workbench["paired"]["groups"], "oa")])
        self.assertIn(bank_row["id"], [row["id"] for row in flatten_groups(updated_workbench["paired"]["groups"], "bank")])
        self.assertIn(invoice_row["id"], [row["id"] for row in flatten_groups(updated_workbench["paired"]["groups"], "invoice")])

        cancel_response = app.handle_request(
            "POST",
            "/api/workbench/actions/cancel-link",
            json.dumps({"month": "2026-03", "row_id": bank_row["id"], "comment": "reopen for review"}),
        )
        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertTrue(cancel_payload["success"])
        self.assertEqual(cancel_payload["action"], "cancel_link")
        self.assertCountEqual(
            cancel_payload["affected_row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )
        self.assertNotIn("updated_rows", cancel_payload)

        app_for_bank_exception = build_application()
        initial_open_for_exception = json.loads(app_for_bank_exception.handle_request("GET", "/api/workbench?month=2026-03").body)
        bank_exception_row = flatten_groups(initial_open_for_exception["open"]["groups"], "bank")[0]
        update_bank_response = app_for_bank_exception.handle_request(
            "POST",
            "/api/workbench/actions/update-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_id": bank_exception_row["id"],
                    "relation_code": "bank_fee",
                    "relation_label": "银行手续费",
                    "comment": "由出纳补录手续费",
                }
            ),
        )
        self.assertEqual(update_bank_response.status_code, 200)
        update_bank_payload = json.loads(update_bank_response.body)
        self.assertTrue(update_bank_payload["success"])
        self.assertEqual(update_bank_payload["action"], "update_bank_exception")

        app_for_mark_exception = build_application()
        initial_open_for_mark = json.loads(app_for_mark_exception.handle_request("GET", "/api/workbench?month=2026-03").body)
        open_invoice_after_confirm = flatten_groups(initial_open_for_mark["open"]["groups"], "invoice")[0]
        mark_response = app_for_mark_exception.handle_request(
            "POST",
            "/api/workbench/actions/mark-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_id": open_invoice_after_confirm["id"],
                    "exception_code": "pending_collection",
                    "comment": "客户尚未付款",
                }
            ),
        )
        self.assertEqual(mark_response.status_code, 200)
        mark_payload = json.loads(mark_response.body)
        self.assertTrue(mark_payload["success"])
        self.assertEqual(mark_payload["action"], "mark_exception")
        self.assertEqual(mark_payload["updated_rows"][0]["id"], open_invoice_after_confirm["id"])

    def test_cancel_link_uses_existing_case_members_without_rebuilding_workbench(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]
        resolved_rows = [
            app._workbench_query_service.serialize_row(app._workbench_query_service.get_row_record(oa_row["id"])),
            app._resolve_live_row_direct(bank_row["id"]),
            app._resolve_live_row_direct(invoice_row["id"]),
        ]
        relation = app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-FAST-CANCEL-001",
            row_ids=[row["id"] for row in resolved_rows],
            row_types=[row["type"] for row in resolved_rows],
            relation_mode="manual_confirmed",
            created_by="YNSYLP005",
            month_scope="2026-03",
        )
        self.assertCountEqual(
            relation["row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )

        with patch.object(app, "_build_api_workbench_payload", side_effect=AssertionError("should not rebuild workbench")):
            cancel_response = app._handle_live_workbench_cancel_link(
                {"month": "2026-03", "row_id": bank_row["id"], "comment": "reopen for review"}
            )

        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertTrue(cancel_payload["success"])
        self.assertCountEqual(
            cancel_payload["affected_row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )
        self.assertNotIn("updated_rows", cancel_payload)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-FAST-CANCEL-001"))

    def test_confirm_link_persists_pair_relation_without_pairing_override(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-PAIR-ONLY-001",
                }
            ),
        )

        self.assertEqual(response.status_code, 200)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-PAIR-ONLY-001")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertCountEqual(relation["row_ids"], [oa_row["id"], bank_row["id"], invoice_row["id"]])
        self.assertIsNone(app._workbench_override_service.case_id_for_row(oa_row["id"]))
        self.assertIsNone(app._workbench_override_service.case_id_for_row(bank_row["id"]))
        self.assertIsNone(app._workbench_override_service.case_id_for_row(invoice_row["id"]))

    def test_confirm_and_cancel_link_invalidate_cached_read_model_for_follow_up_get(self) -> None:
        app = build_application()
        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(initial_payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(initial_payload["open"]["groups"], "invoice")[0]

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-HOT-READMODEL-001",
                }
            ),
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertIsNone(app._workbench_read_model_service.get_read_model("2026-03"))
        confirmed_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        self.assertIn(
            oa_row["id"],
            [row["id"] for row in flatten_groups(confirmed_payload["paired"]["groups"], "oa")],
        )

        cancel_response = app.handle_request(
            "POST",
            "/api/workbench/actions/cancel-link",
            json.dumps({"month": "2026-03", "row_id": bank_row["id"], "comment": "reopen"}),
        )
        self.assertEqual(cancel_response.status_code, 200)
        self.assertIsNone(app._workbench_read_model_service.get_read_model("2026-03"))
        cancelled_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        self.assertIn(
            bank_row["id"],
            [row["id"] for row in flatten_groups(cancelled_payload["open"]["groups"], "bank")],
        )

    def test_import_confirm_invalidates_cached_read_models_for_changed_workbench_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_read_model_service.upsert_read_model(
                scope_key="all",
                payload={
                    "month": "all",
                    "summary": {
                        "oa_count": 999,
                        "bank_count": 999,
                        "invoice_count": 999,
                        "paired_count": 0,
                        "open_count": 0,
                        "exception_count": 0,
                    },
                    "paired": {"groups": []},
                    "open": {"groups": []},
                },
                ignored_rows=[],
            )

            preview = app._import_service.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name="bank-new.xlsx",
                imported_by="user_finance_01",
                rows=[
                    {
                        "account_no": "62220009",
                        "account_name": "云南溯源科技有限公司测试户",
                        "txn_date": "2026-03-21",
                        "trade_time": "2026-03-21 09:00:00",
                        "pay_receive_time": "2026-03-21 09:00:00",
                        "counterparty_name": "测试客户",
                        "debit_amount": "100.00",
                        "credit_amount": "",
                        "summary": "测试导入",
                    }
                ],
            )

            response = app.handle_request(
                "POST",
                "/imports/confirm",
                json.dumps({"batch_id": preview.id}),
            )

            self.assertEqual(response.status_code, 200)
            self.assertIsNone(app._workbench_read_model_service.get_read_model("all"))

    def test_confirm_link_resolves_selected_rows_without_rebuilding_grouped_workbench(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        with patch.object(app, "_build_api_workbench_payload", side_effect=AssertionError("should not rebuild workbench")):
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-FAST-CONFIRM-001",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertTrue(confirm_payload["success"])
        self.assertCountEqual(
            confirm_payload["affected_row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )
        self.assertNotIn("updated_rows", confirm_payload)

    def test_confirm_link_does_not_resolve_source_rows_in_hot_path(self) -> None:
        app = build_application()

        with patch.object(app, "_resolve_live_rows_direct", side_effect=AssertionError("should not resolve source rows")):
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "all",
                    "row_ids": ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
                    "case_id": "CASE-MINIMAL-CONFIRM-001",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertCountEqual(
            confirm_payload["affected_row_ids"],
            ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
        )
        self.assertNotIn("updated_rows", confirm_payload)

    def test_confirm_link_ignores_empty_row_ids_in_minimal_hot_path(self) -> None:
        app = build_application()

        response = app._handle_live_workbench_confirm_link(
            {
                "month": "2026-03",
                "row_ids": ["oa-o-202603-001", None, "  ", "bk-o-202603-001"],
                "case_id": "CASE-NORMALIZE-ROWIDS-001",
            }
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(
            payload["affected_row_ids"],
            ["oa-o-202603-001", "bk-o-202603-001"],
        )

    def test_confirm_and_cancel_link_defer_read_model_persistence_to_background(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist") as schedule_pair_relation_persist,
            patch.object(app, "_schedule_workbench_read_model_persist") as schedule_read_model_persist,
        ):
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-ASYNC-PERSIST-001",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        schedule_pair_relation_persist.assert_called_once()
        self.assertEqual(
            schedule_pair_relation_persist.call_args.kwargs,
            {
                "changed_case_ids": ["CASE-ASYNC-PERSIST-001"],
                "request_id": None,
                "action_name": "confirm_link",
            },
        )
        schedule_read_model_persist.assert_called_once()
        self.assertCountEqual(
            schedule_read_model_persist.call_args.kwargs["changed_scope_keys"],
            ["2026-03", "all"],
        )
        self.assertIsNone(schedule_read_model_persist.call_args.kwargs["request_id"])
        self.assertEqual(schedule_read_model_persist.call_args.kwargs["action_name"], "confirm_link")

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist") as schedule_pair_relation_persist,
            patch.object(app, "_schedule_workbench_read_model_persist") as schedule_read_model_persist,
        ):
            cancel_response = app._handle_live_workbench_cancel_link(
                {
                    "month": "2026-03",
                    "row_id": bank_row["id"],
                    "comment": "reopen",
                }
            )

        self.assertEqual(cancel_response.status_code, 200)
        schedule_pair_relation_persist.assert_called_once()
        self.assertEqual(
            schedule_pair_relation_persist.call_args.kwargs,
            {
                "changed_case_ids": ["CASE-ASYNC-PERSIST-001"],
                "request_id": None,
                "action_name": "cancel_link",
            },
        )
        schedule_read_model_persist.assert_called_once()
        self.assertCountEqual(
            schedule_read_model_persist.call_args.kwargs["changed_scope_keys"],
            ["2026-03", "all"],
        )
        self.assertIsNone(schedule_read_model_persist.call_args.kwargs["request_id"])
        self.assertEqual(schedule_read_model_persist.call_args.kwargs["action_name"], "cancel_link")

    def test_confirm_link_emits_phased_timing_logs(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist"),
            patch.object(app, "_emit_workbench_action_timing") as emit_timing,
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link",
                json.dumps(
                    {
                        "month": "2026-03",
                        "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                        "case_id": "CASE-TIMING-CONFIRM-001",
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        phases = [call.kwargs["phase"] for call in emit_timing.call_args_list]
        self.assertIn("oa_auth", phases)
        self.assertIn("resolve_rows", phases)
        self.assertIn("pair_relation_update", phases)
        self.assertIn("invalidate_read_model_scopes", phases)
        self.assertIn("schedule_background_persist", phases)
        self.assertIn("request_total", phases)

    def test_background_persist_emits_timing_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-TIMING-BG-001",
                row_ids=["oa-o-202603-001", "txn-o-202603-001"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="system",
                month_scope="2026-03",
            )
            payload = app._build_api_workbench_payload("2026-03")
            app._workbench_read_model_service.upsert_read_model(scope_key="2026-03", payload=payload, ignored_rows=[])
            app._workbench_read_model_service.upsert_read_model(scope_key="all", payload=payload, ignored_rows=[])

            app._workbench_pair_relation_persist_version = 1
            app._workbench_read_model_persist_version = 1

            with patch.object(app, "_emit_workbench_action_timing") as emit_timing:
                app._persist_workbench_pair_relations_in_background(
                    version=1,
                    case_ids=["CASE-TIMING-BG-001"],
                    request_id="req-bg-001",
                    action_name="confirm_link",
                )
                app._rebuild_workbench_read_models_in_background(
                    version=1,
                    scope_keys=["2026-03", "all"],
                    request_id="req-bg-001",
                    action_name="confirm_link",
                )

        phases = [call.kwargs["phase"] for call in emit_timing.call_args_list]
        self.assertIn("persist_pair_relations", phases)
        self.assertIn("rebuild_read_model_scope", phases)
        self.assertIn("persist_read_models", phases)
        self.assertIn("background_total", phases)

    def test_confirm_and_cancel_link_rebuild_live_cache_only_once_per_action(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        with patch.object(app._live_workbench_service, "_rebuild_cache", wraps=app._live_workbench_service._rebuild_cache) as rebuild_cache:
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-SINGLE-REBUILD-001",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertLessEqual(rebuild_cache.call_count, 1)

        with patch.object(app._live_workbench_service, "_rebuild_cache", wraps=app._live_workbench_service._rebuild_cache) as rebuild_cache:
            cancel_response = app._handle_live_workbench_cancel_link(
                {
                    "month": "2026-03",
                    "row_id": bank_row["id"],
                    "comment": "reopen",
                }
            )

        self.assertEqual(cancel_response.status_code, 200)
        self.assertLessEqual(rebuild_cache.call_count, 1)

    def test_cancel_link_does_not_resolve_source_rows_in_hot_path(self) -> None:
        app = build_application()
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-MINIMAL-CANCEL-001",
            row_ids=["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="YNSYLP005",
            month_scope="2026-03",
        )

        with patch.object(app, "_resolve_live_rows_direct", side_effect=AssertionError("should not resolve source rows")):
            cancel_response = app._handle_live_workbench_cancel_link(
                {
                    "month": "2026-03",
                    "row_id": "bk-o-202603-001",
                    "comment": "reopen",
                }
            )

        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertCountEqual(
            cancel_payload["affected_row_ids"],
            ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
        )
        self.assertNotIn("updated_rows", cancel_payload)

    def test_confirm_link_rebuilds_live_cache_once_for_multiple_live_rows(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="multi-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220031",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 09:00:00",
                    "pay_receive_time": "2026-03-10 09:00:00",
                    "counterparty_name": "测试对方A",
                    "debit_amount": "100.00",
                    "credit_amount": "",
                    "summary": "测试流水A",
                },
                {
                    "account_no": "62220032",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 09:05:00",
                    "pay_receive_time": "2026-03-10 09:05:00",
                    "counterparty_name": "测试对方B",
                    "debit_amount": "",
                    "credit_amount": "100.00",
                    "summary": "测试流水B",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions() if transaction.source_batch_id == preview.id]

        with patch.object(app._live_workbench_service, "_rebuild_cache", wraps=app._live_workbench_service._rebuild_cache) as rebuild_cache:
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "case_id": "CASE-LIVE-BULK-001",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertLessEqual(rebuild_cache.call_count, 1)

    def test_cancel_exception_returns_processed_rows_to_open_state(self) -> None:
        app = build_application()
        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(initial_payload["open"]["groups"], "bank")[0]

        exception_response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "测试异常处理",
                }
            ),
        )
        self.assertEqual(exception_response.status_code, 200)

        cancel_response = app.handle_request(
            "POST",
            "/api/workbench/actions/cancel-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "comment": "撤回异常处理",
                }
            ),
        )
        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertTrue(cancel_payload["success"])
        self.assertEqual(cancel_payload["action"], "cancel_exception")
        self.assertEqual(cancel_payload["affected_row_ids"], [oa_row["id"], bank_row["id"]])

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        updated_oa = next(row for row in flatten_groups(updated_payload["open"]["groups"], "oa") if row["id"] == oa_row["id"])
        updated_bank = next(row for row in flatten_groups(updated_payload["open"]["groups"], "bank") if row["id"] == bank_row["id"])

        self.assertFalse(updated_oa.get("handled_exception", False))
        self.assertFalse(updated_bank.get("handled_exception", False))
        self.assertEqual(updated_oa["oa_bank_relation"]["tone"], "warn")
        self.assertEqual(updated_bank["invoice_relation"]["tone"], "warn")

    def test_confirm_link_supports_live_workbench_rows(self) -> None:
        app = build_application()
        app._live_workbench_service = _StubLiveWorkbenchService()

        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertTrue(
            any(
                row["id"] == "txn-live-202603-001"
                for row in flatten_groups(initial_payload["open"]["groups"], "bank")
            )
        )

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": ["oa-o-202603-001", "txn-live-202603-001"],
                    "case_id": "CASE-LIVE-202603-001",
                }
            ),
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["action"], "confirm_link")
        self.assertEqual(confirm_payload["affected_row_ids"], ["oa-o-202603-001", "txn-live-202603-001"])

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        paired_oa_ids = [row["id"] for row in flatten_groups(updated_payload["paired"]["groups"], "oa")]
        paired_bank_ids = [row["id"] for row in flatten_groups(updated_payload["paired"]["groups"], "bank")]
        self.assertIn("oa-o-202603-001", paired_oa_ids)
        self.assertIn("txn-live-202603-001", paired_bank_ids)
        paired_group = next(
            group
            for group in updated_payload["paired"]["groups"]
            if any(row["id"] == "txn-live-202603-001" for row in group["bank_rows"])
        )
        self.assertEqual([row["id"] for row in paired_group["oa_rows"]], ["oa-o-202603-001"])
        self.assertEqual([row["id"] for row in paired_group["bank_rows"]], ["txn-live-202603-001"])
        self.assertEqual(paired_group["invoice_rows"], [])

    def test_confirm_link_falls_back_to_underlying_live_row_services_when_group_payload_is_missing_selected_rows(self) -> None:
        app = build_application()
        app._live_workbench_service = _StubLiveWorkbenchService()

        original_build_api_workbench_payload = app._build_api_workbench_payload

        def _build_payload_without_selected_rows(month: str) -> dict[str, object]:
            payload = original_build_api_workbench_payload(month)
            for section in ("paired", "open"):
                for group in payload[section]["groups"]:
                    group["oa_rows"] = [row for row in group["oa_rows"] if row["id"] != "oa-o-202603-001"]
                    group["bank_rows"] = [row for row in group["bank_rows"] if row["id"] != "txn-live-202603-001"]
            return payload

        app._build_api_workbench_payload = _build_payload_without_selected_rows

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": ["oa-o-202603-001", "txn-live-202603-001"],
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["action"], "confirm_link")
        self.assertEqual(confirm_payload["affected_row_ids"], ["oa-o-202603-001", "txn-live-202603-001"])

    def test_ignore_and_unignore_invoice_moves_row_between_open_and_ignored_views(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        ignore_response = app.handle_request(
            "POST",
            "/api/workbench/actions/ignore-row",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_id": invoice_row["id"],
                    "comment": "暂不处理这张票",
                }
            ),
        )
        self.assertEqual(ignore_response.status_code, 200)
        ignore_payload = json.loads(ignore_response.body)
        self.assertTrue(ignore_payload["success"])
        self.assertEqual(ignore_payload["action"], "ignore_row")

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertNotIn(invoice_row["id"], [row["id"] for row in flatten_groups(updated_payload["open"]["groups"], "invoice")])

        ignored_response = app.handle_request("GET", "/api/workbench/ignored?month=2026-03")
        self.assertEqual(ignored_response.status_code, 200)
        ignored_payload = json.loads(ignored_response.body)
        self.assertIn(invoice_row["id"], [row["id"] for row in ignored_payload["rows"]])

        unignore_response = app.handle_request(
            "POST",
            "/api/workbench/actions/unignore-row",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_id": invoice_row["id"],
                }
            ),
        )
        self.assertEqual(unignore_response.status_code, 200)
        unignore_payload = json.loads(unignore_response.body)
        self.assertTrue(unignore_payload["success"])
        self.assertEqual(unignore_payload["action"], "unignore_row")

        restored_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertIn(invoice_row["id"], [row["id"] for row in flatten_groups(restored_payload["open"]["groups"], "invoice")])

    def test_oa_bank_exception_updates_selected_oa_and_bank_rows(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "付款金额与OA金额不一致，继续核查",
                }
            ),
        )

        self.assertEqual(response.status_code, 200)
        response_payload = json.loads(response.body)
        self.assertTrue(response_payload["success"])
        self.assertEqual(response_payload["action"], "oa_bank_exception")
        self.assertEqual(response_payload["affected_row_ids"], [oa_row["id"], bank_row["id"]])

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        updated_oa_row = next(row for row in flatten_groups(updated_payload["open"]["groups"], "oa") if row["id"] == oa_row["id"])
        updated_bank_row = next(row for row in flatten_groups(updated_payload["open"]["groups"], "bank") if row["id"] == bank_row["id"])
        self.assertEqual(updated_oa_row["oa_bank_relation"]["code"], "oa_bank_amount_mismatch")
        self.assertEqual(updated_oa_row["oa_bank_relation"]["label"], "金额不一致，继续异常")
        self.assertEqual(updated_bank_row["invoice_relation"]["code"], "oa_bank_amount_mismatch")
        self.assertEqual(updated_bank_row["invoice_relation"]["label"], "金额不一致，继续异常")

    def test_oa_bank_exception_rejects_invoice_rows(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [bank_row["id"], invoice_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                }
            ),
        )

        self.assertEqual(response.status_code, 400)
        response_payload = json.loads(response.body)
        self.assertEqual(response_payload["error"], "invalid_oa_bank_exception_request")

    def test_confirm_link_supports_cross_month_selection_in_all_time_view(self) -> None:
        app = build_application()

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "all",
                    "row_ids": ["oa-o-202603-001", "bk-o-202604-001"],
                    "case_id": "CASE-CROSS-MONTH-001",
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["action"], "confirm_link")
        self.assertEqual(confirm_payload["month"], "all")
        self.assertEqual(confirm_payload["affected_row_ids"], ["oa-o-202603-001", "bk-o-202604-001"])


if __name__ == "__main__":
    unittest.main()


def flatten_groups(groups: list[dict[str, object]], record_type: str) -> list[dict[str, object]]:
    key = f"{record_type}_rows"
    flattened: list[dict[str, object]] = []
    for group in groups:
        flattened.extend(group[key])
    return flattened


def all_groups(payload: dict[str, object]) -> list[dict[str, object]]:
    return [*payload["paired"]["groups"], *payload["open"]["groups"]]


class _StubLiveWorkbenchService:
    def has_rows_for_month(self, month: str) -> bool:
        return month == "2026-03"

    def get_workbench(self, month: str) -> dict[str, object]:
        if month != "2026-03":
            return {
                "month": month,
                "summary": {"oa_count": 0, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 0, "exception_count": 0},
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {"oa": [], "bank": [], "invoice": []},
            }
        return {
            "month": "2026-03",
            "summary": {"oa_count": 0, "bank_count": 1, "invoice_count": 0, "paired_count": 0, "open_count": 1, "exception_count": 0},
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [],
                "bank": [
                    {
                        "id": "txn-live-202603-001",
                        "type": "bank",
                        "case_id": "CASE-LIVE-202603-001",
                        "trade_time": "2026-03-28 11:20:00",
                        "debit_amount": "58,000.00",
                        "credit_amount": "",
                        "counterparty_name": "智能工厂设备商",
                        "payment_account_label": "工商银行 账户 8888",
                        "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                        "pay_receive_time": "2026-03-28 11:20:00",
                        "remark": "设备尾款待支付",
                        "repayment_date": "",
                        "available_actions": ["detail"],
                    }
                ],
                "invoice": [],
            },
        }

    def get_row_detail(self, row_id: str) -> dict[str, object]:
        if row_id != "txn-live-202603-001":
            raise KeyError(row_id)
        return {
            "id": "txn-live-202603-001",
            "type": "bank",
            "case_id": "CASE-LIVE-202603-001",
            "trade_time": "2026-03-28 11:20:00",
            "debit_amount": "58,000.00",
            "credit_amount": "",
            "counterparty_name": "智能工厂设备商",
            "payment_account_label": "工商银行 账户 8888",
            "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
            "pay_receive_time": "2026-03-28 11:20:00",
            "remark": "设备尾款待支付",
            "repayment_date": "",
            "available_actions": ["detail"],
            "summary_fields": {"和发票关联情况": "待人工确认", "备注": "设备尾款待支付"},
            "detail_fields": {"备注": "设备尾款待支付"},
        }
