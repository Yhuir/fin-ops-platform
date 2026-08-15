from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from fin_ops_platform.services.runtime_worker_registry import (
    RUNTIME_WORKER_REGISTRY,
    rabbitmq_dispatch_event_types,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_CONTROL = REPO_ROOT / "deploy/oa/bin/finops-deploy-control.sh"
DISPATCHER_ENV = REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example"
WORKER_UNIT = REPO_ROOT / "deploy/oa/systemd/fin-ops-worker@.service.example"
QUEUE_PRUNE = REPO_ROOT / "deploy/oa/bin/finops-prune-runtime-queue-history.sh"


class DeployRuntimeExampleTests(unittest.TestCase):
    def test_runtime_worker_inventory_is_exactly_the_four_current_workers(self) -> None:
        required = [
            registration.instance_name
            for registration in RUNTIME_WORKER_REGISTRY
            if registration.required
        ]

        self.assertEqual(
            required,
            ["oa-sync", "workbench-matching", "import", "settings-maintenance"],
        )
        self.assertFalse(
            any(event_type.endswith(".read_model.refresh") for event_type in rabbitmq_dispatch_event_types())
        )

    def test_dispatcher_example_contains_only_registry_events(self) -> None:
        values = {}
        for raw_line in DISPATCHER_ENV.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        configured = tuple(
            item.strip()
            for item in values["RABBITMQ_DISPATCH_EVENT_TYPES"].split(",")
            if item.strip()
        )

        self.assertEqual(configured, rabbitmq_dispatch_event_types())

    def test_worker_unit_uses_registry_registration_contract(self) -> None:
        unit = WORKER_UNIT.read_text(encoding="utf-8")

        self.assertIn("--worker-instance ${FIN_OPS_WORKER_INSTANCE}", unit)
        self.assertNotIn("FIN_OPS_WORKER_EVENT_TYPES", unit)
        self.assertNotIn("FIN_OPS_WORKER_KIND", unit)

    def test_activation_retires_unknown_workers_before_ensuring_current_workers(self) -> None:
        script = DEPLOY_CONTROL.read_text(encoding="utf-8")
        activate = script[script.index("activate_release() {") : script.index("repair_active_api_runtime() {")]

        self.assertLess(
            activate.index('retire_unregistered_worker_services "$src"'),
            activate.index('ensure_runtime_workers "$src"'),
        )
        self.assertIn("run_workbench_direct_compatibility_preflight", activate)
        self.assertNotIn("read_model", activate)

    def test_release_gate_uses_one_bounded_stability_window(self) -> None:
        script = DEPLOY_CONTROL.read_text(encoding="utf-8")
        gate = script[script.index("release_gate_activate() {") : script.index('cmd="${1:-}"')]

        self.assertIn("sleep 30", gate)
        self.assertIn('release_gate_checkpoint "$release" t30', gate)
        self.assertNotIn("sleep 60", gate)
        self.assertNotIn("sleep 240", gate)
        self.assertNotIn("t300", gate)

    def test_retired_worker_and_generation_assets_are_absent(self) -> None:
        retired_paths = (
            "deploy/oa/env/fin-ops.worker.workbench-relation.env.example",
            "deploy/oa/env/fin-ops.worker.workbench-relation-rabbitmq.env.example",
            "deploy/oa/bin/finops-prune-workbench-generations.sh",
            "deploy/oa/systemd/finops-prune-workbench-generations.service.example",
            "deploy/oa/systemd/finops-prune-workbench-generations.timer.example",
        )

        for relative_path in retired_paths:
            self.assertFalse((REPO_ROOT / relative_path).exists(), relative_path)

    def test_runtime_queue_prune_has_no_projection_state_dependency(self) -> None:
        helper = QUEUE_PRUNE.read_text(encoding="utf-8")

        self.assertIn("runtime-queue-history-prune", helper)
        self.assertNotIn("read_model_dirty_scopes", helper)

    def test_runtime_queue_prune_is_portable_bash(self) -> None:
        helper = QUEUE_PRUNE.read_text(encoding="utf-8")

        subprocess.run(["bash", "-n", str(QUEUE_PRUNE)], check=True)
        self.assertIn("job_schema_size_query=", helper)
        self.assertNotIn('-Atc \\"', helper)


if __name__ == "__main__":
    unittest.main()
