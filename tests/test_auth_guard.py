import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from tests.app_test_support import (
    build_local_state_application as build_application,
    configure_access_control,
)
from fin_ops_platform.services.oa_identity_service import OASessionExpiredError, OAUserIdentity
from fin_ops_platform.services.access_control_service import AccessControlService


class AuthGuardTests(unittest.TestCase):
    def test_access_control_uses_one_snapshot_and_cannot_create_second_admin(self) -> None:
        snapshot_reads = 0

        def snapshot_provider() -> dict[str, object]:
            nonlocal snapshot_reads
            snapshot_reads += 1
            return {
                "allowed_usernames": ["YNSYLP005", "ATTACKER"],
                "readonly_export_usernames": [],
                "admin_usernames": ["YNSYLP005"],
                "full_access_usernames": ["ATTACKER"],
            }

        service = AccessControlService(access_control_snapshot_provider=snapshot_provider)
        decision = service.evaluate(
            OAUserIdentity(
                user_id="attacker-id",
                username="ATTACKER",
                nickname="attacker",
                display_name="attacker",
                roles=[],
                permissions=[],
            )
        )

        self.assertEqual(snapshot_reads, 1)
        self.assertEqual(decision.access_tier, "full_access")
        self.assertFalse(decision.can_admin_access)

    def test_protected_admin_skips_snapshot_and_provider_failure_denies_others(self) -> None:
        def failing_provider() -> dict[str, object]:
            raise RuntimeError("provider secret must not be logged")

        service = AccessControlService(access_control_snapshot_provider=failing_provider)
        admin = service.evaluate(
            OAUserIdentity("005", "YNSYLP005", "admin", "admin")
        )
        with self.assertLogs("fin_ops_platform.services.access_control_service", level="WARNING") as logs:
            denied = service.evaluate(
                OAUserIdentity(
                    "outsider",
                    "OUTSIDER001",
                    "outsider",
                    "outsider",
                    roles=["finance"],
                    permissions=["finops:app:view"],
                )
            )

        self.assertEqual(admin.access_tier, "admin")
        self.assertEqual(denied.access_tier, "denied")
        self.assertNotIn("provider secret", "\n".join(logs.output))

    def test_shared_local_fixture_admits_only_its_default_identity_without_persisting_acl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            default_decision = app._access_control_service.evaluate(
                OAUserIdentity("test-id", "test_finops_user", "test", "test")
            )
            outsider_decision = app._access_control_service.evaluate(
                OAUserIdentity("outsider-id", "OUTSIDER001", "outsider", "outsider")
            )
            persisted_acl = app._app_settings_service.get_access_control_payload()

        self.assertEqual(default_decision.access_tier, "full_access")
        self.assertEqual(outsider_decision.access_tier, "denied")
        self.assertEqual(persisted_acl["accounts"], [])

    @contextmanager
    def _without_default_test_auth(self):
        previous = os.environ.get("FIN_OPS_TEST_DEFAULT_AUTH")
        os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = "0"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("FIN_OPS_TEST_DEFAULT_AUTH", None)
            else:
                os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = previous

    def test_protected_api_returns_unauthorized_without_oa_token(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request("GET", "/api/workbench?month=2026-03")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(payload["error"], "invalid_oa_session")

    def test_permission_present_006_is_denied_by_direct_read_and_write_apis(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="006",
                username="YNSYLP006",
                nickname="外部用户",
                display_name="外部用户",
                dept_id="99",
                dept_name="其他部门",
                roles=["finance", "finops_full_access"],
                permissions=["finops:app:view", "system:user:list"],
            )

            read_response = app.handle_request(
                "GET",
                "/api/workbench?month=2026-07",
                headers={"Authorization": "Bearer no-access"},
            )
            write_response = app.handle_request(
                "POST",
                "/api/workbench/actions/ignore-row",
                headers={"Authorization": "Bearer no-access"},
                body=json.dumps({"row_id": "row-1"}),
            )

        self.assertEqual(read_response.status_code, 403)
        self.assertEqual(json.loads(read_response.body)["error"], "forbidden")
        self.assertEqual(write_response.status_code, 403)
        self.assertEqual(json.loads(write_response.body)["error"], "forbidden")

    def test_import_endpoints_are_also_protected(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            def raise_expired(_: str) -> OAUserIdentity:
                raise OASessionExpiredError("登录状态已过期")

            app._oa_identity_service.resolve_identity = raise_expired

            response = app.handle_request(
                "GET",
                "/imports/templates",
                headers={"Authorization": "Bearer expired-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(payload["error"], "invalid_oa_session")

    def test_readonly_export_user_can_export_but_cannot_mutate_or_admin(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, read_export_only=["READONLY001"])
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="401",
                username="READONLY001",
                nickname="只读导出用户",
                display_name="只读导出用户",
                roles=["finance"],
                permissions=[],
            )
            headers = {"Authorization": "Bearer readonly-user"}
            readable_routes = [
                ("GET", "/api/cost-statistics/export-preview?month=all&view=time", None),
                ("GET", "/api/cost-statistics/export?month=all&view=time", None),
                ("GET", "/api/turnover-ledger/export-preview?family=company", None),
                ("GET", "/api/turnover-ledger/export?family=company", None),
                ("GET", "/api/pending-invoices/export-preview?direction=expense", None),
                ("GET", "/api/pending-invoices/export?direction=expense", None),
            ]
            forbidden_routes = [
                ("PUT", "/api/pending-invoices/rules", {}),
                ("PUT", "/api/input-invoice-usage/payment-status-rules", {}),
                ("PUT", "/api/turnover-ledger/tag-selection", {}),
                ("POST", "/api/bank-details/auto-tag-rules/reapply", {}),
                (
                    "POST",
                    "/api/workbench/settings/data-reset/jobs",
                    {"action": "reset_bank_transactions", "oa_password": "not-used-for-non-admin"},
                ),
                ("GET", "/api/workbench/settings/data-reset/jobs/active", {}),
                ("GET", "/api/workbench/settings/data-reset/jobs/job-1", {}),
            ]

            readable_responses = []
            for method, route, body in readable_routes:
                with self.subTest(route=route):
                    response = app.handle_request(
                        method,
                        route,
                        headers=headers,
                        body=json.dumps(body) if body is not None else None,
                    )
                    readable_responses.append((route, response))
                    self.assertNotIn(response.status_code, {401, 403})
                    if response.headers.get("Content-Type", "").startswith("application/json"):
                        payload = json.loads(response.body)
                        self.assertNotIn(payload.get("error"), {"invalid_oa_session", "forbidden", "admin_only"})

            for method, route, body in forbidden_routes:
                with self.subTest(route=route):
                    response = app.handle_request(
                        method,
                        route,
                        headers=headers,
                        body=json.dumps(body),
                    )
                    payload = json.loads(response.body)
                    self.assertEqual(response.status_code, 403)
                    self.assertIn(payload["error"], {"permission_denied", "admin_only"})

        responses_by_route = dict(readable_responses)
        cost_export_response = responses_by_route["/api/cost-statistics/export?month=all&view=time"]
        self.assertEqual(cost_export_response.status_code, 200)
        self.assertEqual(
            cost_export_response.headers.get("Content-Type"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(
            responses_by_route["/api/turnover-ledger/export?family=company"].headers.get("Content-Type"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_readonly_export_user_is_rejected_before_all_formerly_unguarded_write_routes(self) -> None:
        write_routes = (
            ("POST", "/api/workbench/exception/apply"),
            ("POST", "/api/workbench/actions/mark-exception"),
            ("POST", "/api/workbench/actions/confirm-cash-pass-through"),
            ("POST", "/api/workbench/actions/confirm-cash-ticket-purchase"),
            ("POST", "/api/workbench/actions/cancel-cash-special"),
            ("POST", "/api/workbench/actions/update-bank-exception"),
            ("POST", "/api/workbench/actions/oa-bank-exception"),
            ("POST", "/api/workbench/actions/confirm-personal-advance-repayment"),
            ("POST", "/api/workbench/actions/cancel-exception"),
            ("POST", "/api/workbench/actions/ignore-row"),
            ("POST", "/api/workbench/actions/unignore-row"),
            ("POST", "/imports/files/preview"),
            ("POST", "/imports/files/confirm"),
            ("POST", "/imports/files/retry"),
            ("POST", "/api/background-jobs/job-1/acknowledge"),
            ("POST", "/api/background-jobs/job-1/retry"),
            ("POST", "/api/etc/import/preview"),
            ("POST", "/api/etc/import/confirm"),
            ("POST", "/api/etc/reconciliation-tasks"),
            ("DELETE", "/api/etc/reconciliation-tasks/task-1"),
            ("DELETE", "/api/etc/reconciliation-tasks/task-1/source-files/file-1"),
            ("POST", "/api/etc/reconciliation-tasks/task-1/credit-card-statement"),
            ("POST", "/api/etc/reconciliation-tasks/task-1/ticket-root-files"),
            ("POST", "/api/etc/reconciliation-tasks/task-1/ticket-root-texts"),
            ("POST", "/api/etc/reconciliation-tasks/task-1/supplement-evidences"),
            ("POST", "/api/etc/reconciliation-tasks/task-1/supplement-evidences/item-1"),
            ("PATCH", "/api/etc/reconciliation-tasks/task-1/items/item-1"),
            ("POST", "/api/etc/reconciliation-tasks/task-1/confirm"),
            ("POST", "/api/etc/reconciliation-tasks/task-1/reopen"),
            ("POST", "/api/etc/reconciliation-tasks/task-1/refresh-matches"),
            ("DELETE", "/api/etc/reconciliation-tasks/task-1/imported-invoices"),
        )
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, read_export_only=["READONLY001"])
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="401",
                username="READONLY001",
                nickname="只读导出用户",
                display_name="只读导出用户",
                roles=["finance"],
                permissions=[],
            )
            headers = {"Authorization": "Bearer readonly-user"}

            for method, route in write_routes:
                with self.subTest(method=method, route=route):
                    response = app.handle_request(method, route, headers=headers, body="{}")
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(json.loads(response.body)["error"], "permission_denied")

    def test_readonly_export_user_keeps_read_only_post_contracts(self) -> None:
        read_routes = (
            "/api/operation-barrier/status",
            "/api/workbench/exception/preview",
            "/api/workbench/actions/confirm-link/preview",
            "/api/workbench/actions/withdraw-link/preview",
            "/api/pending-invoices/invoice-candidates/batch",
            "/api/pending-invoices/rows/row-1/attach-existing-invoice/preview",
            "/api/pending-invoices/attach-existing-invoices/preview",
            "/api/input-invoice-usage/oa-reverse/preview",
            "/api/tax-offset/calculate",
        )
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, read_export_only=["READONLY001"])
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="401",
                username="READONLY001",
                nickname="只读导出用户",
                display_name="只读导出用户",
                roles=["finance"],
                permissions=[],
            )
            headers = {"Authorization": "Bearer readonly-user"}

            for route in read_routes:
                with self.subTest(route=route):
                    response = app.handle_request("POST", route, headers=headers, body="{}")
                    payload = json.loads(response.body)
                    self.assertNotEqual(response.status_code, 403)
                    self.assertNotEqual(payload.get("error"), "permission_denied")

    def test_readonly_write_rejection_happens_before_request_body_parsing(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, read_export_only=["READONLY001"])
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="401",
                username="READONLY001",
                nickname="只读导出用户",
                display_name="只读导出用户",
                roles=["finance"],
                permissions=[],
            )
            headers = {"Authorization": "Bearer readonly-user"}

            with patch.object(app, "_load_json_body", side_effect=AssertionError("body parsed")):
                json_response = app.handle_request(
                    "POST",
                    "/api/workbench/actions/ignore-row",
                    headers=headers,
                    body='{"row_id":"row-1"}',
                )
            with patch.object(app, "_load_multipart_body", side_effect=AssertionError("body parsed")):
                multipart_response = app.handle_request(
                    "POST",
                    "/api/etc/import/preview",
                    headers=headers,
                    body=b"not-parsed",
                )

        self.assertEqual(json_response.status_code, 403)
        self.assertEqual(multipart_response.status_code, 403)

    def test_unknown_protected_post_fails_closed_for_readonly_but_reaches_not_found_for_full_access(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, full_access=["FULL001"], read_export_only=["READONLY001"])
            identities = {
                "readonly-user": OAUserIdentity(
                    user_id="401",
                    username="READONLY001",
                    nickname="只读用户",
                    display_name="只读用户",
                ),
                "full-user": OAUserIdentity(
                    user_id="402",
                    username="FULL001",
                    nickname="可写用户",
                    display_name="可写用户",
                ),
            }
            app._oa_identity_service.resolve_identity = lambda token: identities[token]

            readonly_response = app.handle_request(
                "POST",
                "/api/future-write-route",
                headers={"Authorization": "Bearer readonly-user"},
                body="{}",
            )
            full_response = app.handle_request(
                "POST",
                "/api/future-write-route",
                headers={"Authorization": "Bearer full-user"},
                body="{}",
            )

        self.assertEqual(readonly_response.status_code, 403)
        self.assertEqual(full_response.status_code, 404)

    def test_etc_reconciliation_actor_comes_from_authenticated_session(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, full_access=["FULL001"])
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="trusted-user-id",
                username="FULL001",
                nickname="可信用户",
                display_name="可信用户",
                roles=[],
                permissions=[],
            )
            response = app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                headers={"Authorization": "Bearer full-user"},
                body=json.dumps({"title": "actor test", "createdBy": "spoofed-user"}),
            )
            task_id = json.loads(response.body)["taskId"]
            task = app._etc_reconciliation_task_service.get_task(task_id)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(task.created_by, "FULL001")


if __name__ == "__main__":
    unittest.main()
