import unittest

from fin_ops_platform.app.route_access_policy import requires_data_mutation


class RouteAccessPolicyTests(unittest.TestCase):
    def test_safe_methods_and_known_read_only_posts_do_not_require_mutation(self) -> None:
        for method, route_path in (
            ("GET", "/api/workbench"),
            ("GET", "/api/operations/app-health-dashboard"),
            ("GET", "/api/workbench/settings/oa-applicant-credentials"),
            ("GET", "/api/workbench/settings/data-reset/preview?action=reset_bank_transactions"),
            ("GET", "/api/workbench/settings/data-reset/jobs/active"),
            ("HEAD", "/api/workbench"),
            ("OPTIONS", "/api/workbench/actions/ignore-row"),
            ("POST", "/api/operation-barrier/status"),
            ("POST", "/api/workbench/exception/preview"),
            ("POST", "/api/workbench/actions/confirm-link/preview"),
            ("POST", "/api/workbench/actions/withdraw-link/preview"),
            ("POST", "/api/pending-invoices/invoice-candidates/batch"),
            ("POST", "/api/pending-invoices/rows/row-1/attach-existing-invoice/preview"),
            ("POST", "/api/pending-invoices/attach-existing-invoices/preview"),
            ("POST", "/api/input-invoice-usage/oa-reverse/preview"),
            ("POST", "/api/tax-offset/calculate"),
        ):
            with self.subTest(method=method, route_path=route_path):
                self.assertFalse(requires_data_mutation(method, route_path))

    def test_every_other_unsafe_request_requires_mutation(self) -> None:
        for method, route_path in (
            ("POST", "/api/workbench/actions/ignore-row"),
            ("POST", "/imports/files/preview"),
            ("PUT", "/api/pending-invoices/rules"),
            ("PATCH", "/api/etc/reconciliation-tasks/task-1/items/item-1"),
            ("DELETE", "/api/etc/reconciliation-tasks/task-1"),
            ("PUT", "/api/workbench/settings/oa-applicant-credentials/user-1"),
            ("POST", "/api/workbench/settings/data-reset/jobs"),
            ("POST", "/api/future-write-route"),
        ):
            with self.subTest(method=method, route_path=route_path):
                self.assertTrue(requires_data_mutation(method, route_path))


if __name__ == "__main__":
    unittest.main()
