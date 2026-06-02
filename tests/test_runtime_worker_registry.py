from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import unittest

from fin_ops_platform.app import worker as worker_app
from fin_ops_platform.tools import runtime_worker_manifest
from fin_ops_platform.services.rabbitmq_runtime import SUPPORTED_EVENT_TYPES
from fin_ops_platform.services.runtime_monitoring import READ_MODEL_EVENT_TYPES
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES
from fin_ops_platform.services.runtime_worker_registry import (
    rabbitmq_dispatch_event_types,
    registration_by_instance_name,
    required_worker_instance_names,
    worker_check_command_args,
    worker_claim_event_types,
    worker_command_args,
    worker_registrations,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ENSURE_WORKERS_SCRIPT = REPO_ROOT / "deploy/oa/bin/finops-ensure-runtime-workers.sh"
ENV_DIR = REPO_ROOT / "deploy/oa/env"
DISPATCHER_ENV = ENV_DIR / "fin-ops.rabbitmq-dispatcher.env.example"


class RuntimeWorkerRegistryTests(unittest.TestCase):
    def test_required_workers_match_deploy_helper_defaults(self) -> None:
        script = ENSURE_WORKERS_SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(script, r"required_workers=\"\\$\\{FINOPS_REQUIRED_WORKERS:-")
        self.assertIn("runtime_worker_manifest --required-instances", script)

    def test_required_workers_have_env_examples_and_heartbeat_slos(self) -> None:
        for registration in worker_registrations(required_only=True):
            self.assertTrue(registration.worker_kind)
            self.assertGreater(registration.heartbeat_stale_after_seconds, 0)
            self.assertTrue((ENV_DIR / registration.env_example).exists(), registration.env_example)
            self.assertTrue(registration.handler_flags or registration.event_types)

    def test_registered_worker_env_examples_exist(self) -> None:
        for registration in worker_registrations():
            self.assertTrue((ENV_DIR / registration.env_example).exists(), registration.env_example)
            if registration.rabbitmq_env_example:
                self.assertTrue((ENV_DIR / registration.rabbitmq_env_example).exists(), registration.rabbitmq_env_example)

    def test_rabbitmq_supported_and_default_dispatch_events_are_registry_derived(self) -> None:
        registry_events = rabbitmq_dispatch_event_types()

        self.assertEqual(DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, registry_events)
        self.assertEqual(SUPPORTED_EVENT_TYPES, registry_events)

    def test_rabbitmq_dispatcher_env_example_covers_registry_events(self) -> None:
        dispatcher_env = DISPATCHER_ENV.read_text(encoding="utf-8")

        for event_type in rabbitmq_dispatch_event_types():
            self.assertIn(event_type, dispatcher_env)

    def test_registration_lookup_and_command_args_are_registry_derived(self) -> None:
        registration = registration_by_instance_name()["workbench"]

        self.assertEqual(
            worker_command_args(registration, transport="postgres"),
            (
                "--enable-workbench-read-model-refresh",
                "--event-type",
                "workbench.read_model.refresh",
            ),
        )
        self.assertEqual(
            worker_check_command_args(registration, transport="postgres"),
            (
                "--registration",
                "workbench",
                "--worker-instance",
                "workbench",
                "--check",
            ),
        )

    def test_import_claim_events_include_postgres_local_ack_event_but_rabbitmq_dispatch_does_not(self) -> None:
        registration = registration_by_instance_name()["import"]

        self.assertEqual(
            worker_claim_event_types(registration, transport="postgres"),
            ("import.process.requested", "import.fact.changed"),
        )
        self.assertEqual(
            worker_claim_event_types(registration, transport="rabbitmq"),
            ("import.process.requested",),
        )
        self.assertIn("import.process.requested", rabbitmq_dispatch_event_types())
        self.assertNotIn("import.fact.changed", rabbitmq_dispatch_event_types())

    def test_read_model_monitoring_events_are_covered_by_registry(self) -> None:
        registry_events = set(rabbitmq_dispatch_event_types())

        self.assertLessEqual(set(READ_MODEL_EVENT_TYPES), registry_events)

    def test_worker_kind_inference_uses_registry_for_optional_workers(self) -> None:
        args = worker_app.build_parser().parse_args(["--enable-bank-account-balance-read-model-refresh"])

        self.assertEqual(worker_app._infer_worker_kind(args), "bank-account-balance-read-model")

    def test_worker_kind_inference_uses_registry_for_turnover_ledger_worker(self) -> None:
        args = worker_app.build_parser().parse_args(["--enable-turnover-ledger-read-model-refresh"])

        self.assertEqual(worker_app._infer_worker_kind(args), "turnover-ledger-read-model")

    def test_worker_kind_inference_uses_registry_for_no_oa_bank_batch_worker(self) -> None:
        args = worker_app.build_parser().parse_args(["--enable-no-oa-bank-batch-read-model-refresh"])

        self.assertEqual(worker_app._infer_worker_kind(args), "no-oa-bank-batch-read-model")

    def test_worker_registration_check_outputs_registry_derived_configuration(self) -> None:
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = worker_app.main(["--registration", "workbench", "--worker-instance", "workbench", "--check"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["worker_instance"], "workbench")
        self.assertEqual(payload["worker_kind"], "workbench-read-model")
        self.assertEqual(payload["event_types"], ["workbench.read_model.refresh"])
        self.assertEqual(payload["handlers"], ["workbench.read_model.refresh"])
        self.assertEqual(payload["registration"]["instance_name"], "workbench")

    def test_unknown_worker_registration_fails_fast(self) -> None:
        with self.assertRaises(SystemExit):
            worker_app.main(["--registration", "missing-worker", "--check"])

    def test_manifest_cli_lists_required_instances_and_env_examples(self) -> None:
        stdout = io.StringIO()

        exit_code = runtime_worker_manifest.main(["--required-instances"], stdout=stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(tuple(stdout.getvalue().split()), required_worker_instance_names())

        stdout = io.StringIO()
        exit_code = runtime_worker_manifest.main(["--env-example", "workbench"], stdout=stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "fin-ops.worker.workbench.env.example")


if __name__ == "__main__":
    unittest.main()
