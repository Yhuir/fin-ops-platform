from __future__ import annotations

import inspect
from pathlib import Path
import re
import unittest

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.operation_freshness_barrier import OperationFreshnessTarget
from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresReadModelRepository,
    PostgresWorkbenchRelationReadModelRepository,
)
from fin_ops_platform.services.read_model_manifest import (
    READ_MODEL_MANIFEST,
    is_command_only_read_model_scope,
    read_model_manifest_by_refresh_event_type,
    read_model_manifest_by_scope_type,
)
from fin_ops_platform.services.read_model_scope_policy import DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY
from fin_ops_platform.services.runtime_worker_registry import (
    rabbitmq_dispatch_event_types,
    read_model_event_types,
    registration_by_instance_name,
)
from fin_ops_platform.tools.read_model_slo_smoke import PAGE_FIRST_SCREEN_SCOPE_KEYS


REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_MATRIX_PATH = (
    REPO_ROOT / ".planning" / "phases" / "27-read-model-fan-out" / "27-COVERAGE-MATRIX.md"
)


def _phase_27_read_model_coverage() -> dict[str, tuple[str, str]]:
    coverage = COVERAGE_MATRIX_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"^## Read model coverage\s*$\n(?P<body>.*?)^## Mutating frontend API function coverage\s*$",
        coverage,
        re.MULTILINE | re.DOTALL,
    )
    if section_match is None:
        raise AssertionError("Could not find Phase 27 read model coverage section")
    rows = {
        key: (scope_contract, query_owner)
        for key, scope_contract, query_owner in re.findall(
            r"^\| `([^`]+)` \| (.*?) \| `([^`]+)` \|",
            section_match.group("body"),
            re.MULTILINE,
        )
    }
    if not rows:
        raise AssertionError("Could not find Phase 27 read model coverage rows")
    return rows


class ReadModelManifestTests(unittest.TestCase):
    def test_declared_read_model_dependency_graph_is_complete_and_acyclic(self) -> None:
        graph = {
            key: tuple(entry.read_dependencies)
            for key, entry in READ_MODEL_MANIFEST.items()
        }
        for key, dependencies in graph.items():
            self.assertNotIn(key, dependencies)
            self.assertLessEqual(set(dependencies), set(graph))

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visited:
                return
            self.assertNotIn(key, visiting, f"read model dependency cycle at {key}")
            visiting.add(key)
            for dependency in graph[key]:
                visit(dependency)
            visiting.remove(key)
            visited.add(key)

        for key in graph:
            visit(key)

        self.assertEqual(
            graph,
            {
                "workbench": (),
                "workbench_relation": (),
            },
        )

    def test_phase_27_coverage_matches_manifest_keys_scopes_and_query_owners(self) -> None:
        coverage = _phase_27_read_model_coverage()

        self.assertLessEqual(set(READ_MODEL_MANIFEST), set(coverage))
        for key, entry in READ_MODEL_MANIFEST.items():
            with self.subTest(read_model_key=key):
                scope_contract, query_owner = coverage[key]
                self.assertIn(f"`{entry.scope_type}`", scope_contract)
                self.assertEqual(query_owner, entry.query_owner)

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

    def test_manifest_and_runtime_registry_have_exact_worker_instance_sets(self) -> None:
        registrations_by_read_model: dict[str, set[str]] = {}
        registrations = registration_by_instance_name()

        for registration in registrations.values():
            if registration.read_model_key is None:
                continue
            self.assertIsNotNone(registration.read_model_scope_type)
            registrations_by_read_model.setdefault(registration.read_model_key, set()).add(
                registration.instance_name
            )

        self.assertEqual(set(registrations_by_read_model), set(READ_MODEL_MANIFEST))
        for entry in READ_MODEL_MANIFEST.values():
            with self.subTest(read_model_key=entry.key):
                expected_instances = {
                    entry.primary_worker_instance,
                    *entry.auxiliary_refresh_worker_instances,
                }
                self.assertEqual(
                    registrations_by_read_model[entry.key],
                    expected_instances,
                )
                for worker_instance in expected_instances:
                    registration = registrations[worker_instance]
                    self.assertEqual(registration.read_model_key, entry.key)
                    self.assertEqual(registration.read_model_scope_type, entry.scope_type)
                    self.assertIn(entry.refresh_event_type, registration.event_types)

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
            "queryable_all_scope",
            "queryable_parent_aggregate",
        }
        allowed_force_refresh_contracts = {
            "gateway_force_refresh",
            "gateway_force_refresh_active_generation_scope",
            "gateway_force_refresh_with_page_first_screen_scope",
        }
        allowed_operation_barrier_contracts = {"app_status_registry_target"}

        for entry in READ_MODEL_MANIFEST.values():
            with self.subTest(read_model_key=entry.key):
                self.assertIn(entry.query_status_contract, allowed_query_contracts)
                self.assertIn(entry.all_scope_semantics, allowed_all_scope_semantics)
                self.assertIn(entry.force_refresh_contract, allowed_force_refresh_contracts)
                self.assertIn(entry.operation_barrier_contract, allowed_operation_barrier_contracts)
                self.assertTrue(entry.repository_port_contract)
                self.assertTrue(entry.projection_strategy)
                self.assertTrue(entry.query_owner)
                self.assertTrue(entry.repository_owner)
                self.assertTrue(entry.permission_owner)
                self.assertTrue(entry.test_owner.startswith("tests/"))

    def test_manifest_entries_record_partition_rebuild_and_freshness_contracts(self) -> None:
        required_contract_fields = (
            "partition_key_contract",
            "scoped_incremental_target",
            "full_rebuild_fallback",
            "freshness_proof_contract",
        )

        for entry in READ_MODEL_MANIFEST.values():
            with self.subTest(read_model_key=entry.key):
                for field_name in required_contract_fields:
                    value = getattr(entry, field_name)
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.strip(), f"{entry.key} missing {field_name}")
                    self.assertNotIn("TODO", value)

                if entry.key == "bank_account_balance":
                    self.assertIn("all scope only", entry.partition_key_contract)
                    continue

                if entry.all_scope_semantics == "fan_out_command":
                    self.assertIn("fan-out", entry.partition_key_contract)
                    self.assertIn("gateway force refresh", entry.full_rebuild_fallback)

    def test_read_model_module_readme_records_manifest_contracts(self) -> None:
        readme = (REPO_ROOT / "docs/modules/read-models/README.md").read_text(encoding="utf-8")

        for entry in READ_MODEL_MANIFEST.values():
            with self.subTest(read_model_key=entry.key):
                self.assertIn(f"| `{entry.key}` | `{entry.scope_type}` |", readme)
                self.assertIn(entry.partition_key_contract, readme)
                self.assertIn(entry.scoped_incremental_target, readme)
                self.assertIn(entry.full_rebuild_fallback, readme)
                self.assertIn(entry.freshness_proof_contract, readme)
                self.assertIn(f"`{entry.force_refresh_contract}` / `{entry.operation_barrier_contract}`", readme)

    def test_manifest_declares_operation_barrier_targets(self) -> None:
        for entry in READ_MODEL_MANIFEST.values():
            with self.subTest(read_model_key=entry.key):
                target = OperationFreshnessTarget.from_payload({"read_model_key": entry.key})

                self.assertEqual(target.read_model_key, entry.key)
                self.assertEqual(target.scope_type, entry.scope_type)
                self.assertEqual(target.scope_key, "all")
                self.assertEqual(entry.operation_barrier_contract, "app_status_registry_target")

    def test_manifest_declares_force_refresh_smoke_contract(self) -> None:
        self.assertLessEqual(set(PAGE_FIRST_SCREEN_SCOPE_KEYS), set(READ_MODEL_MANIFEST))

        for entry in READ_MODEL_MANIFEST.values():
            with self.subTest(read_model_key=entry.key):
                if entry.key == "workbench":
                    expected_contract = "gateway_force_refresh_active_generation_scope"
                elif entry.key in PAGE_FIRST_SCREEN_SCOPE_KEYS:
                    expected_contract = "gateway_force_refresh_with_page_first_screen_scope"
                else:
                    expected_contract = "gateway_force_refresh"

                self.assertEqual(entry.force_refresh_contract, expected_contract)
                self.assertEqual(entry.refresh_event_type, f"{entry.scope_type}.read_model.refresh")

    def test_manifest_repository_port_contract_methods_exist(self) -> None:
        for entry in READ_MODEL_MANIFEST.values():
            with self.subTest(read_model_key=entry.key):
                for method_name in entry.repository_port_contract:
                    self.assertTrue(
                        callable(getattr(PostgresReadModelRepository, method_name, None)),
                        f"{entry.key} repository port method is missing: {method_name}",
                    )

    def test_manifest_repository_port_contract_methods_have_single_owner(self) -> None:
        owners_by_method: dict[str, str] = {}

        for entry in READ_MODEL_MANIFEST.values():
            for method_name in entry.repository_port_contract:
                previous_owner = owners_by_method.setdefault(method_name, entry.key)
                self.assertEqual(
                    previous_owner,
                    entry.key,
                    f"{method_name} is declared by both {previous_owner} and {entry.key}",
                )

    def test_manifest_repository_owner_uses_retained_read_model_ports(self) -> None:
        expected_port_owners = {
            "workbench": "PostgresReadModelRepository.workbench",
            "workbench_relation": "WorkbenchRelationReadModelRepositoryPort",
        }

        self.assertEqual(set(READ_MODEL_MANIFEST), set(expected_port_owners))
        for key, repository_owner in expected_port_owners.items():
            with self.subTest(read_model_key=key):
                self.assertEqual(READ_MODEL_MANIFEST[key].repository_owner, repository_owner)

    def test_retired_invoice_page_repository_methods_are_absent(self) -> None:
        retired_methods = {
            "list_pending_invoice_rows",
            "list_pending_invoice_lifecycle_source_rows",
            "list_pending_invoice_filter_options",
            "save_pending_invoice_rows",
            "mark_pending_invoice_scope",
            "pending_invoice_source_summary",
            "pending_invoice_bank_source_versions",
            "pending_invoice_workbench_relation_source_versions",
            "save_invoice_lifecycle_rows",
            "mark_invoice_lifecycle_scope",
            "get_invoice_lifecycle_rows_by_subject_ids",
            "get_invoice_lifecycle_rows_by_identity_keys",
            "list_invoice_lifecycle_rows",
            "invoice_lifecycle_scope_summary",
            "list_input_invoice_usage_rows",
            "list_input_invoice_usage_filter_options",
            "input_invoice_usage_scope_source_versions",
            "input_invoice_usage_relation_source_versions",
            "save_input_invoice_usage_rows",
            "mark_input_invoice_usage_scope",
            "prune_input_invoice_usage_scope_shards",
            "get_input_invoice_usage_row_by_row_id",
            "list_input_invoice_usage_rows_by_invoice_ids",
            "list_output_invoice_collection_rows",
            "output_invoice_collection_scope_source_versions",
            "output_invoice_collection_relation_source_versions",
            "get_output_invoice_collection_row_by_row_id",
            "save_output_invoice_collection_rows",
            "mark_output_invoice_collection_scope",
            "prune_output_invoice_collection_scope_shards",
            "get_batch_accounting_relation_rows_by_ids",
            "list_batch_accounting_relation_groups_by_year",
        }

        for method_name in retired_methods:
            with self.subTest(method_name=method_name):
                self.assertFalse(hasattr(PostgresReadModelRepository, method_name))

    def test_retired_bank_read_model_repository_methods_are_absent(self) -> None:
        retired_methods = {
            "bank_detail_scope_keys_for_range",
            "bank_detail_scope_summary",
            "bank_detail_category_source_signatures",
            "bank_account_balance_scope_summary",
            "list_bank_detail_transactions",
            "list_bank_detail_accounts",
            "get_bank_detail_tagged_rows_by_transaction_ids",
            "list_bank_detail_tagged_rows_by_month",
            "list_bank_account_balances",
            "save_bank_account_balances",
            "save_bank_detail_rows",
            "mark_bank_detail_scope",
        }

        for method_name in retired_methods:
            with self.subTest(method_name=method_name):
                self.assertFalse(hasattr(PostgresReadModelRepository, method_name))

    def test_workbench_relation_physical_sql_owner_is_split_from_shared_repository(self) -> None:
        owned_methods = {
            "save_workbench_relation_distribution",
            "save_workbench_relation_distribution_rows",
            "mark_workbench_relation_scope_empty",
            "get_workbench_relation_rows_by_ids",
            "list_workbench_relation_rows",
            "get_workbench_relation_groups_by_ids",
            "workbench_relation_source_versions",
        }

        for method_name in owned_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(callable(getattr(PostgresWorkbenchRelationReadModelRepository, method_name, None)))
                shared_source = inspect.getsource(getattr(PostgresReadModelRepository, method_name))
                self.assertIn("_workbench_relation_repository", shared_source)
                self.assertNotIn("read_model.search_index_rows", shared_source)
                self.assertNotIn("read_model.workbench_relation_rows", shared_source)
                self.assertNotIn("read_model.workbench_relation_groups", shared_source)
                self.assertNotIn("read_model.workbench_relation_scopes", shared_source)

    def test_workbench_page_and_relation_manifests_remain(self) -> None:
        workbench = READ_MODEL_MANIFEST["workbench"]
        relation = READ_MODEL_MANIFEST["workbench_relation"]
        self.assertEqual(workbench.projection_strategy, "active_generation_scoped_publish")
        self.assertEqual(workbench.primary_worker_instance, "workbench")
        self.assertEqual(relation.projection_strategy, "scoped_incremental_distribution")
        self.assertEqual(relation.primary_worker_instance, "workbench-relation")

    def test_bank_detail_and_balance_page_manifests_are_retired(self) -> None:
        self.assertNotIn("bank_detail", READ_MODEL_MANIFEST)
        self.assertNotIn("bank_account_balance", READ_MODEL_MANIFEST)

    def test_manifest_distinguishes_fan_out_commands_from_queryable_all_scopes(self) -> None:
        self.assertTrue(is_command_only_read_model_scope("workbench_relation", "all"))
        self.assertFalse(is_command_only_read_model_scope("workbench", "all"))
        self.assertFalse(is_command_only_read_model_scope("search", "2026-06"))
        self.assertFalse(is_command_only_read_model_scope("search", "all"))
        self.assertFalse(is_command_only_read_model_scope("no_oa_bank_batch", "all"))
        self.assertFalse(is_command_only_read_model_scope("pending_invoice", "all"))

    def test_pending_invoice_and_oa_payment_page_manifests_are_retired(self) -> None:
        self.assertNotIn("pending_invoice", READ_MODEL_MANIFEST)
        self.assertNotIn("oa_pending_payment", READ_MODEL_MANIFEST)

    def test_invoice_lifecycle_and_usage_page_manifests_are_retired(self) -> None:
        for key in (
            "invoice_lifecycle",
            "input_invoice_usage",
            "output_invoice_collection",
        ):
            self.assertNotIn(key, READ_MODEL_MANIFEST)

    def test_cost_and_tax_are_direct_canonical_reads(self) -> None:
        self.assertNotIn("cost_statistics", READ_MODEL_MANIFEST)
        self.assertNotIn("tax_offset", READ_MODEL_MANIFEST)

    def test_search_and_no_oa_read_models_are_retired(self) -> None:
        self.assertNotIn("search", READ_MODEL_MANIFEST)
        self.assertNotIn("no_oa_bank_batch", READ_MODEL_MANIFEST)
        for method_name in (
            "search_index",
            "search_index_scope_summary",
            "save_search_index_rows",
            "list_no_oa_bank_batch_rows",
            "no_oa_bank_batch_source_versions_summary",
        ):
            self.assertFalse(hasattr(PostgresReadModelRepository, method_name))


if __name__ == "__main__":
    unittest.main()
