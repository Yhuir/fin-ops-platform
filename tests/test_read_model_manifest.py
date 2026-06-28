from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresBankReadModelRepository,
    PostgresReadModelRepository,
    PostgresSummaryReadModelRepository,
)
from fin_ops_platform.services.read_model_manifest import (
    READ_MODEL_MANIFEST,
)
from fin_ops_platform.services.runtime_worker_registry import (
    rabbitmq_dispatch_event_types,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReadModelManifestTests(unittest.TestCase):
    def test_manifest_and_app_status_read_model_registry_are_empty(self) -> None:
        self.assertEqual(READ_MODEL_MANIFEST, {})
        self.assertEqual(APP_STATUS_READ_MODEL_REGISTRY, {})

    def test_read_model_module_readme_records_empty_manifest(self) -> None:
        readme = (REPO_ROOT / "docs/modules/read-models/README.md").read_text(encoding="utf-8")

        self.assertIn("当前为空", readme)
        self.assertIn("| 无 | 无 | 无 | 无 | 无 | 无 | 无 |", readme)

    def test_workbench_read_model_manifest_is_removed(self) -> None:
        self.assertNotIn("workbench", READ_MODEL_MANIFEST)
        self.assertNotIn("workbench", APP_STATUS_READ_MODEL_REGISTRY)

    def test_invoice_usage_collection_read_models_are_removed(self) -> None:
        removed_keys = {"input_invoice_usage", "output_invoice_collection", "oa_pending_payment"}
        removed_events = {f"{key}.read_model.refresh" for key in removed_keys}

        self.assertFalse(removed_keys.intersection(READ_MODEL_MANIFEST))
        self.assertFalse(removed_keys.intersection(APP_STATUS_READ_MODEL_REGISTRY))
        self.assertFalse(removed_events.intersection(rabbitmq_dispatch_event_types()))

        for method_name in (
            "list_input_invoice_usage_rows",
            "save_input_invoice_usage_rows",
            "mark_input_invoice_usage_scope",
            "list_output_invoice_collection_rows",
            "save_output_invoice_collection_rows",
            "mark_output_invoice_collection_scope",
            "list_oa_pending_payment_rows",
            "save_oa_pending_payment_rows",
            "mark_oa_pending_payment_scope",
        ):
            with self.subTest(method_name=method_name):
                self.assertFalse(hasattr(PostgresReadModelRepository, method_name))

    def test_invoice_lifecycle_read_model_methods_are_removed(self) -> None:
        removed_methods = {
            "save_invoice_lifecycle_rows",
            "mark_invoice_lifecycle_scope",
            "get_invoice_lifecycle_rows_by_subject_ids",
            "get_invoice_lifecycle_rows_by_identity_keys",
            "list_invoice_lifecycle_rows",
            "invoice_lifecycle_scope_summary",
        }

        for method_name in removed_methods:
            with self.subTest(method_name=method_name):
                self.assertFalse(callable(getattr(PostgresReadModelRepository, method_name, None)))

    def test_bank_detail_read_model_repository_methods_are_removed(self) -> None:
        removed_methods = {
            "bank_detail_scope_keys_for_range",
            "bank_detail_scope_summary",
            "list_bank_detail_transactions",
            "list_bank_detail_accounts",
            "get_bank_detail_tagged_rows_by_transaction_ids",
            "list_bank_detail_tagged_rows_by_month",
            "save_bank_detail_rows",
            "mark_bank_detail_scope",
        }

        for method_name in removed_methods:
            with self.subTest(method_name=method_name):
                self.assertFalse(callable(getattr(PostgresReadModelRepository, method_name, None)))
                self.assertFalse(callable(getattr(PostgresBankReadModelRepository, method_name, None)))

    def test_workbench_relation_read_model_methods_are_removed(self) -> None:
        removed_methods = {
            "save_workbench_relation_distribution",
            "mark_workbench_relation_scope_empty",
            "get_workbench_relation_rows_by_ids",
            "list_workbench_relation_rows",
            "get_workbench_relation_groups_by_ids",
            "workbench_relation_source_versions",
            "workbench_relation_scope_summary",
        }

        for method_name in removed_methods:
            with self.subTest(method_name=method_name):
                self.assertFalse(callable(getattr(PostgresReadModelRepository, method_name, None)))

    def test_turnover_summary_read_model_methods_are_removed(self) -> None:
        removed_methods = {
            "list_turnover_ledger_view",
            "save_turnover_ledger_rows",
            "clear_turnover_ledger_rows",
        }

        for method_name in removed_methods:
            with self.subTest(method_name=method_name):
                self.assertFalse(callable(getattr(PostgresSummaryReadModelRepository, method_name, None)))
                self.assertFalse(callable(getattr(PostgresReadModelRepository, method_name, None)))

    def test_cost_and_tax_summary_read_model_methods_are_removed(self) -> None:
        removed_methods = {
            "load_cost_statistics_read_models",
            "get_cost_statistics_view",
            "save_cost_statistics_read_models",
            "load_tax_offset_read_models",
            "get_tax_offset_view",
            "save_tax_offset_read_models",
        }

        for method_name in removed_methods:
            with self.subTest(method_name=method_name):
                self.assertFalse(callable(getattr(PostgresSummaryReadModelRepository, method_name, None)))
                self.assertFalse(callable(getattr(PostgresReadModelRepository, method_name, None)))

    def test_workbench_active_generation_exception_is_not_a_manifest_contract(self) -> None:
        self.assertNotIn("workbench", READ_MODEL_MANIFEST)

    def test_bank_account_balance_manifest_is_removed(self) -> None:
        self.assertNotIn("bank_account_balance", READ_MODEL_MANIFEST)

    def test_bank_detail_manifest_is_removed(self) -> None:
        self.assertNotIn("bank_detail", READ_MODEL_MANIFEST)

    def test_invoice_lifecycle_manifest_is_removed(self) -> None:
        self.assertNotIn("invoice_lifecycle", READ_MODEL_MANIFEST)

    def test_cost_tax_and_turnover_manifests_are_removed(self) -> None:
        self.assertNotIn("cost_statistics", READ_MODEL_MANIFEST)
        self.assertNotIn("tax_offset", READ_MODEL_MANIFEST)
        self.assertNotIn("turnover_ledger", READ_MODEL_MANIFEST)
        self.assertNotIn("cost_statistics", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("tax_offset", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("turnover_ledger", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("cost_statistics.read_model.refresh", rabbitmq_dispatch_event_types())
        self.assertNotIn("tax_offset.read_model.refresh", rabbitmq_dispatch_event_types())
        self.assertNotIn("turnover_ledger.read_model.refresh", rabbitmq_dispatch_event_types())

    def test_no_oa_bank_batch_manifest_entry_is_removed(self) -> None:
        self.assertNotIn("no_oa_bank_batch", READ_MODEL_MANIFEST)

    def test_workbench_relation_manifest_entry_is_removed(self) -> None:
        self.assertNotIn("workbench_relation", READ_MODEL_MANIFEST)
        self.assertNotIn("workbench_relation", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("workbench_relation.read_model.refresh", rabbitmq_dispatch_event_types())


if __name__ == "__main__":
    unittest.main()
