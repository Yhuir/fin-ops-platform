import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.state_store import ApplicationStateStore
from tests.app_test_support import build_local_state_application, configure_default_test_access


class SettingsRetirementTests(unittest.TestCase):
    def test_normalization_removes_only_retired_settings_and_preserves_project_records(self):
        project = {"id": "proj_manual_0001", "project_code": "LOCAL", "project_name": "保留项目", "project_status": "active", "department_name": None, "owner_name": None}
        baseline = AppSettingsService.normalize_settings_payload({"manual_projects": [project], "synced_projects": [dict(project, id="oa-project")]})
        retired = {**baseline, "completed_project_ids": [project["id"]], "oa_invoice_offset": {"applicant_names": ["历史申请人"]}}
        self.assertEqual(AppSettingsService.normalize_settings_payload(retired), AppSettingsService.normalize_settings_payload(baseline))
        self.assertEqual(baseline["manual_projects"], [project])
        self.assertEqual(len(baseline["synced_projects"]), 1)

    def test_general_save_preserves_dedicated_rules_projects_and_prefill(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ApplicationStateStore(Path(directory))
            snapshot = AppSettingsService.normalize_settings_payload({
                "manual_projects": [{"id": "proj_manual_0001", "project_code": "LOCAL", "project_name": "保留项目"}],
                "pending_invoice_tag_groups": {"version": 9, "groups": {"requires_invoice": {"tag_codes": ["historical-missing-tag"]}}},
            })
            store.save_app_settings(snapshot)
            app = build_local_state_application(data_dir=Path(directory))
            try:
                before = store.load_app_settings()
                saved = app._app_settings_service.update_settings(bank_account_mappings=[{"last4": "1234", "bank_name": "测试银行", "short_name": "测试"}])
                after = store.load_app_settings()
                for key in ("manual_projects", "synced_projects", "pending_invoice_tag_groups", "pending_output_invoice_tag_groups", "input_invoice_usage_payment_status_rules"):
                    self.assertEqual(after[key], before[key], key)
                self.assertNotIn("projects", saved)
                self.assertNotIn("oa_invoice_offset", saved)
                self.assertEqual(saved["bank_account_mappings"][0]["last4"], "1234")
                self.assertEqual(app._project_costing_service.get_project("proj_manual_0001").project_name, "保留项目")
            finally:
                app.close()

    def test_retired_routes_and_fields_cannot_write_or_restore_old_config(self):
        with tempfile.TemporaryDirectory() as directory:
            app = build_local_state_application(data_dir=Path(directory))
            configure_default_test_access(app)
            try:
                before = app._state_store.load_app_settings()
                for method, path in (("POST", "/api/workbench/settings/projects"), ("POST", "/api/workbench/settings/projects/sync"), ("DELETE", "/api/workbench/settings/projects/unused")):
                    response = app.handle_request(method, path, body="{}")
                    self.assertEqual(response.status_code, 404)
                for field, value in (("completed_project_ids", []), ("oa_invoice_offset", {}), ("pending_invoice_tag_groups", {}), ("pending_output_invoice_tag_groups", {})):
                    response = app.handle_request("POST", "/api/workbench/settings", body=json.dumps({field: value}))
                    payload = json.loads(response.body)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(payload["error"], "unsupported_settings_fields")
                    self.assertEqual(payload["fields"], [field])
                self.assertEqual(app._state_store.load_app_settings(), before)
            finally:
                app.close()

    def test_save_failure_does_not_report_success_or_replace_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            app = build_local_state_application(data_dir=Path(directory))
            try:
                service = app._app_settings_service
                before = service.get_settings_payload()
                with patch.object(app._state_store, "save_app_settings", side_effect=OSError("write failed")):
                    with self.assertRaisesRegex(OSError, "write failed"):
                        service.update_settings(bank_account_mappings=[{"last4": "1234", "bank_name": "不能写入"}])
                self.assertEqual(service.get_settings_payload(), before)
            finally:
                app.close()
