from __future__ import annotations

import io
import unittest

from fin_ops_platform.services.runtime_worker_registry import (
    required_worker_instance_names,
    worker_registrations,
)
from fin_ops_platform.tools import runtime_worker_manifest


class RuntimeWorkerRegistryTests(unittest.TestCase):
    def test_runtime_inventory_has_four_business_workers_and_no_read_models(self) -> None:
        self.assertEqual(
            required_worker_instance_names(),
            ("oa-sync", "workbench-matching", "import", "settings-maintenance"),
        )
        event_types = {
            event_type
            for registration in worker_registrations()
            for event_type in registration.event_types
        }
        self.assertNotIn("workbench_relation.read_model.refresh", event_types)
        self.assertTrue(all("read-model" not in registration.worker_kind for registration in worker_registrations()))

    def test_manifest_cli_uses_registry_inventory(self) -> None:
        stdout = io.StringIO()
        self.assertEqual(runtime_worker_manifest.main(["--required-instances"], stdout=stdout), 0)
        self.assertEqual(tuple(stdout.getvalue().split()), required_worker_instance_names())


if __name__ == "__main__":
    unittest.main()
