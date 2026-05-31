from __future__ import annotations

from io import StringIO
import json
import unittest

from fin_ops_platform.tools import run_rabbitmq_staging_preflight as preflight


class FakeRunner(preflight.CommandRunner):
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[tuple[list[str], dict[str, str], int]] = []

    def run(self, command, *, env, timeout):
        self.calls.append((list(command), dict(env), timeout))
        return preflight.CommandResult(returncode=self.returncode, stdout="ok\n", stderr="")


class RabbitMqStagingPreflightTests(unittest.TestCase):
    def test_missing_env_fails_before_running_commands(self) -> None:
        runner = FakeRunner()
        stdout = StringIO()

        exit_code = preflight.main(["--json"], stdout=stdout, runner=runner, environ={})

        self.assertEqual(exit_code, 1)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "fail")
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
        self.assertEqual([check["name"] for check in report["checks"]], [
            "env.required",
            "postgres.integration",
            "rabbitmq.integration",
            "rabbitmq.topology_check",
            "rabbitmq.dispatcher_shadow_check",
            "rabbitmq.consumer_worker_check.workbench",
            "rabbitmq.consumer_worker_check.search_pending",
            "rabbitmq.consumer_worker_check.bank_detail",
            "rabbitmq.consumer_worker_check.invoice_usage_collection",
            "rabbitmq.consumer_worker_check.cost_tax",
            "rabbitmq.consumer_worker_check.oa_sync",
            "rabbitmq.consumer_worker_check.file_migration",
            "rabbitmq.consumer_worker_check.import_job",
        ])
        self.assertEqual(len(runner.calls), 12)
        dispatcher_env = runner.calls[3][1]
        self.assertEqual(dispatcher_env["FIN_OPS_QUEUE_BACKEND"], "postgres")
        self.assertEqual(dispatcher_env["RABBITMQ_SHADOW_PUBLISH"], "true")
        self.assertEqual(dispatcher_env["FIN_OPS_POSTGRES_DATABASE_URL"], env["FIN_OPS_TEST_DATABASE_URL"])
        self.assertEqual(dispatcher_env["RABBITMQ_URL"], env["RABBITMQ_TEST_URL"])
        dispatcher_command = runner.calls[3][0]
        self.assertIn("--event-type", dispatcher_command)
        self.assertIn("workbench.read_model.refresh", dispatcher_command)
        self.assertIn("bank_detail.read_model.refresh", dispatcher_command)
        self.assertIn("input_invoice_usage.read_model.refresh", dispatcher_command)
        self.assertIn("output_invoice_collection.read_model.refresh", dispatcher_command)
        self.assertIn("file_object.gridfs_migration", dispatcher_command)
        self.assertIn("import.process.requested", dispatcher_command)
        worker_env = runner.calls[4][1]
        self.assertEqual(worker_env["FIN_OPS_QUEUE_BACKEND"], "rabbitmq")
        encoded = stdout.getvalue()
        self.assertNotIn("pw@", encoded)
        self.assertNotIn("secret@", encoded)

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
