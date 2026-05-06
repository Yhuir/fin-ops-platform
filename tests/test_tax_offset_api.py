import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.oa_adapter import InMemoryOAAdapter, OAApplicationRecord
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService
from tests.mock_import_files import CERTIFIED_JAN, MockImportFile


def build_multipart_payload(
    *,
    imported_by: str,
    files: list[MockImportFile],
) -> tuple[bytes, dict[str, str]]:
    boundary = "----finops-tax-certified-boundary"
    chunks: list[bytes] = []

    def add_text(name: str, value: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    def add_file(name: str, file: MockImportFile) -> None:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{file.name}"\r\n'
                "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(file.content)
        chunks.append(b"\r\n")

    add_text("imported_by", imported_by)
    for file in files:
        add_file("files", file)
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def tax_offset_payload(month: str = "2026-05", *, output_count: int = 1, input_count: int = 1, certified_count: int = 0) -> dict[str, object]:
    return {
        "month": month,
        "summary": {
            "output_tax": "0.00",
            "input_tax": "0.00",
            "planned_input_tax": "0.00",
            "certified_input_tax": "0.00",
            "deductible_tax": "0.00",
            "result_label": "本月留抵税额",
            "result_amount": "0.00",
        },
        "output_items": [{"id": f"output-{index}"} for index in range(output_count)],
        "input_plan_items": [{"id": f"input-{index}"} for index in range(input_count)],
        "certified_items": [{"id": f"certified-{index}"} for index in range(certified_count)],
        "certified_matched_rows": [],
        "certified_outside_plan_rows": [],
        "locked_certified_input_ids": [],
        "default_selected_output_ids": [],
        "default_selected_input_ids": [],
    }


class TaxOffsetApiTests(unittest.TestCase):
    def test_tax_offset_cache_hit_does_not_rebuild_month_payload(self) -> None:
        app = build_application()
        cached_payload = tax_offset_payload("2026-05", output_count=2, input_count=3, certified_count=1)
        app._tax_offset_read_model_service.upsert_read_model("2026-05", cached_payload)

        with (
            patch.object(
                app._tax_api_routes,
                "get_tax_offset",
                side_effect=AssertionError("should not rebuild cached tax offset payload"),
            ),
            patch("builtins.print") as print_mock,
        ):
            response = app.handle_request("GET", "/api/tax-offset?month=2026-05")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["output_items"], cached_payload["output_items"])
        metric_payloads = [
            json.loads(call.args[0])
            for call in print_mock.call_args_list
            if call.args and json.loads(call.args[0]).get("kind") == "tax_offset_month_metric"
        ]
        self.assertEqual(len(metric_payloads), 1)
        self.assertTrue(metric_payloads[0]["cache_hit"])
        self.assertEqual(metric_payloads[0]["output_count"], 2)
        self.assertEqual(metric_payloads[0]["input_plan_count"], 3)
        self.assertEqual(metric_payloads[0]["certified_count"], 1)

    def test_tax_offset_cache_miss_writes_read_model_and_logs_hit_metrics(self) -> None:
        app = build_application()
        calls: list[str] = []

        def build_tax_offset(month: str) -> dict[str, object]:
            calls.append(month)
            return tax_offset_payload(month, output_count=1, input_count=2, certified_count=0)

        app._tax_api_routes = SimpleNamespace(get_tax_offset=build_tax_offset)

        with patch("builtins.print") as print_mock:
            first_response = app.handle_request("GET", "/api/tax-offset?month=2026-05")
            second_response = app.handle_request("GET", "/api/tax-offset?month=2026-05")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(calls, ["2026-05"])
        self.assertEqual(json.loads(second_response.body)["input_plan_items"], [{"id": "input-0"}, {"id": "input-1"}])
        metric_payloads = [
            json.loads(call.args[0])
            for call in print_mock.call_args_list
            if call.args and json.loads(call.args[0]).get("kind") == "tax_offset_month_metric"
        ]
        self.assertEqual([payload["cache_hit"] for payload in metric_payloads], [False, True])

    def test_tax_offset_calculate_logs_structured_metric(self) -> None:
        app = build_application()
        app._tax_api_routes = SimpleNamespace(calculate=lambda payload: {"summary": {"result_amount": "0.00"}})

        with patch("builtins.print") as print_mock:
            response = app.handle_request(
                "POST",
                "/api/tax-offset/calculate",
                json.dumps(
                    {
                        "month": "2026-05",
                        "selected_output_ids": ["output-1"],
                        "selected_input_ids": ["input-1", "input-2"],
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        metric_payloads = [
            json.loads(call.args[0])
            for call in print_mock.call_args_list
            if call.args and json.loads(call.args[0]).get("kind") == "tax_offset_calculate_metric"
        ]
        self.assertEqual(len(metric_payloads), 1)
        self.assertEqual(metric_payloads[0]["metric"], "tax_offset.calculate.duration_ms")
        self.assertEqual(metric_payloads[0]["month"], "2026-05")
        self.assertEqual(metric_payloads[0]["selected_output_count"], 1)
        self.assertEqual(metric_payloads[0]["selected_input_count"], 2)

    def test_tax_offset_cache_warmup_is_optional_and_environment_gated(self) -> None:
        app = build_application()
        job = SimpleNamespace(job_id="tax-offset-warmup-job-1", owner_user_id="system")

        with (
            patch.object(
                app._background_job_service,
                "create_or_get_idempotent_job_with_created",
                return_value=(job, True),
            ) as create_job,
            patch.object(app._background_job_service, "run_job") as run_job,
        ):
            app._schedule_tax_offset_cache_warmup(["2026-05"], reason="test_disabled")

        create_job.assert_not_called()
        run_job.assert_not_called()

        with (
            patch.dict("os.environ", {"FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED": "1"}),
            patch.object(
                app._background_job_service,
                "create_or_get_idempotent_job_with_created",
                return_value=(job, True),
            ) as create_job,
            patch.object(app._background_job_service, "run_job") as run_job,
        ):
            app._schedule_tax_offset_cache_warmup(["2026-05"], reason="test_enabled")

        create_job.assert_called_once()
        self.assertEqual(create_job.call_args.kwargs["job_type"], "tax_offset_cache_warmup")
        self.assertIn("2026-05", create_job.call_args.kwargs["idempotency_key"])
        run_job.assert_called_once()

    def test_tax_certified_confirm_invalidates_tax_offset_month_cache(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            preview_body, preview_headers = build_multipart_payload(
                imported_by="user_finance_01",
                files=[CERTIFIED_JAN],
            )
            preview_response = app.handle_request(
                "POST",
                "/api/tax-offset/certified-import/preview",
                body=preview_body,
                headers=preview_headers,
            )
            preview_payload = json.loads(preview_response.body)

            with patch.object(app, "_invalidate_tax_offset_read_model_scopes") as invalidate:
                confirm_response = app.handle_request(
                    "POST",
                    "/api/tax-offset/certified-import/confirm",
                    json.dumps({"session_id": preview_payload["session"]["id"]}),
                )

        self.assertEqual(confirm_response.status_code, 200)
        invalidate.assert_called_once_with(["2026-01"], reason="tax_certified_import_confirm")

    def test_invoice_import_confirm_invalidates_tax_offset_month_cache(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="input-invoices.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "255020000001",
                    "invoice_no": "45098656",
                    "counterparty_name": "重庆高新技术产业开发区国家税务局",
                    "seller_name": "重庆高新技术产业开发区国家税务局",
                    "invoice_date": "2026-05-02",
                    "amount": "6000.00",
                    "tax_amount": "180.00",
                }
            ],
        )

        with patch.object(app, "_invalidate_tax_offset_read_model_scopes") as invalidate:
            response = app.handle_request(
                "POST",
                "/imports/confirm",
                json.dumps({"batch_id": preview.id}),
            )

        self.assertEqual(response.status_code, 200)
        invalidate.assert_called_once_with(["2026-05"], reason="invoice_import_confirm")

    def test_bank_import_confirm_does_not_invalidate_tax_offset_cache(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "6222000000008106",
                    "txn_date": "2026-05-02",
                    "counterparty_name": "云南溯源科技有限公司",
                    "credit_amount": "88.00",
                    "debit_amount": "",
                    "balance": "88.00",
                }
            ],
        )

        with patch.object(app, "_invalidate_tax_offset_read_model_scopes") as invalidate:
            response = app.handle_request(
                "POST",
                "/imports/confirm",
                json.dumps({"batch_id": preview.id}),
            )

        self.assertEqual(response.status_code, 200)
        invalidate.assert_called_once_with([], reason="invoice_import_confirm")

    def test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month(self) -> None:
        app = build_application()
        target_oa_record = OAApplicationRecord(
            id="oa-tax-202602-001",
            month="2026-02",
            section="open",
            case_id=None,
            applicant="周洁莹",
            project_name="云南溯源科技",
            apply_type="日常报销",
            amount="600.00",
            counterparty_name="云南城建物业运营集团",
            reason="物业费",
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            detail_fields={"OA单号": "OA-TAX-001", "申请日期": "2026-02-09"},
            attachment_invoices=[
                {
                    "invoice_code": "",
                    "invoice_no": "26532000000021026521",
                    "seller_name": "云南城建物业运营集团",
                    "seller_tax_no": "91530103MA6KHJWK8C",
                    "buyer_name": "云南溯源科技有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "issue_date": "2026-01-06",
                    "amount": "600.00",
                    "tax_rate": "6%",
                    "tax_amount": "33.96",
                    "total_with_tax": "600.00",
                    "invoice_type": "进项发票",
                    "attachment_name": "物业费.pdf",
                }
            ],
        )
        app._workbench_query_service = WorkbenchQueryService(
            oa_adapter=InMemoryOAAdapter({"2026-02": [target_oa_record]})
        )

        response = app.handle_request("GET", "/api/tax-offset?month=2026-01")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        matched_items = [
            item
            for item in payload["input_plan_items"]
            if item["invoice_no"] == "26532000000021026521"
        ]
        self.assertEqual(len(matched_items), 1)
        self.assertEqual(matched_items[0]["seller_name"], "云南城建物业运营集团")
        self.assertEqual(matched_items[0]["tax_amount"], "33.96")
        self.assertEqual(matched_items[0]["total_with_tax"], "600.00")
        self.assertIn(matched_items[0]["id"], payload["default_selected_input_ids"])

    def test_tax_offset_uses_real_imported_input_invoices_as_plan_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            preview = app._import_service.preview_import(
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
            app._import_service.confirm_import(preview.id)

            response = app.handle_request("GET", "/api/tax-offset?month=2026-01")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["input_plan_items"]), 1)
        self.assertEqual(payload["input_plan_items"][0]["invoice_no"], "25502000000145098656")
        self.assertEqual(payload["input_plan_items"][0]["digital_invoice_no"], "25502000000145098656")
        self.assertEqual(payload["input_plan_items"][0]["invoice_type"], "进项普票")
        self.assertEqual(payload["input_plan_items"][0]["tax_rate"], "3%")
        self.assertEqual(payload["default_selected_input_ids"], [payload["input_plan_items"][0]["id"]])

    def test_certified_import_preview_confirm_and_month_list_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            preview_body, preview_headers = build_multipart_payload(
                imported_by="user_finance_01",
                files=[CERTIFIED_JAN],
            )

            preview_response = app.handle_request(
                "POST",
                "/api/tax-offset/certified-import/preview",
                body=preview_body,
                headers=preview_headers,
            )
            self.assertEqual(preview_response.status_code, 200)
            preview_payload = json.loads(preview_response.body)
            self.assertEqual(preview_payload["session"]["file_count"], 1)
            self.assertEqual(preview_payload["files"][0]["month"], "2026-01")
            self.assertEqual(preview_payload["files"][0]["recognized_count"], 2)
            self.assertEqual(preview_payload["files"][0]["matched_plan_count"], 0)
            self.assertEqual(preview_payload["files"][0]["outside_plan_count"], 2)
            self.assertEqual(preview_payload["summary"]["recognized_count"], 2)
            self.assertEqual(preview_payload["summary"]["matched_plan_count"], 0)
            self.assertEqual(preview_payload["summary"]["outside_plan_count"], 2)

            with patch.object(app, "_schedule_tax_offset_cache_warmup"):
                confirm_response = app.handle_request(
                    "POST",
                    "/api/tax-offset/certified-import/confirm",
                    json.dumps({"session_id": preview_payload["session"]["id"]}),
                )
            self.assertEqual(confirm_response.status_code, 200)
            confirm_payload = json.loads(confirm_response.body)
            self.assertEqual(confirm_payload["batch"]["months"], ["2026-01"])
            self.assertEqual(confirm_payload["batch"]["persisted_record_count"], 2)

            list_response = app.handle_request("GET", "/api/tax-offset/certified-imports?month=2026-01")
            self.assertEqual(list_response.status_code, 200)
            list_payload = json.loads(list_response.body)
            self.assertEqual(list_payload["month"], "2026-01")
            self.assertEqual(len(list_payload["records"]), 2)
            self.assertEqual(list_payload["records"][0]["selection_status"], "已勾选")

            month_payload_response = app.handle_request("GET", "/api/tax-offset?month=2026-01")
            self.assertEqual(month_payload_response.status_code, 200)
            month_payload = json.loads(month_payload_response.body)
            self.assertEqual(len(month_payload["certified_items"]), 2)
            self.assertEqual(len(month_payload["certified_matched_rows"]), 0)
            self.assertEqual(len(month_payload["certified_outside_plan_rows"]), 2)
            self.assertEqual(month_payload["locked_certified_input_ids"], [])
            self.assertEqual(month_payload["summary"]["certified_input_tax"], "250.75")

    def test_get_tax_offset_returns_month_rows_without_hardcoded_certified_items_by_default(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/tax-offset?month=2026-03")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)

        self.assertEqual(payload["month"], "2026-03")
        self.assertEqual(len(payload["output_items"]), 0)
        self.assertEqual(len(payload["input_plan_items"]), 0)
        self.assertEqual(len(payload["certified_items"]), 0)
        self.assertIn("certified_matched_rows", payload)
        self.assertIn("certified_outside_plan_rows", payload)
        self.assertEqual(len(payload["certified_outside_plan_rows"]), 0)
        self.assertEqual(payload["locked_certified_input_ids"], [])
        self.assertEqual(payload["default_selected_output_ids"], [])
        self.assertEqual(payload["default_selected_input_ids"], [])
        self.assertEqual(payload["summary"]["certified_input_tax"], "0.00")
        self.assertEqual(payload["summary"]["output_tax"], "0.00")

    def test_calculate_tax_offset_uses_zero_certified_input_when_no_real_import_exists(self) -> None:
        app = build_application()

        response = app.handle_request(
            "POST",
            "/api/tax-offset/calculate",
            json.dumps(
                {
                    "month": "2026-03",
                    "selected_output_ids": [],
                    "selected_input_ids": [],
                }
            ),
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)

        self.assertEqual(payload["summary"]["output_tax"], "0.00")
        self.assertEqual(payload["summary"]["input_tax"], "0.00")
        self.assertEqual(payload["summary"]["planned_input_tax"], "0.00")
        self.assertEqual(payload["summary"]["certified_input_tax"], "0.00")
        self.assertEqual(payload["summary"]["deductible_tax"], "0.00")
        self.assertEqual(payload["summary"]["result_label"], "本月留抵税额")
        self.assertEqual(payload["summary"]["result_amount"], "0.00")


if __name__ == "__main__":
    unittest.main()
