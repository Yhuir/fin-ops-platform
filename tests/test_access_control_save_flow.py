import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

from fin_ops_platform.services.app_settings_service import AppSettingsPersistenceError
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncError, OAUserSummary

from tests.app_test_support import build_local_state_application
from tests.test_app_settings_service import RecordingSyncService


class AccessControlSaveFlowTests(unittest.TestCase):
    def test_unchanged_deleted_account_does_not_block_another_accounts_page_change(self):
        with tempfile.TemporaryDirectory() as directory:
            app = build_local_state_application(data_dir=Path(directory))
            service = app._app_settings_service
            sync = RecordingSyncService()
            service._oa_role_sync_service = sync
            accounts = [
                {"username": "OLDUSER", "page_keys": ["settings"]},
                {"username": "USER001", "page_keys": ["settings"]},
            ]
            args = dict(actor_id="YNSYLP005", actor_name="admin", request_id="historical-inactive")
            first = service.update_access_control(expected_version=1, accounts=accounts, **args)
            sync.calls.clear()
            sync.resolve_users = Mock(return_value=[
                OAUserSummary("YNSYLP005", "管理员", True), OAUserSummary("USER001", "用户", True),
            ])
            accounts[1] = {"username": "USER001", "page_keys": ["bank-details"]}
            result = service.update_access_control(expected_version=first["version"], accounts=accounts, **args)
            self.assertTrue(result["changed"])
            self.assertEqual(result["version"], first["version"] + 1)
            self.assertEqual(sync.calls, [])
            self.assertEqual(result["accounts"][0]["oa_status"], "missing")
            self.assertEqual(result["accounts"][1]["page_keys"], ["bank-details"])

    def test_page_change_uses_one_directory_read_no_role_write_and_returns_committed_version(self):
        with tempfile.TemporaryDirectory() as directory:
            app = build_local_state_application(data_dir=Path(directory))
            service = app._app_settings_service
            sync = RecordingSyncService()
            service._oa_role_sync_service = sync
            def save(version, pages):
                return service.update_access_control(expected_version=version,
                    accounts=[{"username": "USER001", "page_keys": pages}],
                    actor_id="YNSYLP005", actor_name="admin", request_id="page-change")
            first = save(1, ["settings"])
            sync.calls.clear()
            sync.resolve_users = Mock(side_effect=[[
                OAUserSummary("YNSYLP005", "管理员", True), OAUserSummary("USER001", "用户", True),
            ]])
            result = save(first["version"], ["bank-details"])
            self.assertEqual(result["version"], first["version"] + 1)
            self.assertEqual(result["accounts"][0]["page_keys"], ["bank-details"])
            self.assertEqual(result["accounts"][0]["display_name"], "用户")
            self.assertEqual(sync.calls, [])
            self.assertEqual(sync.resolve_users.call_count, 1)
            self.assertEqual(service.get_access_control_snapshot()["access_control_version"], result["version"])

    def test_invalid_changed_account_and_directory_failure_do_not_write(self):
        for failure in [False, True]:
            with self.subTest(directory_failure=failure), tempfile.TemporaryDirectory() as directory:
                app = build_local_state_application(data_dir=Path(directory))
                service = app._app_settings_service
                sync = RecordingSyncService()
                service._oa_role_sync_service = sync
                sync.resolve_users = Mock(side_effect=OARoleSyncError("offline")) if failure else Mock(return_value=[])
                with self.assertRaises(OARoleSyncError):
                    service.update_access_control(expected_version=1,
                        accounts=[{"username": "deleted", "page_keys": ["settings"]}],
                        actor_id="YNSYLP005", actor_name="admin", request_id="invalid-account")
                self.assertEqual(sync.calls, [])
                self.assertEqual(service.get_access_control_snapshot()["access_control_version"], 1)

    def test_page_only_persistence_failure_never_compensates_oa(self):
        with tempfile.TemporaryDirectory() as directory:
            app = build_local_state_application(data_dir=Path(directory))
            service = app._app_settings_service
            sync = RecordingSyncService()
            service._oa_role_sync_service = sync
            args = dict(actor_id="YNSYLP005", actor_name="admin", request_id="page-db-failure")
            service.update_access_control(expected_version=1, accounts=[{"username": "USER001", "page_keys": ["settings"]}], **args)
            sync.calls.clear()
            original = app._state_store.begin_settings_acl_critical_section
            @contextmanager
            def failing(version):
                with original(version) as section:
                    section.commit = Mock(side_effect=RuntimeError("DB unavailable"))
                    yield section
            app._state_store.begin_settings_acl_critical_section = failing
            with self.assertRaises(AppSettingsPersistenceError):
                service.update_access_control(expected_version=2, accounts=[{"username": "USER001", "page_keys": ["bank-details"]}], **args)
            self.assertEqual(sync.calls, [])
            self.assertEqual(sync.restored, [])
            self.assertEqual(service.get_access_control_snapshot()["access_control_version"], 2)
