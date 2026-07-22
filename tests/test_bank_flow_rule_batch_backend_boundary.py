from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.read_model_manifest import READ_MODEL_MANIFEST
from fin_ops_platform.services.runtime_worker_registry import registration_by_instance_name


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "backend/src/fin_ops_platform/app"
SERVICES_ROOT = REPO_ROOT / "backend/src/fin_ops_platform/services"


class BankFlowRuleBatchBackendBoundaryTests(unittest.TestCase):
    def test_no_oa_route_does_not_expose_bank_flow_api(self) -> None:
        source = (APP_ROOT / "routes_no_oa_bank_batches.py").read_text(encoding="utf-8")

        self.assertNotIn("/api/bank-flow-rule-batches", source)
        self.assertNotIn("BANK_FLOW_RULE_BATCH_RELATION_MODE", source)

    def test_server_dispatches_bank_flow_to_dedicated_route(self) -> None:
        source = (APP_ROOT / "server.py").read_text(encoding="utf-8")

        self.assertIn("from fin_ops_platform.app.routes_bank_flow_rule_batches import BankFlowRuleBatchApiRoutes", source)
        self.assertIn("def _bank_flow_rule_batch_routes(self) -> BankFlowRuleBatchApiRoutes:", source)
        self.assertIn("self._bank_flow_rule_batch_routes().route(method, route_path, query, body, headers)", source)
        self.assertIn("read_model_refresh_producer=self._bank_flow_rule_batch_read_model_refresh_producer()", source)
        self.assertIn("BankFlowRuleBatchReadModelRepositoryPort", source)

    def test_bank_flow_runtime_files_do_not_import_no_oa_module_boundaries(self) -> None:
        forbidden = (
            "no_oa_bank_batch_application_service",
            "no_oa_bank_batch_read_model_refresh",
            "no_oa_bank_batch_service",
            "NoOaBankBatchPersistenceError",
            "NoOaBankBatchReadModelPersistencePort",
            "save_no_oa_bank_batch",
            "save_no_oa_bank_batches",
            "load_no_oa_bank_batches",
        )
        for relative_path in (
            APP_ROOT / "routes_bank_flow_rule_batches.py",
            SERVICES_ROOT / "bank_flow_rule_batch_application_service.py",
            SERVICES_ROOT / "bank_flow_rule_batch_read_model_refresh.py",
        ):
            source = relative_path.read_text(encoding="utf-8")
            for snippet in forbidden:
                self.assertNotIn(snippet, source, f"{relative_path.name} still references {snippet}")

    def test_server_and_worker_bank_flow_wiring_use_bank_flow_io_names(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        worker_source = (APP_ROOT / "worker.py").read_text(encoding="utf-8")

        server_start = server_source.index("    def _bank_flow_rule_batch_application_service")
        server_end = server_source.index("\n    def _bank_flow_rule_batch_routes", server_start)
        server_body = server_source[server_start:server_end]
        self.assertIn("bank_batch_service=self._bank_flow_rule_batch_service", server_body)
        self.assertIn("pair_relation_snapshot_port = BankBatchPairRelationSnapshotPort", server_body)
        self.assertIn("relation_source_repository = pair_relation_snapshot_port", server_body)
        self.assertIn("relation_source_repository=relation_source_repository", server_body)
        self.assertIn("bank_batch_read_model_repository=read_repository", server_body)
        self.assertNotIn("no_oa_bank_batch_service=", server_body)
        self.assertNotIn("no_oa_bank_batch_read_model_repository=", server_body)

        worker_start = worker_source.index("    if args.enable_bank_flow_rule_batch_read_model_refresh:")
        worker_end = worker_source.index("\n    if args.enable_turnover_ledger_read_model_refresh:", worker_start)
        worker_body = worker_source[worker_start:worker_end]
        self.assertIn("bank_batch_service=bank_flow_service", worker_body)
        self.assertIn("BankFlowRuleBatchReadModelPersistencePort", worker_body)
        self.assertIn("load_bank_flow_rule_batches()", worker_body)
        self.assertIn("relation_source_repository=(", worker_body)
        self.assertIn("WorkbenchRelationReadModelRepositoryPort(read_model_repository)", worker_body)
        self.assertNotIn("load_workbench_pair_relations()", worker_body)
        self.assertNotIn("relation_facade=workbench_relation_read_facade", worker_body)
        self.assertNotIn("no_oa_bank_batch_service=", worker_body)
        self.assertNotIn("NoOaBankBatchReadModelPersistencePort", worker_body)

    def test_operation_barrier_has_no_bank_flow_to_no_oa_alias(self) -> None:
        source = (SERVICES_ROOT / "operation_freshness_barrier.py").read_text(encoding="utf-8")

        self.assertNotIn("READ_MODEL_STATUS_SOURCE_KEYS", source)
        self.assertNotIn('"bank_flow_rule_batch": "no_oa_bank_batch"', source)

    def test_postgres_state_store_bank_flow_storage_uses_dedicated_repository_io(self) -> None:
        source = (SERVICES_ROOT / "postgres_state_store.py").read_text(encoding="utf-8")
        start = source.index("    def load_bank_flow_rule_batches")
        end = source.index("\n    def save_no_oa_bank_batches", start)
        load_body = source[start:end]
        self.assertIn("load_bank_flow_rule_batches()", load_body)
        self.assertNotIn("load_no_oa_bank_batches()", load_body)

        start = source.index("    def save_bank_flow_rule_batches")
        end = source.index("\n    def load_workbench_read_models", start)
        save_body = source[start:end]
        self.assertIn("_workbench_repository.save_bank_flow_rule_batches(snapshot)", save_body)
        self.assertIn("_workbench_repository.save_bank_flow_rule_batches_scope(", save_body)
        self.assertNotIn("save_no_oa_bank_batches", save_body)

    def test_bank_flow_read_model_runtime_contract_is_independent(self) -> None:
        definition = APP_STATUS_READ_MODEL_REGISTRY["bank_flow_rule_batch"]
        manifest = READ_MODEL_MANIFEST["bank_flow_rule_batch"]
        worker = registration_by_instance_name()["bank-flow-rule-batch"]

        self.assertEqual(definition.scope_type, "bank_flow_rule_batch")
        self.assertEqual(definition.worker_instance, "bank-flow-rule-batch")
        self.assertEqual(definition.refresh_event_type, "bank_flow_rule_batch.read_model.refresh")
        self.assertEqual(manifest.repository_owner, "BankFlowRuleBatchReadModelRepositoryPort")
        self.assertEqual(worker.handler_flags, ("--enable-bank-flow-rule-batch-read-model-refresh",))
        self.assertEqual(worker.event_types, ("bank_flow_rule_batch.read_model.refresh",))
        self.assertEqual(worker.read_model_scope_type, "bank_flow_rule_batch")

    def test_tag_rule_save_cannot_rewrite_relations_or_run_broad_lifecycle(self) -> None:
        bank_flow_source = (SERVICES_ROOT / "bank_flow_rule_batch_application_service.py").read_text(encoding="utf-8")
        base_source = (SERVICES_ROOT / "bank_batch_application_service.py").read_text(encoding="utf-8")
        no_oa_source = (SERVICES_ROOT / "no_oa_bank_batch_application_service.py").read_text(encoding="utf-8")
        start = bank_flow_source.index("    def update_tag_selection(")
        body = bank_flow_source[start:]
        no_oa_start = no_oa_source.index("    def update_tag_selection(")
        no_oa_end = no_oa_source.index("\n    def detail_payload(", no_oa_start)
        no_oa_body = no_oa_source[no_oa_start:no_oa_end]

        for forbidden in (
            "list_active_relations",
            "update_relation_metadata_for_case_id",
            "_sync_bank_flow_rule_relation_requirements",
            "after_mutation(",
            "bank_flow_rule_batch_changed",
        ):
            self.assertNotIn(forbidden, body)
        self.assertNotIn("enqueue_background_refresh(", body)
        self.assertNotIn("enqueue_read_model_refreshes_in_transaction", body)
        self.assertNotIn("_read_model_refresh_producer.enqueue", body)
        self.assertIn("affected_scope_keys_for_tag_codes", body)
        self.assertNotIn("_sync_bank_flow_rule_relation_requirements", no_oa_source)
        self.assertNotIn("def _sync_bank_flow_rule_relation_requirements(", base_source)
        self.assertNotIn("list_active_relations", no_oa_body)
        self.assertNotIn("update_relation_metadata_for_case_id", no_oa_body)


if __name__ == "__main__":
    unittest.main()
