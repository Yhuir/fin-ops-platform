from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.runtime_worker_registry import (
    RUNTIME_WORKER_REGISTRY,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend/src/fin_ops_platform"


class ReadModelRuntimeRemovalTests(unittest.TestCase):
    def test_projection_runtime_modules_are_absent(self) -> None:
        services = BACKEND / "services"
        retired_modules = (
            "read_model_manifest.py",
            "read_model_query_gateway.py",
            "read_model_readiness.py",
            "read_model_refresh_gateway.py",
            "read_model_scope_contract.py",
            "read_model_scope_policy.py",
            "workbench_relation_read_facade.py",
            "workbench_relation_read_model_refresh.py",
            "workbench_relation_read_model_repository.py",
            "workbench_relation_sql_projection.py",
        )

        for filename in retired_modules:
            self.assertFalse((services / filename).exists(), filename)

    def test_worker_registry_has_no_projection_refresh_events(self) -> None:
        self.assertEqual(
            [registration.instance_name for registration in RUNTIME_WORKER_REGISTRY],
            ["oa-sync", "workbench-matching", "import", "settings-maintenance"],
        )
        event_types = {
            event_type
            for registration in RUNTIME_WORKER_REGISTRY
            for event_type in registration.event_types
        }
        self.assertFalse(
            any(event_type.endswith(".read_model.refresh") for event_type in event_types)
        )

    def test_http_and_frontend_contracts_have_no_projection_freshness_fields(self) -> None:
        http_probe = (BACKEND / "tools/http_slo_probe.py").read_text(encoding="utf-8")
        page_audit_types = (REPO_ROOT / "web/src/features/appHealth/types.ts").read_text(encoding="utf-8")
        app_health_api = (REPO_ROOT / "web/src/features/appHealth/api.ts").read_text(encoding="utf-8")
        app_health_page = (REPO_ROOT / "web/src/pages/AppHealthOperationsPage.tsx").read_text(encoding="utf-8")

        for source in (http_probe, page_audit_types, app_health_api, app_health_page):
            self.assertNotIn("registered_read_model", source)
            self.assertNotIn("read_model_status", source)
            self.assertNotIn("refresh_enqueued", source)

    def test_deploy_runtime_has_one_direct_path(self) -> None:
        deploy_control = (REPO_ROOT / "deploy/oa/bin/finops-deploy-control.sh").read_text(encoding="utf-8")

        self.assertNotIn("read_model", deploy_control)
        self.assertIn("run_workbench_direct_compatibility_preflight", deploy_control)
        self.assertIn("retire_removed_runtime_assets", deploy_control)
        self.assertIn("queue_stable_after_30_seconds", deploy_control)

    def test_terminal_migration_removes_projection_storage(self) -> None:
        migration = (
            BACKEND / "postgres/migrations/0149_remove_read_model_runtime.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("drop table if exists job.read_model_dirty_scopes cascade", migration)
        self.assertIn("drop schema if exists read_model cascade", migration)
        self.assertIn("event_type like '%.read_model.refresh'", migration)


if __name__ == "__main__":
    unittest.main()
