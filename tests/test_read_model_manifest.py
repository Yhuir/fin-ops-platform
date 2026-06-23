from __future__ import annotations

import unittest

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.operation_freshness_barrier import OperationFreshnessTarget
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
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


if __name__ == "__main__":
    unittest.main()
