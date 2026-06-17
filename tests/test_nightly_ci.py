from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "nightly-ci.yml"
VERIFY_SCRIPT_PATH = REPO_ROOT / "scripts" / "verify.sh"


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
        self.assertIn("npm ci", workflow)
        self.assertIn("npx playwright install --with-deps chromium", workflow)
        self.assertIn("bash scripts/verify.sh all", workflow)
        self.assertNotIn("bash scripts/verify.sh e2e", workflow)

    def test_verify_all_runs_backend_frontend_e2e_and_docs_checks(self) -> None:
        script = VERIFY_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("run_clean_app_check", script)
        self.assertIn("PYTHONPATH=backend/src python3 -m unittest discover -s tests -v", script)
        self.assertIn("npm test -- --run", script)
        self.assertIn("npm run build", script)
        self.assertIn("npm run e2e:smoke", script)
        self.assertIn("docs/dev/nightly-ci.md", script)
        self.assertIn("docs/dev/testing-closure-state.md", script)
        self.assertIn("docs/dev/testing-closure-dependency-map.md", script)
        self.assertRegex(
            script,
            re.compile(r"all\)\s+run_backend\s+run_frontend\s+run_e2e\s+run_docs\s+;;", re.MULTILINE),
        )

    def test_backend_verification_uses_clean_app_state_by_default(self) -> None:
        script = VERIFY_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn('verify_data_dir="$(mktemp -d)"', script)
        self.assertIn(
            'FIN_OPS_DATA_DIR="$verify_data_dir" PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check',
            script,
        )
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


if __name__ == "__main__":
    unittest.main()
