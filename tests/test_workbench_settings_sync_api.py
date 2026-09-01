import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pymongo.errors import NetworkTimeout

from tests.app_test_support import (
    build_local_state_application as build_application,
    configure_access_control,
)
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncError, OAUserSummary


class ExplodingSyncService:
    def sync_access_control(self, snapshot: dict[str, object]) -> None:
        raise OARoleSyncError("OA role sync failed")

    def resolve_users(self, usernames: list[str]) -> list[OAUserSummary]:
        return [OAUserSummary(username=username, display_name=username, active=True) for username in usernames]


class CompensationFailingSyncService:
    def __init__(self) -> None:
        self.calls = 0

    def sync_access_control(self, snapshot: dict[str, object]) -> None:
        del snapshot
        self.calls += 1
        if self.calls == 2:
            raise OARoleSyncError("OA compensation failed")

    def resolve_users(self, usernames: list[str]) -> list[OAUserSummary]:
        return [OAUserSummary(username=username, display_name=username, active=True) for username in usernames]


class ExplodingProjectAdapter:
    name = "exploding_project_adapter"

    def fetch_counterparties(self) -> list[dict[str, Any]]:
        return []

    def fetch_projects(self) -> list[dict[str, Any]]:
        raise RuntimeError("OA project sync failed")

    def fetch_documents(self, scope: str) -> list[dict[str, Any]]:
        return []


class WorkbenchSettingsSyncApiTests(unittest.TestCase):
    def _limited_identity(self) -> OAUserIdentity:
        return OAUserIdentity(
            user_id="limited-user-id",
            username="LIMITED001",
            nickname="受限用户",
            display_name="受限用户",
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
                            {"username": "YNSYLP006", "page_keys": ["settings"]}
                        ],
                    }
                ),
                headers={"Authorization": "Bearer admin"},
            )
            payload = json.loads(response.body)
            settings_payload = app._app_settings_service.get_access_control_snapshot()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(payload["error"], "oa_role_sync_failed")
        self.assertEqual(settings_payload["page_access_accounts"], [])

    def test_settings_update_returns_bad_gateway_when_oa_role_sync_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service._oa_role_sync_service = None
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
                        "accounts": [{"username": "YNSYLP006", "page_keys": ["settings"]}],
                    }
                ),
                headers={"Authorization": "Bearer admin"},
            )
            payload = json.loads(response.body)
            settings_payload = app._app_settings_service.get_access_control_snapshot()
            state_path = Path(temp_dir) / "app_settings.json"
            persisted = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

        self.assertEqual(response.status_code, 502)
        self.assertEqual(payload["error"], "oa_role_sync_failed")
        self.assertEqual(settings_payload["page_access_accounts"], [])
        self.assertEqual(persisted.get("_settings_acl_audit_events", []), [])

    def test_settings_update_keeps_existing_inconsistent_contract_when_compensation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            sync_service = CompensationFailingSyncService()
            app._app_settings_service._oa_role_sync_service = sync_service
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="admin-id",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                roles=[],
                permissions=[],
            )
            original_critical_section = app._state_store.begin_settings_acl_critical_section

            def failing_critical_section(expected_version: int):
                context = original_critical_section(expected_version)

                @contextmanager
                def wrapped():
                    with context as critical_section:
                        critical_section.commit = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            RuntimeError("synthetic DB failure")
                        )
                        yield critical_section

                return wrapped()

            app._state_store.begin_settings_acl_critical_section = failing_critical_section

            response = app.handle_request(
                "PUT",
                "/api/workbench/settings/access-control",
                body=json.dumps(
                    {
                        "expected_version": 1,
                        "accounts": [{"username": "FULL001", "page_keys": ["settings"]}],
                    }
                ),
                headers={"Authorization": "Bearer admin"},
            )
            payload = json.loads(response.body)
            settings_payload = app._app_settings_service.get_access_control_payload()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "access_control_sync_inconsistent")
        self.assertEqual(sync_service.calls, 2)
        self.assertEqual(settings_payload["accounts"], [])

    def test_only_protected_admin_can_use_versioned_access_control_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, usernames=["FULL001"])
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
            generic_payload = json.loads(
                app.handle_request(
                    "GET",
                    "/api/workbench/settings",
                    headers={"Authorization": "Bearer full"},
                ).body
            )
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

    def test_project_mutation_endpoints_reject_account_without_settings_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, page_access={"LIMITED001": ["bank-details"]})
            created_payload = app._app_settings_service.create_manual_project(
                actor_id="settings_owner",
                project_code="LOCAL-001",
                project_name="本地测试项目",
            )
            project_id = created_payload["projects"]["active"][0]["id"]
            app._oa_identity_service.resolve_identity = lambda _token: self._limited_identity()
            headers = {"Authorization": "Bearer limited-token"}

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
        self.assertEqual(json.loads(sync_response.body)["error"], "page_access_denied")
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(json.loads(create_response.body)["error"], "page_access_denied")
        self.assertEqual(delete_response.status_code, 403)
        self.assertEqual(json.loads(delete_response.body)["error"], "page_access_denied")
        sync_projects.assert_not_called()
        self.assertEqual([project["project_code"] for project in settings_payload["projects"]["active"]], ["LOCAL-001"])


if __name__ == "__main__":
    unittest.main()
