from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from fin_ops_platform.app.server import build_application


ROOT = Path(__file__).resolve().parents[1]
INVOICE_JAN = ROOT / "发票信息导出1-3月" / "全量发票查询导出结果-2026年1月.xlsx"
PINGAN_JAN = ROOT / "测试用银行流水下载" / "平安1-3月" / "2026-01-01至2026-01-31交易明细.xlsx"


def build_multipart_payload(
    *,
    imported_by: str,
    file_paths: list[Path],
) -> tuple[bytes, dict[str, str]]:
    boundary = "----finops-import-boundary"
    chunks: list[bytes] = []

    def add_text(name: str, value: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    def add_file(name: str, path: Path) -> None:
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if path.suffix.lower() == ".xlsx"
            else "application/vnd.ms-excel"
        )
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")

    add_text("imported_by", imported_by)
    for file_path in file_paths:
        add_file("files", file_path)
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


class ImportFormalizationApiTests(unittest.TestCase):
    def test_confirmed_import_persists_across_restart_and_refreshes_api_workbench(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            preview_body, preview_headers = build_multipart_payload(
                imported_by="user_finance_01",
                file_paths=[INVOICE_JAN, PINGAN_JAN],
            )
            preview_response = app.handle_request(
                "POST",
                "/imports/files/preview",
                body=preview_body,
                headers=preview_headers,
            )
            self.assertEqual(preview_response.status_code, 200)
            preview_payload = json.loads(preview_response.body)

            confirm_response = app.handle_request(
                "POST",
                "/imports/files/confirm",
                json.dumps(
                    {
                        "session_id": preview_payload["session"]["id"],
                        "selected_file_ids": [file["id"] for file in preview_payload["files"] if file["status"] == "preview_ready"],
                    }
                ),
            )
            self.assertEqual(confirm_response.status_code, 200)
            confirm_payload = json.loads(confirm_response.body)
            self.assertIn("matching_run", confirm_payload)
            self.assertGreater(confirm_payload["matching_run"]["result_count"], 0)

            restarted = build_application(data_dir=Path(temp_dir))
            session_response = restarted.handle_request(
                "GET",
                f"/imports/files/sessions/{preview_payload['session']['id']}",
            )
            self.assertEqual(session_response.status_code, 200)
            session_payload = json.loads(session_response.body)
            self.assertEqual(session_payload["session"]["status"], "confirmed")

            workbench_response = restarted.handle_request("GET", "/api/workbench?month=2026-01")
            self.assertEqual(workbench_response.status_code, 200)
            workbench_payload = json.loads(workbench_response.body)
            self.assertEqual(workbench_payload["month"], "2026-01")
            self.assertGreater(workbench_payload["summary"]["bank_count"], 0)
            self.assertGreater(workbench_payload["summary"]["invoice_count"], 0)

    def test_templates_retry_with_invoice_batch_override_and_original_file_retention(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            invoice_file = temp_path / "auto-output.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(
                [
                    "序号",
                    "发票代码",
                    "发票号码",
                    "数电发票号码",
                    "销方识别号",
                    "销方名称",
                    "购方识别号",
                    "购买方名称",
                    "开票日期",
                    "税收分类编码",
                    "特定业务类型",
                    "货物或应税劳务名称",
                    "规格型号",
                    "单位",
                    "数量",
                    "单价",
                    "金额",
                    "税率",
                    "税额",
                    "价税合计",
                    "发票来源",
                    "发票票种",
                    "发票状态",
                    "是否正数发票",
                    "发票风险等级",
                    "开票人",
                    "备注",
                ]
            )
            sheet.append(
                [
                    "1",
                    "033001",
                    "5001",
                    "",
                    "91330106589876543T",
                    "杭州溯源科技有限公司",
                    "91530000291993988P",
                    "云南客户公司",
                    "2026-02-11 12:00:00",
                    "1090510990000000000",
                    "",
                    "*技术服务*平台服务",
                    "",
                    "项",
                    "1",
                    "100.00",
                    "100.00",
                    "6%",
                    "6.00",
                    "106.00",
                    "电子发票服务平台",
                    "数电发票（普通发票）",
                    "正常",
                    "是",
                    "正常",
                    "测试员",
                    "",
                ]
            )
            workbook.save(invoice_file)

            app = build_application(data_dir=temp_path)
            templates_response = app.handle_request("GET", "/imports/templates")
            self.assertEqual(templates_response.status_code, 200)
            templates_payload = json.loads(templates_response.body)
            self.assertGreaterEqual(len(templates_payload["templates"]), 6)

            preview_body, preview_headers = build_multipart_payload(
                imported_by="user_finance_01",
                file_paths=[invoice_file],
            )
            preview_response = app.handle_request(
                "POST",
                "/imports/files/preview",
                body=preview_body,
                headers=preview_headers,
            )
            self.assertEqual(preview_response.status_code, 200)
            preview_payload = json.loads(preview_response.body)
            file_payload = preview_payload["files"][0]
            self.assertEqual(file_payload["batch_type"], "output_invoice")

            storage_dir = temp_path / "import_files"
            self.assertTrue(storage_dir.exists())

            retry_response = app.handle_request(
                "POST",
                "/imports/files/retry",
                json.dumps(
                    {
                        "session_id": preview_payload["session"]["id"],
                        "selected_file_ids": [file_payload["id"]],
                        "overrides": {
                            file_payload["id"]: {
                                "batch_type": "input_invoice",
                                "template_code": "invoice_export",
                            }
                        },
                    }
                ),
            )
            self.assertEqual(retry_response.status_code, 200)
            retry_payload = json.loads(retry_response.body)
            self.assertEqual(retry_payload["files"][0]["batch_type"], "input_invoice")

    def test_revert_batch_and_download_batch_export(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            preview_body, preview_headers = build_multipart_payload(
                imported_by="user_finance_01",
                file_paths=[INVOICE_JAN],
            )
            preview_response = app.handle_request(
                "POST",
                "/imports/files/preview",
                body=preview_body,
                headers=preview_headers,
            )
            preview_payload = json.loads(preview_response.body)
            file_payload = preview_payload["files"][0]

            confirm_response = app.handle_request(
                "POST",
                "/imports/files/confirm",
                json.dumps(
                    {
                        "session_id": preview_payload["session"]["id"],
                        "selected_file_ids": [file_payload["id"]],
                    }
                ),
            )
            confirm_payload = json.loads(confirm_response.body)
            batch_id = confirm_payload["files"][0]["batch_id"]

            download_response = app.handle_request("GET", f"/imports/batches/{batch_id}/download")
            self.assertEqual(download_response.status_code, 200)
            self.assertIn("attachment", download_response.headers["Content-Disposition"])
            download_payload = json.loads(download_response.body)
            self.assertEqual(download_payload["batch"]["id"], batch_id)

            revert_response = app.handle_request("POST", f"/imports/batches/{batch_id}/revert", json.dumps({}))
            self.assertEqual(revert_response.status_code, 200)
            revert_payload = json.loads(revert_response.body)
            self.assertEqual(revert_payload["batch"]["status"], "reverted")

            batch_response = app.handle_request("GET", f"/imports/batches/{batch_id}")
            batch_payload = json.loads(batch_response.body)
            self.assertEqual(batch_payload["batch"]["status"], "reverted")

            session_response = app.handle_request(
                "GET",
                f"/imports/files/sessions/{preview_payload['session']['id']}",
            )
            session_payload = json.loads(session_response.body)
            self.assertEqual(session_payload["files"][0]["status"], "reverted")


if __name__ == "__main__":
    unittest.main()
