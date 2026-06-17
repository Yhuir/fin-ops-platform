from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "backend" / "src" / "fin_ops_platform"

DIRECT_FRESH_ALLOWLIST: dict[tuple[str, str, str], tuple[int, str]] = {
    (
        "backend/src/fin_ops_platform/app/routes_output_invoice_collections.py",
        "OutputInvoiceCollectionApiRoutes.filter_options",
        "read_model_status=fresh",
    ): (1, "filter options are derived only after sql_all_rows_provider returned a fresh rows payload."),
    (
        "backend/src/fin_ops_platform/app/routes_output_invoice_collections.py",
        "OutputInvoiceCollectionApiRoutes.filter_options",
        "readModelStatus=fresh",
    ): (1, "camelCase alias for the same fresh-gated filter-options response."),
    (
        "backend/src/fin_ops_platform/app/routes_pending_invoices.py",
        "PendingInvoiceApiRoutes.filter_options",
        "read_model_status=fresh",
    ): (1, "filter options are derived only after PendingInvoiceReadModelService.filter_options returned fresh."),
    (
        "backend/src/fin_ops_platform/app/server.py",
        "Application._handle_api_input_invoice_usage_filter_options",
        "read_model_status=fresh",
    ): (1, "legacy route derives filter options only from all-rows SQL payload that rejects non-fresh read models."),
    (
        "backend/src/fin_ops_platform/app/server.py",
        "Application._get_invoice_relation_all_rows_from_sql_read_model",
        "dict read_model_status=fresh",
    ): (1, "all-rows helper returns fresh only after every paged SQL read-model payload is fresh."),
    (
        "backend/src/fin_ops_platform/app/server.py",
        "Application._get_input_invoice_usage_rows_from_sql_read_model",
        "read_model_status=fresh",
    ): (1, "legacy query path performs schema/status/source-version checks before marking the SQL payload fresh."),
    (
        "backend/src/fin_ops_platform/app/server.py",
        "Application._get_output_invoice_collection_rows_from_sql_read_model",
        "read_model_status=fresh",
    ): (1, "legacy query path performs schema/status/source-version checks before marking the SQL payload fresh."),
    (
        "backend/src/fin_ops_platform/app/server.py",
        "Application._get_output_invoice_collection_rows_from_sql_read_model",
        "readModelStatus=fresh",
    ): (1, "camelCase alias for the same fresh-gated output invoice collection payload."),
    (
        "backend/src/fin_ops_platform/app/server.py",
        "Application.rebuild_tax_offset_read_model_scope",
        "read_model_status=fresh",
    ): (1, "worker rebuild publishes a freshly generated payload before writing a fresh cache envelope."),
    (
        "backend/src/fin_ops_platform/services/cost_statistics_runtime_service.py",
        "CostStatisticsRuntimeService._cache_fresh_explorer_payload",
        "read_model_status=fresh",
    ): (1, "runtime helper caches only freshly built cost-statistics explorer payloads."),
    (
        "backend/src/fin_ops_platform/services/cost_tax_sql_projection.py",
        "CostStatisticsSqlProjectionBuilder._publish_cost_statistics_scope",
        "dict read_model_status=fresh",
    ): (1, "projection builder publishes the read model it just rebuilt."),
    (
        "backend/src/fin_ops_platform/services/cost_tax_sql_projection.py",
        "TaxOffsetSqlProjectionBuilder.rebuild_tax_offset_read_model_scope",
        "dict read_model_status=fresh",
    ): (1, "projection builder publishes the read model it just rebuilt."),
    (
        "backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py",
        "InputInvoiceUsageExportService.export_preview",
        "dict readModelStatus=fresh",
    ): (1, "export preview first collects pages and rejects non-fresh read-model payloads."),
    (
        "backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py",
        "InputInvoiceUsageExportService.export_preview",
        "dict read_model_status=fresh",
    ): (1, "export preview first collects pages and rejects non-fresh read-model payloads."),
    (
        "backend/src/fin_ops_platform/services/input_invoice_usage_read_model_detail_service.py",
        "InputInvoiceUsageReadModelDetailService.relation_details",
        "read_model_status=fresh",
    ): (1, "detail service checks refresh_status and source versions before returning detail payload fresh."),
    (
        "backend/src/fin_ops_platform/services/input_invoice_usage_read_model_detail_service.py",
        "InputInvoiceUsageReadModelDetailService.relation_details",
        "readModelStatus=fresh",
    ): (1, "camelCase alias for the same fresh-gated detail payload."),
    (
        "backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py",
        "NoOaBankBatchApplicationService.list_batches_payload",
        "dict read_model_status=fresh",
    ): (2, "read-model rows are source-version checked; legacy live fallback is not a read-model projection."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService.rows",
        "read_model_status=fresh",
    ): (1, "service checks refresh_status and source versions before marking rows fresh."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService.rows",
        "readModelStatus=fresh",
    ): (1, "camelCase alias for the same fresh-gated rows payload."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService.all_rows",
        "dict read_model_status=fresh",
    ): (1, "all-rows helper returns fresh only after each page is fresh."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService.all_rows",
        "dict readModelStatus=fresh",
    ): (1, "camelCase alias for the same fresh-gated all-rows payload."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService.filter_options",
        "read_model_status=fresh",
    ): (1, "filter options are derived only after all_rows returned fresh."),
    (
        "backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py",
        "OaPendingPaymentReadModelService.filter_options",
        "readModelStatus=fresh",
    ): (1, "camelCase alias for the same fresh-gated filter-options payload."),
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
        "PostgresReadModelRepository.get_bank_detail_tagged_rows_by_transaction_ids",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes current read-model query result to downstream freshness facade."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresReadModelRepository.get_invoice_lifecycle_rows_by_subject_ids",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes matched rows from an already materialized read model."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresReadModelRepository.get_invoice_lifecycle_rows_by_identity_keys",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes matched rows from an already materialized read model."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresReadModelRepository.get_workbench_relation_rows_by_ids",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes current relation rows to downstream freshness facade."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresReadModelRepository.get_workbench_relation_groups_by_ids",
        "dict read_model_status=fresh",
    ): (1, "repository fact lookup exposes current relation groups to downstream freshness facade."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresReadModelRepository._workbench_summary_from_payload",
        "dict read_model_status=fresh",
    ): (1, "repository shaper mirrors fresh workbench summary payload read from active generation metadata."),
    (
        "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
        "PostgresReadModelRepository.list_turnover_ledger_view",
        "dict read_model_status=fresh",
    ): (1, "repository returns the turnover ledger view; query service applies source-version freshness gate."),
    (
        "backend/src/fin_ops_platform/services/read_model_query_gateway.py",
        "build_fresh_cache_envelope",
        "dict read_model_status=fresh",
    ): (1, "shared helper is the only generic fresh cache envelope writer."),
    (
        "backend/src/fin_ops_platform/services/workbench_query_facade.py",
        "WorkbenchQueryFacade.group_detail",
        "dict read_model_status=fresh",
    ): (1, "facade returns group detail from SQL active generation repository."),
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


class ReadModelArchitectureGuardTests(unittest.TestCase):
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


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


if __name__ == "__main__":
    unittest.main()
