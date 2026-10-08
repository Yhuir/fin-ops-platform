import unittest

from fin_ops_platform.app.route_access_policy import (
    is_admin_only_route,
    is_state_changing_request,
    page_keys_for_route,
)


class RouteAccessPolicyTests(unittest.TestCase):
    def test_state_changing_classification_is_used_only_for_audit(self) -> None:
        self.assertFalse(is_state_changing_request("GET", "/api/workbench"))
        for endpoint in ("export", "export-summary"):
            self.assertFalse(is_state_changing_request("POST", f"/api/cost-statistics/{endpoint}"))
        self.assertFalse(is_state_changing_request("POST", "/api/workbench/actions/confirm-link/preview"))
        self.assertTrue(is_state_changing_request("POST", "/api/workbench/exceptions/review"))
        self.assertTrue(is_state_changing_request("PUT", "/api/pending-invoices/rules"))

    def test_routes_map_to_page_access_keys(self) -> None:
        cases = {
            "/api/workbench?month=2026-08": ("reconciliation-workbench",),
            "/api/cost-statistics/export": ("cost-statistics",),
            "/api/bank-details/auto-tag-rules": ("bank-details",),
            "/api/input-invoice-usage/rows": ("input-invoice-usage",),
            "/imports/files/preview": (
                "imports.bank-transactions",
                "imports.invoices",
                "imports.etc-invoices",
            ),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(page_keys_for_route(path.split("?", 1)[0]), expected)

    def test_control_plane_routes_remain_admin_only(self) -> None:
        for path in (
            "/api/workbench/settings/access-control",
            "/api/workbench/settings/access-control/users",
            "/api/workbench/settings/oa-applicant-credentials",
            "/api/workbench/settings/oa-applicant-credentials/users",
            "/api/workbench/settings/data-reset/preview",
            "/api/operations/history",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_admin_only_route(path))

        self.assertFalse(is_admin_only_route("/api/workbench/settings"))
        self.assertFalse(is_admin_only_route("/api/bank-details"))

    def test_reverse_prefill_read_ownership_does_not_expand_other_settings_routes(self) -> None:
        self.assertEqual(
            page_keys_for_route("/api/workbench/settings/oa-draft-prefill/input-invoice-usage"),
            ("input-invoice-usage", "settings"),
        )
        for path in (
            "/api/workbench/settings", "/api/workbench/settings/oa-draft-prefill/etc",
            "/api/workbench/settings/oa-draft-prefill/unknown",
        ):
            self.assertEqual(page_keys_for_route(path), ("settings",))

    def test_batch_history_tab_keeps_its_own_api_permission(self) -> None:
        for path in ("/api/batch-accounting", "/api/batch-accounting/relations/relation-1"):
            self.assertEqual(page_keys_for_route(path), ("batch-accounting",))
        for path in (
            "/api/workbench/settings",
            "/api/workbench/settings/access-control",
            "/api/workbench/settings/data-reset/preview",
            "/api/workbench/settings/data-reset/jobs",
        ):
            self.assertEqual(page_keys_for_route(path), ("settings",))
        bank_permissions = page_keys_for_route("/api/bank-transactions/bank-1/source-detail")
        self.assertNotIn("batch-accounting", bank_permissions)
        self.assertEqual(bank_permissions, (
            "bank-details", "reconciliation-workbench", "cost-statistics", "turnover-ledger",
            "pending-invoices", "input-invoice-usage", "output-invoice-collections",
            "oa-pending-payments", "bank-flow-rule-batches",
        ))
        self.assertNotIn("batch-accounting", page_keys_for_route("/api/background-jobs/active"))


if __name__ == "__main__":
    unittest.main()
