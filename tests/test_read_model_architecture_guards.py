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

DIRECT_FRESH_ALLOWLIST: dict[tuple[str, str, str], tuple[int, str]] = {}

SAFE_EXPECTED_SOURCE_VERSION_METHOD_CALLS: set[tuple[str, str]] = set()

SHARED_SOURCE_VERSION_COMPARATORS = {
    (
        "backend/src/fin_ops_platform/services/read_model_freshness.py",
        "source_versions_match",
    ),
    (
        "backend/src/fin_ops_platform/services/read_model_freshness.py",
        "resolve_read_model_freshness",
    ),
}

DIRECT_REFRESH_ENQUEUE_ALLOWLIST: dict[tuple[str, str], str] = {}

FRONTEND_DEFAULT_FRESH_ALLOWLIST: dict[tuple[str, str, str], tuple[int, str]] = {}

REQUIRED_WRITE_TARGET_INVENTORY_MODULES = {
    "workbench",
    "batch-accounting",
    "bank-details",
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
            "def _enqueue_input_invoice_usage_read_model_refresh(",
            "def _invalidate_input_invoice_usage_oa_reverse_read_models(",
            "def _enqueue_input_invoice_usage_payment_rules_refreshes(",
        }

        self.assertEqual([helper for helper in sorted(forbidden_helpers) if helper in server_source], [])

    def test_oa_pending_payment_app_level_refresh_helper_does_not_return(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")

        self.assertNotIn("def _enqueue_oa_pending_payment_read_model_refresh(", server_source)

    def test_application_generic_read_model_refresh_gateway_does_not_return(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")

        forbidden_snippets = {
            "ReadModelRefreshGateway",
            "def _read_model_refresh_gateway(",
            "def _enqueue_generic_read_model_refreshes(",
        }
        self.assertEqual([snippet for snippet in sorted(forbidden_snippets) if snippet in server_source], [])

    def test_runtime_worker_handler_generic_read_model_refresh_gateway_does_not_return(self) -> None:
        source = (SOURCE_ROOT / "services" / "runtime_worker_handlers.py").read_text(encoding="utf-8")

        forbidden_snippets = {
            "ReadModelRefreshGateway",
            "def _enqueue_scopes(",
            "def _enqueue_domain(",
        }
        self.assertEqual([snippet for snippet in sorted(forbidden_snippets) if snippet in source], [])

    def test_runtime_worker_dependency_refresh_gateway_does_not_return(self) -> None:
        source = (SOURCE_ROOT / "services" / "runtime_worker.py").read_text(encoding="utf-8")

        forbidden_snippets = {
            "ReadModelRefreshGateway",
            "_read_model_refresh_gateway",
            "_enqueue_dependency_refreshes",
            "read_model_refresh_is_active",
            "read_model_refresh_is_fresh",
            "enqueue_read_model_refresh(",
            "dependency_refreshes",
        }
        self.assertEqual([snippet for snippet in sorted(forbidden_snippets) if snippet in source], [])

    def test_read_model_refresh_gateway_module_is_removed(self) -> None:
        self.assertFalse((SOURCE_ROOT / "services" / "read_model_refresh_gateway.py").exists())

    def test_runtime_queue_read_model_refresh_methods_are_removed(self) -> None:
        from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository

        forbidden_methods = {
            "enqueue_read_model_refresh",
            "enqueue_read_model_refresh_in_transaction",
            "complete_read_model_refresh",
            "read_model_refresh_is_current",
            "read_model_refresh_is_active",
            "read_model_refresh_is_fresh",
        }
        self.assertEqual(
            [name for name in sorted(forbidden_methods) if hasattr(RuntimeQueueRepository, name)],
            [],
        )

    def test_pending_invoice_app_level_scope_list_helper_does_not_return(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")

        self.assertNotIn("def _pending_invoice_read_model_scope_keys(", server_source)

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
            "redis_set_json_best_effort(",
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
        self.assertNotIn("def _invalidate_tax_offset_read_model_scopes(", server_source)
        self.assertNotIn("def _tax_offset_cache_warmup_enabled(", server_source)
        self.assertIn("TaxOffsetCacheWarmupExecutor(", server_source)
        self.assertIn("_tax_offset_cache_warmup_executor.schedule(months, reason=reason)", helper_body)

        required_executor_snippets = {
            "class TaxOffsetCacheWarmupExecutor",
            "def schedule(",
            "def run_job(",
            'job_type="tax_offset_cache_warmup"',
            "FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED",
            "create_or_get_idempotent_job_with_created(",
            "succeed_job(",
            "update_progress(",
        }
        self.assertEqual(
            [snippet for snippet in sorted(required_executor_snippets) if snippet not in executor_source],
            [],
        )
        forbidden_executor_snippets = {
            "read_model_service:",
            "self._read_model_service",
            "upsert_legacy_read_model(",
            "upsert_read_model(",
            "snapshot_scope_keys(",
        }
        self.assertEqual(
            [snippet for snippet in sorted(forbidden_executor_snippets) if snippet in executor_source],
            [],
        )

    def test_cost_and_tax_read_models_are_not_written_by_broad_full_state_persist(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        start = server_source.index("    def _persist_state(self) -> None:")
        end = server_source.index("\n    def _persist_state_with_workbench_invalidation", start)
        helper_body = server_source[start:end]

        self.assertNotIn("cost_statistics_read_models", helper_body)
        self.assertNotIn("_cost_statistics_local_store.snapshot()", helper_body)
        self.assertNotIn("tax_offset_read_models", helper_body)
        self.assertNotIn("_tax_offset_local_store.snapshot()", helper_body)
        self.assertNotIn("def _persist_cost_statistics_read_models_best_effort(", server_source)
        self.assertNotIn("def _persist_tax_offset_read_models_best_effort(", server_source)

    def test_cost_statistics_app_level_invalidation_wrappers_do_not_return(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")

        self.assertNotIn("def _invalidate_cost_statistics_read_models(", server_source)
        self.assertNotIn("def _invalidate_cost_statistics_read_model_scopes(", server_source)

    def test_no_oa_bank_batches_are_not_written_by_broad_full_state_persist(self) -> None:
        server_source = (SOURCE_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        start = server_source.index("    def _persist_state(self) -> None:")
        end = server_source.index("\n    def _persist_state_with_workbench_invalidation", start)
        helper_body = server_source[start:end]

        self.assertNotIn('"no_oa_bank_batches"', helper_body)
        self.assertNotIn("_no_oa_bank_batch_service.snapshot()", helper_body)

        state_store_source = (SOURCE_ROOT / "services" / "state_store.py").read_text(encoding="utf-8")
        postgres_state_store_source = (SOURCE_ROOT / "services" / "postgres_state_store.py").read_text(encoding="utf-8")
        self.assertFalse((SOURCE_ROOT / "services" / "no_oa_bank_batch_read_model_refresh.py").exists())
        self.assertIn("def save_no_oa_bank_batch_mutation(", state_store_source)
        self.assertIn("def save_no_oa_bank_batch_mutation(", postgres_state_store_source)

    def test_read_model_query_gateway_is_removed(self) -> None:
        self.assertFalse((SOURCE_ROOT / "services" / "read_model_query_gateway.py").exists())

    def test_oa_pending_payment_read_model_service_is_removed(self) -> None:
        self.assertFalse((SOURCE_ROOT / "services" / "oa_pending_payment_read_model_service.py").exists())
        self.assertFalse((SOURCE_ROOT / "services" / "oa_pending_payment_read_model_details.py").exists())

    def test_pending_invoice_read_model_service_is_removed(self) -> None:
        self.assertFalse((SOURCE_ROOT / "services" / "pending_invoice_read_model_service.py").exists())

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
            "direct refetch",
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
