import json
import tempfile
import unittest
from pathlib import Path

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.oa_role_sync_service import OARoleAssignment


class RecordingSyncService:
    def __init__(self) -> None:
        self.assignments: list[OARoleAssignment] | None = None

    def sync_access_control(self, snapshot: dict[str, object]) -> None:
        readonly = [
            OARoleAssignment(username=str(username), tier="read_export_only")
            for username in list(snapshot.get("readonly_export_usernames") or [])
        ]
        full_access = [
            OARoleAssignment(username=str(username), tier="full_access")
            for username in list(snapshot.get("full_access_usernames") or [])
        ]
        admin = [
            OARoleAssignment(username=str(username), tier="admin")
            for username in list(snapshot.get("admin_usernames") or [])
        ]
        self.assignments = [*readonly, *full_access, *admin]


class AppSettingsServiceTests(unittest.TestCase):
    def test_update_settings_normalizes_access_control_lists_and_keeps_admin_in_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FULL001", "READONLY001"],
                readonly_export_usernames=["READONLY001", "OUTSIDER001", "YNSYLP005"],
                admin_usernames=["ADMIN002"],
            )

        access_control = payload["access_control"]
        self.assertEqual(
            access_control["allowed_usernames"],
            ["ADMIN002", "FULL001", "READONLY001", "YNSYLP005"],
        )
        self.assertEqual(access_control["readonly_export_usernames"], ["READONLY001"])
        self.assertEqual(access_control["admin_usernames"], ["ADMIN002", "YNSYLP005"])
        self.assertEqual(access_control["full_access_usernames"], ["FULL001"])

    def test_update_settings_persists_access_control_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FULL001"],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_retention={"cutoff_date": "2026-01-01"},
                workbench_column_layouts={"oa": ["projectName", "applicant"]},
            )

            reloaded_app = build_application(data_dir=Path(temp_dir))
            payload = reloaded_app._app_settings_service.get_settings_payload()

        access_control = payload["access_control"]
        self.assertEqual(access_control["allowed_usernames"], ["FULL001", "YNSYLP005"])
        self.assertEqual(access_control["readonly_export_usernames"], [])
        self.assertEqual(access_control["admin_usernames"], ["YNSYLP005"])
        self.assertEqual(access_control["full_access_usernames"], ["FULL001"])
        self.assertEqual(
            payload["workbench_column_layouts"]["oa"],
            ["projectName", "applicant", "amount", "counterparty", "reason"],
        )
        self.assertEqual(payload["oa_retention"], {"cutoff_date": "2026-01-01"})

    def test_invalid_oa_retention_cutoff_date_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_retention={"cutoff_date": "2026-99-99"},
                workbench_column_layouts={},
            )

        self.assertEqual(payload["oa_retention"], {"cutoff_date": "2026-01-01"})

    def test_update_settings_persists_oa_invoice_offset_applicants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            updated_payload = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_invoice_offset={"applicant_names": [" 周洁莹 ", "周洁莹", "李四"]},
                workbench_column_layouts={},
            )
            reloaded_payload = build_application(data_dir=Path(temp_dir))._app_settings_service.get_settings_payload()

        self.assertEqual(updated_payload["oa_invoice_offset"], {"applicant_names": ["周洁莹", "李四"]})
        self.assertEqual(reloaded_payload["oa_invoice_offset"], updated_payload["oa_invoice_offset"])

    def test_update_settings_triggers_oa_role_sync_with_normalized_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            sync_service = RecordingSyncService()
            app._app_settings_service._oa_role_sync_service = sync_service

            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FULL001", "READONLY001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )

        self.assertEqual(
            sync_service.assignments,
            [
                OARoleAssignment(username="READONLY001", tier="read_export_only"),
                OARoleAssignment(username="FULL001", tier="full_access"),
                OARoleAssignment(username="YNSYLP005", tier="admin"),
            ],
        )

    def test_workbench_settings_api_accepts_and_returns_access_control_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            update_response = app.handle_request(
                "POST",
                "/api/workbench/settings",
                body=json.dumps(
                    {
                        "completed_project_ids": [],
                        "bank_account_mappings": [],
                        "allowed_usernames": ["FULL001", "READONLY001"],
                        "readonly_export_usernames": ["READONLY001"],
                        "admin_usernames": [],
                        "oa_retention": {"cutoff_date": "2026-01-01"},
                        "workbench_column_layouts": {
                            "oa": ["projectName", "applicant"],
                            "bank": ["amount", "counterparty"],
                        },
                    }
                ),
            )
            updated_payload = json.loads(update_response.body)

            get_response = app.handle_request("GET", "/api/workbench/settings")
            get_payload = json.loads(get_response.body)

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(
            updated_payload["access_control"],
            {
                "allowed_usernames": ["FULL001", "READONLY001", "YNSYLP005"],
                "readonly_export_usernames": ["READONLY001"],
                "admin_usernames": ["YNSYLP005"],
                "full_access_usernames": ["FULL001"],
            },
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_payload["access_control"], updated_payload["access_control"])
        self.assertEqual(updated_payload["oa_retention"], {"cutoff_date": "2026-01-01"})
        self.assertEqual(get_payload["oa_retention"], updated_payload["oa_retention"])
        self.assertEqual(
            updated_payload["workbench_column_layouts"],
            {
                "oa": ["projectName", "applicant", "amount", "counterparty", "reason"],
                "bank": ["amount", "counterparty", "loanRepaymentDate", "note"],
                "invoice": ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"],
            },
        )
        self.assertEqual(get_payload["workbench_column_layouts"], updated_payload["workbench_column_layouts"])


if __name__ == "__main__":
    unittest.main()
