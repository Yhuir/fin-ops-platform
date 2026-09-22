from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fin_ops_platform.domain.enums import BatchType, ImportDecision
from fin_ops_platform.domain.models import ImportedBatchRowResult
from fin_ops_platform.services.import_file_service import FileImportPreviewItem
from fin_ops_platform.services.import_job_queue import ImportJobIdempotencyConflict

from tests.app_test_support import build_local_state_application as build_application
from tests.app_test_support import install_durable_import_queue
from tests.mock_import_files import (
    BOCOM_JAN,
    CCB_JAN,
    CEB_JAN,
    CMBC_JAN,
    ICBC_JAN,
    INVOICE_JAN,
    PINGAN_JAN,
    UNSUPPORTED,
    MockImportFile,
)


def build_multipart_payload(
    *,
    imported_by: str,
    files: list[MockImportFile],
    file_overrides: list[dict[str, str]] | None = None,
) -> tuple[bytes, dict[str, str]]:
    boundary = "----finops-import-boundary"
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
                f"Content-Type: {file.content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(file.content)
        chunks.append(b"\r\n")

    add_text("imported_by", imported_by)
    for file in files:
        add_file("files", file)
    if file_overrides is not None:
        add_text("file_overrides", json.dumps(file_overrides, ensure_ascii=False))
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def manual_invoice_payload(**overrides: str) -> dict[str, str]:
    values = {
        "invoice_direction": "input",
        "invoice_nature": "blue",
        "seller_name": "云南供应商有限公司",
        "seller_tax_no": "915300000000000001",
        "buyer_name": "云南溯源科技有限公司",
        "buyer_tax_no": "915300007194052520",
        "invoice_number": "26117000001052654674",
        "invoice_code": "",
        "invoice_date": "2026-08-14",
        "net_amount": "100.00",
        "tax_rate": "13",
        "tax_amount": "13.00",
        "total_with_tax": "113.00",
    }
    values.update(overrides)
    return values


def manual_bank_transaction_payload(**overrides: str) -> dict[str, str]:
    values = {
        "bank_mapping_id": "ccb-8106",
        "account_no": "6227000012348106",
        "account_name": "云南溯源科技有限公司",
        "direction": "outflow",
        "amount": "100.00",
        "balance": "900.00",
        "trade_time": "2026-08-28T09:01:02",
        "currency": "CNY",
        "counterparty_name": "测试供应商",
    }
    values.update(overrides)
    return values


class ImportFileApiTests(unittest.TestCase):
    def _prepare(self, app, *, body, headers):
        queue = getattr(app, "_import_job_repository", None)
        if queue is None:
            queue = install_durable_import_queue(app)
        before_invoices = len(app._import_service.list_invoices())
        before_transactions = len(app._import_service.list_transactions())
        accepted = app.handle_request("POST", "/imports/files/preview", body=body, headers=headers)
        self.assertEqual(accepted.status_code, 202, accepted.body)
        job = json.loads(accepted.body)["job"]
        self.assertEqual(job["phase"], "prepare")
        self.assertEqual(job["status"], "queued")
        self.assertEqual(len(app._import_service.list_invoices()), before_invoices)
        self.assertEqual(len(app._import_service.list_transactions()), before_transactions)
        queue.process_all()
        response = app.handle_request("GET", f"/imports/files/sessions/{job['source']['session_id']}")
        self.assertEqual(response.status_code, 200, response.body)
        self.assertGreater(json.loads(response.body)["job"]["version"], job["version"])
        return response

    def test_manual_bank_transaction_preview_rejects_non_object_batch_items(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)

        response = app.handle_request(
            "POST",
            "/imports/bank-transactions/manual/preview",
            json.dumps({"transactions": [manual_bank_transaction_payload(), "invalid"]}),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.body)["error"],
            "manual_bank_transaction_payload_invalid",
        )

    def test_manual_bank_transaction_preview_and_confirm_use_the_formal_import_job_chain(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        import_queue = install_durable_import_queue(app)
        app._app_settings_service.get_bank_account_mappings_payload = lambda: [{  # type: ignore[attr-defined]
            "id": "ccb-8106",
            "last4": "8106",
            "bank_name": "中国建设银行",
            "short_name": "建行",
        }]

        preview_response = app.handle_request(
            "POST",
            "/imports/bank-transactions/manual/preview",
            json.dumps({"transactions": [manual_bank_transaction_payload()]}),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertNotIn("reference_field_key", preview_payload["values"][0])
        self.assertEqual(len(preview_payload["file_ids"]), 1)
        preview_file = preview_payload["import_session"]["files"][0]
        self.assertEqual(preview_file["template_code"], "manual_bank_transaction_entry")
        self.assertEqual(
            preview_file["row_results"],
            [{
                "id": preview_file["row_results"][0]["id"],
                "row_no": 1,
                "source_record_type": "bank_transaction",
                "decision": "created",
                "decision_reason": "Ready to create new bank transaction.",
            }],
        )
        self.assertNotIn("normalized_rows", preview_file)
        self.assertNotIn("raw_payload", preview_file["row_results"][0])
        self.assertNotIn("normalized_payload", preview_file["row_results"][0])

        confirm_response = app.handle_request(
            "POST",
            "/imports/files/confirm",
            json.dumps({
                "session_id": preview_payload["import_session"]["session"]["id"],
                "selected_file_ids": preview_payload["file_ids"],
            }),
        )
        self.assertEqual(confirm_response.status_code, 202)
        self.assertEqual(
            json.loads(confirm_response.body)["job"]["affected_domains"],
            ["imports_bank_transactions"],
        )

        import_queue.process_all()
        transactions = app._import_service.list_transactions()  # type: ignore[attr-defined]
        self.assertEqual(len(transactions), 1)
        self.assertIsNone(transactions[0].account_detail_no)
        self.assertTrue(transactions[0].data_fingerprint.startswith("bank:"))
        self.assertEqual(str(transactions[0].amount), "100.00")

    def test_discard_cancels_queued_commit_before_worker_can_write(self) -> None:
        app = build_application()
        self.addCleanup(app._test_import_storage_tmp.cleanup)
        queue = install_durable_import_queue(app)
        body, headers = build_multipart_payload(imported_by="user_finance_01", files=[INVOICE_JAN])
        preview = json.loads(self._prepare(app, body=body, headers=headers).body)
        session_id = preview["session"]["id"]
        accepted = app.handle_request("POST", "/imports/files/confirm", json.dumps({
            "session_id": session_id, "selected_file_ids": [preview["files"][0]["id"]],
            "preview_version": preview["job"]["version"],
        }))
        self.assertEqual(accepted.status_code, 202)
        discarded = app.handle_request("POST", "/imports/files/discard", json.dumps({"session_id": session_id}))
        self.assertEqual(discarded.status_code, 200, discarded.body)
        self.assertEqual(json.loads(discarded.body)["session"]["status"], "reverted")
        queue.process_all()
        self.assertEqual(queue.jobs[0].status, "canceled")
        self.assertEqual(app._import_service.list_invoices(), [])

    def test_reprepare_is_queued_and_old_preview_version_cannot_confirm(self) -> None:
        app = build_application()
        self.addCleanup(app._test_import_storage_tmp.cleanup)
        queue = install_durable_import_queue(app)
        body, headers = build_multipart_payload(imported_by="user_finance_01", files=[INVOICE_JAN])
        preview = json.loads(self._prepare(app, body=body, headers=headers).body)
        old_batch = preview["files"][0]["preview_batch_id"]
        request = {"session_id": preview["session"]["id"], "selected_file_ids": [preview["files"][0]["id"]]}
        with patch.object(app._file_import_service, "_read_rows", side_effect=AssertionError("HTTP retry must not parse")):
            retried = app.handle_request("POST", "/imports/files/retry", json.dumps(request))
        self.assertEqual(retried.status_code, 202, retried.body)
        self.assertEqual(json.loads(retried.body)["job"]["import_job_id"], preview["job"]["import_job_id"])
        queue.process_all()
        stale = app.handle_request("POST", "/imports/files/confirm", json.dumps({**request, "preview_version": preview["job"]["version"]}))
        self.assertEqual(stale.status_code, 409, stale.body)
        self.assertEqual(app._import_service.get_batch(old_batch).batch.status.value, "reverted")
        self.assertEqual(app._import_service.list_invoices(), [])

    def test_manual_invoice_preview_and_confirm_use_the_formal_import_job_chain(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        import_queue = install_durable_import_queue(app)

        preview_response = app.handle_request(
            "POST",
            "/imports/invoices/manual/preview",
            json.dumps({"invoices": [
                manual_invoice_payload(),
                manual_invoice_payload(
                    invoice_number="26117000001052654675",
                    net_amount="50.00",
                    tax_amount="5.00",
                    total_with_tax="55.00",
                ),
            ]}),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual([item["invoice_number"] for item in preview_payload["values"]], [
            "26117000001052654674",
            "26117000001052654675",
        ])
        self.assertEqual(len(preview_payload["file_ids"]), 2)
        self.assertEqual(preview_payload["import_session"]["files"][0]["template_code"], "manual_invoice_entry")
        self.assertEqual(preview_payload["import_session"]["files"][0]["batch_type"], "input_invoice")

        confirm_response = app.handle_request(
            "POST",
            "/imports/files/confirm",
            json.dumps(
                {
                    "session_id": preview_payload["import_session"]["session"]["id"],
                    "selected_file_ids": preview_payload["file_ids"],
                }
            ),
        )
        self.assertEqual(confirm_response.status_code, 202)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["job"]["affected_domains"], ["imports_invoices"])

        import_queue.process_all()
        invoices = app._import_service.list_invoices()  # type: ignore[attr-defined]
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].invoice_no, "26117000001052654674")
        self.assertEqual(str(invoices[0].amount), "100.00")
        self.assertEqual(invoices[0].invoice_source, "manual_invoice_entry")
        self.assertEqual(invoices[0].source_links[0]["source_type"], "manual_invoice_import")

    def test_manual_invoice_preview_blocks_exact_duplicate(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        first = app._manual_invoice_entry_service.preview_batch(  # type: ignore[attr-defined]
            payloads=[manual_invoice_payload()],
            imported_by="local",
        )
        app._file_import_service.confirm_session(  # type: ignore[attr-defined]
            session_id=first.session.id,
            selected_file_ids=first.file_ids,
        )

        response = app.handle_request(
            "POST",
            "/imports/invoices/manual/preview",
            json.dumps({"invoices": [manual_invoice_payload()]}),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error"], "manual_invoice_duplicate")

    def test_manual_invoice_recognition_uses_only_the_first_uploaded_file(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        calls: list[tuple[str, bytes]] = []

        def recognize(*, file_name: str, content: bytes) -> dict[str, str]:
            calls.append((file_name, content))
            return {"invoice_number": "FIRST"}

        app._manual_invoice_entry_service.recognize = recognize  # type: ignore[attr-defined,method-assign]
        body, headers = build_multipart_payload(
            imported_by="finance-user",
            files=[MockImportFile("first.jpg", b"first"), MockImportFile("second.pdf", b"second")],
        )

        response = app.handle_request(
            "POST",
            "/imports/invoices/manual/recognize",
            body=body,
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["values"]["invoice_number"], "FIRST")
        self.assertEqual(calls, [("first.jpg", b"first")])

    def test_manual_recognition_never_prefills_bank_account_as_invoice_or_writes_facts(self) -> None:
        from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService
        from tests.test_oa_attachment_invoice_service import VALID_PNG, _digital_invoice_text
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        parser = OAAttachmentInvoiceService()
        app._manual_invoice_entry_service._document_recognizer = parser
        before = len(app._import_service.list_invoices())
        body, headers = build_multipart_payload(imported_by="finance-user", files=[MockImportFile("invoice.png", VALID_PNG)])
        for labelled in (False, True):
            text = _digital_invoice_text("26317000002920092512")
            if not labelled:
                text = text.replace("发票号码：26317000002920092512", "发票号码：\n开票日期：\n263170000029200925122026")
            text += "\n银行账号：53001905038050548106"
            with patch.object(parser, "_extract_image_text", return_value=text):
                response = app.handle_request("POST", "/imports/invoices/manual/recognize", body=body, headers=headers)
            self.assertEqual(response.status_code, 200)
            values = json.loads(response.body)["values"]
            self.assertEqual(values["invoice_number"], "26317000002920092512" if labelled else "")
            self.assertNotIn("source_region_key", values)
            self.assertEqual(len(app._import_service.list_invoices()), before)

    def test_import_batch_error_csv_contains_review_rows_without_internal_ids(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        preview = app._import_service.preview_import(  # type: ignore[attr-defined]
            batch_type=BatchType.INPUT_INVOICE,
            source_name="invalid.xlsx",
            imported_by="user_finance_01",
            rows=[{"invoice_no": "", "amount": "bad"}],
        )

        response = app.handle_request("GET", f"/imports/batches/{preview.id}/errors.csv")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/csv; charset=utf-8")
        self.assertTrue(response.body.startswith("\ufeff行号,数据类型,处理结果,原因"))
        self.assertIn(",error,", response.body)
        self.assertNotIn(preview.row_results[0].id, response.body)
        app.close()

    def test_import_fact_files_list_omits_preview_detail_payloads(self) -> None:
        class FakeImportFactRepository:
            def list_import_files_page(self, **_kwargs):
                return [
                    FileImportPreviewItem(
                        id="file_1",
                        file_name="input.xlsx",
                        template_code="invoice_export",
                        batch_type=BatchType.INPUT_INVOICE,
                        status="confirmed",
                        message="ok",
                        row_count=1,
                        success_count=1,
                        row_results=[
                            ImportedBatchRowResult(
                                id="row_1",
                                batch_id="batch_1",
                                row_no=1,
                                source_record_type="invoice",
                                source_unique_key=None,
                                data_fingerprint=None,
                                decision=ImportDecision.CREATED,
                                decision_reason="created",
                                linked_object_type="invoice",
                                linked_object_id="invoice_1",
                                raw_payload={"large": "payload"},
                            )
                        ],
                        normalized_rows=[{"invoice_no": "INV-001"}],
                    )
                ], 1

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._state_store.import_fact_repository = FakeImportFactRepository()  # type: ignore[attr-defined]

            response = app.handle_request("GET", "/api/import-facts/files?page=1&page_size=50")

            self.assertEqual(response.status_code, 200)
            payload = json.loads(response.body)
            self.assertEqual(payload["pagination"], {"page": 1, "page_size": 50, "total": 1})
            self.assertEqual(payload["items"][0]["id"], "file_1")
            self.assertEqual(payload["items"][0]["row_count"], 1)
            self.assertNotIn("row_results", payload["items"][0])
            self.assertNotIn("normalized_rows", payload["items"][0])
            app.close()

    def test_preview_files_uses_lightweight_import_preview_persistence(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        persist_calls: list[str] = []
        app._persist_confirmed_import_delta = lambda **_kwargs: self.fail(  # type: ignore[attr-defined]
            "file preview must not persist full workbench state"
        )
        original_persist = app._persist_import_preview_delta
        def persist_preview(session_id, **kwargs):
            persist_calls.append(session_id)
            return original_persist(session_id, **kwargs)
        app._import_processing_service._persist_import_preview_delta = persist_preview
        body, headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[INVOICE_JAN],
        )

        response = self._prepare(app, body=body, headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(persist_calls), 1)
        self.assertRegex(persist_calls[0], r"^import_session_[0-9a-f]{32}$")

    def test_preview_files_keeps_corrupt_excel_as_file_level_error_without_aborting_batch(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
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
            INVOICE_JAN.content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

        response = self._prepare(app,
            body=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        file_map = {item["file_name"]: item for item in payload["files"]}
        self.assertEqual(file_map["损坏流水.xlsx"]["status"], "unrecognized_template")
        self.assertIn("不是有效的 Excel 工作簿", file_map["损坏流水.xlsx"]["message"])
        self.assertEqual(file_map[INVOICE_JAN.name]["status"], "preview_ready")

    def test_preview_files_detects_supported_templates_and_keeps_unrecognized_file_level_error(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        body, headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[INVOICE_JAN, ICBC_JAN, PINGAN_JAN, UNSUPPORTED],
        )

        response = self._prepare(app, body=body, headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["session"]["file_count"], 4)
        file_map = {item["file_name"]: item for item in payload["files"]}

        self.assertEqual(file_map[INVOICE_JAN.name]["template_code"], "invoice_export")
        self.assertEqual(file_map[INVOICE_JAN.name]["batch_type"], "input_invoice")
        self.assertGreater(file_map[INVOICE_JAN.name]["row_count"], 0)
        self.assertNotIn("row_results", file_map[INVOICE_JAN.name])
        self.assertNotIn("normalized_rows", file_map[INVOICE_JAN.name])
        self.assertEqual(payload["duplicate_groups"], [])

        self.assertEqual(file_map[ICBC_JAN.name]["template_code"], "bank_statement")
        self.assertEqual(file_map[ICBC_JAN.name]["batch_type"], "bank_transaction")
        self.assertGreater(file_map[ICBC_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[PINGAN_JAN.name]["template_code"], "bank_statement")
        self.assertEqual(file_map[PINGAN_JAN.name]["batch_type"], "bank_transaction")
        self.assertGreater(file_map[PINGAN_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[UNSUPPORTED.name]["status"], "unrecognized_template")
        self.assertIn("无法识别", file_map[UNSUPPORTED.name]["message"])

        session_id = payload["session"]["id"]
        review_response = app.handle_request(
            "GET",
            f"/imports/files/sessions/{session_id}/review-rows?file_id={payload['files'][0]['id']}&offset=0&limit=999",
        )
        self.assertEqual(review_response.status_code, 200)
        review_payload = json.loads(review_response.body)
        self.assertEqual(review_payload["limit"], 100)
        self.assertEqual(review_payload["offset"], 0)
        self.assertLessEqual(len(review_payload["rows"]), 100)

        missing_file = app.handle_request("GET", f"/imports/files/sessions/{session_id}/review-rows?kind=unimported")
        self.assertEqual(missing_file.status_code, 400)
        unknown_file = app.handle_request("GET", f"/imports/files/sessions/{session_id}/review-rows?file_id=another-session-file")
        self.assertEqual(unknown_file.status_code, 404)
        self.assertEqual(sum(review_payload["summary"].values()), review_payload["total"])

        invalid_review_response = app.handle_request(
            "GET",
            f"/imports/files/sessions/{session_id}/review-rows?file_id={payload['files'][0]['id']}&limit=bad",
        )
        self.assertEqual(invalid_review_response.status_code, 400)
        self.assertEqual(json.loads(invalid_review_response.body)["error"], "invalid_import_review_rows_request")

    def test_preview_files_recognizes_bank_statement_templates(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        body, headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[CEB_JAN, CCB_JAN, CMBC_JAN, BOCOM_JAN],
        )

        response = self._prepare(app, body=body, headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        file_map = {item["file_name"]: item for item in payload["files"]}

        self.assertEqual(file_map[CEB_JAN.name]["template_code"], "bank_statement")
        self.assertGreater(file_map[CEB_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[CCB_JAN.name]["template_code"], "bank_statement")
        self.assertGreater(file_map[CCB_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[CMBC_JAN.name]["template_code"], "bank_statement")
        self.assertGreater(file_map[CMBC_JAN.name]["row_count"], 0)

        self.assertEqual(file_map[BOCOM_JAN.name]["template_code"], "bank_statement")
        self.assertEqual(file_map[BOCOM_JAN.name]["detected_bank_name"], "交通银行")
        self.assertEqual(file_map[BOCOM_JAN.name]["detected_last4"], "3847")
        self.assertEqual(file_map[BOCOM_JAN.name]["row_count"], 2)

    def test_preview_files_accepts_per_file_overrides(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        body, headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[INVOICE_JAN, PINGAN_JAN],
            file_overrides=[
                {
                    "file_name": INVOICE_JAN.name,
                    "template_code": "invoice_export",
                    "batch_type": "output_invoice",
                },
                {
                    "file_name": PINGAN_JAN.name,
                    "template_code": "bank_statement",
                    "batch_type": "bank_transaction",
                    "bank_mapping_id": "bank_mapping_pingan_override",
                    "bank_name": "平安银行",
                    "bank_short_name": "平安",
                    "last4": "0093",
                },
            ],
        )

        response = self._prepare(app, body=body, headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        file_map = {item["file_name"]: item for item in payload["files"]}

        self.assertIsNone(file_map[INVOICE_JAN.name]["batch_type"])
        self.assertIn("方向", file_map[INVOICE_JAN.name]["message"])
        self.assertNotEqual(file_map[INVOICE_JAN.name]["status"], "preview_ready")
        self.assertEqual(file_map[INVOICE_JAN.name]["override_batch_type"], "output_invoice")
        self.assertEqual(file_map[PINGAN_JAN.name]["template_code"], "bank_statement")
        self.assertEqual(file_map[PINGAN_JAN.name]["override_template_code"], "bank_statement")
        self.assertEqual(file_map[PINGAN_JAN.name]["selected_bank_mapping_id"], "bank_mapping_pingan_override")
        self.assertEqual(file_map[PINGAN_JAN.name]["selected_bank_name"], "平安银行")
        self.assertEqual(file_map[PINGAN_JAN.name]["selected_bank_short_name"], "平安")
        self.assertEqual(file_map[PINGAN_JAN.name]["selected_bank_last4"], "0093")

    def test_preview_files_returns_bank_selection_conflict_fields(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        body, headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[PINGAN_JAN],
            file_overrides=[
                {
                    "file_name": PINGAN_JAN.name,
                    "template_code": "bank_statement",
                    "batch_type": "bank_transaction",
                    "bank_mapping_id": "bank_mapping_manual_8826",
                    "bank_name": "建设银行",
                    "last4": "8826",
                },
            ],
        )

        response = self._prepare(app, body=body, headers=headers)

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
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        import_queue = install_durable_import_queue(app)
        preview_body, preview_headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[INVOICE_JAN, PINGAN_JAN],
        )
        preview_response = self._prepare(app,
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
                    "preview_version": preview_payload["job"]["version"],
                    "selected_file_ids": [invoice_file["id"]],
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 202)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["job"]["type"], "file_import")
        self.assertEqual(confirm_payload["job"]["affected_domains"], ["imports_invoices"])
        self.assertEqual(confirm_payload["job"]["route"], "/imports/invoices")
        job_id = confirm_payload["job"]["job_id"]
        import_queue.process_all()
        job_payload = confirm_payload["job"]
        for _ in range(20):
            job_response = app.handle_request("GET", f"/api/background-jobs/{job_id}")
            job_payload = json.loads(job_response.body)["job"]
            if job_payload["status"] == "succeeded":
                break
            sleep(0.02)
        self.assertEqual(job_payload["status"], "succeeded")

        session_response = app.handle_request(
            "GET",
            f"/imports/files/sessions/{preview_payload['session']['id']}",
        )
        self.assertEqual(session_response.status_code, 200)
        confirm_payload = json.loads(session_response.body)
        confirmed_file = next(item for item in confirm_payload["files"] if item["id"] == invoice_file["id"])
        skipped_file = next(item for item in confirm_payload["files"] if item["id"] == pingan_file["id"])

        self.assertEqual(confirmed_file["status"], "confirmed")
        self.assertTrue(confirmed_file["batch_id"])
        self.assertEqual(skipped_file["status"], "preview_ready")
        self.assertIsNone(skipped_file["batch_id"])

        batch_response = app.handle_request("GET", f"/imports/batches/{confirmed_file['batch_id']}")
        self.assertEqual(batch_response.status_code, 200)
        batch_payload = json.loads(batch_response.body)
        self.assertEqual(batch_payload["batch"]["batch_type"], "input_invoice")

        session_file = next(item for item in confirm_payload["files"] if item["id"] == invoice_file["id"])
        self.assertEqual(session_file["status"], "confirmed")
        # Confirm the remaining file as a new intent on the retained originals.
        second = app.handle_request("POST", "/imports/files/confirm", json.dumps({
            "session_id": preview_payload["session"]["id"],
            "preview_version": confirm_payload["job"]["version"],
            "selected_file_ids": [pingan_file["id"]],
        }))
        self.assertEqual(second.status_code, 202, second.body)
        self.assertNotEqual(json.loads(second.body)["job"]["job_id"], job_id)
        import_queue.process_all()
        repeated = app.handle_request("POST", "/imports/files/confirm", json.dumps({
            "session_id": preview_payload["session"]["id"],
            "preview_version": preview_payload["job"]["version"],
            "selected_file_ids": [invoice_file["id"]],
        }))
        self.assertEqual(repeated.status_code, 202, repeated.body)
        self.assertEqual(json.loads(repeated.body)["job"]["job_id"], job_id)
        self.assertEqual(app._file_import_service.get_session(preview_payload["session"]["id"]).status, "confirmed")

    def test_all_duplicate_bank_upload_finishes_without_commit(self):
        app = build_application()
        self.addCleanup(app._test_import_storage_tmp.cleanup)
        body, headers = build_multipart_payload(imported_by="user_finance_01", files=[PINGAN_JAN], file_overrides=[{"field_mapping": {"bank_serial_no": "10"}}])
        first = json.loads(self._prepare(app, body=body, headers=headers).body)
        response = app.handle_request("POST", "/imports/files/confirm", json.dumps({
            "session_id": first["session"]["id"], "selected_file_ids": [first["files"][0]["id"]],
            "preview_version": first["job"]["version"],
        }))
        self.assertEqual(response.status_code, 202)
        app._import_job_repository.process_all()
        count = len(app._import_service.list_transactions())
        duplicate = json.loads(self._prepare(app, body=body, headers=headers).body)
        self.assertEqual(duplicate["job"]["status"], "succeeded")
        self.assertEqual(duplicate["job"]["result_summary"]["outcome"], "no_changes")
        self.assertEqual(duplicate["job"]["result_summary"]["created"], 0)
        self.assertEqual(len(app._import_service.list_transactions()), count)

    def test_upload_fails_explicitly_when_durable_import_queue_is_unavailable(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        app._import_job_repository = None
        body, headers = build_multipart_payload(imported_by="user_finance_01", files=[INVOICE_JAN])
        response = app.handle_request("POST", "/imports/files/preview", body=body, headers=headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body)["error"], "import_preparation_unavailable")
        self.assertEqual(app._import_service.list_invoices(), [])

    def test_confirm_retry_reuses_failed_import_intent_and_has_no_outbox(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        queue = install_durable_import_queue(app)
        body, headers = build_multipart_payload(imported_by="user_finance_01", files=[INVOICE_JAN])
        preview = json.loads(self._prepare(app, body=body, headers=headers).body)
        request = json.dumps({"session_id": preview["session"]["id"],
                              "selected_file_ids": [preview["files"][0]["id"]],
                              "preview_version": preview["job"]["version"]})
        first = app.handle_request("POST", "/imports/files/confirm", request)
        self.assertEqual(first.status_code, 202, first.body)
        job_id = json.loads(first.body)["job"]["import_job_id"]
        # Failure happens before facts, then the same confirmation resumes commit.
        with patch.object(app._file_import_service, "confirm_session", side_effect=RuntimeError("temporary database failure")):
            queue.process_all(raise_errors=False)
        self.assertEqual(queue.get_job(job_id).status, "failed")
        second = app.handle_request("POST", "/imports/files/confirm", request)
        self.assertEqual(second.status_code, 202, second.body)
        self.assertEqual(json.loads(second.body)["job"]["import_job_id"], job_id)
        queue.process_all()
        self.assertEqual(queue.get_job(job_id).status, "succeeded")
        self.assertEqual(len(queue.jobs), 1)
        self.assertEqual(queue.events, [])
        self.assertNotIn("background_job_id", queue.get_job(job_id).payload)
        self.assertEqual(app._file_import_service.get_session(preview["session"]["id"]).files[0].status, "confirmed")

    def test_confirm_returns_structured_conflict_for_mismatched_idempotent_job(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        install_durable_import_queue(app)
        preview_body, preview_headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[INVOICE_JAN],
        )
        preview_payload = json.loads(
            self._prepare(app,
                body=preview_body,
                headers=preview_headers,
            ).body
        )

        def conflict(*_args, **_kwargs):
            raise ImportJobIdempotencyConflict("request fingerprint mismatch")

        app._import_job_repository.confirm_job = conflict
        response = app.handle_request(
            "POST",
            "/imports/files/confirm",
            json.dumps(
                {
                    "session_id": preview_payload["session"]["id"],
                    "preview_version": preview_payload["job"]["version"],
                    "selected_file_ids": [preview_payload["files"][0]["id"]],
                }
            ),
        )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["error"], "import_confirmation_conflict")
        self.assertEqual(payload["message"], "request fingerprint mismatch")
        self.assertEqual(app._import_job_repository.jobs[0].status, "awaiting_confirmation")

    def test_confirm_bank_transaction_file_job_reports_bank_import_domain(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        import_queue = install_durable_import_queue(app)
        preview_body, preview_headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[PINGAN_JAN],
            file_overrides=[
                {
                    "file_name": PINGAN_JAN.name,
                    "template_code": "bank_statement",
                    "batch_type": "bank_transaction",
                    "bank_mapping_id": "bank_mapping_pingan_0093",
                    "bank_name": "平安银行",
                    "bank_short_name": "平安",
                    "last4": "0093",
                }
            ],
        )
        preview_response = self._prepare(app,
            body=preview_body,
            headers=preview_headers,
        )
        preview_payload = json.loads(preview_response.body)
        bank_file = preview_payload["files"][0]

        confirm_response = app.handle_request(
            "POST",
            "/imports/files/confirm",
            json.dumps(
                {
                    "session_id": preview_payload["session"]["id"],
                    "preview_version": preview_payload["job"]["version"],
                    "selected_file_ids": [bank_file["id"]],
                }
            ),
        )
        confirm_payload = json.loads(confirm_response.body)
        import_queue.process_all()
        job_id = confirm_payload["job"]["job_id"]
        job_response = app.handle_request("GET", f"/api/background-jobs/{job_id}")
        job_payload = json.loads(job_response.body)["job"]

        self.assertEqual(confirm_response.status_code, 202)
        self.assertEqual(confirm_payload["job"]["affected_domains"], ["imports_bank_transactions"])
        self.assertEqual(confirm_payload["job"]["route"], "/imports/bank-transactions")
        self.assertEqual(job_payload["affected_domains"], ["imports_bank_transactions"])
        self.assertEqual(job_payload["route"], "/imports/bank-transactions")

    def test_preview_session_can_be_discarded_before_confirm(self) -> None:
        app = build_application()
        fixture = getattr(app, "_test_import_storage_tmp", None)
        if fixture is not None:
            self.addCleanup(fixture.cleanup)
        preview_body, preview_headers = build_multipart_payload(
            imported_by="user_finance_01",
            files=[INVOICE_JAN],
        )
        preview_payload = json.loads(
            self._prepare(app, body=preview_body, headers=preview_headers).body
        )
        session_id = preview_payload["session"]["id"]

        discard_response = app.handle_request(
            "POST",
            "/imports/files/discard",
            json.dumps({"session_id": session_id}),
        )
        repeated_response = app.handle_request(
            "POST",
            "/imports/files/discard",
            json.dumps({"session_id": session_id}),
        )
        confirm_response = app.handle_request(
            "POST",
            "/imports/files/confirm",
            json.dumps({"session_id": session_id, "selected_file_ids": [preview_payload["files"][0]["id"]]}),
        )

        self.assertEqual(discard_response.status_code, 200)
        self.assertEqual(json.loads(discard_response.body)["session"]["status"], "reverted")
        self.assertEqual(repeated_response.status_code, 200)
        self.assertEqual(confirm_response.status_code, 409)
        self.assertEqual(json.loads(confirm_response.body)["error"], "import_file_session_not_confirmable")


if __name__ == "__main__":
    unittest.main()
