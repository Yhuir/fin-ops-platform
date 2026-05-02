import json
import os
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, MongoOASettings
from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService
from fin_ops_platform.services.oa_identity_service import OAIdentityServiceError, OAUserIdentity
from fin_ops_platform.services.settings_data_reset_service import (
    RESET_BANK_TRANSACTIONS_ACTION,
    RESET_INVOICES_ACTION,
    RESET_OA_AND_REBUILD_ACTION,
)


class RetentionScopedMongoWorkbenchOAAdapter(MongoOAAdapter):
    def __init__(self, *, form_documents: dict[str, list[dict]], project_documents: list[dict]) -> None:
        super().__init__(settings=MongoOASettings(host="127.0.0.1", database="form_data_db"))
        self._form_documents = form_documents
        self._project_documents = project_documents
        self.month_calls: list[str] = []
        self.bulk_call_count = 0

    def list_available_months(self) -> list[str]:
        months: set[str] = set()
        for documents in self._form_documents.values():
            for document in documents:
                data = document.get("data", {})
                application_date = str(data.get("applicationDate") or data.get("ApplicationDate") or "")
                if len(application_date) >= 7:
                    months.add(application_date[:7])
        return sorted(months)

    def list_application_records(self, month: str):
        self.month_calls.append(month)
        return super().list_application_records(month)

    def list_all_application_records(self):
        self.bulk_call_count += 1
        raise AssertionError("should not bulk scan all OA records")

    def _load_form_documents(self, form_id: str, month: str | None = None) -> list[dict]:
        documents = list(self._form_documents.get(str(form_id), []))
        if month is None:
            return documents
        return [
            document
            for document in documents
            if str(
                document.get("data", {}).get("applicationDate")
                or document.get("data", {}).get("ApplicationDate")
                or ""
            ).startswith(month)
        ]

    def _load_project_documents(self) -> list[dict]:
        return list(self._project_documents)

    def _load_form_month_documents(self, form_id: str) -> list[dict]:
        return list(self._form_documents.get(str(form_id), []))


class SettingsDataResetServiceTests(unittest.TestCase):
    @contextmanager
    def _temporary_env(self, **updates: str | None):
        previous = {key: os.environ.get(key) for key in updates}
        try:
            for key, value in updates.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    @contextmanager
    def _without_default_test_auth(self):
        previous = os.environ.get("FIN_OPS_TEST_DEFAULT_AUTH")
        os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = "0"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("FIN_OPS_TEST_DEFAULT_AUTH", None)
            else:
                os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = previous

    def test_reset_bank_transactions_keeps_invoices_and_protects_form_data_db(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            invoice_preview = app._import_service.preview_import(
                batch_type=BatchType.INPUT_INVOICE,
                source_name="input-demo.json",
                imported_by="tester",
                rows=[
                    {
                        "invoice_code": "033001",
                        "invoice_no": "9002",
                        "counterparty_name": "Vendor A",
                        "amount": "120.00",
                        "tax_amount": "7.20",
                        "total_with_tax": "127.20",
                        "invoice_date": "2026-03-24",
                        "invoice_status_from_source": "valid",
                    }
                ],
            )
            bank_preview = app._import_service.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name="bank-demo.json",
                imported_by="tester",
                rows=[
                    {
                        "account_no": "62229999",
                        "txn_date": "2026-03-24",
                        "counterparty_name": "Vendor A",
                        "debit_amount": "50.00",
                        "credit_amount": "",
                        "bank_serial_no": "SERIAL-NEW-001",
                        "summary": "purchase",
                    }
                ],
            )
            app._import_service.confirm_import(invoice_preview.id)
            app._import_service.confirm_import(bank_preview.id)
            app._matching_service.run(triggered_by="tester")
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-RESET-001",
                row_ids=["bk-reset-001", "inv-reset-001"],
                row_types=["bank", "invoice"],
                relation_mode="manual_confirmed",
                created_by="tester",
            )
            app._workbench_read_model_service.upsert_read_model(scope_key="2026-03", payload={"month": "2026-03"})
            app._workbench_override_service.mark_exception(
                row={"id": "bk-reset-001", "type": "bank"},
                exception_code="manual_review",
            )

            result = app._settings_data_reset_service.execute(RESET_BANK_TRANSACTIONS_ACTION)
            persisted = app._state_store.load()

        self.assertIn("form_data_db.form_data", result.protected_targets)
        self.assertEqual(result.deleted_counts["bank_transactions"], 1)
        self.assertEqual(result.deleted_counts["invoices"], 0)
        imports_payload = persisted["imports"]
        self.assertEqual(len(imports_payload["transactions"]), 0)
        self.assertEqual(len(imports_payload["invoices"]), 1)
        self.assertEqual(persisted["matching"], {})
        self.assertEqual(persisted["workbench_pair_relations"], {})
        self.assertEqual(persisted["workbench_read_models"], {})

    def test_reset_invoices_clears_tax_certified_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            invoice_preview = app._import_service.preview_import(
                batch_type=BatchType.OUTPUT_INVOICE,
                source_name="output-demo.json",
                imported_by="tester",
                rows=[
                    {
                        "invoice_code": "033001",
                        "invoice_no": "9003",
                        "counterparty_name": "Customer A",
                        "amount": "200.00",
                        "tax_amount": "26.00",
                        "total_with_tax": "226.00",
                        "invoice_date": "2026-03-24",
                        "invoice_status_from_source": "valid",
                    }
                ],
            )
            app._import_service.confirm_import(invoice_preview.id)
            preview_session = app._tax_certified_import_service.preview_files(
                imported_by="tester",
                uploads=[],
            )
            preview_session.files = []
            app._tax_certified_import_service._sessions[preview_session.id] = preview_session
            app._tax_certified_import_service._records["manual-cert-001"] = {
                "id": "manual-cert-001"
            }
            app._state_store.save_tax_certified_imports(app._tax_certified_import_service.snapshot())

            result = app._settings_data_reset_service.execute(RESET_INVOICES_ACTION)
            persisted = app._state_store.load()
            tax_persisted = app._state_store.load_tax_certified_imports()

        self.assertIn("form_data_db.form_data", result.protected_targets)
        self.assertEqual(result.deleted_counts["invoices"], 1)
        self.assertEqual(len(persisted["imports"]["invoices"]), 0)
        self.assertEqual(tax_persisted, {})

    def test_reset_api_requires_admin_access(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FULL001"],
                readonly_export_usernames=[],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="101",
                username="FULL001",
                nickname="普通用户",
                display_name="普通用户",
                dept_id="01",
                dept_name="财务部",
                roles=["finance"],
                permissions=[],
            )

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset",
                body=json.dumps({"action": RESET_BANK_TRANSACTIONS_ACTION}),
                headers={"Authorization": "Bearer full-access"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "admin_only")

    def test_reset_api_allows_admin_and_returns_protected_targets(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: (
                token == "admin-token" and password == "correct-password"
            )

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset",
                body=json.dumps(
                    {
                        "action": RESET_BANK_TRANSACTIONS_ACTION,
                        "oa_password": "correct-password",
                    }
                ),
                headers={"Authorization": "Bearer admin-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["action"], RESET_BANK_TRANSACTIONS_ACTION)
        self.assertIn("form_data_db.form_data", payload["protected_targets"])
        self.assertNotIn("oa_password", payload)
        self.assertNotIn("correct-password", response.body)

    def test_reset_job_api_creates_queryable_job_without_storing_password(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: (
                token == "admin-token" and password == "correct-password"
            )

            create_response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset/jobs",
                body=json.dumps(
                    {
                        "action": RESET_BANK_TRANSACTIONS_ACTION,
                        "oa_password": "correct-password",
                    }
                ),
                headers={"Authorization": "Bearer admin-token"},
            )
            create_payload = json.loads(create_response.body)
            job_id = create_payload["job"]["job_id"]

            deadline = time.monotonic() + 3
            job_payload = create_payload["job"]
            while time.monotonic() < deadline:
                query_response = app.handle_request(
                    "GET",
                    f"/api/workbench/settings/data-reset/jobs/{job_id}",
                    headers={"Authorization": "Bearer admin-token"},
                )
                job_payload = json.loads(query_response.body)["job"]
                if job_payload["status"] == "completed":
                    break
                time.sleep(0.02)

        self.assertEqual(create_response.status_code, 202)
        self.assertEqual(query_response.status_code, 200)
        self.assertEqual(job_payload["job_id"], job_id)
        self.assertEqual(job_payload["action"], RESET_BANK_TRANSACTIONS_ACTION)
        self.assertEqual(job_payload["status"], "completed")
        self.assertEqual(job_payload["phase"], "complete")
        self.assertEqual(job_payload["current"], job_payload["total"])
        self.assertEqual(job_payload["percent"], 100)
        self.assertIn("result", job_payload)
        self.assertNotIn("oa_password", json.dumps(job_payload, ensure_ascii=False))
        self.assertNotIn("correct-password", json.dumps(job_payload, ensure_ascii=False))

    def test_reset_job_api_exposes_active_running_job_for_page_reentry(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: (
                token == "admin-token" and password == "correct-password"
            )

            original_execute = app._settings_data_reset_service.execute
            release_job = Event()

            def slow_execute(action: str, **kwargs: object):
                progress_callback = kwargs.get("progress_callback")
                if callable(progress_callback):
                    progress_callback("persist_state", "正在写入银行流水重置结果。", 2, 4)
                release_job.wait(timeout=2)
                return original_execute(action, **kwargs)

            app._settings_data_reset_service.execute = slow_execute
            create_response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset/jobs",
                body=json.dumps(
                    {
                        "action": RESET_BANK_TRANSACTIONS_ACTION,
                        "oa_password": "correct-password",
                    }
                ),
                headers={"Authorization": "Bearer admin-token"},
            )
            create_payload = json.loads(create_response.body)
            job_id = create_payload["job"]["job_id"]

            active_payload = None
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                active_response = app.handle_request(
                    "GET",
                    "/api/workbench/settings/data-reset/jobs/active",
                    headers={"Authorization": "Bearer admin-token"},
                )
                active_payload = json.loads(active_response.body)["job"]
                if active_payload is not None and active_payload["status"] == "running":
                    break
                time.sleep(0.02)

            release_job.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                completed_response = app.handle_request(
                    "GET",
                    f"/api/workbench/settings/data-reset/jobs/{job_id}",
                    headers={"Authorization": "Bearer admin-token"},
                )
                completed_payload = json.loads(completed_response.body)["job"]
                if completed_payload["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.02)

        self.assertEqual(create_response.status_code, 202)
        self.assertEqual(active_response.status_code, 200)
        self.assertIsNotNone(active_payload)
        self.assertEqual(active_payload["job_id"], job_id)
        self.assertEqual(active_payload["action"], RESET_BANK_TRANSACTIONS_ACTION)
        self.assertEqual(active_payload["status"], "running")
        self.assertGreater(active_payload["percent"], 0)

    def test_reset_oa_job_rebuilds_progress_with_retained_months_only(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=["YNSYLP005"],
                oa_retention={"cutoff_date": "2026-02-01"},
            )
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: (
                token == "admin-token" and password == "correct-password"
            )
            adapter = RetentionScopedMongoWorkbenchOAAdapter(
                form_documents={
                    "2": [
                        {
                            "_id": "payment-doc-old",
                            "form_id": "2",
                            "data": {
                                "applicationDate": "2026-01-20",
                                "userName": "旧单据",
                                "fromTitle": "支付申请",
                                "amount": "100",
                                "beneficiary": "旧供应商",
                                "cause": "旧付款",
                                "projectName": "oa-project-001",
                                "flowRequestId": "2046",
                            },
                        },
                        {
                            "_id": "payment-doc-new",
                            "form_id": "2",
                            "data": {
                                "applicationDate": "2026-02-20",
                                "userName": "近期单据",
                                "fromTitle": "支付申请",
                                "amount": "200",
                                "beneficiary": "新供应商",
                                "cause": "近期付款",
                                "projectName": "oa-project-001",
                                "flowRequestId": "2047",
                            },
                        },
                    ],
                    "32": [],
                },
                project_documents=[
                    {"_id": "oa-project-001", "data": {"name": "云南溯源科技", "code": "YNSY"}},
                ],
            )
            app._workbench_query_service._oa_adapter = adapter

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset/jobs",
                body=json.dumps(
                    {
                        "action": RESET_OA_AND_REBUILD_ACTION,
                        "oa_password": "correct-password",
                    }
                ),
                headers={"Authorization": "Bearer admin-token"},
            )
            payload = json.loads(response.body)
            job_id = payload["job"]["job_id"]

            deadline = time.monotonic() + 3
            job_payload = payload["job"]
            while time.monotonic() < deadline:
                query_response = app.handle_request(
                    "GET",
                    f"/api/workbench/settings/data-reset/jobs/{job_id}",
                    headers={"Authorization": "Bearer admin-token"},
                )
                job_payload = json.loads(query_response.body)["job"]
                if job_payload["status"] == "completed":
                    break
                time.sleep(0.02)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(query_response.status_code, 200)
        self.assertEqual(job_payload["status"], "completed")
        self.assertEqual(job_payload["percent"], 100)
        self.assertEqual(job_payload["result"]["rebuild_status"], "completed")

    def test_reset_api_allows_local_dev_admin_with_local_dev_password(self) -> None:
        with self._without_default_test_auth(), self._temporary_env(
            FIN_OPS_DEV_ALLOW_LOCAL_SESSION="1",
            FIN_OPS_DEV_USERNAME="local_finops_admin",
            FIN_OPS_DEV_OA_PASSWORD="local-reset-password",
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            def fail_if_real_oa_password_verification_is_called(token: str, password: str) -> bool:
                raise AssertionError("local dev reset must not call real OA password verification")

            app._oa_identity_service.verify_current_user_password = fail_if_real_oa_password_verification_is_called
            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset",
                body=json.dumps(
                    {
                        "action": RESET_BANK_TRANSACTIONS_ACTION,
                        "oa_password": "local-reset-password",
                    }
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["action"], RESET_BANK_TRANSACTIONS_ACTION)
        self.assertNotIn("local-reset-password", response.body)

    def test_reset_oa_api_uses_mode_b_and_rebuilds_with_oa_retention_cutoff(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=["YNSYLP005"],
                oa_retention={"cutoff_date": "2026-02-01"},
            )
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: (
                token == "admin-token" and password == "correct-password"
            )
            app._state_store.save_oa_attachment_invoice_cache_entry("cache-oa-old", {"invoice_no": "INV-OLD"})
            app._workbench_read_model_service.upsert_read_model(
                scope_key="all",
                payload={
                    "month": "all",
                    "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 1, "exception_count": 0},
                    "paired": {"groups": []},
                    "open": {"groups": [{"group_id": "old", "oa_rows": [{"id": "oa-stale"}], "bank_rows": [], "invoice_rows": []}]},
                },
            )
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-STALE",
                row_ids=["oa-stale"],
                row_types=["oa"],
                relation_mode="manual_confirmed",
                created_by="tester",
            )
            app._workbench_override_service.mark_exception(
                row={"id": "oa-stale", "type": "oa"},
                exception_code="manual_review",
            )
            raw_payload = _build_retention_raw_payload(
                oa_rows=[
                    _build_retention_oa_row("oa-before-cutoff", "CASE-BEFORE", "2026-01-20"),
                    _build_retention_oa_row("oa-after-cutoff", "CASE-AFTER", "2026-02-02"),
                ],
                bank_rows=[],
                invoice_rows=[],
            )

            with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload) as raw_builder:
                response = app.handle_request(
                    "POST",
                    "/api/workbench/settings/data-reset",
                    body=json.dumps(
                        {
                            "action": RESET_OA_AND_REBUILD_ACTION,
                            "oa_password": "correct-password",
                        }
                    ),
                    headers={"Authorization": "Bearer admin-token"},
                )
            payload = json.loads(response.body)
            rebuilt_payload = app._build_api_workbench_payload("all")
            retained_attachment_cache_entry = app._state_store.load_oa_attachment_invoice_cache_entry("cache-oa-old")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["action"], RESET_OA_AND_REBUILD_ACTION)
        self.assertEqual(payload["rebuild_status"], "completed")
        self.assertEqual(
            payload["cleared_collections"],
            [
                "workbench_row_overrides",
                "workbench_pair_relations",
                "workbench_read_models",
            ],
        )
        self.assertNotIn("oa_attachment_invoice_cache", payload["deleted_counts"])
        self.assertEqual(payload["deleted_counts"]["workbench_read_models"], 1)
        self.assertEqual(payload["deleted_counts"]["workbench_pair_relations"], 1)
        self.assertEqual(payload["deleted_counts"]["workbench_row_overrides"], 1)
        self.assertIsNotNone(retained_attachment_cache_entry)
        self.assertEqual(retained_attachment_cache_entry["invoice_no"], "INV-OLD")
        self.assertEqual(app._workbench_pair_relation_service.snapshot()["pair_relations"], {})
        self.assertEqual(app._workbench_override_service.snapshot()["row_overrides"], {})
        raw_builder.assert_called_once_with("all")
        rebuilt_oa_ids = _flatten_group_rows(rebuilt_payload, "oa")
        self.assertNotIn("oa-before-cutoff", rebuilt_oa_ids)
        self.assertIn("oa-after-cutoff", rebuilt_oa_ids)

    def test_reset_oa_and_rebuild_imports_only_configured_oa_form_types_and_statuses(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "oa_mongo_config.json").write_text(
                json.dumps(
                    {
                        "host": "127.0.0.1",
                        "database": "form_data_db",
                        "cache_ttl_seconds": 0,
                    }
                ),
                encoding="utf-8",
            )
            app = build_application(data_dir=data_dir)
            app._app_settings_service._oa_import_options_provider = None
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=["YNSYLP005"],
                oa_retention={"cutoff_date": "2026-01-01"},
                oa_import={
                    "form_types": ["payment_request"],
                    "statuses": ["completed"],
                },
            )
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: (
                token == "admin-token" and password == "correct-password"
            )
            form_documents = {
                "2": [
                    {
                        "_id": "payment-completed",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请单",
                            "amount": "199",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "cause": "托收电话费及宽带",
                            "projectName": "project-001",
                            "flowRequestId": "2047",
                            "processStatus": "2",
                        },
                    },
                    {
                        "_id": "payment-in-progress",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-17",
                            "userName": "樊祖芳",
                            "fromTitle": "支付申请",
                            "amount": "88050",
                            "beneficiary": "云南辰飞机电工程有限公司",
                            "cause": "空气源热泵预付款",
                            "projectName": "project-001",
                            "flowRequestId": "2048",
                            "processStatus": "1",
                        },
                    },
                ],
                "32": [
                    {
                        "_id": "expense-completed",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-001",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "project-001",
                                    "detailReimbursementAmount": "127",
                                    "feeContent": "角磨机",
                                }
                            ],
                        },
                    }
                ],
            }
            load_calls: list[tuple[str, str | None]] = []

            def load_form_documents(adapter: MongoOAAdapter, form_id: str, month: str | None = None) -> list[dict]:
                load_calls.append((str(form_id), month))
                documents = list(form_documents.get(str(form_id), []))
                if month is None:
                    return documents
                return [
                    document
                    for document in documents
                    if str(
                        document.get("data", {}).get("applicationDate")
                        or document.get("data", {}).get("ApplicationDate")
                        or ""
                    ).startswith(month)
                ]

            def load_form_month_documents(adapter: MongoOAAdapter, form_id: str) -> list[dict]:
                load_calls.append((str(form_id), None))
                return list(form_documents.get(str(form_id), []))

            with patch.object(MongoOAAdapter, "_load_project_documents", autospec=True, return_value=[]), patch.object(
                MongoOAAdapter,
                "_load_form_documents",
                autospec=True,
                side_effect=load_form_documents,
            ), patch.object(
                MongoOAAdapter,
                "_load_form_month_documents",
                autospec=True,
                side_effect=load_form_month_documents,
            ):
                response = app.handle_request(
                    "POST",
                    "/api/workbench/settings/data-reset",
                    body=json.dumps(
                        {
                            "action": RESET_OA_AND_REBUILD_ACTION,
                            "oa_password": "correct-password",
                        }
                    ),
                    headers={"Authorization": "Bearer admin-token"},
                )
                rebuilt_payload = app._build_api_workbench_payload("all")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["rebuild_status"], "completed")
        rebuilt_oa_ids = _flatten_group_rows(rebuilt_payload, "oa")
        self.assertEqual(rebuilt_oa_ids, ["oa-pay-2047"])
        self.assertNotIn("oa-pay-2048", rebuilt_oa_ids)
        self.assertFalse(any(form_id == "32" for form_id, _month in load_calls))

    def test_reset_oa_and_rebuild_reuses_cached_attachment_invoices_without_reparsing(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "oa_mongo_config.json").write_text(
                json.dumps(
                    {
                        "host": "127.0.0.1",
                        "database": "form_data_db",
                        "cache_ttl_seconds": 0,
                    }
                ),
                encoding="utf-8",
            )
            app = build_application(data_dir=data_dir)
            app._app_settings_service._oa_import_options_provider = None
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=["YNSYLP005"],
                oa_retention={"cutoff_date": "2026-01-01"},
                oa_import={
                    "form_types": ["expense_claim"],
                    "statuses": ["completed"],
                },
            )
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: (
                token == "admin-token" and password == "correct-password"
            )
            form_documents = {
                "2": [],
                "32": [
                    {
                        "_id": "expense-with-attachment",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-attach-001",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "project-001",
                                    "detailReimbursementAmount": "127",
                                    "feeContent": "角磨机",
                                    "detailReimbursementAttachment": {
                                        "list": [
                                            {
                                                "status": "success",
                                                "name": "invoice-a.pdf",
                                                "response": {
                                                    "extra": {
                                                        "filePath": "/oa/invoice-a.pdf",
                                                        "fileName": "invoice-a.pdf",
                                                        "suffix": "pdf",
                                                    }
                                                },
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                    }
                ],
            }

            def load_form_documents(adapter: MongoOAAdapter, form_id: str, month: str | None = None) -> list[dict]:
                documents = list(form_documents.get(str(form_id), []))
                if month is None:
                    return documents
                return [
                    document
                    for document in documents
                    if str(
                        document.get("data", {}).get("applicationDate")
                        or document.get("data", {}).get("ApplicationDate")
                        or ""
                    ).startswith(month)
                ]

            def load_form_month_documents(adapter: MongoOAAdapter, form_id: str) -> list[dict]:
                return list(form_documents.get(str(form_id), []))

            parsed_invoice = {
                "invoice_no": "40512344",
                "seller_name": "云南顺丰速运有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-18",
                "amount": "119.81",
                "tax_amount": "7.19",
                "total_with_tax": "127.00",
                "attachment_name": "invoice-a.pdf",
            }
            cache_key = MongoOAAdapter._attachment_invoice_cache_key(
                {"fileName": "invoice-a.pdf", "filePath": "/oa/invoice-a.pdf", "suffix": "pdf"}
            )
            app._state_store.save_oa_attachment_invoice_cache_entry(
                cache_key,
                {
                    "cache_key": cache_key,
                    "parser_version": OAAttachmentInvoiceService.PARSER_VERSION,
                    "invoices": [parsed_invoice],
                    "parsed_at": "2026-04-01T00:00:00",
                },
            )
            with patch.object(MongoOAAdapter, "_load_project_documents", autospec=True, return_value=[]), patch.object(
                MongoOAAdapter,
                "_load_form_documents",
                autospec=True,
                side_effect=load_form_documents,
            ), patch.object(
                MongoOAAdapter,
                "_load_form_month_documents",
                autospec=True,
                side_effect=load_form_month_documents,
            ), patch(
                "fin_ops_platform.services.mongo_oa_adapter.OAAttachmentInvoiceService.parse_files",
                side_effect=AssertionError("reset OA should not re-run attachment invoice OCR"),
            ) as parse_files:
                response = app.handle_request(
                    "POST",
                    "/api/workbench/settings/data-reset",
                    body=json.dumps(
                        {
                            "action": RESET_OA_AND_REBUILD_ACTION,
                            "oa_password": "correct-password",
                        }
                    ),
                    headers={"Authorization": "Bearer admin-token"},
                )
                rebuilt_payload = app._build_api_workbench_payload("all")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["rebuild_status"], "completed")
        parse_files.assert_not_called()
        rebuilt_invoice_ids = _flatten_group_rows(rebuilt_payload, "invoice")
        self.assertEqual(rebuilt_invoice_ids, ["oa-att-inv-oa-exp-exp-attach-001-0-01"])
        invoice_rows = _flatten_group_payload_rows(rebuilt_payload, "invoice")
        self.assertEqual(invoice_rows[0]["source_kind"], "oa_attachment_invoice")
        self.assertEqual(invoice_rows[0]["detail_fields"]["发票号码"], "40512344")

    def test_reset_oa_attachment_parse_is_limited_to_retained_months(self) -> None:
        class CaptureParseAdapter:
            def __init__(self) -> None:
                self.parsed_months: list[str] = []

            def list_available_months(self) -> list[str]:
                return ["2023-06", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04"]

            def parse_attachment_invoices_for_months(self, months: list[str]) -> None:
                self.parsed_months.extend(months)

        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_retention={"cutoff_date": "2026-01-01"},
            )
            adapter = CaptureParseAdapter()
            app._workbench_query_service._oa_adapter = adapter

            app._parse_oa_attachment_invoices_for_reset_rebuild()

        self.assertEqual(adapter.parsed_months, ["2026-01", "2026-02", "2026-03", "2026-04"])

    def test_reset_api_rejects_missing_oa_password_without_clearing_data(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: True
            bank_preview = app._import_service.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name="bank-demo.json",
                imported_by="tester",
                rows=[
                    {
                        "account_no": "62229999",
                        "txn_date": "2026-03-24",
                        "counterparty_name": "Vendor A",
                        "debit_amount": "50.00",
                        "credit_amount": "",
                        "bank_serial_no": "SERIAL-RESET-PASSWORD-001",
                        "summary": "purchase",
                    }
                ],
            )
            app._import_service.confirm_import(bank_preview.id)
            app._state_store.save({"imports": app._import_service.snapshot()})

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset",
                body=json.dumps({"action": RESET_BANK_TRANSACTIONS_ACTION}),
                headers={"Authorization": "Bearer admin-token"},
            )
            payload = json.loads(response.body)
            persisted = app._state_store.load()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "oa_password_verification_failed")
        self.assertNotIn("oa_password", payload)
        self.assertEqual(len(persisted["imports"]["transactions"]), 1)

    def test_reset_api_rejects_wrong_oa_password_without_clearing_data_or_echoing_secret(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: False
            bank_preview = app._import_service.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name="bank-demo.json",
                imported_by="tester",
                rows=[
                    {
                        "account_no": "62229999",
                        "txn_date": "2026-03-24",
                        "counterparty_name": "Vendor A",
                        "debit_amount": "50.00",
                        "credit_amount": "",
                        "bank_serial_no": "SERIAL-RESET-PASSWORD-002",
                        "summary": "purchase",
                    }
                ],
            )
            app._import_service.confirm_import(bank_preview.id)
            app._state_store.save({"imports": app._import_service.snapshot()})

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset",
                body=json.dumps(
                    {
                        "action": RESET_BANK_TRANSACTIONS_ACTION,
                        "oa_password": "wrong-password",
                    }
                ),
                headers={"Authorization": "Bearer admin-token"},
            )
            payload = json.loads(response.body)
            persisted = app._state_store.load()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "oa_password_verification_failed")
        self.assertNotIn("oa_password", payload)
        self.assertNotIn("wrong-password", response.body)
        self.assertEqual(len(persisted["imports"]["transactions"]), 1)

    def test_reset_api_does_not_leak_oa_password_when_verification_service_fails(self) -> None:
        secret = "wrong-password-must-not-leak"
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )

            def raise_verification_failure(token: str, password: str) -> bool:
                raise OAIdentityServiceError(f"upstream verification failed for {password}")

            app._oa_identity_service.verify_current_user_password = raise_verification_failure
            with patch.object(app._settings_data_reset_service, "execute") as execute_reset:
                response = app.handle_request(
                    "POST",
                    "/api/workbench/settings/data-reset",
                    body=json.dumps(
                        {
                            "action": RESET_BANK_TRANSACTIONS_ACTION,
                            "oa_password": secret,
                        }
                    ),
                    headers={"Authorization": "Bearer admin-token"},
                )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(payload["error"], "oa_password_verification_unavailable")
        self.assertNotIn(secret, response.body)
        execute_reset.assert_not_called()
        self.assertFalse(
            any(secret in json.dumps(entry, ensure_ascii=False) for entry in app._audit_service.as_dicts())
        )

    def test_reset_api_rejects_wrong_oa_password_without_clearing_oa_or_rebuilding(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="1",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                dept_id="01",
                dept_name="财务部",
                roles=["finance_admin"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda token, password: False
            app._state_store.save_oa_attachment_invoice_cache_entry("cache-keep", {"invoice_no": "INV-KEEP"})
            app._workbench_read_model_service.upsert_read_model(
                scope_key="all",
                payload={
                    "month": "all",
                    "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 1, "exception_count": 0},
                    "paired": {"groups": []},
                    "open": {"groups": [{"group_id": "keep", "oa_rows": [{"id": "oa-keep"}], "bank_rows": [], "invoice_rows": []}]},
                },
            )

            with patch.object(app._settings_data_reset_service, "execute") as execute_reset, patch.object(
                app,
                "_build_api_workbench_payload",
                side_effect=AssertionError("should not rebuild OA when password verification fails"),
            ):
                response = app.handle_request(
                    "POST",
                    "/api/workbench/settings/data-reset",
                    body=json.dumps(
                        {
                            "action": RESET_OA_AND_REBUILD_ACTION,
                            "oa_password": "wrong-password",
                        }
                    ),
                    headers={"Authorization": "Bearer admin-token"},
            )
            payload = json.loads(response.body)
            retained_cache_entry = app._state_store.load_oa_attachment_invoice_cache_entry("cache-keep")
            retained_read_model = app._workbench_read_model_service.get_read_model("all")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "oa_password_verification_failed")
        execute_reset.assert_not_called()
        self.assertIsNotNone(retained_cache_entry)
        self.assertIsNotNone(retained_read_model)


def _build_retention_raw_payload(
    *,
    oa_rows: list[dict[str, object]],
    bank_rows: list[dict[str, object]],
    invoice_rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "month": "all",
        "summary": {
            "oa_count": len(oa_rows),
            "bank_count": len(bank_rows),
            "invoice_count": len(invoice_rows),
            "paired_count": 0,
            "open_count": len(oa_rows) + len(bank_rows) + len(invoice_rows),
            "exception_count": 0,
        },
        "paired": {"oa": [], "bank": [], "invoice": []},
        "open": {"oa": oa_rows, "bank": bank_rows, "invoice": invoice_rows},
    }


def _build_retention_oa_row(row_id: str, case_id: str, application_date: str) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "case_id": case_id,
        "applicant": "测试申请人",
        "project_name": "测试项目",
        "apply_type": "支付申请",
        "amount": "100.00",
        "counterparty_name": "测试供应商",
        "reason": "测试保OA",
        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
        "available_actions": ["detail"],
        "summary_fields": {"申请人": "测试申请人"},
        "detail_fields": {"申请日期": application_date},
    }


def _flatten_group_rows(payload: dict[str, object], row_type: str) -> list[str]:
    return [str(row["id"]) for row in _flatten_group_payload_rows(payload, row_type)]


def _flatten_group_payload_rows(payload: dict[str, object], row_type: str) -> list[dict[str, object]]:
    row_key = f"{row_type}_rows"
    groups = [*list(payload["paired"]["groups"]), *list(payload["open"]["groups"])]
    return [row for group in groups for row in list(group.get(row_key, []))]


if __name__ == "__main__":
    unittest.main()
