from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from openpyxl import Workbook

from tests.app_test_support import (
    build_grouped_workbench_projection,
    build_local_state_application as build_application,
    install_durable_import_queue,
)
from tests.mock_import_files import INVOICE_JAN, PINGAN_JAN, MockImportFile


def build_multipart_payload(
    *,
    imported_by: str,
    files: list[Path | MockImportFile],
) -> tuple[bytes, dict[str, str]]:
    boundary = "----finops-import-boundary"
    chunks: list[bytes] = []

    def add_text(name: str, value: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    def add_file(name: str, file: Path | MockImportFile) -> None:
        file_name = file.name
        content = file.read_bytes() if isinstance(file, Path) else file.content
        suffix = file.suffix.lower() if isinstance(file, Path) else f".{file.suffix}"
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if suffix == ".xlsx"
            else "application/vnd.ms-excel"
        )
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{file_name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(content)
        chunks.append(b"\r\n")

    add_text("imported_by", imported_by)
    for file in files:
        add_file("files", file)
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


class ImportFormalizationApiTests(unittest.TestCase):
    def _wait_for_background_job(self, app, job_id: str) -> dict[str, object]:
        deadline = time.monotonic() + 3
        job_payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            job_response = app.handle_request("GET", f"/api/background-jobs/{job_id}")
            self.assertEqual(job_response.status_code, 200)
            job_payload = json.loads(job_response.body)["job"]
            if job_payload["status"] in {"succeeded", "partial_success", "failed"}:
                return job_payload
            time.sleep(0.02)
        return job_payload

    def test_confirmed_import_persists_across_restart_and_refreshes_api_workbench(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            import_queue = install_durable_import_queue(app)
            preview_body, preview_headers = build_multipart_payload(
                imported_by="user_finance_01",
                files=[INVOICE_JAN, PINGAN_JAN],
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
                        "selected_file_ids": [
                            file["id"] for file in preview_payload["files"] if file["status"] == "preview_ready"
                        ],
                    }
                ),
            )
            self.assertEqual(confirm_response.status_code, 202)
            confirm_payload = json.loads(confirm_response.body)
            import_queue.process_all()
            job_payload = self._wait_for_background_job(app, confirm_payload["job"]["job_id"])
            self.assertEqual(job_payload["status"], "succeeded")
            matching_job_id = job_payload["result_summary"]["enqueued_matching_job_id"]
            self.assertTrue(matching_job_id)
            matching_job_payload = self._wait_for_background_job(app, matching_job_id)
            self.assertEqual(matching_job_payload["status"], "succeeded")
            self.assertIn("planned_relation_count", matching_job_payload["result_summary"])
            self.assertNotIn("candidate_count", matching_job_payload["result_summary"])
            self.assertIn("2026-01", matching_job_payload["result_summary"]["affected_months"])
            self.assertNotIn("matching_results", matching_job_payload["result_summary"])

            restarted = build_application(data_dir=Path(temp_dir), bootstrap_mode="legacy")
            session_response = restarted.handle_request(
                "GET",
                f"/imports/files/sessions/{preview_payload['session']['id']}",
            )
            self.assertEqual(session_response.status_code, 200)
            session_payload = json.loads(session_response.body)
            self.assertEqual(session_payload["session"]["status"], "confirmed")

            workbench_payload = build_grouped_workbench_projection(
                restarted,
                "2026-01",
                include_query_rows=False,
            )
            self.assertEqual(workbench_payload["month"], "2026-01")
            self.assertGreater(workbench_payload["summary"]["bank_count"], 0)
            self.assertGreater(workbench_payload["summary"]["invoice_count"], 0)
            app.shutdown_background_jobs()
            restarted.shutdown_background_jobs()

    def test_stale_api_preview_cannot_downgrade_another_process_confirmed_import(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            stale_api = build_application(data_dir=data_dir)
            invoice_body, invoice_headers = build_multipart_payload(
                imported_by="user_finance_01",
                files=[INVOICE_JAN],
            )
            invoice_preview_response = stale_api.handle_request(
                "POST",
                "/imports/files/preview",
                body=invoice_body,
                headers=invoice_headers,
            )
            self.assertEqual(invoice_preview_response.status_code, 200)
            invoice_preview = json.loads(invoice_preview_response.body)
            invoice_session_id = invoice_preview["session"]["id"]
            invoice_file = invoice_preview["files"][0]
            invoice_batch_id = invoice_file["preview_batch_id"]

            worker_api = build_application(data_dir=data_dir, bootstrap_mode="legacy")
            import_queue = install_durable_import_queue(worker_api)
            confirm_response = worker_api.handle_request(
                "POST",
                "/imports/files/confirm",
                json.dumps(
                    {
                        "session_id": invoice_session_id,
                        "selected_file_ids": [invoice_file["id"]],
                    }
                ),
            )
            self.assertEqual(confirm_response.status_code, 202)
            confirm_payload = json.loads(confirm_response.body)
            import_queue.process_all()
            job_payload = self._wait_for_background_job(worker_api, confirm_payload["job"]["job_id"])
            self.assertEqual(job_payload["status"], "succeeded")
            matching_job_id = job_payload["result_summary"].get("enqueued_matching_job_id")
            if matching_job_id:
                matching_job_payload = self._wait_for_background_job(worker_api, matching_job_id)
                self.assertEqual(matching_job_payload["status"], "succeeded")

            bank_body, bank_headers = build_multipart_payload(
                imported_by="user_finance_01",
                files=[PINGAN_JAN],
            )
            bank_preview_response = stale_api.handle_request(
                "POST",
                "/imports/files/preview",
                body=bank_body,
                headers=bank_headers,
            )
            self.assertEqual(bank_preview_response.status_code, 200)

            restarted = build_application(data_dir=data_dir, bootstrap_mode="legacy")
            session_response = restarted.handle_request(
                "GET",
                f"/imports/files/sessions/{invoice_session_id}",
            )
            self.assertEqual(session_response.status_code, 200)
            session_payload = json.loads(session_response.body)
            self.assertEqual(session_payload["session"]["status"], "confirmed")
            self.assertEqual(session_payload["files"][0]["status"], "confirmed")
            self.assertEqual(
                restarted._import_service.get_batch(invoice_batch_id).batch.status.value,  # noqa: SLF001
                "completed",
            )

            stale_api.shutdown_background_jobs()
            worker_api.shutdown_background_jobs()
            restarted.shutdown_background_jobs()

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
                files=[invoice_file],
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
            app.shutdown_background_jobs()

    def test_revert_batch_and_download_batch_export(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            import_queue = install_durable_import_queue(app)
            preview_body, preview_headers = build_multipart_payload(
                imported_by="user_finance_01",
                files=[INVOICE_JAN],
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
            import_queue.process_all()
            job_payload = self._wait_for_background_job(app, confirm_payload["job"]["job_id"])
            self.assertEqual(job_payload["status"], "succeeded")
            session_response = app.handle_request("GET", f"/imports/files/sessions/{preview_payload['session']['id']}")
            session_payload = json.loads(session_response.body)
            batch_id = session_payload["files"][0]["batch_id"]

            download_response = app.handle_request("GET", f"/imports/batches/{batch_id}/download")
            self.assertEqual(download_response.status_code, 200)
            self.assertIn("attachment", download_response.headers["Content-Disposition"])
            download_payload = json.loads(download_response.body)
            self.assertEqual(download_payload["batch"]["id"], batch_id)

            revert_response = app.handle_request("POST", f"/imports/batches/{batch_id}/revert", json.dumps({}))
            self.assertEqual(revert_response.status_code, 404)

            batch_response = app.handle_request("GET", f"/imports/batches/{batch_id}")
            batch_payload = json.loads(batch_response.body)
            self.assertEqual(batch_payload["batch"]["status"], "completed")

            session_response = app.handle_request(
                "GET",
                f"/imports/files/sessions/{preview_payload['session']['id']}",
            )
            session_payload = json.loads(session_response.body)
            self.assertEqual(session_payload["files"][0]["status"], "confirmed")
            app.shutdown_background_jobs()


if __name__ == "__main__":
    unittest.main()
