import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType


ROOT = Path(__file__).resolve().parents[1]
CERTIFIED_JAN = ROOT / "测试数据" / "2026年1月 进项认证结果  用途确认信息.xlsx"


def build_multipart_payload(
    *,
    imported_by: str,
    file_paths: list[Path],
) -> tuple[bytes, dict[str, str]]:
    boundary = "----finops-tax-certified-boundary"
    chunks: list[bytes] = []

    def add_text(name: str, value: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    def add_file(name: str, path: Path) -> None:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
                "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")

    add_text("imported_by", imported_by)
    for file_path in file_paths:
        add_file("files", file_path)
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


class TaxOffsetApiTests(unittest.TestCase):
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
                file_paths=[CERTIFIED_JAN],
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
            self.assertEqual(preview_payload["files"][0]["recognized_count"], 60)
            self.assertEqual(preview_payload["files"][0]["matched_plan_count"], 0)
            self.assertEqual(preview_payload["files"][0]["outside_plan_count"], 60)
            self.assertEqual(preview_payload["summary"]["recognized_count"], 60)
            self.assertEqual(preview_payload["summary"]["matched_plan_count"], 0)
            self.assertEqual(preview_payload["summary"]["outside_plan_count"], 60)

            confirm_response = app.handle_request(
                "POST",
                "/api/tax-offset/certified-import/confirm",
                json.dumps({"session_id": preview_payload["session"]["id"]}),
            )
            self.assertEqual(confirm_response.status_code, 200)
            confirm_payload = json.loads(confirm_response.body)
            self.assertEqual(confirm_payload["batch"]["months"], ["2026-01"])
            self.assertEqual(confirm_payload["batch"]["persisted_record_count"], 60)

            list_response = app.handle_request("GET", "/api/tax-offset/certified-imports?month=2026-01")
            self.assertEqual(list_response.status_code, 200)
            list_payload = json.loads(list_response.body)
            self.assertEqual(list_payload["month"], "2026-01")
            self.assertEqual(len(list_payload["records"]), 60)
            self.assertEqual(list_payload["records"][0]["selection_status"], "已勾选")

            month_payload_response = app.handle_request("GET", "/api/tax-offset?month=2026-01")
            self.assertEqual(month_payload_response.status_code, 200)
            month_payload = json.loads(month_payload_response.body)
            self.assertEqual(len(month_payload["certified_items"]), 60)
            self.assertEqual(len(month_payload["certified_matched_rows"]), 0)
            self.assertEqual(len(month_payload["certified_outside_plan_rows"]), 60)
            self.assertEqual(month_payload["locked_certified_input_ids"], [])
            self.assertEqual(month_payload["summary"]["certified_input_tax"], "4,855.00")

    def test_get_tax_offset_returns_month_rows_without_hardcoded_certified_items_by_default(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/tax-offset?month=2026-03")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)

        self.assertEqual(payload["month"], "2026-03")
        self.assertGreater(len(payload["output_items"]), 0)
        self.assertGreater(len(payload["input_plan_items"]), 0)
        self.assertEqual(len(payload["certified_items"]), 0)
        self.assertIn("certified_matched_rows", payload)
        self.assertIn("certified_outside_plan_rows", payload)
        self.assertEqual(len(payload["certified_outside_plan_rows"]), 0)
        self.assertEqual(payload["locked_certified_input_ids"], [])
        self.assertEqual(payload["default_selected_output_ids"], [item["id"] for item in payload["output_items"]])
        self.assertEqual(payload["default_selected_input_ids"], ["ti-202603-001", "ti-202603-002"])
        self.assertEqual(payload["summary"]["certified_input_tax"], "0.00")
        self.assertEqual(payload["output_items"][0]["tax_rate"], "13%")

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

        self.assertEqual(payload["summary"]["output_tax"], "41,600.00")
        self.assertEqual(payload["summary"]["input_tax"], "0.00")
        self.assertEqual(payload["summary"]["planned_input_tax"], "0.00")
        self.assertEqual(payload["summary"]["certified_input_tax"], "0.00")
        self.assertEqual(payload["summary"]["deductible_tax"], "0.00")
        self.assertEqual(payload["summary"]["result_label"], "本月应纳税额")
        self.assertEqual(payload["summary"]["result_amount"], "41,600.00")


if __name__ == "__main__":
    unittest.main()
