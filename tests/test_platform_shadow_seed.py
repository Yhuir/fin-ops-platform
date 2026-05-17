from __future__ import annotations

import importlib.util
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


def load_seed_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "platform_shadow_seed.py"
    spec = importlib.util.spec_from_file_location("platform_shadow_seed", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PlatformShadowSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seed = load_seed_module()

    def test_seed_plan_is_deterministic_and_exports_runtime_ids(self) -> None:
        first = self.seed.build_seed_plan(run_id="p0-platform-test", actor_id="actor-1")
        second = self.seed.build_seed_plan(run_id="p0-platform-test", actor_id="actor-1")

        self.assertEqual(first, second)
        self.assertEqual(
            set(first.runtime_variables),
            {
                "BACKGROUND_JOB_ID",
                "BANK_TRANSACTION_ID",
                "LEDGER_ID",
                "PROJECT_DELETE_ID",
                "PROJECT_ID",
                "SHADOW_RUN_ID",
            },
        )
        env_text = self.seed.render_env_exports(first)
        self.assertIn("FIN_OPS_SHADOW_OA_TOKEN", env_text)
        self.assertIn("FIN_OPS_SHADOW_OA_PASSWORD", env_text)
        self.assertIn("FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers", env_text)
        self.assertIn("export PROJECT_ID=", env_text)

    def test_seed_sql_covers_all_postgres_probe_sources_and_support_tables(self) -> None:
        plan = self.seed.build_seed_plan(run_id="p0-platform-test", actor_id="test", user_id="63")

        sql = self.seed.render_seed_sql(plan)

        cleanup_marker = sql.index("-- Clean runtime side effects for this SHADOW_RUN_ID before reseeding.")
        first_insert_marker = sql.index("insert into job.worker_tasks")
        self.assertLess(cleanup_marker, first_insert_marker)
        for statement in (
            "delete from app.ledger_events",
            "delete from app.reminder_runs",
            "delete from job.worker_task_acknowledgements",
            "delete from app.project_profile_events",
            "delete from app.project_assignments",
            "delete from app.data_reset_requests",
            "delete from app.write_idempotency_records",
            "delete from job.outbox_events",
            "delete from job.worker_tasks",
            "delete from audit.events",
            "delete from app.settings_profiles",
            "delete from app.project_profiles",
        ):
            self.assertIn(statement, sql)
        for key in (
            "shadow-background-job-ack-p0-platform-test",
            "shadow-settings-save-p0-platform-test",
            "shadow-project-sync-p0-platform-test",
            "shadow-settings-project-p0-platform-test",
            "shadow-settings-project-delete-p0-platform-test",
            "shadow-data-reset-p0-platform-test",
            "shadow-data-reset-direct-p0-platform-test",
            "shadow-project-create-p0-platform-test",
            "shadow-project-assign-p0-platform-test",
            "shadow-ledger-status-p0-platform-test",
            "shadow-reminder-run-p0-platform-test",
        ):
            self.assertIn(key, sql)
        self.assertIn("platform-shadow:p0-platform-test:%", sql)
        self.assertIn("shadow-%p0-platform-test%", sql)
        self.assertIn("payload->>'run_id' = 'p0-platform-test'", sql)
        self.assertIn("metadata->>'run_id' = 'p0-platform-test'", sql)
        self.assertIn("app.create_financial_fact_month_partition", sql)
        for statement in (
            "insert into job.worker_tasks",
            "insert into app.settings_profiles",
            "insert into app.project_profiles",
            "insert into app.bank_transactions",
            "insert into app.ledgers",
            "insert into app.reminders",
            "insert into app.data_reset_requests",
            "insert into job.outbox_events",
            "insert into audit.events",
            "insert into app.write_idempotency_records",
        ):
            self.assertIn(statement, sql)
        for value in plan.runtime_variables.values():
            if value.startswith("p0-platform"):
                continue
            self.assertIn(value, sql)
        self.assertIn("on conflict", sql.lower())
        self.assertIn("timestamptz '2026-05-17 09:00:00+08'", sql)
        self.assertNotIn("updated_at = now()", sql)
        self.assertNotIn("YNSYLP005", sql)
        self.assertNotIn("shadow-admin-user-id", sql)
        self.assertIn("'test'", sql)
        self.assertIn("'63'", sql)
        self.assertIn("1288.00", sql)
        self.assertIn("平台 Shadow 往来单位", sql)
        self.assertIn("'source_object_type', 'bank_transaction'", sql)
        self.assertIn(f"'source_object_id', '{plan.bank_transaction_id}'", sql)
        self.assertIn("'channel', 'in_app'", sql)
        self.assertIn("commit;", sql)

    def test_probe_sql_checks_every_runtime_fact_id_with_status_requirements(self) -> None:
        plan = self.seed.build_seed_plan(run_id="p0-platform-test", actor_id="actor-1")

        probe_sql = self.seed.render_probe_sql(plan)

        expected_checks = {
            "BACKGROUND_JOB_ID": "job.worker_tasks",
            "BANK_TRANSACTION_ID": "app.bank_transactions",
            "LEDGER_ID": "app.ledgers",
            "PROJECT_ID": "app.project_profiles",
            "PROJECT_DELETE_ID": "app.project_profiles",
        }
        for variable, table in expected_checks.items():
            self.assertIn(variable, probe_sql)
            self.assertIn(table, probe_sql)
        self.assertIn("visibility = 'system'", probe_sql)
        self.assertIn("status = 'open'", probe_sql)
        self.assertIn("project_status = 'active'", probe_sql)

    def test_seed_report_records_legacy_no_go_without_secrets(self) -> None:
        plan = self.seed.build_seed_plan(run_id="p0-platform-test", actor_id="test", user_id="63")

        report = self.seed.build_report(
            plan=plan,
            report_date="20260517",
            sql_path=Path("/tmp/seed.sql"),
            env_path=Path("/tmp/env.sh"),
            probe_sql_path=Path("/tmp/probe.sql"),
            apply_status="SKIPPED",
            database_url_present=False,
        )

        self.assertEqual(report["status"], "NO_GO")
        self.assertEqual(report["postgres_seed_generation"]["status"], "GO")
        self.assertEqual(report["postgres_seed_generation"]["cleanup_model"]["status"], "GO")
        self.assertEqual(report["postgres_apply"]["status"], "SKIPPED")
        self.assertEqual(report["legacy_python_mongo_seed_plan"]["status"], "NO_GO")
        self.assertIn("background_jobs", report["legacy_python_mongo_seed_plan"]["required_collections"])
        self.assertIn("app_settings", report["legacy_python_mongo_seed_plan"]["required_collections"])
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("postgres://", encoded)
        self.assertNotIn("mongodb://", encoded)
        self.assertNotIn("password=", encoded.lower())
        self.assertNotIn("token=", encoded.lower())

    def test_cli_writes_sql_env_probe_and_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = self.seed.main(
                    [
                        "--run-id",
                        "p0-platform-test",
                        "--actor-id",
                        "test",
                        "--user-id",
                        "63",
                        "--output-dir",
                        tmpdir,
                        "--report-date",
                        "20260517",
                    ]
                )

            self.assertEqual(code, 0)
            self.assertIn("p0-platform-shadow-seed-20260517.json", stdout.getvalue())
            output_dir = Path(tmpdir)
            self.assertTrue((output_dir / "p0-platform-shadow-seed-p0-platform-test.sql").exists())
            self.assertTrue((output_dir / "p0-platform-shadow-env-p0-platform-test.sh").exists())
            self.assertTrue((output_dir / "p0-platform-shadow-probe-p0-platform-test.sql").exists())
            report_path = output_dir / "p0-platform-shadow-seed-20260517.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "NO_GO")
            self.assertEqual(report["runtime_variables"]["SHADOW_RUN_ID"], "p0-platform-test")


if __name__ == "__main__":
    unittest.main()
