from __future__ import annotations

import unittest

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.read_model_manifest import (
    READ_MODEL_MANIFEST,
    read_model_manifest_by_refresh_event_type,
    read_model_manifest_by_scope_type,
)
from fin_ops_platform.services.read_model_scope_policy import DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY
from fin_ops_platform.services.runtime_worker_registry import (
    rabbitmq_dispatch_event_types,
    read_model_event_types,
    registration_by_instance_name,
)


class ReadModelManifestTests(unittest.TestCase):
    def test_manifest_covers_every_app_status_read_model(self) -> None:
        self.assertEqual(set(READ_MODEL_MANIFEST), set(APP_STATUS_READ_MODEL_REGISTRY))

    def test_manifest_matches_app_status_registry(self) -> None:
        for key, definition in APP_STATUS_READ_MODEL_REGISTRY.items():
            with self.subTest(read_model_key=key):
                entry = READ_MODEL_MANIFEST[key]
                self.assertEqual(entry.key, definition.key)
                self.assertEqual(entry.scope_type, definition.scope_type)
                self.assertEqual(entry.refresh_event_type, definition.refresh_event_type)
                self.assertEqual(entry.primary_worker_instance, definition.worker_instance)

    def test_manifest_matches_worker_event_contracts(self) -> None:
        registrations = registration_by_instance_name()
        read_model_events = read_model_event_types()
        dispatch_events = set(rabbitmq_dispatch_event_types())

        for entry in READ_MODEL_MANIFEST.values():
            with self.subTest(read_model_key=entry.key):
                self.assertIn(entry.primary_worker_instance, registrations)
                primary = registrations[entry.primary_worker_instance]
                self.assertTrue(primary.required)
                self.assertIn(entry.refresh_event_type, primary.event_types)
                self.assertIn(entry.refresh_event_type, dispatch_events)
                self.assertEqual(read_model_events[entry.refresh_event_type], (entry.key, entry.scope_type))

                for worker_instance in entry.auxiliary_refresh_worker_instances:
                    self.assertIn(worker_instance, registrations)
                    auxiliary = registrations[worker_instance]
                    self.assertTrue(auxiliary.required)
                    self.assertIn(entry.refresh_event_type, auxiliary.event_types)

    def test_manifest_scope_types_are_policy_registered(self) -> None:
        registered_scope_types = set(DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY.registered_scope_types())

        self.assertEqual(
            {entry.scope_type for entry in READ_MODEL_MANIFEST.values()},
            registered_scope_types,
        )

    def test_manifest_indexes_are_unique(self) -> None:
        self.assertEqual(len(read_model_manifest_by_scope_type()), len(READ_MODEL_MANIFEST))
        self.assertEqual(len(read_model_manifest_by_refresh_event_type()), len(READ_MODEL_MANIFEST))

    def test_manifest_entries_have_contract_owners(self) -> None:
        allowed_query_contracts = {
            "read_model_query_gateway",
            "self_managed_freshness",
            "equivalent_active_generation",
        }
        allowed_all_scope_semantics = {
            "active_month_shard_aggregate",
            "fan_out_command",
            "forbidden_bare_all",
            "queryable_parent_aggregate",
        }

        for entry in READ_MODEL_MANIFEST.values():
            with self.subTest(read_model_key=entry.key):
                self.assertIn(entry.query_status_contract, allowed_query_contracts)
                self.assertIn(entry.all_scope_semantics, allowed_all_scope_semantics)
                self.assertTrue(entry.projection_strategy)
                self.assertTrue(entry.query_owner)
                self.assertTrue(entry.repository_owner)
                self.assertTrue(entry.permission_owner)
                self.assertTrue(entry.test_owner.startswith("tests/"))


if __name__ == "__main__":
    unittest.main()
