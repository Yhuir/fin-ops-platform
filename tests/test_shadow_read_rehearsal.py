from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.services.shadow_read_psql_store import PsqlShadowReadStore
from fin_ops_platform.services.shadow_read_rehearsal import (
    ShadowReadDomainSpec,
    ShadowReadRehearsalRunner,
    default_shadow_read_domain_specs,
)
from fin_ops_platform.tools import run_shadow_read_rehearsal


class FakeStore:
    def __init__(self, *, payloads: dict[str, object], backend: str = "fake", failures: dict[str, Exception] | None = None) -> None:
        self.payloads = payloads
        self.storage_backend = backend
        self.failures = failures or {}
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        if name.startswith("load_"):
            def method(*args, **kwargs):
                self.calls.append(name)
                failure = self.failures.get(name)
                if failure is not None:
                    raise failure
                return self.payloads.get(name, {})

            return method
        raise AttributeError(name)


class ShadowReadRehearsalTests(unittest.TestCase):
    def test_runner_reports_pass_for_matching_domain(self) -> None:
        spec = ShadowReadDomainSpec(domain="app_settings", method_name="load_app_settings", severity="P0")
        primary = FakeStore(payloads={"load_app_settings": {"admin_usernames": ["admin"]}}, backend="mongo")
        shadow = FakeStore(payloads={"load_app_settings": {"admin_usernames": ["admin"]}}, backend="postgres")

        report = ShadowReadRehearsalRunner(
            primary_store=primary,
            shadow_store=shadow,
            domain_specs=[spec],
            run_id="run-1",
        ).run().to_dict()

        self.assertEqual(report["gate_recommendation"], "PASS")
        self.assertEqual(report["summary"]["matched_domains"], 1)
        self.assertEqual(report["domain_results"][0]["status"], "matched")

    def test_runner_classifies_mismatch_with_severity(self) -> None:
        spec = ShadowReadDomainSpec(
            domain="no_oa_bank_batches",
            method_name="load_no_oa_bank_batches",
            severity="P2",
            severity_by_path={"batches.batch-1.status": "P0"},
        )
        primary = FakeStore(payloads={"load_no_oa_bank_batches": {"batches": {"batch-1": {"status": "ready"}}}})
        shadow = FakeStore(payloads={"load_no_oa_bank_batches": {"batches": {"batch-1": {"status": "missing"}}}})

        report = ShadowReadRehearsalRunner(
            primary_store=primary,
            shadow_store=shadow,
            domain_specs=[spec],
            run_id="run-2",
        ).run().to_dict()

        self.assertEqual(report["gate_recommendation"], "BLOCKED")
        self.assertEqual(report["summary"]["severity_counts"]["P0"], 1)
        self.assertEqual(report["domain_results"][0]["mismatches"][0]["severity"], "P0")
        self.assertNotIn("ready", json.dumps(report, ensure_ascii=False))
        self.assertIn("sha256", report["domain_results"][0]["mismatches"][0]["primary"])

    def test_runner_allows_p2_only_runtime_mismatch_as_partial(self) -> None:
        spec = ShadowReadDomainSpec(domain="background_jobs", method_name="load_background_jobs", severity="P2")
        primary = FakeStore(payloads={"load_background_jobs": {}})
        shadow = FakeStore(
            payloads={
                "load_background_jobs": {
                    "job-1": {
                        "type": "file_import",
                        "status": "succeeded",
                        "finished_at": "2026-05-20T10:00:00+00:00",
                    }
                }
            }
        )

        report = ShadowReadRehearsalRunner(
            primary_store=primary,
            shadow_store=shadow,
            domain_specs=[spec],
            run_id="run-p2-only",
        ).run().to_dict()

        self.assertEqual(report["gate_recommendation"], "PARTIAL")
        self.assertEqual(report["summary"]["severity_counts"], {"P0": 0, "P1": 0, "P2": 1, "ignored": 0})
        self.assertEqual(report["summary"]["primary_errors"], 0)
        self.assertEqual(report["summary"]["shadow_errors"], 0)

    def test_pending_invoice_command_mismatch_blocks_as_p1(self) -> None:
        spec = ShadowReadDomainSpec(
            domain="pending_invoice_commands",
            method_name="load_pending_invoice_commands",
            severity="P1",
        )
        primary = FakeStore(payloads={"load_pending_invoice_commands": {"cmd-1": {"status": "failed_recoverable"}}})
        shadow = FakeStore(payloads={"load_pending_invoice_commands": {"cmd-1": {"status": "completed"}}})

        report = ShadowReadRehearsalRunner(primary_store=primary, shadow_store=shadow, domain_specs=[spec]).run().to_dict()

        self.assertEqual(report["gate_recommendation"], "BLOCKED")
        self.assertEqual(report["summary"]["severity_counts"]["P1"], 1)

    def test_shadow_error_is_redacted_and_blocks_gate(self) -> None:
        spec = ShadowReadDomainSpec(domain="jobs", method_name="load_background_jobs", severity="P1")
        primary = FakeStore(payloads={"load_background_jobs": {"job-1": {"status": "done"}}})
        sensitive_password = "sensitive" + "-password"
        sensitive_token = "to" + "ken=abc"
        shadow = FakeStore(
            payloads={},
            failures={
                "load_background_jobs": RuntimeError(
                    "failed " + "postgresql://user:" + sensitive_password + "@db.example/fin_ops?" + sensitive_token
                )
            },
        )

        report = ShadowReadRehearsalRunner(
            primary_store=primary,
            shadow_store=shadow,
            domain_specs=[spec],
            run_id="run-secret",
        ).run().to_dict()

        encoded = json.dumps(report, sort_keys=True)
        self.assertEqual(report["gate_recommendation"], "BLOCKED")
        self.assertEqual(report["summary"]["shadow_errors"], 1)
        self.assertNotIn(sensitive_password, encoded)
        self.assertNotIn(sensitive_token, encoded)
        self.assertIn("<redacted-uri>", encoded)

    def test_primary_error_is_reported_without_shadow_call(self) -> None:
        spec = ShadowReadDomainSpec(domain="jobs", method_name="load_background_jobs")
        primary = FakeStore(payloads={}, failures={"load_background_jobs": RuntimeError("primary unavailable")})
        shadow = FakeStore(payloads={"load_background_jobs": {"job-1": {}}})

        report = ShadowReadRehearsalRunner(primary_store=primary, shadow_store=shadow, domain_specs=[spec]).run().to_dict()

        self.assertEqual(report["summary"]["primary_errors"], 1)
        self.assertEqual(shadow.calls, [])

    def test_forbidden_methods_and_oa_domains_are_rejected(self) -> None:
        for method_name in ("save_app_settings", "store_import_file", "read_import_file", "load_oa_sync_state"):
            with self.subTest(method_name=method_name):
                with self.assertRaisesRegex(ValueError, "Shadow-read rehearsal"):
                    ShadowReadDomainSpec(domain="bad", method_name=method_name)

    def test_default_domain_specs_are_conservative_and_json_safe(self) -> None:
        specs = default_shadow_read_domain_specs(
            domains=["app_settings", "workbench_pair_relations", "pending_invoice_commands"],
            max_mismatches=3,
        )

        self.assertEqual([spec.domain for spec in specs], ["app_settings", "workbench_pair_relations", "pending_invoice_commands"])
        self.assertEqual(specs[-1].method_name, "load_pending_invoice_commands")
        self.assertEqual(specs[-1].severity, "P1")
        self.assertTrue(all(not spec.method_name.startswith("load_oa") for spec in specs))
        json.dumps([spec.to_dict() for spec in specs], ensure_ascii=False)

    def test_default_domain_specs_do_not_include_legacy_page_read_models(self) -> None:
        specs = default_shadow_read_domain_specs()
        domains = {spec.domain for spec in specs}

        self.assertNotIn("workbench_read_models", domains)
        self.assertNotIn("cost_statistics_read_models", domains)
        self.assertNotIn("tax_offset_read_models", domains)
        with self.assertRaisesRegex(ValueError, "Unsupported shadow-read domains"):
            default_shadow_read_domain_specs(domains=["workbench_read_models"])

    def test_cli_rejects_forbidden_flags(self) -> None:
        stderr = StringIO()

        exit_code = run_shadow_read_rehearsal.main(["--cutover"], stdout=StringIO(), stderr=stderr)

        self.assertEqual(exit_code, 2)
        self.assertIn("refuses write or cutover action", stderr.getvalue())

    def test_cli_requires_read_only_guard_for_production(self) -> None:
        stderr = StringIO()

        with patch.dict("os.environ", {}, clear=True):
            exit_code = run_shadow_read_rehearsal.main(
                ["--production", "--json"],
                stdout=StringIO(),
                stderr=stderr,
                runner=run_shadow_read_rehearsal.StaticRunner({"gate_recommendation": "PASS"}),
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1", stderr.getvalue())

    def test_cli_outputs_json_and_artifact_with_injected_runner(self) -> None:
        report = {
            "run_id": "run-cli",
            "gate_recommendation": "PASS",
            "primary_backend": "local_pickle",
            "shadow_backend": "postgres",
            "summary": {"total_domains": 0},
            "domain_results": [],
        }
        stdout = StringIO()
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {"FIN_OPS_SHADOW_REHEARSAL_READ_ONLY": "1"},
            clear=True,
        ):
            output_path = Path(temp_dir) / "report.json"
            exit_code = run_shadow_read_rehearsal.main(
                ["--json", "--production", "--output", str(output_path)],
                stdout=stdout,
                stderr=StringIO(),
                runner=run_shadow_read_rehearsal.StaticRunner(report),
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["run_id"], "run-cli")
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["run_id"], "run-cli")

    def test_cli_outputs_markdown(self) -> None:
        report = {
            "run_id": "run-md",
            "gate_recommendation": "PARTIAL",
            "primary_backend": "local_pickle",
            "shadow_backend": "postgres",
            "summary": {"total_domains": 1, "compared_domains": 1, "matched_domains": 0, "mismatched_domains": 1},
            "domain_results": [
                {
                    "domain": "jobs",
                    "status": "mismatched",
                    "mismatch_count": 1,
                    "severity_counts": {"P0": 0, "P1": 0, "P2": 1},
                }
            ],
        }
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {"FIN_OPS_SHADOW_REHEARSAL_READ_ONLY": "1"},
            clear=True,
        ):
            output_path = Path(temp_dir) / "report.md"
            stdout = StringIO()
            exit_code = run_shadow_read_rehearsal.main(
                ["--markdown", "--production", "--output", str(output_path)],
                stdout=stdout,
                stderr=StringIO(),
                runner=run_shadow_read_rehearsal.StaticRunner(report),
            )

            self.assertEqual(exit_code, 1)
            self.assertIn("# Shadow-read rehearsal run-md", stdout.getvalue())
            self.assertIn("| jobs | mismatched |", output_path.read_text(encoding="utf-8"))

    def test_psql_shadow_store_uses_fixed_read_only_shapes(self) -> None:
        calls: list[list[str]] = []
        outputs = [
            '{"admin_usernames":["admin"]}',
            '{}',
            '{"job-1":{"status":"done"}}',
            '{}',
            '{"alert-1":{"status":"open"}}',
            '{"case-1":{"status":"paired"}}',
            '[{"pair_relation_history":[{"event_id":"pair-event"}]}]',
            '{}',
            '{"batch-1":{"status":"ready"}}',
            '[{"event_id":"batch-event"}]',
            '{"schema_version":"no-oa-v1"}',
            '{"tx-1":{"category_code":"sales"}}',
            '[{"audit_log":[{"event_id":"category-event"}]}]',
            '{"schema_version":"category-v1","categories":{},"audit_log":[]}',
            '[{"relation_id":"rel-1","status":"active"}]',
            '[{"event_id":"turnover-event"}]',
            '{"schema_version":"turnover-v1","relations":[],"audit_log":[]}',
            '{"cmd-1":{"request_id":"cmd-1","status":"failed_recoverable"}}',
        ]

        def fake_run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=outputs.pop(0), stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            store = PsqlShadowReadStore(database="fin_ops", psql_command="sudo -u postgres psql")

            self.assertEqual(store.load_app_settings()["admin_usernames"], ["admin"])
            self.assertEqual(store.load_background_jobs(), {"job-1": {"status": "done"}})
            self.assertEqual(store.load_app_health_alerts(), {"records": {"alert-1": {"status": "open"}}})
            self.assertEqual(
                store.load_workbench_pair_relations(),
                {"pair_relations": {"case-1": {"status": "paired"}}, "pair_relation_history": [{"event_id": "pair-event"}]},
            )
            self.assertEqual(
                store.load_no_oa_bank_batches(),
                {"schema_version": "no-oa-v1", "batches": {"batch-1": {"status": "ready"}}, "audit_log": [{"event_id": "batch-event"}]},
            )
            self.assertEqual(
                store.load_bank_transaction_categories(),
                {
                    "schema_version": "category-v1",
                    "categories": {"tx-1": {"category_code": "sales"}},
                    "audit_log": [{"event_id": "category-event"}],
                },
            )
            self.assertEqual(
                store.load_turnover_relations(),
                {
                    "schema_version": "turnover-v1",
                    "relations": [{"relation_id": "rel-1", "status": "active"}],
                    "audit_log": [{"event_id": "turnover-event"}],
                },
            )
            self.assertEqual(store.load_pending_invoice_commands(), {"cmd-1": {"request_id": "cmd-1", "status": "failed_recoverable"}})

        self.assertTrue(all("ON_ERROR_STOP=1" in command for command in calls))
        self.assertTrue(all(command[:3] == ["sudo", "-u", "postgres"] for command in calls))
        self.assertTrue(all("-d" in command and "fin_ops" in command for command in calls))
        self.assertTrue(any("_stage04_child_index" in " ".join(command) for command in calls))

    def test_psql_shadow_store_app_settings_fill_mongo_shape_defaults(self) -> None:
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(["psql"], 0, stdout='{"admin_usernames":["admin"]}', stderr=""),
        ):
            payload = PsqlShadowReadStore(database="fin_ops", psql_command="psql").load_app_settings()

        self.assertEqual(payload["admin_usernames"], ["admin"])
        self.assertEqual(payload["bank_transaction_tags"], {})
        self.assertEqual(payload["pending_invoice_tag_groups"], {})

    def test_cli_builds_psql_shadow_backend_without_psycopg(self) -> None:
        with patch.dict("os.environ", {"FIN_OPS_SHADOW_REHEARSAL_READ_ONLY": "1"}, clear=True):
            with patch.object(run_shadow_read_rehearsal, "ApplicationStateStore") as state_store:
                with patch.object(run_shadow_read_rehearsal, "PsqlShadowReadStore") as psql_store:
                    state_store.return_value.storage_backend = "mongo"

                    runner = run_shadow_read_rehearsal.build_runner_from_args(
                        run_shadow_read_rehearsal.build_parser().parse_args(
                            [
                                "--production",
                                "--primary-backend",
                                "mongo_readonly",
                                "--shadow-backend",
                                "postgres_psql_json",
                                "--psql-command",
                                "sudo -u postgres psql",
                                "--postgres-database",
                                "fin_ops",
                                "--domains",
                                "app_settings",
                            ]
                        )
                    )

        self.assertEqual(psql_store.call_args.kwargs["psql_command"], "sudo -u postgres psql")
        self.assertEqual(psql_store.call_args.kwargs["database"], "fin_ops")
        self.assertIsInstance(runner, ShadowReadRehearsalRunner)


if __name__ == "__main__":
    unittest.main()
