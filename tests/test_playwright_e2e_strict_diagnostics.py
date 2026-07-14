from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
E2E_DIR = REPO_ROOT / "web" / "e2e"
STRICT_FIXTURE_PATH = E2E_DIR / "fixtures" / "strictTest.ts"
SUCCESS_ASSERTIONS_PATH = E2E_DIR / "fixtures" / "successAssertions.ts"
PRODUCTION_ADMIN_APP_HEALTH_SPEC_PATH = E2E_DIR / "production-admin-app-health.spec.ts"
PRODUCTION_ROUTE_SHELL_SPEC_PATH = E2E_DIR / "production-route-shell.spec.ts"
WEB_PACKAGE_JSON_PATH = REPO_ROOT / "web" / "package.json"
PLAYWRIGHT_CONFIG_PATH = REPO_ROOT / "web" / "playwright.config.ts"


class PlaywrightE2EStrictDiagnosticsTests(unittest.TestCase):
    def test_every_e2e_spec_uses_strict_browser_diagnostics_fixture(self) -> None:
        direct_imports: list[str] = []
        missing_strict_imports: list[str] = []
        for spec_path in sorted(E2E_DIR.glob("*.spec.ts")):
            source = spec_path.read_text(encoding="utf-8")
            relative = spec_path.relative_to(REPO_ROOT).as_posix()
            if 'from "@playwright/test"' in source:
                direct_imports.append(relative)
            if 'from "./fixtures/strictTest"' not in source:
                missing_strict_imports.append(relative)

        self.assertEqual(
            direct_imports,
            [],
            "Browser E2E specs must import test/expect/types from ./fixtures/strictTest "
            "so console errors, page errors, request failures, and native dialogs cannot be hidden.",
        )
        self.assertEqual(
            missing_strict_imports,
            [],
            "Every Browser E2E spec must opt into strict browser diagnostics.",
        )

    def test_strict_fixture_observes_hidden_browser_error_channels(self) -> None:
        source = STRICT_FIXTURE_PATH.read_text(encoding="utf-8")
        for required in (
            'page.on("console"',
            'page.on("pageerror"',
            'page.on("requestfailed"',
            'page.on("dialog"',
            "expect(diagnostics",
        ):
            self.assertIn(required, source)

    def test_strict_fixture_treats_browser_http_status_resource_logs_as_handled_api_responses(self) -> None:
        source = STRICT_FIXTURE_PATH.read_text(encoding="utf-8")
        self.assertIn(r"status of \d{3}", source)
        self.assertNotIn("(401|403|409|500)", source)

    def test_e2e_specs_do_not_commit_only_markers_and_ci_forbids_only(self) -> None:
        config = PLAYWRIGHT_CONFIG_PATH.read_text(encoding="utf-8")
        only_markers: list[str] = []
        only_pattern = r"\b(?:test|describe)\.only\s*\(|\btest\.describe\.only\s*\("

        for spec_path in sorted(E2E_DIR.glob("*.spec.ts")):
            source = spec_path.read_text(encoding="utf-8")
            if re.search(only_pattern, source):
                only_markers.append(spec_path.relative_to(REPO_ROOT).as_posix())

        self.assertIn("forbidOnly: !!process.env.CI", config)
        self.assertEqual(
            only_markers,
            [],
            "Browser E2E specs must not commit test.only/describe.only markers. "
            "They can make local or CI smoke runs skip the rest of the Spec-first suite.",
        )

    def test_successful_write_flows_have_reusable_visible_error_guard(self) -> None:
        helper = SUCCESS_ASSERTIONS_PATH.read_text(encoding="utf-8")
        guarded_success_flows = {
            "workbench shared confirm flow": (E2E_DIR / "fixtures" / "workbenchFlow.ts").read_text(encoding="utf-8"),
            "bank details auto-tag rules": (E2E_DIR / "bank-details-auto-tag-rules-flow.spec.ts").read_text(encoding="utf-8"),
            "OA pending confirm-paid": (E2E_DIR / "oa-pending-payments-confirm-paid-flow.spec.ts").read_text(encoding="utf-8"),
            "OA pending bank-link": (E2E_DIR / "oa-pending-payments-bank-link-flow.spec.ts").read_text(encoding="utf-8"),
            "pending invoices attach existing": (E2E_DIR / "pending-invoices-attach-existing-flow.spec.ts").read_text(encoding="utf-8"),
            "pending invoices income status": (E2E_DIR / "pending-invoices-income-status-flow.spec.ts").read_text(encoding="utf-8"),
            "output invoice red relation": (E2E_DIR / "output-invoice-red-relation-fanout.spec.ts").read_text(encoding="utf-8"),
            "batch accounting submit and withdraw": (E2E_DIR / "batch-accounting-flow.spec.ts").read_text(encoding="utf-8"),
            "bank flow rule tag, submit, fan-out, and withdraw": (E2E_DIR / "bank-flow-rule-batches-flow.spec.ts").read_text(encoding="utf-8"),
            "turnover tag, closure, fan-out, and withdraw": (E2E_DIR / "turnover-ledger-flow.spec.ts").read_text(encoding="utf-8"),
            "settings reset and project-scope fan-out": (E2E_DIR / "settings-data-reset-flow.spec.ts").read_text(encoding="utf-8"),
            "ETC OA draft and manual submitted": (E2E_DIR / "etc-tickets-flow.spec.ts").read_text(encoding="utf-8"),
            "output invoice status and receipt": (E2E_DIR / "output-invoice-collections-flow.spec.ts").read_text(encoding="utf-8"),
            "bank import confirm and downstream": (E2E_DIR / "imports-bank-transactions-flow.spec.ts").read_text(encoding="utf-8"),
            "invoice import confirm and downstream": (E2E_DIR / "imports-invoices-flow.spec.ts").read_text(encoding="utf-8"),
            "ETC import confirm and downstream": (E2E_DIR / "imports-etc-invoices-flow.spec.ts").read_text(encoding="utf-8"),
            "input invoice payment rules and OA reverse": (E2E_DIR / "input-invoice-usage-flow.spec.ts").read_text(encoding="utf-8"),
            "tax offset plan and certified import": (E2E_DIR / "tax-offset-flow.spec.ts").read_text(encoding="utf-8"),
            "pending invoice rules save": (E2E_DIR / "pending-invoices-rules-save-flow.spec.ts").read_text(encoding="utf-8"),
            "workbench relation to bank details": (E2E_DIR / "workbench-relation-fanout.spec.ts").read_text(encoding="utf-8"),
            "workbench relation to pending invoices": (E2E_DIR / "pending-invoices-fanout.spec.ts").read_text(encoding="utf-8"),
            "workbench relation to input invoice usage": (E2E_DIR / "input-invoice-relation-fanout.spec.ts").read_text(encoding="utf-8"),
            "workbench relation to cost statistics": (E2E_DIR / "cost-statistics-relation-fanout.spec.ts").read_text(encoding="utf-8"),
            "workbench relation to OA pending": (E2E_DIR / "workbench-relations-oa-pending-fanout.spec.ts").read_text(encoding="utf-8"),
            "workbench relation tax-offset isolation": (E2E_DIR / "workbench-relations-tax-offset-isolation.spec.ts").read_text(encoding="utf-8"),
            "workbench withdraw": (E2E_DIR / "workbench-withdraw-flow.spec.ts").read_text(encoding="utf-8"),
            "workbench exception recovery": (E2E_DIR / "workbench-exception-flow.spec.ts").read_text(encoding="utf-8"),
            "workbench network recovery and duplicate submit": (E2E_DIR / "workbench-network-recovery-flow.spec.ts").read_text(encoding="utf-8"),
            "bank details category confirmation and assignment": (E2E_DIR / "bank-details-category-flow.spec.ts").read_text(encoding="utf-8"),
            "bank details relation export": (E2E_DIR / "bank-details-export-download.spec.ts").read_text(encoding="utf-8"),
            "bank details filtered export and permissions": (E2E_DIR / "bank-details-filtered-export-permissions.spec.ts").read_text(encoding="utf-8"),
            "pending invoices relation export": (E2E_DIR / "pending-invoices-export-download.spec.ts").read_text(encoding="utf-8"),
        }

        for required in (
            "expectNoUnexpectedSuccessUiErrors",
            "操作失败",
            "保存失败",
            "刷新失败",
            "导入任务创建失败",
            "关联失败",
            "同步.*失败",
            "关系已写入，关联台刷新未完成",
            "操作同步等待超时",
        ):
            self.assertIn(required, helper)

        for name, source in guarded_success_flows.items():
            self.assertIn("expectNoUnexpectedSuccessUiErrors", source, name)

    def test_success_like_specs_without_visible_error_guard_are_explicitly_allowlisted(self) -> None:
        success_like_pattern = re.compile(
            r"成功|已保存|已创建|已提交|已确认|已撤回|导入成功|保存|确认导入|POST /api|PUT /api|DELETE /api|PATCH /api",
        )
        allowed_without_guard = {
            "web/e2e/permissions-role-matrix.spec.ts",
            "web/e2e/workbench-permissions-flow.spec.ts",
            "web/e2e/workbench-stale-error-flow.spec.ts",
        }
        missing_guard: set[str] = set()

        for spec_path in sorted(E2E_DIR.glob("*.spec.ts")):
            source = spec_path.read_text(encoding="utf-8")
            if success_like_pattern.search(source) and "expectNoUnexpectedSuccessUiErrors" not in source:
                missing_guard.add(spec_path.relative_to(REPO_ROOT).as_posix())

        self.assertEqual(
            missing_guard,
            allowed_without_guard,
            "Any Browser spec with apparent success/write/download flows should either call "
            "expectNoUnexpectedSuccessUiErrors after successful user-visible completion, or be "
            "explicitly allowlisted here as a negative/permission/read-only semantics spec.",
        )

    def test_production_route_shell_smoke_keeps_secret_and_readonly_guards(self) -> None:
        source = PRODUCTION_ROUTE_SHELL_SPEC_PATH.read_text(encoding="utf-8")
        package_json = WEB_PACKAGE_JSON_PATH.read_text(encoding="utf-8")

        for required in (
            'from "./fixtures/strictTest"',
            'process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1"',
            "process.env.FIN_OPS_E2E_OA_TOKEN",
            "test.skip(!productionSmokeEnabled",
            "test.skip(!oaToken",
            'test.use({ screenshot: "off", trace: "off", video: "off" })',
            'name: "Admin-Token"',
            "page.on(\"request\"",
            '"POST"',
            '"PUT"',
            '"PATCH"',
            '"DELETE"',
            "blockedSession",
            "stillLoading",
        ):
            self.assertIn(required, source)

        self.assertIn("FIN_OPS_E2E_PRODUCTION_SMOKE=1", package_json)
        self.assertIn("FIN_OPS_E2E_SKIP_WEBSERVER=1", package_json)
        self.assertIn("PLAYWRIGHT_BASE_URL=https://www.yn-sourcing.com", package_json)
        self.assertIn("e2e/production-route-shell.spec.ts", package_json)
        self.assertNotIn("textSample", source)
        self.assertNotIn("bodyText.slice", source)

    def test_production_smoke_strict_diagnostics_are_redacted(self) -> None:
        source = STRICT_FIXTURE_PATH.read_text(encoding="utf-8")

        for required in (
            'process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1"',
            "productionDiagnosticsRedactionEnabled",
            "redactProductionDiagnosticDetail",
            "redactProductionPath",
            '"/api/<redacted>"',
            '"/fin-ops/"',
            "request_failed",
            '"<redacted>"',
            "pushBrowserDiagnostic",
            "pushBrowserDiagnostic(diagnostics, { category: \"console.error\"",
            "pushBrowserDiagnostic(diagnostics, { category: \"pageerror\"",
            "pushBrowserDiagnostic(diagnostics, {",
            "category: \"requestfailed\"",
            "category: \"dialog\"",
        ):
            self.assertIn(required, source)

        self.assertNotIn("pushDiagnostic(diagnostics, { category: \"console.error\"", source)
        self.assertNotIn("pushDiagnostic(diagnostics, { category: \"pageerror\"", source)

    def test_production_admin_app_health_smoke_keeps_secret_admin_and_readonly_guards(self) -> None:
        source = PRODUCTION_ADMIN_APP_HEALTH_SPEC_PATH.read_text(encoding="utf-8")
        package_json = WEB_PACKAGE_JSON_PATH.read_text(encoding="utf-8")

        for required in (
            'from "./fixtures/strictTest"',
            'process.env.FIN_OPS_E2E_PRODUCTION_ADMIN_SMOKE === "1"',
            "process.env.FIN_OPS_E2E_ADMIN_TOKEN",
            "test.skip(!productionAdminSmokeEnabled",
            "test.skip(!adminToken",
            'test.use({ screenshot: "off", trace: "off", video: "off" })',
            'name: "Admin-Token"',
            "page.on(\"request\"",
            "page.on(\"response\"",
            '"POST"',
            '"PUT"',
            '"PATCH"',
            '"DELETE"',
            '"/fin-ops/operations/app-health"',
            '"/api/operations/app-health-dashboard"',
            '"AppHealth 运维状态"',
            '"app-health-data"',
            '"app-health-requests"',
            '"app-health-runtime"',
            "当前账号没有管理员权限，不能查看 AppHealth 运维状态。",
            "dashboardStatuses",
            "mutatingRequests",
        ):
            self.assertIn(required, source)

        self.assertIn("FIN_OPS_E2E_PRODUCTION_ADMIN_SMOKE=1", package_json)
        self.assertIn("FIN_OPS_E2E_SKIP_WEBSERVER=1", package_json)
        self.assertIn("PLAYWRIGHT_BASE_URL=https://www.yn-sourcing.com", package_json)
        self.assertIn("e2e/production-admin-app-health.spec.ts", package_json)


if __name__ == "__main__":
    unittest.main()
