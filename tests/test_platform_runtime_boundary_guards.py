from __future__ import annotations

import ast
import inspect
import os
import re
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.app import server as server_module
from fin_ops_platform.services.cutover_preflight import redact_secret_text
from fin_ops_platform.services.etc_business_batch_application_service import EtcBusinessBatchApplicationService
from fin_ops_platform.services.etc_existing_invoice_link_service import EtcExistingInvoiceLinkService
from fin_ops_platform.services.etc_service import EtcImportItem, EtcImportResult
from fin_ops_platform.services.runtime_worker_handlers import (
    _RuntimeWorkerDerivedLifecycle,
    _link_etc_import_result_to_existing_invoices,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "backend" / "src" / "fin_ops_platform"
APP_ROOT = SOURCE_ROOT / "app"
SERVICES_ROOT = SOURCE_ROOT / "services"
TOOLS_ROOT = SOURCE_ROOT / "tools"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
WEB_SRC_ROOT = REPO_ROOT / "web" / "src"

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

def _parses_http_auth_headers_or_cookies(tree: ast.Module) -> bool:
    imported_modules = _imported_modules(tree)
    if "http.cookies" in imported_modules:
        return True
    if _imports_name_from_module(tree, module="http.cookies", name="SimpleCookie"):
        return True

    forbidden_header_names = {"authorization", "cookie", "admin-token"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get":
            continue
        owner_name = _attribute_chain(node.func.value).lower()
        if not owner_name.endswith("headers") and not owner_name.endswith(".headers"):
            continue
        if not node.args:
            continue
        key_arg = node.args[0]
        if isinstance(key_arg, ast.Constant) and isinstance(key_arg.value, str):
            if key_arg.value.strip().lower() in forbidden_header_names:
                return True
    return False

def _attribute_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attribute_chain(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""

def _function_source(tree: ast.Module, source: str, function_name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    return ""

def _class_source(tree: ast.Module, source: str, class_name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return ast.get_source_segment(source, node) or ""
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
            "get_active_relation_by_case_id",
            "get_active_relation_by_row_id",
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
            "backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py": {
                "NoOaPairRelationSnapshotPort.restore",
            },
            "backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py": {
                "NoOaRelationRepairReadPort.active_relation_by_case_id",
                "NoOaRelationRepairReadPort.active_relations_for_row_ids",
            },
            "backend/src/fin_ops_platform/services/batch_accounting_service.py": {
                "BatchAccountingService._submit_unlocked",
                "BatchAccountingService.withdraw",
                "BatchAccountingService._withdraw_unlocked",
            },
        }
        qualified = f"{class_name}.{function_name}" if class_name and function_name else function_name
        if qualified in allowed_methods.get(rel_path, set()):
            return True
        return call_name == "load_workbench_pair_relations" and rel_path in {
            "backend/src/fin_ops_platform/app/worker.py",
            "backend/src/fin_ops_platform/services/runtime_worker_handlers.py",
            "backend/src/fin_ops_platform/services/postgres_state_store.py",
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
    app._runtime_repositories = RuntimeRepositorySummary()
    app._seed_payload = {}
    return app

class PlatformRuntimeBoundaryGuardTests(unittest.TestCase):
    def test_file_import_has_one_durable_confirm_path_and_removed_revert_fallbacks(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        confirm_source = _function_source(server_tree, server_source, "_handle_import_file_confirm")
        imports_source = (SERVICES_ROOT / "imports.py").read_text(encoding="utf-8")
        file_service_source = (SERVICES_ROOT / "import_file_service.py").read_text(encoding="utf-8")
        web_api_source = (WEB_SRC_ROOT / "features" / "imports" / "api.ts").read_text(encoding="utf-8")
        bank_audit_source = (
            SERVICES_ROOT / "postgres_repositories" / "bank_transaction_import_page_audit.py"
        ).read_text(encoding="utf-8")
        invoice_audit_source = (
            SERVICES_ROOT / "postgres_repositories" / "invoice_import_page_audit.py"
        ).read_text(encoding="utf-8")

        self.assertIn("_enqueue_import_process_job", confirm_source)
        self.assertNotIn("execute_file_import_confirm_job", confirm_source)
        self.assertNotIn("run_file_import", confirm_source)
        for source in (server_source, imports_source, file_service_source, web_api_source):
            self.assertNotIn("revertImportBatch", source)
            self.assertNotIn("_handle_import_batch_revert", source)
            self.assertNotIn("def revert_import", source)
            self.assertNotIn("def mark_batch_reverted", source)
        self.assertNotIn("f.import_batch_id", bank_audit_source)
        self.assertNotIn("f.import_batch_id", invoice_audit_source)

    def test_workbench_scope_invalidation_does_not_refresh_invoice_usage_domains(self) -> None:
        source_path = APP_ROOT / "server.py"
        source = source_path.read_text(encoding="utf-8")
        function_source = _function_source(_parse(source_path), source, "_invalidate_workbench_read_model_scopes")

        self.assertNotIn("_invalidate_invoice_usage_collection_read_model_scopes", function_source)
        self.assertNotIn("_enqueue_input_invoice_usage_read_model_refresh", function_source)
        self.assertNotIn("_enqueue_output_invoice_collection_read_model_refresh", function_source)
        self.assertNotIn("_enqueue_oa_pending_payment_read_model_refresh", function_source)

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

    def test_legacy_etc_batch_backend_api_is_removed(self) -> None:
        app = _bare_application(backend="postgres")

        with patch.dict(os.environ, {"FIN_OPS_PRODUCTION_RUNTIME_GUARD": "1"}, clear=True):
            summary = app.readiness_summary(check_dependencies=False)

        entrypoints = "\n".join(summary["entrypoints"])
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        removed_paths = [
            APP_ROOT / "routes_etc_legacy_batches.py",
            SERVICES_ROOT / "etc_legacy_batch_delete_service.py",
            SERVICES_ROOT / "etc_legacy_batch_lifecycle_service.py",
            SERVICES_ROOT / "etc_legacy_batch_read_facade.py",
        ]
        forbidden_markers = (
            "EtcLegacyBatch",
            "_etc_legacy_batch",
            "_legacy_etc_batch_api_enabled",
            "FIN_OPS_ENABLE_LEGACY_ETC_BATCH_API",
        )
        violations = [f"{_relative(path)} still exists" for path in removed_paths if path.exists()]
        violations.extend(marker for marker in forbidden_markers if marker in server_source)
        if "/api/etc/batches" in entrypoints:
            violations.append("readiness entrypoints still expose legacy ETC batch API")

        self.assertEqual(violations, [])

    def test_shadow_and_dual_state_store_modules_are_removed(self) -> None:
        removed_paths = [
            SERVICES_ROOT / "shadow_state_store.py",
            SERVICES_ROOT / "dual_state_store.py",
            REPO_ROOT / "tests" / "test_shadow_state_store.py",
            REPO_ROOT / "tests" / "test_dual_state_store.py",
        ]
        violations = [f"{_relative(path)} still exists" for path in removed_paths if path.exists()]

        self.assertEqual(violations, [])

    def test_legacy_import_fact_consistency_tool_is_removed(self) -> None:
        path = TOOLS_ROOT / "check_import_fact_consistency.py"

        self.assertFalse(path.exists(), f"{_relative(path)} still exists")

    def test_legacy_postgres_migration_reconcile_tool_is_removed(self) -> None:
        removed_paths = [
            TOOLS_ROOT / "reconcile_postgres_migration.py",
            REPO_ROOT / "tests" / "test_reconcile_postgres_migration.py",
        ]
        violations = [f"{_relative(path)} still exists" for path in removed_paths if path.exists()]

        self.assertEqual(violations, [])

    def test_legacy_mongo_staging_migration_cli_tools_are_removed(self) -> None:
        removed_paths = [
            TOOLS_ROOT / "import_postgres_staging.py",
            TOOLS_ROOT / "transform_staging_to_postgres.py",
            REPO_ROOT / "tests" / "test_import_postgres_staging.py",
        ]
        violations = [f"{_relative(path)} still exists" for path in removed_paths if path.exists()]

        self.assertEqual(violations, [])

    def test_legacy_postgres_transform_tool_is_removed(self) -> None:
        removed_paths = [
            TOOLS_ROOT / "postgres_transform.py",
            REPO_ROOT / "tests" / "test_postgres_transform.py",
        ]
        violations = [f"{_relative(path)} still exists" for path in removed_paths if path.exists()]

        self.assertEqual(violations, [])

    def test_legacy_mongo_export_manifest_helpers_are_removed(self) -> None:
        removed_paths = [
            TOOLS_ROOT / "export_manifest.py",
            REPO_ROOT / "tests" / "test_mongo_export_manifest.py",
        ]
        violations = [f"{_relative(path)} still exists" for path in removed_paths if path.exists()]

        self.assertEqual(violations, [])

    def test_legacy_mongo_exporter_definition_package_is_removed(self) -> None:
        exporters_root = TOOLS_ROOT / "exporters"
        forbidden_markers = {
            "ExportDefinition",
            "CORE_EXPORTS",
            "WORKBENCH_EXPORTS",
            "OPS_TAX_ETC_EXPORTS",
            "READ_MODEL_EXPORTS",
            "gridfs_files_manifest",
            "stage 03",
            "stage 04",
        }
        violations: list[str] = []

        if exporters_root.exists():
            violations.extend(f"{_relative(path)} still exists" for path in sorted(exporters_root.rglob("*")) if path.is_file())

        for path in _python_files(TOOLS_ROOT):
            rel_path = _relative(path)
            source = path.read_text(encoding="utf-8")
            if "fin_ops_platform.tools.exporters" in source:
                violations.append(f"{rel_path} imports legacy exporters package")
            for marker in forbidden_markers:
                if marker in source:
                    violations.append(f"{rel_path} references legacy exporter marker {marker}")

        self.assertEqual(violations, [])

    def test_deploy_runtime_templates_do_not_enable_postgres_full_state_snapshot(self) -> None:
        deploy_files = [
            *sorted((REPO_ROOT / "deploy" / "oa" / "env").glob("*.env.example")),
            REPO_ROOT / "deploy" / "oa" / "bin" / "finops-deploy-control.sh",
        ]
        violations = [
            _relative(path)
            for path in deploy_files
            if "FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT" in path.read_text(encoding="utf-8")
        ]
        deploy_script = (REPO_ROOT / "scripts" / "deploy_oa.py").read_text(encoding="utf-8")

        self.assertEqual(violations, [])
        self.assertIn("check-release", deploy_script)

    def test_deploy_runtime_templates_keep_app_storage_backend_postgres(self) -> None:
        deploy_files = [
            *sorted((REPO_ROOT / "deploy" / "oa" / "env").glob("*.env.example")),
        ]
        violations: list[str] = []
        for path in deploy_files:
            source = path.read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                if not stripped.startswith("FIN_OPS_APP_STORAGE_BACKEND="):
                    continue
                if stripped != "FIN_OPS_APP_STORAGE_BACKEND=postgres":
                    violations.append(f"{_relative(path)} uses {stripped}")
        common_source = (REPO_ROOT / "deploy" / "oa" / "env" / "fin-ops.common.env.example").read_text(encoding="utf-8")

        self.assertEqual(violations, [])
        self.assertIn("FIN_OPS_APP_STORAGE_BACKEND=postgres", common_source)

    def test_canonical_fact_legacy_source_paths_stay_in_removal_baseline(self) -> None:
        production_paths = {
            "backend/src/fin_ops_platform/app/server.py": APP_ROOT / "server.py",
            "backend/src/fin_ops_platform/app/worker.py": APP_ROOT / "worker.py",
            "backend/src/fin_ops_platform/services/runtime_worker_handlers.py": SERVICES_ROOT / "runtime_worker_handlers.py",
            "backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py": SERVICES_ROOT / "turnover_ledger_write_adapters.py",
            "backend/src/fin_ops_platform/services/file_object_migration.py": SERVICES_ROOT / "file_object_migration.py",
        }
        expected_legacy_refs = {
            "backend/src/fin_ops_platform/app/server.py": {
                "load_full_snapshot": 0,
                "MongoOAAdapter": 0,
                "WorkbenchPairRelationService": 3,
                "pair_relation_service": 27,
            },
            "backend/src/fin_ops_platform/app/worker.py": {
                "GridFSObjectMigrationService": 0,
                "LegacyGridFSFileReader": 0,
                "MongoOAAdapter": 0,
                "WorkbenchPairRelationService": 2,
                "pair_relation_service": 6,
            },
            "backend/src/fin_ops_platform/services/runtime_worker_handlers.py": {
                "WorkbenchPairRelationService": 0,
                "pair_relation_service": 0,
            },
            "backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py": {
                "pair_relation_service": 7,
            },
            "backend/src/fin_ops_platform/services/file_object_migration.py": {
                "GridFSObjectMigrationService": 0,
                "LegacyGridFSFileReader": 0,
            },
        }
        forbidden_uninventoried_tokens = (
            "ApplicationStateStore",
            "_load_local_pickle",
            "_save_local_pickle",
            "load_bootstrap_snapshot",
            "state:full_state",
            "state:imports",
            "state:file_imports",
            "state:workbench",
            "TurnoverLedgerBankRowTagsLegacyFallback",
            "TurnoverLedgerClosureLegacyFallback",
            "TurnoverLedgerConfirmLegacyFallback",
            "TurnoverLedgerRelationExtraLegacyFallback",
            "TurnoverLedgerTagSelectionLegacyFallback",
            "TurnoverLedgerWithdrawLegacyFallback",
        )
        tracked_tokens = sorted({token for counts in expected_legacy_refs.values() for token in counts})
        violations: list[str] = []

        for rel_path, path in sorted(production_paths.items()):
            source = path.read_text(encoding="utf-8")
            for token in forbidden_uninventoried_tokens:
                if token in source:
                    violations.append(f"{rel_path} contains uninventoried canonical fact legacy token {token}")
            expected_counts = expected_legacy_refs.get(rel_path, {})
            for token in tracked_tokens:
                actual = source.count(token)
                expected = expected_counts.get(token, 0)
                if actual != expected:
                    violations.append(f"{rel_path} has {actual} {token} reference(s), expected removal baseline {expected}")

        self.assertEqual(violations, [])

    def test_production_services_do_not_type_bind_to_local_application_state_store(self) -> None:
        allowed_paths = {
            "backend/src/fin_ops_platform/services/state_store_factory.py",
        }
        violations: list[str] = []

        for path in _python_files(SERVICES_ROOT):
            rel_path = _relative(path)
            if rel_path in allowed_paths or rel_path.endswith("/state_store.py"):
                continue
            source = path.read_text(encoding="utf-8")
            if "from fin_ops_platform.services.state_store import ApplicationStateStore" in source:
                violations.append(f"{rel_path} imports local ApplicationStateStore")

        self.assertEqual(violations, [])

    def test_application_state_store_does_not_open_app_mongo_snapshot_source(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        init_source = _function_source(ast.parse(class_source), class_source, "__init__")
        violations = [
            token
            for token in (
                "load_mongo_state_settings(",
                "MongoClient(",
                "GridFSBucket(",
                "FIN_OPS_STORAGE_MODE",
                "MONGO_ONLY_STORAGE_MODE",
                "_mongo_client",
                "_mongo_database",
                "_legacy_mongo_collection",
                "_mongo_state_collections",
                "_mongo_metadata_collection",
                "_mongo_meta_collection",
                "_mongo_detailed_collections",
                "_run_mongo_operation",
                "_replace_collection_documents",
                "_load_entities_by_id",
                "_load_entities_list",
                "_load_binary_payload",
                "_clear_legacy_snapshot_collections",
            )
            if token in class_source
        ]
        for forbidden_import in (
            "from gridfs import GridFSBucket",
            "from pymongo import MongoClient",
            "from pymongo.errors import PyMongoError",
            "from bson.binary import Binary",
        ):
            if forbidden_import in source:
                violations.append(forbidden_import)

        self.assertEqual(violations, [])

    def test_local_state_store_does_not_expose_legacy_mongo_settings_loader(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("MongoStateSettings", source)
        self.assertNotIn("load_mongo_state_settings", source)

    def test_production_runtime_paths_do_not_import_local_state_store(self) -> None:
        production_roots = (APP_ROOT, SERVICES_ROOT, TOOLS_ROOT)
        violations: list[str] = []

        for root in production_roots:
            for path in _python_files(root):
                if path == SERVICES_ROOT / "state_store.py":
                    continue
                source = path.read_text(encoding="utf-8")
                if "from fin_ops_platform.services.state_store import" in source:
                    violations.append(_relative(path))

        self.assertEqual(violations, [])

    def test_canonical_fact_tools_use_runtime_application_state_io_boundary(self) -> None:
        violations: list[str] = []

        for path in _python_files(TOOLS_ROOT):
            source = path.read_text(encoding="utf-8")
            if "build_full_snapshot_application" in source:
                violations.append(f"{_relative(path)} uses legacy full snapshot tool runtime builder name")
            for forbidden in (
                '._state_store',
                'getattr(app, "_state_store"',
                "_initialize_runtime_services",
                "app._",
            ):
                if forbidden in source:
                    violations.append(f"{_relative(path)} directly accesses {forbidden}")
            if path != TOOLS_ROOT / "runtime_application.py" and "build_application(" in source:
                violations.append(f"{_relative(path)} directly accesses build_application(")

        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        tool_ports_source = _function_source(_parse(server_path), server_source, "tool_runtime_ports")
        if "state_store=" in tool_ports_source:
            violations.append("Application.tool_runtime_ports exposes the full state_store")
        if "def tool_runtime_state_snapshot" not in server_source:
            violations.append("Application missing dedicated tool runtime state snapshot port")

        runtime_path = TOOLS_ROOT / "runtime_application.py"
        runtime_source = runtime_path.read_text(encoding="utf-8")
        runtime_tree = _parse(runtime_path)
        builder_source = _function_source(runtime_tree, runtime_source, "build_tool_runtime_application")
        bank_runtime_source = _function_source(runtime_tree, runtime_source, "bank_auto_tag_rules_runtime")
        if 'bootstrap_mode="lightweight"' not in builder_source:
            violations.append("tool runtime application builder no longer uses lightweight bootstrap")
        if "build_tool_runtime_application(data_dir)" not in bank_runtime_source:
            violations.append("bank auto-tag restore runtime no longer enters the shared tool runtime builder")
        if "build_application(" in bank_runtime_source:
            violations.append("bank auto-tag restore runtime directly builds the Application")

        self.assertEqual(violations, [])

    def test_application_state_store_etc_file_paths_do_not_use_mongo_gridfs(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = (
            "store_etc_reconciliation_file",
            "read_etc_reconciliation_file",
            "store_etc_invoice_file",
            "read_etc_invoice_file",
            "etc_invoice_file_exists",
            "delete_etc_invoice_file",
        )
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_file_bucket", "MONGO_ONLY_STORAGE_MODE", "_build_gridfs_ref"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_settings_and_oa_cache_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = (
            "load_app_settings",
            "save_app_settings",
            "load_oa_attachment_invoice_cache_entry",
            "save_oa_attachment_invoice_cache_entry",
            "load_oa_sync_state",
            "save_oa_sync_state",
            "load_manual_oa_imports",
            "save_manual_oa_imports",
            "load_oa_sync_state",
            "save_oa_sync_state",
            "save_historical_etc_repair_bundle",
            "load_historical_etc_repair_bundle_metadata",
            "save_historical_etc_repair_parsed_seed",
            "load_historical_etc_repair_parsed_seeds",
            "load_historical_etc_repair_states",
            "save_historical_etc_repair_states",
        )
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")

        self.assertEqual(violations, [])

    def test_turnover_local_tag_selection_does_not_bypass_settings_owner(self) -> None:
        adapter_path = SERVICES_ROOT / "turnover_ledger_write_adapters.py"
        adapter_source = adapter_path.read_text(encoding="utf-8")
        adapter_class_source = _class_source(
            _parse(adapter_path),
            adapter_source,
            "TurnoverLedgerLocalTagSelectionAdapterSet",
        )
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")

        self.assertIn("get_turnover_ledger_tag_selection_state", adapter_class_source)
        self.assertIn("commit_turnover_ledger_tag_selection_update", adapter_class_source)
        self.assertIn("restore_turnover_ledger_tag_selection_state", adapter_class_source)
        self.assertNotIn("_snapshot", adapter_class_source)
        self.assertNotIn("save_app_settings", adapter_class_source)
        self.assertNotIn("_refresh_local_app_settings_snapshot", server_source)
        self.assertNotIn("refresh_app_settings_snapshot", adapter_source)

    def test_application_state_store_etc_states_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = (
            "load_etc_state",
            "save_etc_state",
            "load_etc_reconciliation_state",
            "save_etc_reconciliation_state",
        )
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")
        for forbidden in (
            "BANK_TRANSACTION_CATEGORIES_META_COLLECTION",
            "BANK_TRANSACTION_CATEGORIES_COLLECTION",
            "_load_bank_transaction_categories_detailed_payload",
            "_save_bank_transaction_categories_detailed",
        ):
            if forbidden in source:
                violations.append(f"state_store.py contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_historical_etc_repair_does_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = (
            "save_historical_etc_repair_bundle",
            "load_historical_etc_repair_bundle_metadata",
            "read_historical_etc_repair_bundle",
            "save_historical_etc_repair_parsed_seed",
            "load_historical_etc_repair_parsed_seeds",
            "load_historical_etc_repair_states",
            "save_historical_etc_repair_states",
        )
        violations: list[str] = []

        if "HISTORICAL_ETC_REPAIR_GRIDFS_ID_PREFIX" in class_source:
            violations.append("ApplicationStateStore contains HISTORICAL_ETC_REPAIR_GRIDFS_ID_PREFIX")
        if "_historical_etc_gridfs_id" in class_source:
            violations.append("ApplicationStateStore contains _historical_etc_gridfs_id")

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in (
                "_mongo_database",
                "_mongo_detailed_collections",
                "_mongo_file_bucket",
                "_build_gridfs_ref",
                "MONGO_ONLY_STORAGE_MODE",
            ):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_jobs_and_health_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = (
            "load_background_jobs",
            "save_background_jobs",
            "load_app_health_alerts",
            "save_app_health_alerts",
            "load_manual_oa_imports",
            "save_manual_oa_imports",
        )
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_no_oa_bank_batches_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = ("load_no_oa_bank_batches", "save_no_oa_bank_batches")
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_does_not_expose_oa_pending_payment_relation_snapshot(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")

        self.assertNotIn("load_oa_pending_payment_bank_relations", class_source)
        self.assertNotIn("save_oa_pending_payment_bank_relations", class_source)
        self.assertNotIn('"oa_pending_payment_bank_relations"', class_source)

    def test_application_state_store_tax_imports_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = ("load_tax_certified_imports", "save_tax_certified_imports", "save_tax_offset_plan")
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_workbench_pair_relations_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = ("load_workbench_pair_relations", "save_workbench_pair_relations")
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_workbench_overrides_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = ("save_workbench_overrides", "save_workbench_exception_cases")
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_bank_transaction_categories_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = ("load_bank_transaction_categories", "save_bank_transaction_categories")
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")
        for forbidden in (
            "BANK_TRANSACTION_CATEGORIES_META_COLLECTION",
            "BANK_TRANSACTION_CATEGORIES_COLLECTION",
            "_load_bank_transaction_categories_detailed_payload",
            "_save_bank_transaction_categories_detailed",
        ):
            if forbidden in source:
                violations.append(f"state_store.py contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_turnover_facts_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = (
            "load_turnover_relations",
            "save_turnover_relations",
            "load_turnover_ledger_extras",
            "save_turnover_ledger_extras",
            "load_tax_certified_imports",
            "save_tax_certified_imports",
            "load_pending_invoice_commands",
            "save_pending_invoice_commands",
        )
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")
        for forbidden in (
            "TURNOVER_RELATIONS_META_COLLECTION",
            "TURNOVER_RELATIONS_COLLECTION",
            "TURNOVER_RELATION_AUDIT_LOG_COLLECTION",
            "TURNOVER_LEDGER_EXTRAS_META_COLLECTION",
            "TURNOVER_LEDGER_EXTRAS_COLLECTION",
            "_load_turnover_relations_detailed_payload",
            "_load_turnover_ledger_extras_detailed_payload",
            "_save_turnover_relations_detailed",
            "_save_turnover_ledger_extras_detailed",
        ):
            if forbidden in source:
                violations.append(f"state_store.py contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_tax_read_models_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = (
            "load_tax_offset_read_models",
            "save_tax_offset_read_models",
            "load_background_jobs",
            "save_background_jobs",
            "load_app_health_alerts",
            "save_app_health_alerts",
        )
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")
        for forbidden in (
            "COST_STATISTICS_READ_MODELS_META_COLLECTION",
            "COST_STATISTICS_READ_MODELS_COLLECTION",
            "TAX_OFFSET_READ_MODELS_META_COLLECTION",
            "TAX_OFFSET_READ_MODELS_COLLECTION",
            "_load_" + "cost_statistics_read_models_detailed_payload",
            "_load_tax_offset_read_models_detailed_payload",
            "_save_" + "cost_statistics_read_models_detailed",
            "_save_tax_offset_read_models_detailed",
        ):
            if forbidden in source:
                violations.append(f"state_store.py contains {forbidden}")

        self.assertEqual(violations, [])

    def test_cost_statistics_does_not_retain_full_snapshot_load_or_unconditional_save_io(self) -> None:
        legacy_methods = (
            "load_" + "cost_statistics_read_models",
            "save_" + "cost_statistics_read_models",
        )
        paths = (
            SERVICES_ROOT / "cost_statistics_read_model_repository.py",
            SERVICES_ROOT / "postgres_repositories/read_models.py",
            SERVICES_ROOT / "postgres_state_store.py",
            SERVICES_ROOT / "state_store.py",
            SERVICES_ROOT / "state_store_protocol.py",
        )
        violations: list[str] = []

        for path in paths:
            source = path.read_text(encoding="utf-8")
            for method_name in legacy_methods:
                if f"def {method_name}(" in source:
                    violations.append(f"{path.name} retains {method_name}")
        postgres_state_store_source = (SERVICES_ROOT / "postgres_state_store.py").read_text(encoding="utf-8")
        local_state_store_source = (SERVICES_ROOT / "state_store.py").read_text(encoding="utf-8")
        self.assertNotIn('"cost_statistics_read_models": self.', postgres_state_store_source)
        self.assertNotIn('current_payload["cost_statistics_read_models"]', local_state_store_source)
        self.assertEqual(violations, [])

    def test_cost_statistics_bulk_export_does_not_reload_full_explorer_payload(self) -> None:
        query_source = (SERVICES_ROOT / "cost_statistics_query_service.py").read_text(encoding="utf-8")
        repository_source = (SERVICES_ROOT / "postgres_repositories/read_models.py").read_text(encoding="utf-8")

        self.assertNotIn("def _filtered_entries_from_read_model(", query_source)
        self.assertIn("def get_cost_statistics_export_page(", repository_source)
        self.assertIn("COST_STATISTICS_EXPORT_BATCH_SIZE = 1000", query_source)
        self.assertIn("Workbook(write_only=True)", query_source)
        self.assertIn("normalized_page_size > 1000", repository_source)

        export_start = query_source.index("    def _export_view_from_read_model(")
        export_end = query_source.index("    def _load_export_first_page(", export_start)
        export_source = query_source[export_start:export_end]
        self.assertNotIn("_require_fresh_explorer", export_source)
        self.assertNotIn("_entries_from_explorer_payload", export_source)
        self.assertNotIn("get_cost_statistics_view", export_source)

    def test_cost_statistics_projection_unchanged_check_reads_scope_metadata_only(self) -> None:
        projection_source = (SERVICES_ROOT / "cost_statistics_sql_projection.py").read_text(encoding="utf-8")
        method_start = projection_source.index("    def _unchanged_cost_statistics_scope_result(")
        method_end = projection_source.index("    def _build_explorer_payload(", method_start)
        method_source = projection_source[method_start:method_end]

        self.assertIn("get_cost_statistics_scope_metadata", method_source)
        self.assertNotIn("get_cost_statistics_view", method_source)
        self.assertNotIn("payload", method_source)

    def test_cost_and_tax_sql_projection_owners_are_split_without_legacy_module(self) -> None:
        legacy_path = SERVICES_ROOT / "cost_tax_sql_projection.py"
        cost_source = (SERVICES_ROOT / "cost_statistics_sql_projection.py").read_text(encoding="utf-8")
        tax_source = (SERVICES_ROOT / "tax_offset_sql_projection.py").read_text(encoding="utf-8")
        worker_source = (REPO_ROOT / "backend/src/fin_ops_platform/app/worker.py").read_text(encoding="utf-8")

        self.assertFalse(legacy_path.exists())
        self.assertIn("class CostStatisticsSqlProjectionBuilder", cost_source)
        self.assertNotIn("TaxOffsetSqlProjectionBuilder", cost_source)
        self.assertNotIn("tax_offset_", cost_source)
        self.assertIn("class TaxOffsetSqlProjectionBuilder", tax_source)
        self.assertNotIn("CostStatisticsSqlProjectionBuilder", tax_source)
        self.assertNotIn("cost_statistics_", tax_source)
        self.assertIn("services.cost_statistics_sql_projection import CostStatisticsSqlProjectionBuilder", worker_source)
        self.assertIn("services.tax_offset_sql_projection import TaxOffsetSqlProjectionBuilder", worker_source)
        self.assertNotIn("cost_tax_sql_projection", worker_source)

    def test_application_state_store_workbench_read_models_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = (
            "load_workbench_read_models",
            "save_workbench_read_models",
        )
        violations: list[str] = []

        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_mongo_database", "_mongo_detailed_collections", "MONGO_ONLY_STORAGE_MODE"):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")
        for forbidden in (
            "WORKBENCH_READ_MODELS_META_COLLECTION",
            "WORKBENCH_READ_MODELS_COLLECTION",
            "WORKBENCH_MATCHING_DIRTY_SCOPES_META_COLLECTION",
            "WORKBENCH_MATCHING_DIRTY_SCOPES_COLLECTION",
            "_load_workbench_read_models_detailed_payload",
            "_load_workbench_matching_dirty_scopes_detailed_payload",
            "_save_workbench_read_models_detailed",
            "_save_workbench_matching_dirty_scopes_detailed",
        ):
            if forbidden in source:
                violations.append(f"state_store.py contains {forbidden}")

        self.assertEqual(violations, [])

    def test_application_state_store_import_matching_snapshots_do_not_use_app_mongo(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        violations: list[str] = []

        for method_name in (
            "load",
            "save",
            "store_import_file",
            "read_import_file",
            "delete_import_files",
            "clear_oa_attachment_invoice_cache",
            "import_session_exists",
            "import_file_exists",
            "import_batch_exists",
            "invoice_exists",
            "transaction_exists",
        ):
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in (
                "_mongo_database",
                "_mongo_detailed_collections",
                "_mongo_file_bucket",
                "_build_gridfs_ref",
                "_parse_gridfs_ref",
                "MONGO_ONLY_STORAGE_MODE",
            ):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")
        for forbidden in (
            "GRIDFS_BUCKET_NAME",
            "MONGO_ONLY_STORAGE_MODE",
            "LEGACY_APP_MONGO_COLLECTION",
            "STATE_COLLECTIONS",
            "FILE_METADATA_COLLECTION",
            "IMPORTS_META_COLLECTION",
            "IMPORT_BATCHES_COLLECTION",
            "INVOICES_COLLECTION",
            "BANK_TRANSACTIONS_COLLECTION",
            "FILE_IMPORTS_META_COLLECTION",
            "FILE_IMPORT_SESSIONS_COLLECTION",
            "FILE_IMPORT_FILES_COLLECTION",
            "MATCHING_META_COLLECTION",
            "MATCHING_RUNS_COLLECTION",
            "MATCHING_RESULTS_COLLECTION",
            "_load_detailed_mongo_payload",
            "_load_split_mongo_payload",
            "_load_legacy_mongo_payload",
            "_load_imports_detailed_payload",
            "_load_file_imports_detailed_payload",
            "_load_matching_detailed_payload",
            "_save_imports_detailed",
            "_save_file_imports_detailed",
            "_save_matching_detailed",
            "_save_file_import_metadata",
            "_migrate_legacy_file_refs_to_gridfs",
            "_build_gridfs_ref",
            "_parse_gridfs_ref",
        ):
            if re.search(rf"\b{re.escape(forbidden)}\b", source):
                violations.append(f"state_store.py contains {forbidden}")

        self.assertEqual(violations, [])

    def test_postgres_canonical_fact_methods_do_not_use_runtime_settings_snapshots(self) -> None:
        path = SERVICES_ROOT / "postgres_state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "PostgresStateStore")
        class_tree = ast.parse(class_source)
        violations: list[str] = []

        for forbidden in (
            "STATE_KEY_PREFIX",
            "def _load_snapshot(",
            "def _save_snapshot(",
            "def _load_snapshot_or_empty(",
            "def _load_snapshot_or_table_map(",
        ):
            if forbidden in source:
                violations.append(f"postgres_state_store.py retains runtime settings snapshot API {forbidden}")

        method_names = (
            "load_workbench_pair_relations",
            "save_workbench_pair_relations",
            "load_no_oa_bank_batches",
            "save_no_oa_bank_batches",
            "load_bank_transaction_categories",
            "save_bank_transaction_categories",
            "load_turnover_relations",
            "save_turnover_relations",
            "load_turnover_ledger_extras",
            "save_turnover_ledger_extras",
            "load_tax_certified_imports",
            "save_tax_certified_imports",
            "load_pending_invoice_commands",
            "save_pending_invoice_commands",
            "load_workbench_overrides",
            "save_workbench_overrides",
            "load_workbench_exception_cases",
            "save_workbench_exception_cases",
            "load_tax_offset_read_models",
            "save_tax_offset_read_models",
            "load_etc_state",
            "save_etc_state",
            "load_etc_reconciliation_state",
            "save_etc_reconciliation_state",
        )
        for method_name in method_names:
            method_source = _function_source(class_tree, class_source, method_name)
            for forbidden in ("_load_snapshot(", "_save_snapshot("):
                if forbidden in method_source:
                    violations.append(f"{method_name} contains {forbidden}")

        self.assertEqual(violations, [])

    def test_services_do_not_import_http_auth_boundary_or_parse_cookie_token_headers(self) -> None:
        violations: list[str] = []
        for path in _python_files(SERVICES_ROOT):
            tree = _parse(path)
            modules = _imported_modules(tree)
            if "fin_ops_platform.app.auth" in modules:
                violations.append(f"{_relative(path)} imports app.auth")
            if _parses_http_auth_headers_or_cookies(tree):
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

    def test_invoice_lifecycle_reuses_pending_invoice_read_model_without_live_rebuild(self) -> None:
        source = (SERVICES_ROOT / "invoice_lifecycle_sql_projection.py").read_text(encoding="utf-8")

        self.assertNotIn("SearchPendingSqlProjectionBuilder", source)
        self.assertNotIn("._pending_invoice_rows(", source)
        self.assertNotIn("InputInvoiceUsageQueryService", source)
        self.assertNotIn("OutputInvoiceCollectionQueryService", source)
        self.assertNotIn("ImportNormalizationService", source)
        self.assertIn("list_pending_invoice_lifecycle_source_rows", source)
        self.assertIn("pending_invoice_read_model_not_fresh", source)
        self.assertIn("input_invoice_usage_read_model_not_fresh", source)
        self.assertIn("output_invoice_collection_read_model_not_fresh", source)

    def test_server_no_longer_owns_import_confirm_processors(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        service_source = (SERVICES_ROOT / "import_processing_service.py").read_text(encoding="utf-8")
        worker_source = (SERVICES_ROOT / "runtime_worker_handlers.py").read_text(encoding="utf-8")
        forbidden_server_snippets = {
            "def _execute_file_import_confirm_job",
            "def _execute_general_import_confirm",
            "def _file_import_job_label",
            "def _process_etc_invoice_import_confirm_job",
            "def _process_file_import_confirm_job",
            "def _process_general_import_confirm_job",
            "def _process_tax_certified_import_confirm_job",
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
        self.assertNotIn("general_import.confirm", service_source)
        self.assertNotIn("general_import.confirm", worker_source)
        self.assertNotIn("execute_general_import_confirm", service_source)
        self.assertNotIn("process_general_import_confirm_job", service_source)

    def test_server_no_longer_exposes_legacy_json_import_write_routes(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")

        for endpoint in ('"/imports/preview"', '"/imports/confirm"', "'/imports/preview'", "'/imports/confirm'"):
            self.assertNotIn(endpoint, server_source)

    def test_bank_transaction_import_frontend_uses_file_session_api_only(self) -> None:
        page_source = (WEB_SRC_ROOT / "pages" / "imports" / "ImportBankTransactionsPage.tsx").read_text(encoding="utf-8")
        api_source = (WEB_SRC_ROOT / "features" / "imports" / "api.ts").read_text(encoding="utf-8")
        runtime_files = [
            WEB_SRC_ROOT / "pages" / "imports" / "ImportBankTransactionsPage.tsx",
            WEB_SRC_ROOT / "components" / "imports" / "ImportWorkflowPage.tsx",
            WEB_SRC_ROOT / "features" / "imports" / "api.ts",
            WEB_SRC_ROOT / "features" / "imports" / "importRoutes.ts",
            WEB_SRC_ROOT / "contexts" / "ImportWorkflowDraftContext.tsx",
        ]
        violations: list[str] = []

        if '<ImportWorkflowPage mode="bank_transaction" />' not in page_source:
            violations.append("bank transaction import page no longer uses the shared bank_transaction workflow mode")
        for endpoint in ('"/imports/files/preview"', '"/imports/files/confirm"', "/imports/files/sessions/"):
            if endpoint not in api_source:
                violations.append(f"imports API is missing file/session endpoint {endpoint}")
        for path in runtime_files:
            source = path.read_text(encoding="utf-8")
            for legacy_endpoint in ('"/imports/preview"', '"/imports/confirm"', "'/imports/preview'", "'/imports/confirm'"):
                if legacy_endpoint in source:
                    violations.append(f"{_relative(path)} references legacy JSON import endpoint {legacy_endpoint}")

        self.assertEqual(violations, [])

    def test_server_route_owner_inventory_stays_registered(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_owners = {
            "routes_bank_details.py": {
                "module": "fin_ops_platform.app.routes_bank_details",
                "class": "BankDetailsApiRoutes",
                "server_markers": ("def _bank_details_routes", "_bank_details_routes()."),
            },
            "routes_batch_accounting.py": {
                "module": "fin_ops_platform.app.routes_batch_accounting",
                "class": "BatchAccountingApiRoutes",
                "server_markers": ("def _batch_accounting_routes", "_batch_accounting_routes()."),
            },
            "routes_bank_flow_rule_batches.py": {
                "module": "fin_ops_platform.app.routes_bank_flow_rule_batches",
                "class": "BankFlowRuleBatchApiRoutes",
                "server_markers": ("def _bank_flow_rule_batch_routes", "_bank_flow_rule_batch_routes()."),
            },
            "routes_cost_statistics.py": {
                "module": "fin_ops_platform.app.routes_cost_statistics",
                "class": "CostStatisticsApiRoutes",
                "server_markers": ("def _cost_statistics_routes", "_cost_statistics_routes()."),
            },
            "routes_etc.py": {
                "module": "fin_ops_platform.app.routes_etc",
                "class": "EtcBusinessBatchApiRoutes",
                "server_markers": ("def _etc_business_routes", "_etc_business_routes()."),
            },
            "routes_etc_import.py": {
                "module": "fin_ops_platform.app.routes_etc_import",
                "class": "EtcImportApiRoutes",
                "server_markers": ("def _etc_import_routes", "_etc_import_routes()."),
            },
            "routes_etc_invoices.py": {
                "module": "fin_ops_platform.app.routes_etc_invoices",
                "class": "EtcInvoiceApiRoutes",
                "server_markers": ("def _etc_invoice_routes", "_etc_invoice_routes()."),
            },
            "routes_etc_reconciliation.py": {
                "module": "fin_ops_platform.app.routes_etc_reconciliation",
                "class": "EtcReconciliationTaskApiRoutes",
                "server_markers": ("def _etc_reconciliation_routes", "_etc_reconciliation_routes()."),
            },
            "routes_input_invoice_usage_oa_reverse.py": {
                "module": "fin_ops_platform.app.routes_input_invoice_usage_oa_reverse",
                "class": "InputInvoiceUsageOaReverseApiRoutes",
                "server_markers": ("def _input_invoice_usage_oa_reverse_routes", "_input_invoice_usage_oa_reverse_routes().route("),
            },
            "routes_input_invoice_usage.py": {
                "module": "fin_ops_platform.app.routes_input_invoice_usage",
                "class": "InputInvoiceUsageApiRoutes",
                "server_markers": ("def _input_invoice_usage_routes", "_input_invoice_usage_routes().route("),
            },
            "routes_no_oa_bank_batches.py": {
                "module": "fin_ops_platform.app.routes_no_oa_bank_batches",
                "class": "NoOaBankBatchApiRoutes",
                "server_markers": ("def _no_oa_bank_batch_routes", "_no_oa_bank_batch_routes()."),
            },
            "routes_oa_pending_payments.py": {
                "module": "fin_ops_platform.app.routes_oa_pending_payments",
                "class": "OaPendingPaymentApiRoutes",
                "server_markers": ("def _oa_pending_payment_routes", "_oa_pending_payment_routes()."),
            },
            "routes_output_invoice_collections.py": {
                "module": "fin_ops_platform.app.routes_output_invoice_collections",
                "class": "OutputInvoiceCollectionApiRoutes",
                "server_markers": ("def _output_invoice_collection_routes", "_output_invoice_collection_routes().route("),
            },
            "routes_pending_invoices.py": {
                "module": "fin_ops_platform.app.routes_pending_invoices",
                "class": "PendingInvoiceApiRoutes",
                "server_markers": ("def _pending_invoice_routes", "_pending_invoice_routes()."),
            },
            "routes_settings.py": {
                "module": "fin_ops_platform.app.routes_settings",
                "class": "SettingsApiRoutes",
                "server_markers": ("def _settings_routes", "_settings_routes().route("),
            },
            "routes_tax.py": {
                "module": "fin_ops_platform.app.routes_tax",
                "class": "TaxApiRoutes",
                "server_markers": ("def _tax_offset_routes", "_tax_offset_routes().", "_tax_api_routes"),
            },
            "routes_turnover_ledger.py": {
                "module": "fin_ops_platform.app.routes_turnover_ledger",
                "class": "TurnoverLedgerApiRoutes",
                "server_markers": ("_turnover_ledger_api_routes = TurnoverLedgerApiRoutes(", "_turnover_ledger_api_routes."),
            },
            "routes_workbench.py": {
                "module": "fin_ops_platform.app.routes_workbench",
                "class": "WorkbenchReadApiRoutes",
                "server_markers": ("def _workbench_read_routes", "_workbench_read_routes()."),
            },
            "routes_workbench_actions.py": {
                "module": "fin_ops_platform.app.routes_workbench_actions",
                "class": "WorkbenchActionApiRoutes",
                "server_markers": (
                    "_workbench_action_api_routes = WorkbenchActionApiRoutes(",
                    "_workbench_action_api_routes.",
                ),
            },
        }
        discovered_route_modules = {path.name for path in APP_ROOT.glob("routes_*.py")}
        violations: list[str] = []

        missing_from_inventory = sorted(discovered_route_modules - set(route_owners))
        stale_inventory = sorted(set(route_owners) - discovered_route_modules)
        if missing_from_inventory:
            violations.append(f"routes_*.py files missing route owner inventory: {missing_from_inventory}")
        if stale_inventory:
            violations.append(f"route owner inventory references missing files: {stale_inventory}")

        for filename, owner in sorted(route_owners.items()):
            route_path = APP_ROOT / filename
            if not route_path.exists():
                continue
            route_source = route_path.read_text(encoding="utf-8")
            route_tree = _parse(route_path)
            route_class = str(owner["class"])
            module = str(owner["module"])
            if not _class_source(route_tree, route_source, route_class):
                violations.append(f"{filename} does not define {route_class}")
            if not _imports_name_from_module(server_tree, module=module, name=route_class):
                violations.append(f"server.py does not import {route_class} from {module}")
            for marker in owner["server_markers"]:
                if marker not in server_source:
                    violations.append(f"server.py route owner {route_class} is missing marker {marker}")

        self.assertEqual(violations, [])

    def test_workbench_exception_preview_mapping_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        if not route_class:
            violations.append("modern Workbench action route owner is missing")
        for marker in (
            "def exception_preview",
            "WorkbenchExceptionApplicationService",
            "workbench_row_not_found",
            "invalid_workbench_exception_preview_request",
        ):
            if marker not in route_class:
                violations.append(f"exception preview route owner is missing marker {marker}")

        handler_source = _function_source(server_tree, server_source, "_handle_api_workbench_exception_preview")
        if "_workbench_action_api_routes.exception_preview(payload)" not in handler_source:
            violations.append("server.py exception preview wrapper does not delegate to the route owner")
        for forbidden in (
            "_workbench_exception_application_service.preview",
            "workbench_row_not_found",
            "invalid_workbench_exception_preview_request",
        ):
            if forbidden in handler_source:
                violations.append(f"server.py exception preview wrapper still owns {forbidden}")

        self.assertEqual(violations, [])

    def test_pending_invoice_read_export_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        route_path = APP_ROOT / "routes_pending_invoices.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "PendingInvoiceApiRoutes")
        for marker in (
            "def route",
            "/api/pending-invoices/rows",
            "/api/pending-invoices/filter-options",
            "/api/pending-invoices/invoice-candidates",
            "/api/pending-invoices/export",
            "def _export_read",
            "export_response",
        ):
            if marker not in route_class:
                violations.append(f"pending invoice route owner is missing marker {marker}")

        if "_pending_invoice_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("server.py does not delegate pending invoice route dispatch to the route owner")
        if "def _pending_invoice_export_response" not in server_source:
            violations.append("server.py no longer provides the pending invoice export platform response port")

        for forbidden in (
            "def _handle_api_pending_invoice_rows",
            "def _handle_api_pending_invoice_filter_options",
            "def _handle_api_pending_invoice_candidates",
            "def _handle_api_pending_invoice_batch_candidates",
            "def _handle_api_pending_invoice_relation_detail",
            "def _handle_api_pending_invoice_bank_transaction_detail",
            "def _handle_api_pending_invoice_invoice_detail",
            "def _handle_api_pending_invoice_oa_detail",
            "def _handle_api_pending_invoice_export_preview",
            "def _handle_api_pending_invoice_export",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still owns pending invoice read/export callback {forbidden}")

        self.assertEqual(violations, [])

    def test_pending_invoice_write_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        route_path = APP_ROOT / "routes_pending_invoices.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "PendingInvoiceApiRoutes")
        for marker in (
            "/api/pending-invoices/rules",
            "/api/pending-invoices/income-statuses",
            "/api/pending-invoices/attach-existing-invoices",
            "resolve_write_session",
            "persist_on_pending_error=True",
            "persist_on_success=True",
            "persist_on_unexpected=True",
        ):
            if marker not in route_class:
                violations.append(f"pending invoice write route owner is missing marker {marker}")

        route_factory = _function_source(_parse(server_path), server_source, "_pending_invoice_routes")
        for marker in (
            "resolve_write_session=self._resolve_pending_invoice_write_session",
            "persist_state=self._persist_state",
        ):
            if marker not in route_factory:
                violations.append(f"pending invoice route factory is missing port {marker}")

        for forbidden in (
            "def _handle_api_pending_invoice_rules",
            "def _handle_api_pending_invoice_rules_update",
            "def _handle_api_pending_invoice_attach_existing_preview",
            "def _handle_api_pending_invoice_attach_existing_batch_preview",
            "def _handle_api_pending_invoice_attach_existing_confirm",
            "def _handle_api_pending_invoice_attach_existing_batch_confirm",
            "def _handle_api_pending_invoice_income_status_update",
            "def _handle_api_pending_invoice_income_statuses_update",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still owns pending invoice write callback {forbidden}")

        self.assertEqual(violations, [])

    def test_tax_offset_read_plan_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        route_path = APP_ROOT / "routes_tax.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "TaxApiRoutes")
        for marker in (
            "def route",
            "/api/tax-offset/summary",
            "/api/tax-offset/calculate",
            "/api/tax-offset/plans",
            "/api/tax-offset/certified-import/jobs/",
            "/api/tax-offset/certified-imports",
            "resolve_mutation_session",
            "certified_import_records_provider",
        ):
            if marker not in route_class:
                violations.append(f"tax route owner is missing marker {marker}")

        route_factory = _function_source(_parse(server_path), server_source, "_configure_tax_offset_application_services")
        for marker in (
            "resolve_read_session=self._resolve_tax_offset_read_session",
            "resolve_mutation_session=self._resolve_tax_offset_mutation_session",
            "load_json_body=self._load_json_body",
            "actor_id_provider=self._tax_offset_actor_id",
            "certified_import_records_provider=self._tax_certified_import_application_service.records_payload",
        ):
            if marker not in route_factory:
                violations.append(f"tax route factory is missing port {marker}")

        if "_tax_offset_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("server.py does not delegate tax offset dispatch to the route owner")
        for forbidden in (
            "def _handle_api_tax_offset(",
            "def _handle_api_tax_offset_summary",
            "def _handle_api_tax_certified_import_job",
            "def _handle_api_tax_certified_imports",
            "def _handle_api_tax_offset_calculate",
            "def _handle_api_tax_offset_plan_save",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still owns migrated tax callback {forbidden}")
        self.assertEqual(violations, [])

    def test_tax_certified_import_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        route_path = APP_ROOT / "routes_tax.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "TaxApiRoutes")
        for marker in (
            "/api/tax-offset/certified-import/preview",
            "/api/tax-offset/certified-import/confirm",
            "UploadedCertifiedImportFile",
            "load_multipart_body",
            "certified_import_preview_provider",
            "enqueue_import_job",
            "serialize_import_job",
            "execute_tax_certified_import_confirm",
            'idempotency_key=f"tax_certified_import.confirm:{session_id}"',
        ):
            if marker not in route_class:
                violations.append(f"tax certified import route owner is missing marker {marker}")

        route_factory = _function_source(_parse(server_path), server_source, "_configure_tax_offset_application_services")
        for marker in (
            "load_multipart_body=self._load_multipart_body",
            "certified_import_preview_provider=self._tax_certified_import_application_service.preview_payload",
            "import_job_processing_enabled=self._import_job_processing_enabled",
            "enqueue_import_job=self._enqueue_import_process_job",
            "serialize_import_job=self._serialize_import_job",
            "execute_tax_certified_import_confirm=self._import_processing_service.execute_tax_certified_import_confirm",
        ):
            if marker not in route_factory:
                violations.append(f"tax route factory is missing certified import port {marker}")

        for forbidden in (
            "def _handle_api_tax_certified_import_preview",
            "def _handle_api_tax_certified_import_confirm",
            "def _execute_tax_certified_import_confirm",
            "UploadedCertifiedImportFile",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still owns migrated tax certified import surface {forbidden}")

        self.assertEqual(violations, [])

    def test_workbench_exception_apply_mapping_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def exception_apply",
            "write_facade_provider",
            "apply_exception",
            "confirmed_by",
            "exception_apply",
        ):
            if marker not in route_class:
                violations.append(f"exception apply route owner is missing marker {marker}")

        handler_source = _function_source(server_tree, server_source, "_handle_api_workbench_exception_apply")
        if "_workbench_action_api_routes.exception_apply(payload, request_id=request_id)" not in handler_source:
            violations.append("server.py exception apply wrapper does not delegate to the route owner")
        if "_workbench_write_freshness_guard(payload)" not in handler_source:
            violations.append("server.py exception apply wrapper no longer preserves the freshness guard")
        if "_workbench_write_response(result)" not in handler_source:
            violations.append("server.py exception apply wrapper no longer preserves write response mapping")
        for forbidden in (
            "_workbench_write_facade().apply_exception",
            "payload.get(\"confirmed_by\")",
            "action_name=\"exception_apply\"",
        ):
            if forbidden in handler_source:
                violations.append(f"server.py exception apply wrapper still owns {forbidden}")

        self.assertEqual(violations, [])

    def test_workbench_confirm_link_preview_mapping_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def confirm_link_preview",
            "preview_confirm_link",
            "invalid_confirm_link_preview_request",
            "KeyError",
            "TypeError",
            "ValueError",
        ):
            if marker not in route_class:
                violations.append(f"confirm-link preview route owner is missing marker {marker}")

        handler_source = _function_source(server_tree, server_source, "_handle_api_workbench_confirm_link_preview")
        if "_workbench_action_api_routes.confirm_link_preview(payload)" not in handler_source:
            violations.append("server.py confirm-link preview wrapper does not delegate to the route owner")
        if "_json_response(status, preview)" not in handler_source:
            violations.append("server.py confirm-link preview wrapper no longer serializes the owner result")
        for forbidden in (
            "_workbench_write_facade().preview_confirm_link",
            "invalid_confirm_link_preview_request",
            "except (KeyError, TypeError, ValueError)",
        ):
            if forbidden in handler_source:
                violations.append(f"server.py confirm-link preview wrapper still owns {forbidden}")

        self.assertEqual(violations, [])

    def test_workbench_confirm_link_submit_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def confirm_link",
            ".confirm_link(",
            "request_id=request_id",
            "actor_id=actor_id",
            "tenant_id=tenant_id",
        ):
            if marker not in route_class:
                violations.append(f"confirm-link submit route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_confirm_link")
        for marker in (
            "_workbench_write_freshness_guard(payload)",
            "_workbench_write_auth_context(headers)",
            "_handle_live_workbench_confirm_link(",
            "request_id=request_id",
            "actor_id=actor_id",
            "tenant_id=tenant_id",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py confirm-link wrapper no longer preserves marker {marker}")

        live_source = _function_source(server_tree, server_source, "_handle_live_workbench_confirm_link")
        if "_workbench_action_api_routes.confirm_link(" not in live_source:
            violations.append("server.py confirm-link live handler does not delegate to the route owner")
        if "_workbench_write_response(result)" not in live_source:
            violations.append("server.py confirm-link live handler no longer preserves write response mapping")
        if "_workbench_write_facade().confirm_link" in live_source:
            violations.append("server.py confirm-link live handler still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_mark_exception_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def mark_exception",
            ".mark_exception(",
        ):
            if marker not in route_class:
                violations.append(f"mark-exception route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_mark_exception")
        for marker in (
            "_workbench_write_freshness_guard(payload)",
            "_handle_live_workbench_mark_exception(payload)",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py mark-exception wrapper no longer preserves marker {marker}")

        live_source = _function_source(server_tree, server_source, "_handle_live_workbench_mark_exception")
        if "_workbench_action_api_routes.mark_exception(payload)" not in live_source:
            violations.append("server.py mark-exception live handler does not delegate to the route owner")
        if "_workbench_write_response(result)" not in live_source:
            violations.append("server.py mark-exception live handler no longer preserves write response mapping")
        if "_workbench_write_facade().mark_exception" in live_source:
            violations.append("server.py mark-exception live handler still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_cancel_link_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def cancel_link",
            ".cancel_link(",
            "request_id=request_id",
            "actor_id=actor_id",
            "tenant_id=tenant_id",
        ):
            if marker not in route_class:
                violations.append(f"cancel-link route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_cancel_link")
        for marker in (
            "_workbench_write_freshness_guard(payload)",
            "_workbench_write_auth_context(headers)",
            "_handle_live_workbench_cancel_link(",
            "request_id=request_id",
            "actor_id=actor_id",
            "tenant_id=tenant_id",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py cancel-link wrapper no longer preserves marker {marker}")

        live_source = _function_source(server_tree, server_source, "_handle_live_workbench_cancel_link")
        if "_workbench_action_api_routes.cancel_link(" not in live_source:
            violations.append("server.py cancel-link live handler does not delegate to the route owner")
        if "_workbench_write_response(result)" not in live_source:
            violations.append("server.py cancel-link live handler no longer preserves write response mapping")
        if "_workbench_write_facade().cancel_link" in live_source:
            violations.append("server.py cancel-link live handler still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_withdraw_link_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def withdraw_link",
            ".withdraw_link(",
            "request_id=request_id",
            "actor_id=actor_id",
            "tenant_id=tenant_id",
        ):
            if marker not in route_class:
                violations.append(f"withdraw-link route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_withdraw_link")
        for marker in (
            "_workbench_write_freshness_guard(payload)",
            "_workbench_write_auth_context(headers)",
            "_workbench_action_api_routes.withdraw_link(",
            "request_id=request_id",
            "actor_id=actor_id",
            "tenant_id=tenant_id",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py withdraw-link wrapper no longer preserves marker {marker}")
        if "_workbench_write_response(result)" not in wrapper_source:
            violations.append("server.py withdraw-link wrapper no longer preserves write response mapping")
        if "_workbench_write_facade().withdraw_link" in wrapper_source:
            violations.append("server.py withdraw-link wrapper still calls the write facade directly")

        live_source = _function_source(server_tree, server_source, "_handle_live_workbench_withdraw_link")
        if "_workbench_action_api_routes.withdraw_link(payload, request_id=request_id)" not in live_source:
            violations.append("server.py withdraw-link live handler does not delegate to the route owner")
        if "_workbench_write_response(result)" not in live_source:
            violations.append("server.py withdraw-link live handler no longer preserves write response mapping")
        if "_workbench_write_facade().withdraw_link" in live_source:
            violations.append("server.py withdraw-link live handler still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_withdraw_link_preview_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def withdraw_link_preview",
            ".preview_withdraw_link(",
        ):
            if marker not in route_class:
                violations.append(f"withdraw-link preview route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_withdraw_link_preview")
        for marker in (
            "_load_json_body(body)",
            "_workbench_action_api_routes.withdraw_link_preview(payload)",
            "_workbench_write_response(result)",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py withdraw-link preview wrapper no longer preserves marker {marker}")
        if "_workbench_write_facade().preview_withdraw_link" in wrapper_source:
            violations.append("server.py withdraw-link preview wrapper still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_cash_special_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def confirm_cash_pass_through",
            ".confirm_cash_pass_through(",
            "def confirm_cash_ticket_purchase",
            ".confirm_cash_ticket_purchase(",
            "def cancel_cash_special",
            ".cancel_cash_special(",
            "request_id=request_id",
        ):
            if marker not in route_class:
                violations.append(f"cash special route owner is missing marker {marker}")

        handler_expectations = {
            "_handle_api_workbench_confirm_cash_pass_through": "confirm_cash_pass_through",
            "_handle_api_workbench_confirm_cash_ticket_purchase": "confirm_cash_ticket_purchase",
            "_handle_api_workbench_cancel_cash_special": "cancel_cash_special",
        }
        for handler_name, route_method in handler_expectations.items():
            handler_source = _function_source(server_tree, server_source, handler_name)
            for marker in (
                "_load_json_body(body)",
                "_workbench_write_freshness_guard(payload)",
                f"_workbench_action_api_routes.{route_method}(payload, request_id=request_id)",
                "_workbench_write_response(result)",
            ):
                if marker not in handler_source:
                    violations.append(f"{handler_name} no longer preserves marker {marker}")
            if f"_workbench_write_facade().{route_method}" in handler_source:
                violations.append(f"{handler_name} still calls WorkbenchWriteFacade.{route_method} directly")

        self.assertEqual(violations, [])

    def test_workbench_update_bank_exception_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def update_bank_exception",
            ".update_bank_exception(",
        ):
            if marker not in route_class:
                violations.append(f"update-bank-exception route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_update_bank_exception")
        for marker in (
            "_load_json_body(body)",
            "_workbench_write_freshness_guard(payload)",
            "_workbench_action_api_routes.update_bank_exception(payload)",
            "_workbench_write_response(result)",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py update-bank-exception wrapper no longer preserves marker {marker}")
        if "_workbench_write_facade().update_bank_exception" in wrapper_source:
            violations.append("server.py update-bank-exception wrapper still calls the write facade directly")

        live_source = _function_source(server_tree, server_source, "_handle_live_workbench_update_bank_exception")
        if "_workbench_action_api_routes.update_bank_exception(payload)" not in live_source:
            violations.append("server.py update-bank-exception live handler does not delegate to the route owner")
        if "_workbench_write_response(result)" not in live_source:
            violations.append("server.py update-bank-exception live handler no longer preserves write response mapping")
        if "_workbench_write_facade().update_bank_exception" in live_source:
            violations.append("server.py update-bank-exception live handler still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_oa_bank_exception_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def oa_bank_exception",
            ".oa_bank_exception(",
        ):
            if marker not in route_class:
                violations.append(f"OA-bank exception route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_oa_bank_exception")
        for marker in (
            "_load_json_body(body)",
            "_workbench_write_freshness_guard(payload)",
            "_workbench_action_api_routes.oa_bank_exception(payload)",
            "_workbench_write_response(result)",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py OA-bank exception wrapper no longer preserves marker {marker}")
        if "_workbench_write_facade().oa_bank_exception" in wrapper_source:
            violations.append("server.py OA-bank exception wrapper still calls the write facade directly")

        live_source = _function_source(server_tree, server_source, "_handle_live_workbench_oa_bank_exception")
        if "_workbench_action_api_routes.oa_bank_exception(payload)" not in live_source:
            violations.append("server.py OA-bank exception live handler does not delegate to the route owner")
        if "_workbench_write_response(result)" not in live_source:
            violations.append("server.py OA-bank exception live handler no longer preserves write response mapping")
        if "_workbench_write_facade().oa_bank_exception" in live_source:
            violations.append("server.py OA-bank exception live handler still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_personal_advance_repayment_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def confirm_personal_advance_repayment",
            ".confirm_personal_advance_repayment(",
            "request_id=request_id",
        ):
            if marker not in route_class:
                violations.append(f"personal advance repayment route owner is missing marker {marker}")

        wrapper_source = _function_source(
            server_tree,
            server_source,
            "_handle_api_workbench_confirm_personal_advance_repayment",
        )
        for marker in (
            "_load_json_body(body)",
            "_workbench_write_freshness_guard(payload)",
            "_workbench_action_api_routes.confirm_personal_advance_repayment(payload, request_id=request_id)",
            "_workbench_write_response(result)",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py personal advance repayment wrapper no longer preserves marker {marker}")
        if "_workbench_write_facade().confirm_personal_advance_repayment" in wrapper_source:
            violations.append("server.py personal advance repayment wrapper still calls the write facade directly")

        live_source = _function_source(server_tree, server_source, "_handle_live_workbench_confirm_personal_advance_repayment")
        if "_workbench_action_api_routes.confirm_personal_advance_repayment(payload, request_id=request_id)" not in live_source:
            violations.append("server.py personal advance repayment live handler does not delegate to the route owner")
        if "_workbench_write_response(result)" not in live_source:
            violations.append("server.py personal advance repayment live handler no longer preserves write response mapping")
        if "_workbench_write_facade().confirm_personal_advance_repayment" in live_source:
            violations.append("server.py personal advance repayment live handler still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_cancel_exception_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def cancel_exception",
            ".cancel_exception(",
        ):
            if marker not in route_class:
                violations.append(f"cancel-exception route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_cancel_exception")
        for marker in (
            "_load_json_body(body)",
            "_workbench_write_freshness_guard(payload)",
            "_handle_live_workbench_cancel_exception(payload)",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py cancel-exception wrapper no longer preserves marker {marker}")
        if "_live_workbench_service.has_rows_for_month(month)" in wrapper_source:
            violations.append("server.py cancel-exception wrapper still contains the no-op live service branch")
        if "_workbench_write_facade().cancel_exception" in wrapper_source:
            violations.append("server.py cancel-exception wrapper still calls the write facade directly")

        live_source = _function_source(server_tree, server_source, "_handle_live_workbench_cancel_exception")
        if "_workbench_action_api_routes.cancel_exception(payload)" not in live_source:
            violations.append("server.py cancel-exception live handler does not delegate to the route owner")
        if "_workbench_write_response(result)" not in live_source:
            violations.append("server.py cancel-exception live handler no longer preserves write response mapping")
        if "_workbench_write_facade().cancel_exception" in live_source:
            violations.append("server.py cancel-exception live handler still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_ignore_row_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def ignore_row",
            ".ignore_row(",
        ):
            if marker not in route_class:
                violations.append(f"ignore-row route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_ignore_row")
        for marker in (
            "_load_json_body(body)",
            "_workbench_write_freshness_guard(payload)",
            "_handle_workbench_ignore_row_payload(payload)",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py ignore-row wrapper no longer preserves marker {marker}")
        if "_workbench_write_facade().ignore_row" in wrapper_source:
            violations.append("server.py ignore-row wrapper still calls the write facade directly")

        helper_source = _function_source(server_tree, server_source, "_handle_workbench_ignore_row_payload")
        if "_workbench_action_api_routes.ignore_row(payload)" not in helper_source:
            violations.append("server.py ignore-row helper does not delegate to the route owner")
        if "_workbench_write_response(result)" not in helper_source:
            violations.append("server.py ignore-row helper no longer preserves write response mapping")
        if "_workbench_write_facade().ignore_row" in helper_source:
            violations.append("server.py ignore-row helper still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_workbench_unignore_row_delegation_is_owned_by_action_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "WorkbenchActionApiRoutes")
        for marker in (
            "def unignore_row",
            ".unignore_row(",
        ):
            if marker not in route_class:
                violations.append(f"unignore-row route owner is missing marker {marker}")

        wrapper_source = _function_source(server_tree, server_source, "_handle_api_workbench_unignore_row")
        for marker in (
            "_load_json_body(body)",
            "_workbench_write_freshness_guard(payload)",
            "_handle_workbench_unignore_row_payload(payload)",
        ):
            if marker not in wrapper_source:
                violations.append(f"server.py unignore-row wrapper no longer preserves marker {marker}")
        if "_workbench_write_facade().unignore_row" in wrapper_source:
            violations.append("server.py unignore-row wrapper still calls the write facade directly")

        helper_source = _function_source(server_tree, server_source, "_handle_workbench_unignore_row_payload")
        if "_workbench_action_api_routes.unignore_row(payload)" not in helper_source:
            violations.append("server.py unignore-row helper does not delegate to the route owner")
        if "_workbench_write_response(result)" not in helper_source:
            violations.append("server.py unignore-row helper no longer preserves write response mapping")
        if "_workbench_write_facade().unignore_row" in helper_source:
            violations.append("server.py unignore-row helper still calls the write facade directly")

        self.assertEqual(violations, [])

    def test_legacy_workbench_http_endpoints_stay_deleted(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_legacy_workbench_actions.py"
        prototype_path = REPO_ROOT / "web/prototypes/reconciliation-workbench-v2.html"
        violations: list[str] = []

        if route_path.exists():
            violations.append("routes_legacy_workbench_actions.py must stay deleted")
        if prototype_path.exists():
            violations.append("legacy reconciliation workbench prototype must stay deleted")
        if _imports_name_from_module(
            server_tree,
            module="fin_ops_platform.app.routes_legacy_workbench_actions",
            name="LegacyWorkbenchActionRoutes",
        ):
            violations.append("server.py still imports LegacyWorkbenchActionRoutes")
        for forbidden in (
            "LegacyWorkbenchActionRoutes",
            "self._legacy_workbench_action_routes = LegacyWorkbenchActionRoutes(",
            'route_path == "/workbench"',
            'route_path == "/workbench/prototype"',
            'return self._handle_legacy_workbench_action("confirm", body)',
            'return self._handle_legacy_workbench_action("difference", body)',
            'return self._handle_legacy_workbench_action("exception", body)',
            'return self._handle_legacy_workbench_action("offline", body)',
            'return self._handle_legacy_workbench_action("offset", body)',
            '"/workbench"',
            '"/workbench/prototype"',
            '"/workbench/actions/confirm"',
            '"/workbench/actions/difference"',
            '"/workbench/actions/exception"',
            '"/workbench/actions/offline"',
            '"/workbench/actions/offset"',
        ):
            if forbidden in server_source:
                violations.append(f"server.py still exposes legacy Workbench action marker {forbidden}")

        for old_handler in (
            "_handle_workbench_confirm",
            "_handle_workbench_difference",
            "_handle_workbench_exception",
            "_handle_workbench_offline",
            "_handle_workbench_offset",
            "_handle_legacy_workbench_exception_via_application",
            "_handle_legacy_workbench_action",
            "_handle_workbench",
            "_handle_workbench_prototype",
        ):
            if _function_source(server_tree, server_source, old_handler):
                violations.append(f"server.py still owns legacy Workbench action handler {old_handler}")

        self.assertEqual(violations, [])

    def test_legacy_workbench_api_routes_and_action_service_stay_deleted(self) -> None:
        route_path = APP_ROOT / "routes_workbench.py"
        service_path = SERVICES_ROOT / "workbench_action_service.py"
        server_path = APP_ROOT / "server.py"
        route_source = route_path.read_text(encoding="utf-8")
        server_source = server_path.read_text(encoding="utf-8")
        violations: list[str] = []

        if service_path.exists():
            violations.append("legacy workbench_action_service.py must stay deleted")
        for forbidden in (
            "WorkbenchApiRoutes",
            "_workbench_api_routes",
            "def get_workbench(",
            "WorkbenchActionService",
            "workbench_action_service",
            "_workbench_action_service",
            "_action_service",
        ):
            if forbidden in route_source:
                violations.append(f"routes_workbench.py resurrected legacy surface {forbidden}")
            if forbidden in server_source:
                violations.append(f"Application runtime still references {forbidden}")

        self.assertEqual(violations, [])

    def test_bank_details_disconnected_write_uow_stays_deleted(self) -> None:
        legacy_path = SERVICES_ROOT / "bankdetail_write_uow.py"
        violations: list[str] = []

        if legacy_path.exists():
            violations.append("disconnected bankdetail_write_uow.py must stay deleted")

        for path in _python_files(APP_ROOT, SERVICES_ROOT, TOOLS_ROOT):
            source = path.read_text(encoding="utf-8")
            for forbidden in (
                "BankdetailWriteUnitOfWork",
                "fin_ops_platform.services.bankdetail_write_uow",
            ):
                if forbidden in source:
                    violations.append(f"{_relative(path)} still references {forbidden}")

        owner_markers = {
            SERVICES_ROOT / "bank_details_application_service.py": "class BankDetailsApplicationService",
            SERVICES_ROOT / "bank_detail_category_side_effects.py": "class BankDetailCategoryMutationSideEffectPort",
            APP_ROOT / "routes_bank_details.py": "class BankDetailsApiRoutes",
        }
        for path, marker in owner_markers.items():
            if marker not in path.read_text(encoding="utf-8"):
                violations.append(f"{_relative(path)} is missing production owner marker {marker}")

        self.assertEqual(violations, [])

    def test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        routes_source = (APP_ROOT / "routes_bank_details.py").read_text(encoding="utf-8")
        settings_routes_source = (APP_ROOT / "routes_settings.py").read_text(encoding="utf-8")
        service_source = (SERVICES_ROOT / "bank_details_application_service.py").read_text(encoding="utf-8")
        app_settings_source = (SERVICES_ROOT / "app_settings_service.py").read_text(encoding="utf-8")

        violations: list[str] = []

        for forbidden in (
            "def _finalize_bank_auto_tag_rules_update",
            "def _bank_detail_refresh_scope_keys_from_auto_tag_rules_payload",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still owns legacy bank auto-tag write helper {forbidden}")

        for removed_handler in (
            "_handle_api_bank_details_auto_tag_rules_update",
            "_handle_api_bank_details_auto_tag_rules_file_replacement",
            "_handle_api_bank_details_auto_tag_rules_reapply",
            "_handle_api_bank_detail_category_confirmation",
            "_handle_api_bank_detail_category_confirmation_delete",
            "_handle_api_bank_detail_category_assignment",
            "_handle_api_bank_detail_category_assignment_delete",
            "_handle_api_bank_transaction_categories",
        ):
            if f"def {removed_handler}(" in server_source:
                violations.append(f"server.py still defines migrated bank details write handler {removed_handler}")

        for route_marker in (
            'route_path == "/api/bank-details/auto-tag-rules"',
            'route_path == "/api/bank-details/auto-tag-rules/reapply"',
            'route_path == "/api/bank-details/auto-tag-rules/file-replacement"',
            'route_path == "/api/bank-details/transactions/categories"',
            "manual_bank_transaction_category_disabled",
            'confirmation_suffix = "/category-confirmation"',
            'assignment_suffix = "/category-assignment"',
            "load_json_body=",
            "default_auto_tag_rules_source_provider=",
            "update_auto_tag_rules(payload, session=session)",
            "reapply_auto_tag_rules(session=session)",
            "replace_auto_tag_rules_from_file_source(source, session=session)",
            "confirm_category(transaction_id, payload, session=session)",
            "revoke_category_confirmation(transaction_id, session=session)",
            "assign_category(transaction_id, payload, session=session)",
            "clear_category_assignment(transaction_id, session=session)",
        ):
            if route_marker not in server_source + routes_source:
                violations.append(f"bank details write route owner is missing marker {route_marker}")

        for forbidden in (
            "update_bank_auto_tag_rules(",
            "replace_bank_auto_tag_rules_from_file_source(",
            "_execute_derived_data_lifecycle_event(",
            "_enqueue_bank_detail_read_model_refreshes(",
            "_enqueue_turnover_ledger_read_model_refreshes(",
        ):
            if forbidden in routes_source:
                violations.append(f"routes_bank_details.py bypasses application service via {forbidden}")

        required_service_snippets = {
            "self._app_settings_service.update_bank_auto_tag_rules(",
            "self._app_settings_service.replace_bank_auto_tag_rules_from_file_source(",
            "def finalize_auto_tag_rules_update",
            "self._execute_derived_data_lifecycle_event(",
            "self._enqueue_read_model_refreshes(priority_scope_keys",
            "self._bank_transaction_category_service.confirm_auto_category(",
            "self._bank_transaction_category_service.assign_manual_category(",
            "self._persist_category_mutation(",
        }
        for snippet in sorted(required_service_snippets):
            if snippet not in service_source:
                violations.append(f"BankDetailsApplicationService is missing boundary behavior {snippet}")

        if "bank_transaction_tags_write_forbidden" not in settings_routes_source:
            violations.append("settings route owner no longer blocks legacy bank_transaction_tags writes")
        if "def update_bank_auto_tag_rules" not in app_settings_source:
            violations.append("AppSettingsService no longer owns bank auto-tag settings persistence")

        for path, source in {
            "routes_bank_details.py": routes_source,
            "bank_details_application_service.py": service_source,
            "app_settings_service.py": app_settings_source,
        }.items():
            direct_job_writes = _sql_write_table_references(source)
            if direct_job_writes:
                violations.append(f"{path} writes job queue tables directly: {direct_job_writes}")

        self.assertEqual(violations, [])

    def test_bank_details_read_export_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        routes_source = (APP_ROOT / "routes_bank_details.py").read_text(encoding="utf-8")
        violations: list[str] = []

        for removed_handler in (
            "_handle_api_bank_details_accounts",
            "_handle_api_bank_details_auto_tag_rules",
            "_handle_api_bank_details_transactions",
            "_handle_api_bank_details_transactions_export",
        ):
            if f"def {removed_handler}(" in server_source:
                violations.append(f"server.py still defines migrated bank details read/export handler {removed_handler}")

        for marker in (
            "def route(",
            'route_path == "/api/bank-details/accounts"',
            'route_path == "/api/bank-details/transactions"',
            'route_path == "/api/bank-details/transactions/export"',
            'route_path == "/api/bank-details/auto-tag-rules"',
            "resolve_read_session=",
            "export_response=",
            "self._bank_details_routes().route(method, route_path, query, body, headers)",
        ):
            if marker not in server_source + routes_source:
                violations.append(f"bank details route owner is missing marker {marker}")

        self.assertEqual(violations, [])

    def test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        service_source = (SERVICES_ROOT / "bank_details_application_service.py").read_text(encoding="utf-8")
        service_tree = _parse(SERVICES_ROOT / "bank_details_application_service.py")
        service_class = _class_source(service_tree, service_source, "BankDetailsApplicationService")
        violations: list[str] = []

        removed_application_helpers = {
            "_bank_detail_scope_keys_for_range",
            "_bank_detail_scope_summary",
            "_with_bank_detail_auto_tag_rule_freshness",
            "_bank_detail_accounts_refreshing_payload",
            "_bank_detail_transactions_refreshing_payload",
            "_with_bank_detail_tag_dictionary",
            "_enqueue_bank_detail_read_model_refreshes_unless_refreshing",
            "_enqueue_bank_detail_read_model_refreshes",
            "_bank_detail_redis_cache_key",
            "_get_bank_detail_cached_payload",
            "_set_bank_detail_cached_payload",
            "_delete_bank_detail_redis_cache",
            "_bank_detail_available_month_scope_keys",
            "_derived_lifecycle_bank_detail_executor",
        }
        for helper_name in sorted(removed_application_helpers):
            if _function_source(server_tree, server_source, helper_name):
                violations.append(f"server.py still owns removed bank detail read/cache helper {helper_name}")

        required_service_helpers = {
            "_scope_keys_for_range",
            "_scope_summary",
            "_with_auto_tag_rule_freshness",
            "_accounts_refreshing_payload",
            "_transactions_refreshing_payload",
            "_with_tag_dictionary",
            "_enqueue_read_model_refreshes_unless_refreshing",
            "_redis_cache_key",
            "_get_cached_payload",
            "_set_cached_payload",
        }
        for helper_name in sorted(required_service_helpers):
            if not _function_source(service_tree, service_source, helper_name):
                violations.append(f"BankDetailsApplicationService is missing bank detail read/cache owner {helper_name}")
        for forbidden_snippet in (
            "import_service:",
            "_import_service",
            "bank_details_service:",
            "_bank_details_service",
            "BankDetailsService",
            "requires_sql_read_model_runtime",
            ".list_accounts(",
            ".list_transactions(",
            ".auto_category_input_row(",
        ):
            if forbidden_snippet in service_class:
                violations.append(f"BankDetailsApplicationService still owns legacy bank detail I/O fallback {forbidden_snippet}")

        producer_source = (SERVICES_ROOT / "bank_detail_read_model_refresh_producer.py").read_text(encoding="utf-8")
        producer_tree = _parse(SERVICES_ROOT / "bank_detail_read_model_refresh_producer.py")
        producer_class = _class_source(producer_tree, producer_source, "BankDetailReadModelRefreshProducer")
        for snippet in (
            "def enqueue(",
            "refresh_gateway = self._refresh_gateway_provider()",
            'refresh_gateway.enqueue_many("bank_detail"',
            'publish_wakeup("bank_detail_read_model_refresh"',
        ):
            if snippet not in producer_class:
                violations.append(f"bank detail refresh producer is missing gateway/wakeup behavior {snippet}")
        direct_job_writes = _sql_write_table_references(producer_class)
        if direct_job_writes:
            violations.append(f"bank detail refresh producer writes job queue tables directly: {direct_job_writes}")

        turnover_producer_path = SERVICES_ROOT / "turnover_ledger_read_model_refresh_producer.py"
        turnover_producer_source = turnover_producer_path.read_text(encoding="utf-8")
        turnover_producer_tree = _parse(turnover_producer_path)
        turnover_producer_class = _class_source(
            turnover_producer_tree,
            turnover_producer_source,
            "TurnoverLedgerReadModelRefreshProducer",
        )
        for snippet in (
            "def enqueue(",
            "refresh_gateway = self._refresh_gateway_provider()",
            'refresh_gateway.enqueue_many("turnover_ledger"',
        ):
            if snippet not in turnover_producer_class:
                violations.append(f"turnover ledger refresh producer is missing boundary behavior {snippet}")
        for forbidden in (
            "def clear_best_effort(",
            "clear_turnover_ledger_rows",
            "read_repository_provider",
        ):
            if forbidden in turnover_producer_class:
                violations.append(f"turnover ledger refresh producer still exposes direct clear I/O {forbidden}")
        direct_job_writes = _sql_write_table_references(turnover_producer_class)
        if direct_job_writes:
            violations.append(f"turnover ledger refresh producer writes job queue tables directly: {direct_job_writes}")

        factory_source = _function_source(server_tree, server_source, "_bank_details_application_service")
        if _function_source(server_tree, server_source, "_enqueue_turnover_ledger_read_model_refreshes"):
            violations.append("server.py still owns removed turnover ledger refresh enqueue helper")
        if _function_source(server_tree, server_source, "_clear_turnover_ledger_read_model_best_effort"):
            violations.append("server.py still owns removed turnover ledger read model clear helper")
        if _function_source(server_tree, server_source, "_after_turnover_relation_mutation"):
            violations.append("server.py still owns removed turnover relation mutation invalidation helper")
        if _function_source(server_tree, server_source, "_turnover_ledger_relation_mutation_invalidation_adapter"):
            violations.append("server.py still owns removed turnover relation mutation invalidation adapter factory")
        if _function_source(server_tree, server_source, "_latest_bank_detail_auto_category_suggestion"):
            violations.append("server.py still owns removed bank detail suggestion provider callback")
        if _function_source(server_tree, server_source, "_bank_detail_available_month_scope_keys"):
            violations.append("server.py still owns removed bank detail available-month scope helper")
        if _function_source(server_tree, server_source, "_derived_lifecycle_bank_detail_executor"):
            violations.append("server.py still owns removed bank detail derived lifecycle executor")
        for removed_helper_name in sorted(removed_application_helpers):
            if removed_helper_name in factory_source:
                violations.append(f"BankDetailsApplicationService factory still injects removed helper {removed_helper_name}")
        for retained_callback in (
            "_bank_detail_auto_category_suggestion_provider",
            "_bank_detail_read_model_refresh_producer",
            "_bank_detail_available_month_scope_provider",
            "_bank_account_balance_read_model_refresh_producer",
            "_turnover_ledger_read_model_refresh_producer",
        ):
            if retained_callback not in factory_source:
                violations.append(f"BankDetailsApplicationService factory no longer classifies retained callback {retained_callback}")
        if "BankDetailAutoCategorySuggestionProvider(" not in factory_source:
            violations.append("BankDetailsApplicationService factory does not build the explicit bank detail suggestion provider")
        if "BankDetailAvailableMonthScopeProvider(" not in server_source:
            violations.append("server.py does not build the explicit bank detail available-month scope provider")
        if 'getattr(self, "_bank_detail_available_month_scope_keys"' in server_source:
            violations.append("server.py still allows the removed bank detail available-month scope helper")
        if "BankDetailDerivedLifecycleExecutor(" not in server_source:
            violations.append("server.py does not build the explicit bank detail derived lifecycle executor")
        if '"bank_detail_read_model": self._bank_detail_derived_lifecycle_executor().execute' not in server_source:
            violations.append("derived lifecycle registry does not use the explicit bank detail executor")
        removed_side_effect_callback = "_after_bank_category_confirmation_mutation"
        if _function_source(server_tree, server_source, removed_side_effect_callback):
            violations.append(f"server.py still owns removed bank detail category side-effect callback {removed_side_effect_callback}")
        if removed_side_effect_callback in factory_source:
            violations.append("BankDetailsApplicationService factory still injects removed category side-effect callback")
        if "BankDetailCategoryMutationSideEffectPort(" not in factory_source:
            violations.append("BankDetailsApplicationService factory does not build the explicit category side-effect port")
        if "category_mutation_side_effects=category_mutation_side_effects" not in factory_source:
            violations.append("BankDetailsApplicationService factory does not inject the explicit category side-effect port")

        side_effect_source = (SERVICES_ROOT / "bank_detail_category_side_effects.py").read_text(encoding="utf-8")
        side_effect_tree = _parse(SERVICES_ROOT / "bank_detail_category_side_effects.py")
        side_effect_class = _class_source(side_effect_tree, side_effect_source, "BankDetailCategoryMutationSideEffectPort")
        for snippet in (
            "def after_mutation(",
            'reason="bank_detail_category_confirmation_changed"',
            "entity_type=\"bank_transaction_category_confirmation\"",
            "self._enqueue_bank_detail_refresh(",
            "self._enqueue_turnover_ledger_refresh(",
            "self._invalidate_workbench_after_category_mutation(",
            "self._audit_service.record_action(",
        ):
            if snippet not in side_effect_class:
                violations.append(f"category side-effect port is missing behavior {snippet}")
        direct_job_writes = _sql_write_table_references(side_effect_class)
        if direct_job_writes:
            violations.append(f"category side-effect port writes job queue tables directly: {direct_job_writes}")

        self.assertEqual(violations, [])

    def test_workbench_relation_derived_lifecycle_uses_explicit_executor_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        executor_path = SERVICES_ROOT / "workbench_relation_derived_lifecycle_executor.py"
        executor_source = executor_path.read_text(encoding="utf-8") if executor_path.exists() else ""
        violations: list[str] = []

        removed_helper = "_derived_lifecycle_workbench_relation_read_model_executor"
        if _function_source(server_tree, server_source, removed_helper):
            violations.append(f"server.py still owns removed workbench relation lifecycle executor {removed_helper}")
        if "WorkbenchRelationDerivedLifecycleExecutor(" not in server_source:
            violations.append("server.py does not build the explicit workbench relation lifecycle executor")
        if '"workbench_relation_read_model": self._workbench_relation_derived_lifecycle_executor().execute' not in server_source:
            violations.append("derived lifecycle registry does not use the explicit workbench relation executor")
        if "class WorkbenchRelationDerivedLifecycleExecutor" not in executor_source:
            violations.append("workbench relation lifecycle executor service is missing")
        for snippet in (
            "def execute(",
            'reason=str(domain_plan.get("reason") or "derived_lifecycle_workbench_relation")',
            '"deleted_counts": {"workbench_relation_read_models": 0}',
            '"enqueued_jobs": ["workbench_relation.read_model.refresh"] if enqueued else []',
        ):
            if snippet not in executor_source:
                violations.append(f"workbench relation lifecycle executor is missing behavior {snippet}")

        self.assertEqual(violations, [])

    def test_invoice_lifecycle_derived_lifecycle_uses_explicit_executor_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        executor_path = SERVICES_ROOT / "invoice_lifecycle_derived_lifecycle_executor.py"
        executor_source = executor_path.read_text(encoding="utf-8") if executor_path.exists() else ""
        violations: list[str] = []

        removed_helper = "_derived_lifecycle_invoice_lifecycle_executor"
        if _function_source(server_tree, server_source, removed_helper):
            violations.append(f"server.py still owns removed invoice lifecycle executor {removed_helper}")
        if "InvoiceLifecycleDerivedLifecycleExecutor(" not in server_source:
            violations.append("server.py does not build the explicit invoice lifecycle executor")
        if '"invoice_lifecycle_read_model": self._invoice_lifecycle_derived_lifecycle_executor().execute' not in server_source:
            violations.append("derived lifecycle registry does not use the explicit invoice lifecycle executor")
        if "class InvoiceLifecycleDerivedLifecycleExecutor" not in executor_source:
            violations.append("invoice lifecycle executor service is missing")
        for snippet in (
            "def execute(",
            'reason=str(domain_plan.get("reason") or "derived_lifecycle_invoice_lifecycle")',
            '"deleted_counts": {"invoice_lifecycle_read_models": 0}',
            '"enqueued_jobs": ["invoice_lifecycle.read_model.refresh"] if enqueued else []',
        ):
            if snippet not in executor_source:
                violations.append(f"invoice lifecycle executor is missing behavior {snippet}")

        self.assertEqual(violations, [])

    def test_cost_statistics_derived_lifecycle_uses_explicit_executor_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        executor_path = SERVICES_ROOT / "cost_statistics_derived_lifecycle_executor.py"
        executor_source = executor_path.read_text(encoding="utf-8") if executor_path.exists() else ""
        violations: list[str] = []

        removed_helper = "_derived_lifecycle_cost_statistics_executor"
        if _function_source(server_tree, server_source, removed_helper):
            violations.append(f"server.py still owns removed cost statistics lifecycle executor {removed_helper}")
        if "CostStatisticsDerivedLifecycleExecutor(" not in server_source:
            violations.append("server.py does not build the explicit cost statistics lifecycle executor")
        if '"cost_statistics_read_model": self._cost_statistics_derived_lifecycle_executor().execute' not in server_source:
            violations.append("derived lifecycle registry does not use the explicit cost statistics executor")
        if "class CostStatisticsDerivedLifecycleExecutor" not in executor_source:
            violations.append("cost statistics lifecycle executor service is missing")
        for snippet in (
            "def execute(",
            'reason = str(domain_plan.get("reason") or "derived_lifecycle_cost_statistics")',
            "runtime_service: CostStatisticsRuntimeService",
            '"deleted_counts": {"cost_statistics_read_models": len(deleted_scope_keys)}',
            '"enqueued_jobs": ["cost_statistics.read_model.refresh"] if enqueued else []',
            '"cost_statistics.read_model.refresh"',
        ):
            if snippet not in executor_source:
                violations.append(f"cost statistics lifecycle executor is missing behavior {snippet}")
        if '"cost_statistics_cache_warmup"' in executor_source:
            violations.append("cost statistics lifecycle executor still reports legacy cache warmup fallback")

        self.assertEqual(violations, [])

    def test_cost_statistics_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        route_path = APP_ROOT / "routes_cost_statistics.py"
        server_source = server_path.read_text(encoding="utf-8")
        route_source = route_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        violations: list[str] = []

        if "def route(" not in route_source:
            violations.append("CostStatisticsApiRoutes does not own route dispatch")
        for snippet in (
            'route_path == "/api/cost-statistics/explorer"',
            'route_path == "/api/cost-statistics/export-preview"',
            'route_path == "/api/cost-statistics/export"',
            'route_path.startswith("/api/cost-statistics/transactions/")',
            "CostStatisticsReadModelNotFreshError",
            "self._optional_bool_parser(",
        ):
            if snippet not in route_source:
                violations.append(f"CostStatisticsApiRoutes is missing route-owner behavior {snippet}")
        for forbidden_snippet in (
            'route_path == "/api/cost-statistics"',
            'route_path.startswith("/api/cost-statistics/projects/")',
            "self._cost_statistics_service.get_project_statistics",
            "self._cost_statistics_service.get_transaction_detail",
            "self._cost_statistics_service.get_export_preview",
            "self._cost_statistics_service.export_view",
        ):
            if forbidden_snippet in route_source:
                violations.append(f"CostStatisticsApiRoutes still calls legacy service path {forbidden_snippet}")
        for removed_handler in (
            "_handle_api_cost_statistics",
            "_handle_api_cost_statistics_explorer",
            "_handle_api_cost_statistics_project",
            "_handle_api_cost_statistics_export",
            "_handle_api_cost_statistics_export_preview",
            "_handle_api_cost_statistics_transaction",
        ):
            if _function_source(server_tree, server_source, removed_handler):
                violations.append(f"server.py still owns cost statistics route callback {removed_handler}")
        if "self._cost_statistics_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("server.py does not delegate cost statistics routing to the route owner")

        self.assertEqual(violations, [])

    def test_relation_cost_refresh_has_transactional_delta_and_publish_convergence_owners(self) -> None:
        uow_source = (SERVICES_ROOT / "workbench_uow.py").read_text(encoding="utf-8")
        facade_source = (SERVICES_ROOT / "workbench_write_facade.py").read_text(encoding="utf-8")
        relation_repository_source = (
            SERVICES_ROOT / "postgres_repositories" / "workbench_relation.py"
        ).read_text(encoding="utf-8")
        matching_orchestrator_source = (SERVICES_ROOT / "workbench_matching_orchestrator.py").read_text(
            encoding="utf-8"
        )
        lifecycle_source = (SERVICES_ROOT / "derived_data_lifecycle_service.py").read_text(encoding="utf-8")
        turnover_write_source = (SERVICES_ROOT / "turnover_ledger_write_facade.py").read_text(encoding="utf-8")
        workbench_refresh_source = (SERVICES_ROOT / "workbench_read_model_refresh.py").read_text(
            encoding="utf-8"
        )
        cost_refresh_source = (SERVICES_ROOT / "cost_statistics_read_model_refresh.py").read_text(
            encoding="utf-8"
        )
        cost_projection_source = (SERVICES_ROOT / "cost_statistics_sql_projection.py").read_text(
            encoding="utf-8"
        )
        page_source = (REPO_ROOT / "web/src/pages/CostStatisticsPage.tsx").read_text(encoding="utf-8")
        violations: list[str] = []

        uow_refresh_targets = uow_source[
            uow_source.index("def _refresh_targets_for(") : uow_source.index("def _extend_refresh_targets(")
        ]
        facade_start = facade_source.index("    def _relation_downstream_scope_types(")
        facade_downstream = facade_source[
            facade_start : facade_source.index("    def _relation_pending_invoice_scope_keys(", facade_start)
        ]
        for required in (
            'scope_type="cost_statistics"',
            'reason="cost_statistics_relation_delta"',
            "_active_cost_statistics_scope_keys(scope_keys)",
            'metadata["relation_deltas"]',
            'if action_name == "confirm_link"',
            'if action_name in {"withdraw_link", "cancel_link"}',
        ):
            if required not in uow_source:
                violations.append(f"relation UoW is missing bounded cost delta contract {required}")
        if '"cost_statistics"' in facade_downstream:
            violations.append("relation facade downstream discovery still owns cost statistics fan-out")
        for forbidden in (
            "CostStatisticsRuntimeService",
            "_workbench_relation_downstream_scope_types",
            '"cost_statistics"',
        ):
            if forbidden in relation_repository_source:
                violations.append(f"relation repository still owns removed cost path {forbidden}")
        for required in (
            '"scope_type": "cost_statistics"',
            '"reason": "cost_statistics_relation_delta"',
            "_active_cost_statistics_scope_keys(normalized_months)",
        ):
            if required not in turnover_write_source:
                violations.append(f"turnover relation writer is missing bounded cost delta contract {required}")
        if re.search(
            r'"scope_type":\s*"cost_statistics"[\s\S]{0,180}"reason":\s*"turnover_relation_changed"',
            turnover_write_source,
        ):
            violations.append("turnover relation writer still emits the removed full cost refresh reason")
        formal_command_start = matching_orchestrator_source.index("class WorkbenchFormalRelationCommand:")
        formal_command_end = matching_orchestrator_source.index("class WorkbenchMatchingOrchestrator:")
        if '"cost_statistics"' in matching_orchestrator_source[formal_command_start:formal_command_end]:
            violations.append("formal relation command still advertises removed direct cost fan-out")
        domain_registry_start = lifecycle_source.index("    _EVENT_DOMAINS:")
        job_registry_start = lifecycle_source.index("    _EVENT_JOBS:")
        for event_name in (
            "pair_relation_changed",
            "pending_invoice_manual_invoice_confirmed",
            "pending_invoice_attach_existing_invoice_confirmed",
            "no_oa_bank_batch_changed",
            "bank_flow_rule_batch_changed",
            "batch_accounting_relation_changed",
            "turnover_relation_changed",
        ):
            domain_start = lifecycle_source.index(f'        "{event_name}": (', domain_registry_start)
            domain_end = lifecycle_source.index("        ),", domain_start)
            if '"cost_statistics_read_model"' in lifecycle_source[domain_start:domain_end]:
                violations.append(f"relation lifecycle event {event_name} still directly invalidates cost statistics")
            job_marker = f'        "{event_name}": ('
            job_start = lifecycle_source.find(job_marker, job_registry_start)
            if job_start >= 0:
                job_end = lifecycle_source.index("        ),", job_start)
                if '"cost_statistics.read_model.refresh"' in lifecycle_source[job_start:job_end]:
                    violations.append(f"relation lifecycle event {event_name} still advertises a direct cost job")
        if workbench_refresh_source.count('reason="workbench_shard_published"') != 1:
            violations.append("Workbench successful publish does not retain one convergence refresh")
        for required in (
            '"cost_statistics",',
            "if payload.get(\"published\") is not True:",
            'trace_id=event.trace_id or event.event_id',
        ):
            if required not in workbench_refresh_source:
                violations.append(f"Workbench publish-derived convergence owner is missing {required}")
        for required in (
            'relation_deltas=_event_relation_deltas(event)',
            "if relation_deltas:",
            'relation_deltas=relation_deltas',
        ):
            if required not in cost_refresh_source:
                violations.append(f"Cost delta handler is missing explicit relation-state I/O {required}")
        if "from app.workbench_pair_relations" in cost_projection_source:
            violations.append("Cost projection still reads the relation module canonical table directly")
        for required in (
            "rebuild_cost_statistics_relation_delta",
            "_active_workbench_rows_by_ids",
            "publish_cost_statistics_relation_delta",
            "_normalize_relation_deltas",
        ):
            if required not in cost_projection_source:
                violations.append(f"Cost projection is missing isolated relation delta behavior {required}")
        for required in (
            "tenant_id=event.tenant_id",
            "priority=priority",
            "trace_id=event.trace_id",
        ):
            if required not in cost_refresh_source:
                violations.append(f"Cost shard/parent causal metadata propagation is missing {required}")

        handler_start = page_source.index("  const handleWorkbenchRelationMutation = useCallback")
        handler_end = page_source.index("  const handleManualRefresh", handler_start)
        handler_source = page_source[handler_start:handler_end]
        for required in (
            "waitForOperationFreshness(",
            "currentCostStatisticsScopeKey",
            "setIsRelationRefreshWaiting(true)",
            "setLoadedExplorer(null)",
        ):
            if required not in handler_source:
                violations.append(f"Cost relation barrier is missing {required}")
        if "handleDomainMutation" in handler_source:
            violations.append("Cost relation barrier still delegates to the generic App Status refresh path")

        self.assertEqual(violations, [])

    def test_cost_statistics_query_runtime_do_not_keep_legacy_live_fallbacks(self) -> None:
        query_path = SERVICES_ROOT / "cost_statistics_query_service.py"
        runtime_path = SERVICES_ROOT / "cost_statistics_runtime_service.py"
        service_path = SERVICES_ROOT / "cost_statistics_service.py"
        read_model_service_path = SERVICES_ROOT / "cost_statistics_read_model_service.py"
        service_test_path = REPO_ROOT / "tests" / "test_cost_statistics_service.py"
        read_model_service_test_path = REPO_ROOT / "tests" / "test_cost_statistics_read_model_service.py"
        removed_export_service_path = SERVICES_ROOT / "project_detail_export_service.py"
        server_path = APP_ROOT / "server.py"
        route_path = APP_ROOT / "routes_cost_statistics.py"
        repository_port_path = SERVICES_ROOT / "cost_statistics_read_model_repository.py"
        postgres_repository_path = SERVICES_ROOT / "postgres_repositories/read_models.py"
        projection_path = SERVICES_ROOT / "cost_statistics_sql_projection.py"
        worker_path = APP_ROOT / "worker.py"
        job_registry_path = SERVICES_ROOT / "app_status_job_registry.py"
        domain_registry_path = SERVICES_ROOT / "app_status_domain_registry.py"
        runtime_policy_path = SERVICES_ROOT / "runtime_state_policy.py"
        frontend_job_types_path = REPO_ROOT / "web/src/features/backgroundJobs/types.ts"
        query_source = query_path.read_text(encoding="utf-8")
        runtime_source = runtime_path.read_text(encoding="utf-8")
        server_source = server_path.read_text(encoding="utf-8")
        route_source = route_path.read_text(encoding="utf-8")
        repository_port_source = repository_port_path.read_text(encoding="utf-8")
        postgres_repository_source = postgres_repository_path.read_text(encoding="utf-8")
        projection_source = projection_path.read_text(encoding="utf-8")
        worker_source = worker_path.read_text(encoding="utf-8")
        registry_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (job_registry_path, domain_registry_path, runtime_policy_path, frontend_job_types_path)
        )
        violations: list[str] = []

        if service_path.exists():
            violations.append("legacy cost_statistics_service.py still exists")
        if service_test_path.exists():
            violations.append("legacy test_cost_statistics_service.py still exists")
        if read_model_service_path.exists():
            violations.append("legacy cost_statistics_read_model_service.py still exists")
        if read_model_service_test_path.exists():
            violations.append("legacy test_cost_statistics_read_model_service.py still exists")

        for forbidden in (
            "_cost_statistics_service",
            "self._read_model_service",
            "read_model_service:",
            "_cached_month_entries",
            "upsert_cost_statistics_explorer_read_model",
            "schedule_cache_warmup",
            "requires_sql_read_model_runtime",
            "def get_month_statistics(",
            "def get_project_statistics(",
            "get_cost_statistics_view",
            "def _refreshing_explorer_payload(",
            "def _refreshing_month_payload(",
        ):
            if forbidden in query_source:
                violations.append(f"CostStatisticsQueryService still has legacy fallback input {forbidden}")
        for forbidden in (
            "explorer_loader",
            "_explorer_loader",
            "_upsert_read_model",
            "_cache_fresh_explorer_payload",
            "worker_cost_statistics_read_model_refresh",
            "build_fresh_cache_envelope",
            "source_versions_provider",
            "expected_source_versions",
            "delete_redis_cache",
            "read_model_service",
            "persist_read_models",
            "_persist_read_models",
            "cost_statistics_cache_warmup",
            "schedule_warmup",
        ):
            if forbidden in runtime_source:
                violations.append(f"CostStatisticsRuntimeService still has legacy writer path {forbidden}")
        for forbidden in (
            'route_path == "/api/cost-statistics"',
            'route_path.startswith("/api/cost-statistics/projects/")',
            "def handle_month(",
            "def handle_project(",
        ):
            if forbidden in route_source:
                violations.append(f"CostStatisticsApiRoutes still has removed HTTP contract {forbidden}")
        for source_name, source in (
            ("repository port", repository_port_source),
            ("PostgreSQL repository", postgres_repository_source),
        ):
            if "def get_cost_statistics_view(" in source:
                violations.append(f"{source_name} still exposes removed full-view loader")
        if "redis_helper" in projection_source:
            violations.append("CostStatisticsSqlProjectionBuilder still accepts or uses Redis")
        cost_worker_start = worker_source.index("    if args.enable_cost_statistics_read_model_refresh:")
        cost_worker_end = worker_source.index("    if args.enable_tax_offset_read_model_refresh:", cost_worker_start)
        if "redis_helper" in worker_source[cost_worker_start:cost_worker_end]:
            violations.append("cost statistics worker assembly still injects Redis into projection")
        if "cost_statistics_cache_warmup" in registry_sources:
            violations.append("runtime/App Health/frontend registries still expose removed cost warmup job")
        if removed_export_service_path.exists():
            violations.append("project_detail_export_service.py still exists")
        for forbidden in (
            "CostStatisticsService(",
            "self._cost_statistics_service =",
            "grouped_workbench_loader=self._build_api_workbench_payload",
            "raw_workbench_loader=self._build_raw_workbench_payload",
            "_cost_statistics_expected_source_versions",
            "_cost_statistics_source_versions",
            "_cost_statistics_workbench_source_versions",
            "_cost_statistics_bank_detail_source_versions",
            "_delete_cost_statistics_redis_cache",
            "_cost_statistics_read_model_service",
            "_persist_cost_statistics_read_models_best_effort",
            "tag_selection_provider=getattr(self, \"_app_settings_service\", None)",
            "cost_statistics_cache_warmup",
            "_schedule_cost_statistics_cache_warmup",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still wires legacy CostStatisticsService via {forbidden}")
        for path in _python_files(SOURCE_ROOT):
            source = path.read_text(encoding="utf-8")
            for forbidden in (
                "CostStatisticsService",
                "cost_statistics_service",
                "_cost_statistics_service",
                "CostStatisticsReadModelService",
                "cost_statistics_read_model_service",
                "_cost_statistics_read_model_service",
            ):
                if forbidden in source:
                    violations.append(f"{_relative(path)} still references removed {forbidden}")

        self.assertEqual(violations, [])

    def test_turnover_ledger_read_export_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        route_path = APP_ROOT / "routes_turnover_ledger.py"
        removed_read_facade_path = APP_ROOT / "turnover_ledger_read_facade.py"
        server_source = server_path.read_text(encoding="utf-8")
        route_source = route_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        violations: list[str] = []

        if removed_read_facade_path.exists():
            violations.append("turnover_ledger_read_facade.py must stay deleted")
        for forbidden in (
            "TurnoverLedgerReadFacade",
            "_turnover_ledger_read_facade",
            "turnover_ledger_read_facade",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still references removed turnover read facade {forbidden}")
        if "def route(" not in route_source:
            violations.append("TurnoverLedgerApiRoutes does not own read/export route dispatch")
        for snippet in (
            'route_path == "/api/turnover-ledger"',
            'route_path == "/api/turnover-ledger/export-preview"',
            'route_path == "/api/turnover-ledger/export"',
            'route_path == "/api/turnover-ledger/tag-selection"',
            'route_path.startswith("/api/turnover-ledger/relations/")',
            "def handle_list_route(",
            "def handle_export_preview_route(",
            "def handle_export_route(",
            "def handle_relation_route(",
            "def handle_relation_extra_route(",
            "def handle_tag_selection_route(",
            "def handle_tag_selection_update_route(",
            "def handle_bank_row_tags_batch_route(",
            "def handle_relation_extra_update_route(",
            "def handle_confirm_relation_route(",
            "def handle_closure_confirm_route(",
            "def handle_closure_withdraw_route(",
            "def handle_withdraw_relation_route(",
        ):
            if snippet not in route_source:
                violations.append(f"TurnoverLedgerApiRoutes is missing read/export route-owner behavior {snippet}")
        for removed_handler in (
            "_handle_api_turnover_ledger",
            "_handle_api_turnover_ledger_export_preview",
            "_handle_api_turnover_ledger_export",
            "_handle_api_turnover_ledger_relation",
            "_handle_api_turnover_ledger_relation_extra",
            "_handle_api_turnover_ledger_tag_selection",
            "_handle_api_turnover_ledger_tag_selection_update",
            "_handle_api_turnover_ledger_bank_row_tags_batch",
            "_handle_api_turnover_ledger_relation_extra_update",
            "_handle_api_turnover_ledger_confirm",
            "_handle_api_turnover_ledger_closure_confirm",
            "_handle_api_turnover_ledger_closure_withdraw",
            "_handle_api_turnover_ledger_withdraw",
        ):
            if _function_source(server_tree, server_source, removed_handler):
                violations.append(f"server.py still owns turnover ledger migrated route callback {removed_handler}")
        if "self._turnover_ledger_api_routes.route(method, route_path, query, body, headers)" not in server_source:
            violations.append("server.py does not delegate turnover ledger routing to the route owner")
        for snippet in (
            "json_response=self._json_response",
            "export_response=self._turnover_ledger_export_response",
            "tag_selection_provider=self._app_settings_service.get_turnover_ledger_tag_selection_payload",
            "mutation_session_resolver=self._turnover_mutation_session",
            "tenant_id_provider=tenant_id_for_session",
            "tag_selection_write_boundary_provider=self._turnover_ledger_tag_selection_request_boundary_facade",
            "bank_row_tags_request_boundary_provider=self._turnover_ledger_bank_row_tags_request_boundary_facade",
            "relation_extra_request_boundary_provider=self._turnover_ledger_relation_extra_request_boundary_facade",
            "relation_extra_tenant_id_provider=self._workbench_reconciliation_tenant_id",
            "confirm_relation_request_boundary_provider=self._turnover_ledger_confirm_request_boundary_facade",
            "closure_request_boundary_provider=lambda: self._turnover_ledger_closure_request_boundary_facade()",
            "withdraw_request_boundary_provider=self._turnover_ledger_withdraw_request_boundary_facade",
            "write_precondition_error_payload=self._turnover_write_precondition_error_payload",
        ):
            if snippet not in server_source:
                violations.append(f"server.py does not inject turnover ledger route port {snippet}")

        self.assertEqual(violations, [])

    def test_tax_offset_derived_lifecycle_uses_explicit_executor_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        executor_path = SERVICES_ROOT / "tax_offset_derived_lifecycle_executor.py"
        executor_source = executor_path.read_text(encoding="utf-8") if executor_path.exists() else ""
        violations: list[str] = []

        removed_helpers = {
            "_derived_lifecycle_tax_offset_executor",
            "_derived_lifecycle_tax_offset_month_cache_executor",
        }
        for helper_name in sorted(removed_helpers):
            if _function_source(server_tree, server_source, helper_name):
                violations.append(f"server.py still owns removed tax offset lifecycle executor {helper_name}")
        if "TaxOffsetDerivedLifecycleExecutor(" not in server_source:
            violations.append("server.py does not build the explicit tax offset lifecycle executor")
        if '"tax_offset_read_model": self._tax_offset_derived_lifecycle_executor().execute_read_model' not in server_source:
            violations.append("derived lifecycle registry does not use the explicit tax offset read model executor")
        if '"tax_offset_month_cache": self._tax_offset_derived_lifecycle_executor().execute_month_cache' not in server_source:
            violations.append("derived lifecycle registry does not use the explicit tax offset month cache executor")
        if "class TaxOffsetDerivedLifecycleExecutor" not in executor_source:
            violations.append("tax offset lifecycle executor service is missing")
        for snippet in (
            "def execute_read_model(",
            "def execute_month_cache(",
            'reason=str(domain_plan.get("reason") or "derived_lifecycle_tax_offset")',
            '"deleted_counts": {"tax_offset_read_models": len(deleted_scope_keys)}',
            '"deleted_counts": {"tax_offset_month_cache": len(months) if months else int("all" in scope_keys)}',
            '"enqueued_jobs": ["tax_offset_cache_warmup"] if deleted_scope_keys else []',
        ):
            if snippet not in executor_source:
                violations.append(f"tax offset lifecycle executor is missing behavior {snippet}")

        self.assertEqual(violations, [])

    def test_no_oa_bank_batch_derived_lifecycle_uses_explicit_executor_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        executor_path = SERVICES_ROOT / "no_oa_bank_batch_derived_lifecycle_executor.py"
        executor_source = executor_path.read_text(encoding="utf-8") if executor_path.exists() else ""
        violations: list[str] = []

        removed_helper = "_derived_lifecycle_no_oa_bank_batch_executor"
        if _function_source(server_tree, server_source, removed_helper):
            violations.append(f"server.py still owns removed no-OA bank batch lifecycle executor {removed_helper}")
        if "NoOaBankBatchDerivedLifecycleExecutor(" not in server_source:
            violations.append("server.py does not build the explicit no-OA bank batch lifecycle executor")
        if '"no_oa_bank_batch_read_model": self._no_oa_bank_batch_derived_lifecycle_executor().execute' not in server_source:
            violations.append("derived lifecycle registry does not use the explicit no-OA bank batch executor")
        if "class NoOaBankBatchDerivedLifecycleExecutor" not in executor_source:
            violations.append("no-OA bank batch lifecycle executor service is missing")
        for snippet in (
            "def execute(",
            'reason=str(domain_plan.get("reason") or "derived_lifecycle_no_oa_bank_batch")',
            '"deleted_counts": {"no_oa_bank_batch_read_models": 0}',
            '"enqueued_jobs": ["no_oa_bank_batch.read_model.refresh"] if enqueued else []',
        ):
            if snippet not in executor_source:
                violations.append(f"no-OA bank batch lifecycle executor is missing behavior {snippet}")

        self.assertEqual(violations, [])

    def test_bank_flow_rule_batch_derived_lifecycle_uses_own_executor_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        app_factory_source = _function_source(server_tree, server_source, "_bank_flow_rule_batch_derived_lifecycle_executor")
        executor_path = SERVICES_ROOT / "bank_flow_rule_batch_derived_lifecycle_executor.py"
        executor_source = executor_path.read_text(encoding="utf-8") if executor_path.exists() else ""
        violations: list[str] = []

        if "BankFlowRuleBatchDerivedLifecycleExecutor(" not in app_factory_source:
            violations.append("bank-flow rule batch lifecycle executor is not wired through its own executor")
        if "NoOaBankBatchDerivedLifecycleExecutor(" in app_factory_source:
            violations.append("bank-flow rule batch lifecycle executor still reuses the no-OA executor")
        for forbidden in ("read_model_name=", "default_reason="):
            if forbidden in app_factory_source:
                violations.append(f"bank-flow lifecycle executor still uses configurable no-OA identity {forbidden}")
        for snippet in (
            "class BankFlowRuleBatchDerivedLifecycleExecutor",
            "def execute(",
            'reason=str(domain_plan.get("reason") or "derived_lifecycle_bank_flow_rule_batch")',
            '"deleted_counts": {"bank_flow_rule_batch_read_models": 0}',
            '"enqueued_jobs": ["bank_flow_rule_batch.read_model.refresh"] if enqueued else []',
        ):
            if snippet not in executor_source:
                violations.append(f"bank-flow lifecycle executor is missing behavior {snippet}")

        self.assertEqual(violations, [])

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

    def test_output_invoice_collection_read_export_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        route_path = APP_ROOT / "routes_output_invoice_collections.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        route_class = _class_source(route_tree, route_source, "OutputInvoiceCollectionApiRoutes")
        factory_source = _function_source(server_tree, server_source, "_output_invoice_collection_routes")
        read_application_source = (SERVICES_ROOT / "output_invoice_collection_read_application_service.py").read_text(encoding="utf-8")
        fresh_gate_source = (SERVICES_ROOT / "output_invoice_collection_read_model_fresh_gate_service.py").read_text(encoding="utf-8")
        violations: list[str] = []

        for required in (
            "def route(",
            "/api/output-invoice-collections/rows",
            "/api/output-invoice-collections/filter-options",
            "/api/output-invoice-collections/export-preview",
            "/api/output-invoice-collections/export",
            "/api/output-invoice-collections/status-rules",
            "/api/output-invoice-collections/receipts/history",
            "/api/output-invoice-collections/receipt-preview",
            "/api/output-invoice-collections/receipt-settings",
            "/api/output-invoice-collections/receipts/",
            "/api/output-invoice-collections/red-invoice-relations/",
            "/api/output-invoice-collections/invoices/",
            "/api/output-invoice-collections/bank-transactions/",
            "/api/output-invoice-collections/rows/",
            "/collection-status",
            "/collection-reminder",
            "/red-invoice-relations",
            "/receipts",
            "def _json_read(",
            "def _json_body_mutation(",
            "def _json_session(",
            "def _relation_details_response(",
            "_idempotency_key(headers)",
            "_trace_id(headers)",
            "allow_live_fallback=allow_live_fallback",
        ):
            if required not in route_class:
                violations.append(f"Output collection route owner is missing {required}")
        for forbidden in (
            "filter_options_for_rows(",
            "apply_lifecycle_overlays_to_rows(",
            "export_preview_for_rows(",
            "export_for_rows(",
            "_sql_rows_provider",
            "_sql_all_rows_provider",
            "_sql_relation_details_provider",
        ):
            if forbidden in route_class:
                violations.append(f"Output collection route owner still owns read application orchestration {forbidden}")
        for required in (
            "class OutputInvoiceCollectionReadApplicationService",
            "def rows(",
            "def filter_options(",
            "def export_preview(",
            "def export(",
            "def relation_details(",
            "_allow_live_fallback",
        ):
            if required not in read_application_source:
                violations.append(f"Output collection read application service is missing {required}")
        if "allow_live_fallback=not self._requires_sql_read_model_runtime()" not in factory_source:
            violations.append("Application output collection route factory must disable live fallback in SQL read model runtime")
        if "_output_invoice_collection_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("Application does not dispatch output collection read routes through route owner")
        if "def _output_invoice_collection_xlsx_response(" not in server_source:
            violations.append("Application is missing explicit output collection xlsx response port")
        for required in (
            "class OutputInvoiceCollectionReadModelFreshGateService",
            "source_version_mismatch_reasons",
            "require_expected_source_versions",
            "payload_requires_schema_refresh",
            "def all_rows(",
            "def rows(",
            "def relation_details(",
        ):
            if required not in fresh_gate_source:
                violations.append(f"Output collection fresh-gate service is missing {required}")
        for removed_handler in (
            "_handle_api_output_invoice_collections_rows",
            "_handle_api_output_invoice_collections_filter_options",
            "_handle_api_output_invoice_collections_export_preview",
            "_handle_api_output_invoice_collections_export",
            "_handle_api_output_invoice_collections_invoice_detail",
            "_handle_api_output_invoice_collections_bank_transaction_detail",
            "_handle_api_output_invoice_collections_relation_details",
            "_handle_api_output_invoice_collections_status_rules",
            "_handle_api_output_invoice_collections_receipt_history",
            "_handle_api_output_invoice_collections_receipt_preview",
            "_handle_api_output_invoice_collections_collection_status",
            "_handle_api_output_invoice_collections_collection_reminder",
            "_handle_api_output_invoice_collections_collection_reminder_delete",
            "_handle_api_output_invoice_collections_red_relation_create",
            "_handle_api_output_invoice_collections_red_relation_delete",
            "_handle_api_output_invoice_collections_receipt_create",
            "_handle_api_output_invoice_collections_receipt_void",
            "_handle_api_output_invoice_collections_receipt_reissue",
            "_handle_api_output_invoice_collections_receipt_settings",
            "_handle_api_output_invoice_collections_receipt_settings_update",
            "_output_invoice_collection_mutation",
            "_get_invoice_relation_all_rows_from_sql_read_model",
            "_output_invoice_collection_sql_payload_requires_schema_refresh",
            "_invoice_relation_scope_key_from_query",
            "_invoice_relation_refreshing_payload",
            "_compat_output_invoice_collections_rows_response",
        ):
            if _function_source(server_tree, server_source, removed_handler):
                violations.append(f"server.py still owns output collection route callback {removed_handler}")

        self.assertEqual(violations, [])

    def test_oa_pending_payment_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        route_path = APP_ROOT / "routes_oa_pending_payments.py"
        retired_query_service_path = SERVICES_ROOT / "oa_pending_payment_service.py"
        command_service_path = SERVICES_ROOT / "oa_pending_payment_command_service.py"
        read_model_service_path = SERVICES_ROOT / "oa_pending_payment_read_model_service.py"
        relation_repository_path = SERVICES_ROOT / "postgres_repositories" / "oa_pending_payment_relation.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        route_class = _class_source(route_tree, route_source, "OaPendingPaymentApiRoutes")
        command_service_source = command_service_path.read_text(encoding="utf-8")
        read_model_service_source = read_model_service_path.read_text(encoding="utf-8")
        relation_repository_source = relation_repository_path.read_text(encoding="utf-8")
        violations: list[str] = []
        if retired_query_service_path.exists():
            violations.append("retired OA live query service still exists")

        for required in (
            "def route(",
            "/api/oa-pending-payments/rows",
            "/api/oa-pending-payments/bank-transaction-candidates",
            "/api/oa-pending-payments/oa/",
            "/api/oa-pending-payments/bank-transactions/",
            "/api/oa-pending-payments/invoices/",
            "/api/oa-pending-payments/rows/",
            "/api/oa-pending-payments/writeback-paid",
            "/api/oa-pending-payments/link-bank-transactions",
            "def _json_read(",
            "def _json_write(",
            "def _command_unavailable(",
            "def _read_model_service_required(",
        ):
            if required not in route_class:
                violations.append(f"OA pending payment route owner is missing {required}")
        if "_oa_pending_payment_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("Application does not dispatch OA pending payment routes through route owner")
        for forbidden_fallback in (
            "/api/oa-pending-payments/filter-options",
            "def filter_options(",
            "def all_rows(",
            "self._query_service",
            "return self._query_service.",
            "payload = self._query_service.",
            "self._query_service.list_rows",
            "self._query_service.filter_options",
            "self._query_service.oa_detail",
            "self._query_service.bank_transaction_detail",
            "self._query_service.invoice_detail",
            "self._query_service.row_relation_details",
        ):
            if forbidden_fallback in route_class:
                violations.append(f"OA pending payment route owner still has live read fallback {forbidden_fallback}")
        for forbidden_service_symbol in (
            "def all_rows(",
            "def filter_options(",
            "def filter_options_for_rows(",
        ):
            if forbidden_service_symbol in read_model_service_source:
                violations.append(f"OA pending payment service still exposes retired symbol {forbidden_service_symbol}")
        if "SnapshotOaPendingPaymentRelationRepository" in relation_repository_source:
            violations.append("OA pending payment relation repository still exposes the snapshot fallback")
        source_projection = _function_source(server_tree, server_source, "_oa_pending_payment_source_projection")
        if "_oa_adapter" in source_projection:
            violations.append("OA pending payment source projection still falls back to Workbench's private OA adapter")
        relation_repository = _function_source(server_tree, server_source, "_oa_pending_payment_relation_repository")
        if "load_oa_pending_payment_bank_relations" in relation_repository or "save_oa_pending_payment_bank_relations" in relation_repository:
            violations.append("OA pending payment relation composition still falls back to local snapshot persistence")
        command_composition = _function_source(server_tree, server_source, "_oa_pending_payment_command_service")
        if "payment_status_snapshot_writer=self._oa_pending_payment_source_snapshot_repository()" not in command_composition:
            violations.append("OA payment command does not compose the canonical PostgreSQL status snapshot writer")
        paid_snapshot_write = _function_source(
            _parse(command_service_path),
            command_service_source,
            "_record_paid_statuses",
        )
        if "record_paid_statuses" not in paid_snapshot_write:
            violations.append("OA payment command does not reconcile successful external writes into PostgreSQL")
        enqueue_refreshes = _function_source(
            _parse(command_service_path),
            command_service_source,
            "_enqueue_refreshes_for_records",
        )
        if 'scope_key != "all"' not in enqueue_refreshes:
            violations.append("OA payment command can still enqueue ordinary oa_pending_payment:all refreshes")
        for removed_write_path in (
            "/api/oa-pending-payments/confirm-paid",
            "/api/oa-pending-payments/auto-reconcile-bank-transactions",
            "def confirm_paid(",
            ".confirm_paid(",
            "def auto_reconcile_bank_transactions(",
            ".auto_reconcile_bank_transactions(",
        ):
            if removed_write_path in route_class:
                violations.append(f"OA pending payment route owner still exposes removed manual write path {removed_write_path}")
        for removed_handler in (
            "_handle_api_oa_pending_payments_rows",
            "_handle_api_oa_pending_payments_filter_options",
            "_handle_api_oa_pending_payments_bank_transaction_candidates",
            "_handle_api_oa_pending_payments_oa_detail",
            "_handle_api_oa_pending_payments_bank_transaction_detail",
            "_handle_api_oa_pending_payments_invoice_detail",
            "_handle_api_oa_pending_payments_relation_details",
            "_handle_api_oa_pending_payments_confirm_paid",
            "_handle_api_oa_pending_payments_auto_reconcile_bank_transactions",
            "_handle_api_oa_pending_payments_link_bank_transactions",
            "_oa_pending_payment_sql_payload_status",
        ):
            if _function_source(server_tree, server_source, removed_handler):
                violations.append(f"server.py still owns OA pending payment route callback {removed_handler}")

        self.assertEqual(violations, [])

    def test_downstream_relation_read_models_use_workbench_relation_distribution(self) -> None:
        downstream_paths = {
            SERVICES_ROOT / "search_pending_sql_projection.py",
            SERVICES_ROOT / "invoice_usage_collection_sql_projection.py",
            SERVICES_ROOT / "invoice_relation_query_context.py",
            SERVICES_ROOT / "input_invoice_usage_service.py",
            SERVICES_ROOT / "output_invoice_collection_service.py",
            SERVICES_ROOT / "bank_detail_sql_projection.py",
            SERVICES_ROOT / "bank_details_relation_tag_projection_service.py",
            SERVICES_ROOT / "pending_invoice_service.py",
            SERVICES_ROOT / "batch_accounting_service.py",
            SERVICES_ROOT / "no_oa_bank_batch_application_service.py",
            SERVICES_ROOT / "no_oa_bank_batch_service.py",
            SERVICES_ROOT / "cost_statistics_sql_projection.py",
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

    def test_downstream_relation_query_services_do_not_accept_pair_relation_service(self) -> None:
        downstream_query_service_paths = {
            SERVICES_ROOT / "pending_invoice_service.py",
            SERVICES_ROOT / "input_invoice_usage_service.py",
            SERVICES_ROOT / "output_invoice_collection_service.py",
            SERVICES_ROOT / "invoice_relation_query_context.py",
            SERVICES_ROOT / "bank_details_relation_tag_projection_service.py",
        }
        violations: list[str] = []

        for path in sorted(downstream_query_service_paths):
            if not path.exists():
                violations.append(f"{_relative(path)} is missing")
                continue
            tree = _parse(path)
            rel_path = _relative(path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    arg_names = [arg.arg for arg in [*node.args.args, *node.args.kwonlyargs]]
                    if "pair_relation_service" in arg_names:
                        violations.append(f"{rel_path}:{node.lineno} {node.name} accepts pair_relation_service")
                    if node.name == "active_relations_for_row_ids":
                        violations.append(f"{rel_path}:{node.lineno} exposes legacy active_relations_for_row_ids")
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "fin_ops_platform.services.workbench_pair_relation_service"
                ):
                    violations.append(f"{rel_path}:{node.lineno} imports WorkbenchPairRelationService")

        self.assertEqual(violations, [])

    def test_no_oa_application_uses_pair_relation_snapshot_port(self) -> None:
        path = SERVICES_ROOT / "no_oa_bank_batch_application_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        app_source = _class_source(tree, source, "NoOaBankBatchApplicationService")
        port_source = _class_source(tree, source, "NoOaPairRelationSnapshotPort")

        violations: list[str] = []
        if "NoOaPairRelationSnapshotPort" not in source:
            violations.append("no-OA application module lacks explicit pair relation snapshot port")
        if "_pair_relation_snapshot_port" not in app_source:
            violations.append("NoOaBankBatchApplicationService does not store pair relation snapshot port")
        for forbidden in (
            "pair_relation_service:",
            "pair_relation_service=",
            "self._pair_relation_service",
            "._pair_relations",
            "._pair_relation_history",
            "WorkbenchPairRelationService.from_snapshot",
        ):
            if forbidden in app_source:
                violations.append(f"NoOaBankBatchApplicationService keeps direct pair relation dependency {forbidden}")
        for required in (
            "snapshot_case_ids",
            "snapshot_version",
            "snapshot_by_case_id",
            "restore",
            "WorkbenchPairRelationService.from_snapshot",
        ):
            if required not in port_source:
                violations.append(f"NoOaPairRelationSnapshotPort is missing {required}")

        self.assertEqual(violations, [])

    def test_no_oa_domain_relation_reads_use_repair_read_port(self) -> None:
        path = SERVICES_ROOT / "no_oa_bank_batch_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        service_source = _class_source(tree, source, "NoOaBankBatchService")
        port_source = _class_source(tree, source, "NoOaRelationRepairReadPort")
        repair_source = _function_source(tree, source, "_repair_submitted_no_oa_relation_consistency")
        stale_projection_source = _function_source(tree, source, "_has_active_no_oa_relation")
        month_scope_source = _function_source(tree, source, "_build_batches_for_month_scope")

        violations: list[str] = []
        if "NoOaRelationRepairReadPort" not in source:
            violations.append("no-OA domain module lacks explicit relation repair read port")
        if "_relation_read_port" not in service_source:
            violations.append("NoOaBankBatchService does not store relation read port")
        for forbidden in (
            "self._pair_relation_service",
            "_pair_relation_service.get_active_relation_by_case_id",
            "_pair_relation_service.active_relations_for_row_ids",
        ):
            if forbidden in service_source:
                violations.append(f"NoOaBankBatchService keeps direct pair relation read dependency {forbidden}")
        for required in (
            "active_relation_by_case_id",
            "active_relations_for_row_ids",
            "get_active_relation_by_case_id",
        ):
            if required not in port_source:
                violations.append(f"NoOaRelationRepairReadPort is missing {required}")
        for required in (
            "_relation_read_port.active_relation_by_case_id",
            "_relation_read_port.active_relations_for_row_ids",
            "_confirm_no_oa_relation",
            "_cancel_no_oa_relation",
        ):
            if required not in repair_source:
                violations.append(f"submitted no-OA repair no longer uses expected boundary {required}")
        if "_relation_read_port.active_relation_by_case_id" not in stale_projection_source:
            violations.append("stale/submitted projection does not use relation read port")
        if "relation_read_port=self._relation_read_port" not in month_scope_source:
            violations.append("month-scoped no-OA rebuild does not forward relation read port")

        self.assertEqual(violations, [])

    def test_etc_summary_relation_delete_uses_workbench_relation_command_boundary(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        route_path = APP_ROOT / "routes_etc.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        business_delete_path = SERVICES_ROOT / "etc_business_batch_delete_service.py"
        business_delete_source = business_delete_path.read_text(encoding="utf-8")
        business_delete_tree = _parse(business_delete_path)
        cleanup_path = SERVICES_ROOT / "etc_reconciliation_import_cleanup_service.py"
        cleanup_source = cleanup_path.read_text(encoding="utf-8")
        cleanup_tree = _parse(cleanup_path)
        cancel_method = _function_source(tree, source, "_cancel_etc_summary_relations_for_batch")
        route_delete_method = _function_source(route_tree, route_source, "delete_batch")
        business_delete_method = _function_source(business_delete_tree, business_delete_source, "delete_business_batch")
        task_delete_method = _function_source(cleanup_tree, cleanup_source, "delete_reconciliation_task_business_batch_sources")

        violations: list[str] = []
        if "cancel_relations_for_row_ids" not in cancel_method:
            violations.append("_cancel_etc_summary_relations_for_batch does not delegate row cancellation to command service")
        if "cancel_active_relations_for_row_ids" in cancel_method:
            violations.append("_cancel_etc_summary_relations_for_batch directly mutates pair relation service")
        if "_workbench_pair_relation_service" in cancel_method:
            violations.append("_cancel_etc_summary_relations_for_batch reaches app pair relation service directly")
        if "_handle_api_etc_business_batch_delete" in source:
            violations.append("server.py reintroduced ETC business batch API delete callback")
        if "_delete_service.delete_business_batch(" not in route_delete_method:
            violations.append("ETC business batch route owner delete no longer delegates side-effect orchestration to service")
        if "_refresh_after_etc_invoice_link(" not in route_delete_method:
            violations.append("ETC business batch route owner delete does not publish returned refresh events")
        if "_persist_state(" not in route_delete_method:
            violations.append("ETC business batch route owner delete does not persist returned persistence events")
        if "_assert_etc_summary_relation_write_precondition_for_batch(batch)" not in business_delete_method:
            violations.append("ETC business batch delete service lacks relation freshness preflight before local mutation")
        if "_cancel_etc_summary_relations_for_batch(batch)" not in business_delete_method:
            violations.append("ETC business batch delete service lacks summary relation cancellation")
        if "delete_reconciliation_task_after_business_batch_delete(task)" not in business_delete_method:
            violations.append("ETC business batch delete service lacks reconciliation task cleanup")
        if "_refresh_after_etc_invoice_link(" in business_delete_source:
            violations.append("ETC business batch delete service performs app refresh directly")
        if "_persist_state(" in business_delete_source:
            violations.append("ETC business batch delete service performs app persistence directly")
        if "_assert_etc_summary_relation_write_precondition_for_batch(business_batch)" not in task_delete_method:
            violations.append("ETC reconciliation task delete lacks relation freshness preflight before local mutation")
        if "_delete_reconciliation_task_business_batch_sources" in source:
            violations.append("server.py reintroduced ETC reconciliation business-batch cleanup ownership")

        self.assertEqual(violations, [])

    def test_etc_business_batch_routes_do_not_keep_removed_legacy_handlers(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        removed_handlers = {
            "_handle_api_etc_business_batches",
            "_handle_api_etc_business_batch_create",
            "_route_api_etc_business_batch",
            "_handle_api_etc_business_import_preview",
            "_handle_api_etc_business_import_confirm",
            "_handle_api_etc_business_oa_draft",
            "_handle_api_etc_business_manual_oa_status",
            "_handle_api_etc_business_batch_delete",
            "_handle_api_etc_business_oa_draft_revoke",
        }
        present = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in removed_handlers
        ]
        v2_route = _function_source(tree, source, "_route_api_etc_business_batch_v2")
        list_route = _function_source(tree, source, "_handle_api_etc_business_batches_route")
        route_factory = _function_source(tree, source, "_etc_business_routes")

        violations: list[str] = []
        if present:
            violations.append(f"server.py keeps removed ETC business batch legacy handlers: {sorted(present)}")
        for required_delegate in (
            "routes.source_files(",
            "routes.preview_import(",
            "routes.confirm_import(",
            "routes.create_oa_draft(",
            "routes.revoke_oa_draft(",
            "routes.manual_oa_status(",
            "self._etc_business_routes().delete_batch(",
        ):
            if required_delegate not in v2_route:
                violations.append(f"_route_api_etc_business_batch_v2 no longer delegates {required_delegate} to EtcBusinessBatchApiRoutes")
        for required_delegate in (
            "_etc_business_routes().list_batches(",
            "_etc_business_routes().create_batch(",
        ):
            if required_delegate not in list_route:
                violations.append(f"_handle_api_etc_business_batches_route no longer delegates {required_delegate} to EtcBusinessBatchApiRoutes")
        for required_port in (
            "delete_service=self._etc_business_batch_delete_service()",
            "load_json_body=self._load_json_body",
            "refresh_after_etc_invoice_link=",
            "persist_state=self._persist_state",
        ):
            if required_port not in route_factory:
                violations.append(f"_etc_business_routes lacks explicit route owner port {required_port}")
        if "EtcBusinessBatchActor" in source:
            violations.append("server.py reintroduced direct EtcBusinessBatchActor construction instead of route-owned actor mapping")

        self.assertEqual(violations, [])

    def test_etc_reconciliation_task_routes_delegate_to_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_etc_reconciliation.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        source_upload_path = SERVICES_ROOT / "etc_reconciliation_source_upload_service.py"
        source_upload_source = source_upload_path.read_text(encoding="utf-8")
        payload_facade_path = SERVICES_ROOT / "etc_reconciliation_task_payload_facade.py"
        payload_facade_source = payload_facade_path.read_text(encoding="utf-8")

        handle_request = _function_source(server_tree, server_source, "_handle_request_untracked")
        route_factory = _function_source(server_tree, server_source, "_etc_reconciliation_routes")
        source_upload_factory = _function_source(server_tree, server_source, "_etc_reconciliation_source_upload_service")
        route_owner_names = [
            node.name
            for node in ast.walk(route_tree)
            if isinstance(node, ast.ClassDef)
        ]
        route_owner_init = _function_source(route_tree, route_source, "__init__")
        route_owner_route = _function_source(route_tree, route_source, "route")
        route_owner_delete_task = _function_source(route_tree, route_source, "delete_task")
        route_owner_delete_imported_invoices = _function_source(route_tree, route_source, "delete_imported_invoices")
        route_owner_delete_source_file = _function_source(route_tree, route_source, "delete_source_file")
        route_owner_patch_item = _function_source(route_tree, route_source, "patch_item")
        route_owner_confirm_task = _function_source(route_tree, route_source, "confirm_task")
        route_owner_reopen_task = _function_source(route_tree, route_source, "reopen_task")
        route_owner_refresh_matches = _function_source(route_tree, route_source, "refresh_matches")
        route_owner_upload_source = _function_source(route_tree, route_source, "upload_source")
        route_owner_ticket_root_texts = _function_source(route_tree, route_source, "submit_ticket_root_texts")

        violations: list[str] = []
        if "EtcReconciliationTaskApiRoutes" not in server_source:
            violations.append("server.py does not import/use EtcReconciliationTaskApiRoutes")
        if "_etc_reconciliation_routes().route(" not in handle_request:
            violations.append("handle_request no longer delegates ETC reconciliation task routes to route owner")
        if "EtcReconciliationTaskApiRoutes(" not in route_factory:
            violations.append("_etc_reconciliation_routes does not construct the route owner")
        if "task_service=self._etc_reconciliation_task_service" not in route_factory:
            violations.append("ETC reconciliation route owner lacks explicit task service injection")
        if "load_multipart_body=self._load_multipart_body" not in route_factory:
            violations.append("ETC reconciliation route owner lacks explicit multipart body parser")
        if "cleanup_service=self._etc_reconciliation_import_cleanup_service()" not in route_factory:
            violations.append("ETC reconciliation route owner lacks explicit cleanup service injection")
        if "expected_version_from_payload=self._expected_version_from_payload" not in route_factory:
            violations.append("ETC reconciliation route owner lacks explicit expected-version parser")
        if "expected_version_from_fields=self._expected_version_from_fields" not in route_factory:
            violations.append("ETC reconciliation route owner lacks explicit multipart expected-version parser")
        if "reconciliation_storage_error_response=self._reconciliation_storage_error_response" not in route_factory:
            violations.append("ETC reconciliation route owner lacks explicit storage error mapper")
        if "persist_state=self._persist_state" not in route_factory:
            violations.append("ETC reconciliation route owner lacks explicit persist callback")
        if "source_upload_service=self._etc_reconciliation_source_upload_service()" not in route_factory:
            violations.append("ETC reconciliation route owner lacks explicit source upload service injection")
        if "payload_facade = self._etc_reconciliation_task_payload_facade()" not in route_factory:
            violations.append("ETC reconciliation route owner lacks explicit payload facade assembly")
        if "task_payload=payload_facade.task_payload" not in route_factory:
            violations.append("ETC reconciliation route owner no longer receives payload facade task payload")
        if "unavailable_task_payload=payload_facade.unavailable_task_payload" not in route_factory:
            violations.append("ETC reconciliation route owner no longer receives payload facade unavailable payload")
        if "EtcReconciliationSourceUploadService(task_service=self._etc_reconciliation_task_service)" not in source_upload_factory:
            violations.append("ETC reconciliation source upload service is not explicitly assembled from task service")
        if "EtcReconciliationTaskPayloadFacade(" not in server_source:
            violations.append("server.py does not explicitly assemble ETC reconciliation task payload facade")
        if "etc_import_batch_by_id=self._etc_import_batch_by_id" not in server_source:
            violations.append("ETC reconciliation payload facade lacks explicit import batch lookup dependency")
        if "serialize_value=self._serialize_value" not in server_source:
            violations.append("ETC reconciliation payload facade lacks explicit serializer dependency")
        if "self._source_upload_service.upload_sources(" not in route_owner_upload_source:
            violations.append("ETC reconciliation route owner upload handler no longer delegates parser orchestration to source upload service")
        if "self._source_upload_service.submit_ticket_root_texts(" not in route_owner_ticket_root_texts:
            violations.append("ETC reconciliation route owner ticket-root text handler no longer delegates parser orchestration to source upload service")
        for forbidden_upload_parser_detail in (
            "CcbCreditCardStatementParser",
            "TicketRootClipboardTextParser",
            "TicketRootDocumentParser",
            "SupplementEvidenceParser",
            "_reconciliation_wrong_slot_message",
            "_validate_ticket_root_upload_source_mode",
            "_ticket_root_upload_source_mode",
            "_ticket_root_text_file_not_trip_result",
        ):
            if forbidden_upload_parser_detail in server_source:
                violations.append(f"server.py reintroduced ETC reconciliation source upload parser detail {forbidden_upload_parser_detail}")
        for forbidden_ticket_text_detail in (
            "store_uploaded_source_file(",
            "apply_parse_result(",
        ):
            if forbidden_ticket_text_detail in route_owner_ticket_root_texts:
                violations.append(f"ETC reconciliation route owner reintroduced ticket-root text persistence/parser detail {forbidden_ticket_text_detail}")
        for required_service_detail in (
            "class EtcReconciliationSourceUploadService",
            "def upload_sources(",
            "def submit_ticket_root_texts(",
            "reconciliation_wrong_slot_message(",
            "validate_ticket_root_upload_source_mode(",
            "TicketRootDocumentParser().parse_file(",
            "TicketRootClipboardTextParser().parse_text(",
            "SupplementEvidenceParser().parse_text(",
        ):
            if required_service_detail not in source_upload_source:
                violations.append(f"ETC reconciliation source upload service lacks {required_service_detail}")
        for required_payload_detail in (
            "class EtcReconciliationTaskPayloadFacade",
            "def task_payload(",
            "def unavailable_task_payload(",
            "def import_blockers(",
            "def imported_invoice_summary(",
            "def task_can_confirm(",
            "def source_file_payloads(",
            "def parse_issue_payloads(",
        ):
            if required_payload_detail not in payload_facade_source:
                violations.append(f"ETC reconciliation payload facade lacks {required_payload_detail}")
        for removed_payload_helper in (
            "def _etc_reconciliation_task_payload(",
            "def _etc_reconciliation_unavailable_task_payload(",
            "def _etc_reconciliation_import_blockers(",
            "def _etc_reconciliation_imported_invoice_summary(",
            "def _etc_reconciliation_task_can_confirm(",
            "def _etc_source_file_payloads(",
            "def _etc_parse_issue_payloads(",
            "def _etc_task_card_has_linked_etc_evidence(",
            "def _etc_task_card_has_linked_supplement(",
            "def _etc_task_card_supplement_delta_requires_note(",
        ):
            if removed_payload_helper in server_source:
                violations.append(f"server.py reintroduced ETC reconciliation payload helper {removed_payload_helper}")
        if "_handle_api_etc_reconciliation_task_delete" in server_source:
            violations.append("server.py reintroduced ETC reconciliation task delete HTTP callback")
        if "_handle_api_etc_reconciliation_imported_invoices_delete" in server_source:
            violations.append("server.py reintroduced ETC reconciliation imported-invoices delete HTTP callback")
        for removed_callback in (
            "_handle_api_etc_reconciliation_upload",
            "_handle_api_etc_reconciliation_ticket_root_texts",
            "_handle_api_etc_reconciliation_source_file_delete",
            "_handle_api_etc_reconciliation_item_patch",
            "_handle_api_etc_reconciliation_confirm",
            "_handle_api_etc_reconciliation_reopen",
            "_handle_api_etc_reconciliation_refresh_matches",
            "_handle_api_etc_reconciliation_supplement_for_card_upload",
        ):
            if removed_callback in server_source:
                violations.append(f"server.py reintroduced ETC reconciliation route-owned callback {removed_callback}")
        if "Application" in route_owner_init:
            violations.append("ETC reconciliation route owner accepts the whole Application")
        if "EtcReconciliationTaskApiRoutes" not in route_owner_names:
            violations.append("routes_etc_reconciliation.py does not define EtcReconciliationTaskApiRoutes")
        if "cleanup_task_import_sources" not in route_owner_delete_task:
            violations.append("ETC reconciliation route owner task delete does not use cleanup service")
        if "remove_imported_invoices" not in route_owner_delete_imported_invoices:
            violations.append("ETC reconciliation route owner imported-invoices delete does not use cleanup service")
        if "etc_reconciliation_task_deleted" not in route_owner_delete_task:
            violations.append("ETC reconciliation route owner task delete lacks refresh reason")
        if "etc_reconciliation_imported_invoices_removed" not in route_owner_delete_imported_invoices:
            violations.append("ETC reconciliation route owner imported-invoices delete lacks refresh reason")
        if "delete_source_file(" not in route_owner_delete_source_file:
            violations.append("ETC reconciliation route owner source-file delete does not delegate to task service")
        if "patch_item(" not in route_owner_patch_item:
            violations.append("ETC reconciliation route owner item patch does not delegate to task service")
        if "confirm_task(" not in route_owner_confirm_task:
            violations.append("ETC reconciliation route owner confirm does not delegate to task service")
        if "reopen_task(" not in route_owner_reopen_task:
            violations.append("ETC reconciliation route owner reopen does not delegate to task service")
        if "refresh_matches(task_id=task_id)" not in route_owner_refresh_matches:
            violations.append("ETC reconciliation route owner refresh-matches does not delegate to task service")
        for required_route in (
            'route_path == "/api/etc/reconciliation-tasks"',
            'route_path == "/api/etc/reconciliation-tasks/ready-for-import"',
            'route_path.startswith("/api/etc/reconciliation-tasks/")',
        ):
            if required_route not in route_owner_route:
                violations.append(f"ETC reconciliation route owner missing dispatch branch {required_route}")
        for out_of_scope_route in (
            "/api/etc/import/preview",
            "/api/etc/import/confirm",
            "/api/etc/batches",
        ):
            if out_of_scope_route in route_source:
                violations.append(f"ETC reconciliation route owner took out-of-scope route {out_of_scope_route}")

        self.assertEqual(violations, [])

    def test_etc_import_routes_delegate_to_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_etc_import.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        etc_service_source = (SERVICES_ROOT / "etc_service.py").read_text(encoding="utf-8")
        preview_service_source = (SERVICES_ROOT / "etc_import_preview_service.py").read_text(encoding="utf-8")
        processing_service_source = (SERVICES_ROOT / "import_processing_service.py").read_text(encoding="utf-8")

        handle_request = _function_source(server_tree, server_source, "_handle_request_untracked")
        route_factory = _function_source(server_tree, server_source, "_etc_import_routes")
        route_owner_names = [
            node.name
            for node in ast.walk(route_tree)
            if isinstance(node, ast.ClassDef)
        ]
        route_owner_init = _function_source(route_tree, route_source, "__init__")
        route_owner_route = _function_source(route_tree, route_source, "route")
        route_owner_preview = _function_source(route_tree, route_source, "preview")
        route_owner_confirm = _function_source(route_tree, route_source, "confirm")

        violations: list[str] = []
        if "EtcImportApiRoutes" not in server_source:
            violations.append("server.py does not import/use EtcImportApiRoutes")
        if "_etc_import_routes().route(" not in handle_request:
            violations.append("handle_request no longer delegates ETC import routes to route owner")
        if "EtcImportApiRoutes(" not in route_factory:
            violations.append("_etc_import_routes does not construct the route owner")
        for required_dependency in (
            "preview_service=self._etc_import_preview_service",
            "background_job_service=self._background_job_service",
            "enqueue_import_job=self._enqueue_import_process_job",
        ):
            if required_dependency not in route_factory:
                violations.append(f"ETC import route owner lacks explicit dependency {required_dependency}")
        for removed_handler in (
            "_handle_api_etc_import_preview",
            "_handle_api_etc_import_confirm",
            "_handle_api_etc_import(",
        ):
            if removed_handler in server_source:
                violations.append(f"server.py reintroduced ETC import handler {removed_handler}")
        if "Application" in route_owner_init:
            violations.append("ETC import route owner accepts the whole Application")
        if "EtcImportApiRoutes" not in route_owner_names:
            violations.append("routes_etc_import.py does not define EtcImportApiRoutes")
        for required_route in (
            'route_path == "/api/etc/import/preview"',
            'route_path == "/api/etc/import/confirm"',
        ):
            if required_route not in route_owner_route:
                violations.append(f"ETC import route owner missing dispatch branch {required_route}")
        if "self._preview_service.preview(" not in route_owner_preview:
            violations.append("ETC import route owner preview does not delegate to the durable preview service")
        if "create_or_get_idempotent_job_with_created" not in route_owner_confirm:
            violations.append("ETC import route owner confirm does not create idempotent background job")
        if "self._preview_service.validate(" not in route_owner_confirm:
            violations.append("ETC import route owner confirm does not validate the durable preview")
        if "begin_import" in route_owner_confirm or "run_job" in route_owner_confirm:
            violations.append("ETC import route owner reintroduced task mutation or inline processing")
        if 'route_path == "/api/etc/import"' in route_owner_route:
            violations.append("ETC import route owner reintroduced the removed direct-import route")
        for removed_runtime in (
            "_etc_reconciliation_import_previews",
            "_execute_etc_invoice_import_confirm_job",
            "execute_etc_invoice_import_confirm_job=self.",
        ):
            if removed_runtime in server_source:
                violations.append(f"server.py reintroduced ETC legacy runtime {removed_runtime}")
        if "_enqueue_import_process_job" in route_source:
            violations.append("ETC import route owner uses app-private enqueue helper instead of injected port")
        if "_import_sessions" in etc_service_source:
            violations.append("EtcService reintroduced process-local import session ownership")
        if "class EtcImportPreviewService" not in preview_service_source:
            violations.append("ETC import durable preview owner is missing")
        for marker in ("self._etc_import_preview_service.validate(", "begin_import(", "uploads=list(validated_preview.uploads)"):
            if marker not in processing_service_source:
                violations.append(f"ETC import worker processing lacks durable boundary marker {marker}")

        self.assertEqual(violations, [])

    def test_web_etc_api_does_not_call_legacy_batch_mutations_or_list(self) -> None:
        api_source = (REPO_ROOT / "web" / "src" / "features" / "etc" / "api.ts").read_text(encoding="utf-8")
        forbidden_markers = (
            "export async function fetchEtcBatches",
            "export async function createEtcOaDraft",
            "export async function createEtcOaDraftForBatch",
            "export async function confirmEtcBatchSubmitted",
            "export async function markEtcBatchNotSubmitted",
            "export async function deleteEtcBatch",
            "export async function fetchEtcBatchDetail",
            "export async function revokeEtcSubmittedInvoices",
            '"/api/etc/batches/draft"',
            '"/api/etc/invoices/revoke-submitted"',
            '`/api/etc/batches?${params.toString()}`',
            '`/api/etc/batches/${encodeURIComponent(batchId)}`',
            '`/api/etc/batches/${encodeURIComponent(batchId)}/confirm-submitted`',
            '`/api/etc/batches/${encodeURIComponent(batchId)}/mark-not-submitted`',
        )
        violations = [marker for marker in forbidden_markers if marker in api_source]

        self.assertEqual(violations, [])

    def test_etc_ticket_page_does_not_restore_full_task_or_dual_selection_hot_path(self) -> None:
        page_source = (REPO_ROOT / "web" / "src" / "pages" / "EtcTicketManagementPage.tsx").read_text(encoding="utf-8")
        forbidden_markers = (
            "fetchEtcReconciliationTasks",
            "loadReconciliationTasks",
            "selectedTaskId",
            "selectedTaskImportBatchId",
            "selectedTaskImportBatchCanSubmit",
            "deleteEtcReconciliationTask",
            'kind: "task"',
        )

        self.assertEqual([marker for marker in forbidden_markers if marker in page_source], [])

    def test_etc_business_batch_reads_stay_on_narrow_repository_contracts(self) -> None:
        repository_path = SERVICES_ROOT / "postgres_repositories" / "ops_tax_etc.py"
        repository_source = repository_path.read_text(encoding="utf-8")
        repository_tree = _parse(repository_path)
        application_path = SERVICES_ROOT / "etc_business_batch_application_service.py"
        application_source = application_path.read_text(encoding="utf-8")
        application_tree = _parse(application_path)
        narrow_sources = [
            _function_source(repository_tree, repository_source, "list_etc_business_batch_summaries"),
            _function_source(repository_tree, repository_source, "get_etc_business_batch_record"),
            _function_source(application_tree, application_source, "list_batches_payload"),
            _function_source(application_tree, application_source, "detail_payload"),
        ]
        forbidden_markers = ("load_etc_state", "load_etc_reconciliation_state", "_stored_invoice_file_exists")

        self.assertTrue(all(narrow_sources))
        self.assertEqual(
            [marker for source in narrow_sources for marker in forbidden_markers if marker in source],
            [],
        )

    def test_web_etc_test_mock_does_not_reintroduce_legacy_etc_routes(self) -> None:
        mock_source = (REPO_ROOT / "web" / "src" / "test" / "apiMock.ts").read_text(encoding="utf-8")
        forbidden_markers = (
            '"/api/etc/batches"',
            '"/api/etc/batches/draft"',
            '"/api/etc/invoices/revoke-submitted"',
            "latestEtcDraftInvoiceIds",
            "latestEtcDraftBatchId",
            "listBatches(",
            "batchDetail(",
            "markBatchSubmitted(",
            "markBatchUnsubmitted(",
            "markSubmitted(",
            "markUnsubmitted(",
            'segment === "oa-status" && trailing === "refresh"',
            "^\\/api\\/etc\\/batches\\/",
        )
        violations = [marker for marker in forbidden_markers if marker in mock_source]

        self.assertEqual(violations, [])

    def test_etc_invoice_routes_delegate_to_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_etc_invoices.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        service_source = (SERVICES_ROOT / "etc_service.py").read_text(encoding="utf-8")

        handle_request = _function_source(server_tree, server_source, "_handle_request_untracked")
        route_factory = _function_source(server_tree, server_source, "_etc_invoice_routes")
        route_owner_init = _function_source(route_tree, route_source, "__init__")
        route_owner_route = _function_source(route_tree, route_source, "route")
        route_owner_list = _function_source(route_tree, route_source, "list_invoices")

        violations: list[str] = []
        if "EtcInvoiceApiRoutes" not in server_source:
            violations.append("server.py does not import/use EtcInvoiceApiRoutes")
        if "_etc_invoice_routes().route(" not in handle_request:
            violations.append("handle_request no longer delegates ETC invoice routes to route owner")
        if "EtcInvoiceApiRoutes(" not in route_factory:
            violations.append("_etc_invoice_routes does not construct the route owner")
        for required_port in (
            "etc_service=self._etc_service",
            "json_response=self._json_response",
            "serialize_invoice=self._serialize_etc_invoice",
        ):
            if required_port not in route_factory:
                violations.append(f"ETC invoice route owner lacks explicit port {required_port}")
        for forbidden_port in (
            "load_json_body=self._load_json_body",
            "link_etc_invoices_to_existing_invoices=self._link_etc_invoices_to_existing_invoices",
            "refresh_after_etc_invoice_link=self._refresh_after_etc_invoice_link",
        ):
            if forbidden_port in route_factory:
                violations.append(f"ETC invoice route owner still receives write-side port {forbidden_port}")
        if "Application" in route_owner_init:
            violations.append("ETC invoice route owner accepts the whole Application")
        if 'route_path == "/api/etc/invoices"' not in route_owner_route:
            violations.append("ETC invoice route owner missing list dispatch branch")
        if '"/api/etc/invoices/revoke-submitted"' in route_source or '"/api/etc/invoices/revoke-submitted"' in server_source:
            violations.append("ETC invoice revoke-submitted route was reintroduced")
        if "def revoke_submitted(" in route_source:
            violations.append("ETC invoice route owner kept legacy revoke handler")
        if "def revoke_submitted(" in service_source:
            violations.append("ETC service kept legacy invoice-id revoke method")
        for forbidden_write_port in (
            "_load_json_body",
            "_link_etc_invoices_to_existing_invoices",
            "_refresh_after_etc_invoice_link",
        ):
            if forbidden_write_port in route_owner_init:
                violations.append(f"ETC invoice route owner constructor kept write-side port {forbidden_write_port}")
        if "list_invoices(" not in route_owner_list:
            violations.append("ETC invoice list route does not delegate to ETC service")
        for removed_handler in (
            "_handle_api_etc_invoices(",
            "_handle_api_etc_revoke_submitted(",
        ):
            if removed_handler in server_source:
                violations.append(f"server.py reintroduced ETC invoice callback {removed_handler}")
        forbidden_imports = {
            "fin_ops_platform.app.server",
            "fin_ops_platform.app.auth",
            "http.cookies",
        }
        route_imports = _imported_modules(route_tree)
        leaked_imports = sorted(forbidden_imports.intersection(route_imports))
        if leaked_imports:
            violations.append(f"ETC invoice route owner imports forbidden modules: {leaked_imports}")

        self.assertEqual(violations, [])

    def test_etc_repair_and_link_services_do_not_keep_direct_relation_write_fallbacks(self) -> None:
        checks = {
            "backend/src/fin_ops_platform/services/historical_etc_repair_service.py": {
                "_reconcile_batch": "_pair_relation_service.create_active_relation",
            },
            "backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py": {
                "_update_relation_metadata": "_pair_relation_service.update_relation_metadata_for_case_id",
            },
            "backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py": {
                "link_existing_invoices": "_pair_relation_service.update_relation_metadata_for_case_id",
            },
        }
        violations: list[str] = []
        for rel_path, method_checks in checks.items():
            path = REPO_ROOT / rel_path
            source = path.read_text(encoding="utf-8")
            tree = _parse(path)
            for forbidden in (
                "pair_relation_service",
                "_pair_relation_service",
            ):
                if forbidden in source:
                    violations.append(f"{rel_path} keeps legacy pair relation dependency {forbidden}")
            for required in (
                "get_active_relation_by_case_id",
                "update_relation_metadata_for_case_id"
                if "historical_etc_repair_service.py" not in rel_path
                else "confirm_relation",
            ):
                if required not in source:
                    violations.append(f"{rel_path} does not use relation command boundary method {required}")
            for method_name, forbidden in method_checks.items():
                method_source = _function_source(tree, source, method_name)
                if forbidden in method_source:
                    violations.append(f"{rel_path}:{method_name} keeps direct relation write fallback {forbidden}")

        self.assertEqual(violations, [])

    def test_input_invoice_oa_reverse_relation_writer_uses_command_boundary(self) -> None:
        service_path = SERVICES_ROOT / "input_invoice_usage_oa_reverse_service.py"
        service_source = service_path.read_text(encoding="utf-8")
        service_tree = _parse(service_path)
        writer_source = _class_source(service_tree, service_source, "WorkbenchInputInvoiceUsageOaReverseRelationWriter")

        app_path = APP_ROOT / "server.py"
        app_source = app_path.read_text(encoding="utf-8")
        app_tree = _parse(app_path)
        factory_source = _function_source(app_tree, app_source, "_input_invoice_usage_oa_reverse_service")

        violations: list[str] = []
        if "confirm_relation" not in writer_source:
            violations.append("OA reverse relation writer does not delegate writes to WorkbenchRelationCommandService")
        for forbidden in (
            "_pair_relation_service",
            "active_relations_for_row_ids",
            "create_active_relation",
        ):
            if forbidden in writer_source:
                violations.append(f"OA reverse relation writer keeps direct pair relation fallback {forbidden}")
        if "WorkbenchInputInvoiceUsageOaReverseRelationWriter(self._workbench_relation_command_service())" not in factory_source:
            violations.append("Application does not inject WorkbenchRelationCommandService into OA reverse relation writer")
        if "WorkbenchInputInvoiceUsageOaReverseRelationWriter(self._workbench_pair_relation_service)" in factory_source:
            violations.append("Application still injects WorkbenchPairRelationService into OA reverse relation writer")
        for forbidden in (
            "query_service:",
            "query_service=",
            "self._query_service",
            "_all_input_invoice_usage_rows",
        ):
            if forbidden in service_source or forbidden in factory_source:
                violations.append(f"OA reverse service keeps removed input usage live query fallback {forbidden}")

        self.assertEqual(violations, [])

    def test_input_invoice_oa_reverse_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_input_invoice_usage_oa_reverse.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        route_class = _class_source(route_tree, route_source, "InputInvoiceUsageOaReverseApiRoutes")
        factory_source = _function_source(server_tree, server_source, "_input_invoice_usage_oa_reverse_routes")

        violations: list[str] = []
        if not route_class:
            violations.append("InputInvoiceUsageOaReverseApiRoutes is missing")
        for forbidden in (
            "Application",
            "_handle_api_input_invoice_usage_oa_reverse_preview",
            "_handle_api_input_invoice_usage_oa_reverse_batch_create",
            "_handle_api_input_invoice_usage_oa_reverse_submitted_history",
            "_handle_api_input_invoice_usage_oa_reverse_staged_drafts",
            "_handle_api_input_invoice_usage_oa_reverse_batch_get",
            "_handle_api_input_invoice_usage_oa_reverse_one_step_draft_create",
            "_handle_api_input_invoice_usage_oa_reverse_draft_create",
            "_handle_api_input_invoice_usage_oa_reverse_draft_revoke",
            "_handle_api_input_invoice_usage_oa_reverse_status_refresh",
            "_handle_api_input_invoice_usage_oa_reverse_manual_status",
        ):
            if forbidden in route_source:
                violations.append(f"OA reverse route owner leaks legacy/application ownership marker {forbidden}")
        for required in (
            "service=service",
            "resolve_read_session=self._resolve_fin_ops_read_session",
            "mutation_actor=self._input_invoice_usage_mutation_actor",
            "load_json_body=self._load_json_body",
            "json_response=self._json_response",
            "input_usage_error_response=self._input_invoice_usage_error_response",
            "oa_reverse_error_response=self._input_invoice_usage_oa_reverse_error_response",
            "target_oa_applicant_token_provider=self._target_oa_applicant_token_provider",
            "oa_draft_client_for_batch=self._input_invoice_usage_oa_draft_client_for_batch",
            "int_or_none=self._int_or_none",
        ):
            if required not in factory_source:
                violations.append(f"Application OA reverse route factory is missing explicit port {required}")
        for required in (
            "/api/input-invoice-usage/oa-reverse/preview",
            "/api/input-invoice-usage/oa-reverse/staged-drafts",
            "/api/input-invoice-usage/oa-reverse/submitted-history",
            "/api/input-invoice-usage/oa-reverse/batches",
            "/api/input-invoice-usage/oa-reverse/oa-draft",
            "create_oa_draft_from_selection",
            "create_oa_draft",
            "revoke_oa_draft",
            "refresh_oa_status",
            "manual_oa_status",
        ):
            if required not in route_class:
                violations.append(f"OA reverse route owner is missing route/method marker {required}")
        if "_input_invoice_usage_oa_reverse_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("Application does not dispatch OA reverse routes through route owner")
        for removed_handler in (
            "def _handle_api_input_invoice_usage_oa_reverse_preview",
            "def _handle_api_input_invoice_usage_oa_reverse_batch_create",
            "def _handle_api_input_invoice_usage_oa_reverse_submitted_history",
            "def _handle_api_input_invoice_usage_oa_reverse_staged_drafts",
            "def _handle_api_input_invoice_usage_oa_reverse_batch_get",
            "def _handle_api_input_invoice_usage_oa_reverse_one_step_draft_create",
            "def _handle_api_input_invoice_usage_oa_reverse_draft_create",
            "def _handle_api_input_invoice_usage_oa_reverse_draft_revoke",
            "def _handle_api_input_invoice_usage_oa_reverse_status_refresh",
            "def _handle_api_input_invoice_usage_oa_reverse_manual_status",
        ):
            if removed_handler in server_source:
                violations.append(f"server.py still owns removed OA reverse handler {removed_handler}")

        self.assertEqual(violations, [])

    def test_input_invoice_usage_read_routes_use_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_input_invoice_usage.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        route_class = _class_source(route_tree, route_source, "InputInvoiceUsageApiRoutes")
        service_path = SERVICES_ROOT / "input_invoice_usage_service.py"
        service_source = service_path.read_text(encoding="utf-8")
        service_tree = _parse(service_path)
        service_class = _class_source(service_tree, service_source, "InputInvoiceUsageQueryService")
        payment_rules_source = (SERVICES_ROOT / "input_invoice_usage_payment_rules.py").read_text(encoding="utf-8")
        lifecycle_policy_source = (SERVICES_ROOT / "invoice_lifecycle_policy.py").read_text(encoding="utf-8")
        fresh_gate_source = (SERVICES_ROOT / "input_invoice_usage_read_model_fresh_gate_service.py").read_text(encoding="utf-8")
        factory_source = _function_source(server_tree, server_source, "_input_invoice_usage_routes")
        service_factory_source = _function_source(server_tree, server_source, "_input_invoice_usage_service")

        violations: list[str] = []
        if not route_class:
            violations.append("InputInvoiceUsageApiRoutes is missing")
        if not service_class:
            violations.append("InputInvoiceUsageQueryService is missing")
        if "StaticInputInvoiceUsagePaymentRulesProvider" in service_source:
            violations.append("Input usage query service still imports static payment rules fallback")
        if "StaticInputInvoiceUsagePaymentRulesProvider" in payment_rules_source:
            violations.append("Input usage payment rules module still defines static payment rules provider")
        if "StaticInputInvoiceUsagePaymentRulesProvider" in lifecycle_policy_source:
            violations.append("Invoice lifecycle policy still imports static input payment rules fallback")
        for required in (
            "payment_rules_provider is required for input invoice usage payment status rules",
            "input_invoice_usage_payment_rules_provider_required",
        ):
            if required not in service_class:
                violations.append(f"Input usage query service is missing explicit payment rules guard {required}")
        if "input_payment_rules_provider is required for input invoice usage payment evaluation" not in lifecycle_policy_source:
            violations.append("Invoice lifecycle policy is missing explicit input payment rules provider guard")
        if "payment_rules_provider=self._input_invoice_usage_payment_rules_provider()" not in service_factory_source:
            violations.append("Application input usage service factory must inject app-settings payment rules provider")
        for forbidden_service_marker in (
            "READ_MODEL_STATUS",
            '"live_query"',
            "'live_query'",
        ):
            if forbidden_service_marker in service_source:
                violations.append(f"Input usage query service keeps removed live read marker {forbidden_service_marker}")
        for forbidden in (
            "Application",
            "_handle_api_input_invoice_usage_rows",
            "_handle_api_input_invoice_usage_filter_options",
            "_handle_api_input_invoice_usage_invoice_detail",
            "_handle_api_input_invoice_usage_bank_transaction_detail",
            "_handle_api_input_invoice_usage_oa_detail",
            "_handle_api_input_invoice_usage_relation_details",
            "_handle_api_input_invoice_usage_payment_status_rules",
        ):
            if forbidden in route_source:
                violations.append(f"Input usage route owner leaks legacy/application ownership marker {forbidden}")
        for required in (
            "invoice_detail_loader=query_service.invoice_detail",
            "bank_transaction_detail_loader=query_service.bank_transaction_detail",
            "oa_detail_loader=query_service.oa_detail",
            "payment_status_rules_loader=query_service.payment_status_rules",
            "rows_from_sql_read_model=self._get_input_invoice_usage_rows_from_sql_read_model",
            "filter_options_from_sql_read_model=self._get_input_invoice_usage_filter_options_from_sql_read_model",
            "relation_details_from_sql_read_model=self._get_input_invoice_usage_relation_details_from_sql_read_model",
            "export_service=self._input_invoice_usage_export_service()",
            "resolve_read_session=self._resolve_fin_ops_read_session",
            "export_query_kwargs=self._input_invoice_usage_export_query_kwargs",
            "export_error_response=self._input_invoice_usage_export_error_response",
            "record_export_download=self._record_input_invoice_usage_export_download",
            "xlsx_response=self._input_invoice_usage_xlsx_response",
            "app_settings_service=self._app_settings_service",
            "load_json_body=self._load_json_body",
            "payment_rules_refreshes=self._enqueue_input_invoice_usage_payment_rules_refreshes",
            "payment_rules_error_response=self._input_invoice_usage_payment_rules_error_response",
            "json_response=self._json_response",
            "input_usage_error_response=self._input_invoice_usage_error_response",
        ):
            if required not in factory_source:
                violations.append(f"Application input usage route factory is missing explicit port {required}")
        for required in (
            "/api/input-invoice-usage/rows",
            "/api/input-invoice-usage/filter-options",
            "/api/input-invoice-usage/export-preview",
            "/api/input-invoice-usage/export",
            "/api/input-invoice-usage/payment-status-rules",
            "update_payment_status_rules",
            "/api/input-invoice-usage/invoices/",
            "/api/input-invoice-usage/bank-transactions/",
            "/api/input-invoice-usage/oa/",
            "/api/input-invoice-usage/rows/",
            "relation_details",
            "export_preview",
            "def export(",
        ):
            if required not in route_class:
                violations.append(f"Input usage route owner is missing route/method marker {required}")
        for forbidden_fallback in (
            "allow_live_fallback",
            "_allow_live_fallback",
            "_query_service",
            "query_service: InputInvoiceUsageQueryService",
            "query_service=",
            "self._query_service.list_rows",
            "self._query_service.filter_options",
            "self._query_service.row_relation_details",
        ):
            if forbidden_fallback in route_class or forbidden_fallback in factory_source:
                violations.append(f"Input usage route owner keeps removed live fallback {forbidden_fallback}")
        if "_input_invoice_usage_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("Application does not dispatch input usage read routes through route owner")
        for forbidden in (
            "def _load_input_invoice_usage_export_page(",
            "def _input_invoice_usage_export_query_from_kwargs(",
            "def _input_invoice_usage_sql_payload_requires_schema_refresh(",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still owns input usage fresh-gate implementation {forbidden}")
        for required in (
            "class InputInvoiceUsageReadModelFreshGateService",
            "source_version_mismatch_reasons",
            "require_expected_source_versions",
            "payload_requires_schema_refresh",
            "def export_page(",
            "def filter_options(",
            "def relation_details(",
        ):
            if required not in fresh_gate_source:
                violations.append(f"Input usage fresh-gate service is missing {required}")
        for forbidden in (
            "all_rows_from_sql_read_model=",
            "def _get_input_invoice_usage_all_rows_from_sql_read_model(",
            "def all_rows(",
            "self._query_service.list_rows(",
        ):
            if forbidden in route_source or forbidden in server_source or forbidden in fresh_gate_source:
                violations.append(f"Input usage read path keeps removed all-rows filter-options path {forbidden}")
        for forbidden_fresh_gate_dependency in (
            "query_service:",
            "query_service=",
            "self._query_service",
            "getattr(self._query_service",
        ):
            if forbidden_fresh_gate_dependency in fresh_gate_source:
                violations.append(f"Input usage fresh gate keeps removed query service dependency {forbidden_fresh_gate_dependency}")
        for removed_handler in (
            "def _handle_api_input_invoice_usage_rows(",
            "def _handle_api_input_invoice_usage_filter_options(",
            "def _handle_api_input_invoice_usage_export_preview(",
            "def _handle_api_input_invoice_usage_export(",
            "def _handle_api_input_invoice_usage_payment_status_rules_update(",
            "def _handle_api_input_invoice_usage_invoice_detail(",
            "def _handle_api_input_invoice_usage_bank_transaction_detail(",
            "def _handle_api_input_invoice_usage_oa_detail(",
            "def _handle_api_input_invoice_usage_relation_details(",
            "def _handle_api_input_invoice_usage_payment_status_rules(",
            "def _compat_input_invoice_usage_rows_response(",
            "def _compat_input_invoice_usage_relation_details_response(",
        ):
            if removed_handler in server_source:
                violations.append(f"server.py still owns removed input usage read handler {removed_handler}")

        self.assertEqual(violations, [])

    def test_batch_accounting_submit_has_no_direct_pair_write_fallback(self) -> None:
        path = SERVICES_ROOT / "batch_accounting_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        submit_source = _function_source(tree, source, "_submit_unlocked")

        violations: list[str] = []
        for forbidden in (
            "WorkbenchPairRelationService",
            "pair_relation_service",
            "_pair_relation_service",
        ):
            if forbidden in source:
                violations.append(f"BatchAccountingService keeps legacy pair relation dependency {forbidden}")
        for forbidden in (
            "replace_with_confirmed_relation",
            "_pair_relation_service.create_active_relation",
            "_pair_relation_service.record_history",
        ):
            if forbidden in submit_source:
                violations.append(f"BatchAccountingService.submit keeps direct pair write fallback {forbidden}")
        if "batch_accounting_relation_command_unavailable" not in submit_source:
            violations.append("BatchAccountingService.submit does not fail fast when relation command service is unavailable")

        self.assertEqual(violations, [])

    def test_batch_accounting_withdraw_has_no_direct_pair_write_fallback(self) -> None:
        path = SERVICES_ROOT / "batch_accounting_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        withdraw_source = _function_source(tree, source, "_withdraw_unlocked")

        violations: list[str] = []
        for forbidden in (
            "withdraw_latest_for_row_ids",
            "_pair_relation_service.create_active_relation",
            "_pair_relation_service.record_history",
        ):
            if forbidden in withdraw_source:
                violations.append(f"BatchAccountingService.withdraw keeps direct pair write fallback {forbidden}")
        if "batch_accounting_relation_command_unavailable" not in withdraw_source:
            violations.append("BatchAccountingService.withdraw does not fail fast when relation command service is unavailable")

        self.assertEqual(violations, [])

    def test_batch_accounting_legacy_repair_entrypoint_is_removed(self) -> None:
        path = SERVICES_ROOT / "batch_accounting_service.py"
        source = path.read_text(encoding="utf-8")

        violations: list[str] = []
        if "def repair_legacy_case_id_collisions" in source:
            violations.append("BatchAccountingService keeps removed legacy repair entrypoint")
        if "BATCH_ACCOUNTING_RELATION_REPAIR_ACTOR" in source:
            violations.append("BatchAccountingService keeps removed legacy repair actor")
        for helper in ("def _relation_history(", "def _active_relations(", "def _batch_relation_bank_row_id("):
            if helper in source:
                violations.append(f"BatchAccountingService keeps legacy repair-only helper {helper}")

        self.assertEqual(violations, [])

    def test_batch_accounting_route_handlers_do_not_bypass_service_boundaries(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        list_source = _function_source(tree, source, "_handle_api_batch_accounting")
        submit_source = _function_source(tree, source, "_handle_api_batch_accounting_submit")
        withdraw_source = _function_source(tree, source, "_handle_api_batch_accounting_withdraw")
        routes_path = APP_ROOT / "routes_batch_accounting.py"
        routes_source = routes_path.read_text(encoding="utf-8")
        routes_tree = _parse(routes_path)
        route_list_source = _function_source(routes_tree, routes_source, "list_payload")
        route_submit_source = _function_source(routes_tree, routes_source, "submit")
        route_withdraw_source = _function_source(routes_tree, routes_source, "withdraw")
        service_path = SERVICES_ROOT / "batch_accounting_service.py"
        service_source = service_path.read_text(encoding="utf-8")
        service_tree = _parse(service_path)
        submitted_relations_source = _function_source(service_tree, service_source, "_submitted_relations")
        unsubmitted_distribution_source = _function_source(
            service_tree,
            service_source,
            "_relation_distribution_row_id_sets",
        )
        submitted_distribution_source = _function_source(
            service_tree,
            service_source,
            "_distribution_rows_by_bank_id",
        )
        workbench_context_source = _function_source(service_tree, service_source, "_build_workbench_row_context")
        service_factory_source = _function_source(tree, source, "_batch_accounting_service")

        violations: list[str] = []
        if "def _repair_batch_accounting_relation_case_ids" in source:
            violations.append("server.py still defines unused batch accounting app-level repair helper")
        if "_batch_accounting_routes().list_payload" not in list_source:
            violations.append("GET /api/batch-accounting no longer delegates reads to BatchAccountingApiRoutes")
        if "_service_factory(use_sql_read_model=True).build_payload" not in route_list_source:
            violations.append("BatchAccountingApiRoutes no longer delegates reads to BatchAccountingService with SQL read model")
        for forbidden in (
            "_repair_batch_accounting_relation_case_ids",
            "repair_legacy_case_id_collisions",
            "_execute_derived_data_lifecycle_event",
            "_schedule_workbench_pair_relation_persist",
            "_schedule_workbench_read_model_persist",
            "_workbench_pair_relation_service",
            "_workbench_relation_command_service",
            "confirm_relation",
            "withdraw_relation",
            "replace_with_confirmed_relation",
            "withdraw_latest_for_row_ids",
        ):
            if forbidden in list_source:
                violations.append(f"GET /api/batch-accounting bypasses read-only route boundary via {forbidden}")
            if forbidden in route_list_source:
                violations.append(f"BatchAccountingApiRoutes list bypasses read-only route boundary via {forbidden}")
        if "list_batch_accounting_relations_by_year" not in submitted_relations_source:
            violations.append("submitted batch accounting list no longer uses the year-level relation DTO boundary")
        if "list_by_month" in submitted_relations_source:
            violations.append("submitted batch accounting list keeps legacy 12-month relation scan fallback")
        for distribution_source in (unsubmitted_distribution_source, submitted_distribution_source):
            if "get_batch_accounting_by_row_ids" not in distribution_source:
                violations.append("batch accounting relation distribution no longer uses its dedicated row read I/O")
            if 'getattr(self._relation_facade, "get_by_row_ids"' in distribution_source:
                violations.append("batch accounting relation distribution keeps the generic row read fallback")
        for forbidden in ("grouped_workbench_loader", "_build_api_workbench_payload"):
            if forbidden in service_source:
                violations.append(f"BatchAccountingService keeps full Workbench payload fallback {forbidden}")
            if forbidden in service_factory_source:
                violations.append(f"Application batch accounting wiring keeps full Workbench payload fallback {forbidden}")
        if "batch_accounting_workbench_read_model_unavailable" not in workbench_context_source:
            violations.append("BatchAccountingService does not fail closed when its dedicated Workbench loader is unavailable")
        for required_loader in (
            "load_batch_accounting_workbench_payload",
            "load_batch_accounting_submit_workbench_payload",
            "load_batch_accounting_submitted_bank_workbench_payload",
        ):
            if required_loader not in service_factory_source:
                violations.append(f"Application batch accounting wiring is missing dedicated loader {required_loader}")

        read_model_path = SERVICES_ROOT / "postgres_repositories" / "read_models.py"
        read_model_source = read_model_path.read_text(encoding="utf-8")
        read_model_tree = _parse(read_model_path)
        batch_loader_source = _function_source(
            read_model_tree,
            read_model_source,
            "_load_batch_accounting_workbench_payload",
        )
        invoice_loader_source = _function_source(
            read_model_tree,
            read_model_source,
            "_load_batch_accounting_invoice_rows",
        )
        if batch_loader_source.count("self._connection.fetch_all(") != 1:
            violations.append("batch accounting list candidate snapshot is no longer one repository I/O")
        if "_load_batch_accounting_invoice_rows" in batch_loader_source:
            violations.append("batch accounting list keeps the separate attachment round trip")
        for required_candidate_bound in (
            "oa_candidate_ids as materialized",
            "r.source_kind = 'oa_attachment_invoice'",
            "r.scope_key <> 'all'",
            "_BATCH_ACCOUNTING_INVOICE_CANDIDATE_MATCH_SQL",
        ):
            if required_candidate_bound not in batch_loader_source:
                violations.append(
                    f"batch accounting list attachment I/O is missing current OA bound {required_candidate_bound}"
                )
        for required_shared_match in (
            "from oa_candidate_ids candidate",
            "candidate.oa_row_id",
            "jsonb_array_elements",
        ):
            if required_shared_match not in read_model_source:
                violations.append(
                    f"batch accounting shared attachment match is missing candidate bound {required_shared_match}"
                )
        if "r.counterparty_name = %s" not in batch_loader_source:
            violations.append("batch accounting bank candidate read no longer uses the structured indexed counterparty field")
        for legacy_bank_filter in ("r.payload->>'counterparty_name'", "r.payload->>'counterparty_name_raw'"):
            if legacy_bank_filter in batch_loader_source:
                violations.append(f"batch accounting bank candidate read keeps legacy JSON fallback {legacy_bank_filter}")
        for required_oa_type_filter in (
            "coalesce(r.payload->>'apply_type', '')",
            "coalesce(r.payload->>'expense_type', '')",
            ") like %s",
        ):
            if required_oa_type_filter not in batch_loader_source:
                violations.append(f"batch accounting OA candidate read is missing indexed type expression {required_oa_type_filter}")
        if "r.payload->>'apply_type' like %s" in batch_loader_source or "r.payload->>'expense_type' like %s" in batch_loader_source:
            violations.append("batch accounting OA candidate read keeps the unindexed OR filter")
        for required_filter in (
            "normalized_oa_row_ids",
            "oa_candidate_ids as materialized",
            "select unnest(%s::text[])",
            "_BATCH_ACCOUNTING_INVOICE_CANDIDATE_MATCH_SQL",
        ):
            if required_filter not in invoice_loader_source:
                violations.append(f"batch accounting attachment loader is missing scoped filter {required_filter}")

        mutation_handlers = (
            (
                "submit",
                submit_source,
                route_submit_source,
                "_batch_accounting_routes().submit",
                "_service_factory(use_sql_read_model=True).submit",
            ),
            (
                "withdraw",
                withdraw_source,
                route_withdraw_source,
                "_batch_accounting_routes().withdraw",
                "_service_factory(use_sql_read_model=True).withdraw",
            ),
        )
        for name, handler_source, route_source, route_call, service_call in mutation_handlers:
            if "_batch_accounting_mutation_session" not in handler_source:
                violations.append(f"batch accounting {name} route no longer enforces mutation session")
            if route_call not in handler_source:
                violations.append(f"batch accounting {name} route no longer delegates mutation to BatchAccountingApiRoutes")
            if service_call not in route_source:
                violations.append(f"BatchAccountingApiRoutes {name} no longer delegates mutation to BatchAccountingService")
            if name == "submit":
                submit_unlocked_source = _function_source(service_tree, service_source, "_submit_unlocked")
                if "_build_submit_context(" not in submit_unlocked_source:
                    violations.append("BatchAccountingService submit no longer uses the submit context boundary")
                if "_build_list_context(" in submit_unlocked_source or "_context_with_candidate_relation_distribution(" in submit_unlocked_source:
                    violations.append("BatchAccountingService submit is polluted by list relation distribution context")
            for forbidden in (
                "repair_legacy_case_id_collisions",
                "_after_relation_mutation",
                "_execute_derived_data_lifecycle_event",
                "_schedule_workbench_pair_relation_persist",
                "_schedule_workbench_read_model_persist",
                "confirm_relation(",
                "withdraw_relation(",
                "replace_with_confirmed_relation",
                "withdraw_latest_for_row_ids",
                "create_active_relation",
                "record_history",
            ):
                if forbidden in handler_source:
                    violations.append(f"batch accounting {name} route bypasses service boundary via {forbidden}")
                if forbidden in route_source:
                    violations.append(f"BatchAccountingApiRoutes {name} bypasses service boundary via {forbidden}")

        self.assertEqual(violations, [])

    def test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback(self) -> None:
        path = SERVICES_ROOT / "turnover_ledger_write_adapters.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        port_source = _class_source(tree, source, "TurnoverLedgerWorkbenchPairPort")
        dirty_writer_source = _class_source(tree, source, "TurnoverLedgerDirtyOutboxWriter")
        local_dirty_writer_source = _class_source(tree, source, "TurnoverLedgerLocalDirtyOutboxWriter")
        uow_path = SERVICES_ROOT / "turnover_ledger_write_uow.py"
        uow_source = uow_path.read_text(encoding="utf-8")
        uow_tree = _parse(uow_path)
        uow_class_source = _class_source(uow_tree, uow_source, "TurnoverLedgerWriteUnitOfWork")

        violations: list[str] = []
        if "TurnoverLedgerRelationMutationInvalidationLegacyAdapter" in source:
            violations.append("turnover write adapters still expose removed relation mutation invalidation legacy adapter")
        for forbidden in (
            "pair_relation_service",
            "_pair_relation_service",
            "replace_with_confirmed_relation",
            "cancel_relation(case_id)",
            "_persist_pair_relations",
            "def _active_relation_by_case_id(",
        ):
            if forbidden in port_source:
                violations.append(f"TurnoverLedgerWorkbenchPairPort keeps broad pair service surface {forbidden}")
        if "workbench_relation_command_unavailable" not in port_source:
            violations.append("TurnoverLedgerWorkbenchPairPort does not fail fast when relation command service is unavailable")
        if "enqueue_read_model_refreshes_in_transaction" not in dirty_writer_source:
            violations.append("TurnoverLedgerDirtyOutboxWriter does not use transaction-bound batch enqueue")
        if ".enqueue_refresh(" in uow_class_source:
            violations.append("TurnoverLedgerWriteUnitOfWork keeps per-request refresh enqueue")
        for name, writer_source in (
            ("TurnoverLedgerDirtyOutboxWriter", dirty_writer_source),
            ("TurnoverLedgerLocalDirtyOutboxWriter", local_dirty_writer_source),
        ):
            if "def enqueue_refreshes(" not in writer_source:
                violations.append(f"{name} does not expose the batched refresh contract")
            if "def enqueue_refresh(" in writer_source:
                violations.append(f"{name} keeps the removed single-refresh contract")

        self.assertEqual(violations, [])

    def test_workbench_matching_uses_formal_relation_uow_not_broad_pair_service(self) -> None:
        checks = {
            "backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py": (
                "WorkbenchMatchingOrchestrator",
                "WorkbenchFormalRelationCommand",
            ),
        }
        violations: list[str] = []
        for rel_path, (class_name, required_port) in checks.items():
            path = REPO_ROOT / rel_path
            source = path.read_text(encoding="utf-8")
            tree = _parse(path)
            class_source = _class_source(tree, source, class_name)
            if required_port not in source:
                violations.append(f"{rel_path} does not expose/use {required_port}")
            for forbidden in (
                "WorkbenchPairRelationService",
                "pair_relation_service:",
                "pair_relation_service=",
                "self._pair_relation_service",
                "_pair_relation_service.",
            ):
                if forbidden in class_source:
                    violations.append(f"{class_name} keeps broad pair relation dependency {forbidden}")

        runtime_path = SERVICES_ROOT / "runtime_worker_handlers.py"
        runtime_source = runtime_path.read_text(encoding="utf-8")
        runtime_tree = _parse(runtime_path)
        factory_source = _class_source(runtime_tree, runtime_source, "WorkbenchMatchingWorkerFactory")
        if "matching_orchestrator=WorkbenchMatchingOrchestrator(" not in factory_source:
            violations.append("WorkbenchMatchingWorkerFactory no longer constructs WorkbenchMatchingOrchestrator")
        else:
            orchestrator_call = factory_source.split("matching_orchestrator=WorkbenchMatchingOrchestrator(", 1)[1]
            orchestrator_call = orchestrator_call.split("),\n            source_versions_provider", 1)[0]
            if "pair_relation_service=" in orchestrator_call:
                violations.append("WorkbenchMatchingWorkerFactory passes stale pair_relation_service keyword to orchestrator")

        self.assertEqual(violations, [])

    def test_server_workbench_payload_relation_reads_use_payload_read_port(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        port_source = (SERVICES_ROOT / "workbench_payload_relation_read_port.py").read_text(encoding="utf-8")

        checked_sources = {
            "_resolve_live_rows_direct": _function_source(tree, source, "_resolve_live_rows_direct")
        }
        violations: list[str] = []
        if "class WorkbenchPayloadRelationReadPort" not in port_source:
            violations.append("Workbench payload relation read port is missing")
        if "from fin_ops_platform.services.workbench_payload_relation_read_port import WorkbenchPayloadRelationReadPort" not in source:
            violations.append("Application does not import WorkbenchPayloadRelationReadPort")
        if "def _workbench_payload_relation_read_port(self) -> WorkbenchPayloadRelationReadPort" not in source:
            violations.append("Application does not expose Workbench payload relation read port factory")
        for method_name, method_source in checked_sources.items():
            if "_workbench_pair_relation_service" in method_source:
                violations.append(f"{method_name} still reads broad pair relation service directly")
            if "_workbench_payload_relation_read_port()" not in method_source:
                violations.append(f"{method_name} does not use Workbench payload relation read port")
        if "get_active_relation_by_row_id" not in port_source:
            violations.append("WorkbenchPayloadRelationReadPort is missing get_active_relation_by_row_id")
        if "list_active_relations" in port_source:
            violations.append("WorkbenchPayloadRelationReadPort retains unused broad list_active_relations I/O")

        self.assertEqual(violations, [])

    def test_server_source_versions_use_relation_source_version_provider(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        provider_source = (SERVICES_ROOT / "workbench_relation_source_version_provider.py").read_text(encoding="utf-8")
        checked_sources = {
            method_name: _function_source(tree, source, method_name)
            for method_name in (
                "_bank_batch_workbench_source_versions",
                "_workbench_read_model_source_versions",
            )
        }

        violations: list[str] = []
        if "class WorkbenchRelationSourceVersionProvider" not in provider_source:
            violations.append("Workbench relation source version provider is missing")
        if "from fin_ops_platform.services.workbench_relation_source_version_provider import WorkbenchRelationSourceVersionProvider" not in source:
            violations.append("Application does not import WorkbenchRelationSourceVersionProvider")
        if "def _workbench_relation_source_version_provider(self) -> WorkbenchRelationSourceVersionProvider" not in source:
            violations.append("Application does not expose Workbench relation source version provider")
        for method_name, method_source in checked_sources.items():
            if "_workbench_pair_relation_service.snapshot" in method_source:
                violations.append(f"{method_name} still reads pair relation snapshot directly")
            if "pair_relation_snapshot_version()" not in method_source:
                violations.append(f"{method_name} does not use relation source version provider")

        self.assertEqual(violations, [])

    def test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback(self) -> None:
        path = SERVICES_ROOT / "workbench_write_facade.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        checked_sources = {
            method_name: _function_source(tree, source, method_name)
            for method_name in (
                "confirm_link",
                "_confirm_link_with_uow",
                "cancel_link",
                "_cancel_link_with_uow",
            )
        }

        violations: list[str] = []
        for method_name, method_source in checked_sources.items():
            if (
                "_relation_command_unavailable_result" not in method_source
                and "workbench_relation_command_unavailable" not in method_source
            ):
                violations.append(f"{method_name} does not fail fast when relation command service is unavailable")
            for forbidden in (
                "replace_with_confirmed_relation",
                "cancel_relation_for_row_id",
                "_persist_pair_relations_in_transaction(",
            ):
                if forbidden in method_source:
                    violations.append(f"{method_name} keeps direct pair relation fallback {forbidden}")

        self.assertEqual(violations, [])

    def test_workbench_confirm_uow_does_not_use_legacy_snapshot_rollback_io(self) -> None:
        path = SERVICES_ROOT / "workbench_write_facade.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_confirm_link_with_uow")

        self.assertNotIn("_relation_read_snapshot_port.snapshot", method_source)
        self.assertNotIn("_restore_pair_relation_snapshot", method_source)

    def test_workbench_write_facade_relation_reads_and_cash_special_mutations_use_ports(self) -> None:
        path = SERVICES_ROOT / "workbench_write_facade.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        facade_source = _class_source(tree, source, "WorkbenchWriteFacade")
        read_port_source = _class_source(tree, source, "WorkbenchWriteRelationReadSnapshotPort")
        metadata_port_source = _class_source(tree, source, "WorkbenchWriteRelationSpecialMetadataMutationPort")
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        factory_source = _function_source(server_tree, server_source, "_workbench_write_facade")

        violations: list[str] = []
        if "WorkbenchWriteRelationReadSnapshotPort" not in source:
            violations.append("WorkbenchWriteFacade module lacks explicit relation read/snapshot port")
        if "_relation_read_snapshot_port" not in facade_source:
            violations.append("WorkbenchWriteFacade does not store relation read/snapshot port")
        if "pair_relation_service:" in facade_source or "pair_relation_service=" in factory_source:
            violations.append("WorkbenchWriteFacade still accepts broad pair_relation_service instead of required ports")
        for forbidden in (
            "_pair_relation_service.active_relations_for_row_ids",
            "_pair_relation_service.get_active_relation_by_row_id",
            "_pair_relation_service.preview_withdraw_for_row_ids",
            "_pair_relation_service.snapshot",
        ):
            if forbidden in facade_source:
                violations.append(f"WorkbenchWriteFacade keeps direct pair read/snapshot call {forbidden}")
        for required in (
            "active_relations_for_row_ids",
            "get_active_relation_by_row_id",
            "preview_withdraw_for_row_ids",
            "snapshot",
        ):
            if required not in read_port_source:
                violations.append(f"WorkbenchWriteRelationReadSnapshotPort is missing {required}")
        if "relation_read_snapshot_port=WorkbenchWriteRelationReadSnapshotPort(" not in factory_source:
            violations.append("Application does not inject WorkbenchWriteRelationReadSnapshotPort")
        if "WorkbenchWriteRelationSpecialMetadataMutationPort" not in source:
            violations.append("WorkbenchWriteFacade module lacks explicit special metadata mutation port")
        if "_relation_special_metadata_mutation_port" not in facade_source:
            violations.append("WorkbenchWriteFacade does not store special metadata mutation port")
        for forbidden in (
            "_pair_relation_service.update_special_metadata_for_row_ids",
            "_pair_relation_service.clear_special_metadata_for_row_ids",
        ):
            if forbidden in facade_source:
                violations.append(f"WorkbenchWriteFacade keeps direct pair special metadata mutation {forbidden}")
        for required in (
            "update_special_metadata_for_row_ids",
            "clear_special_metadata_for_row_ids",
        ):
            if required not in metadata_port_source:
                violations.append(f"WorkbenchWriteRelationSpecialMetadataMutationPort is missing {required}")
        if "relation_special_metadata_mutation_port=WorkbenchWriteRelationSpecialMetadataMutationPort(" not in factory_source:
            violations.append("Application does not inject WorkbenchWriteRelationSpecialMetadataMutationPort")

        self.assertEqual(violations, [])

    def test_workbench_personal_advance_repayment_uses_relation_command_boundary(self) -> None:
        path = SERVICES_ROOT / "workbench_write_facade.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "confirm_personal_advance_repayment")

        violations: list[str] = []
        if "confirm_relation" not in method_source:
            violations.append("confirm_personal_advance_repayment does not delegate relation creation to command service")
        if "_relation_command_unavailable_result" not in method_source:
            violations.append("confirm_personal_advance_repayment does not fail fast when relation command service is unavailable")
        for forbidden in (
            "replace_with_confirmed_relation",
            "create_active_relation",
            "_persist_pair_relations_in_transaction(",
        ):
            if forbidden in method_source:
                violations.append(f"confirm_personal_advance_repayment keeps direct pair relation fallback {forbidden}")

        self.assertEqual(violations, [])

    def test_workbench_exception_application_uses_relation_command_boundary(self) -> None:
        service_path = SERVICES_ROOT / "workbench_exception_application_service.py"
        service_source = service_path.read_text(encoding="utf-8")
        service_tree = _parse(service_path)
        apply_source = _function_source(service_tree, service_source, "apply")
        create_relation_source = _function_source(service_tree, service_source, "_create_pair_relation")

        app_path = APP_ROOT / "server.py"
        app_source = app_path.read_text(encoding="utf-8")
        app_tree = _parse(app_path)
        factory_source = _function_source(app_tree, app_source, "_configure_workbench_exception_application_service")

        violations: list[str] = []
        if "_require_relation_command_service()" not in apply_source:
            violations.append("Workbench exception apply does not fail fast when relation command service is unavailable")
        if "assert_write_precondition" not in apply_source:
            violations.append("Workbench exception apply lacks relation freshness preflight before local case creation")
        for forbidden in (
            "WorkbenchPairRelationService",
            "pair_relation_service:",
            "_pair_relation_service",
        ):
            if forbidden in service_source:
                violations.append(f"Workbench exception application keeps legacy pair relation dependency {forbidden}")
        if "confirm_relation" not in create_relation_source:
            violations.append("Workbench exception relation creation does not delegate writes to command service")
        for forbidden in (
            "create_active_relation",
            "replace_with_confirmed_relation",
            "_pair_relation_service.",
        ):
            if forbidden in create_relation_source:
                violations.append(f"Workbench exception relation creation keeps direct pair write fallback {forbidden}")
        if "relation_command_service=self._workbench_relation_command_service()" not in factory_source:
            violations.append("Application does not inject WorkbenchRelationCommandService into WorkbenchExceptionApplicationService")

        self.assertEqual(violations, [])

    def test_workbench_oa_attachment_context_row_index_extraction_stays_local(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        index_source = (SERVICES_ROOT / "workbench_oa_attachment_context_row_index.py").read_text(encoding="utf-8")
        context_source = _function_source(
            server_tree,
            server_source,
            "_cached_oa_attachment_context_row_ids",
        )
        factory_source = _function_source(server_tree, server_source, "_workbench_oa_attachment_context_row_index")
        violations: list[str] = []

        for marker in (
            "_workbench_oa_attachment_context_row_index()",
            "grouped_payload_rows_by_id(payload)",
            "attachment_row_ids_by_oa_id(rows_by_id)",
            "invoice_row_is_attachment_context",
        ):
            if marker not in context_source:
                violations.append(f"Confirm-link OA attachment context lookup missing marker: {marker}")
        for marker in (
            "class WorkbenchOaAttachmentContextRowIndex",
            "def grouped_payload_rows_by_id(",
            "def attachment_row_ids_by_oa_id(",
            "def invoice_row_is_attachment_context(",
            "def oa_id_from_attachment_invoice_id(",
            "attachment_parent_oa_id",
            "attachment_matches_oa",
            "attachment_row_id_matches_oa",
            "oa_source_ids",
            "source_kind",
            "oa_attachment_invoice",
            "derived_from_oa_id",
        ):
            if marker not in index_source:
                violations.append(f"WorkbenchOaAttachmentContextRowIndex missing marker: {marker}")
        for forbidden in (
            "def raw_payload_rows_by_id(",
            "def raw_payload_row_ids(",
            "def _raw_payload_sections(",
        ):
            if forbidden in index_source:
                violations.append(f"WorkbenchOaAttachmentContextRowIndex retains raw payload surface: {forbidden}")
        for marker in (
            "WorkbenchOaAttachmentContextRowIndex(",
            "attachment_parent_oa_id=oa_attachment_parent_oa_id",
            "attachment_matches_oa=oa_attachment_matches_oa",
            "attachment_row_id_matches_oa=oa_attachment_row_id_matches_oa",
            "oa_source_ids=oa_row_source_ids",
        ):
            if marker not in factory_source:
                violations.append(f"Application row index factory missing explicit dependency: {marker}")
        for forbidden in (
            "Response",
            "HTTPStatus",
            "_json_response",
            "ReadModelRefreshGateway",
            "outbox",
            "clear_cache",
            "set_cached",
            "save_workbench",
            "app.auth",
            "server.py",
            "MongoOAAdapter",
        ):
            if forbidden in index_source:
                violations.append(f"WorkbenchOaAttachmentContextRowIndex gained forbidden dependency: {forbidden}")

        self.assertEqual(violations, [])

    def test_server_confirm_link_context_uses_relation_read_port(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_expand_confirm_link_row_ids_for_existing_context")
        port_source = (SERVICES_ROOT / "workbench_confirm_link_context_relation_read_port.py").read_text(encoding="utf-8")

        violations: list[str] = []
        if "class WorkbenchConfirmLinkContextRelationReadPort" not in port_source:
            violations.append("Workbench confirm-link context relation read port is missing")
        if "def active_relations_for_row_ids" not in port_source:
            violations.append("WorkbenchConfirmLinkContextRelationReadPort does not expose active_relations_for_row_ids")
        if "_workbench_pair_relation_service.active_relations_for_row_ids" in method_source:
            violations.append("_expand_confirm_link_row_ids_for_existing_context still reads broad pair service directly")
        if "_workbench_confirm_link_context_relation_read_port()" not in method_source:
            violations.append("_expand_confirm_link_row_ids_for_existing_context does not use confirm-link context relation read port")
        if "_normalize_row_ids(row_ids)" not in method_source:
            violations.append("_expand_confirm_link_row_ids_for_existing_context no longer normalizes selected row ids")
        if "_cached_existing_context_groups_for_row_ids" not in method_source:
            violations.append("_expand_confirm_link_row_ids_for_existing_context no longer preserves cached existing context expansion")
        if "_confirm_link_context_row_ids_to_preserve" not in method_source:
            violations.append("_expand_confirm_link_row_ids_for_existing_context no longer preserves context row-id filter")

        self.assertEqual(violations, [])

    def test_server_case_id_allocation_uses_allocator(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_next_workbench_relation_case_id")
        allocator_source = (SERVICES_ROOT / "workbench_relation_case_id_allocator.py").read_text(encoding="utf-8")

        violations: list[str] = []
        if "class WorkbenchRelationCaseIdAllocator" not in allocator_source:
            violations.append("Workbench relation case-id allocator is missing")
        if "def next_case_id" not in allocator_source:
            violations.append("WorkbenchRelationCaseIdAllocator does not expose next_case_id")
        if "pair_relations" in method_source:
            violations.append("_next_workbench_relation_case_id still parses pair relation snapshot shape")
        if "_workbench_pair_relation_service.snapshot()" in method_source:
            violations.append("_next_workbench_relation_case_id still reads relation snapshot directly")
        if "WorkbenchRelationCaseIdAllocator(" not in method_source:
            violations.append("_next_workbench_relation_case_id does not use WorkbenchRelationCaseIdAllocator")
        if "relation_snapshot_provider=self._workbench_pair_relation_service.snapshot" not in method_source:
            violations.append("_next_workbench_relation_case_id does not pass relation snapshot provider")
        if "next_case_id=self._workbench_override_service._next_case_id" not in method_source:
            violations.append("_next_workbench_relation_case_id does not preserve override case-id source")
        if "pair_relations" not in allocator_source:
            violations.append("WorkbenchRelationCaseIdAllocator does not inspect relation case ids")

        self.assertEqual(violations, [])

    def test_transaction_pair_relation_persist_uses_relation_repository_owner(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_persist_workbench_pair_relations_in_transaction")

        violations: list[str] = []
        if "PostgresWorkbenchRelationRepository(transaction).save_workbench_pair_relations(" not in method_source:
            violations.append("transaction pair relation persist does not use PostgresWorkbenchRelationRepository")
        if "PostgresWorkbenchRepository(transaction).save_workbench_pair_relations(" in method_source:
            violations.append("transaction pair relation persist still uses broad PostgresWorkbenchRepository")

        self.assertEqual(violations, [])

    def test_workbench_uow_pair_relation_repository_disables_repository_fanout(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_workbench_uow_repository_factory")

        violations: list[str] = []
        if "PostgresWorkbenchRelationRepository(transaction, enqueue_refreshes=False)" not in method_source:
            violations.append("Workbench UoW repository factory must disable repository read-model fan-out")
        if "PostgresWorkbenchRelationRepository(transaction)" in method_source:
            violations.append("Workbench UoW repository factory still uses default repository fan-out")

        self.assertEqual(violations, [])

    def test_broad_persist_state_does_not_serialize_pair_relations(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_persist_state")

        violations: list[str] = []
        if '"workbench_pair_relations"' in method_source:
            violations.append("_persist_state still serializes Workbench pair relation facts")
        if "_workbench_pair_relation_service.snapshot()" in method_source:
            violations.append("_persist_state still snapshots Workbench pair relation service")
        if "save_workbench_pair_relations(" in method_source:
            violations.append("_persist_state still writes Workbench pair relations directly")

        self.assertEqual(violations, [])

    def test_workbench_relation_command_repository_uses_explicit_snapshot_adapter(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        factory_source = _function_source(server_tree, server_source, "_workbench_relation_command_repository")
        adapter_path = SERVICES_ROOT / "workbench_relation_command_repository_adapter.py"
        adapter_source = adapter_path.read_text(encoding="utf-8") if adapter_path.exists() else ""
        violations: list[str] = []

        for removed_helper in (
            "_save_workbench_relation_command_snapshot",
            "_apply_workbench_relation_command_snapshot",
            "_relation_history_touches_cases",
        ):
            if _function_source(server_tree, server_source, removed_helper):
                violations.append(f"server.py still owns removed relation command repository helper {removed_helper}")
        if "WorkbenchRelationCommandRepositoryAdapter(" not in factory_source:
            violations.append("relation command repository factory does not build explicit adapter")
        if "CallbackWorkbenchRelationRepository(" in factory_source:
            violations.append("relation command repository factory still builds callback repository inline")
        for snippet in (
            "class WorkbenchRelationCommandRepositoryAdapter",
            "def load_workbench_pair_relations(",
            "def save_workbench_pair_relations(",
            "self._pair_relation_service._pair_relations",
            "self._after_apply()",
        ):
            if snippet not in adapter_source:
                violations.append(f"relation command repository adapter missing behavior {snippet}")

        self.assertEqual(violations, [])

    def test_workbench_pair_relation_persist_uses_explicit_service_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        service_path = SERVICES_ROOT / "workbench_pair_relation_persist_service.py"
        service_source = service_path.read_text(encoding="utf-8") if service_path.exists() else ""
        factory_source = _function_source(server_tree, server_source, "_workbench_pair_relation_persist_service")
        persist_source = _function_source(server_tree, server_source, "_persist_workbench_pair_relations")
        schedule_source = _function_source(server_tree, server_source, "_schedule_workbench_pair_relation_persist")
        background_source = _function_source(server_tree, server_source, "_persist_workbench_pair_relations_in_background")
        violations: list[str] = []

        if "WorkbenchPairRelationPersistService(" not in factory_source:
            violations.append("server.py does not build explicit pair relation persist service")
        if ".persist(changed_case_ids=changed_case_ids)" not in persist_source:
            violations.append("pair relation persist wrapper does not delegate to service.persist")
        if ".schedule(" not in schedule_source:
            violations.append("pair relation schedule wrapper does not delegate to service.schedule")
        if ".persist_in_background(" not in background_source:
            violations.append("pair relation background wrapper does not delegate to service.persist_in_background")
        for forbidden in (
            "save_workbench_pair_relations(",
            "_pending_workbench_pair_relation_case_ids.update",
            "Thread(",
            "_emit_workbench_action_timing(",
        ):
            if forbidden in persist_source or forbidden in schedule_source or forbidden in background_source:
                violations.append(f"server.py pair relation persist wrapper still owns behavior {forbidden}")
        for snippet in (
            "class WorkbenchPairRelationPersistService",
            "def persist(",
            "def schedule(",
            "def persist_in_background(",
            "phase=\"persist_pair_relations\"",
            "self._thread_factory(",
        ):
            if snippet not in service_source:
                violations.append(f"pair relation persist service missing behavior {snippet}")

        self.assertEqual(violations, [])

    def test_workbench_pair_relation_restore_uses_explicit_service_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        service_path = SERVICES_ROOT / "workbench_pair_relation_rollback_restore_service.py"
        service_source = service_path.read_text(encoding="utf-8") if service_path.exists() else ""
        wrapper_source = _function_source(server_tree, server_source, "_restore_workbench_pair_relation_snapshot")
        factory_source = _function_source(server_tree, server_source, "_workbench_pair_relation_rollback_restore_service")
        replace_source = _function_source(server_tree, server_source, "_replace_workbench_pair_relation_service")
        violations: list[str] = []

        if "WorkbenchPairRelationRollbackRestoreService(" not in factory_source:
            violations.append("server.py does not build explicit pair relation rollback restore service")
        if ".restore(" not in wrapper_source:
            violations.append("pair relation rollback wrapper does not delegate to service.restore")
        for forbidden in (
            "WorkbenchPairRelationService.from_snapshot",
            "save_workbench_pair_relations(",
            "_configure_workbench_exception_application_service()",
        ):
            if forbidden in wrapper_source:
                violations.append(f"server.py pair relation restore wrapper still owns behavior {forbidden}")
        if 'delattr(self, "_workbench_pair_relation_persist_service_instance")' not in replace_source:
            violations.append("pair relation service replacement does not clear cached persist service")
        for snippet in (
            "class WorkbenchPairRelationRollbackRestoreService",
            "def restore(",
            "WorkbenchPairRelationService.from_snapshot(snapshot)",
            "self._replace_pair_relation_service(restored_service)",
            "self._configure_exception_application_service()",
            "save_workbench_pair_relations(",
        ):
            if snippet not in service_source:
                violations.append(f"pair relation rollback restore service missing behavior {snippet}")

        self.assertEqual(violations, [])

    def test_batch_accounting_pair_relation_restore_uses_shared_pair_relation_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        wrapper_source = _function_source(server_tree, server_source, "_restore_workbench_pair_relation_snapshot")
        factory_source = _function_source(server_tree, server_source, "_workbench_pair_relation_rollback_restore_service")
        facade_source = _function_source(server_tree, server_source, "_workbench_write_facade")
        violations: list[str] = []

        if "_restore_batch_accounting_pair_relation_snapshot" in server_source:
            violations.append("batch accounting still has a dedicated pair relation restore wrapper")
        if "_batch_accounting_pair_relation_rollback_restore_service" in server_source:
            violations.append("batch accounting still has a dedicated pair relation restore service factory")
        if "restore_pair_relation_snapshot=self._restore_workbench_pair_relation_snapshot" not in facade_source:
            violations.append("Workbench facade does not inject the shared pair relation restore boundary")
        if "_workbench_pair_relation_rollback_restore_service().restore(" not in wrapper_source:
            violations.append("shared pair relation restore wrapper does not delegate to service.restore")
        for forbidden in (
            "WorkbenchPairRelationService.from_snapshot",
            "_configure_workbench_exception_application_service()",
            "save_workbench_pair_relations(",
        ):
            if forbidden in wrapper_source:
                violations.append(f"shared pair relation restore wrapper still owns behavior {forbidden}")
        if "WorkbenchPairRelationRollbackRestoreService(" not in factory_source:
            violations.append("server.py does not build shared pair relation rollback restore service")
        if "state_store=self._state_store" not in factory_source:
            violations.append("shared pair relation rollback restore service no longer uses the canonical state store")
        if "replace_pair_relation_service=self._replace_workbench_pair_relation_service" not in factory_source:
            violations.append("shared pair relation rollback restore service does not use shared pair service replacement")
        if (
            "configure_exception_application_service=self._configure_workbench_exception_application_service"
            not in factory_source
        ):
            violations.append("shared pair relation rollback restore service does not reconfigure exception application service")

        self.assertEqual(violations, [])

    def test_workbench_exception_restore_uses_explicit_service_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        service_path = SERVICES_ROOT / "workbench_exception_rollback_restore_service.py"
        service_source = service_path.read_text(encoding="utf-8") if service_path.exists() else ""
        factory_source = _function_source(server_tree, server_source, "_workbench_exception_rollback_restore_service")
        wrapper_sources = [
            _function_source(server_tree, server_source, name)
            for name in (
                "_restore_workbench_exception_write_snapshots",
                "_restore_workbench_exception_pair_snapshots",
                "_restore_workbench_exception_override_snapshots",
            )
        ]
        inline_restore_sources = [
            _function_source(server_tree, server_source, name)
            for name in (
                "_apply_workbench_exception_application",
                "_persist_workbench_exception_and_override_change",
            )
        ]
        violations: list[str] = []

        if "WorkbenchExceptionRollbackRestoreService(" not in factory_source:
            violations.append("server.py does not build explicit exception rollback restore service")
        for source in wrapper_sources:
            if "restore_" not in source:
                violations.append("exception restore wrapper does not delegate to service restore method")
            for forbidden in (
                "WorkbenchExceptionCaseService.from_snapshot",
                "WorkbenchOverrideService.from_snapshot",
                "save_workbench_exception_cases(",
            ):
                if forbidden in source:
                    violations.append(f"server.py exception restore wrapper still owns behavior {forbidden}")
        for source in inline_restore_sources:
            if "_workbench_exception_rollback_restore_service().restore_" not in source:
                violations.append("exception inline restore path does not delegate to rollback restore service")
            for forbidden in (
                "WorkbenchExceptionCaseService.from_snapshot",
                "WorkbenchOverrideService.from_snapshot",
                "save_workbench_exception_cases(previous_exception_snapshot)",
            ):
                if forbidden in source:
                    violations.append(f"server.py exception inline restore still owns behavior {forbidden}")
        for snippet in (
            "class WorkbenchExceptionRollbackRestoreService",
            "def restore_write_snapshots(",
            "def restore_pair_snapshots(",
            "def restore_override_snapshots(",
            "WorkbenchExceptionCaseService.from_snapshot(previous_exception_snapshot)",
            "WorkbenchPairRelationService.from_snapshot(previous_pair_snapshot)",
            "WorkbenchOverrideService.from_snapshot(previous_override_snapshot)",
            "save_workbench_exception_cases(",
        ):
            if snippet not in service_source:
                violations.append(f"exception rollback restore service missing behavior {snippet}")

        self.assertEqual(violations, [])

    def test_no_oa_read_model_refresh_does_not_run_relation_repairs(self) -> None:
        path = SERVICES_ROOT / "no_oa_bank_batch_read_model_refresh.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        handler_source = _function_source(tree, source, "handle_runtime_event")

        violations: list[str] = []
        if "class NoOaBankBatchReadModelPersistencePort" not in source:
            violations.append("No-OA read model refresh persistence port is missing")
        if "save_public_snapshot" not in handler_source:
            violations.append("No-OA read model refresh must persist through the explicit persistence boundary")
        if "apply_relation_repairs=False" not in handler_source:
            violations.append("No-OA read model refresh must call refresh_batches with apply_relation_repairs=False")
        for forbidden in (
            "save_no_oa_bank_batches",
            "save_workbench_pair_relations",
            "save_no_oa_bank_batch_mutation",
            "create_active_relation",
            "cancel_relation",
        ):
            if forbidden in handler_source:
                violations.append(f"No-OA read model refresh keeps relation write side effect {forbidden}")

        self.assertEqual(violations, [])

    def test_no_oa_list_read_model_uses_repository_port(self) -> None:
        path = SERVICES_ROOT / "no_oa_bank_batch_application_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        list_source = _function_source(tree, source, "list_batches_payload")

        violations: list[str] = []
        if "NoOaBankBatchReadModelRepositoryPort" not in source:
            violations.append("No-OA application service must import the read model repository port")
        if "_no_oa_bank_batch_read_model_repository" not in list_source:
            violations.append("No-OA list path must read through the dedicated no-OA read model repository port")
        if "_workbench_sql_read_repository" in list_source:
            violations.append("No-OA list path must not read through broad workbench_sql_read_repository")

        self.assertEqual(violations, [])

    def test_no_oa_mutation_persistence_requires_atomic_boundary(self) -> None:
        path = SERVICES_ROOT / "no_oa_bank_batch_application_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        persist_source = _function_source(tree, source, "persist_mutation")

        violations: list[str] = []
        if "save_no_oa_bank_batch_mutation" not in persist_source:
            violations.append("No-OA mutation persistence must call the explicit atomic mutation boundary")
        for forbidden in (
            "save_workbench_pair_relations",
            "save_no_oa_bank_batches",
            "save_workbench_read_models",
        ):
            if forbidden in persist_source:
                violations.append(f"No-OA mutation persistence still falls back to broad state-store write {forbidden}")

        self.assertEqual(violations, [])

    def test_bank_account_balance_derived_lifecycle_uses_explicit_executor_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        executor_path = SERVICES_ROOT / "bank_account_balance_derived_lifecycle_executor.py"
        executor_source = executor_path.read_text(encoding="utf-8")

        violations: list[str] = []
        removed_helper = "_derived_lifecycle_bank_account_balance_executor"
        if _function_source(server_tree, server_source, removed_helper):
            violations.append(f"server.py still owns removed bank account balance derived lifecycle helper {removed_helper}")
        if "BankAccountBalanceDerivedLifecycleExecutor(" not in server_source:
            violations.append("server.py does not assemble BankAccountBalanceDerivedLifecycleExecutor")
        if '"bank_account_balance_read_model": self._bank_account_balance_derived_lifecycle_executor().execute' not in server_source:
            violations.append("derived lifecycle registry does not use the explicit bank account balance executor")
        if "class BankAccountBalanceDerivedLifecycleExecutor" not in executor_source:
            violations.append("BankAccountBalanceDerivedLifecycleExecutor is missing")
        if "bank_account_balance.read_model.refresh" not in executor_source or '"invalidated_scopes": ["all"]' not in executor_source:
            violations.append("BankAccountBalanceDerivedLifecycleExecutor does not preserve all-only payload shape")

        self.assertEqual(violations, [])

    def test_bank_account_balance_accounts_path_does_not_fallback_to_bank_detail_port(self) -> None:
        bank_detail_port_source = (SERVICES_ROOT / "bank_detail_read_model_repository.py").read_text(encoding="utf-8")
        service_path = SERVICES_ROOT / "bank_details_application_service.py"
        service_source = service_path.read_text(encoding="utf-8")
        service_tree = _parse(service_path)
        accounts_source = _function_source(service_tree, service_source, "_accounts_from_sql_read_model")

        violations: list[str] = []
        if "def list_bank_account_balances" in bank_detail_port_source:
            violations.append("BankDetailReadModelRepositoryPort still exposes bank account balance read model access")
        if "self._bank_account_balance_read_model_repository or self._bank_detail_sql_read_repository" in accounts_source:
            violations.append("Bank Details accounts SQL read path still falls back to Bank Detail repository port")
        if "_bank_detail_sql_read_repository" in accounts_source and "api_sql_repository_unavailable" not in accounts_source:
            violations.append("Bank Details accounts path has an unclassified Bank Detail repository reference")

        self.assertEqual(violations, [])

    def test_no_oa_source_version_helpers_stay_out_of_application(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)

        violations: list[str] = []
        for removed_helper in (
            "_no_oa_bank_batch_source_versions",
            "_no_oa_bank_batch_stale_reasons",
        ):
            if _function_source(tree, source, removed_helper):
                violations.append(f"server.py still owns removed no-OA helper {removed_helper}")

        service_source = (SERVICES_ROOT / "no_oa_bank_batch_application_service.py").read_text(encoding="utf-8")
        if "def no_oa_bank_batch_source_versions(" not in service_source:
            violations.append("NoOaBankBatchApplicationService no longer owns no-OA source version calculation")
        if "def no_oa_bank_batch_stale_reasons(" not in service_source:
            violations.append("NoOaBankBatchApplicationService no longer owns no-OA stale reason calculation")

        self.assertEqual(violations, [])

    def test_no_oa_bank_batch_refresh_enqueue_uses_producer_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        producer_path = SERVICES_ROOT / "no_oa_bank_batch_read_model_refresh_producer.py"
        producer_source = producer_path.read_text(encoding="utf-8")
        app_service_path = SERVICES_ROOT / "no_oa_bank_batch_application_service.py"
        app_service_source = app_service_path.read_text(encoding="utf-8")
        app_service_tree = _parse(app_service_path)

        violations: list[str] = []
        if _function_source(server_tree, server_source, "_enqueue_no_oa_bank_batch_read_model_refreshes"):
            violations.append("server.py still owns no-OA bank batch refresh enqueue helper")
        if 'enqueue_many("no_oa_bank_batch"' in server_source or "enqueue_many('no_oa_bank_batch'" in server_source:
            violations.append("server.py still directly enqueues no-OA bank batch refresh scopes")

        app_factory_source = _function_source(server_tree, server_source, "_no_oa_bank_batch_read_model_refresh_producer")
        if "NoOaBankBatchReadModelRefreshProducer" not in app_factory_source:
            violations.append("Application no longer assembles NoOaBankBatchReadModelRefreshProducer")
        if "read_model_refresh_producer=self._no_oa_bank_batch_read_model_refresh_producer()" not in server_source:
            violations.append("NoOaBankBatchApplicationService is not wired with the refresh producer")
        if "enqueue_refresh=self._no_oa_bank_batch_read_model_refresh_producer().enqueue" not in server_source:
            violations.append("NoOaBankBatchDerivedLifecycleExecutor is not wired with the refresh producer")

        if "class NoOaBankBatchReadModelRefreshProducer" not in producer_source:
            violations.append("NoOaBankBatchReadModelRefreshProducer is missing")
        if "def normalize_scope_keys(" not in producer_source:
            violations.append("NoOaBankBatchReadModelRefreshProducer no longer owns scope normalization")
        if 'enqueue_many(\n                "no_oa_bank_batch"' not in producer_source:
            violations.append("NoOaBankBatchReadModelRefreshProducer no longer enqueues through the gateway")

        enqueue_source = _function_source(app_service_tree, app_service_source, "enqueue_background_refresh")
        if "_read_model_refresh_producer.enqueue(scope_keys, reason=reason)" not in enqueue_source:
            violations.append("NoOaBankBatchApplicationService does not prefer the injected refresh producer")

        self.assertEqual(violations, [])

    def test_no_oa_bank_batch_workbench_payload_decoration_uses_service_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        service_path = SERVICES_ROOT / "no_oa_bank_batch_workbench_payload_decorator.py"
        service_source = service_path.read_text(encoding="utf-8")

        violations: list[str] = []
        for removed_helper in (
            "_relation_with_no_oa_bank_batch_metadata",
            "_apply_no_oa_bank_batch_pair_metadata",
            "_apply_no_oa_bank_batch_available_actions",
        ):
            if _function_source(server_tree, server_source, removed_helper):
                violations.append(f"server.py still owns no-OA Workbench payload helper {removed_helper}")

        app_factory_source = _function_source(server_tree, server_source, "_no_oa_bank_batch_workbench_payload_decorator")
        if "NoOaBankBatchWorkbenchPayloadDecorator" not in app_factory_source:
            violations.append("Application no longer assembles NoOaBankBatchWorkbenchPayloadDecorator")
        for expected_delegate in (
            ".relation_with_batch_metadata(relation)",
            ".apply_pair_metadata(payload, relation_payload)",
            ".apply_available_actions(payload)",
        ):
            if expected_delegate not in server_source:
                violations.append(f"server.py does not delegate no-OA payload behavior through {expected_delegate}")

        for service_marker in (
            "class NoOaBankBatchWorkbenchPayloadDecorator",
            "def relation_with_batch_metadata(",
            "def apply_pair_metadata(",
            "def apply_available_actions(",
            "withdraw_no_oa_batch",
            "免OA批次",
        ):
            if service_marker not in service_source:
                violations.append(f"NoOaBankBatchWorkbenchPayloadDecorator missing {service_marker}")

        self.assertEqual(violations, [])

    def test_no_oa_bank_batch_workbench_display_policy_uses_service_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        display_policy_path = SERVICES_ROOT / "no_oa_bank_batch_workbench_display_policy.py"
        display_policy_source = display_policy_path.read_text(encoding="utf-8")

        violations: list[str] = []
        derive_tags_source = _function_source(server_tree, server_source, "_derive_workbench_row_tags")
        display_payload_source = _function_source(server_tree, server_source, "_pair_relation_display_payload")
        if "NO_OA_MANAGED_LABELS" in derive_tags_source:
            violations.append("Application still owns no-OA managed-label filtering for Workbench row tags")
        if "relation.get(\"display_tags\")" in derive_tags_source or "special_metadata.get(\"display_tags\")" in derive_tags_source:
            violations.append("Application still owns no-OA display tag source selection")
        if "已匹配：免OA流水" in display_payload_source or "已匹配：{batch_label}" in display_payload_source:
            violations.append("Application still owns no-OA relation display payload labels")

        app_factory_source = _function_source(server_tree, server_source, "_no_oa_bank_batch_workbench_display_policy")
        if "NoOaBankBatchWorkbenchDisplayPolicy" not in app_factory_source:
            violations.append("Application no longer assembles NoOaBankBatchWorkbenchDisplayPolicy")
        for expected_delegate in (
            ".row_tags(",
            "_no_oa_bank_batch_workbench_display_policy().relation_display_payload",
        ):
            if expected_delegate not in server_source:
                violations.append(f"server.py does not delegate no-OA display policy through {expected_delegate}")

        for service_marker in (
            "class NoOaBankBatchWorkbenchDisplayPolicy",
            "def relation_display_payload(",
            "def row_tags(",
            "NO_OA_MANAGED_LABELS",
            "已匹配：免OA流水",
        ):
            if service_marker not in display_policy_source:
                violations.append(f"NoOaBankBatchWorkbenchDisplayPolicy missing {service_marker}")

        self.assertEqual(violations, [])

    def test_workbench_pair_relation_display_policy_extraction_stays_local(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        policy_source = (SERVICES_ROOT / "workbench_pair_relation_display_policy.py").read_text(encoding="utf-8")
        display_source = _function_source(server_tree, server_source, "_pair_relation_display_payload")
        factory_source = _function_source(server_tree, server_source, "_workbench_pair_relation_display_policy")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-pair-relation-display-policy-extraction-2026-06-25.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        if "_workbench_pair_relation_display_policy().display_payload(" not in display_source:
            violations.append("Application pair relation display helper does not delegate to display policy")
        for forbidden in (
            "internal_transfer_pair",
            "salary_personal_auto_match",
            "turnover_manual_closure",
            "OA_INVOICE_OFFSET_AUTO_MATCH_MODE",
            "PERSONAL_ADVANCE_REPAYMENT_MODE",
            "fully_linked",
            "已匹配：",
            "完全关联",
        ):
            if forbidden in display_source:
                violations.append(f"Application still owns pair relation display detail: {forbidden}")
        for marker in (
            "class WorkbenchPairRelationDisplayPolicy",
            "def display_payload(",
            "no_oa_relation_display_payload",
            "bank_transaction_tag_label",
            "internal_transfer_pair",
            "salary_personal_auto_match",
            "turnover_manual_closure",
            "oa_invoice_offset_auto_match_mode",
            "fully_linked",
        ):
            if marker not in policy_source:
                violations.append(f"WorkbenchPairRelationDisplayPolicy missing marker: {marker}")
        for marker in (
            "WorkbenchPairRelationDisplayPolicy(",
            "no_oa_relation_display_payload=self._no_oa_bank_batch_workbench_display_policy().relation_display_payload",
            "bank_transaction_tag_label=self._bank_transaction_tag_label_current",
            "no_oa_bank_batch_relation_mode=NO_OA_BANK_BATCH_RELATION_MODE",
            "personal_advance_repayment_mode=PERSONAL_ADVANCE_REPAYMENT_MODE",
            "oa_invoice_offset_auto_match_mode=OA_INVOICE_OFFSET_AUTO_MATCH_MODE",
        ):
            if marker not in factory_source:
                violations.append(f"Application display policy factory missing explicit dependency: {marker}")
        for forbidden in (
            "Response",
            "HTTPStatus",
            "_json_response",
            "ReadModelRefreshGateway",
            "outbox",
            "clear_cache",
            "set_cached",
            "save_workbench",
            "app.auth",
            "server.py",
            "MongoOAAdapter",
        ):
            if forbidden in policy_source:
                violations.append(f"WorkbenchPairRelationDisplayPolicy gained forbidden dependency: {forbidden}")
        for marker in (
            "server-py:workbench-pair-relation-display-policy-extraction",
            "WorkbenchPairRelationDisplayPolicy",
            "relation display payload mapping",
            "mode-specific metadata mutation remains deferred",
        ):
            if marker not in analysis_source:
                violations.append(f"Workbench pair relation display policy analysis missing marker: {marker}")

        self.assertEqual(violations, [])

    def test_no_oa_bank_batch_routes_delegate_to_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        route_path = APP_ROOT / "routes_no_oa_bank_batches.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "NoOaBankBatchApiRoutes")
        for marker in (
            "def route(",
            "/api/no-oa-bank-batches",
            "/api/no-oa-bank-batches/tag-selection",
            "/submit-selection",
            "/withdraw",
            "resolve_mutation_session",
            "load_json_body",
            "json_response",
            "bulk_submit(payload, session=session)",
            "submit_selection(payload, session=session)",
        ):
            if marker not in route_class:
                violations.append(f"no-OA bank batch route owner is missing marker {marker}")

        if "_no_oa_bank_batch_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("server.py does not delegate no-OA bank batch dispatch to the route owner")
        for removed_handler in (
            "_handle_api_no_oa_bank_batches",
            "_handle_api_no_oa_bank_batch_tag_selection",
            "_handle_api_no_oa_bank_batch_tag_selection_update",
            "_handle_api_no_oa_bank_batch_detail",
            "_handle_api_no_oa_bank_batch_submit",
            "_handle_api_no_oa_bank_batch_withdraw",
            "_handle_api_no_oa_bank_batches_bulk_submit",
            "_handle_api_no_oa_bank_batches_submit_selection",
        ):
            if f"def {removed_handler}(" in server_source:
                violations.append(f"server.py still defines migrated no-OA route callback {removed_handler}")

        for forbidden in (
            "save_no_oa_bank_batch_mutation",
            "enqueue_many(",
            "job.outbox_events",
            "job.read_model_dirty_scopes",
        ):
            if forbidden in route_source:
                violations.append(f"no-OA route owner owns side effect boundary {forbidden}")

        self.assertEqual(violations, [])

    def test_bank_flow_rule_batch_runtime_has_no_no_oa_compatibility_path(self) -> None:
        paths = (
            APP_ROOT / "routes_bank_flow_rule_batches.py",
            SERVICES_ROOT / "bank_flow_rule_batch_application_service.py",
            SERVICES_ROOT / "bank_flow_rule_batch_read_model_refresh.py",
        )
        violations: list[str] = []
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for forbidden in ("no_oa", "NO_OA", "免OA", "LEGACY_ERROR_CODES"):
                if forbidden in source:
                    violations.append(f"{_relative(path)} keeps bank-flow legacy marker {forbidden}")

        self.assertEqual(violations, [])

    def test_search_rebuild_helpers_stay_out_of_application(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)

        violations: list[str] = []
        for removed_helper in (
            "rebuild_search_index_scope",
            "_build_search_index_rows_for_month",
        ):
            if _function_source(tree, source, removed_helper):
                violations.append(f"server.py still owns removed search rebuild helper {removed_helper}")

        projection_source = (SERVICES_ROOT / "search_pending_sql_projection.py").read_text(encoding="utf-8")
        if "def rebuild_search_index_scope(" not in projection_source:
            violations.append("SearchPendingSqlProjectionBuilder no longer owns search index rebuild")
        if "SearchReadModelRepositoryPort" not in projection_source:
            violations.append("Search projection no longer saves through SearchReadModelRepositoryPort")

        self.assertEqual(violations, [])

    def test_search_query_freshness_helpers_stay_out_of_application(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)

        violations: list[str] = []
        for removed_helper in (
            "_get_search_payload_from_sql_read_model",
            "_search_index_expected_source_versions",
        ):
            if _function_source(tree, source, removed_helper):
                violations.append(f"server.py still owns removed search query freshness helper {removed_helper}")

        handle_search_source = _function_source(tree, source, "_handle_api_search")
        if "_search_query_freshness_service().get_payload" not in handle_search_source:
            violations.append("/api/search route no longer delegates SQL freshness payloads to SearchQueryFreshnessService")

        service_source = (SERVICES_ROOT / "search_query_freshness_service.py").read_text(encoding="utf-8")
        if "class SearchQueryFreshnessService" not in service_source:
            violations.append("SearchQueryFreshnessService is missing")
        if "require_expected_source_versions" not in service_source or "source_version_mismatch_reasons" not in service_source:
            violations.append("SearchQueryFreshnessService no longer owns source-version freshness proof")

        self.assertEqual(violations, [])

    def test_search_refresh_producer_helpers_stay_out_of_application(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)

        violations: list[str] = []
        for removed_helper in (
            "_enqueue_search_read_model_refresh",
            "_invalidate_search_read_model_scopes",
        ):
            if _function_source(tree, source, removed_helper):
                violations.append(f"server.py still owns removed search refresh helper {removed_helper}")

        app_factory_source = _function_source(tree, source, "_search_read_model_refresh_producer")
        if "SearchReadModelRefreshProducer" not in app_factory_source:
            violations.append("Application no longer assembles SearchReadModelRefreshProducer")

        service_source = (SERVICES_ROOT / "search_read_model_refresh_producer.py").read_text(encoding="utf-8")
        if "class SearchReadModelRefreshProducer" not in service_source:
            violations.append("SearchReadModelRefreshProducer is missing")
        if 'enqueue_many(\n                "search"' not in service_source:
            violations.append("SearchReadModelRefreshProducer no longer enqueues search scopes through the gateway")

        oa_projection_sync_source = (SERVICES_ROOT / "oa_projection_sync.py").read_text(encoding="utf-8")
        if 'enqueue_many("search"' in oa_projection_sync_source or "enqueue_many('search'" in oa_projection_sync_source:
            violations.append("OAProjectionSyncService still bypasses SearchReadModelRefreshProducer for search refresh")

        runtime_worker_handlers_source = (SERVICES_ROOT / "runtime_worker_handlers.py").read_text(encoding="utf-8")
        for bypass in (
            '_enqueue_scopes("search"',
            "_enqueue_scopes('search'",
            'enqueue_many("search"',
            "enqueue_many('search'",
        ):
            if bypass in runtime_worker_handlers_source:
                violations.append("Runtime worker handlers still bypass SearchReadModelRefreshProducer for search refresh")
                break

        search_pending_refresh_source = (SERVICES_ROOT / "search_pending_read_model_refresh.py").read_text(encoding="utf-8")
        if 'enqueue_many("search"' in search_pending_refresh_source or "enqueue_many('search'" in search_pending_refresh_source:
            violations.append("SearchPendingReadModelRefreshService still bypasses SearchReadModelRefreshProducer for search fan-out")
        if "SearchReadModelRefreshProducer" not in search_pending_refresh_source:
            violations.append("SearchPendingReadModelRefreshService no longer uses SearchReadModelRefreshProducer")

        self.assertEqual(violations, [])

    def test_bank_account_balance_refresh_producer_helpers_stay_out_of_application(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)

        violations: list[str] = []
        if _function_source(tree, source, "_enqueue_bank_account_balance_read_model_refresh"):
            violations.append("server.py still owns bank account balance refresh enqueue helper")

        app_factory_source = _function_source(tree, source, "_bank_account_balance_read_model_refresh_producer")
        if "BankAccountBalanceReadModelRefreshProducer" not in app_factory_source:
            violations.append("Application no longer assembles BankAccountBalanceReadModelRefreshProducer")

        service_source = (SERVICES_ROOT / "bank_account_balance_read_model_refresh_producer.py").read_text(encoding="utf-8")
        if "class BankAccountBalanceReadModelRefreshProducer" not in service_source:
            violations.append("BankAccountBalanceReadModelRefreshProducer is missing")
        if 'enqueue_many(\n                "bank_account_balance"' not in service_source:
            violations.append("BankAccountBalanceReadModelRefreshProducer no longer enqueues through the gateway")
        if 'return ["all"]' not in service_source:
            violations.append("BankAccountBalanceReadModelRefreshProducer no longer preserves the all-only contract")

        for rel_path in (
            "backend/src/fin_ops_platform/app/server.py",
            "backend/src/fin_ops_platform/app/bank_account_balance_backfill.py",
            "backend/src/fin_ops_platform/services/runtime_worker_handlers.py",
        ):
            checked_source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
            for bypass in (
                '_enqueue_scopes("bank_account_balance"',
                "_enqueue_scopes('bank_account_balance'",
                'enqueue_one("bank_account_balance"',
                "enqueue_one('bank_account_balance'",
                'enqueue_many("bank_account_balance"',
                "enqueue_many('bank_account_balance'",
            ):
                if bypass in checked_source:
                    violations.append(f"{rel_path} still bypasses BankAccountBalanceReadModelRefreshProducer")
                    break

        self.assertEqual(violations, [])

    def test_workbench_compute_reference_state_writes_stay_in_python_boundaries(self) -> None:
        worker_source = (SERVICES_ROOT / "workbench_matching_dirty_scope_worker.py").read_text(encoding="utf-8")
        orchestrator_source = (SERVICES_ROOT / "workbench_matching_orchestrator.py").read_text(encoding="utf-8")
        engine_source = (SERVICES_ROOT / "workbench_free_matching_engine.py").read_text(encoding="utf-8")

        violations: list[str] = []
        for marker in (
            "claim_due_scopes(",
            "mark_stale_completed_scopes",
            "complete(",
            "fail(",
            "record_worker_heartbeat",
        ):
            if marker not in worker_source:
                violations.append(f"Workbench matching dirty worker no longer owns state marker {marker}")

        for marker in (
            "_matcher.plan_relations",
            "_relation_uow.run",
            "confirm_formal_relation_plans",
            "WorkbenchFormalRelationCommand",
        ):
            if marker not in orchestrator_source:
                violations.append(f"Workbench matching orchestrator no longer owns reference marker {marker}")

        for marker in (
            "plan_relations(",
            "_build_edges(",
            "_plans_for_component(",
            "withdrawal_fingerprints",
            "preserved_active_count",
        ):
            if marker not in engine_source:
                violations.append(f"Workbench deterministic relation engine no longer owns safety marker {marker}")

        self.assertEqual(violations, [])

    def test_workbench_compute_go_shadow_admission_remains_guarded(self) -> None:
        analysis_source = (
            REPO_ROOT
            / ".planning"
            / "refactors"
            / "modular-io-boundaries"
            / "analysis"
            / "go-hot-path-workbench-compute-performance-baseline-contract.md"
        ).read_text(encoding="utf-8")
        queue_source = (
            REPO_ROOT
            / ".planning"
            / "refactors"
            / "modular-io-boundaries"
            / "autonomous"
            / "MODULE-QUEUE.md"
        ).read_text(encoding="utf-8")
        next_prompt_source = (
            REPO_ROOT
            / ".planning"
            / "refactors"
            / "modular-io-boundaries"
            / "autonomous"
            / "NEXT-PROMPT.md"
        ).read_text(encoding="utf-8")

        violations: list[str] = []
        for marker in (
            "Forbidden Writes In Go Shadow Mode",
            "Claim, ack, complete, fail or requeue `job.workbench_matching_dirty_scopes`",
            "Write `job.outbox_events` or `job.read_model_dirty_scopes`",
            "Publish or retire Workbench active generations",
            "Write or mutate `app.workbench_pair_relations`",
            "canonical key should include scope month, row-id set, row-type set, rule code/match domain/status and source-version signature",
            "`go-hot-path:workbench-compute-admission` cannot become the next pending boundary yet",
        ):
            if marker not in analysis_source:
                violations.append(f"Workbench Go shadow contract is missing marker: {marker}")

        if (
            "| 182 | `go-hot-path:workbench-compute-python-reference-contract-guards` | static-guard-closed"
            not in queue_source
        ):
            violations.append("Workbench compute reference-contract guard is not closed as a static guard")
        if (
            "| 183 | `go-hot-path:workbench-compute-performance-evidence-collector-contract` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench compute performance evidence collector is not closed")
        if (
            "| 184 | `go-hot-path:workbench-compute-production-evidence-gate` | production-evidence-deferred"
            not in queue_source
        ):
            violations.append("Workbench compute production evidence gate is not deferred after missing real evidence")
        if "| 185 | `go-hot-path:workbench-compute-admission` | blocked-by-prerequisite" not in queue_source:
            violations.append("Workbench compute admission is no longer blocked behind production evidence prerequisites")
        if (
            "| 189 | `planning:post-workbench-compute-evidence-gate-next-boundary-selection` | planning-closed"
            not in queue_source
        ):
            violations.append("Post-evidence boundary selection slice is not closed")
        if (
            "| 190 | `server-py:residual-route-handler-boundary-audit` | analysis-closed"
            not in queue_source
        ):
            violations.append("Residual server.py handler boundary audit is not closed as analysis")
        if (
            "| 191 | `server-py:workbench-legacy-action-handler-quarantine-audit` | analysis-closed"
            not in queue_source
        ):
            violations.append("Workbench legacy action handler audit is not closed as analysis")
        if (
            "| 192 | `server-py:legacy-workbench-action-route-module-quarantine` | implementation-closed"
            not in queue_source
        ):
            violations.append("Legacy Workbench action route quarantine is not closed as implementation")
        if (
            "| 193 | `server-py:legacy-workbench-exception-helper-dead-code-audit` | implementation-closed"
            not in queue_source
        ):
            violations.append("Legacy Workbench exception helper audit is not closed as implementation")
        if (
            "| 194 | `server-py:modern-workbench-action-route-owner-audit` | analysis-closed"
            not in queue_source
        ):
            violations.append("Modern Workbench action route-owner audit is not closed as analysis")
        if (
            "| 195 | `server-py:workbench-exception-preview-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench exception preview route owner extraction is not closed as implementation")
        if (
            "| 196 | `server-py:workbench-exception-apply-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench exception apply route owner extraction is not closed as implementation")
        if (
            "| 197 | `server-py:workbench-confirm-link-preview-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench confirm-link preview route owner extraction is not closed as implementation")
        if (
            "| 198 | `server-py:workbench-confirm-link-submit-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench confirm-link submit route owner extraction is not closed as implementation")
        if (
            "| 199 | `server-py:workbench-mark-exception-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench mark-exception route owner extraction is not closed as implementation")
        if (
            "| 200 | `server-py:workbench-cancel-link-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench cancel-link route owner extraction is not closed as implementation")
        if (
            "| 201 | `server-py:workbench-withdraw-link-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench withdraw-link route owner extraction is not closed as implementation")
        if (
            "| 202 | `server-py:workbench-cash-special-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench cash special route owner extraction is not closed as implementation")
        if (
            "| 203 | `server-py:workbench-update-bank-exception-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench update-bank-exception route owner extraction is not closed as implementation")
        if (
            "| 204 | `server-py:workbench-oa-bank-exception-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench OA-bank exception route owner extraction is not closed as implementation")
        if (
            "| 205 | `server-py:workbench-personal-advance-repayment-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench personal advance repayment route owner extraction is not closed as implementation")
        if (
            "| 206 | `server-py:workbench-cancel-exception-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench cancel-exception route owner extraction is not closed as implementation")
        if (
            "| 207 | `server-py:workbench-ignore-row-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench ignore-row route owner extraction is not closed as implementation")
        if (
            "| 208 | `server-py:workbench-unignore-row-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench unignore-row route owner extraction is not closed as implementation")
        self.assertEqual(violations, [])

    def test_modern_workbench_action_route_owner_post_extraction_audit_selects_withdraw_preview(self) -> None:
        queue_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md"
        ).read_text(encoding="utf-8")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-post-extraction-audit.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        if (
            "| 209 | `server-py:modern-workbench-action-route-owner-post-extraction-audit` | analysis-closed"
            not in queue_source
        ):
            violations.append("Workbench action route-owner post-extraction audit is not closed as analysis")
        if (
            "| 210 | `server-py:workbench-withdraw-link-preview-route-owner-extraction`"
            not in queue_source
        ):
            violations.append("Post-extraction audit no longer records Workbench withdraw-link preview as follow-up")
        if "preview_withdraw_link" not in analysis_source:
            violations.append("Post-extraction audit does not record the remaining withdraw preview facade delegation")

        self.assertEqual(violations, [])

    def test_workbench_withdraw_link_preview_route_owner_extraction_updates_queue(self) -> None:
        queue_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md"
        ).read_text(encoding="utf-8")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-withdraw-link-preview-route-owner-extraction.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        if (
            "| 210 | `server-py:workbench-withdraw-link-preview-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench withdraw-link preview route owner extraction is not closed as implementation")
        if (
            "| 211 | `server-py:modern-workbench-action-route-owner-final-residual-audit`"
            not in queue_source
        ):
            violations.append("Withdraw preview extraction no longer records final residual audit as follow-up")
        if "preview_withdraw_link" not in analysis_source:
            violations.append("Withdraw preview extraction analysis does not record preview facade delegation")

        self.assertEqual(violations, [])

    def test_modern_workbench_action_route_owner_final_residual_audit_selects_cancel_exception_cleanup(self) -> None:
        queue_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md"
        ).read_text(encoding="utf-8")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-final-residual-audit.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        if (
            "| 211 | `server-py:modern-workbench-action-route-owner-final-residual-audit` | analysis-closed"
            not in queue_source
        ):
            violations.append("Final Workbench action route-owner residual audit is not closed as analysis")
        if (
            "| 212 | `server-py:workbench-cancel-exception-live-dispatch-noop-cleanup`"
            not in queue_source
        ):
            violations.append("Final residual audit no longer records cancel-exception no-op cleanup as follow-up")
        if "_workbench_write_facade()." not in analysis_source:
            violations.append("Final residual audit does not record direct facade search evidence")

        self.assertEqual(violations, [])

    def test_workbench_cancel_exception_noop_cleanup_updates_queue(self) -> None:
        queue_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md"
        ).read_text(encoding="utf-8")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-cancel-exception-live-dispatch-noop-cleanup.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        if (
            "| 212 | `server-py:workbench-cancel-exception-live-dispatch-noop-cleanup` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench cancel-exception no-op cleanup is not closed as implementation")
        if (
            "| 213 | `server-py:modern-workbench-action-route-owner-local-closure-audit`"
            not in queue_source
        ):
            violations.append("Cancel-exception cleanup no longer records route-owner local closure follow-up")
        if "has_rows_for_month" not in analysis_source:
            violations.append("Cancel-exception cleanup analysis does not record removed no-op branch")

        self.assertEqual(violations, [])

    def test_modern_workbench_action_route_owner_local_closure_audit_selects_row_detail_audit(self) -> None:
        queue_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md"
        ).read_text(encoding="utf-8")
        next_prompt_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md"
        ).read_text(encoding="utf-8")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-local-closure-audit.md"
        ).read_text(encoding="utf-8")
        notes_source = (REPO_ROOT / "docs/modules/workbench-relations/implementation-notes.md").read_text(
            encoding="utf-8"
        )
        violations: list[str] = []

        if (
            "| 213 | `server-py:modern-workbench-action-route-owner-local-closure-audit` | analysis-closed"
            not in queue_source
        ):
            violations.append("Modern Workbench action route-owner local closure audit is not closed as analysis")
        if (
            "| 214 | `server-py:workbench-row-detail-route-owner-audit`"
            not in queue_source
        ):
            violations.append("Route-owner local closure audit no longer records row detail audit follow-up")
        for marker in (
            "WorkbenchActionApiRoutes",
            "_workbench_write_facade().",
            "LegacyWorkbenchActionRoutes",
            "`server-py:workbench-row-detail-route-owner-audit`",
            "GET /api/workbench/rows/{row_id}",
            "No module can be marked `closed`",
        ):
            if marker not in analysis_source:
                violations.append(f"Route-owner local closure audit missing marker: {marker}")
        if (
            "`server-py:workbench-row-detail-route-owner-audit`" not in next_prompt_source
            and "| 214 | `server-py:workbench-row-detail-route-owner-audit` | analysis-closed" not in queue_source
        ):
            violations.append("Next prompt no longer points at Workbench row detail route owner audit")
        if (
            "Do not implement Go, Go Fiber or Go Worker." not in next_prompt_source
            and "Do not choose Go implementation; Go admission remains blocked." not in next_prompt_source
        ):
            violations.append("Next prompt no longer forbids Go implementation during the row detail audit")
        if "Modern Workbench action route-owner local closure audit" not in notes_source:
            violations.append("Workbench relations implementation notes missing local closure audit record")

        self.assertEqual(violations, [])

    def test_workbench_row_detail_route_owner_audit_selects_extraction(self) -> None:
        queue_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md"
        ).read_text(encoding="utf-8")
        next_prompt_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md"
        ).read_text(encoding="utf-8")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-row-detail-route-owner-audit.md"
        ).read_text(encoding="utf-8")
        notes_source = (REPO_ROOT / "docs/modules/workbench-relations/implementation-notes.md").read_text(
            encoding="utf-8"
        )
        violations: list[str] = []

        if (
            "| 214 | `server-py:workbench-row-detail-route-owner-audit` | analysis-closed"
            not in queue_source
        ):
            violations.append("Workbench row detail route-owner audit is not closed as analysis")
        if (
            "| 215 | `server-py:workbench-row-detail-route-owner-extraction`"
            not in queue_source
        ):
            violations.append("Workbench row detail route-owner audit no longer records extraction follow-up")
        for marker in (
            "GET /api/workbench/rows/{row_id}",
            "Application._get_api_workbench_row_detail_payload",
            "WorkbenchQueryFacade.row_detail",
            "PostgresReadModelRepository.get_workbench_row_detail",
            "tests/test_workbench_sql_runtime.py",
            "`server-py:workbench-row-detail-route-owner-extraction`",
            "Do not implement Go, Go Fiber or Go Worker.",
        ):
            if marker not in analysis_source:
                violations.append(f"Workbench row detail route-owner audit missing marker: {marker}")
        if (
            "`server-py:workbench-row-detail-route-owner-extraction`" not in next_prompt_source
            and "| 215 | `server-py:workbench-row-detail-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Next prompt no longer points at Workbench row detail route-owner extraction")
        if (
            "Do not implement Go, Go Fiber or Go Worker." not in next_prompt_source
            and "Do not choose Go implementation; Go admission remains blocked." not in next_prompt_source
        ):
            violations.append("Next prompt no longer forbids Go implementation during row detail extraction")
        if "Workbench row detail route-owner audit" not in notes_source:
            violations.append("Workbench relations implementation notes missing row detail route-owner audit record")

        self.assertEqual(violations, [])

    def test_workbench_row_detail_route_owner_uses_generation_query_facade_only(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        routes_path = APP_ROOT / "routes_workbench.py"
        routes_source = routes_path.read_text(encoding="utf-8")
        routes_tree = _parse(routes_path)
        row_detail_route_source = _class_source(routes_tree, routes_source, "WorkbenchRowDetailApiRoutes")
        handler_source = _function_source(server_tree, server_source, "_handle_api_workbench_row_detail")
        builder_source = _function_source(server_tree, server_source, "_build_workbench_row_detail_api_routes")
        violations: list[str] = []

        for marker in (
            "class WorkbenchRowDetailApiRoutes",
            "query_facade_provider",
            "def get_result(",
            "expected_read_model_version",
            ".row_detail(",
        ):
            if marker not in row_detail_route_source:
                violations.append(f"WorkbenchRowDetailApiRoutes missing generation-query marker: {marker}")
        for marker in (
            "_workbench_row_detail_routes().get_result(",
            "expected_read_model_version=expected_read_model_version",
        ):
            if marker not in handler_source:
                violations.append(f"Application row-detail HTTP handler missing marker: {marker}")
        if "WorkbenchRowDetailApiRoutes(" not in builder_source or "query_facade_provider=self._workbench_query_facade" not in builder_source:
            violations.append("Application row-detail route builder does not inject only the query facade")
        for forbidden in (
            "etc_summary_row_detail",
            "live_row_detail",
            "cached_rows_resolver",
            "legacy_row_detail",
            "_legacy_route_fallback_allowed",
            "_row_detail_from_query_facade",
            "apply_row_override",
            "WorkbenchQueryService",
            "_records_by_id",
            "ReadModelRefreshGateway",
            "outbox",
            "save_workbench",
        ):
            if forbidden in row_detail_route_source or forbidden in builder_source:
                violations.append(f"row-detail route resurrected non-generation fallback: {forbidden}")
        if "def _get_api_workbench_row_detail_payload" in server_source:
            violations.append("Application resurrected the internal legacy row-detail payload helper")

        self.assertEqual(violations, [])

    def test_legacy_contamination_surfaces_stay_deleted(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        routes_source = (APP_ROOT / "routes_workbench.py").read_text(encoding="utf-8")
        batch_service_source = (SERVICES_ROOT / "batch_accounting_service.py").read_text(encoding="utf-8")
        violations: list[str] = []

        for forbidden in (
            "legacy_row_detail",
            "_legacy_route_fallback_allowed",
            "_row_detail_from_query_facade",
            "WorkbenchApiRoutes",
            "_workbench_api_routes",
            "_get_api_workbench_row_detail_payload",
        ):
            if forbidden in server_source or forbidden in routes_source:
                violations.append(f"legacy Workbench contamination resurfaced: {forbidden}")
        if "def repair_legacy_case_id_collisions" in batch_service_source:
            violations.append("batch accounting legacy repair method still exists after removal")
        active_repair_callers: list[str] = []
        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            if path == SERVICES_ROOT / "batch_accounting_service.py":
                continue
            source = path.read_text(encoding="utf-8")
            if "repair_legacy_case_id_collisions(" in source:
                active_repair_callers.append(_relative(path))
        if active_repair_callers:
            violations.append(
                "batch accounting legacy repair gained active app/service caller(s): "
                + ", ".join(active_repair_callers)
            )

        self.assertEqual(violations, [])

    def test_workbench_group_detail_route_owner_audit_selects_extraction(self) -> None:
        queue_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md"
        ).read_text(encoding="utf-8")
        next_prompt_source = (
            REPO_ROOT / ".planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md"
        ).read_text(encoding="utf-8")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-group-detail-route-owner-audit.md"
        ).read_text(encoding="utf-8")
        notes_source = (REPO_ROOT / "docs/modules/workbench-relations/implementation-notes.md").read_text(
            encoding="utf-8"
        )
        violations: list[str] = []

        if (
            "| 216 | `server-py:workbench-group-detail-route-owner-audit` | analysis-closed"
            not in queue_source
        ):
            violations.append("Workbench group detail route-owner audit is not closed as analysis")
        if (
            "| 217 | `server-py:workbench-group-detail-route-owner-extraction` | pending" not in queue_source
            and "| 218 | `server-py:workbench-group-detail-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Workbench group detail route-owner audit no longer records extraction follow-up")
        for marker in (
            "GET /api/workbench/groups/detail",
            "Application._handle_api_workbench_group_detail",
            "WorkbenchQueryFacade.group_detail",
            "PostgresReadModelRepository.get_workbench_group_detail",
            "source_versions",
            "read_model_status",
            "read_model_version",
            "`server-py:workbench-group-detail-route-owner-extraction`",
            "Do not implement Go, Go Fiber or Go Worker.",
        ):
            if marker not in analysis_source:
                violations.append(f"Workbench group detail route-owner audit missing marker: {marker}")
        if (
            "`server-py:workbench-group-detail-route-owner-extraction`" not in next_prompt_source
            and "| 218 | `server-py:workbench-group-detail-route-owner-extraction` | implementation-closed"
            not in queue_source
        ):
            violations.append("Next prompt no longer points at Workbench group detail route-owner extraction")
        if (
            "Do not implement Go, Go Fiber or Go Worker." not in next_prompt_source
            and "Do not choose Go implementation; Go admission remains blocked." not in next_prompt_source
        ):
            violations.append("Next prompt no longer forbids Go implementation during group detail extraction")
        if "Workbench group detail route-owner audit" not in notes_source:
            violations.append("Workbench relations implementation notes missing group detail route-owner audit record")

        self.assertEqual(violations, [])

    def test_workbench_groups_read_route_owner_extraction_stays_local(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        routes_path = APP_ROOT / "routes_workbench.py"
        routes_source = routes_path.read_text(encoding="utf-8")
        routes_tree = _parse(routes_path)
        read_route_source = _class_source(routes_tree, routes_source, "WorkbenchReadApiRoutes")
        groups_handler_source = _function_source(server_tree, server_source, "_handle_api_workbench_groups")
        refresh_status_handler_source = _function_source(
            server_tree,
            server_source,
            "_handle_api_workbench_refresh_status",
        )
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-groups-read-route-owner-extraction-2026-06-25.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        for marker in (
            "def initial(",
            "def refresh_status(",
            "def groups(",
            "normalize_workbench_group_search_mode",
            "normalize_workbench_group_detail_level",
            "_normalize_json_query_param",
            "invalid_workbench_groups_query",
        ):
            if marker not in read_route_source:
                violations.append(f"WorkbenchReadApiRoutes missing marker: {marker}")
        if "def summary(" in read_route_source:
            violations.append("WorkbenchReadApiRoutes still exposes the deleted summary endpoint")
        if "_handle_api_workbench_summary" in server_source:
            violations.append("server.py still defines the deleted Workbench summary handler")
        if 'route_path == "/api/workbench/summary"' in server_source:
            violations.append("server.py still routes the deleted Workbench summary endpoint")
        for forbidden in (
            "_normalize_workbench_group_json_query_param",
            "_normalize_workbench_group_search_mode",
            "_normalize_workbench_group_detail_level",
            "stable_json_value",
            "normalize_workbench_group_search_mode",
            "normalize_workbench_group_detail_level",
            "_workbench_query_facade().groups",
        ):
            if forbidden in groups_handler_source:
                violations.append(f"server.py groups handler still owns route mapping: {forbidden}")
        if "_workbench_read_routes().groups(" not in groups_handler_source:
            violations.append("server.py groups handler does not delegate to WorkbenchReadApiRoutes")
        if "_workbench_read_routes().refresh_status(" not in refresh_status_handler_source:
            violations.append("server.py refresh-status handler does not delegate to WorkbenchReadApiRoutes")
        if "_workbench_query_facade().refresh_status" in refresh_status_handler_source:
            violations.append("server.py refresh-status handler still calls WorkbenchQueryFacade directly")
        for forbidden in (
            "WorkbenchRelationCommandService",
            "ReadModelRefreshGateway",
            "dirty_scope",
            "outbox",
            "readiness",
            "clear_cache",
            "set_cached",
            "save_workbench",
        ):
            if forbidden in read_route_source:
                violations.append(f"WorkbenchReadApiRoutes gained write/runtime side effect: {forbidden}")
        for marker in (
            "server-py:workbench-groups-read-route-owner-extraction",
            "GET /api/workbench/groups",
            "WorkbenchReadApiRoutes",
            "SSE events",
        ):
            if marker not in analysis_source:
                violations.append(f"Workbench groups read extraction analysis missing marker: {marker}")

        self.assertEqual(violations, [])

    def test_workbench_events_stream_route_owner_extraction_stays_local(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        routes_path = APP_ROOT / "routes_workbench.py"
        routes_source = routes_path.read_text(encoding="utf-8")
        routes_tree = _parse(routes_path)
        events_route_source = _class_source(routes_tree, routes_source, "WorkbenchEventsApiRoutes")
        events_handler_source = _function_source(server_tree, server_source, "_handle_api_workbench_events")
        builder_source = _function_source(server_tree, server_source, "_build_workbench_events_api_routes")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-events-stream-route-owner-extraction-2026-06-25.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        for marker in (
            "def events(",
            "event_stream",
            "_mark_stream_started",
            "_mark_stream_closed",
            "_serialize_sse_event",
            '"heartbeat"',
            '"X-Accel-Buffering"',
        ):
            if marker not in events_route_source:
                violations.append(f"WorkbenchEventsApiRoutes missing marker: {marker}")
        for forbidden in (
            "while True",
            "serialize_sse_event",
            "_workbench_refresh_status_payload_for_scope",
            "_workbench_refresh_status_event_name",
            "_mark_workbench_events_stream_started",
            "_mark_workbench_events_stream_closed",
            "text/event-stream",
            "X-Accel-Buffering",
        ):
            if forbidden in events_handler_source:
                violations.append(f"server.py events handler still owns SSE stream behavior: {forbidden}")
        if "_workbench_events_routes().events(" not in events_handler_source:
            violations.append("server.py events handler does not delegate to WorkbenchEventsApiRoutes")
        for marker in (
            "scope_key_for_month=self._workbench_read_model_scope_key",
            "status_payload_provider = self._workbench_refresh_status_payload_provider()",
            "status_payload_for_scope=status_payload_provider.payload_for_scope",
            "event_name_for_payload=status_payload_normalizer.event_name",
            "serialize_sse_event=self._app_health_service.serialize_sse_event",
            "mark_stream_started=stream_registry.mark_started",
            "mark_stream_closed=stream_registry.mark_closed",
        ):
            if marker not in builder_source:
                violations.append(f"Workbench events route builder missing explicit port: {marker}")
        for forbidden in (
            "WorkbenchRelationCommandService",
            "ReadModelRefreshGateway",
            "dirty_scope",
            "outbox",
            "readiness",
            "clear_cache",
            "set_cached",
            "save_workbench",
        ):
            if forbidden in events_route_source:
                violations.append(f"WorkbenchEventsApiRoutes gained write/runtime side effect: {forbidden}")
        for marker in (
            "server-py:workbench-events-stream-route-owner-extraction",
            "GET /api/workbench/events",
            "WorkbenchEventsApiRoutes",
            "heartbeat",
            "stream close cleanup",
        ):
            if marker not in analysis_source:
                violations.append(f"Workbench events extraction analysis missing marker: {marker}")

        self.assertEqual(violations, [])

    def test_workbench_events_active_stream_registry_extraction_stays_local(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        service_source = (SERVICES_ROOT / "workbench_events_active_stream_registry.py").read_text(encoding="utf-8")
        builder_source = _function_source(server_tree, server_source, "_build_workbench_events_api_routes")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-events-active-stream-registry-extraction-2026-06-25.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        for forbidden in (
            "def _mark_workbench_events_stream_started",
            "def _mark_workbench_events_stream_closed",
            "def _workbench_events_active_streams_registry",
            "_workbench_events_active_streams_lock",
            "_workbench_events_active_streams:",
        ):
            if forbidden in server_source:
                violations.append(f"Application still owns Workbench active stream registry surface: {forbidden}")
        for marker in (
            "class WorkbenchEventsActiveStreamRegistry",
            "def mark_started(",
            "def mark_closed(",
            "def snapshot(",
            "Lock()",
        ):
            if marker not in service_source:
                violations.append(f"WorkbenchEventsActiveStreamRegistry missing marker: {marker}")
        for marker in (
            "stream_registry = self._workbench_events_stream_registry()",
            "mark_stream_started=stream_registry.mark_started",
            "mark_stream_closed=stream_registry.mark_closed",
        ):
            if marker not in builder_source:
                violations.append(f"Workbench events route builder is not wired through registry owner: {marker}")
        for forbidden in (
            "ReadModelRefreshGateway",
            "outbox",
            "readiness",
            "clear_cache",
            "set_cached",
            "save_workbench",
            "Response",
            "HTTPStatus",
        ):
            if forbidden in service_source:
                violations.append(f"WorkbenchEventsActiveStreamRegistry gained forbidden dependency: {forbidden}")
        for marker in (
            "server-py:workbench-events-active-stream-registry-extraction",
            "WorkbenchEventsActiveStreamRegistry",
            "stream close cleanup",
            "refresh-status payload normalization",
        ):
            if marker not in analysis_source:
                violations.append(f"Workbench events registry extraction analysis missing marker: {marker}")

        self.assertEqual(violations, [])

    def test_workbench_refresh_status_payload_normalizer_extraction_stays_local(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        service_source = (SERVICES_ROOT / "workbench_refresh_status_payload.py").read_text(encoding="utf-8")
        facade_source = _function_source(server_tree, server_source, "_workbench_query_facade")
        events_builder_source = _function_source(server_tree, server_source, "_build_workbench_events_api_routes")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-refresh-status-payload-normalizer-extraction-2026-06-25.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        for forbidden in (
            "def _normalize_workbench_refresh_status_payload",
            "def _workbench_refresh_status_event_name",
            "normalize_refresh_status_payload=self._normalize_workbench_refresh_status_payload",
            "event_name_for_payload=self._workbench_refresh_status_event_name",
        ):
            if forbidden in server_source:
                violations.append(f"Application still owns Workbench refresh-status normalizer surface: {forbidden}")
        for marker in (
            "class WorkbenchRefreshStatusPayloadNormalizer",
            "def normalize(",
            "def event_name(",
            "read_model_status = \"refreshing\"",
            "workbench.read_model.completed",
            "workbench.read_model.failed",
        ):
            if marker not in service_source:
                violations.append(f"WorkbenchRefreshStatusPayloadNormalizer missing marker: {marker}")
        if "normalize_refresh_status_payload=self._workbench_refresh_status_payload_normalizer().normalize" not in facade_source:
            violations.append("WorkbenchQueryFacade is not wired through WorkbenchRefreshStatusPayloadNormalizer")
        if "status_payload_normalizer = self._workbench_refresh_status_payload_normalizer()" not in events_builder_source:
            violations.append("Workbench events builder does not resolve WorkbenchRefreshStatusPayloadNormalizer")
        if "event_name_for_payload=status_payload_normalizer.event_name" not in events_builder_source:
            violations.append("Workbench events builder is not wired through normalizer event_name")
        for forbidden in (
            "ReadModelRefreshGateway",
            "outbox",
            "readiness",
            "clear_cache",
            "set_cached",
            "save_workbench",
            "Response",
            "HTTPStatus",
            "repository",
        ):
            if forbidden in service_source:
                violations.append(f"WorkbenchRefreshStatusPayloadNormalizer gained forbidden dependency: {forbidden}")
        for marker in (
            "server-py:workbench-refresh-status-payload-normalizer-extraction",
            "WorkbenchRefreshStatusPayloadNormalizer",
            "refresh-status payload normalization",
            "legacy `/api/workbench` SQL fallback",
        ):
            if marker not in analysis_source:
                violations.append(f"Workbench refresh status normalizer analysis missing marker: {marker}")

        self.assertEqual(violations, [])

    def test_workbench_refresh_status_payload_provider_extraction_stays_local(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        provider_source = (SERVICES_ROOT / "workbench_refresh_status_payload_provider.py").read_text(encoding="utf-8")
        events_builder_source = _function_source(server_tree, server_source, "_build_workbench_events_api_routes")
        provider_builder_source = _function_source(server_tree, server_source, "_workbench_refresh_status_payload_provider")
        analysis_source = (
            REPO_ROOT
            / ".planning/refactors/modular-io-boundaries/analysis/server-py-workbench-refresh-status-payload-provider-extraction-2026-06-25.md"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        for forbidden in (
            "def _workbench_refresh_status_payload_for_scope",
            "status_payload_for_scope=self._workbench_refresh_status_payload_for_scope",
        ):
            if forbidden in server_source:
                violations.append(f"Application still owns Workbench refresh-status payload provider surface: {forbidden}")
        for marker in (
            "class WorkbenchRefreshStatusPayloadProvider",
            "repository_provider",
            "source_freshness",
            "normalizer",
            "def payload_for_scope",
            "get_workbench_refresh_status",
            "fallback_status=\"unavailable\"",
        ):
            if marker not in provider_source:
                violations.append(f"WorkbenchRefreshStatusPayloadProvider missing marker: {marker}")
        for marker in (
            "status_payload_provider = self._workbench_refresh_status_payload_provider()",
            "status_payload_for_scope=status_payload_provider.payload_for_scope",
        ):
            if marker not in events_builder_source:
                violations.append(f"Workbench events builder missing provider marker: {marker}")
        for marker in (
            "WorkbenchRefreshStatusPayloadProvider(",
            "repository_provider=lambda: getattr(self, \"_workbench_sql_read_repository\", None)",
            "source_freshness=self._workbench_refresh_status_with_source_freshness",
            "normalizer=self._workbench_refresh_status_payload_normalizer()",
        ):
            if marker not in provider_builder_source:
                violations.append(f"Application provider builder missing explicit dependency: {marker}")
        for forbidden in (
            "Response",
            "HTTPStatus",
            "ReadModelRefreshGateway",
            "outbox",
            "readiness",
            "clear_cache",
            "set_cached",
            "save_workbench",
            "app.auth",
            "server.py",
        ):
            if forbidden in provider_source:
                violations.append(f"WorkbenchRefreshStatusPayloadProvider gained forbidden dependency: {forbidden}")
        for marker in (
            "server-py:workbench-refresh-status-payload-provider-extraction",
            "WorkbenchRefreshStatusPayloadProvider",
            "repository status lookup",
            "legacy `/api/workbench` SQL fallback",
        ):
            if marker not in analysis_source:
                violations.append(f"Workbench refresh status provider analysis missing marker: {marker}")

        self.assertEqual(violations, [])

    def test_workbench_legacy_api_sql_read_provider_stays_deleted(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        provider_path = SERVICES_ROOT / "workbench_legacy_api_sql_read_provider.py"

        self.assertFalse(provider_path.exists())
        for forbidden in (
            "WorkbenchLegacyApiSqlReadProvider",
            "_workbench_legacy_api_sql_read_provider",
            "_handle_api_workbench_from_sql_read_model",
        ):
            self.assertNotIn(forbidden, server_source)

    def test_workbench_full_payload_fetcher_stays_deleted_from_frontend_runtime(self) -> None:
        violations: list[str] = []
        api_source = (WEB_SRC_ROOT / "features" / "workbench" / "api.ts").read_text(encoding="utf-8")
        for marker in (
            "function fetchWorkbench(",
            "function fetchWorkbenchWithProgress(",
            "requestJsonWithByteProgress<ApiWorkbenchPayload>(`/api/workbench?month=",
        ):
            if marker in api_source:
                violations.append(f"Workbench frontend API resurrected legacy full payload fetcher: {marker}")

        for path in sorted(WEB_SRC_ROOT.rglob("*.ts*")):
            if "/test/" in path.as_posix() or path.name.endswith((".test.ts", ".test.tsx")):
                continue
            source = path.read_text(encoding="utf-8")
            for marker in ("fetchWorkbench(", "fetchWorkbenchWithProgress(", "/api/workbench?month="):
                if marker in source:
                    violations.append(f"{_relative(path)} calls legacy Workbench full payload fetcher: {marker}")

        self.assertEqual(violations, [])

    def test_workbench_api_full_payload_assembler_stays_deleted(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        repository_source = (SERVICES_ROOT / "postgres_repositories" / "read_models.py").read_text(encoding="utf-8")
        deleted_service_modules = (
            "workbench_api_payload_assembler.py",
            "workbench_cache_read_payload_helper.py",
            "workbench_canonical_oa_attachment_invoice_row_builder.py",
            "workbench_canonical_oa_attachment_raw_payload_repairer.py",
            "workbench_group_row_payload_helper.py",
            "workbench_legacy_api_sql_read_provider.py",
            "workbench_live_oa_merge_helper.py",
            "workbench_live_payload_builder.py",
            "workbench_oa_attachment_repair_context_executor.py",
            "workbench_oa_attachment_repair_relation_read_port.py",
            "workbench_oa_attachment_source_link_resolver.py",
            "workbench_oa_invoice_offset_desired_relation_builder.py",
            "workbench_oa_invoice_offset_rebuild_helper.py",
            "workbench_oa_invoice_offset_relation_read_port.py",
            "workbench_oa_invoice_offset_sync_executor.py",
            "workbench_oa_payload_builder.py",
            "workbench_oa_raw_payload_signal_month_helper.py",
            "workbench_raw_payload_assembler.py",
            "workbench_raw_payload_mutation_helper.py",
            "workbench_retained_all_oa_payload_builder.py",
            "workbench_retained_oa_supplemental_relation_read_port.py",
            "workbench_selected_scope_raw_oa_payload_builder.py",
            "workbench_supplemental_retained_oa_row_selector.py",
            "workbench_auto_pair_conflict_relation_read_port.py",
        )

        for module_name in deleted_service_modules:
            with self.subTest(module_name=module_name):
                self.assertFalse((SERVICES_ROOT / module_name).exists())
        for forbidden in (
            "WorkbenchApiPayloadAssembler",
            "_workbench_api_payload_assembler",
            "_build_api_workbench_payload",
            "_build_invoice_inventory_payload",
            "InvoiceInventoryStatsService",
            "_get_persisted_workbench_read_model",
            "_get_or_build_workbench_read_model",
            "_build_raw_workbench_payload",
            "_workbench_raw_payload_assembler",
            "WorkbenchRawPayloadAssembler",
            "WorkbenchCacheReadPayloadHelper",
            "_workbench_cache_read_payload_helper",
            "_apply_pair_relations_to_payload",
            "_supplement_missing_active_pair_relation_rows",
            "_sync_oa_invoice_offset_auto_pair_relations",
            "_repair_active_relations_with_oa_attachment_context",
            "_raw_workbench_payload_rows_by_id",
            "_raw_workbench_payload_row_ids",
            "_oa_invoice_offset_desired_relations",
            "_auto_pair_conflicts_with_manual_relation",
            "SYSTEM_AUTO_PAIR_RELATION_MODES",
            "_append_etc_invoice_summary_rows",
            "_etc_invoice_summary_rows_by_external_batch_id",
            "_etc_invoice_summary_row_detail",
            "_derive_tags_for_grouped_payload",
            "_relation_for_group",
            "_apply_grouped_row_overrides",
            "_resolve_live_group",
            "_workbench_sql_view_oa_sync_refresh_reason",
            "_enqueue_oa_attachment_parser_resync",
            "_handle_api_workbench_action",
            "_persist_workbench_override_change",
            "_workbench_persistence_unavailable_response",
            "_rebuild_workbench_matching_dirty_scopes_once",
            "_workbench_matching_scope_months_for_import_preview",
            "_is_workbench_read_model_rebuild_job",
        ):
            self.assertNotIn(forbidden, server_source)
        for forbidden in (
            "def get_workbench_view(",
            "def _load_all_workbench_view(",
            "def _load_workbench_rows_page(",
        ):
            self.assertNotIn(forbidden, repository_source)

    def test_workbench_oa_retention_parser_remains_narrow(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        parser_source = (SERVICES_ROOT / "workbench_oa_retention_date_parser.py").read_text(encoding="utf-8")
        delegate_source = _function_source(server_tree, server_source, "_parse_oa_retention_date")

        self.assertIn("return WorkbenchOaRetentionDateParser.parse(value)", delegate_source)
        self.assertEqual(parser_source.count("    def "), 1)
        self.assertIn("def parse(value: object) -> datetime | None:", parser_source)
        for forbidden in (
            "raw_payload",
            "grouped_payload",
            "row_date_candidates",
            "row_is_on_or_after",
            "row_has_parseable_retention_date",
        ):
            self.assertNotIn(forbidden, parser_source)

    def test_workbench_sync_page_cache_warmer_stays_deleted(self) -> None:
        worker_source = (APP_ROOT / "worker.py").read_text(encoding="utf-8")
        refresh_source = (SERVICES_ROOT / "workbench_read_model_refresh.py").read_text(encoding="utf-8")
        cache_source = (SERVICES_ROOT / "workbench_groups_page_cache.py").read_text(encoding="utf-8")

        for forbidden in (
            "WorkbenchGroupsPageCacheWarmer",
            "workbench_groups_sync_cache_warmup_enabled_from_env",
            "FIN_OPS_WORKBENCH_GROUPS_SYNC_CACHE_WARMUP_ENABLED",
            "post_refresh_warmer",
            'payload["cache_warmup"]',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, worker_source)
                self.assertNotIn(forbidden, refresh_source)
                self.assertNotIn(forbidden, cache_source)

    def test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback(self) -> None:
        checks = {
            "backend/src/fin_ops_platform/services/no_oa_legacy_relation_migration_service.py": (
                "migrate_relations_to_no_oa",
            ),
            "backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py": (
                "_migrate_legacy_active_relations",
                "_consolidate_submitted_single_side_batches",
                "_prune_submitted_single_side_batches_for_category_drift",
                "_repair_submitted_no_oa_relation_consistency",
                "_replace_consolidated_no_oa_relation",
            ),
        }
        violations: list[str] = []
        for rel_path, method_names in checks.items():
            path = REPO_ROOT / rel_path
            source = path.read_text(encoding="utf-8")
            tree = _parse(path)
            class_source = _class_source(
                tree,
                source,
                "NoOaLegacyRelationMigrationService"
                if rel_path.endswith("no_oa_legacy_relation_migration_service.py")
                else "NoOaBankBatchService",
            )
            command_markers = (
                ("_confirm_relation", "confirm_relation")
                if rel_path.endswith("no_oa_legacy_relation_migration_service.py")
                else ("_confirm_no_oa_relation", "confirm_relation")
            )
            cancel_markers = (
                ("_cancel_relation", "cancel_relation")
                if rel_path.endswith("no_oa_legacy_relation_migration_service.py")
                else ("_cancel_no_oa_relation", "cancel_relation")
            )
            if command_markers[0] not in class_source or command_markers[1] not in class_source:
                violations.append(f"{rel_path} lacks command-backed relation confirm helper")
            if cancel_markers[0] not in class_source or cancel_markers[1] not in class_source:
                violations.append(f"{rel_path} lacks command-backed relation cancel helper")
            if "no_oa_relation_command_unavailable" not in class_source:
                violations.append(f"{rel_path} does not fail fast when relation command service is unavailable")
            if rel_path.endswith("no_oa_legacy_relation_migration_service.py"):
                for forbidden in (
                    "WorkbenchPairRelationService",
                    "pair_relation_service",
                    "_pair_relation_service",
                    "get_active_relation_by_case_id",
                    "active_relations_for_row_ids",
                    "list_active_relations",
                ):
                    if forbidden in class_source:
                        violations.append(f"{rel_path} keeps legacy pair relation read dependency {forbidden}")
            for method_name in method_names:
                method_source = _function_source(tree, source, method_name)
                for forbidden in (
                    "_pair_relation_service.create_active_relation",
                    "_pair_relation_service.cancel_relation",
                    "_pair_relation_service.record_history",
                ):
                    if forbidden in method_source:
                        violations.append(f"{rel_path}:{method_name} keeps direct pair write fallback {forbidden}")

        self.assertEqual(violations, [])

    def test_canonical_workbench_pair_relation_direct_write_fallbacks_do_not_return(self) -> None:
        allowed_paths = {
            "backend/src/fin_ops_platform/services/workbench_pair_relation_service.py",
            "backend/src/fin_ops_platform/services/workbench_relation_command_service.py",
        }
        forbidden_methods = {
            "create_active_relation",
            "cancel_relation",
            "record_history",
            "replace_with_confirmed_relation",
        }
        violations: list[str] = []

        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            rel_path = _relative(path)
            if rel_path in allowed_paths:
                continue
            tree = _parse(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in forbidden_methods:
                    continue
                owner = _attribute_chain(node.func.value)
                if owner.endswith("pair_relation_service") or owner.endswith("._pair_relation_service"):
                    violations.append(f"{rel_path}:{node.lineno} calls direct pair relation write {owner}.{node.func.attr}")

        self.assertEqual(violations, [])

    def test_canonical_gridfs_legacy_worker_path_is_removed(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        postgres_state_store_source = (SERVICES_ROOT / "postgres_state_store.py").read_text(encoding="utf-8")
        worker_path = APP_ROOT / "worker.py"
        worker_source = worker_path.read_text(encoding="utf-8")
        registry_source = (SERVICES_ROOT / "runtime_worker_registry.py").read_text(encoding="utf-8")
        file_migration_source = (SERVICES_ROOT / "file_object_migration.py").read_text(encoding="utf-8")
        deploy_env_dir = REPO_ROOT / "deploy" / "oa" / "env"
        violations: list[str] = []

        for forbidden in (
            "LegacyGridFSFileReader",
            "GridFSObjectMigrationService",
            "file_object.gridfs_migration",
            "FIN_OPS_ENABLE_LEGACY_GRIDFS_READS",
        ):
            if forbidden in server_source:
                violations.append(f"server.py references legacy GridFS source path {forbidden}")
        for forbidden in (
            "from fin_ops_platform.services.state_store import",
            "FIN_OPS_ENABLE_LEGACY_GRIDFS_READS",
            "_legacy_file_reader",
            "legacy_file_reader:",
            "legacy_file_reader=",
        ):
            if forbidden in postgres_state_store_source:
                violations.append(f"postgres_state_store.py keeps legacy GridFS read fallback {forbidden}")
        production_sources = {
            "worker.py": worker_source,
            "runtime_worker_registry.py": registry_source,
            "file_object_migration.py": file_migration_source,
            "fin-ops.rabbitmq-dispatcher.env.example": (deploy_env_dir / "fin-ops.rabbitmq-dispatcher.env.example").read_text(encoding="utf-8"),
            "fin-ops.secrets.env.example": (deploy_env_dir / "fin-ops.secrets.env.example").read_text(encoding="utf-8"),
        }
        for name, source in production_sources.items():
            for forbidden in (
                "file_object.gridfs_migration",
                "--enable-file-object-migration",
                "LegacyGridFSFileReader",
                "GridFSObjectMigrationService",
                '"legacy_gridfs"',
                "fin-ops.worker.file-migration",
                "FIN_OPS_APP_MONGO_",
            ):
                if forbidden in source:
                    violations.append(f"{name} keeps removed GridFS migration path {forbidden}")
        for removed_file in (
            "fin-ops.worker.file-migration.env.example",
            "fin-ops.worker.file-migration-rabbitmq.env.example",
        ):
            if (deploy_env_dir / removed_file).exists():
                violations.append(f"{removed_file} still exists")
        for removed_tool in ("verify_file_object_migration.py", "rollback_file_object_migration.py"):
            if (TOOLS_ROOT / removed_tool).exists():
                violations.append(f"{removed_tool} still exists")

        self.assertEqual(violations, [])

    def test_workbench_candidate_snapshot_repair_tool_is_removed(self) -> None:
        tool_path = TOOLS_ROOT / "repair_workbench_candidate_snapshot.py"
        violations: list[str] = []

        if tool_path.exists():
            violations.append("repair_workbench_candidate_snapshot.py still exists")
        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            source = path.read_text(encoding="utf-8")
            if "repair_workbench_candidate_snapshot" in source:
                violations.append(f"{_relative(path)} imports or references repair_workbench_candidate_snapshot")

        self.assertEqual(violations, [])

    def test_turnover_local_pair_snapshot_uses_explicit_port(self) -> None:
        adapters_path = SERVICES_ROOT / "turnover_ledger_write_adapters.py"
        adapters_source = adapters_path.read_text(encoding="utf-8")
        adapters_tree = _parse(adapters_path)
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)

        port_source = _class_source(adapters_tree, adapters_source, "TurnoverLedgerLocalPairSnapshotPort")
        connection_source = _class_source(adapters_tree, adapters_source, "TurnoverLedgerLocalClosureConnection")
        builder_sources = [
            _class_source(adapters_tree, adapters_source, "TurnoverLedgerConfirmPrimaryWriteFacadeBuilder"),
            _class_source(adapters_tree, adapters_source, "TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder"),
        ]
        server_builder_sources = [
            _function_source(server_tree, server_source, "_turnover_ledger_closure_write_facade"),
            _function_source(server_tree, server_source, "_turnover_ledger_withdraw_write_facade"),
        ]
        violations: list[str] = []

        for snippet in (
            "class TurnoverLedgerLocalPairSnapshotPort",
            "def snapshot(",
            "def save_current(",
            "def restore(",
            "from_snapshot(snapshot)",
            "_pair_relations",
            "_pair_relation_history",
        ):
            if snippet not in port_source:
                violations.append(f"turnover local pair snapshot port missing {snippet}")
        for forbidden in (
            "pair_relation_service:",
            "self._pair_relation_service",
            "from_snapshot(snapshot)",
            "_pair_relations",
            "_pair_relation_history",
        ):
            if forbidden in connection_source:
                violations.append(f"TurnoverLedgerLocalClosureConnection still owns broad pair behavior {forbidden}")
        if "pair_snapshot_port: TurnoverLedgerLocalPairSnapshotPort" not in connection_source:
            violations.append("TurnoverLedgerLocalClosureConnection does not require explicit pair snapshot port")
        for source in builder_sources:
            if "pair_relation_service:" in source or "self._pair_relation_service" in source:
                violations.append("turnover primary builder still accepts or stores broad pair relation service")
            if "pair_snapshot_port:" not in source:
                violations.append("turnover primary builder does not accept explicit pair snapshot port")
            if "pair_snapshot_port=self._pair_snapshot_port" not in source:
                violations.append("turnover primary builder does not pass pair snapshot port to local connection")
        for source in server_builder_sources:
            if "pair_snapshot_port=TurnoverLedgerLocalPairSnapshotPort(" not in source:
                violations.append("Application turnover builder wiring does not wrap pair service in explicit port")

        self.assertEqual(violations, [])

    def test_settings_data_reset_pair_snapshot_uses_explicit_port(self) -> None:
        service_path = SERVICES_ROOT / "settings_data_reset_service.py"
        service_source = service_path.read_text(encoding="utf-8")
        service_tree = _parse(service_path)
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)

        port_source = _class_source(service_tree, service_source, "SettingsDataResetPairSnapshotPort")
        service_class_source = _class_source(service_tree, service_source, "SettingsDataResetService")
        runtime_init_source = _function_source(server_tree, server_source, "_initialize_runtime_services")
        violations: list[str] = []

        for snippet in (
            "class SettingsDataResetPairSnapshotPort",
            "def pair_relations(",
            "def save_pair_relations(",
            "def snapshot(",
            "save_pair_relation_snapshot",
        ):
            if snippet not in port_source:
                violations.append(f"settings data reset pair snapshot port missing {snippet}")
        for forbidden in (
            "workbench_pair_relation_service:",
            "self._workbench_pair_relation_service",
        ):
            if forbidden in service_class_source:
                violations.append(f"SettingsDataResetService still accepts broad pair service {forbidden}")
        if "workbench_pair_snapshot_port: SettingsDataResetPairSnapshotPort" not in service_class_source:
            violations.append("SettingsDataResetService does not require explicit pair snapshot port")
        if "_workbench_pair_snapshot_port.pair_relations()" not in service_class_source:
            violations.append("SettingsDataResetService does not read pair relations through the port")
        if "_workbench_pair_snapshot_port.save_pair_relations(kept_pair_relations)" not in service_class_source:
            violations.append("SettingsDataResetService does not save filtered pair relations through the port")
        if "_persist_import_reset_state(" not in service_class_source:
            violations.append("SettingsDataResetService import resets no longer share explicit persistence boundary")
        for snippet in (
            "self._state_store.save_workbench_overrides({})",
            "self._state_store.save_workbench_pair_relations({})",
            "self._state_store.save_workbench_read_models({})",
        ):
            if snippet not in service_class_source:
                violations.append(f"SettingsDataResetService reset persistence no longer uses explicit port {snippet}")
        for forbidden in (
            '"workbench_overrides": {}',
            '"workbench_pair_relations": {}',
            '"workbench_read_models": {}',
        ):
            if forbidden in service_class_source:
                violations.append(f"SettingsDataResetService still clears workbench state through broad save payload {forbidden}")
        if "workbench_pair_snapshot_port=SettingsDataResetPairSnapshotPort(" not in runtime_init_source:
            violations.append("Application settings reset wiring does not wrap pair service in explicit port")

        self.assertEqual(violations, [])

    def test_settings_routes_use_route_owner(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        route_source = (APP_ROOT / "routes_settings.py").read_text(encoding="utf-8")
        route_tree = _parse(APP_ROOT / "routes_settings.py")
        violations: list[str] = []

        route_class = _class_source(route_tree, route_source, "SettingsApiRoutes")
        if not route_class:
            violations.append("settings route owner is missing")
        for marker in (
            "def update_settings(",
            "bank_transaction_tags_write_forbidden",
            "def oa_applicant_credentials(",
            "def create_oa_manual_imports(",
            "def create_data_reset_job(",
            "job_type=\"settings_data_reset\"",
            "app_settings_persistence_failed",
        ):
            if marker not in route_class:
                violations.append(f"settings route owner missing marker {marker}")
        if "settings_response = self._settings_routes().route(" not in server_source:
            violations.append("server.py does not delegate settings routes to SettingsApiRoutes")
        for forbidden in (
            "def _handle_api_workbench_settings",
            "def _resolve_settings_mutation_session",
            "def _parse_oa_manual_search_pagination",
            "def _parse_oa_manual_import_row_ids",
            "def _unsupported_settings_data_reset_response",
            "def _handle_api_workbench_settings_data_reset",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still owns settings route I/O {forbidden}")

        self.assertEqual(violations, [])

    def test_settings_data_reset_uses_background_job_service_only(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        routes_source = (APP_ROOT / "routes_settings.py").read_text(encoding="utf-8")
        combined_source = f"{server_source}\n{routes_source}"

        violations: list[str] = []
        for forbidden in (
            "class DataResetJob",
            "_data_reset_jobs",
            "_data_reset_jobs_lock",
            "def _active_data_reset_job(",
            "def _run_settings_data_reset_job(",
            "def _update_data_reset_job(",
        ):
            if forbidden in combined_source:
                violations.append(f"server.py keeps legacy in-memory data reset job path {forbidden}")
        for forbidden in (
            "def _handle_api_workbench_settings_data_reset",
            "def _run_settings_data_reset_background_job(",
            "def _active_data_reset_background_job(",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still owns settings data reset route concern {forbidden}")
        if "job_type=\"settings_data_reset\"" not in routes_source:
            violations.append("settings route owner data reset job create no longer uses BackgroundJobService")
        if "def _active_data_reset_background_job(" not in routes_source:
            violations.append("settings route owner data reset active job lookup no longer uses BackgroundJobService")

        self.assertEqual(violations, [])

    def test_bank_details_relation_tags_only_read_relation_distribution_facade(self) -> None:
        path = SERVICES_ROOT / "bank_details_relation_tag_projection_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        violations: list[str] = []

        forbidden_snippets = {
            "_build_raw_workbench_payload",
            "_bank_details_relation_tag_workbench_read_model",
            "candidate_match",
            "workbench_pair_relation_service",
            "WorkbenchPairRelationService",
            "load_workbench_pair_relations",
            "list_active_relations",
            "active_relations_for_row_ids",
            "get_active_relation_by_row_id",
            "get_active_relation_by_case_id",
            "list_by_month(",
            "relation_groups_by_ids(",
        }
        for snippet in sorted(forbidden_snippets):
            if snippet in source:
                violations.append(f"{_relative(path)} contains forbidden bank relation tag source {snippet}")
        if "_bank_details_relation_tag_workbench_read_model" in server_source:
            violations.append("backend/src/fin_ops_platform/app/server.py keeps removed BankDetails raw workbench relation tag fallback")

        facade_method = _function_source(tree, source, "_relation_tags_from_distribution")
        if "get_by_row_ids" not in facade_method:
            violations.append(f"{_relative(path)} does not read relation tags through WorkbenchRelationReadFacade.get_by_row_ids")

        self.assertEqual(violations, [])

    def test_financial_object_identity_rules_are_centralized(self) -> None:
        allowed_private_identity_wrappers = {
            "backend/src/fin_ops_platform/services/input_invoice_usage_service.py",
            "backend/src/fin_ops_platform/services/output_invoice_collection_service.py",
        }
        allowed_identity_rule_modules = {
            "backend/src/fin_ops_platform/services/object_identity_policy.py",
            "backend/src/fin_ops_platform/services/invoice_identity_service.py",
            "backend/src/fin_ops_platform/services/bank_transaction_identity_service.py",
        }
        violations: list[str] = []

        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            rel_path = _relative(path)
            if rel_path in allowed_identity_rule_modules:
                continue
            tree = _parse(path)
            source = path.read_text(encoding="utf-8")
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_identity_key":
                    body_source = ast.get_source_segment(source, node) or ""
                    if rel_path not in allowed_private_identity_wrappers:
                        violations.append(f"{rel_path}:{node.lineno} defines private _identity_key")
                    elif "legacy_invoice_identity_key" not in body_source:
                        violations.append(f"{rel_path}:{node.lineno} _identity_key does not delegate to FinancialObjectIdentityPolicy")
            if rel_path == "backend/src/fin_ops_platform/app/server.py":
                canonical_method = _function_source(tree, source, "_canonical_invoice_key_exists_for_etc_import")
                if "list_invoices(" in canonical_method or "source_unique_key" in canonical_method:
                    violations.append("backend/src/fin_ops_platform/app/server.py owns canonical invoice key scan")
            if rel_path == "backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py":
                canonical_method = _function_source(tree, source, "_canonical_invoices_by_number")
                if "list_invoices(" in canonical_method:
                    violations.append(f"{rel_path} scans invoices for canonical ETC identity lookup")
            if rel_path == "backend/src/fin_ops_platform/services/tax_certified_import_service.py":
                unique_key_method = _function_source(tree, source, "_build_unique_key")
                if "tax_certified_unique_key" not in unique_key_method:
                    violations.append(f"{rel_path} _build_unique_key does not delegate to FinancialObjectIdentityPolicy")
                for literal in ('"digital:', '"invoice:', '"fallback:', "f\"digital:", "f\"invoice:", "f\"fallback:"):
                    if literal in unique_key_method:
                        violations.append(f"{rel_path} _build_unique_key locally owns identity literal {literal}")

        self.assertEqual(violations, [])

    def test_oa_attachment_invoice_identity_and_etc_dry_run_do_not_reintroduce_private_rules(self) -> None:
        violations: list[str] = []

        mongo_path = SERVICES_ROOT / "mongo_oa_adapter.py"
        mongo_source = mongo_path.read_text(encoding="utf-8")
        mongo_tree = _parse(mongo_path)
        mongo_method = _function_source(mongo_tree, mongo_source, "_attachment_invoice_dedupe_keys")
        if "oa_attachment_invoice_dedupe_keys" not in mongo_method:
            violations.append(f"{_relative(mongo_path)} _attachment_invoice_dedupe_keys does not delegate to FinancialObjectIdentityPolicy")
        for forbidden in ("invoice:digital_invoice_no", "invoice:code_no", "invoice:fallback", "digital_invoice_no", "invoice_code", "invoice_no"):
            if forbidden in mongo_method and forbidden != "oa_attachment_invoice_dedupe_keys":
                violations.append(f"{_relative(mongo_path)} _attachment_invoice_dedupe_keys locally owns {forbidden}")

        attachment_service_path = SERVICES_ROOT / "oa_attachment_invoice_service.py"
        attachment_source = attachment_service_path.read_text(encoding="utf-8")
        attachment_tree = _parse(attachment_service_path)
        invoice_method = _function_source(attachment_tree, attachment_source, "_invoice_evidence_dedupe_key")
        if "oa_attachment_invoice_dedupe_keys" not in invoice_method:
            violations.append(f"{_relative(attachment_service_path)} _invoice_evidence_dedupe_key does not delegate to FinancialObjectIdentityPolicy")
        evidence_method = _function_source(attachment_tree, attachment_source, "_evidence_dedupe_key")
        for forbidden in ("invoice:digital_invoice_no", "invoice:code_no", "invoice:fallback"):
            if forbidden in evidence_method or forbidden in invoice_method:
                violations.append(f"{_relative(attachment_service_path)} owns private attachment invoice identity literal {forbidden}")

        for path in _python_files(SERVICES_ROOT):
            rel_path = _relative(path)
            if rel_path in {
                "backend/src/fin_ops_platform/services/object_identity_policy.py",
                "backend/src/fin_ops_platform/services/mongo_oa_adapter.py",
                "backend/src/fin_ops_platform/services/oa_attachment_invoice_service.py",
            }:
                continue
            for node in ast.walk(_parse(path)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
                    "_attachment_invoice_dedupe_key",
                    "_attachment_invoice_dedupe_keys",
                    "_invoice_dedupe_key",
                }:
                    violations.append(f"{rel_path}:{node.lineno} defines private invoice dedupe helper {node.name}")

        etc_tool_path = TOOLS_ROOT / "link_existing_etc_batches.py"
        etc_tool_source = etc_tool_path.read_text(encoding="utf-8")
        if "list_invoices(" in etc_tool_source:
            violations.append(f"{_relative(etc_tool_path)} dry-run scans canonical invoices with list_invoices()")
        if "EtcExistingInvoiceLinkService" not in etc_tool_source:
            violations.append(f"{_relative(etc_tool_path)} does not delegate ETC invoice linking to EtcExistingInvoiceLinkService")
        if "upsert_etc_invoice" in etc_tool_source:
            violations.append(f"{_relative(etc_tool_path)} owns ETC canonical invoice link loop")
        audit_tool_path = TOOLS_ROOT / "audit_object_identity.py"
        audit_tool_source = audit_tool_path.read_text(encoding="utf-8")
        if "invoice_evidence_types" in audit_tool_source or "document_kind.endswith" in audit_tool_source:
            violations.append(f"{_relative(audit_tool_path)} owns private OA attachment invoice evidence classification")
        for path in _python_files(SERVICES_ROOT, TOOLS_ROOT):
            rel_path = _relative(path)
            if rel_path == "backend/src/fin_ops_platform/services/object_identity_policy.py":
                continue
            source = path.read_text(encoding="utf-8")
            for constant_name in (
                "FORMAL_INVOICE_EVIDENCE_TYPES",
                "OA_ATTACHMENT_INVOICE_EVIDENCE_TYPES",
                "ATTACHMENT_INVOICE_EVIDENCE_TYPES",
            ):
                if f"{constant_name} =" in source:
                    violations.append(f"{rel_path} defines private OA attachment invoice evidence type set {constant_name}")

        self.assertEqual(violations, [])

    def test_oa_attachment_invoice_create_permission_is_gated_by_recognition_service(self) -> None:
        violations: list[str] = []
        allowed_path = "backend/src/fin_ops_platform/app/server.py"

        for path in _python_files(APP_ROOT, SERVICES_ROOT, TOOLS_ROOT):
            rel_path = _relative(path)
            source = path.read_text(encoding="utf-8")
            if "allow_create=" not in source:
                continue
            if rel_path != allowed_path:
                violations.append(f"{rel_path} passes allow_create to OA attachment invoice upsert")

        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        promote_method = _function_source(_parse(server_path), server_source, "_promote_oa_attachment_invoices_to_canonical")
        if "InvoiceAttachmentRecognitionService" not in promote_method:
            violations.append("server.py OA attachment promotion does not use InvoiceAttachmentRecognitionService")
        if "allow_create=decision.action == CREATE_INVOICE_AND_LINK" not in promote_method:
            violations.append("server.py OA attachment promotion does not gate allow_create on CREATE_INVOICE_AND_LINK")

        self.assertEqual(violations, [])

    def test_business_services_do_not_directly_query_identity_sql(self) -> None:
        allowed_sql_paths = {
            "backend/src/fin_ops_platform/services/postgres_repositories/core.py",
            "backend/src/fin_ops_platform/services/object_identity_policy.py",
            "backend/src/fin_ops_platform/services/object_dedup_decision_service.py",
        }
        violations: list[str] = []

        for path in _python_files(SERVICES_ROOT):
            rel_path = _relative(path)
            if rel_path in allowed_sql_paths or "/postgres_repositories/" in rel_path:
                continue
            source = path.read_text(encoding="utf-8")
            normalized = " ".join(source.lower().split())
            if " from app.invoices" in normalized and ("source_unique_key" in normalized or "data_fingerprint" in normalized):
                violations.append(f"{rel_path} directly queries invoice identity SQL")
            if " from app.bank_transactions" in normalized and ("source_unique_key" in normalized or "data_fingerprint" in normalized):
                violations.append(f"{rel_path} directly queries bank transaction identity SQL")

        self.assertEqual(violations, [])

    def test_app_invoice_writes_stay_in_core_repository(self) -> None:
        allowed_write_paths = {
            "backend/src/fin_ops_platform/services/postgres_repositories/core.py",
        }
        write_patterns = (
            "insert into app.invoices",
            "update app.invoices",
            "delete from app.invoices",
        )
        violations: list[str] = []

        for path in _python_files(APP_ROOT, SERVICES_ROOT, TOOLS_ROOT):
            rel_path = _relative(path)
            if rel_path in allowed_write_paths:
                continue
            normalized = " ".join(path.read_text(encoding="utf-8").lower().split())
            for pattern in write_patterns:
                if pattern in normalized:
                    violations.append(f"{rel_path} contains direct `{pattern}` SQL")

        self.assertEqual(violations, [])

    def test_etc_paths_do_not_call_legacy_canonical_sync_helpers(self) -> None:
        forbidden_names = {
            "_sync_etc_import_result_to_canonical_invoices",
            "_sync_etc_invoices_to_canonical_invoices",
            "_refresh_after_etc_invoice_sync",
            "remove_etc_invoices_by_import_batch_id",
        }
        violations: list[str] = []

        for path in _python_files(APP_ROOT, SERVICES_ROOT, TOOLS_ROOT, SCRIPTS_ROOT):
            rel_path = _relative(path)
            source = path.read_text(encoding="utf-8")
            for name in forbidden_names:
                if name in source:
                    violations.append(f"{rel_path} references legacy ETC canonical sync helper `{name}`")

        self.assertEqual(violations, [])

    def test_etc_existing_invoice_link_logic_stays_out_of_server_and_worker_helpers(self) -> None:
        checks = [
            (APP_ROOT / "server.py", "_link_etc_import_result_to_existing_invoices"),
            (APP_ROOT / "server.py", "_link_etc_invoices_to_existing_invoices"),
            (SERVICES_ROOT / "runtime_worker_handlers.py", "_link_etc_import_result_to_existing_invoices"),
        ]
        violations: list[str] = []

        for path, function_name in checks:
            source = path.read_text(encoding="utf-8")
            function_source = _function_source(_parse(path), source, function_name)
            rel_path = _relative(path)
            if "EtcExistingInvoiceLinkService" not in function_source:
                violations.append(f"{rel_path}.{function_name} does not delegate to EtcExistingInvoiceLinkService")
            if "upsert_etc_invoice" in function_source:
                violations.append(f"{rel_path}.{function_name} owns ETC canonical invoice link loop")
            if "list_invoices_by_numbers" in function_source:
                violations.append(f"{rel_path}.{function_name} owns ETC import result invoice lookup")

        runtime_source = (SERVICES_ROOT / "runtime_worker_handlers.py").read_text(encoding="utf-8")
        if "def _link_etc_invoices_to_existing_invoices(" in runtime_source:
            violations.append("runtime worker retains unused ETC invoice-link wrapper")

        self.assertEqual(violations, [])

    def test_runtime_code_does_not_reference_legacy_etc_oa_detection_worker(self) -> None:
        forbidden_terms = {
            "etc-business-oa-detection",
            "etc_business.oa_detection.refresh",
            "OA detection worker",
        }
        scanned_roots = (APP_ROOT, SERVICES_ROOT, TOOLS_ROOT, SCRIPTS_ROOT, REPO_ROOT / "deploy")
        violations: list[str] = []

        for path in _python_files(*[root for root in scanned_roots if root.exists()]):
            rel_path = _relative(path)
            source = path.read_text(encoding="utf-8")
            for term in forbidden_terms:
                if term in source:
                    violations.append(f"{rel_path} references legacy ETC OA detection runtime `{term}`")

        self.assertEqual(violations, [])

    def test_oa_mongo_adapter_direct_use_is_allowlisted(self) -> None:
        allowed_paths = {
            "backend/src/fin_ops_platform/services/oa_sync_source_adapter.py",
        }
        violations: list[str] = []
        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            tree = _parse(path)
            rel_path = _relative(path)
            if _imports_name_from_module(
                tree,
                module="fin_ops_platform.services.mongo_oa_adapter",
                name="MongoOAAdapter",
            ) and rel_path not in allowed_paths:
                violations.append(rel_path)

        self.assertEqual(violations, [])

    def test_worker_oa_mongo_adapter_is_confined_to_sync_source_boundary(self) -> None:
        worker_path = APP_ROOT / "worker.py"
        worker_source = worker_path.read_text(encoding="utf-8")
        boundary_path = SERVICES_ROOT / "oa_sync_source_adapter.py"
        boundary_source = boundary_path.read_text(encoding="utf-8")
        violations: list[str] = []

        if "MongoOAAdapter._attachment_invoice_cache_parser_version" in worker_source:
            violations.append("worker still reads parser version through MongoOAAdapter")
        if "MongoOAAdapter" in worker_source:
            violations.append("worker still directly imports or constructs MongoOAAdapter")
        if worker_source.count("build_oa_sync_source_adapter(") != 2:
            violations.append("worker does not delegate both OA sync source adapter paths to the boundary")
        if "MongoOAAdapter(" not in boundary_source:
            violations.append("OA sync source boundary no longer owns the direct adapter construction")

        self.assertEqual(violations, [])

    def test_oa_sync_admission_source_and_fanout_are_isolated(self) -> None:
        adapter_source = (SERVICES_ROOT / "mongo_oa_adapter.py").read_text(encoding="utf-8")
        sync_source = (SERVICES_ROOT / "oa_projection_sync.py").read_text(encoding="utf-8")
        snapshot_source = (
            SERVICES_ROOT / "postgres_repositories" / "oa_pending_payment_source_snapshot.py"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        if "def load_sync_application_batch(" not in adapter_source:
            violations.append("OA Mongo adapter no longer exposes the strict dual-view sync batch")
        if "def poll_sync_fingerprints(" in adapter_source:
            violations.append("OA Mongo adapter still exposes the unused legacy fingerprint polling path")
        for legacy_call in (
            ".list_available_months(",
            ".list_application_records(",
            ".list_all_application_records(",
        ):
            if legacy_call in sync_source:
                violations.append(f"OAProjectionSyncService still uses legacy source path {legacy_call}")
        if 'getattr(source_snapshot_result, "affected_scope_keys"' in sync_source:
            violations.append("OAProjectionSyncService still fans out a mixed snapshot change set")
        if "include_workbench_relation" in snapshot_source:
            violations.append("OA pending source repository still owns legacy Workbench relation fan-out")
        if '"scope_type": "workbench_relation"' in snapshot_source:
            violations.append("OA pending source repository still enqueues Workbench relation refreshes")

        self.assertEqual(violations, [])

    def test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        builder = _function_source(server_tree, server_source, "_build_legacy_direct_oa_mongo_adapter")
        initializer = _function_source(server_tree, server_source, "_initialize_runtime_services")
        pending_source = _function_source(server_tree, server_source, "_oa_pending_payment_source_adapter")
        violations: list[str] = []

        if builder:
            violations.append("_build_legacy_direct_oa_mongo_adapter still exists")
        if "_build_legacy_direct_oa_mongo_adapter()" in initializer:
            violations.append("_initialize_runtime_services still calls legacy OA Mongo adapter builder")
        if "_source_oa_adapter" in server_source:
            violations.append("server.py still keeps legacy _source_oa_adapter state")
        if "source_oa_adapter" in initializer:
            violations.append("_initialize_runtime_services still keeps legacy source_oa_adapter")
        if pending_source:
            violations.append("_oa_pending_payment_source_adapter still exists")
        if "_build_legacy_direct_oa_mongo_adapter()" in pending_source:
            violations.append("_oa_pending_payment_source_adapter reuses legacy bootstrap Mongo adapter")
        if "_source_oa_adapter" in pending_source:
            violations.append("_oa_pending_payment_source_adapter still reads legacy source adapter")
        if "load_mongo_oa_settings" in server_source:
            violations.append("server.py still loads direct OA Mongo settings")

        self.assertEqual(violations, [])

    def test_app_mongo_export_tool_is_removed(self) -> None:
        tool_path = TOOLS_ROOT / "export_app_mongo.py"
        violations: list[str] = []

        if tool_path.exists():
            violations.append("export_app_mongo.py still exists")
        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            source = path.read_text(encoding="utf-8")
            if "export_app_mongo" in source:
                violations.append(f"{_relative(path)} imports or references export_app_mongo")

        self.assertEqual(violations, [])

    def test_app_mongo_shadow_preflight_tools_are_removed(self) -> None:
        removed_tool_names = (
            "run_shadow_read_rehearsal",
            "run_runtime_state_policy_preflight",
            "run_controlled_mirror_write_rehearsal",
        )
        removed_service_names = (
            "shadow_read_psql_store",
        )
        violations: list[str] = []

        for module_name in removed_tool_names:
            if (TOOLS_ROOT / f"{module_name}.py").exists():
                violations.append(f"{module_name}.py still exists")
        for module_name in removed_service_names:
            if (SERVICES_ROOT / f"{module_name}.py").exists():
                violations.append(f"{module_name}.py still exists")
        for path in _python_files(APP_ROOT, SERVICES_ROOT):
            source = path.read_text(encoding="utf-8")
            for module_name in removed_tool_names:
                if module_name in source:
                    violations.append(f"{_relative(path)} imports or references {module_name}")
            for module_name in removed_service_names:
                if module_name in source:
                    violations.append(f"{_relative(path)} imports or references {module_name}")

        self.assertEqual(violations, [])

    def test_cutover_preflight_checker_is_removed(self) -> None:
        service_source = (SERVICES_ROOT / "cutover_preflight.py").read_text(encoding="utf-8")
        violations: list[str] = []

        if (TOOLS_ROOT / "verify_cutover_preflight.py").exists():
            violations.append("verify_cutover_preflight.py still exists")
        for forbidden in ("CutoverPreflightChecker", "CutoverPreflightConfig", "build_checker_from_env"):
            if forbidden in service_source:
                violations.append(f"cutover_preflight.py still exposes {forbidden}")
        if redact_secret_text("failed postgresql://user:secret@db.example.com/fin_ops") != (
            "failed postgresql://user:***@db.example.com/fin_ops"
        ):
            violations.append("cutover_preflight.py no longer redacts URI passwords")

        self.assertEqual(violations, [])

    def test_runtime_convergence_closure_tool_is_removed(self) -> None:
        violations: list[str] = []

        if (TOOLS_ROOT / "run_runtime_convergence_closure.py").exists():
            violations.append("run_runtime_convergence_closure.py still exists")
        if (REPO_ROOT / "tests/test_runtime_convergence_closure.py").exists():
            violations.append("test_runtime_convergence_closure.py still exists")

        self.assertEqual(violations, [])

    def test_oa_attachment_audit_tool_is_removed(self) -> None:
        violations: list[str] = []

        removed_paths = [
            APP_ROOT / "oa_attachment_audit.py",
            TOOLS_ROOT / "oa_attachment_audit.py",
            SERVICES_ROOT / "oa_attachment_audit.py",
            REPO_ROOT / "tests" / "test_oa_attachment_audit.py",
        ]
        violations.extend(f"{_relative(path)} still exists" for path in removed_paths if path.exists())
        for path in (APP_ROOT / "server.py", APP_ROOT / "worker.py"):
            source = path.read_text(encoding="utf-8")
            if "oa_attachment_audit" in source:
                violations.append(f"{_relative(path)} imports or references oa_attachment_audit")
        for path in _python_files(SERVICES_ROOT):
            source = path.read_text(encoding="utf-8")
            if "oa_attachment_audit" in source:
                violations.append(f"{_relative(path)} imports or references oa_attachment_audit")

        self.assertEqual(violations, [])

    def test_legacy_read_model_reconcile_tools_are_removed(self) -> None:
        removed_tool_names = {
            "reconcile_workbench_read_model",
            "reconcile_cost_statistics_read_model",
            "reconcile_tax_offset_read_model",
        }
        forbidden_private_oracles = {
            "_build_raw_workbench_payload",
            "_apply_candidate_matches_to_payload",
            "_cost_statistics_service.get_explorer",
            "_tax_api_routes.get_tax_offset",
        }
        violations: list[str] = []

        for module_name in sorted(removed_tool_names):
            path = TOOLS_ROOT / f"{module_name}.py"
            if path.exists():
                violations.append(f"{module_name}.py still exists")

        for path in _python_files(TOOLS_ROOT):
            rel_path = _relative(path)
            source = path.read_text(encoding="utf-8")
            for module_name in removed_tool_names:
                if module_name in source:
                    violations.append(f"{rel_path} references removed {module_name}")
            for private_oracle in forbidden_private_oracles:
                if private_oracle in source:
                    violations.append(f"{rel_path} uses legacy read model oracle {private_oracle}")

        self.assertEqual(violations, [])

    def test_workbench_write_and_matching_services_do_not_import_external_clients_directly(self) -> None:
        workbench_boundary_files = {
            "backend/src/fin_ops_platform/services/workbench_write_facade.py",
            "backend/src/fin_ops_platform/services/workbench_pair_relation_service.py",
            "backend/src/fin_ops_platform/services/workbench_override_service.py",
            "backend/src/fin_ops_platform/services/workbench_exception_case_service.py",
            "backend/src/fin_ops_platform/services/workbench_exception_application_service.py",
            "backend/src/fin_ops_platform/services/workbench_exception_projection.py",
            "backend/src/fin_ops_platform/services/workbench_exception_classifier.py",
            "backend/src/fin_ops_platform/services/workbench_exception_rules.py",
            "backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py",
            "backend/src/fin_ops_platform/services/workbench_free_matching_engine.py",
            "backend/src/fin_ops_platform/services/workbench_relation_grouping.py",
            "backend/src/fin_ops_platform/services/postgres_repositories/workbench_formal_relation.py",
            "backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_worker.py",
            "backend/src/fin_ops_platform/services/workbench_amount_check_service.py",
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

    def test_legacy_workbench_candidate_and_decision_modules_are_removed(self) -> None:
        removed_modules = {
            "workbench_candidate_grouping",
            "workbench_candidate_match_service",
            "workbench_matching_rules",
            "workbench_matching_dirty_scope_service",
            "workbench_reconciliation_decision_cleanup",
            "workbench_reconciliation_decision_store",
            "workbench_reconciliation_engine",
            "workbench_reconciliation_models",
            "workbench_special_pair_rule_service",
            "workbench_special_reconciliation_adapter",
            "workbench_special_rule_detectors",
        }
        violations: list[str] = []

        for module_name in sorted(removed_modules):
            path = SERVICES_ROOT / f"{module_name}.py"
            if path.exists():
                violations.append(f"{_relative(path)} still exists")
        for path in [*_python_files(APP_ROOT), *_python_files(SERVICES_ROOT)]:
            source = path.read_text(encoding="utf-8")
            for module_name in removed_modules:
                if f"services.{module_name}" in source:
                    violations.append(f"{_relative(path)} imports removed {module_name}")

        self.assertEqual(violations, [])

    def test_legacy_workbench_candidate_state_is_only_sanitized_at_read_boundaries(self) -> None:
        legacy_terms = {
            "automatic_decision",
            "candidate_relation_distribution",
            "candidate_snapshot_version",
            "workbench_candidate",
            "workbench_reconciliation_decision",
        }
        sanitation_allowlist = {
            (
                "backend/src/fin_ops_platform/services/workbench_read_model_service.py",
                "candidate_snapshot_version",
            ): 2,
            (
                "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
                "workbench_reconciliation_decision",
            ): 1,
        }
        observed_allowlist: dict[tuple[str, str], int] = {}
        violations: list[str] = []

        for path in _python_files(APP_ROOT, SERVICES_ROOT, TOOLS_ROOT):
            relative_path = _relative(path)
            source = path.read_text(encoding="utf-8")
            for term in legacy_terms:
                count = source.count(term)
                if not count:
                    continue
                key = (relative_path, term)
                expected_count = sanitation_allowlist.get(key)
                if expected_count is None:
                    violations.append(f"{relative_path} contains legacy Workbench state term {term}")
                    continue
                observed_allowlist[key] = count
                if count != expected_count:
                    violations.append(
                        f"{relative_path} contains {count} {term} references; expected {expected_count} sanitation references"
                    )

        missing_sanitation = sorted(set(sanitation_allowlist) - set(observed_allowlist))
        violations.extend(
            f"{path} no longer contains the explicit {term} read-boundary sanitation"
            for path, term in missing_sanitation
        )
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
            "backend/src/fin_ops_platform/services/oa_payment_status_service.py",
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
            "backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py",
            "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py",
            "backend/src/fin_ops_platform/services/postgres_repositories/workbench.py",
            "backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py",
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

    def test_read_model_refresh_producers_use_scope_gateway_boundary(self) -> None:
        allowed_exact_paths = {
            "backend/src/fin_ops_platform/services/runtime_queue.py",
            "backend/src/fin_ops_platform/services/read_model_refresh_gateway.py",
        }
        violations: list[str] = []
        for path in _python_files(APP_ROOT, SERVICES_ROOT, TOOLS_ROOT, SCRIPTS_ROOT):
            rel_path = _relative(path)
            if rel_path in allowed_exact_paths:
                continue
            tree = _parse(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "enqueue_read_model_refresh"
                    and "queue" in _attribute_chain(node.func.value)
                ):
                    violations.append(f"{rel_path}:{node.lineno}")
                    continue
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "getattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value == "enqueue_read_model_refresh"
                    and "queue" in _attribute_chain(node.args[0])
                ):
                    violations.append(f"{rel_path}:{node.lineno}")
        self.assertEqual(
            violations,
            [],
            "read model refresh producers must use ReadModelRefreshGateway instead of calling enqueue_read_model_refresh directly.",
        )

    def test_no_oa_worker_bootstrap_does_not_load_full_workbench_snapshot(self) -> None:
        worker_source = (APP_ROOT / "worker.py").read_text(encoding="utf-8")

        self.assertNotIn("load_workbench_read_models()", worker_source)

    def test_operations_audit_uses_service_repository_boundary(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        audit_handler_source = server_source[
            server_source.index("    def _operations_audit_service"):
            server_source.index("    def _handle_api_operations_input_invoice_usage_refresh")
        ]
        repository_source = (
            SERVICES_ROOT / "postgres_repositories" / "operations_audit.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("fin_ops_platform.tools.audit_", server_source)
        self.assertNotIn("_state_store", audit_handler_source)
        self.assertNotIn("fin_ops_platform.tools", repository_source)
        self.assertIn("OperationsAuditService", audit_handler_source)

    def test_operations_audit_cli_files_do_not_own_sql_or_database_reads(self) -> None:
        for file_name in (
            "audit_input_invoice_usage_read_model.py",
            "audit_output_invoice_collection_read_model.py",
            "audit_page_business_read_model.py",
        ):
            path = TOOLS_ROOT / file_name
            source = path.read_text(encoding="utf-8")
            with self.subTest(file_name=file_name):
                self.assertNotIn("/* check:", source)
                self.assertNotIn("_PREDICATE", source)
                self.assertEqual(_attribute_calls(_parse(path), {"fetch_one", "fetch_all", "execute"}), [])

        repository_root = SERVICES_ROOT / "postgres_repositories"
        common_source = (repository_root / "invoice_read_model_audit.py").read_text(encoding="utf-8")
        self.assertIn("class InvoiceReadModelAuditContract", common_source)
        for file_name in ("input_invoice_usage_audit.py", "output_invoice_collection_audit.py"):
            wrapper_source = (repository_root / file_name).read_text(encoding="utf-8")
            with self.subTest(repository_file=file_name):
                self.assertNotIn("/* check:", wrapper_source)
                self.assertIn("audit_invoice_read_model", wrapper_source)

    def test_raw_postgres_sql_in_services_is_classified_by_platform_boundary(self) -> None:
        allowed_exact_paths = {
            "backend/src/fin_ops_platform/services/bank_account_balance_projection.py",
            "backend/src/fin_ops_platform/services/file_object_migration.py",
            "backend/src/fin_ops_platform/services/import_job_queue.py",
            "backend/src/fin_ops_platform/services/oa_payment_status_service.py",
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

class RuntimeWorkerEtcImportLinkExistingTests(unittest.TestCase):
    def test_etc_oa_workflow_methods_do_not_link_or_refresh_canonical_invoice_facts(self) -> None:
        self.assertIn(
            "_link_existing_canonical_invoices",
            inspect.getsource(EtcBusinessBatchApplicationService.confirm_import_payload),
        )
        for method in (
            EtcBusinessBatchApplicationService.create_oa_draft_payload,
            EtcBusinessBatchApplicationService.recover_oa_draft_payload,
            EtcBusinessBatchApplicationService.revoke_oa_draft_payload,
            EtcBusinessBatchApplicationService.manual_oa_status_payload,
        ):
            with self.subTest(method=method.__name__):
                self.assertNotIn("_link_existing_canonical_invoices", inspect.getsource(method))
        self.assertNotIn(
            "_refresh_business_batch_status_change",
            inspect.getsource(EtcBusinessBatchApplicationService.create_oa_draft_payload),
        )
        for method in (
            EtcBusinessBatchApplicationService.revoke_oa_draft_payload,
            EtcBusinessBatchApplicationService.manual_oa_status_payload,
        ):
            with self.subTest(status_refresh_method=method.__name__):
                self.assertIn("_refresh_business_batch_status_change", inspect.getsource(method))

    def test_etc_invoice_refresh_uses_changed_months_once_without_all_scope_or_duplicate_matching(self) -> None:
        api_source = inspect.getsource(server_module.Application._refresh_after_etc_invoice_link)
        worker_source = inspect.getsource(_RuntimeWorkerDerivedLifecycle.refresh_after_etc_invoice_link)

        for source in (api_source, worker_source):
            with self.subTest(source=source.splitlines()[0].strip()):
                self.assertIn("include_all=False", source)
                self.assertNotIn("schedule_workbench_matching", source)
                self.assertNotIn("_schedule_or_run_workbench_auto_matching_for_scopes", source)

    def test_cost_and_tax_pages_ignore_etc_batch_only_domain_events(self) -> None:
        for path in (
            WEB_SRC_ROOT / "pages" / "CostStatisticsPage.tsx",
            WEB_SRC_ROOT / "pages" / "TaxOffsetPage.tsx",
        ):
            with self.subTest(path=_relative(path)):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn(
                    "useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.etcBusinessBatchUpdated",
                    source,
                )
        etc_page_source = (WEB_SRC_ROOT / "pages" / "EtcTicketManagementPage.tsx").read_text(encoding="utf-8")
        self.assertNotIn("emitEtcBusinessDomainUpdated", etc_page_source)
        self.assertEqual(etc_page_source.count("FINANCE_DOMAIN_EVENTS.invoiceFactUpdated"), 2)
        create_draft_source = etc_page_source.split("const handleCreateDraft", maxsplit=1)[1].split(
            "const resolveOaActionBatch", maxsplit=1
        )[0]
        manual_status_source = etc_page_source.split("const handleManualBusinessBatchOaStatus", maxsplit=1)[1].split(
            "const renderOaDecisionActions", maxsplit=1
        )[0]
        for source in (create_draft_source, manual_status_source):
            self.assertIn("FINANCE_DOMAIN_EVENTS.etcBusinessBatchUpdated", source)
            self.assertNotIn("FINANCE_DOMAIN_EVENTS.invoiceFactUpdated", source)

    def test_removed_etc_oa_lifecycle_events_have_no_production_code(self) -> None:
        violations = []
        for path in _python_files(SOURCE_ROOT):
            source = path.read_text(encoding="utf-8")
            for event in ("etc_oa_submitted", "etc_oa_revoked"):
                if event in source:
                    violations.append(f"{_relative(path)}:{event}")

        self.assertEqual(violations, [])

    def test_existing_invoice_link_service_uses_import_items_to_load_existing_invoices(self) -> None:
        upserted: list[object] = []

        class ImportService:
            def upsert_etc_invoice(self, etc_invoice: object) -> object:
                upserted.append(etc_invoice)
                return SimpleNamespace(
                    invoice=SimpleNamespace(invoice_date=getattr(etc_invoice, "issue_date", None)),
                    changed=True,
                )

        class EtcService:
            def __init__(self) -> None:
                self.invoice_numbers: list[str] = []

            def list_invoices_by_numbers(self, invoice_numbers: list[str]) -> list[object]:
                self.invoice_numbers = list(invoice_numbers)
                return [
                    SimpleNamespace(
                        id="etc_invoice_0514",
                        invoice_number="26537911470300077680",
                        issue_date="2026-03-31",
                        seller_name="昆明新机场高速公路建设发展有限公司",
                        total_amount=Decimal("9.22"),
                        passage_start_date=None,
                        passage_end_date=None,
                    )
                ]

        etc_service = EtcService()
        link_service = EtcExistingInvoiceLinkService(import_service=ImportService(), etc_service=etc_service)

        months = link_service.link_import_result_to_existing_invoices(
            EtcImportResult(
                imported=1,
                items=[
                    EtcImportItem(
                        file_name="invoice.xml",
                        invoice_number="26537911470300077680",
                        status="imported",
                    )
                ],
            )
        )

        self.assertEqual(etc_service.invoice_numbers, ["26537911470300077680"])
        self.assertEqual([getattr(item, "invoice_number") for item in upserted], ["26537911470300077680"])
        self.assertEqual(months, ["2026-03"])

    def test_existing_invoice_link_service_persists_linked_invoices_when_configured(self) -> None:
        persisted: list[list[object]] = []
        linked_invoice = SimpleNamespace(invoice_date="2026-04-28")

        class ImportService:
            def upsert_etc_invoice(self, etc_invoice: object) -> object:
                return SimpleNamespace(invoice=linked_invoice, changed=True)

        link_service = EtcExistingInvoiceLinkService(
            import_service=ImportService(),
            persist_linked_invoices=lambda invoices: persisted.append(list(invoices)),
        )

        months = link_service.link_etc_invoices_to_existing_invoices(
            [
                SimpleNamespace(
                    invoice_number="26537912210400752259",
                    issue_date="2026-04-28",
                    passage_start_date=None,
                    passage_end_date=None,
                )
            ]
        )

        self.assertEqual(months, ["2026-04"])
        self.assertEqual(persisted, [[linked_invoice]])

    def test_link_etc_import_result_uses_import_items_to_load_existing_invoices(self) -> None:
        upserted: list[object] = []

        class ImportService:
            def upsert_etc_invoice(self, etc_invoice: object) -> object:
                upserted.append(etc_invoice)
                return SimpleNamespace(
                    invoice=SimpleNamespace(invoice_date=getattr(etc_invoice, "issue_date", None)),
                    changed=True,
                )

        class EtcService:
            def __init__(self) -> None:
                self.invoice_numbers: list[str] = []

            def list_invoices_by_numbers(self, invoice_numbers: list[str]) -> list[object]:
                self.invoice_numbers = list(invoice_numbers)
                return [
                    SimpleNamespace(
                        id="etc_invoice_0514",
                        invoice_number="26537911470300077680",
                        issue_date="2026-03-31",
                        seller_name="昆明新机场高速公路建设发展有限公司",
                        total_amount=Decimal("9.22"),
                        passage_start_date=None,
                        passage_end_date=None,
                    )
                ]

        etc_service = EtcService()
        persisted: list[list[object]] = []
        link = _link_etc_import_result_to_existing_invoices(
            ImportService(),
            etc_service,
            SimpleNamespace(save_invoice_etc_metadata=lambda invoices: persisted.append(list(invoices))),
        )

        months = link(
            EtcImportResult(
                imported=1,
                items=[
                    EtcImportItem(
                        file_name="invoice.xml",
                        invoice_number="26537911470300077680",
                        status="imported",
                    )
                ],
            )
        )

        self.assertEqual(etc_service.invoice_numbers, ["26537911470300077680"])
        self.assertEqual([getattr(item, "invoice_number") for item in upserted], ["26537911470300077680"])
        self.assertEqual(months, ["2026-03"])
        self.assertEqual(len(persisted), 1)

    def test_link_etc_import_result_tolerates_missing_canonical_invoice_without_creation(self) -> None:
        upserted: list[object] = []

        class ImportService:
            def upsert_etc_invoice(self, etc_invoice: object) -> object:
                upserted.append(etc_invoice)
                return SimpleNamespace(invoice=None, changed=False)

        class EtcService:
            def list_invoices_by_numbers(self, invoice_numbers: list[str]) -> list[object]:
                return [
                    SimpleNamespace(
                        id="etc_invoice_9999",
                        invoice_number=invoice_numbers[0],
                        issue_date="2026-04-28",
                        passage_start_date=None,
                        passage_end_date=None,
                    )
                ]

        link = _link_etc_import_result_to_existing_invoices(
            ImportService(),
            EtcService(),
            SimpleNamespace(save_invoice_etc_metadata=lambda _invoices: None),
        )

        months = link(
            EtcImportResult(
                imported=1,
                items=[
                    EtcImportItem(
                        file_name="invoice.xml",
                        invoice_number="26537912210400752259",
                        status="imported",
                    )
                ],
            )
        )

        self.assertEqual([getattr(item, "invoice_number") for item in upserted], ["26537912210400752259"])
        self.assertEqual(months, [])

    def test_runtime_etc_import_link_never_calls_canonical_invoice_create_api(self) -> None:
        forbidden_calls: list[str] = []

        class ImportService:
            def upsert_etc_invoice(self, etc_invoice: object) -> object:
                return SimpleNamespace(invoice=None, changed=False)

            def upsert_invoice(self, *_args: object, **_kwargs: object) -> None:
                forbidden_calls.append("upsert_invoice")

            def create_invoice(self, *_args: object, **_kwargs: object) -> None:
                forbidden_calls.append("create_invoice")

            def register_invoice(self, *_args: object, **_kwargs: object) -> None:
                forbidden_calls.append("register_invoice")

        class EtcService:
            def list_invoices_by_numbers(self, invoice_numbers: list[str]) -> list[object]:
                return [
                    SimpleNamespace(
                        id="etc_invoice_missing_canonical",
                        invoice_number=invoice_numbers[0],
                        issue_date="2026-04-28",
                        passage_start_date=None,
                        passage_end_date=None,
                    )
                ]

        link = _link_etc_import_result_to_existing_invoices(
            ImportService(),
            EtcService(),
            SimpleNamespace(save_invoice_etc_metadata=lambda _invoices: None),
        )

        months = link(
            EtcImportResult(
                imported=1,
                items=[
                    EtcImportItem(
                        file_name="invoice.xml",
                        invoice_number="26537912210400752259",
                        status="imported",
                    )
                ],
            )
        )

        self.assertEqual(months, [])
        self.assertEqual(forbidden_calls, [])

    def test_existing_invoice_link_service_skips_persistence_and_scope_for_unchanged_replay(self) -> None:
        persisted: list[list[object]] = []

        class ImportService:
            def upsert_etc_invoice(self, _etc_invoice: object) -> object:
                return SimpleNamespace(invoice=SimpleNamespace(invoice_date="2026-04-28"), changed=False)

        link_service = EtcExistingInvoiceLinkService(
            import_service=ImportService(),
            persist_linked_invoices=lambda invoices: persisted.append(list(invoices)),
        )

        months = link_service.link_etc_invoices_to_existing_invoices(
            [SimpleNamespace(issue_date="2026-04-28", passage_start_date=None, passage_end_date=None)]
        )

        self.assertEqual(months, [])
        self.assertEqual(persisted, [])

if __name__ == "__main__":
    unittest.main()
