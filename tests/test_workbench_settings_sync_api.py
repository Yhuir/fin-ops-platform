import json
import tempfile
import unittest
from pathlib import Path

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncError


class ExplodingSyncService:
    def sync_access_control(self, snapshot: dict[str, object]) -> None:
        raise OARoleSyncError("OA role sync failed")


class WorkbenchSettingsSyncApiTests(unittest.TestCase):
    def test_settings_update_returns_bad_gateway_when_oa_role_sync_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service._oa_role_sync_service = ExplodingSyncService()

            response = app.handle_request(
                "POST",
                "/api/workbench/settings",
                body=json.dumps(
                    {
                        "completed_project_ids": [],
                        "bank_account_mappings": [],
                        "allowed_usernames": ["YNSYLP006"],
                        "readonly_export_usernames": ["YNSYLP006"],
                        "admin_usernames": ["YNSYLP005"],
                    }
                ),
            )
            payload = json.loads(response.body)
            settings_payload = json.loads(app.handle_request("GET", "/api/workbench/settings").body)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(payload["error"], "oa_role_sync_failed")
        self.assertEqual(settings_payload["access_control"]["allowed_usernames"], ["YNSYLP005"])
        self.assertEqual(settings_payload["access_control"]["readonly_export_usernames"], [])


if __name__ == "__main__":
    unittest.main()
