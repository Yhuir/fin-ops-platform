from __future__ import annotations

from pathlib import Path
import re
import unittest

from fin_ops_platform.app import worker as worker_app
from fin_ops_platform.services.rabbitmq_runtime import SUPPORTED_EVENT_TYPES
from fin_ops_platform.services.runtime_monitoring import READ_MODEL_EVENT_TYPES
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES
from fin_ops_platform.services.runtime_worker_registry import (
    rabbitmq_dispatch_event_types,
    required_worker_instance_names,
    worker_registrations,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ENSURE_WORKERS_SCRIPT = REPO_ROOT / "deploy/oa/bin/finops-ensure-runtime-workers.sh"
ENV_DIR = REPO_ROOT / "deploy/oa/env"
DISPATCHER_ENV = ENV_DIR / "fin-ops.rabbitmq-dispatcher.env.example"


class RuntimeWorkerRegistryTests(unittest.TestCase):
    def test_required_workers_match_deploy_helper_defaults(self) -> None:
        script = ENSURE_WORKERS_SCRIPT.read_text(encoding="utf-8")
        match = re.search(r'FINOPS_REQUIRED_WORKERS:-([^}]+)', script)
        self.assertIsNotNone(match)

        deploy_defaults = tuple(str(match.group(1)).split()) if match else ()

        self.assertEqual(deploy_defaults, required_worker_instance_names())

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


if __name__ == "__main__":
    unittest.main()
