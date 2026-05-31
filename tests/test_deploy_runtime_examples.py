from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class DeployRuntimeExampleTests(unittest.TestCase):
    def test_rabbitmq_dispatcher_systemd_uses_env_allowlist_for_all_runtime_events(self) -> None:
        service = (REPO_ROOT / "deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example").read_text()

        self.assertNotIn("--event-type", service)
        self.assertIn(
            "RABBITMQ_DISPATCH_EVENT_TYPES",
            (REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example").read_text(),
        )

    def test_rabbitmq_dispatcher_env_includes_invoice_usage_collection_events(self) -> None:
        env_example = (REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example").read_text()

        self.assertIn("input_invoice_usage.read_model.refresh", env_example)
        self.assertIn("output_invoice_collection.read_model.refresh", env_example)
        self.assertIn("oa_pending_payment.read_model.refresh", env_example)

    def test_search_pending_workers_and_dispatcher_include_pending_invoice_refresh(self) -> None:
        postgres_worker_env = (REPO_ROOT / "deploy/oa/env/fin-ops.worker.search-pending.env.example").read_text()
        rabbitmq_worker_env = (REPO_ROOT / "deploy/oa/env/fin-ops.worker.search-pending-rabbitmq.env.example").read_text()
        dispatcher_env = (REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example").read_text()

        for env_example in (postgres_worker_env, rabbitmq_worker_env):
            self.assertIn("--enable-search-read-model-refresh", env_example)
            self.assertIn("--enable-pending-invoice-read-model-refresh", env_example)
            self.assertIn("--event-type search.read_model.refresh", env_example)
            self.assertIn("--event-type pending_invoice.read_model.refresh", env_example)
        self.assertIn("pending_invoice.read_model.refresh", dispatcher_env)


if __name__ == "__main__":
    unittest.main()
