from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import unittest

from fin_ops_platform.app import worker as worker_app
from fin_ops_platform.tools import runtime_worker_manifest
from fin_ops_platform.services.rabbitmq_runtime import SUPPORTED_EVENT_TYPES
from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
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

    def test_workbench_read_model_worker_registration_is_removed(self) -> None:
        with self.assertRaises(SystemExit):
            worker_app.build_parser().parse_args(["--enable-workbench-read-model-refresh"])
        self.assertNotIn("workbench", registration_by_instance_name())
        self.assertNotIn("workbench.read_model.refresh", rabbitmq_dispatch_event_types())
        self.assertNotIn("workbench", APP_STATUS_READ_MODEL_REGISTRY)

    def test_cost_tax_read_model_workers_are_removed(self) -> None:
        registrations = registration_by_instance_name()

        self.assertNotIn("cost-tax", registrations)
        self.assertNotIn("cost-statistics", registrations)
        self.assertNotIn("tax-offset", registrations)
        self.assertNotIn("cost_statistics.read_model.refresh", rabbitmq_dispatch_event_types())
        self.assertNotIn("tax_offset.read_model.refresh", rabbitmq_dispatch_event_types())
        self.assertNotIn("pending_invoice", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("bank_account_balance", APP_STATUS_READ_MODEL_REGISTRY)

    def test_invoice_lifecycle_read_model_workers_are_removed(self) -> None:
        registrations = registration_by_instance_name()

        self.assertNotIn("invoice-lifecycle", registrations)
        self.assertNotIn("invoice-lifecycle-secondary", registrations)
        self.assertNotIn("invoice_lifecycle.read_model.refresh", rabbitmq_dispatch_event_types())
        self.assertNotIn("invoice_lifecycle", APP_STATUS_READ_MODEL_REGISTRY)

    def test_import_claim_events_include_import_fact_changed_in_all_transports(self) -> None:
        registration = registration_by_instance_name()["import"]

        self.assertEqual(
            worker_claim_event_types(registration, transport="postgres"),
            ("import.process.requested", "import.fact.changed"),
        )
        self.assertEqual(
            worker_claim_event_types(registration, transport="rabbitmq"),
            ("import.process.requested", "import.fact.changed"),
        )
        self.assertIn("import.process.requested", rabbitmq_dispatch_event_types())
        self.assertIn("import.fact.changed", rabbitmq_dispatch_event_types())

    def test_read_model_event_registry_is_removed(self) -> None:
        self.assertEqual(APP_STATUS_READ_MODEL_REGISTRY, {})

    def test_bank_account_balance_worker_registration_is_removed(self) -> None:
        self.assertNotIn("bank-account-balance", registration_by_instance_name())
        self.assertNotIn("bank_account_balance.read_model.refresh", rabbitmq_dispatch_event_types())

    def test_turnover_ledger_read_model_worker_registration_is_removed(self) -> None:
        with self.assertRaises(SystemExit):
            worker_app.build_parser().parse_args(["--enable-turnover-ledger-read-model-refresh"])
        self.assertNotIn("turnover-ledger", registration_by_instance_name())
        self.assertNotIn("turnover_ledger.read_model.refresh", rabbitmq_dispatch_event_types())

    def test_no_oa_bank_batch_read_model_worker_registration_is_removed(self) -> None:
        self.assertNotIn("no-oa-bank-batch", registration_by_instance_name())
        self.assertNotIn("no_oa_bank_batch.read_model.refresh", rabbitmq_dispatch_event_types())

    def test_unknown_worker_registration_fails_fast(self) -> None:
        with self.assertRaises(SystemExit):
            worker_app.main(["--registration", "missing-worker", "--check"])

    def test_manifest_cli_lists_required_instances_and_env_examples(self) -> None:
        stdout = io.StringIO()

        exit_code = runtime_worker_manifest.main(["--required-instances"], stdout=stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(tuple(stdout.getvalue().split()), required_worker_instance_names())

        with self.assertRaises(KeyError):
            runtime_worker_manifest.main(["--env-example", "workbench"], stdout=io.StringIO())


if __name__ == "__main__":
    unittest.main()
