from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "backend" / "src" / "fin_ops_platform"
WEB_SOURCE_ROOT = REPO_ROOT / "web" / "src"
READ_MODEL_WRITE_TARGET_INVENTORY = (
    REPO_ROOT
    / ".planning"
    / "refactors"
    / "modular-io-boundaries"
    / "analysis"
    / "read-model-main-write-target-inventory-2026-06-26.md"
)
READ_MODEL_PRODUCTION_EVIDENCE_RUNBOOK = (
    REPO_ROOT / "docs" / "operations" / "read-model-production-evidence-runbook.md"
)

DIRECT_FRESH_ALLOWLIST: dict[tuple[str, str, str], tuple[int, str]] = {
    (
        "backend/src/fin_ops_platform/app/routes_pending_invoices.py",
        "PendingInvoiceApiRoutes.filter_options",
        "read_model_status=fresh",
    ): (1, "filter options are derived only after PendingInvoiceReadModelService.filter_options returned fresh."),
    (
        "backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py",
        "NoOaBankBatchApplicationService.list_batches_payload",
        "dict read_model_status=fresh",
    ): (1, "read-model rows are source-version checked before marking the payload fresh."),
    (
        "backend/src/fin_ops_platform/services/bank_batch_application_service.py",
        "BankBatchApplicationService.list_batches_payload",
        "dict read_model_status=fresh",
    ): (2, "read-model rows are source-version checked; legacy live fallback is not a read-model projection."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService.conditional_rows",
        "read_model_status=fresh",
    ): (1, "service checks refresh_status and source versions before marking rows fresh."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService.conditional_rows",
        "readModelStatus=fresh",
    ): (1, "camelCase alias for the same fresh-gated rows payload."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService._detail",
        "read_model_status=fresh",
    ): (1, "detail service checks refresh_status and source versions before returning detail payload fresh."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService._detail",
        "readModelStatus=fresh",
    ): (1, "camelCase alias for the same fresh-gated detail payload."),
    (
        "backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py",
        "PendingInvoiceReadModelService.all_rows",
        "dict read_model_status=fresh",
    ): (1, "all-rows helper returns fresh only after every page is fresh."),
    (
        "backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py",
        "PendingInvoiceReadModelService.filter_options",
        "read_model_status=fresh",
    ): (1, "filter options are derived only after rows gate returned fresh."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresBankReadModelRepository.get_bank_detail_tagged_rows_by_transaction_ids",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes current read-model query result to downstream freshness facade."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresPendingInvoiceLifecycleReadModelRepository.get_invoice_lifecycle_rows_by_subject_ids",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes matched rows from an already materialized read model."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresPendingInvoiceLifecycleReadModelRepository.get_invoice_lifecycle_rows_by_identity_keys",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes matched rows from an already materialized read model."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresSearchWorkbenchRelationReadModelRepository.get_workbench_relation_rows_by_ids",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes current relation rows to downstream freshness facade."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresSearchWorkbenchRelationReadModelRepository.get_batch_accounting_relation_rows_by_ids",
        "dict read_model_status=fresh",
    ): (1, "batch accounting relation lookup exposes current rows only after its bulk freshness proof."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresSearchWorkbenchRelationReadModelRepository.get_workbench_relation_groups_by_ids",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes current relation groups to downstream freshness facade."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresReadModelRepository._workbench_summary_from_payload",
        "dict read_model_status=fresh",
    ): (1, "repository shaper mirrors fresh workbench summary payload read from active generation metadata."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresReadModelRepository.get_workbench_relation_preview_selection",
        "dict read_model_status=fresh",
    ): (1, "exact preview selection verifies fresh status and the active generation before and after its bounded SQL read."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresSummaryReadModelRepository._bank_batch_source_versions_summary",
        "dict read_model_status=fresh",
    ): (1, "repository summary exposes source_versions metadata only after bank batch readiness is fresh."),
    (
        "backend/src/fin_ops_platform/services/read_model_query_gateway.py",
        "build_fresh_cache_envelope",
        "dict read_model_status=fresh",
    ): (1, "shared helper is the only generic fresh cache envelope writer."),
    (
        "backend/src/fin_ops_platform/services/workbench_query_facade.py",
        "WorkbenchQueryFacade.group_detail",
        "dict read_model_status=fresh",
    ): (1, "facade returns group detail only after SQL active generation source/status gate passes."),
    (
        "backend/src/fin_ops_platform/services/workbench_query_facade.py",
        "WorkbenchQueryFacade.relation_preview_selection",
        "dict read_model_status=fresh",
    ): (1, "facade mirrors the repository result only after the exact preview selection freshness and generation proof passes."),
    (
        "backend/src/fin_ops_platform/services/workbench_query_facade.py",
        "WorkbenchQueryFacade._cached_groups_payload",
        "read_model_status=fresh",
    ): (1, "workbench groups page cache is separately gated by active generation cache version before use."),
}

SAFE_EXPECTED_SOURCE_VERSION_METHOD_CALLS = {
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService.rows",
    ),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService._detail",
    ),
    (
        "backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py",
        "PendingInvoiceReadModelService.rows",
    ),
}

SHARED_SOURCE_VERSION_COMPARATORS = {
    (
        "backend/src/fin_ops_platform/services/read_model_freshness.py",
        "source_versions_match",
    ),
    (
        "backend/src/fin_ops_platform/services/read_model_freshness.py",
        "resolve_read_model_freshness",
    ),
    (
        "backend/src/fin_ops_platform/services/read_model_query_gateway.py",
        "_cached_payload_passes_fresh_gate",
    ),
}

DIRECT_REFRESH_ENQUEUE_ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "backend/src/fin_ops_platform/app/server.py",
        "Application._enqueue_tax_offset_read_model_refresh",
    ): "legacy HTTP/app wrapper delegates to TaxOffsetRuntimeService, which uses ReadModelRefreshGateway.",
    (
        "backend/src/fin_ops_platform/services/tax_offset_runtime_service.py",
        "TaxOffsetRuntimeService.enqueue_refresh_for_months",
    ): "runtime cache invalidation wrapper calls same-service gateway boundary after deleting fresh-gated cache.",
}

FRONTEND_DEFAULT_FRESH_ALLOWLIST: dict[tuple[str, str, str], tuple[int, str]] = {}

REQUIRED_WRITE_TARGET_INVENTORY_MODULES = {
    "workbench",
    "batch-accounting",
    "bank-details",
    "bank-account-balance",
    "pending-invoices",
    "input-invoice-usage",
    "oa-pending-payments",
    "output-invoice-collections",
    "cost-statistics",
    "tax-offset",
    "no-oa-bank-batches",
    "turnover-ledger",
    "imports-oa-driven",
}


class ReadModelArchitectureGuardTests(unittest.TestCase):
    def test_input_invoice_usage_app_level_projection_helpers_do_not_return(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        forbidden_helpers = {
            "def list_input_invoice_usage_scope_shards(",
            "def mark_input_invoice_usage_scope_empty(",
            "def rebuild_input_invoice_usage_read_model_scope(",
        }

        self.assertEqual([helper for helper in sorted(forbidden_helpers) if helper in server_source], [])

    def test_output_invoice_collection_app_level_projection_helpers_do_not_return(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        forbidden_helpers = {
            "def list_output_invoice_collection_scope_shards(",
            "def mark_output_invoice_collection_scope_empty(",
            "def rebuild_output_invoice_collection_read_model_scope(",
        }

        self.assertEqual([helper for helper in sorted(forbidden_helpers) if helper in server_source], [])

    def test_tax_offset_worker_rebuild_is_explicit_executor_boundary(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        start = server_source.index("    def rebuild_tax_offset_read_model_scope(")
        end = server_source.index("\n    @staticmethod\n    def _invoice_relation_live_rows", start)
        helper_body = server_source[start:end]

        forbidden_snippets = {
            "upsert_read_model(",
            "_persist_tax_offset_read_models_best_effort(",
            "build_fresh_cache_envelope(",
            "_runtime_redis_set_json_best_effort(",
            "read_model_status",
        }
        self.assertEqual([snippet for snippet in sorted(forbidden_snippets) if snippet in helper_body], [])
        self.assertIn("_tax_offset_worker_rebuild_executor.rebuild_scope(scope_key)", helper_body)

    def test_tax_offset_cache_warmup_is_explicit_executor_boundary(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        executor_source = (
            SOURCE_ROOT / "services" / "tax_offset_cache_warmup_executor.py"
        ).read_text(encoding="utf-8")
        start = server_source.index("    def _schedule_tax_offset_cache_warmup(")
        end = server_source.index("\n    def _scope_keys_for_row_ids", start)
        helper_body = server_source[start:end]

        forbidden_server_snippets = {
            "def _run_tax_offset_cache_warmup_job(",
            "def _tax_offset_cache_warmup_enabled(",
            "create_or_get_idempotent_job_with_created(",
            "_background_job_service.run_job(",
            "upsert_read_model(",
            "_persist_tax_offset_read_models_best_effort(",
            "snapshot_scope_keys(",
            "succeed_job(",
            "update_progress(",
            "FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED",
        }
        self.assertEqual([snippet for snippet in sorted(forbidden_server_snippets) if snippet in helper_body], [])
        self.assertNotIn("def _run_tax_offset_cache_warmup_job(", server_source)
        self.assertNotIn("def _tax_offset_cache_warmup_enabled(", server_source)
        self.assertIn("TaxOffsetCacheWarmupExecutor(", server_source)
        self.assertIn("_tax_offset_cache_warmup_executor.schedule(months, reason=reason)", helper_body)

        required_executor_snippets = {
            "class TaxOffsetCacheWarmupExecutor",
            "def schedule(",
            "def run_job(",
            'job_type="tax_offset_cache_warmup"',
            'operation="tax_offset_cache_warmup"',
            "FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED",
            "create_or_get_idempotent_job_with_created(",
            "upsert_read_model(",
            "snapshot_scope_keys(",
            "succeed_job(",
            "update_progress(",
        }
        self.assertEqual(
            [snippet for snippet in sorted(required_executor_snippets) if snippet not in executor_source],
            [],
        )

    def test_cost_and_tax_read_models_are_not_written_by_broad_full_state_persist(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        start = server_source.index("    def _persist_state(self) -> None:")
        end = server_source.index("\n    def _persist_import_preview_delta", start)
        helper_body = server_source[start:end]

        self.assertNotIn("cost_statistics_read_models", helper_body)
        self.assertNotIn("_cost_statistics_read_model_service.snapshot()", helper_body)
        self.assertNotIn("tax_offset_read_models", helper_body)
        self.assertNotIn("_tax_offset_read_model_service.snapshot()", helper_body)
        self.assertNotIn("def _persist_cost_statistics_read_models_best_effort(", server_source)
        self.assertNotIn("_cost_statistics_read_model_service", server_source)
        self.assertIn("def _persist_tax_offset_read_models_best_effort(", server_source)

    def test_broad_state_persist_does_not_write_import_canonical_or_session_facts(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        start = server_source.index("    def _persist_state(self) -> None:")
        end = server_source.index("\n    def _persist_import_preview_delta", start)
        helper_body = server_source[start:end]

        self.assertNotIn('"imports"', helper_body)
        self.assertNotIn('"file_imports"', helper_body)
        self.assertNotIn("_import_service.snapshot()", helper_body)
        self.assertNotIn("_file_import_service.snapshot()", helper_body)
        self.assertNotIn("self._state_store.save(", helper_body)
        self.assertIn('("save_workbench_read_models",', helper_body)
        self.assertIn('("save_pending_invoice_commands",', helper_body)

    def test_file_import_persistence_does_not_write_unrelated_fact_domains(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        preview_start = server_source.index("    def _persist_import_preview_delta(")
        preview_end = server_source.index(
            "\n    def _persist_confirmed_import_delta(",
            preview_start,
        )
        preview_helper_body = server_source[preview_start:preview_end]
        start = server_source.index("    def _persist_confirmed_import_delta(")
        end = server_source.index("\n    def _persist_workbench_pair_relations(", start)
        helper_body = server_source[start:end]

        self.assertNotIn("def _persist_import_preview_state(", server_source)
        self.assertIn("preview_session_persistence_payload(session_id)", preview_helper_body)
        self.assertNotIn(".snapshot(", preview_helper_body)
        self.assertNotIn("save_etc_state", helper_body)
        self.assertNotIn("save_tax_certified_imports", helper_body)
        self.assertNotIn("_etc_service.snapshot()", helper_body)
        self.assertNotIn("_tax_certified_import_service.snapshot()", helper_body)
        self.assertIn('getattr(self._state_store, "save_import_delta", None)', helper_body)
        self.assertIn("persist(payload)", helper_body)
        self.assertNotIn("def _execute_import_state_changed_lifecycle", server_source)

    def test_no_oa_bank_batches_are_not_written_by_broad_full_state_persist(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        start = server_source.index("    def _persist_state(self) -> None:")
        end = server_source.index("\n    def _persist_import_preview_delta", start)
        helper_body = server_source[start:end]

        self.assertNotIn('"no_oa_bank_batches"', helper_body)
        self.assertNotIn("_no_oa_bank_batch_service.snapshot()", helper_body)

        service_source = (SOURCE_ROOT / "services" / "no_oa_bank_batch_read_model_refresh.py").read_text(encoding="utf-8")
        state_store_source = (SOURCE_ROOT / "services" / "state_store.py").read_text(encoding="utf-8")
        postgres_state_store_source = (SOURCE_ROOT / "services" / "postgres_state_store.py").read_text(encoding="utf-8")
        self.assertIn("class NoOaBankBatchReadModelPersistencePort", service_source)
        self.assertIn("def save_no_oa_bank_batch_mutation(", state_store_source)
        self.assertIn("def save_no_oa_bank_batch_mutation(", postgres_state_store_source)

    def test_legacy_write_time_fan_out_contracts_do_not_return(self) -> None:
        offenders: list[str] = []
        forbidden_backend_tokens = (
            "def after_mutation(",
            '"workbench_rebuild_queued"',
            "workbench_read_model_snapshot=self._workbench_read_model_service.snapshot()",
            'affected_months or ["all"]',
        )
        for path in SOURCE_ROOT.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for token in forbidden_backend_tokens:
                if token in source:
                    offenders.append(f"{path.relative_to(REPO_ROOT)} keeps {token}")

        for path in WEB_SOURCE_ROOT.rglob("*.ts*"):
            source = path.read_text(encoding="utf-8")
            for token in ("workbench_rebuild_queued", "workbenchRebuildQueued"):
                if token in source:
                    offenders.append(f"{path.relative_to(REPO_ROOT)} keeps {token}")

        self.assertEqual(offenders, [])

    def test_only_runtime_queue_repository_writes_read_model_job_tables(self) -> None:
        offenders: list[str] = []
        runtime_queue_path = SOURCE_ROOT / "services" / "runtime_queue.py"
        for path in (SOURCE_ROOT / "services").rglob("*.py"):
            if path == runtime_queue_path:
                continue
            source = path.read_text(encoding="utf-8").lower()
            for token in (
                "insert into job.outbox_events",
                "insert into job.read_model_dirty_scopes",
            ):
                if token in source:
                    offenders.append(f"{path.relative_to(REPO_ROOT)} writes {token}")

        self.assertEqual(offenders, [])

    def test_global_refresh_is_owned_only_by_explicit_settings_reset(self) -> None:
        offenders: list[str] = []
        server_path = SOURCE_ROOT / "app" / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        reset_start = server_source.index("    def _execute_settings_data_reset(")
        reset_end = server_source.index("\n    def ", reset_start + 5)
        reset_body = server_source[reset_start:reset_end]
        if reset_body.count("include_all=True") != 1:
            offenders.append("settings reset must own exactly one explicit include_all=True maintenance call")
        for path in SOURCE_ROOT.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            count = source.count("include_all=True")
            if path == server_path:
                count -= reset_body.count("include_all=True")
            if count:
                offenders.append(f"{path.relative_to(REPO_ROOT)} keeps {count} non-maintenance include_all=True call(s)")

        self.assertEqual(offenders, [])

    def test_read_model_query_gateway_load_call_sites_declare_freshness_contract(self) -> None:
        offenders: list[str] = []
        for path in SOURCE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not self._is_read_model_query_gateway_load(node.func):
                    continue
                keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg}
                if not {"expected_source_versions", "expected_schema_version"}.intersection(keyword_names):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

        self.assertEqual(offenders, [])

    def test_read_model_services_do_not_default_source_version_contract_to_empty(self) -> None:
        offenders: list[str] = []
        for path in (SOURCE_ROOT / "services").glob("*read_model*service.py"):
            text = path.read_text(encoding="utf-8")
            if "source_versions_provider or (lambda: {})" in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual(offenders, [])

    def test_direct_fresh_status_assignments_are_explicitly_classified(self) -> None:
        actual: dict[tuple[str, str, str], int] = {}
        for path, tree, parents in self._iter_source_trees():
            relative_path = str(path.relative_to(REPO_ROOT))
            for node in ast.walk(tree):
                for kind in self._direct_fresh_kinds(node):
                    key = (relative_path, self._scope_name(node, parents), kind)
                    actual[key] = actual.get(key, 0) + 1

        expected_counts = {key: count for key, (count, _reason) in DIRECT_FRESH_ALLOWLIST.items()}
        self.assertEqual(actual, expected_counts)

    def test_direct_source_version_mismatch_calls_require_expected_contract(self) -> None:
        offenders: list[str] = []
        for path, tree, parents in self._iter_source_trees():
            relative_path = str(path.relative_to(REPO_ROOT))
            require_assignments = self._require_expected_assignments_by_function(tree, parents)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or _call_name(node.func) != "source_version_mismatch_reasons":
                    continue
                scope_name = self._scope_name(node, parents)
                if (relative_path, scope_name) in SHARED_SOURCE_VERSION_COMPARATORS:
                    continue
                expected_expr = next((keyword.value for keyword in node.keywords if keyword.arg == "expected"), None)
                if expected_expr is None:
                    offenders.append(f"{relative_path}:{node.lineno}:{scope_name}:missing expected keyword")
                    continue
                if self._expected_contract_is_enforced(
                    expected_expr,
                    relative_path=relative_path,
                    scope_name=scope_name,
                    require_assignments=require_assignments,
                ):
                    continue
                offenders.append(f"{relative_path}:{node.lineno}:{scope_name}")

        self.assertEqual(offenders, [])

    def test_direct_read_model_refresh_enqueue_calls_are_classified(self) -> None:
        actual: set[tuple[str, str]] = set()
        for path, tree, parents in self._iter_source_trees():
            relative_path = str(path.relative_to(REPO_ROOT))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or _call_name(node.func) != "enqueue_read_model_refresh":
                    continue
                actual.add((relative_path, self._scope_name(node, parents)))

        self.assertEqual(actual, set(DIRECT_REFRESH_ENQUEUE_ALLOWLIST))

    def test_frontend_read_model_status_default_fresh_sites_are_classified(self) -> None:
        actual: dict[tuple[str, str, str], int] = {}
        for path in WEB_SOURCE_ROOT.rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".js", ".jsx"} or self._is_frontend_test_file(path):
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                kind = self._frontend_default_fresh_kind(line)
                if kind is None:
                    continue
                key = (
                    str(path.relative_to(REPO_ROOT)),
                    kind,
                    self._normalized_source_line(line),
                )
                actual[key] = actual.get(key, 0) + 1

        expected_counts = {key: count for key, (count, _reason) in FRONTEND_DEFAULT_FRESH_ALLOWLIST.items()}
        self.assertEqual(actual, expected_counts)

    def test_read_model_write_operation_target_inventory_covers_required_modules(self) -> None:
        text = READ_MODEL_WRITE_TARGET_INVENTORY.read_text(encoding="utf-8")
        required_columns = {
            "| Module |",
            "| Route/API source |",
            "| Business writes |",
            "| Affected read models/scopes |",
            "| Current response target evidence |",
            "| Closure status |",
            "| Restore strategy |",
        }
        missing_columns = [column for column in sorted(required_columns) if column not in text]
        self.assertEqual(missing_columns, [])
        missing_modules = [
            module for module in sorted(REQUIRED_WRITE_TARGET_INVENTORY_MODULES) if f"| `{module}` |" not in text
        ]
        self.assertEqual(missing_modules, [])
        self.assertNotRegex(text, r"\b(?:TODO|TBD)\b")
        self.assertIn("business inverse", text)
        self.assertIn("bounded DB restore", text)

    def test_read_model_production_evidence_runbook_keeps_restore_and_secret_gates(self) -> None:
        text = READ_MODEL_PRODUCTION_EVIDENCE_RUNBOOK.read_text(encoding="utf-8")
        required_markers = [
            "Admin Token",
            "不得从普通聊天粘贴到 transcript",
            "业务 inverse",
            "Bounded DB Restore Protocol",
            "operation-before snapshot",
            "exact predicate",
            "单事务",
            "post-restore verification",
            "operation barrier",
            "PSCIP-L4",
            "./scripts/deploy-oa.sh",
        ]
        missing = [marker for marker in required_markers if marker not in text]
        self.assertEqual(missing, [])

        index_text = (REPO_ROOT / "docs" / "operations" / "index.md").read_text(encoding="utf-8")
        self.assertIn("read-model-production-evidence-runbook.md", index_text)

    def _iter_source_trees(self) -> list[tuple[Path, ast.AST, dict[ast.AST, ast.AST]]]:
        entries: list[tuple[Path, ast.AST, dict[ast.AST, ast.AST]]] = []
        for path in SOURCE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            parents: dict[ast.AST, ast.AST] = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parents[child] = node
            entries.append((path, tree, parents))
        return entries

    @staticmethod
    def _direct_fresh_kinds(node: ast.AST) -> list[str]:
        kinds: list[str] = []
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and node.value.value == "fresh":
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    if target.slice.value in {"read_model_status", "readModelStatus"}:
                        kinds.append(f"{target.slice.value}=fresh")
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in {"read_model_status", "readModelStatus"}
                    and isinstance(value, ast.Constant)
                    and value.value == "fresh"
                ):
                    kinds.append(f"dict {key.value}=fresh")
        return kinds

    @staticmethod
    def _scope_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
        scope: list[str] = []
        current = node
        while current in parents:
            current = parents[current]
            if isinstance(current, ast.FunctionDef):
                scope.append(current.name)
            elif isinstance(current, ast.ClassDef):
                scope.append(current.name)
        return ".".join(reversed(scope)) or "<module>"

    def _require_expected_assignments_by_function(
        self,
        tree: ast.AST,
        parents: dict[ast.AST, ast.AST],
    ) -> dict[str, set[str]]:
        assignments: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not self._is_require_expected_call(node.value):
                continue
            scope_name = self._scope_name(node, parents)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments.setdefault(scope_name, set()).add(target.id)
        return assignments

    def _expected_contract_is_enforced(
        self,
        expected_expr: ast.AST,
        *,
        relative_path: str,
        scope_name: str,
        require_assignments: dict[str, set[str]],
    ) -> bool:
        if self._is_require_expected_call(expected_expr):
            return True
        if isinstance(expected_expr, ast.Name) and expected_expr.id in require_assignments.get(scope_name, set()):
            return True
        if self._is_expected_source_versions_method_call(expected_expr):
            return (relative_path, scope_name) in SAFE_EXPECTED_SOURCE_VERSION_METHOD_CALLS
        return False

    @staticmethod
    def _is_require_expected_call(node: ast.AST) -> bool:
        return isinstance(node, ast.Call) and _call_name(node.func) == "require_expected_source_versions"

    @staticmethod
    def _is_expected_source_versions_method_call(node: ast.AST) -> bool:
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "expected_source_versions"

    @staticmethod
    def _is_read_model_query_gateway_load(func: ast.AST) -> bool:
        if not isinstance(func, ast.Attribute) or func.attr != "load":
            return False
        value = func.value
        if isinstance(value, ast.Call):
            return _call_name(value.func) == "ReadModelQueryGateway"
        if isinstance(value, ast.Attribute):
            return value.attr in {"_read_model_query_gateway", "read_model_query_gateway"}
        if isinstance(value, ast.Name):
            return value.id in {"read_model_query_gateway"}
        return False

    @staticmethod
    def _is_frontend_test_file(path: Path) -> bool:
        parts = set(path.parts)
        return "test" in parts or path.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))

    @staticmethod
    def _normalized_source_line(line: str) -> str:
        return " ".join(line.strip().split())

    @staticmethod
    def _frontend_default_fresh_kind(line: str) -> str | None:
        has_status = "readModelStatus" in line or "read_model_status" in line
        if not has_status:
            return None
        if re.search(r"\breadModelStatus\s*:\s*['\"]fresh['\"]", line):
            return "object_literal"
        if re.search(r"\b(?:text|stringValue)\([^\n]*(?:readModelStatus|read_model_status)[^\n]*,\s*['\"]fresh['\"]", line):
            return "helper_default"
        if re.search(r"\breadModelStatus\b.*\buseState\(\s*['\"]fresh['\"]\s*\)", line):
            return "use_state"
        has_nullish_default = re.search(r"(?:readModelStatus|read_model_status).*?\?\?\s*['\"]fresh['\"]", line) is not None
        has_logical_default = re.search(r"(?:readModelStatus|read_model_status).*?\|\|\s*['\"]fresh['\"]", line) is not None
        if has_nullish_default and has_logical_default:
            return "nullish_or_logical"
        if has_nullish_default:
            return "nullish"
        if has_logical_default:
            return "logical_or"
        return None


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


if __name__ == "__main__":
    unittest.main()
