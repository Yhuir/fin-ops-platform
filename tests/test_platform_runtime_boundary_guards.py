from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from fin_ops_platform.app import server as server_module
from fin_ops_platform.services.runtime_bootstrap import LegacySnapshotBootstrap


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "backend" / "src" / "fin_ops_platform"
APP_ROOT = SOURCE_ROOT / "app"
SERVICES_ROOT = SOURCE_ROOT / "services"


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _python_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend(path for path in root.rglob("*.py") if path.is_file())
    return sorted(files)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=_relative(path))


def _imported_modules(tree: ast.Module) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    return modules


def _imports_name_from_module(tree: ast.Module, *, module: str, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            if any(alias.name == name for alias in node.names):
                return True
    return False


def _attribute_calls(tree: ast.Module, names: set[str]) -> list[str]:
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in names:
            calls.append(node.func.attr)
    return calls


def _attribute_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attribute_chain(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


class _ForbiddenRelationReadVisitor(ast.NodeVisitor):
    def __init__(self, *, path: Path) -> None:
        self._path = path
        self._class_stack: list[str] = []
        self._function_stack: list[str] = []
        self.violations: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_stack.append(node.name)
        self.generic_visit(node)
        self._function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = self._forbidden_call_name(node)
        if call_name and not self._is_allowed_context(call_name):
            owner = ".".join([*self._class_stack, *self._function_stack]) or "<module>"
            self.violations.append(f"{_relative(self._path)}:{node.lineno} {owner} calls {call_name}")
        self.generic_visit(node)

    def _forbidden_call_name(self, node: ast.Call) -> str:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {
            "active_relations_for_row_ids",
            "list_active_relations",
            "load_workbench_pair_relations",
        }:
            if _attribute_chain(func.value).endswith("._pair_relation_service"):
                return func.attr
            if func.attr == "load_workbench_pair_relations":
                return func.attr
        if isinstance(func, ast.Attribute) and func.attr == "from_snapshot":
            value = func.value
            if isinstance(value, ast.Name) and value.id == "WorkbenchPairRelationService":
                return "WorkbenchPairRelationService.from_snapshot"
        return ""

    def _is_allowed_context(self, call_name: str) -> bool:
        rel_path = _relative(self._path)
        class_name = self._class_stack[-1] if self._class_stack else ""
        function_name = self._function_stack[-1] if self._function_stack else ""
        allowed_methods = {
            "backend/src/fin_ops_platform/services/pending_invoice_service.py": {
                "PendingInvoiceApplicationService._create_relation",
                "PendingInvoiceApplicationService._create_attach_existing_relation",
                "PendingInvoiceApplicationService._attach_existing_conflicts",
                "PendingInvoiceApplicationService._paid_total_for_invoice",
                "PendingInvoiceApplicationService._invoice_has_pending_relation",
            },
            "backend/src/fin_ops_platform/services/batch_accounting_service.py": {
                "BatchAccountingService._submit_unlocked",
                "BatchAccountingService.repair_legacy_case_id_collisions",
            },
            "backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py": {
                "NoOaBankBatchApplicationService.submit_selected_rows",
                "NoOaBankBatchApplicationService._validate_internal_transfer_selection",
                "NoOaBankBatchApplicationService._restore_snapshots",
            },
            "backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py": {
                "NoOaBankBatchService._repair_submitted_no_oa_relation_consistency",
            },
        }
        qualified = f"{class_name}.{function_name}" if class_name and function_name else function_name
        if qualified in allowed_methods.get(rel_path, set()):
            return True
        return call_name == "load_workbench_pair_relations" and rel_path in {
            "backend/src/fin_ops_platform/app/worker.py",
            "backend/src/fin_ops_platform/services/runtime_worker_handlers.py",
            "backend/src/fin_ops_platform/services/postgres_state_store.py",
            "backend/src/fin_ops_platform/services/shadow_read_psql_store.py",
            "backend/src/fin_ops_platform/services/state_store.py",
        }


def _sql_write_table_references(source: str) -> list[str]:
    normalized = " ".join(source.lower().split())
    patterns = (
        r"\binsert\s+into\s+job\.outbox_events\b",
        r"\bupdate\s+job\.outbox_events\b",
        r"\bdelete\s+from\s+job\.outbox_events\b",
        r"\binsert\s+into\s+job\.read_model_dirty_scopes\b",
        r"\bupdate\s+job\.read_model_dirty_scopes\b",
        r"\bdelete\s+from\s+job\.read_model_dirty_scopes\b",
    )
    return [pattern for pattern in patterns if re.search(pattern, normalized)]


class RuntimeRepositorySummary:
    def summary(self) -> dict[str, object]:
        return {
            "queue_repository": False,
            "queue_backend": "postgres",
            "redis_enabled": False,
            "object_storage_backend": "local",
            "object_storage_enabled": False,
        }


class Store:
    def __init__(self, *, backend: str) -> None:
        self._backend = backend

    @property
    def storage_mode(self) -> str:
        return self._backend

    @property
    def storage_backend(self) -> str:
        return self._backend

    @property
    def mongo_database_name(self) -> str | None:
        return None


def _bare_application(*, backend: str = "postgres", bootstrap_mode: str = "production") -> server_module.Application:
    app = object.__new__(server_module.Application)
    app._bootstrap_mode = bootstrap_mode
    app._state_store = Store(backend=backend)
    app._legacy_bootstrap = LegacySnapshotBootstrap(None)
    app._runtime_repositories = RuntimeRepositorySummary()
    app._seed_payload = {}
    return app


class PlatformRuntimeBoundaryGuardTests(unittest.TestCase):
    def test_explicit_production_guard_rejects_non_postgres_storage_backend(self) -> None:
        app = _bare_application(backend="local_pickle")

        with patch.dict(os.environ, {"FIN_OPS_PRODUCTION_RUNTIME_GUARD": "1"}, clear=True):
            summary = app.readiness_summary()

        self.assertEqual(summary["status"], "not_ready")
        self.assertIn("storage_backend_not_postgres", summary["production_runtime_guard"]["problems"])

    def test_explicit_production_guard_rejects_legacy_bootstrap_and_full_snapshot_flag(self) -> None:
        app = _bare_application(backend="postgres", bootstrap_mode="legacy")

        with patch.dict(
            os.environ,
            {
                "FIN_OPS_PRODUCTION_RUNTIME_GUARD": "1",
                "FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT": "true",
            },
            clear=True,
        ):
            summary = app.readiness_summary()

        self.assertEqual(summary["status"], "not_ready")
        self.assertIn("legacy_bootstrap_in_production", summary["production_runtime_guard"]["problems"])
        self.assertIn("postgres_full_state_snapshot_enabled", summary["production_runtime_guard"]["problems"])

    def test_services_do_not_import_http_auth_boundary_or_parse_cookie_token_headers(self) -> None:
        violations: list[str] = []
        for path in _python_files(SERVICES_ROOT):
            tree = _parse(path)
            modules = _imported_modules(tree)
            source = path.read_text(encoding="utf-8")
            if "fin_ops_platform.app.auth" in modules:
                violations.append(f"{_relative(path)} imports app.auth")
            if re.search(r"\bAdmin-Token\b|\bSimpleCookie\b", source):
                violations.append(f"{_relative(path)} parses OA token cookie/header")

        self.assertEqual(violations, [])

    def test_real_redis_and_rabbitmq_clients_are_confined_to_platform_adapters(self) -> None:
        allowed_imports = {
            "redis": {"backend/src/fin_ops_platform/services/runtime_redis.py"},
            "pika": {"backend/src/fin_ops_platform/services/rabbitmq_runtime.py"},
        }
        violations: list[str] = []
        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            modules = _imported_modules(_parse(path))
            rel_path = _relative(path)
            for module_name, allowed_paths in allowed_imports.items():
                if module_name in modules and rel_path not in allowed_paths:
                    violations.append(f"{rel_path} imports {module_name}")

        self.assertEqual(violations, [])

    def test_pending_invoice_services_do_not_depend_on_redis_or_rabbitmq_clients(self) -> None:
        pending_invoice_paths = {
            SERVICES_ROOT / "pending_invoice_service.py",
            SERVICES_ROOT / "pending_invoice_rules.py",
            SERVICES_ROOT / "pending_invoice_lifecycle_service.py",
            SERVICES_ROOT / "pending_invoice_read_model_service.py",
            SERVICES_ROOT / "pending_invoice_rules_application_service.py",
            SERVICES_ROOT / "search_pending_sql_projection.py",
            SERVICES_ROOT / "search_pending_read_model_refresh.py",
        }
        forbidden_modules = {
            "redis",
            "pika",
            "fin_ops_platform.services.runtime_redis",
            "fin_ops_platform.services.rabbitmq_runtime",
        }
        violations: list[str] = []

        for path in sorted(pending_invoice_paths):
            modules = _imported_modules(_parse(path))
            imported_forbidden = sorted(module for module in forbidden_modules if module in modules)
            if imported_forbidden:
                violations.append(f"{_relative(path)} imports {imported_forbidden}")

        self.assertEqual(violations, [])

    def test_server_no_longer_owns_pending_invoice_read_model_builder_or_gate(self) -> None:
        source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        forbidden_symbols = {
            "def _get_pending_invoice_rows_from_sql_read_model",
            "def _get_pending_invoice_all_rows_from_sql_read_model",
            "def _pending_invoice_expected_source_versions",
            "def _pending_invoice_refreshing_payload",
            "def _pending_invoice_sql_payload_response",
            "def _enqueue_pending_invoice_read_model_refresh",
            "def _record_pending_invoice_manual_invoice_audit",
            "def _finalize_pending_invoice_manual_invoice",
            "def rebuild_pending_invoice_read_model_scope",
        }
        violations = [symbol for symbol in sorted(forbidden_symbols) if symbol in source]

        self.assertEqual(violations, [])

    def test_server_no_longer_owns_import_confirm_processors(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        service_source = (SERVICES_ROOT / "import_processing_service.py").read_text(encoding="utf-8")
        forbidden_server_snippets = {
            "self._import_service.confirm_import(",
            "self._tax_certified_import_service.confirm_session(",
            "self._file_import_service.confirm_session(",
            "self._etc_service.confirm_import_session_with_progress(",
        }
        violations = [snippet for snippet in sorted(forbidden_server_snippets) if snippet in server_source]

        self.assertEqual(violations, [])
        self.assertIn("class ImportProcessingService", service_source)
        self.assertIn("def execute_file_import_confirm_job", service_source)
        self.assertIn("def execute_etc_invoice_import_confirm_job", service_source)

    def test_output_invoice_collection_boundary_does_not_depend_on_redis_or_rabbitmq_clients(self) -> None:
        output_invoice_collection_paths = {
            APP_ROOT / "routes_output_invoice_collections.py",
            SERVICES_ROOT / "output_invoice_collection_lifecycle_service.py",
            SERVICES_ROOT / "output_invoice_collection_models.py",
            SERVICES_ROOT / "output_invoice_collection_receipt_service.py",
            SERVICES_ROOT / "output_invoice_collection_service.py",
            SERVICES_ROOT / "output_invoice_collection_status_service.py",
            SERVICES_ROOT / "invoice_usage_collection_read_model_refresh.py",
            SERVICES_ROOT / "invoice_usage_collection_sql_projection.py",
            SERVICES_ROOT / "postgres_repositories" / "output_invoice_collection.py",
        }
        forbidden_modules = {
            "redis",
            "pika",
            "fin_ops_platform.services.runtime_redis",
            "fin_ops_platform.services.rabbitmq_runtime",
        }
        violations: list[str] = []

        for path in sorted(output_invoice_collection_paths):
            if not path.exists():
                violations.append(f"{_relative(path)} is missing")
                continue
            modules = _imported_modules(_parse(path))
            imported_forbidden = sorted(module for module in forbidden_modules if module in modules)
            if imported_forbidden:
                violations.append(f"{_relative(path)} imports {imported_forbidden}")

        self.assertEqual(violations, [])

    def test_downstream_relation_read_models_use_workbench_relation_distribution(self) -> None:
        downstream_paths = {
            SERVICES_ROOT / "search_pending_sql_projection.py",
            SERVICES_ROOT / "invoice_usage_collection_sql_projection.py",
            SERVICES_ROOT / "invoice_relation_query_context.py",
            SERVICES_ROOT / "input_invoice_usage_service.py",
            SERVICES_ROOT / "output_invoice_collection_service.py",
            SERVICES_ROOT / "oa_pending_payment_service.py",
            SERVICES_ROOT / "bank_detail_sql_projection.py",
            SERVICES_ROOT / "bank_details_relation_tag_projection_service.py",
            SERVICES_ROOT / "pending_invoice_service.py",
            SERVICES_ROOT / "batch_accounting_service.py",
            SERVICES_ROOT / "no_oa_bank_batch_application_service.py",
            SERVICES_ROOT / "no_oa_bank_batch_service.py",
            SERVICES_ROOT / "cost_tax_sql_projection.py",
            SERVICES_ROOT / "cost_statistics_service.py",
        }
        forbidden_snippets = {
            "from app.workbench_pair_relations",
        }
        violations: list[str] = []

        for path in sorted(downstream_paths):
            if not path.exists():
                violations.append(f"{_relative(path)} is missing")
                continue
            source = path.read_text(encoding="utf-8")
            normalized_source = " ".join(source.split())
            rel_path = _relative(path)
            for snippet in sorted(forbidden_snippets):
                actual_count = normalized_source.count(snippet)
                if actual_count:
                    violations.append(f"{rel_path} contains {snippet} {actual_count} time(s)")
            visitor = _ForbiddenRelationReadVisitor(path=path)
            visitor.visit(_parse(path))
            violations.extend(visitor.violations)

        self.assertEqual(violations, [])

    def test_oa_mongo_adapter_direct_use_is_allowlisted(self) -> None:
        allowed_paths = {
            "backend/src/fin_ops_platform/app/oa_attachment_audit.py",
            "backend/src/fin_ops_platform/app/server.py",
            "backend/src/fin_ops_platform/app/worker.py",
            "backend/src/fin_ops_platform/services/etc_oa_detection.py",
            "backend/src/fin_ops_platform/services/oa_manual_import_service.py",
            "backend/src/fin_ops_platform/services/search_pending_sql_projection.py",
            "backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py",
            "backend/src/fin_ops_platform/services/workbench_sql_projection.py",
        }
        known_violations = {
            "backend/src/fin_ops_platform/services/cost_tax_sql_projection.py",
        }
        violations: list[str] = []
        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            tree = _parse(path)
            rel_path = _relative(path)
            if _imports_name_from_module(
                tree,
                module="fin_ops_platform.services.mongo_oa_adapter",
                name="MongoOAAdapter",
            ) and rel_path not in allowed_paths | known_violations:
                violations.append(rel_path)

        self.assertEqual(violations, [])

    def test_workbench_write_and_matching_services_do_not_import_external_clients_directly(self) -> None:
        workbench_boundary_files = {
            "backend/src/fin_ops_platform/services/workbench_action_service.py",
            "backend/src/fin_ops_platform/services/workbench_write_facade.py",
            "backend/src/fin_ops_platform/services/workbench_pair_relation_service.py",
            "backend/src/fin_ops_platform/services/workbench_override_service.py",
            "backend/src/fin_ops_platform/services/workbench_exception_case_service.py",
            "backend/src/fin_ops_platform/services/workbench_exception_application_service.py",
            "backend/src/fin_ops_platform/services/workbench_exception_projection.py",
            "backend/src/fin_ops_platform/services/workbench_exception_classifier.py",
            "backend/src/fin_ops_platform/services/workbench_exception_rules.py",
            "backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py",
            "backend/src/fin_ops_platform/services/workbench_candidate_grouping.py",
            "backend/src/fin_ops_platform/services/workbench_free_matching_engine.py",
            "backend/src/fin_ops_platform/services/workbench_matching_rules.py",
            "backend/src/fin_ops_platform/services/workbench_candidate_match_service.py",
            "backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_service.py",
            "backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_worker.py",
            "backend/src/fin_ops_platform/services/workbench_amount_check_service.py",
            "backend/src/fin_ops_platform/services/workbench_special_pair_rule_service.py",
            "backend/src/fin_ops_platform/services/workbench_special_rule_detectors.py",
            "backend/src/fin_ops_platform/services/workbench_special_reconciliation_adapter.py",
            "backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py",
            "backend/src/fin_ops_platform/services/workbench_reconciliation_decision_store.py",
            "backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py",
        }
        violations: list[str] = []
        for rel_path in sorted(workbench_boundary_files):
            path = REPO_ROOT / rel_path
            if not path.exists():
                violations.append(f"{rel_path} is missing")
                continue
            tree = _parse(path)
            modules = _imported_modules(tree)
            external_imports = sorted({"redis", "pika", "pymysql"} & modules)
            if external_imports:
                violations.append(f"{rel_path} imports {external_imports}")
            if _imports_name_from_module(
                tree,
                module="fin_ops_platform.services.mongo_oa_adapter",
                name="MongoOAAdapter",
            ):
                violations.append(f"{rel_path} imports MongoOAAdapter")

        self.assertEqual(violations, [])

    def test_workbench_write_facade_uses_granular_constructor_dependencies(self) -> None:
        from fin_ops_platform.services.workbench_write_facade import WorkbenchWriteFacade

        signature = inspect.signature(WorkbenchWriteFacade)
        forbidden_terms = {
            "app",
            "application",
            "runtime_repositories",
            "runtime_repository_context",
            "runtime_container",
            "state_store",
            "application_state_store",
        }
        violations = [
            parameter.name
            for parameter in signature.parameters.values()
            if any(term in parameter.name.lower() for term in forbidden_terms)
        ]

        self.assertEqual(violations, [])

    def test_workbench_write_facade_exposes_exception_write_entrypoints(self) -> None:
        from fin_ops_platform.services.workbench_write_facade import WorkbenchWriteFacade

        expected_methods = {
            "apply_exception",
            "mark_exception",
            "cancel_exception",
            "ignore_row",
            "unignore_row",
        }
        missing_methods = [
            method_name
            for method_name in sorted(expected_methods)
            if not callable(getattr(WorkbenchWriteFacade, method_name, None))
        ]

        self.assertEqual(missing_methods, [])

    def test_external_oa_mysql_client_is_confined_to_role_sync_adapter(self) -> None:
        allowed_paths = {
            "backend/src/fin_ops_platform/services/oa_role_sync_service.py",
        }
        violations: list[str] = []
        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            modules = _imported_modules(_parse(path))
            rel_path = _relative(path)
            if "pymysql" in modules and rel_path not in allowed_paths:
                violations.append(rel_path)

        self.assertEqual(violations, [])

    def test_business_code_does_not_write_outbox_or_dirty_scopes_directly(self) -> None:
        allowed_paths = {
            "backend/src/fin_ops_platform/services/postgres_repositories/core.py",
            "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
            "backend/src/fin_ops_platform/services/postgres_repositories/workbench.py",
            "backend/src/fin_ops_platform/services/runtime_queue.py",
        }
        violations: list[str] = []
        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            rel_path = _relative(path)
            if rel_path in allowed_paths:
                continue
            references = _sql_write_table_references(path.read_text(encoding="utf-8"))
            if references:
                violations.append(f"{rel_path}: {references}")

        self.assertEqual(violations, [])

    def test_app_handlers_do_not_execute_raw_postgres_sql(self) -> None:
        allowed_app_sql_files = {
            "backend/src/fin_ops_platform/app/bank_account_balance_backfill.py",
            "backend/src/fin_ops_platform/app/bank_detail_backfill.py",
            "backend/src/fin_ops_platform/app/rabbitmq_dispatcher.py",
            "backend/src/fin_ops_platform/app/worker.py",
        }
        violations: list[str] = []
        for path in _python_files(APP_ROOT):
            rel_path = _relative(path)
            if rel_path in allowed_app_sql_files:
                continue
            calls = _attribute_calls(_parse(path), {"fetch_one", "fetch_all"})
            source = path.read_text(encoding="utf-8")
            if re.search(r"\bPostgresConnection\s*\(", source):
                calls.append("PostgresConnection")
            if calls:
                violations.append(f"{rel_path}: {sorted(set(calls))}")

        self.assertEqual(violations, [])

    def test_runtime_worker_entrypoint_does_not_import_application(self) -> None:
        tree = _parse(APP_ROOT / "worker.py")

        self.assertFalse(
            _imports_name_from_module(
                tree,
                module="fin_ops_platform.app.server",
                name="Application",
            )
        )
        self.assertFalse((APP_ROOT / "worker_legacy_application.py").exists())
        self.assertNotIn(
            "worker_legacy_application",
            (APP_ROOT / "worker.py").read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "RuntimeWorkerApplicationBridge",
            (APP_ROOT / "worker.py").read_text(encoding="utf-8"),
        )

    def test_runtime_worker_handler_bootstrap_does_not_import_application_or_auth(self) -> None:
        path = SERVICES_ROOT / "runtime_worker_handlers.py"
        self.assertTrue(path.exists(), "runtime worker handler bootstrap service is missing")
        tree = _parse(path)
        modules = _imported_modules(tree)

        self.assertNotIn("fin_ops_platform.app.server", modules)
        self.assertNotIn("fin_ops_platform.app.auth", modules)
        self.assertNotIn("HTTPStatus", path.read_text(encoding="utf-8"))
        self.assertNotIn("RuntimeWorkerApplicationBridge", path.read_text(encoding="utf-8"))

    def test_no_oa_worker_bootstrap_does_not_load_full_workbench_snapshot(self) -> None:
        worker_source = (APP_ROOT / "worker.py").read_text(encoding="utf-8")

        self.assertNotIn("load_workbench_read_models()", worker_source)

    def test_raw_postgres_sql_in_services_is_classified_by_platform_boundary(self) -> None:
        allowed_exact_paths = {
            "backend/src/fin_ops_platform/services/bank_account_balance_projection.py",
            "backend/src/fin_ops_platform/services/cutover_preflight.py",
            "backend/src/fin_ops_platform/services/file_object_migration.py",
            "backend/src/fin_ops_platform/services/import_job_queue.py",
            "backend/src/fin_ops_platform/services/oa_role_sync_service.py",
            "backend/src/fin_ops_platform/services/operations_dashboard.py",
            "backend/src/fin_ops_platform/services/postgres_connection.py",
            "backend/src/fin_ops_platform/services/postgres_state_store.py",
            "backend/src/fin_ops_platform/services/runtime_monitoring.py",
            "backend/src/fin_ops_platform/services/runtime_queue.py",
            "backend/src/fin_ops_platform/services/search_pending_sql_projection.py",
        }
        allowed_prefixes = (
            "backend/src/fin_ops_platform/services/postgres_repositories/",
        )
        allowed_suffixes = (
            "_sql_projection.py",
        )
        violations: list[str] = []
        for path in _python_files(SERVICES_ROOT):
            rel_path = _relative(path)
            if rel_path in allowed_exact_paths:
                continue
            if any(rel_path.startswith(prefix) for prefix in allowed_prefixes):
                continue
            if any(rel_path.endswith(suffix) for suffix in allowed_suffixes):
                continue
            calls = _attribute_calls(_parse(path), {"execute", "fetch_one", "fetch_all"})
            if calls:
                violations.append(f"{rel_path}: {sorted(set(calls))}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
