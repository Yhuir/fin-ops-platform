from __future__ import annotations

from io import StringIO
import json
import unittest

from fin_ops_platform.tools import run_rabbitmq_staging_preflight as preflight
from fin_ops_platform.services.runtime_worker_registry import worker_registrations


class FakeRunner(preflight.CommandRunner):
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[tuple[list[str], dict[str, str], int]] = []

    def run(self, command, *, env, timeout):
        self.calls.append((list(command), dict(env), timeout))
        return preflight.CommandResult(returncode=self.returncode, stdout="ok\n", stderr="")


class RabbitMqStagingPreflightTests(unittest.TestCase):
    def test_missing_env_returns_configuration_missing_before_running_commands(self) -> None:
        runner = FakeRunner()
        stdout = StringIO()

        exit_code = preflight.main(["--json"], stdout=stdout, runner=runner, environ={})

        self.assertEqual(exit_code, 2)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "configuration_missing")
        self.assertEqual(report["error"], "staging_preflight_environment_missing")
        self.assertEqual(report["required_env"], ["FIN_OPS_TEST_DATABASE_URL", "RABBITMQ_TEST_URL"])
        self.assertEqual(report["checks"][0]["name"], "env.required")
        self.assertEqual(report["checks"][0]["metadata"]["missing"], ["FIN_OPS_TEST_DATABASE_URL", "RABBITMQ_TEST_URL"])
        self.assertEqual(runner.calls, [])

    def test_preflight_runs_real_checks_with_runtime_env_fallbacks(self) -> None:
        runner = FakeRunner()
        env = {
            "FIN_OPS_TEST_DATABASE_URL": "postgresql://user:pw@postgres.internal:5432/fin_ops_test",
            "RABBITMQ_TEST_URL": "amqp://worker:secret@rabbitmq.internal/%2Ffinops",
        }
        stdout = StringIO()

        exit_code = preflight.main(["--json"], stdout=stdout, runner=runner, environ=env)

        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "pass")
        worker_check_names = [
            f"rabbitmq.consumer_worker_check.{registration.instance_name.replace('-', '_')}"
            for registration in worker_registrations(required_only=True, rabbitmq_eligible_only=True)
        ]
        self.assertEqual([check["name"] for check in report["checks"]], [
            "env.required",
            "postgres.integration",
            "rabbitmq.integration",
            "rabbitmq.topology_check",
            "rabbitmq.dispatcher_shadow_check",
            *worker_check_names,
        ])
        self.assertEqual(report["include_optional_workers"], False)
        self.assertEqual(len(runner.calls), 4 + len(worker_check_names))
        dispatcher_env = runner.calls[3][1]
        self.assertEqual(dispatcher_env["FIN_OPS_QUEUE_BACKEND"], "postgres")
        self.assertEqual(dispatcher_env["RABBITMQ_SHADOW_PUBLISH"], "true")
        self.assertEqual(dispatcher_env["FIN_OPS_POSTGRES_DATABASE_URL"], env["FIN_OPS_TEST_DATABASE_URL"])
        self.assertEqual(dispatcher_env["RABBITMQ_URL"], env["RABBITMQ_TEST_URL"])
        dispatcher_command = runner.calls[3][0]
        self.assertIn("--event-type", dispatcher_command)
        self.assertIn("workbench.read_model.refresh", dispatcher_command)
        self.assertIn("bank_detail.read_model.refresh", dispatcher_command)
        self.assertIn("no_oa_bank_batch.read_model.refresh", dispatcher_command)
        self.assertIn("invoice_lifecycle.read_model.refresh", dispatcher_command)
        self.assertIn("input_invoice_usage.read_model.refresh", dispatcher_command)
        self.assertIn("output_invoice_collection.read_model.refresh", dispatcher_command)
        self.assertIn("bank_account_balance.read_model.refresh", dispatcher_command)
        self.assertIn("file_object.gridfs_migration", dispatcher_command)
        self.assertIn("import.process.requested", dispatcher_command)
        worker_env = runner.calls[4][1]
        self.assertEqual(worker_env["FIN_OPS_QUEUE_BACKEND"], "rabbitmq")
        worker_command = runner.calls[4][0]
        self.assertIn("--registration", worker_command)
        self.assertIn("oa-sync", worker_command)
        self.assertIn("--worker-instance", worker_command)
        self.assertNotIn("--enable-oa-sync", worker_command)
        encoded = stdout.getvalue()
        self.assertNotIn("pw@", encoded)
        self.assertNotIn("secret@", encoded)

    def test_include_optional_workers_runs_optional_rabbitmq_checks(self) -> None:
        runner = FakeRunner()
        env = {
            "FIN_OPS_TEST_DATABASE_URL": "postgresql://user:pw@postgres.internal:5432/fin_ops_test",
            "RABBITMQ_TEST_URL": "amqp://worker:secret@rabbitmq.internal/%2Ffinops",
        }
        stdout = StringIO()

        exit_code = preflight.main(
            ["--json", "--skip-real-tests", "--include-optional-workers"],
            stdout=stdout,
            runner=runner,
            environ=env,
        )

        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["include_optional_workers"], True)
        check_names = [check["name"] for check in report["checks"]]
        self.assertIn("rabbitmq.consumer_worker_check.file_migration", check_names)

    def test_apply_topology_adds_explicit_apply_command(self) -> None:
        runner = FakeRunner()
        env = {
            "FIN_OPS_TEST_DATABASE_URL": "postgresql://user:pw@postgres.internal:5432/fin_ops_test",
            "RABBITMQ_TEST_URL": "amqp://worker:secret@rabbitmq.internal/%2Ffinops",
        }

        exit_code = preflight.main(["--json", "--apply-topology"], stdout=StringIO(), runner=runner, environ=env)

        self.assertEqual(exit_code, 0)
        commands = [" ".join(call[0]) for call in runner.calls]
        self.assertTrue(any("fin_ops_platform.app.rabbitmq_topology --apply" in command for command in commands))

    def test_command_failure_fails_report(self) -> None:
        runner = FakeRunner(returncode=1)
        env = {
            "FIN_OPS_TEST_DATABASE_URL": "postgresql://user:pw@postgres.internal:5432/fin_ops_test",
            "RABBITMQ_TEST_URL": "amqp://worker:secret@rabbitmq.internal/%2Ffinops",
        }
        stdout = StringIO()

        exit_code = preflight.main(["--json"], stdout=stdout, runner=runner, environ=env)

        self.assertEqual(exit_code, 1)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["checks"][1]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
