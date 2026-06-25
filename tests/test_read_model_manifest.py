from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.operation_freshness_barrier import OperationFreshnessTarget
from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresBankReadModelRepository,
    PostgresInvoiceUsageCollectionReadModelRepository,
    PostgresPendingInvoiceLifecycleReadModelRepository,
    PostgresReadModelRepository,
    PostgresSearchWorkbenchRelationReadModelRepository,
    PostgresSummaryReadModelRepository,
)
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
from fin_ops_platform.tools.read_model_slo_smoke import PAGE_FIRST_SCREEN_SCOPE_KEYS


REPO_ROOT = Path(__file__).resolve().parents[1]


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

    def test_manifest_repository_owner_uses_read_model_port_except_workbench(self) -> None:
        expected_port_owners = {
            "bank_account_balance": "BankAccountBalanceReadModelRepositoryPort",
            "bank_detail": "BankDetailReadModelRepositoryPort",
            "cost_statistics": "CostStatisticsReadModelRepositoryPort",
            "input_invoice_usage": "InputInvoiceUsageReadModelRepositoryPort",
            "invoice_lifecycle": "InvoiceLifecycleReadModelRepositoryPort",
            "no_oa_bank_batch": "NoOaBankBatchReadModelRepositoryPort",
            "oa_pending_payment": "OaPendingPaymentReadModelRepositoryPort",
            "output_invoice_collection": "OutputInvoiceCollectionReadModelRepositoryPort",
            "pending_invoice": "PendingInvoiceReadModelRepositoryPort",
            "search": "SearchReadModelRepositoryPort",
            "tax_offset": "TaxOffsetReadModelRepositoryPort",
            "turnover_ledger": "TurnoverLedgerReadModelRepositoryPort",
            "workbench_relation": "WorkbenchRelationReadModelRepositoryPort",
        }

        self.assertEqual(
            READ_MODEL_MANIFEST["workbench"].repository_owner,
            "PostgresReadModelRepository.workbench",
        )
        for key, repository_owner in expected_port_owners.items():
            with self.subTest(read_model_key=key):
                self.assertEqual(READ_MODEL_MANIFEST[key].repository_owner, repository_owner)

    def test_invoice_usage_collection_physical_sql_owner_is_split_from_shared_repository(self) -> None:
        owned_methods = {
            "list_input_invoice_usage_rows",
            "save_input_invoice_usage_rows",
            "mark_input_invoice_usage_scope",
            "prune_input_invoice_usage_scope_shards",
            "get_input_invoice_usage_row_by_row_id",
            "list_output_invoice_collection_rows",
            "get_output_invoice_collection_row_by_row_id",
            "save_output_invoice_collection_rows",
            "mark_output_invoice_collection_scope",
            "prune_output_invoice_collection_scope_shards",
            "list_oa_pending_payment_rows",
            "save_oa_pending_payment_rows",
            "mark_oa_pending_payment_scope",
            "prune_oa_pending_payment_scope_shards",
            "get_oa_pending_payment_row_by_row_id",
            "get_oa_pending_payment_row_by_oa_id",
            "get_oa_pending_payment_row_by_bank_transaction_id",
            "get_oa_pending_payment_row_by_invoice_id",
        }

        for method_name in owned_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(callable(getattr(PostgresInvoiceUsageCollectionReadModelRepository, method_name, None)))
                shared_source = inspect.getsource(getattr(PostgresReadModelRepository, method_name))
                self.assertIn("_invoice_usage_collection_repository", shared_source)
                self.assertNotIn("read_model.input_invoice_usage_rows", shared_source)
                self.assertNotIn("read_model.output_invoice_collection_rows", shared_source)
                self.assertNotIn("read_model.oa_pending_payment_rows", shared_source)

    def test_pending_invoice_lifecycle_physical_sql_owner_is_split_from_shared_repository(self) -> None:
        owned_methods = {
            "list_pending_invoice_rows",
            "list_pending_invoice_filter_options",
            "save_pending_invoice_rows",
            "mark_pending_invoice_scope",
            "pending_invoice_source_summary",
            "pending_invoice_bank_detail_source_versions",
            "pending_invoice_workbench_relation_source_versions",
            "save_invoice_lifecycle_rows",
            "mark_invoice_lifecycle_scope",
            "get_invoice_lifecycle_rows_by_subject_ids",
            "get_invoice_lifecycle_rows_by_identity_keys",
            "list_invoice_lifecycle_rows",
        }

        for method_name in owned_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(callable(getattr(PostgresPendingInvoiceLifecycleReadModelRepository, method_name, None)))
                shared_source = inspect.getsource(getattr(PostgresReadModelRepository, method_name))
                self.assertIn("_pending_invoice_lifecycle_repository", shared_source)
                self.assertNotIn("read_model.pending_invoice_rows", shared_source)
                self.assertNotIn("read_model.invoice_lifecycle_rows", shared_source)

    def test_bank_read_model_physical_sql_owner_is_split_from_shared_repository(self) -> None:
        owned_methods = {
            "bank_detail_scope_keys_for_range",
            "bank_detail_scope_summary",
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

        for method_name in owned_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(callable(getattr(PostgresBankReadModelRepository, method_name, None)))
                shared_source = inspect.getsource(getattr(PostgresReadModelRepository, method_name))
                self.assertIn("_bank_read_model_repository", shared_source)
                self.assertNotIn("read_model.bank_detail_rows", shared_source)
                self.assertNotIn("read_model.bank_detail_scopes", shared_source)
                self.assertNotIn("read_model.bank_account_balances", shared_source)

    def test_search_workbench_relation_physical_sql_owner_is_split_from_shared_repository(self) -> None:
        owned_methods = {
            "search_index",
            "save_search_index_rows",
            "save_workbench_relation_distribution",
            "mark_workbench_relation_scope_empty",
            "get_workbench_relation_rows_by_ids",
            "list_workbench_relation_rows",
            "get_workbench_relation_groups_by_ids",
            "workbench_relation_source_versions",
        }

        for method_name in owned_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(callable(getattr(PostgresSearchWorkbenchRelationReadModelRepository, method_name, None)))
                shared_source = inspect.getsource(getattr(PostgresReadModelRepository, method_name))
                self.assertIn("_search_workbench_relation_repository", shared_source)
                self.assertNotIn("read_model.search_index_rows", shared_source)
                self.assertNotIn("read_model.workbench_relation_rows", shared_source)
                self.assertNotIn("read_model.workbench_relation_groups", shared_source)
                self.assertNotIn("read_model.workbench_relation_scopes", shared_source)

    def test_summary_read_model_physical_sql_owner_is_split_from_shared_repository(self) -> None:
        owned_methods = {
            "load_cost_statistics_read_models",
            "get_cost_statistics_view",
            "save_cost_statistics_read_models",
            "load_tax_offset_read_models",
            "get_tax_offset_view",
            "save_tax_offset_read_models",
            "list_no_oa_bank_batch_rows",
            "list_turnover_ledger_view",
            "save_turnover_ledger_rows",
            "clear_turnover_ledger_rows",
        }

        for method_name in owned_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(callable(getattr(PostgresSummaryReadModelRepository, method_name, None)))
                shared_source = inspect.getsource(getattr(PostgresReadModelRepository, method_name))
                self.assertIn("_summary_read_model_repository", shared_source)
                self.assertNotIn("read_model.cost_statistics_read_models", shared_source)
                self.assertNotIn("read_model.cost_statistics_rows", shared_source)
                self.assertNotIn("read_model.tax_offset_read_models", shared_source)
                self.assertNotIn("read_model.tax_offset_items", shared_source)
                self.assertNotIn("read_model.no_oa_bank_batch_rows", shared_source)
                self.assertNotIn("read_model.turnover_ledger_rows", shared_source)

    def test_workbench_manifest_preserves_active_generation_exception(self) -> None:
        entry = READ_MODEL_MANIFEST["workbench"]
        required_active_generation_ports = {
            "get_workbench_view",
            "get_workbench_summary",
            "get_workbench_groups_page",
            "get_workbench_group_detail",
            "get_workbench_row_detail",
            "get_workbench_refresh_status",
            "get_workbench_groups_freshness_status",
            "save_workbench_read_models",
            "load_workbench_read_models",
        }

        self.assertEqual(entry.query_status_contract, "equivalent_active_generation")
        self.assertEqual(entry.projection_strategy, "active_generation_scoped_publish")
        self.assertEqual(entry.all_scope_semantics, "active_month_shard_aggregate")
        self.assertEqual(entry.force_refresh_contract, "gateway_force_refresh_active_generation_scope")
        self.assertLessEqual(required_active_generation_ports, set(entry.repository_port_contract))

    def test_bank_detail_and_balance_manifest_keep_separate_contracts(self) -> None:
        bank_detail = READ_MODEL_MANIFEST["bank_detail"]
        balance = READ_MODEL_MANIFEST["bank_account_balance"]
        required_bank_detail_ports = {
            "bank_detail_scope_keys_for_range",
            "bank_detail_scope_summary",
            "list_bank_detail_transactions",
            "list_bank_detail_accounts",
            "get_bank_detail_tagged_rows_by_transaction_ids",
            "list_bank_detail_tagged_rows_by_month",
            "save_bank_detail_rows",
            "mark_bank_detail_scope",
        }
        required_balance_ports = {
            "bank_account_balance_scope_summary",
            "list_bank_account_balances",
            "save_bank_account_balances",
        }

        self.assertEqual(bank_detail.scope_type, "bank_detail")
        self.assertEqual(balance.scope_type, "bank_account_balance")
        self.assertEqual(bank_detail.query_status_contract, "self_managed_freshness")
        self.assertEqual(balance.query_status_contract, "self_managed_freshness")
        self.assertEqual(bank_detail.projection_strategy, "partitioned_scoped_incremental")
        self.assertEqual(balance.projection_strategy, "partitioned_scoped_incremental")
        self.assertEqual(bank_detail.all_scope_semantics, "fan_out_command")
        self.assertEqual(balance.all_scope_semantics, "fan_out_command")
        self.assertEqual(bank_detail.force_refresh_contract, "gateway_force_refresh")
        self.assertEqual(balance.force_refresh_contract, "gateway_force_refresh")
        self.assertEqual(bank_detail.query_owner, "BankDetailsApplicationService")
        self.assertEqual(balance.query_owner, "BankDetailsApplicationService")
        self.assertEqual(bank_detail.permission_owner, "bank_details_api_session")
        self.assertEqual(balance.permission_owner, "bank_details_api_session")
        self.assertEqual(bank_detail.test_owner, "tests/test_bank_details_sql_runtime.py")
        self.assertEqual(balance.test_owner, "tests/test_bank_account_balance_read_model.py")
        self.assertLessEqual(required_bank_detail_ports, set(bank_detail.repository_port_contract))
        self.assertEqual(required_balance_ports, set(balance.repository_port_contract))
        self.assertFalse(set(bank_detail.repository_port_contract).intersection(balance.repository_port_contract))

    def test_pending_invoice_and_oa_payment_manifest_preserve_page_scope_contracts(self) -> None:
        pending_invoice = READ_MODEL_MANIFEST["pending_invoice"]
        oa_payment = READ_MODEL_MANIFEST["oa_pending_payment"]
        required_pending_ports = {
            "list_pending_invoice_rows",
            "list_pending_invoice_filter_options",
            "save_pending_invoice_rows",
            "mark_pending_invoice_scope",
            "pending_invoice_source_summary",
            "pending_invoice_bank_detail_source_versions",
            "pending_invoice_workbench_relation_source_versions",
        }
        required_oa_ports = {
            "list_oa_pending_payment_rows",
            "save_oa_pending_payment_rows",
            "mark_oa_pending_payment_scope",
            "prune_oa_pending_payment_scope_shards",
            "get_oa_pending_payment_row_by_row_id",
            "get_oa_pending_payment_row_by_oa_id",
            "get_oa_pending_payment_row_by_bank_transaction_id",
            "get_oa_pending_payment_row_by_invoice_id",
        }

        self.assertEqual(pending_invoice.scope_type, "pending_invoice")
        self.assertEqual(oa_payment.scope_type, "oa_pending_payment")
        self.assertEqual(pending_invoice.query_status_contract, "self_managed_freshness")
        self.assertEqual(oa_payment.query_status_contract, "self_managed_freshness")
        self.assertEqual(pending_invoice.all_scope_semantics, "forbidden_bare_all")
        self.assertEqual(oa_payment.all_scope_semantics, "fan_out_command")
        self.assertEqual(pending_invoice.force_refresh_contract, "gateway_force_refresh_with_page_first_screen_scope")
        self.assertEqual(oa_payment.force_refresh_contract, "gateway_force_refresh")
        self.assertEqual(pending_invoice.query_owner, "PendingInvoiceReadModelService")
        self.assertEqual(oa_payment.query_owner, "OaPendingPaymentReadModelService")
        self.assertEqual(pending_invoice.permission_owner, "pending_invoices_api_session")
        self.assertEqual(oa_payment.permission_owner, "oa_pending_payment_api_session")
        self.assertLessEqual(required_pending_ports, set(pending_invoice.repository_port_contract))
        self.assertLessEqual(required_oa_ports, set(oa_payment.repository_port_contract))
        self.assertFalse(set(pending_invoice.repository_port_contract).intersection(oa_payment.repository_port_contract))

    def test_invoice_lifecycle_and_usage_manifest_preserve_scoped_contracts(self) -> None:
        lifecycle = READ_MODEL_MANIFEST["invoice_lifecycle"]
        input_usage = READ_MODEL_MANIFEST["input_invoice_usage"]
        output_collection = READ_MODEL_MANIFEST["output_invoice_collection"]
        required_lifecycle_ports = {
            "save_invoice_lifecycle_rows",
            "mark_invoice_lifecycle_scope",
            "get_invoice_lifecycle_rows_by_subject_ids",
            "get_invoice_lifecycle_rows_by_identity_keys",
            "list_invoice_lifecycle_rows",
        }
        required_input_ports = {
            "list_input_invoice_usage_rows",
            "save_input_invoice_usage_rows",
            "mark_input_invoice_usage_scope",
            "prune_input_invoice_usage_scope_shards",
            "get_input_invoice_usage_row_by_row_id",
        }
        required_output_ports = {
            "list_output_invoice_collection_rows",
            "get_output_invoice_collection_row_by_row_id",
            "save_output_invoice_collection_rows",
            "mark_output_invoice_collection_scope",
            "prune_output_invoice_collection_scope_shards",
        }

        for entry in (lifecycle, input_usage, output_collection):
            with self.subTest(read_model_key=entry.key):
                self.assertEqual(entry.query_status_contract, "self_managed_freshness")
                self.assertEqual(entry.projection_strategy, "scoped_incremental")
                self.assertEqual(entry.all_scope_semantics, "fan_out_command")
                self.assertEqual(entry.force_refresh_contract, "gateway_force_refresh")
                self.assertEqual(entry.operation_barrier_contract, "app_status_registry_target")
                self.assertEqual(entry.refresh_event_type, f"{entry.scope_type}.read_model.refresh")

        self.assertEqual(lifecycle.scope_type, "invoice_lifecycle")
        self.assertEqual(input_usage.scope_type, "input_invoice_usage")
        self.assertEqual(output_collection.scope_type, "output_invoice_collection")
        self.assertEqual(lifecycle.primary_worker_instance, "invoice-lifecycle")
        self.assertEqual(input_usage.primary_worker_instance, "invoice-usage-collection")
        self.assertEqual(output_collection.primary_worker_instance, "invoice-usage-collection")
        self.assertEqual(lifecycle.auxiliary_refresh_worker_instances, ("invoice-lifecycle-secondary",))
        self.assertEqual(input_usage.auxiliary_refresh_worker_instances, ())
        self.assertEqual(output_collection.auxiliary_refresh_worker_instances, ())
        self.assertEqual(lifecycle.query_owner, "InvoiceLifecycleReadFacade")
        self.assertEqual(input_usage.query_owner, "InputInvoiceUsageReadModelService")
        self.assertEqual(output_collection.query_owner, "OutputInvoiceCollectionService")
        self.assertEqual(lifecycle.permission_owner, "invoice_lifecycle_page_api_session")
        self.assertEqual(input_usage.permission_owner, "input_invoice_usage_api_session")
        self.assertEqual(output_collection.permission_owner, "output_invoice_collection_api_session")
        self.assertLessEqual(required_lifecycle_ports, set(lifecycle.repository_port_contract))
        self.assertLessEqual(required_input_ports, set(input_usage.repository_port_contract))
        self.assertLessEqual(required_output_ports, set(output_collection.repository_port_contract))
        self.assertFalse(set(lifecycle.repository_port_contract).intersection(input_usage.repository_port_contract))
        self.assertFalse(set(lifecycle.repository_port_contract).intersection(output_collection.repository_port_contract))
        self.assertFalse(set(input_usage.repository_port_contract).intersection(output_collection.repository_port_contract))

    def test_cost_tax_and_turnover_manifest_preserve_summary_contracts(self) -> None:
        cost_statistics = READ_MODEL_MANIFEST["cost_statistics"]
        tax_offset = READ_MODEL_MANIFEST["tax_offset"]
        turnover_ledger = READ_MODEL_MANIFEST["turnover_ledger"]
        required_cost_ports = {
            "load_cost_statistics_read_models",
            "get_cost_statistics_view",
            "save_cost_statistics_read_models",
        }
        required_tax_ports = {
            "load_tax_offset_read_models",
            "get_tax_offset_view",
            "save_tax_offset_read_models",
        }
        required_turnover_ports = {
            "list_turnover_ledger_view",
            "save_turnover_ledger_rows",
            "clear_turnover_ledger_rows",
        }

        for entry in (cost_statistics, tax_offset, turnover_ledger):
            with self.subTest(read_model_key=entry.key):
                self.assertEqual(entry.query_status_contract, "read_model_query_gateway")
                self.assertEqual(entry.force_refresh_contract, "gateway_force_refresh")
                self.assertEqual(entry.operation_barrier_contract, "app_status_registry_target")
                self.assertEqual(entry.refresh_event_type, f"{entry.scope_type}.read_model.refresh")

        self.assertEqual(cost_statistics.scope_type, "cost_statistics")
        self.assertEqual(tax_offset.scope_type, "tax_offset")
        self.assertEqual(turnover_ledger.scope_type, "turnover_ledger")
        self.assertEqual(cost_statistics.projection_strategy, "partitioned_scoped_parent_rollup")
        self.assertEqual(tax_offset.projection_strategy, "partitioned_scoped_incremental")
        self.assertEqual(turnover_ledger.projection_strategy, "partitioned_scoped_incremental")
        self.assertEqual(cost_statistics.all_scope_semantics, "queryable_parent_aggregate")
        self.assertEqual(tax_offset.all_scope_semantics, "fan_out_command")
        self.assertEqual(turnover_ledger.all_scope_semantics, "fan_out_command")
        self.assertEqual(cost_statistics.primary_worker_instance, "cost-statistics")
        self.assertEqual(tax_offset.primary_worker_instance, "tax-offset")
        self.assertEqual(turnover_ledger.primary_worker_instance, "turnover-ledger")
        self.assertEqual(cost_statistics.auxiliary_refresh_worker_instances, ("cost-tax",))
        self.assertEqual(tax_offset.auxiliary_refresh_worker_instances, ("cost-tax",))
        self.assertEqual(turnover_ledger.auxiliary_refresh_worker_instances, ())
        self.assertEqual(cost_statistics.query_owner, "CostStatisticsQueryService")
        self.assertEqual(tax_offset.query_owner, "TaxOffsetQueryService")
        self.assertEqual(turnover_ledger.query_owner, "TurnoverLedgerQueryService")
        self.assertEqual(cost_statistics.permission_owner, "cost_statistics_api_session")
        self.assertEqual(tax_offset.permission_owner, "tax_offset_api_session")
        self.assertEqual(turnover_ledger.permission_owner, "turnover_ledger_api_session")
        self.assertEqual(required_cost_ports, set(cost_statistics.repository_port_contract))
        self.assertEqual(required_tax_ports, set(tax_offset.repository_port_contract))
        self.assertEqual(required_turnover_ports, set(turnover_ledger.repository_port_contract))
        self.assertFalse(set(cost_statistics.repository_port_contract).intersection(tax_offset.repository_port_contract))
        self.assertFalse(set(cost_statistics.repository_port_contract).intersection(turnover_ledger.repository_port_contract))
        self.assertFalse(set(tax_offset.repository_port_contract).intersection(turnover_ledger.repository_port_contract))

    def test_search_and_no_oa_bank_batch_manifest_preserve_read_side_contracts(self) -> None:
        search = READ_MODEL_MANIFEST["search"]
        no_oa_bank_batch = READ_MODEL_MANIFEST["no_oa_bank_batch"]
        required_search_ports = {
            "search_index",
            "save_search_index_rows",
        }
        required_no_oa_ports = {
            "list_no_oa_bank_batch_rows",
        }

        for entry in (search, no_oa_bank_batch):
            with self.subTest(read_model_key=entry.key):
                self.assertEqual(entry.query_status_contract, "self_managed_freshness")
                self.assertEqual(entry.all_scope_semantics, "fan_out_command")
                self.assertEqual(entry.force_refresh_contract, "gateway_force_refresh")
                self.assertEqual(entry.operation_barrier_contract, "app_status_registry_target")
                self.assertEqual(entry.refresh_event_type, f"{entry.scope_type}.read_model.refresh")

        self.assertEqual(search.scope_type, "search")
        self.assertEqual(no_oa_bank_batch.scope_type, "no_oa_bank_batch")
        self.assertEqual(search.projection_strategy, "partitioned_scoped_index")
        self.assertEqual(no_oa_bank_batch.projection_strategy, "scoped_incremental")
        self.assertEqual(search.primary_worker_instance, "search")
        self.assertEqual(no_oa_bank_batch.primary_worker_instance, "no-oa-bank-batch")
        self.assertEqual(search.auxiliary_refresh_worker_instances, ("search-pending", "search-secondary", "search-tertiary"))
        self.assertEqual(no_oa_bank_batch.auxiliary_refresh_worker_instances, ())
        self.assertEqual(search.query_owner, "Search read API")
        self.assertEqual(no_oa_bank_batch.query_owner, "NoOaBankBatchApplicationService")
        self.assertEqual(search.permission_owner, "search_api_session")
        self.assertEqual(no_oa_bank_batch.permission_owner, "no_oa_bank_batch_api_session")
        self.assertEqual(search.test_owner, "tests/test_search_pending_sql_runtime.py")
        self.assertEqual(no_oa_bank_batch.test_owner, "tests/test_no_oa_bank_batch_application_service.py")
        self.assertEqual(search.repository_owner, "SearchReadModelRepositoryPort")
        self.assertEqual(no_oa_bank_batch.repository_owner, "NoOaBankBatchReadModelRepositoryPort")
        self.assertEqual(required_search_ports, set(search.repository_port_contract))
        self.assertEqual(required_no_oa_ports, set(no_oa_bank_batch.repository_port_contract))
        self.assertFalse(set(search.repository_port_contract).intersection(no_oa_bank_batch.repository_port_contract))


if __name__ == "__main__":
    unittest.main()
