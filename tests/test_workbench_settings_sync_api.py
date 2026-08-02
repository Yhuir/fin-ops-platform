import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pymongo.errors import NetworkTimeout

from tests.app_test_support import (
    build_local_state_application as build_application,
    configure_access_control,
)
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
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
    def _readonly_identity(self) -> OAUserIdentity:
        return OAUserIdentity(
            user_id="readonly-user-id",
            username="READONLY001",
            nickname="只读用户",
            display_name="只读用户",
            roles=["finance"],
            permissions=["finops:access"],
        )

    def test_settings_update_returns_bad_gateway_when_oa_role_sync_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service._oa_role_sync_service = ExplodingSyncService()
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="admin-id",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                roles=[],
                permissions=[],
            )

            response = app.handle_request(
                "PUT",
                "/api/workbench/settings/access-control",
                body=json.dumps(
                    {
                        "expected_version": 1,
                        "accounts": [
                            {"username": "YNSYLP006", "access_tier": "read_export_only"}
                        ],
                    }
                ),
                headers={"Authorization": "Bearer admin"},
            )
            payload = json.loads(response.body)
            settings_payload = app._app_settings_service.get_access_control_payload()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(payload["error"], "oa_role_sync_failed")
        self.assertEqual(settings_payload["accounts"], [])

    def test_only_protected_admin_can_use_versioned_access_control_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, full_access=["FULL001"])
            identities = {
                "admin": OAUserIdentity(
                    user_id="admin-id",
                    username="YNSYLP005",
                    nickname="管理员",
                    display_name="管理员",
                    roles=[],
                    permissions=[],
                ),
                "full": OAUserIdentity(
                    user_id="full-id",
                    username="FULL001",
                    nickname="业务用户",
                    display_name="业务用户",
                    roles=[],
                    permissions=["finops:app:view"],
                ),
            }
            app._oa_identity_service.resolve_identity = lambda token: identities[token]

            attack = app.handle_request(
                "POST",
                "/api/workbench/settings",
                body=json.dumps({"admin_usernames": ["FULL001"]}),
                headers={"Authorization": "Bearer full"},
            )
            forbidden = app.handle_request(
                "PUT",
                "/api/workbench/settings/access-control",
                body=json.dumps({"expected_version": 1, "accounts": []}),
                headers={"Authorization": "Bearer full"},
            )
            updated = app.handle_request(
                "PUT",
                "/api/workbench/settings/access-control",
                body=json.dumps(
                    {
                        "expected_version": 2,
                        "accounts": [],
                    }
                ),
                headers={"Authorization": "Bearer admin", "X-Request-ID": "spoofed-client-id"},
                request_id="server-request-id",
            )
            stale = app.handle_request(
                "PUT",
                "/api/workbench/settings/access-control",
                body=json.dumps({"expected_version": 2, "accounts": []}),
                headers={"Authorization": "Bearer admin"},
            )
            generic_payload = json.loads(app.handle_request("GET", "/api/workbench/settings").body)
            audit_events = json.loads((Path(temp_dir) / "app_settings.json").read_text(encoding="utf-8"))[
                "_settings_acl_audit_events"
            ]

        self.assertEqual(attack.status_code, 400)
        self.assertEqual(json.loads(attack.body)["error"], "access_control_write_forbidden")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(json.loads(updated.body)["version"], 3)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(json.loads(stale.body)["current_version"], 3)
        self.assertNotIn("access_control", generic_payload)
        self.assertEqual(audit_events[-1]["request_id"], "server-request-id")
        self.assertNotEqual(audit_events[-1]["request_id"], "spoofed-client-id")

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
                    }
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "app_settings_persistence_failed")
        self.assertIn("无法写入持久化设置源", payload["message"])

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

    def test_project_mutation_endpoints_reject_readonly_session_even_with_spoofed_actor(self) -> None:
        with (
            patch.dict(os.environ, {"FIN_OPS_TEST_DEFAULT_AUTH": "0"}),
            tempfile.TemporaryDirectory() as temp_dir,
        ):
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, read_export_only=["READONLY001"])
            created_payload = app._app_settings_service.create_manual_project(
                actor_id="settings_owner",
                project_code="LOCAL-001",
                project_name="本地测试项目",
            )
            project_id = created_payload["projects"]["active"][0]["id"]
            app._oa_identity_service.resolve_identity = lambda _token: self._readonly_identity()
            headers = {"Authorization": "Bearer readonly-token"}

            with patch.object(app._project_costing_service, "sync_projects_from_oa") as sync_projects:
                sync_response = app.handle_request(
                    "POST",
                    "/api/workbench/settings/projects/sync",
                    body=json.dumps({"actor_id": "spoofed-owner"}),
                    headers=headers,
                )
                create_response = app.handle_request(
                    "POST",
                    "/api/workbench/settings/projects",
                    body=json.dumps(
                        {
                            "actor_id": "spoofed-owner",
                            "project_code": "LOCAL-002",
                            "project_name": "伪造项目",
                        }
                    ),
                    headers=headers,
                )
                delete_response = app.handle_request(
                    "DELETE",
                    f"/api/workbench/settings/projects/{project_id}",
                    headers=headers,
                )

            settings_payload = app._app_settings_service.get_settings_payload()

        self.assertEqual(sync_response.status_code, 403)
        self.assertEqual(json.loads(sync_response.body)["error"], "permission_denied")
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(json.loads(create_response.body)["error"], "permission_denied")
        self.assertEqual(delete_response.status_code, 403)
        self.assertEqual(json.loads(delete_response.body)["error"], "permission_denied")
        sync_projects.assert_not_called()
        self.assertEqual([project["project_code"] for project in settings_payload["projects"]["active"]], ["LOCAL-001"])


if __name__ == "__main__":
    unittest.main()
