from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.runtime_worker_registry import RUNTIME_WORKER_REGISTRY


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_CONTROL = REPO_ROOT / "deploy/oa/bin/finops-deploy-control.sh"
WORKER_SERVICE = REPO_ROOT / "deploy/oa/systemd/fin-ops-worker@.service.example"
DISPATCHER_SERVICE = REPO_ROOT / "deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example"
DISPATCHER_ENV = REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example"
RABBITMQ_WORKER_ENV = REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-worker.env.example"
WORKER_ENV_DIR = REPO_ROOT / "deploy/oa/env"


class DeployRuntimeExampleTests(unittest.TestCase):
    def test_rabbitmq_dispatcher_systemd_uses_env_allowlist_for_all_runtime_events(self) -> None:
        service = DISPATCHER_SERVICE.read_text()

        self.assertNotIn("--event-type", service)
        self.assertIn(
            "RABBITMQ_DISPATCH_EVENT_TYPES",
            DISPATCHER_ENV.read_text(),
        )

    def test_rabbitmq_dispatcher_poll_interval_is_env_controlled_and_fast_by_default(self) -> None:
        service = DISPATCHER_SERVICE.read_text()
        env_example = DISPATCHER_ENV.read_text()
        deploy_control = DEPLOY_CONTROL.read_text()

        self.assertIn("RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.5", env_example)
        self.assertIn("Environment=RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.5", service)
        self.assertIn("--poll-interval-seconds ${RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS}", service)
        self.assertIn("Environment=RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.5", deploy_control)
        self.assertIn("--poll-interval-seconds \\${RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS}", deploy_control)
        self.assertNotIn("--poll-interval-seconds 5", service)
        self.assertNotIn("--poll-interval-seconds 5", deploy_control)

    def test_deploy_control_worker_dropin_preserves_per_worker_throughput_env(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text()
        worker_service = WORKER_SERVICE.read_text()

        self.assertIn("--max-events-per-iteration \\${FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION}", deploy_control)
        self.assertIn(
            "--dependency-not-fresh-delay-seconds \\${FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS}",
            deploy_control,
        )
        self.assertNotIn("Environment=FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=1", deploy_control)
        self.assertIn("--max-events-per-iteration ${FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION}", worker_service)
        self.assertIn(
            "--dependency-not-fresh-delay-seconds ${FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS}",
            worker_service,
        )
        self.assertNotIn("Environment=FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=1", worker_service)

    def test_required_worker_env_examples_define_max_events_per_iteration(self) -> None:
        missing_examples: list[str] = []
        for registration in RUNTIME_WORKER_REGISTRY:
            if not registration.required or not registration.env_example:
                continue
            env_example = WORKER_ENV_DIR / registration.env_example
            content = env_example.read_text(encoding="utf-8")
            if "FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=" not in content:
                missing_examples.append(registration.env_example)

        self.assertEqual([], missing_examples)

    def test_rabbitmq_dispatcher_env_includes_invoice_usage_collection_events(self) -> None:
        env_example = DISPATCHER_ENV.read_text()

        self.assertIn("invoice_lifecycle.read_model.refresh", env_example)
        self.assertIn("input_invoice_usage.read_model.refresh", env_example)
        self.assertIn("output_invoice_collection.read_model.refresh", env_example)
        self.assertIn("oa_pending_payment.read_model.refresh", env_example)

    def test_shared_rabbitmq_worker_env_does_not_switch_all_workers_to_rabbitmq(self) -> None:
        env_example = RABBITMQ_WORKER_ENV.read_text(encoding="utf-8")

        self.assertNotRegex(env_example, r"(?m)^\s*FIN_OPS_QUEUE_BACKEND=", msg=env_example)
        self.assertIn("RABBITMQ_URL=", env_example)
        self.assertIn("RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS=1", env_example)

    def test_search_pending_workers_and_dispatcher_include_pending_invoice_refresh(self) -> None:
        postgres_worker_env = (REPO_ROOT / "deploy/oa/env/fin-ops.worker.search-pending.env.example").read_text()
        rabbitmq_worker_env = (REPO_ROOT / "deploy/oa/env/fin-ops.worker.search-pending-rabbitmq.env.example").read_text()
        dispatcher_env = DISPATCHER_ENV.read_text()

        for env_example in (postgres_worker_env, rabbitmq_worker_env):
            self.assertIn("--enable-search-read-model-refresh", env_example)
            self.assertIn("--enable-pending-invoice-read-model-refresh", env_example)
            self.assertIn("--event-type search.read_model.refresh", env_example)
            self.assertIn("--event-type pending_invoice.read_model.refresh", env_example)
        self.assertIn("pending_invoice.read_model.refresh", dispatcher_env)


if __name__ == "__main__":
    unittest.main()
