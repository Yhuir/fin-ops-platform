from __future__ import annotations

from pathlib import Path
import unittest

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
        self.assertIn('getattr(self, "_bank_flow_rule_batch_canonical_query_repository", None)', source)

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
            SERVICES_ROOT / "bank_flow_rule_batch_canonical_draft_owner.py",
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
        self.assertIn('"workbench_relation_repository"', server_body)
        self.assertIn("relation_source_repository=relation_source_repository", server_body)
        self.assertIn("bank_batch_query_repository=query_repository", server_body)
        self.assertIn("background_refresh_producer=", server_body)
        self.assertNotIn("queue_repository=", server_body)
        self.assertNotIn("relation_facade=", server_body)
        self.assertNotIn("no_oa_bank_batch_service=", server_body)
        self.assertNotIn("no_oa_bank_batch_read_model_repository=", server_body)

        worker_start = worker_source.index("    if args.enable_bank_flow_rule_batch_canonical_draft_refresh:")
        worker_end = worker_source.index("\n    if args.enable_import_job_processing:", worker_start)
        worker_body = worker_source[worker_start:worker_end]
        self.assertIn("bank_batch_service=bank_flow_service", worker_body)
        self.assertIn("BankFlowRuleBatchCanonicalDraftPersistencePort", worker_body)
        self.assertIn("load_bank_flow_rule_batches()", worker_body)
        self.assertIn("relation_source_repository=(", worker_body)
        self.assertIn("PostgresWorkbenchRelationRepository(connection)", worker_body)
        self.assertNotIn("load_workbench_pair_relations()", worker_body)
        self.assertNotIn("relation_facade=workbench_relation_read_facade", worker_body)
        self.assertNotIn("no_oa_bank_batch_service=", worker_body)
        self.assertNotIn("NoOaBankBatchReadModelPersistencePort", worker_body)

    def test_canonical_page_query_does_not_read_projection_or_no_oa_fallback(self) -> None:
        source = (
            SERVICES_ROOT / "postgres_repositories" / "bank_flow_rule_batch_canonical_query.py"
        ).read_text(encoding="utf-8")

        self.assertIn("set transaction isolation level repeatable read read only", source)
        self.assertIn("from app.bank_flow_rule_batches batch", source)
        self.assertIn("from app.workbench_pair_relations relation", source)
        self.assertIn("relation.status = 'active'", source)
        self.assertNotIn("read_model.", source)
        self.assertNotIn("app.no_oa_bank_batches", source)
        self.assertNotIn("bank_flow_rule_batch_relation_read_model_not_fresh", source)

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
        end = source.index("\n    def save_bank_flow_rule_batch_items", start)
        save_body = source[start:end]
        self.assertIn("_workbench_repository.save_bank_flow_rule_batches(", save_body)
        self.assertIn("expected_source_proof=expected_source_proof", save_body)
        self.assertIn("_workbench_repository.save_bank_flow_rule_batches_scope(", save_body)
        self.assertNotIn("save_no_oa_bank_batches", save_body)

    def test_bank_flow_canonical_draft_runtime_contract_is_independent(self) -> None:
        worker = registration_by_instance_name()["bank-flow-rule-batch"]

        self.assertEqual(
            worker.handler_flags,
            ("--enable-bank-flow-rule-batch-canonical-draft-refresh",),
        )
        self.assertEqual(
            worker.event_types,
            ("bank_flow_rule_batch.canonical_draft.refresh",),
        )
        self.assertIsNone(worker.read_model_scope_type)

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
        self.assertIn("enqueue_background_refresh(", body)
        self.assertNotIn("enqueue_read_model_refreshes_in_transaction", body)
        self.assertNotIn("_read_model_refresh_producer", body)
        self.assertIn("affected_scope_keys_for_tag_codes", body)
        self.assertNotIn("_sync_bank_flow_rule_relation_requirements", no_oa_source)
        self.assertNotIn("def _sync_bank_flow_rule_relation_requirements(", base_source)
        self.assertNotIn("list_active_relations", no_oa_body)
        self.assertNotIn("update_relation_metadata_for_case_id", no_oa_body)


if __name__ == "__main__":
    unittest.main()
