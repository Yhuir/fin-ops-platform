import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from pymongo.errors import NetworkTimeout

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncError


class ExplodingSyncService:
    def sync_access_control(self, snapshot: dict[str, object]) -> None:
        raise OARoleSyncError("OA role sync failed")


class ExplodingProjectAdapter:
    name = "exploding_project_adapter"

    def fetch_counterparties(self) -> list[dict[str, Any]]:
        return []

    def fetch_projects(self) -> list[dict[str, Any]]:
        raise RuntimeError("OA project sync failed")

    def fetch_documents(self, scope: str) -> list[dict[str, Any]]:
        return []


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

    def test_settings_update_returns_clear_error_when_app_mongo_save_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            def raise_timeout(_: dict[str, Any]) -> None:
                raise NetworkTimeout("139.155.5.132:27017: timed out")

            app._state_store.save_app_settings = raise_timeout

            response = app.handle_request(
                "POST",
                "/api/workbench/settings",
                body=json.dumps(
                    {
                        "completed_project_ids": [],
                        "bank_account_mappings": [],
                        "allowed_usernames": [],
                        "readonly_export_usernames": [],
                        "admin_usernames": [],
                    }
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "app_settings_persistence_failed")
        self.assertIn("无法写入 app Mongo", payload["message"])

    def test_project_sync_endpoint_syncs_oa_projects_into_settings_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/projects/sync",
                body=json.dumps({"actor_id": "settings_test"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["sync"]["scope"], "projects")
        self.assertEqual(payload["sync"]["status"], "succeeded")
        self.assertIn(
            "PJT-001",
            [project["project_code"] for project in payload["settings"]["projects"]["active"]],
        )
        self.assertEqual(payload["settings"]["projects"]["active"][0]["source"], "oa")

    def test_manual_project_create_and_delete_endpoints_persist_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            create_response = app.handle_request(
                "POST",
                "/api/workbench/settings/projects",
                body=json.dumps(
                    {
                        "actor_id": "settings_test",
                        "project_code": "LOCAL-001",
                        "project_name": "本地测试项目",
                    }
                ),
            )
            create_payload = json.loads(create_response.body)
            project_id = create_payload["settings"]["projects"]["active"][0]["id"]

            reloaded_payload = json.loads(
                build_application(data_dir=Path(temp_dir)).handle_request("GET", "/api/workbench/settings").body
            )
            delete_response = app.handle_request(
                "DELETE",
                f"/api/workbench/settings/projects/{project_id}",
            )
            delete_payload = json.loads(delete_response.body)

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_payload["settings"]["projects"]["active"][0]["source"], "manual")
        self.assertEqual(reloaded_payload["projects"]["active"][0]["project_name"], "本地测试项目")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_payload["settings"]["projects"]["active"], [])

    def test_project_sync_endpoint_failure_does_not_destroy_existing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.create_manual_project(
                actor_id="settings_test",
                project_code="LOCAL-001",
                project_name="本地测试项目",
            )
            app._integration_service._adapter = ExplodingProjectAdapter()

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/projects/sync",
                body=json.dumps({"actor_id": "settings_test"}),
            )
            payload = json.loads(response.body)
            settings_payload = json.loads(app.handle_request("GET", "/api/workbench/settings").body)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(payload["error"], "oa_project_sync_failed")
        self.assertEqual(settings_payload["projects"]["active"][0]["project_name"], "本地测试项目")


if __name__ == "__main__":
    unittest.main()
