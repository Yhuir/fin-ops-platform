from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import pickle
import sys
import os
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.state_store import ApplicationStateStore


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PlatformShadowLegacySeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.legacy_seed = load_module(
            "platform_shadow_legacy_seed",
            ROOT / "scripts" / "tools" / "platform_shadow_legacy_seed.py",
        )
        self._original_env = {
            name: os.environ.get(name)
            for name in (
                "FIN_OPS_SHADOW_OA_TOKEN",
                "FIN_OPS_SHADOW_OA_PASSWORD",
                "FIN_OPS_SHADOW_OA_IDENTITY_SOURCE",
            )
        }
        for name in self._original_env:
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        for name, value in self._original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_cli_writes_isolated_python_state_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as output_dir:
            code = self.legacy_seed.main(
                [
                    "--run-id",
                    "p0-platform-test",
                    "--username",
                    "test",
                    "--user-id",
                    "63",
                    "--data-dir",
                    data_dir,
                    "--output-dir",
                    output_dir,
                    "--report-date",
                    "20260517",
                ]
            )

            self.assertEqual(code, 0)
            report_path = Path(output_dir) / "p0-platform-legacy-shadow-seed-20260517.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "NO_GO")
            self.assertEqual(report["legacy_python_seed"]["status"], "GO")
            self.assertEqual(report["legacy_python_seed"]["runtime_reload_required"], "restart_or_reload_required")
            self.assertIn("LedgerReminderService", report["legacy_python_seed"]["reload_note"])
            self.assertEqual(report["secret_requirements"]["status"], "NO_GO")
            self.assertEqual(report["secret_requirements"]["identity_source"]["status"], "NO_GO")

            encoded = json.dumps(report, ensure_ascii=False).lower()
            self.assertNotIn("bearer ", encoded)
            self.assertNotIn("password=", encoded)
            self.assertNotIn("token=", encoded)

            store = ApplicationStateStore(Path(data_dir))
            settings = store.load_app_settings()
            runtime_vars = report["runtime_variables"]
            manual_project_ids = {item["id"] for item in settings["manual_projects"]}
            self.assertIn(runtime_vars["PROJECT_ID"], manual_project_ids)
            self.assertIn(runtime_vars["PROJECT_DELETE_ID"], manual_project_ids)
            self.assertEqual(settings["admin_usernames"], ["test"])

            jobs = store.load_background_jobs()
            self.assertEqual(jobs[runtime_vars["BACKGROUND_JOB_ID"]]["visibility"], "system")
            self.assertEqual(jobs[runtime_vars["BACKGROUND_JOB_ID"]]["owner_user_id"], "63")

            with (Path(data_dir) / "state.pkl").open("rb") as handle:
                state = pickle.load(handle)  # noqa: S301 - test reads trusted local fixture state
            transactions = state["imports"]["transactions"]
            self.assertEqual(transactions[0].id, runtime_vars["BANK_TRANSACTION_ID"])
            self.assertEqual(str(transactions[0].amount), "1288.00")
            self.assertEqual(transactions[0].counterparty_name_raw, "平台 Shadow 往来单位")
            self.assertEqual(
                state["platform_shadow_legacy_seed"]["ledgers"][0]["id"],
                runtime_vars["LEDGER_ID"],
            )
            self.assertEqual(state["platform_shadow_legacy_seed"]["ledgers"][0]["owner_id"], "63")
            self.assertEqual(state["platform_shadow_legacy_seed"]["reminders"][0]["channel"], "in_app")

    def test_application_loads_shadow_ledgers_and_reminders_from_seed_state(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as output_dir:
            self.legacy_seed.main(
                [
                    "--run-id",
                    "p0-platform-test",
                    "--username",
                    "test",
                    "--user-id",
                    "63",
                    "--data-dir",
                    data_dir,
                    "--output-dir",
                    output_dir,
                    "--report-date",
                    "20260517",
                ]
            )
            report = json.loads((Path(output_dir) / "p0-platform-legacy-shadow-seed-20260517.json").read_text())
            runtime_vars = report["runtime_variables"]

            app = Application(data_dir=Path(data_dir))

            ledger = app._ledger_service.get_ledger(runtime_vars["LEDGER_ID"])
            self.assertEqual(ledger.id, runtime_vars["LEDGER_ID"])
            self.assertEqual(ledger.project_id, runtime_vars["PROJECT_ID"])
            reminders = app._ledger_service.list_reminders()
            self.assertEqual([item.ledger_id for item in reminders], [runtime_vars["LEDGER_ID"]])

    def test_report_accepts_production_oa_test_user_as_identity_source(self) -> None:
        os.environ["FIN_OPS_SHADOW_OA_TOKEN"] = "test-token"
        os.environ["FIN_OPS_SHADOW_OA_PASSWORD"] = "test-password"
        os.environ["FIN_OPS_SHADOW_OA_IDENTITY_SOURCE"] = "production_oa_test_user"
        os.environ["FIN_OPS_SHADOW_OA_USERNAME"] = "test"
        os.environ["FIN_OPS_SHADOW_OA_USER_ID"] = "63"

        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as output_dir:
            code = self.legacy_seed.main(
                [
                    "--run-id",
                    "p0-platform-test",
                    "--data-dir",
                    data_dir,
                    "--output-dir",
                    output_dir,
                    "--report-date",
                    "20260517",
                ]
            )

            self.assertEqual(code, 0)
            report = json.loads((Path(output_dir) / "p0-platform-legacy-shadow-seed-20260517.json").read_text())
            self.assertEqual(report["status"], "GO")
            self.assertEqual(report["secret_requirements"]["status"], "GO")
            self.assertEqual(
                report["secret_requirements"]["identity_source"]["value"],
                "production_oa_test_user",
            )
            self.assertEqual(report["secret_requirements"]["identity_source"]["environment"], "production")
            encoded = json.dumps(report, ensure_ascii=False)
            self.assertNotIn("test-token", encoded)
            self.assertNotIn("test-password", encoded)


if __name__ == "__main__":
    unittest.main()
