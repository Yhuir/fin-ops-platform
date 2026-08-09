from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
E2E_DIR = REPO_ROOT / "web" / "e2e"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "nightly-ci.yml"
VERIFY_SCRIPT_PATH = REPO_ROOT / "scripts" / "verify.sh"
WEB_PACKAGE_JSON_PATH = REPO_ROOT / "web" / "package.json"


class NightlyCITests(unittest.TestCase):
    def test_nightly_workflow_runs_unified_verification_on_schedule_dispatch_and_main_push(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("schedule:", workflow)
        self.assertIn('cron: "30 18 * * *"', workflow)
        self.assertRegex(workflow, r"push:\s+branches:\s+- main")
        self.assertIn("uses: actions/setup-python@v5", workflow)
        self.assertIn("python-version: \"3.11\"", workflow)
        self.assertIn("uses: actions/setup-node@v4", workflow)
        self.assertIn("node-version: \"20\"", workflow)
        self.assertIn("python -m pip install -r backend/requirements.txt", workflow)
        self.assertIn("python -m pip install -r backend/requirements-audit.txt", workflow)
        self.assertIn("npm ci", workflow)
        self.assertIn("npx playwright install --with-deps chromium", workflow)
        self.assertIn("bash scripts/verify.sh all", workflow)
        self.assertNotIn("bash scripts/verify.sh e2e", workflow)

    def test_verify_all_runs_backend_frontend_e2e_and_docs_checks(self) -> None:
        script = VERIFY_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("run_clean_app_check", script)
        self.assertIn("python3 -m pip_audit -r backend/requirements.txt", script)
        self.assertIn("PYTHONPATH=backend/src python3 -m unittest discover -s tests -v", script)
        self.assertIn("npm test -- --run", script)
        self.assertIn("npm run build", script)
        self.assertIn("npm run e2e:smoke", script)
        self.assertIn("docs/dev/nightly-ci.md", script)
        self.assertIn("docs/dev/spec-first-e2e-audit.md", script)
        self.assertIn("docs/dev/spec-first-e2e-inventory.md", script)
        self.assertIn("docs/dev/testing-closure-state.md", script)
        self.assertIn("docs/dev/testing-closure-dependency-map.md", script)
        self.assertIn("e2e-spec.md", script)
        self.assertIn("e2e-coverage.md", script)
        self.assertRegex(
            script,
            re.compile(
                r"all\)\s+run_dependency_audit\s+run_backend\s+run_frontend\s+run_e2e\s+run_docs\s+;;",
                re.MULTILINE,
            ),
        )

    def test_docs_verification_falls_back_when_ripgrep_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_bin = Path(temp_dir)
            for command in ("dirname", "find", "git", "grep", "sort"):
                executable = shutil.which(command)
                self.assertIsNotNone(executable, f"Required test command is unavailable: {command}")
                os.symlink(executable, temp_bin / command)
            result = subprocess.run(
                ["/bin/bash", str(VERIFY_SCRIPT_PATH), "docs"],
                cwd=REPO_ROOT,
                env={"PATH": str(temp_bin)},
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_e2e_smoke_script_includes_every_non_production_browser_spec(self) -> None:
        package_json = json.loads(WEB_PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
        e2e_smoke_script = package_json["scripts"]["e2e:smoke"]
        production_specs = {
            "production-admin-app-health.spec.ts",
            "production-route-shell.spec.ts",
        }

        expected_specs = {
            f"e2e/{spec_path.name}"
            for spec_path in E2E_DIR.glob("*.spec.ts")
            if spec_path.name not in production_specs
        }
        listed_specs = {
            token
            for token in shlex.split(e2e_smoke_script)
            if token.startswith("e2e/") and token.endswith(".spec.ts")
        }

        self.assertEqual(
            sorted(expected_specs - listed_specs),
            [],
            "Every deterministic non-production Playwright spec must be listed in npm "
            "run e2e:smoke so verify.sh all and Nightly CI execute new Browser E2E coverage.",
        )
        self.assertEqual(
            sorted(listed_specs - expected_specs),
            [],
            "npm run e2e:smoke must not list deleted or production-only Playwright specs.",
        )
        for production_spec in production_specs:
            self.assertNotIn(f"e2e/{production_spec}", listed_specs)

    def test_backend_verification_checks_postgres_only_startup_contract_by_default(self) -> None:
        script = VERIFY_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn('verify_data_dir="$(mktemp -d)"', script)
        self.assertIn('FIN_OPS_POSTGRES_DATABASE_URL:-${DATABASE_URL:-}', script)
        self.assertIn('requires FIN_OPS_APP_STORAGE_BACKEND=postgres', script)
        self.assertIn('FIN_OPS_APP_STORAGE_BACKEND="${FIN_OPS_APP_STORAGE_BACKEND:-postgres}"', script)
        self.assertIn("python3 -m fin_ops_platform.app.main --check", script)
        self.assertIn('rm -rf "$verify_data_dir"', script)
        self.assertRegex(
            script,
            re.compile(
                r"run_backend\(\) \{.*run_clean_app_check.*python3 -m unittest discover -s tests -v",
                re.DOTALL,
            ),
        )

    def test_runtime_check_is_explicit_opt_in_for_current_runtime_state(self) -> None:
        script = VERIFY_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("runtime-check", script)
        self.assertRegex(
            script,
            re.compile(
                r"run_runtime_check\(\) \{.*PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check",
                re.DOTALL,
            ),
        )
        self.assertRegex(script, re.compile(r"runtime-check\)\s+run_runtime_check\s+;;", re.MULTILINE))

    def test_infra_smoke_is_explicit_opt_in_and_does_not_run_in_verify_all(self) -> None:
        script = VERIFY_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("infra-smoke", script)
        self.assertIn("run_infra_smoke", script)
        self.assertIn("tests.test_read_model_slo_smoke", script)
        self.assertIn("tests.test_runtime_sync_closure_gate", script)
        self.assertIn("tests.test_write_operation_slo_audit", script)
        self.assertIn("tests.test_production_external_gate_preflight", script)
        self.assertIn("tests.test_rabbitmq_staging_preflight", script)
        self.assertIn("tests.test_runtime_infrastructure_postgres_integration", script)
        self.assertIn("tests.test_rabbitmq_integration", script)
        self.assertIn("python3 -m fin_ops_platform.tools.production_external_gate_preflight --json", script)
        self.assertIn("FIN_OPS_POSTGRES_DATABASE_URL=\"${FIN_OPS_POSTGRES_DATABASE_URL:-$FIN_OPS_TEST_DATABASE_URL}\"", script)
        self.assertIn("FIN_OPS_INFRA_SMOKE_APPLY", script)
        self.assertIn("read_model_slo_args+=(--apply)", script)
        self.assertIn("set FIN_OPS_INFRA_SMOKE_APPLY=1 to enqueue refresh events and verify worker drain", script)
        self.assertIn("FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS", script)
        self.assertIn("FIN_OPS_WRITE_OPERATION_AUDIT_LOOKBACK_HOURS", script)
        self.assertIn("FIN_OPS_WRITE_OPERATION_AUDIT_TARGET_MS", script)
        self.assertIn("FIN_OPS_WRITE_OPERATION_AUDIT_SINCE", script)
        self.assertIn("python3 -m fin_ops_platform.tools.write_operation_slo_audit", script)
        self.assertIn("set FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS to audit recent real writes", script)
        self.assertRegex(script, re.compile(r"infra-smoke\)\s+run_infra_smoke\s+;;", re.MULTILINE))
        self.assertRegex(
            script,
            re.compile(
                r"all\)\s+run_dependency_audit\s+run_backend\s+run_frontend\s+run_e2e\s+run_docs\s+;;",
                re.MULTILINE,
            ),
        )


if __name__ == "__main__":
    unittest.main()
