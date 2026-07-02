from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.runtime_worker_registry import RUNTIME_WORKER_REGISTRY


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_CONTROL = REPO_ROOT / "deploy/oa/bin/finops-deploy-control.sh"
ENSURE_RUNTIME_WORKERS = REPO_ROOT / "deploy/oa/bin/finops-ensure-runtime-workers.sh"
WORKER_SERVICE = REPO_ROOT / "deploy/oa/systemd/fin-ops-worker@.service.example"
DISPATCHER_SERVICE = REPO_ROOT / "deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example"
PRUNE_SERVICE = REPO_ROOT / "deploy/oa/systemd/finops-prune-workbench-generations.service.example"
PRUNE_TIMER = REPO_ROOT / "deploy/oa/systemd/finops-prune-workbench-generations.timer.example"
RUNTIME_QUEUE_PRUNE_SERVICE = REPO_ROOT / "deploy/oa/systemd/finops-prune-runtime-queue-history.service.example"
RUNTIME_QUEUE_PRUNE_TIMER = REPO_ROOT / "deploy/oa/systemd/finops-prune-runtime-queue-history.timer.example"
DISPATCHER_ENV = REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example"
RABBITMQ_WORKER_ENV = REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-worker.env.example"
WORKER_ENV_DIR = REPO_ROOT / "deploy/oa/env"
PRUNE_HELPER = REPO_ROOT / "deploy/oa/bin/finops-prune-workbench-generations.sh"
RUNTIME_QUEUE_PRUNE_HELPER = REPO_ROOT / "deploy/oa/bin/finops-prune-runtime-queue-history.sh"


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

    def test_required_worker_env_examples_do_not_pin_legacy_slow_poll_interval(self) -> None:
        slow_examples: list[str] = []
        for registration in RUNTIME_WORKER_REGISTRY:
            if not registration.required or not registration.env_example:
                continue
            env_example = WORKER_ENV_DIR / registration.env_example
            content = env_example.read_text(encoding="utf-8")
            if "--poll-interval-seconds 2" in content:
                slow_examples.append(registration.env_example)
            if registration.instance_name != "workbench-matching" and "--poll-interval-seconds 5" in content:
                slow_examples.append(registration.env_example)

        self.assertEqual([], slow_examples)

    def test_runtime_worker_env_install_migrates_only_legacy_poll_interval(self) -> None:
        helper = ENSURE_RUNTIME_WORKERS.read_text(encoding="utf-8")

        self.assertIn("install_if_missing", helper)
        self.assertIn("migrate_legacy_worker_poll_interval", helper)
        self.assertIn("--poll-interval-seconds 2([^0-9.]|$)", helper)
        self.assertIn("--poll-interval-seconds 0.25", helper)

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

    def test_workbench_generation_prune_helper_uses_current_retention_defaults(self) -> None:
        helper = PRUNE_HELPER.read_text(encoding="utf-8")
        service = PRUNE_SERVICE.read_text(encoding="utf-8")
        timer = PRUNE_TIMER.read_text(encoding="utf-8")
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")

        self.assertIn("KEEP_RECENT=\"${FINOPS_WORKBENCH_PRUNE_KEEP_RECENT:-1}\"", helper)
        self.assertIn("KEEP_DAYS=\"${FINOPS_WORKBENCH_PRUNE_KEEP_DAYS:-0}\"", helper)
        self.assertIn("LIMIT=\"${FINOPS_WORKBENCH_PRUNE_LIMIT:-500}\"", helper)
        self.assertNotIn("FINOPS_WORKBENCH_PRUNE_KEEP_RECENT:-3", helper)
        self.assertNotIn("FINOPS_WORKBENCH_PRUNE_KEEP_DAYS:-1", helper)
        self.assertIn("--keep-recent-generations-per-scope \"$KEEP_RECENT\"", helper)
        self.assertIn("--keep-days \"$KEEP_DAYS\"", helper)
        self.assertIn("status <> 'active'", (REPO_ROOT / "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py").read_text(encoding="utf-8"))

        self.assertIn("ExecStart=/usr/local/sbin/finops-prune-workbench-generations", service)
        self.assertIn("OnCalendar=*-*-* 03:35:00", timer)
        self.assertIn("install_workbench_generation_retention", deploy_control)
        self.assertIn("finops-prune-workbench-generations.sh", deploy_control)
        self.assertIn("systemctl enable --now \"$timer_unit\"", deploy_control)

    def test_runtime_queue_history_prune_helper_uses_controlled_retention_defaults(self) -> None:
        helper = RUNTIME_QUEUE_PRUNE_HELPER.read_text(encoding="utf-8")
        service = RUNTIME_QUEUE_PRUNE_SERVICE.read_text(encoding="utf-8")
        timer = RUNTIME_QUEUE_PRUNE_TIMER.read_text(encoding="utf-8")
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")

        self.assertIn("KEEP_DAYS=\"${FINOPS_RUNTIME_QUEUE_PRUNE_KEEP_DAYS:-30}\"", helper)
        self.assertIn("KEEP_RECENT_PER_TYPE=\"${FINOPS_RUNTIME_QUEUE_PRUNE_KEEP_RECENT_PER_TYPE:-512}\"", helper)
        self.assertIn("LIMIT=\"${FINOPS_RUNTIME_QUEUE_PRUNE_LIMIT:-20000}\"", helper)
        self.assertIn("FIN_OPS_POSTGRES_DATABASE_URL=\"$FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL\"", helper)
        self.assertIn("-m fin_ops_platform.tools.runtime_queue_ops prune-history", helper)
        self.assertIn("--execute", helper)

        self.assertIn("ExecStart=/usr/local/sbin/finops-prune-runtime-queue-history", service)
        self.assertIn("OnCalendar=*-*-* 03:55:00", timer)
        self.assertIn("install_runtime_queue_history_retention", deploy_control)
        self.assertIn("finops-prune-runtime-queue-history.sh", deploy_control)
        self.assertIn("systemctl enable --now \"$timer_unit\"", deploy_control)


if __name__ == "__main__":
    unittest.main()
