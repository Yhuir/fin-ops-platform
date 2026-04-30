from __future__ import annotations

import json
from pathlib import Path
import unittest

from fin_ops_platform.app.server import build_application


ROOT = Path(__file__).resolve().parents[1]
INVOICE_JAN = ROOT / "fixtures" / "进发票信息导出1-3月" / "全量发票查询导出结果-2026年1月.xlsx"
ICBC_JAN = ROOT / "fixtures" / "测试用银行流水下载" / "工行税户1-3月" / "historydetail14080.xlsx"
PINGAN_JAN = ROOT / "fixtures" / "测试用银行流水下载" / "平安1-3月" / "2026-01-01至2026-01-31交易明细.xlsx"
CEB_JAN = ROOT / "fixtures" / "测试用银行流水下载" / "光大1-3月" / "billmx20260320-202601.xls"
CCB_JAN = ROOT / "fixtures" / "测试用银行流水下载" / "建行1-3月" / "A058171TB_ND94389000000501277800011_CN000_20260320150836_2091193_resp.xls"
CMBC_JAN = ROOT / "fixtures" / "测试用银行流水下载" / "民生1-3月" / "活期账户交易明细查询20260320165947097.xlsx"
UNSUPPORTED = ROOT / "README.md"


def build_multipart_payload(
    *,
    imported_by: str,
    file_paths: list[Path],
    file_overrides: list[dict[str, str]] | None = None,
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
    if file_overrides is not None:
        add_text("file_overrides", json.dumps(file_overrides, ensure_ascii=False))
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


class ImportFileApiTests(unittest.TestCase):
    def test_preview_files_keeps_corrupt_excel_as_file_level_error_without_aborting_batch(self) -> None:
        app = build_application()
        boundary = "----finops-import-boundary"
        chunks: list[bytes] = []

        def add_text(name: str, value: str) -> None:
            chunks.append(f"--{boundary}\r\n".encode("utf-8"))
            chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            chunks.append(value.encode("utf-8"))
            chunks.append(b"\r\n")

        def add_file(name: str, filename: str, content: bytes, content_type: str) -> None:
            chunks.append(f"--{boundary}\r\n".encode("utf-8"))
            chunks.append(
                (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8")
            )
            chunks.append(content)
            chunks.append(b"\r\n")

        add_text("imported_by", "user_finance_01")
        add_file(
            "files",
            "损坏流水.xlsx",
            b"not-a-real-xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        add_file(
            "files",
            INVOICE_JAN.name,
            INVOICE_JAN.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

        response = app.handle_request(
            "POST",
            "/imports/files/preview",
            body=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        file_map = {item["file_name"]: item for item in payload["files"]}
        self.assertEqual(file_map["损坏流水.xlsx"]["status"], "unrecognized_template")
        self.assertIn("文件读取失败", file_map["损坏流水.xlsx"]["message"])
        self.assertEqual(file_map[INVOICE_JAN.name]["status"], "preview_ready")

    def test_preview_files_detects_supported_templates_and_keeps_unrecognized_file_level_error(self) -> None:
        app = build_application()
        body, headers = build_multipart_payload(
            imported_by="user_finance_01",
            file_paths=[INVOICE_JAN, ICBC_JAN, PINGAN_JAN, UNSUPPORTED],
        )

        response = app.handle_request("POST", "/imports/files/preview", body=body, headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["session"]["file_count"], 4)
        file_map = {item["file_name"]: item for item in payload["files"]}

        self.assertEqual(file_map[INVOICE_JAN.name]["template_code"], "invoice_export")
        self.assertEqual(file_map[INVOICE_JAN.name]["batch_type"], "input_invoice")
        self.assertGreater(file_map[INVOICE_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[ICBC_JAN.name]["template_code"], "icbc_historydetail")
        self.assertEqual(file_map[ICBC_JAN.name]["batch_type"], "bank_transaction")
        self.assertGreater(file_map[ICBC_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[PINGAN_JAN.name]["template_code"], "pingan_transaction_detail")
        self.assertEqual(file_map[PINGAN_JAN.name]["batch_type"], "bank_transaction")
        self.assertGreater(file_map[PINGAN_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[UNSUPPORTED.name]["status"], "unrecognized_template")
        self.assertIn("无法识别", file_map[UNSUPPORTED.name]["message"])

    def test_preview_files_recognizes_ceb_ccb_and_cmbc_templates(self) -> None:
        app = build_application()
        body, headers = build_multipart_payload(
            imported_by="user_finance_01",
            file_paths=[CEB_JAN, CCB_JAN, CMBC_JAN],
        )

        response = app.handle_request("POST", "/imports/files/preview", body=body, headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        file_map = {item["file_name"]: item for item in payload["files"]}

        self.assertEqual(file_map[CEB_JAN.name]["template_code"], "ceb_transaction_detail")
        self.assertGreater(file_map[CEB_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[CCB_JAN.name]["template_code"], "ccb_transaction_detail")
        self.assertGreater(file_map[CCB_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[CMBC_JAN.name]["template_code"], "cmbc_transaction_detail")
        self.assertGreater(file_map[CMBC_JAN.name]["row_count"], 0)

    def test_preview_files_accepts_per_file_overrides(self) -> None:
        app = build_application()
        body, headers = build_multipart_payload(
            imported_by="user_finance_01",
            file_paths=[INVOICE_JAN, PINGAN_JAN],
            file_overrides=[
                {
                    "file_name": INVOICE_JAN.name,
                    "template_code": "invoice_export",
                    "batch_type": "output_invoice",
                },
                {
                    "file_name": PINGAN_JAN.name,
                    "template_code": "pingan_transaction_detail",
                    "batch_type": "bank_transaction",
                    "bank_mapping_id": "bank_mapping_pingan_override",
                    "bank_name": "平安银行",
                    "bank_short_name": "平安",
                    "last4": "0093",
                },
            ],
        )

        response = app.handle_request("POST", "/imports/files/preview", body=body, headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        file_map = {item["file_name"]: item for item in payload["files"]}

        self.assertEqual(file_map[INVOICE_JAN.name]["batch_type"], "output_invoice")
        self.assertEqual(file_map[INVOICE_JAN.name]["override_batch_type"], "output_invoice")
        self.assertEqual(file_map[PINGAN_JAN.name]["template_code"], "pingan_transaction_detail")
        self.assertEqual(file_map[PINGAN_JAN.name]["override_template_code"], "pingan_transaction_detail")
        self.assertEqual(file_map[PINGAN_JAN.name]["selected_bank_mapping_id"], "bank_mapping_pingan_override")
        self.assertEqual(file_map[PINGAN_JAN.name]["selected_bank_name"], "平安银行")
        self.assertEqual(file_map[PINGAN_JAN.name]["selected_bank_short_name"], "平安")
        self.assertEqual(file_map[PINGAN_JAN.name]["selected_bank_last4"], "0093")

    def test_preview_files_returns_bank_selection_conflict_fields(self) -> None:
        app = build_application()
        body, headers = build_multipart_payload(
            imported_by="user_finance_01",
            file_paths=[PINGAN_JAN],
            file_overrides=[
                {
                    "file_name": PINGAN_JAN.name,
                    "template_code": "pingan_transaction_detail",
                    "batch_type": "bank_transaction",
                    "bank_mapping_id": "bank_mapping_manual_8826",
                    "bank_name": "建设银行",
                    "last4": "8826",
                },
            ],
        )

        response = app.handle_request("POST", "/imports/files/preview", body=body, headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        preview_file = payload["files"][0]
        self.assertTrue(preview_file["bank_selection_conflict"])
        self.assertEqual(preview_file["selected_bank_mapping_id"], "bank_mapping_manual_8826")
        self.assertEqual(preview_file["selected_bank_last4"], "8826")
        self.assertEqual(preview_file["detected_last4"], "0093")
        self.assertEqual(preview_file["detected_bank_name"], "平安银行")
        self.assertIn("建设银行", preview_file["conflict_message"])

    def test_confirm_files_imports_only_selected_files_from_session(self) -> None:
        app = build_application()
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
        invoice_file = next(item for item in preview_payload["files"] if item["file_name"] == INVOICE_JAN.name)
        pingan_file = next(item for item in preview_payload["files"] if item["file_name"] == PINGAN_JAN.name)

        confirm_response = app.handle_request(
            "POST",
            "/imports/files/confirm",
            json.dumps(
                {
                    "session_id": preview_payload["session"]["id"],
                    "selected_file_ids": [invoice_file["id"]],
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        confirmed_file = next(item for item in confirm_payload["files"] if item["id"] == invoice_file["id"])
        skipped_file = next(item for item in confirm_payload["files"] if item["id"] == pingan_file["id"])

        self.assertEqual(confirmed_file["status"], "confirmed")
        self.assertTrue(confirmed_file["batch_id"])
        self.assertEqual(skipped_file["status"], "skipped")
        self.assertIsNone(skipped_file["batch_id"])

        batch_response = app.handle_request("GET", f"/imports/batches/{confirmed_file['batch_id']}")
        self.assertEqual(batch_response.status_code, 200)
        batch_payload = json.loads(batch_response.body)
        self.assertEqual(batch_payload["batch"]["batch_type"], "input_invoice")

        session_response = app.handle_request(
            "GET",
            f"/imports/files/sessions/{preview_payload['session']['id']}",
        )
        self.assertEqual(session_response.status_code, 200)
        session_payload = json.loads(session_response.body)
        session_file = next(item for item in session_payload["files"] if item["id"] == invoice_file["id"])
        self.assertEqual(session_file["status"], "confirmed")


if __name__ == "__main__":
    unittest.main()
