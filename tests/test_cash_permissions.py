from __future__ import annotations

import unittest

from fin_ops_platform.app.route_access_policy import (
    is_admin_only_route,
    is_cash_request,
    is_state_changing_request,
    page_keys_for_route,
)
from fin_ops_platform.services.access_control_service import AccessControlService
from fin_ops_platform.services.app_settings_service import AppSettingsService, AppSettingsValidationError
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.page_audit_registry import PAGE_AUDIT_REGISTRY
from fin_ops_platform.services.state_store_protocol import settings_access_control_from_payload


class CashPermissionTests(unittest.TestCase):
    def test_cash_is_a_binary_page_grant_and_revocation_is_immediate(self) -> None:
        snapshot = {
            "access_control_version": 1,
            "page_access_accounts": [{"username": "CASH_TEST", "page_keys": ["cash"]}],
        }
        service = AccessControlService(access_control_snapshot_provider=lambda: snapshot)
        identity = OAUserIdentity("cash-test", "CASH_TEST", "", "Cash test")
        decision = service.evaluate(identity)
        self.assertTrue(decision.can_access_app)
        self.assertTrue(decision.can_access_page("cash"))
        self.assertFalse(decision.can_admin_access)
        self.assertFalse(decision.can_access_page("bank-details"))
        self.assertTrue(is_admin_only_route("/api/workbench/settings/access-control"))
        snapshot["page_access_accounts"] = []
        snapshot["access_control_version"] = 2
        self.assertFalse(service.evaluate(identity).can_access_page("cash"))

    def test_only_fixed_005_has_administrator_access(self) -> None:
        service = AccessControlService()
        for username, expected in (("YNSYLP005", True), ("YNSYLP006", False)):
            decision = service.evaluate(OAUserIdentity(username, username, "", username))
            self.assertEqual(decision.can_admin_access, expected)
            self.assertEqual(decision.can_access_page("cash"), expected)

    def test_cash_key_round_trips_without_new_permission_tiers(self) -> None:
        accounts = [{"username": "CASH_TEST", "page_keys": ["cash", "bank-details"]}]
        normalized = AppSettingsService._access_control_from_accounts(accounts)
        self.assertEqual(normalized["page_access_accounts"], [
            {"username": "CASH_TEST", "page_keys": ["bank-details", "cash"]},
        ])
        self.assertEqual(settings_access_control_from_payload(normalized), normalized)
        with self.assertRaises(AppSettingsValidationError):
            AppSettingsService._access_control_from_accounts([
                {"username": "CASH_TEST", "page_keys": ["cash.admin"]},
            ])

    def test_private_route_is_segment_exact_and_not_a_read_only_post(self) -> None:
        for route in ("/api/cash", "/api/cash/flows", "/api/cash/settings/project-selection"):
            self.assertTrue(is_cash_request(route))
            self.assertEqual(page_keys_for_route(route), ("cash",))
            self.assertFalse(is_admin_only_route(route))
            self.assertTrue(is_state_changing_request("POST", route))
        for route in ("/api/cashback", "/api/cash-other/flows", "/api/bank-details"):
            self.assertFalse(is_cash_request(route))

    def test_cash_does_not_join_global_job_or_system_audit_owners(self) -> None:
        self.assertNotIn("cash", page_keys_for_route("/api/background-jobs"))
        self.assertIn("bank-details", page_keys_for_route("/api/background-jobs"))
        self.assertNotIn("cash", PAGE_AUDIT_REGISTRY)
        self.assertEqual(len(PAGE_AUDIT_REGISTRY), 18)


if __name__ == "__main__":
    unittest.main()
