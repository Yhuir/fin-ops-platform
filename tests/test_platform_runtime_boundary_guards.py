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
    def test_bank_flow_canonical_draft_runtime_chain_stays_deleted(self) -> None:
        retired_files = (
            SERVICES_ROOT / "bank_flow_rule_batch_canonical_draft_owner.py",
            SERVICES_ROOT / "bank_flow_rule_batch_canonical_draft_producer.py",
            SERVICES_ROOT / "bank_flow_rule_batch_derived_lifecycle_executor.py",
            REPO_ROOT / "deploy" / "oa" / "env" / "fin-ops.worker.bank-flow-rule-batch.env.example",
        )
        retired_tokens = (
            "bank_flow_rule_batch.canonical_draft.refresh",
            "BankFlowRuleBatchCanonicalDraftOwner",
            "BankFlowRuleBatchCanonicalDraftProducer",
            "BankFlowRuleBatchDerivedLifecycleExecutor",
            "--enable-bank-flow-rule-batch-canonical-draft-refresh",
            "bank-flow-rule-batch-canonical-draft",
            "enqueue_bank_flow_canonical_drafts",
            "bank_flow_rule_batch_canonical_draft_scope_lock",
            "save_bank_flow_rule_batches_scope",
        )
        production_roots = (
            SOURCE_ROOT,
            REPO_ROOT / "scripts",
            REPO_ROOT / "deploy",
        )
        violations = [
            f"retired file still exists: {_relative(path)}"
            for path in retired_files
            if path.exists()
        ]
        for path in (
            candidate
            for root in production_roots
            for candidate in root.rglob("*")
            if candidate.is_file()
            and (
                candidate.suffix in {".py", ".sh"}
                or ".env" in candidate.name
            )
        ):
            source = path.read_text(encoding="utf-8", errors="ignore")
            for token in retired_tokens:
                if token in source:
                    violations.append(
                        f"{_relative(path)} retains retired bank-flow draft token {token}"
                    )

        self.assertEqual(violations, [])

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

    def test_workbench_refresh_enqueue_is_exact_and_does_not_fan_out_other_domains(self) -> None:
        source_path = APP_ROOT / "server.py"
        source = source_path.read_text(encoding="utf-8")
        function_source = _function_source(
            _parse(source_path),
            source,
            "_enqueue_workbench_read_model_refresh",
        )

        self.assertNotIn("_invalidate_invoice_usage_collection_read_model_scopes", function_source)
        self.assertNotIn("_enqueue_input_invoice_usage_read_model_refresh", function_source)
        self.assertNotIn("_enqueue_output_invoice_collection_read_model_refresh", function_source)
        self.assertNotIn("_enqueue_oa_pending_payment_read_model_refresh", function_source)
        self.assertNotIn("_invalidate_cost_statistics_read_model_scopes", function_source)
        self.assertNotIn("_invalidate_tax_offset_read_model_scopes", function_source)
        self.assertNotIn("_search_read_model_refresh_producer", function_source)

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

    def test_local_backend_launcher_does_not_restore_app_mongo_runtime(self) -> None:
        source = (REPO_ROOT / "scripts" / "start-backend.sh").read_text(encoding="utf-8")

        self.assertNotIn("FIN_OPS_APP_MONGO_", source)
        self.assertNotIn("mongo_only", source)
        self.assertNotIn("FIN_OPS_STORAGE_MODE", source)

    def test_api_runtime_uses_bounded_gunicorn_and_graceful_reload_pidfile(self) -> None:
        launcher = (REPO_ROOT / "scripts" / "start-backend.sh").read_text(encoding="utf-8")
        unit = (REPO_ROOT / "deploy" / "oa" / "systemd" / "fin-ops.service.example").read_text(
            encoding="utf-8"
        )
        common_env = (REPO_ROOT / "deploy" / "oa" / "env" / "fin-ops.common.env.example").read_text(
            encoding="utf-8"
        )
        gunicorn_config = (APP_ROOT / "gunicorn_conf.py").read_text(encoding="utf-8")

        for source in (launcher, unit):
            self.assertIn("gunicorn", source)
            self.assertNotIn("fin_ops_platform.app.main --host", source)
        self.assertIn('worker_class = "gthread"', gunicorn_config)
        self.assertIn("FIN_OPS_HTTP_PIDFILE", gunicorn_config)
        self.assertIn("FIN_OPS_HTTP_WORKERS=1", common_env)
        self.assertIn("FIN_OPS_HTTP_THREADS=10", common_env)
        self.assertIn("RuntimeDirectory=fin-ops", unit)

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
                "WorkbenchPairRelationService": 0,
                "pair_relation_service": 0,
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

    def test_application_state_store_has_no_tax_read_model_runtime(self) -> None:
        path = SERVICES_ROOT / "state_store.py"
        source = path.read_text(encoding="utf-8")
        class_source = _class_source(_parse(path), source, "ApplicationStateStore")
        class_tree = ast.parse(class_source)
        method_names = (
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
            "load_tax_offset_read_models",
            "save_tax_offset_read_models",
            '"tax_offset_read_models"',
        ):
            if forbidden in source:
                violations.append(f"state_store.py contains {forbidden}")

        self.assertEqual(violations, [])

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

    def test_real_redis_client_is_confined_and_rabbitmq_client_is_absent(self) -> None:
        allowed_imports = {
            "redis": {"backend/src/fin_ops_platform/services/runtime_redis.py"},
            "pika": set(),
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
            SERVICES_ROOT / "pending_invoice_rules_application_service.py",
        }
        self.assertFalse((SERVICES_ROOT / "pending_invoice_lifecycle_service.py").exists())
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

    def test_pending_invoice_page_reads_canonical_facts_without_read_model_runtime(self) -> None:
        canonical_query_path = SERVICES_ROOT / "pending_invoice_canonical_query.py"
        source = canonical_query_path.read_text(encoding="utf-8")

        for retired_path in (
            SERVICES_ROOT / "invoice_lifecycle_sql_projection.py",
            SERVICES_ROOT / "invoice_lifecycle_read_facade.py",
            SERVICES_ROOT / "invoice_lifecycle_read_model_repository.py",
            SERVICES_ROOT / "invoice_lifecycle_read_model_refresh.py",
            SERVICES_ROOT / "pending_invoice_read_model_repository.py",
            SERVICES_ROOT / "pending_invoice_read_model_service.py",
        ):
            self.assertFalse(retired_path.exists(), retired_path.name)
        self.assertIn("class PostgresPendingInvoiceCanonicalRepository", source)
        self.assertIn("class PendingInvoiceCanonicalQueryService", source)
        self.assertIn("set transaction isolation level repeatable read read only", source)
        self.assertIn("app.bank_transactions", source)
        self.assertIn("app.workbench_pair_relations", source)

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

    def test_workbench_page_reads_are_direct_and_have_no_freshness_runtime(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        routes_source = (APP_ROOT / "routes_workbench.py").read_text(encoding="utf-8")
        facade_source = (SERVICES_ROOT / "workbench_query_facade.py").read_text(encoding="utf-8")
        violations: list[str] = []

        for retired_path in (
            SERVICES_ROOT / "workbench_query_freshness_service.py",
            SERVICES_ROOT / "workbench_read_model_refresh.py",
            SERVICES_ROOT / "workbench_refresh_status_payload.py",
            SERVICES_ROOT / "workbench_groups_page_cache.py",
        ):
            if retired_path.exists():
                violations.append(f"retired Workbench page runtime still exists: {_relative(retired_path)}")
        for forbidden in (
            "_workbench_page_relation_status",
            "page_dependency_status",
            "api_initial_page_relation_dependency_stale",
            "read_model_dependency_statuses",
            "WorkbenchQueryFreshnessService",
            "refresh_status",
            "active_generation",
        ):
            if forbidden in server_source or forbidden in facade_source or forbidden in routes_source:
                violations.append(
                    f"Workbench direct page runtime still contains freshness marker {forbidden}"
                )
        if "repository=getattr(self, \"_workbench_page_query_repository\", None)" not in server_source:
            violations.append("server.py does not inject the direct Workbench page query repository")
        if "Direct-only Workbench page query boundary" not in facade_source:
            violations.append("Workbench query facade does not declare its direct-only boundary")

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
            "_workbench_oa_sync_safety_guard(payload)",
            "_workbench_write_auth_context(headers, session=access_session)",
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
            "_workbench_oa_sync_safety_guard(payload)",
            "_workbench_write_auth_context(headers, session=access_session)",
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
            "_workbench_oa_sync_safety_guard(payload)",
            "_workbench_write_auth_context(headers, session=access_session)",
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
                "_workbench_oa_sync_safety_guard(payload)",
                f"_workbench_action_api_routes.{route_method}(payload, request_id=request_id)",
                "_workbench_write_response(result)",
            ):
                if marker not in handler_source:
                    violations.append(f"{handler_name} no longer preserves marker {marker}")
            if f"_workbench_write_facade().{route_method}" in handler_source:
                violations.append(f"{handler_name} still calls WorkbenchWriteFacade.{route_method} directly")

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
            "_workbench_oa_sync_safety_guard(payload)",
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
            SERVICES_ROOT / "bank_transaction_category_mutation_writer.py": "class BankTransactionCategoryMutationWriter",
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
            "self._bank_transaction_category_service.confirm_auto_category(",
            "self._bank_transaction_category_service.assign_manual_category(",
            "self._persist_category_mutation(",
        }
        for snippet in sorted(required_service_snippets):
            if snippet not in service_source:
                violations.append(f"BankDetailsApplicationService is missing boundary behavior {snippet}")

        for removed_service_snippet in (
            "def finalize_auto_tag_rules_update",
            "self._execute_derived_data_lifecycle_event(",
            "self._enqueue_turnover_ledger_read_model_refreshes(",
            "self._invalidate_after_category_mutation(",
        ):
            if removed_service_snippet in service_source:
                violations.append(
                    f"BankDetailsApplicationService retains removed fan-out behavior {removed_service_snippet}"
                )

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
        canonical_source = (SERVICES_ROOT / "bank_details_canonical_query.py").read_text(
            encoding="utf-8"
        )
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

        factory_source = _function_source(server_tree, server_source, "_bank_details_application_service")
        for removed_helper_name in sorted(removed_application_helpers):
            if removed_helper_name in factory_source:
                violations.append(f"BankDetailsApplicationService factory still injects removed helper {removed_helper_name}")
        for required in (
            "query_service=query_service",
            "BankDetailsCanonicalQueryService(",
            "PostgresBankDetailsCanonicalQueryRepository(connection)",
        ):
            if required not in factory_source:
                violations.append(f"BankDetailsApplicationService factory is missing canonical query wiring {required}")
        for forbidden in (
            "read_model_status",
            "enqueue_read_model",
            "_get_cached_payload",
            "_set_cached_payload",
        ):
            if forbidden in service_source:
                violations.append(f"BankDetailsApplicationService still owns retired page read-model behavior {forbidden}")
        if "set transaction isolation level repeatable read read only" not in canonical_source:
            violations.append("bank details canonical query does not open a repeatable-read/read-only snapshot")

        self.assertEqual(violations, [])

    def test_invoice_lifecycle_derived_lifecycle_runtime_is_retired(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        violations: list[str] = []

        for removed_helper in (
            "_derived_lifecycle_invoice_lifecycle_executor",
            "_invoice_lifecycle_derived_lifecycle_executor",
        ):
            if _function_source(server_tree, server_source, removed_helper):
                violations.append(f"server.py still owns retired invoice lifecycle executor {removed_helper}")
        for retired_snippet in (
            "InvoiceLifecycleDerivedLifecycleExecutor(",
            '"invoice_lifecycle_read_model":',
            "invoice_lifecycle.read_model.refresh",
        ):
            if retired_snippet in server_source:
                violations.append(f"server.py still assembles retired invoice lifecycle runtime {retired_snippet}")

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
            'route_path.startswith("/api/cost-statistics/bank-transactions/")',
            'route_path.startswith("/api/cost-statistics/allocations/")',
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

    def test_cost_statistics_direct_canonical_boundary_has_no_legacy_read_model_path(self) -> None:
        repository_path = SERVICES_ROOT / "cost_statistics_canonical_repository.py"
        query_path = SERVICES_ROOT / "cost_statistics_query_service.py"
        repository_source = repository_path.read_text(encoding="utf-8")
        query_source = query_path.read_text(encoding="utf-8")
        runtime_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                APP_ROOT / "worker.py",
                SERVICES_ROOT / "runtime_worker_registry.py",
            )
        )
        self.assertFalse((SERVICES_ROOT / "read_model_manifest.py").exists())
        self.assertFalse((SERVICES_ROOT / "read_model_scope_policy.py").exists())

        self.assertIn("set transaction isolation level repeatable read read only", repository_source)
        for table in (
            "app.bank_transactions",
            "app.oa_applications",
            "app.workbench_pair_relations",
            "app.bank_transaction_categories",
            "app.bank_transaction_category_confirmations",
            "app.app_settings",
        ):
            self.assertIn(table, repository_source)
        self.assertIn("normalized_payload", repository_source)
        self.assertIn("COMPLETED_WORKFLOW_STATUS_ALIASES", repository_source)
        self.assertIn("approved_at", repository_source)
        self.assertNotIn('/api/cost-statistics/transactions/', repository_source + query_source)
        self.assertIn("self._canonical_repository.load_snapshot(", query_source)
        self.assertIn("scope_kind=scope_kind", query_source)
        self.assertIn("include_statistics=False", query_source)
        for forbidden in (
            "read_model.cost_statistics",
            "ReadModelRefreshGateway",
            "cost_statistics.read_model.refresh",
            "CostStatisticsReadModelNotFreshError",
        ):
            self.assertNotIn(forbidden, repository_source + query_source + runtime_sources)
        for removed_name in (
            "cost_statistics_derived_lifecycle_executor.py",
            "cost_statistics_read_model_refresh.py",
            "cost_statistics_read_model_repository.py",
            "cost_statistics_runtime_service.py",
            "cost_statistics_source_versions.py",
            "cost_statistics_sql_projection.py",
        ):
            self.assertFalse((SERVICES_ROOT / removed_name).exists(), removed_name)

    def test_oa_pending_page_reads_canonical_rows_without_freshness_polling(self) -> None:
        page_source = (WEB_SRC_ROOT / "pages" / "OaPendingPaymentsPage.tsx").read_text(encoding="utf-8")

        for forbidden in (
            "waitForOperationFreshness",
            '../features/operationBarrier/api',
            "/api/operation-barrier/status",
            "setConditionalPollingEnabled",
            "CONDITIONAL_REFRESH_INTERVAL_MS",
            "document.visibilityState",
        ):
            self.assertNotIn(forbidden, page_source)
        self.assertIn("fetchOaPendingPaymentRows({", page_source)

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

    def test_tax_offset_derived_lifecycle_runtime_is_retired(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        violations: list[str] = []

        removed_helpers = {
            "_derived_lifecycle_tax_offset_executor",
            "_derived_lifecycle_tax_offset_month_cache_executor",
            "_tax_offset_derived_lifecycle_executor",
        }
        for helper_name in sorted(removed_helpers):
            if _function_source(server_tree, server_source, helper_name):
                violations.append(f"server.py still owns retired tax offset lifecycle executor {helper_name}")
        for retired_snippet in (
            "TaxOffsetDerivedLifecycleExecutor(",
            '"tax_offset_read_model":',
            '"tax_offset_month_cache":',
        ):
            if retired_snippet in server_source:
                violations.append(f"server.py still assembles retired tax offset runtime {retired_snippet}")

        self.assertEqual(violations, [])

    def test_output_invoice_collection_boundary_does_not_depend_on_redis_or_rabbitmq_clients(self) -> None:
        output_invoice_collection_paths = {
            APP_ROOT / "routes_output_invoice_collections.py",
            SERVICES_ROOT / "output_invoice_collection_canonical_query_service.py",
            SERVICES_ROOT / "output_invoice_collection_service.py",
            SERVICES_ROOT / "postgres_repositories" / "invoice_usage_collection_query.py",
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
        for retired_path in (
            SERVICES_ROOT / "output_invoice_collection_lifecycle_service.py",
            SERVICES_ROOT / "output_invoice_collection_models.py",
            SERVICES_ROOT / "output_invoice_collection_receipt_service.py",
            SERVICES_ROOT / "output_invoice_collection_status_service.py",
            SERVICES_ROOT / "postgres_repositories" / "output_invoice_collection.py",
        ):
            if retired_path.exists():
                violations.append(f"{_relative(retired_path)} must be removed")

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
        query_source = (
            SERVICES_ROOT / "output_invoice_collection_canonical_query_service.py"
        ).read_text(encoding="utf-8")
        repository_source = (
            SERVICES_ROOT
            / "postgres_repositories"
            / "invoice_usage_collection_query.py"
        ).read_text(encoding="utf-8")
        violations: list[str] = []

        for required in (
            "def route(",
            "/api/output-invoice-collections/rows",
            "/api/output-invoice-collections/filter-options",
            "/api/output-invoice-collections/export-preview",
            "/api/output-invoice-collections/export",
            "/api/output-invoice-collections/invoices/",
            "/api/output-invoice-collections/bank-transactions/",
            "/api/output-invoice-collections/rows/",
            "def _json_read(",
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
            "read_model_status",
            "readModelStatus",
            "/status-rules",
            "/receipt",
            "/collection-status",
            "/collection-reminder",
            "/red-invoice-relations",
            "def _json_body_mutation(",
            "def _json_session(",
            "_idempotency_key(headers)",
            "_trace_id(headers)",
        ):
            if forbidden in route_class:
                violations.append(
                    f"Output collection route owner keeps removed read-model marker {forbidden}"
                )
        for required in (
            "class OutputInvoiceCollectionCanonicalQueryService",
            "def rows(",
            "def filter_options(",
            "def export_preview(",
            "def export(",
            "def relation_details(",
        ):
            if required not in query_source:
                violations.append(
                    f"Output collection canonical query service is missing {required}"
                )
        if "query_service=self._output_invoice_collection_page_query_service()" not in factory_source:
            violations.append(
                "Application output collection route factory must inject the canonical query service"
            )
        if "_output_invoice_collection_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("Application does not dispatch output collection read routes through route owner")
        if "def _output_invoice_collection_xlsx_response(" not in server_source:
            violations.append("Application is missing explicit output collection xlsx response port")
        for required in (
            "set transaction isolation level repeatable read read only",
            "app.workbench_pair_relations",
            "relation.status = 'active'",
            "app.invoices",
        ):
            if required not in repository_source:
                violations.append(
                    f"Output collection canonical repository is missing {required}"
                )
        for retired in (
            "output_invoice_collection_read_application_service.py",
            "output_invoice_collection_read_model_fresh_gate_service.py",
            "output_invoice_collection_read_model_detail_service.py",
        ):
            if (SERVICES_ROOT / retired).exists():
                violations.append(f"Retired output collection service still exists: {retired}")
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
        query_service_path = SERVICES_ROOT / "oa_pending_payment_query_service.py"
        command_service_path = SERVICES_ROOT / "oa_pending_payment_command_service.py"
        read_model_service_path = SERVICES_ROOT / "oa_pending_payment_read_model_service.py"
        query_repository_path = SERVICES_ROOT / "postgres_repositories" / "oa_pending_payment_query.py"
        retired_relation_repository_path = SERVICES_ROOT / "postgres_repositories" / "oa_pending_payment_relation.py"
        retired_promotion_service_path = SERVICES_ROOT / "oa_pending_payment_relation_promotion_service.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        route_class = _class_source(route_tree, route_source, "OaPendingPaymentApiRoutes")
        command_service_source = command_service_path.read_text(encoding="utf-8")
        query_service_source = query_service_path.read_text(encoding="utf-8")
        query_repository_source = query_repository_path.read_text(encoding="utf-8")
        violations: list[str] = []
        if retired_query_service_path.exists():
            violations.append("retired OA live query service still exists")
        if read_model_service_path.exists():
            violations.append("retired OA pending-payment read model service still exists")
        if retired_relation_repository_path.exists():
            violations.append("retired OA pending-payment relation repository still exists")
        if retired_promotion_service_path.exists():
            violations.append("retired OA pending-payment promotion service still exists")

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
            "def _query_service_required(",
        ):
            if required not in route_class:
                violations.append(f"OA pending payment route owner is missing {required}")
        if "_oa_pending_payment_routes().route(method, route_path, query, body, headers)" not in server_source:
            violations.append("Application does not dispatch OA pending payment routes through route owner")
        for forbidden_fallback in (
            "/api/oa-pending-payments/filter-options",
            "def filter_options(",
            "def all_rows(",
            "self._query_service.list_rows",
            "self._query_service.filter_options",
            "self._query_service.oa_detail",
            "self._query_service.bank_transaction_detail",
            "self._query_service.invoice_detail",
            "self._query_service.row_relation_details",
        ):
            if forbidden_fallback in route_class:
                violations.append(f"OA pending payment route owner still has live read fallback {forbidden_fallback}")
        for required in (
            "with repository.snapshot() as snapshot:",
            "snapshot.select_page(",
            "snapshot.bank_transaction_candidates(",
        ):
            if required not in query_service_source:
                violations.append(f"OA canonical query service is missing {required}")
        for required in (
            "set transaction isolation level repeatable read read only",
            "app.oa_applications",
            "app.oa_pending_payment_admissions",
            "app.workbench_pair_relations",
            "relation.status = 'active'",
        ):
            if required not in query_repository_source:
                violations.append(f"OA canonical query repository is missing {required}")
        for forbidden in (
            "ReadModelRefresh",
            "read_model_status",
            "read_model_repository",
            "source_versions",
            "enqueue",
            "Redis",
        ):
            if forbidden in query_service_source + query_repository_source:
                violations.append(f"OA canonical page query still depends on {forbidden}")
        source_projection = _function_source(server_tree, server_source, "_oa_pending_payment_source_projection")
        if "_oa_adapter" in source_projection:
            violations.append("OA pending payment source projection still falls back to Workbench's private OA adapter")
        for retired_symbol in (
            "PostgresOaPendingPaymentRelationRepository",
            "OaPendingPaymentRelationPromotionService",
            "_oa_pending_payment_relation_repository",
        ):
            if retired_symbol in server_source + command_service_source + query_repository_source:
                violations.append(f"OA pending payment runtime still references {retired_symbol}")
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
        if "_enqueue_refreshes_for_records" in command_service_source:
            violations.append("OA payment command still owns ordinary write-time read-model fan-out")
        if "enqueue_workbench_refresh=" in command_composition or "enqueue_oa_pending_payment_refresh=" in command_composition:
            violations.append("OA payment command composition still injects downstream refresh callbacks")
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
            SERVICES_ROOT / "invoice_relation_query_context.py",
            SERVICES_ROOT / "input_invoice_usage_service.py",
            SERVICES_ROOT / "output_invoice_collection_service.py",
            SERVICES_ROOT / "bank_details_relation_tag_projection_service.py",
            SERVICES_ROOT / "pending_invoice_service.py",
            SERVICES_ROOT / "batch_accounting_service.py",
            SERVICES_ROOT / "no_oa_bank_batch_application_service.py",
            SERVICES_ROOT / "no_oa_bank_batch_service.py",
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

    def test_untrusted_document_parsing_stays_behind_strict_shared_boundary(self) -> None:
        policy_path = SERVICES_ROOT / "untrusted_document_policy.py"
        policy_source = policy_path.read_text(encoding="utf-8")
        source_upload_source = (SERVICES_ROOT / "etc_reconciliation_source_upload_service.py").read_text(
            encoding="utf-8"
        )
        oa_attachment_source = (SERVICES_ROOT / "oa_attachment_invoice_service.py").read_text(encoding="utf-8")
        requirements = (REPO_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
        deploy_control = (REPO_ROOT / "deploy" / "oa" / "bin" / "finops-deploy-control.sh").read_text(
            encoding="utf-8"
        )

        image_open_owners = [
            path
            for path in _python_files(SOURCE_ROOT)
            if "Image.open(" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(image_open_owners, [policy_path])
        self.assertIn('formats=("JPEG", "PNG")', policy_source)
        self.assertIn("inspect_untrusted_document(", source_upload_source)
        self.assertIn("inspect_untrusted_document(", oa_attachment_source)
        self.assertNotIn("_iter_image_ocr_inputs", oa_attachment_source)
        self.assertNotIn("pdftotext", (SERVICES_ROOT / "etc_document_parsers.py").read_text(encoding="utf-8"))
        self.assertIn("pillow==12.3.0", requirements)
        self.assertIn("pdfplumber==0.11.10", requirements)
        self.assertIn("pip_audit", deploy_control)

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

    def test_etc_repair_service_does_not_keep_direct_relation_write_fallback(self) -> None:
        checks = {
            "backend/src/fin_ops_platform/services/historical_etc_repair_service.py": {
                "_reconcile_batch": "_pair_relation_service.create_active_relation",
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
        canonical_query_source = (
            SERVICES_ROOT / "input_invoice_usage_canonical_query_service.py"
        ).read_text(encoding="utf-8")
        repository_source = (
            SERVICES_ROOT
            / "postgres_repositories"
            / "invoice_usage_collection_query.py"
        ).read_text(encoding="utf-8")
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
            "query_service=query_service",
            "resolve_read_session=self._resolve_fin_ops_read_session",
            "record_export_download=self._record_input_invoice_usage_export_download",
            "xlsx_response=self._input_invoice_usage_xlsx_response",
            "app_settings_service=self._app_settings_service",
            "load_json_body=self._load_json_body",
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
            "query_service: InputInvoiceUsageQueryService",
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
            "class InputInvoiceUsageCanonicalQueryService",
            "def rows(",
            "def filter_options(",
            "def relation_details(",
            "def export_page(",
            "def export_rows(",
        ):
            if required not in canonical_query_source:
                violations.append(f"Input usage canonical query service is missing {required}")
        for required in (
            "set transaction isolation level repeatable read read only",
            "app.workbench_pair_relations",
            "relation.status = 'active'",
            "app.invoices",
        ):
            if required not in repository_source:
                violations.append(f"Input usage canonical repository is missing {required}")
        for forbidden in (
            "all_rows_from_sql_read_model=",
            "def _get_input_invoice_usage_all_rows_from_sql_read_model(",
            "def all_rows(",
            "self._query_service.list_rows(",
        ):
            if forbidden in route_source or forbidden in server_source:
                violations.append(f"Input usage read path keeps removed all-rows filter-options path {forbidden}")
        for retired in (
            "input_invoice_usage_read_model_fresh_gate_service.py",
            "input_invoice_usage_read_model_detail_service.py",
        ):
            if (SERVICES_ROOT / retired).exists():
                violations.append(f"Retired input usage service still exists: {retired}")
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
        if "batch_accounting_relation_command_unavailable" not in source:
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
        if "batch_accounting_relation_command_unavailable" not in source:
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

    def test_batch_accounting_membership_has_no_special_metadata_fallback(self) -> None:
        path = SERVICES_ROOT / "batch_accounting_service.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        submitted_source = _function_source(tree, source, "_submitted_payload")
        scope_source = _function_source(tree, source, "_affected_scope_keys_for_relation")
        submit_source = _function_source(tree, source, "submit")
        metadata_literal = submit_source.split("special_metadata = {", 1)[1].split("case_id =", 1)[0]

        violations: list[str] = []
        for retired_key in ("bank_row_id", "oa_row_ids", "invoice_row_ids", "year"):
            marker = f'metadata.get("{retired_key}")'
            if marker in submitted_source or marker in scope_source:
                violations.append(f"BatchAccountingService reads retired membership metadata: {retired_key}")
            if f'"{retired_key}":' in metadata_literal:
                violations.append(f"BatchAccountingService writes retired membership metadata: {retired_key}")
        if "relation_payload = dict(relation)" in submitted_source or '"metadata":' in submitted_source:
            violations.append("BatchAccountingService exposes raw relation metadata in submitted DTO")

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
        service_factory_source = _function_source(tree, source, "_batch_accounting_service")
        repository_path = SERVICES_ROOT / "postgres_repositories" / "batch_accounting.py"
        repository_source = repository_path.read_text(encoding="utf-8")

        violations: list[str] = []
        if "def _repair_batch_accounting_relation_case_ids" in source:
            violations.append("server.py still defines unused batch accounting app-level repair helper")
        if "_batch_accounting_routes().list_payload" not in list_source:
            violations.append("GET /api/batch-accounting no longer delegates reads to BatchAccountingApiRoutes")
        if "_service_factory().build_payload" not in route_list_source:
            violations.append("BatchAccountingApiRoutes no longer delegates reads to BatchAccountingService")
        if "list_snapshot(" not in service_source:
            violations.append("BatchAccountingService no longer reads through its page-owned query repository")
        if "query_repository=" not in service_factory_source:
            violations.append("Application no longer injects the page-owned batch accounting query repository")
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
        for removed_reader in (
            "load_batch_accounting_workbench_payload",
            "load_batch_accounting_submit_workbench_payload",
            "load_batch_accounting_submitted_bank_workbench_payload",
            "get_batch_accounting_by_row_ids",
            "list_batch_accounting_relations_by_year",
            "relation_facade",
            "read_model_status",
            "refresh_enqueued",
        ):
            if removed_reader in service_source or removed_reader in routes_source or removed_reader in service_factory_source:
                violations.append(f"batch accounting runtime keeps removed read-model reader {removed_reader}")
        for required_table in (
            "app.bank_transactions",
            "app.oa_applications",
            "app.oa_attachments",
            "app.invoices",
            "app.workbench_pair_relations",
        ):
            if required_table not in repository_source:
                violations.append(f"batch accounting canonical repository is missing {required_table}")
        if "set transaction isolation level repeatable read read only" not in repository_source:
            violations.append("batch accounting repository no longer uses one explicit read-only repeatable-read snapshot")
        if "read_model." in repository_source or "workbench_generations" in repository_source:
            violations.append("batch accounting page repository reads a removed read-model dependency")
        if "limit %s offset %s" not in repository_source:
            violations.append("batch accounting page repository no longer performs server-side pagination")

        mutation_handlers = (
            (
                "submit",
                submit_source,
                route_submit_source,
                "_batch_accounting_routes().submit",
                "_service_factory().submit",
            ),
            (
                "withdraw",
                withdraw_source,
                route_withdraw_source,
                "_batch_accounting_routes().withdraw",
                "_service_factory().withdraw",
            ),
        )
        for name, handler_source, route_source, route_call, service_call in mutation_handlers:
            if "_batch_accounting_mutation_session" not in handler_source:
                violations.append(f"batch accounting {name} route no longer enforces mutation session")
            if route_call not in handler_source:
                violations.append(f"batch accounting {name} route no longer delegates mutation to BatchAccountingApiRoutes")
            if service_call not in route_source:
                violations.append(f"BatchAccountingApiRoutes {name} no longer delegates mutation to BatchAccountingService")
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
        uow_path = SERVICES_ROOT / "turnover_ledger_write_uow.py"
        uow_source = uow_path.read_text(encoding="utf-8")
        uow_tree = _parse(uow_path)
        uow_class_source = _class_source(uow_tree, uow_source, "TurnoverLedgerWriteUnitOfWork")
        facade_path = SERVICES_ROOT / "turnover_ledger_write_facade.py"
        facade_source = facade_path.read_text(encoding="utf-8")
        facade_tree = _parse(facade_path)
        closure_confirm_source = _function_source(
            facade_tree,
            facade_source,
            "confirm_zero_difference_closure",
        )
        cash_withdraw_source = _function_source(facade_tree, facade_source, "withdraw_cash_closure_case")
        projection_path = SERVICES_ROOT / "turnover_ledger_sql_projection.py"

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
        for required in (
            "def prepare_turnover_manual_closure_write(",
            'getattr(relation_command_service, "prepare_confirm_relation", None)',
            "confirm_preparation = prepare(",
            "preparation=preparation.confirm_preparation",
        ):
            if required not in port_source:
                violations.append(f"TurnoverLedgerWorkbenchPairPort is missing prepared relation write contract {required}")
        for removed in (
            "assert_turnover_manual_closure_write_precondition",
            "_active_relations_for_row_ids_from_command",
        ):
            if removed in port_source:
                violations.append(f"TurnoverLedgerWorkbenchPairPort keeps removed duplicate read path {removed}")
        if ".preview_zero_difference_closure(" not in closure_confirm_source:
            violations.append("modern closure confirm no longer uses the side-effect-free Turnover validation boundary")
        if ".confirm_zero_difference_closure(" in closure_confirm_source:
            violations.append("modern closure confirm restored duplicate Turnover relation persistence")
        if '"turnover_relation":' in closure_confirm_source or '"relation": relation' in closure_confirm_source:
            violations.append("modern closure confirm response restored a non-canonical Turnover relation")
        if projection_path.exists():
            violations.append("retired turnover ledger SQL projection still exists")
        for removed_writer in (
            "TurnoverLedgerDirtyOutboxWriter",
            "TurnoverLedgerLocalDirtyOutboxWriter",
        ):
            if removed_writer in source:
                violations.append(f"turnover write adapters retain removed fan-out writer {removed_writer}")
        if ".enqueue_refresh(" in uow_class_source:
            violations.append("TurnoverLedgerWriteUnitOfWork keeps per-request refresh enqueue")
        for forbidden in (
            "enqueue_read_model_refreshes_in_transaction",
            "refresh_requests",
            "refresh_targets",
        ):
            if forbidden in uow_class_source:
                violations.append(f"TurnoverLedgerWriteUnitOfWork retains write-time fan-out {forbidden}")
        if 'refresh_scope_keys = ["all"]' in cash_withdraw_source:
            violations.append("cash closure withdraw keeps the removed command-only all refresh target")
        for forbidden in (
            "_scoped_month_keys_or_all",
            "_active_cost_statistics_scope_keys",
            "refresh_targets",
        ):
            if forbidden in cash_withdraw_source:
                violations.append(f"cash closure withdraw retains removed refresh target planner {forbidden}")

        self.assertEqual(violations, [])

    def test_bank_flow_rule_batch_runtime_has_no_no_oa_compatibility_path(self) -> None:
        paths = (
            APP_ROOT / "routes_bank_flow_rule_batches.py",
            SERVICES_ROOT / "bank_flow_rule_batch_application_service.py",
        )
        violations: list[str] = []
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for forbidden in ("no_oa", "NO_OA", "免OA", "LEGACY_ERROR_CODES"):
                if forbidden in source:
                    violations.append(f"{_relative(path)} keeps bank-flow legacy marker {forbidden}")

        self.assertEqual(violations, [])

    def test_bank_account_balance_refresh_producer_runtime_is_retired(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)

        violations: list[str] = []
        if _function_source(tree, source, "_enqueue_bank_account_balance_read_model_refresh"):
            violations.append("server.py still owns bank account balance refresh enqueue helper")

        if _function_source(tree, source, "_bank_account_balance_read_model_refresh_producer"):
            violations.append("server.py still assembles retired bank account balance refresh producer")
        for retired_snippet in (
            "BankAccountBalanceReadModelRefreshProducer",
            "bank_account_balance.read_model.refresh",
        ):
            if retired_snippet in source:
                violations.append(f"server.py still references retired bank account balance runtime {retired_snippet}")

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

    def test_workbench_row_detail_route_owner_uses_direct_query_facade_only(self) -> None:
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
            "row_type",
            ".row_detail(",
        ):
            if marker not in row_detail_route_source:
                violations.append(f"WorkbenchRowDetailApiRoutes missing direct-query marker: {marker}")
        for marker in ("_workbench_row_detail_routes().get_result(", "row_type=row_type"):
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
            "expected_read_model_version",
            "active_generation",
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
        for retired_path in (
            SERVICES_ROOT / "existing_etc_batch_link_service.py",
            SERVICES_ROOT / "historical_etc_business_batch_migration_service.py",
            SOURCE_ROOT / "fin_ops_platform/tools/link_existing_etc_batches.py",
            SOURCE_ROOT / "fin_ops_platform/tools/migrate_historical_etc_business_batches.py",
        ):
            if retired_path.exists():
                violations.append(f"retired ETC relation path resurfaced: {_relative(retired_path)}")
        historical_script = (REPO_ROOT / "scripts/repair_historical_etc_batches.py").read_text(encoding="utf-8")
        if "create_active_relation(" in historical_script or "--apply" in historical_script:
            violations.append("historical ETC script bypasses HistoricalEtcRepairService")

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

    def test_workbench_direct_read_route_owner_stays_local(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        routes_path = APP_ROOT / "routes_workbench.py"
        routes_source = routes_path.read_text(encoding="utf-8")
        routes_tree = _parse(routes_path)
        read_route_source = _class_source(routes_tree, routes_source, "WorkbenchReadApiRoutes")
        groups_handler_source = _function_source(server_tree, server_source, "_handle_api_workbench_groups")
        violations: list[str] = []

        for marker in (
            "def initial(",
            "def groups(",
            "def filter_options(",
            "_normalize_search_query",
            "WORKBENCH_SEARCH_QUERY_MAX_LENGTH",
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
        if "_handle_api_workbench_refresh_status" in server_source:
            violations.append("server.py still defines the retired Workbench refresh-status handler")
        if "def refresh_status(" in read_route_source:
            violations.append("WorkbenchReadApiRoutes still exposes the retired refresh-status endpoint")
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
        self.assertEqual(violations, [])

    def test_retired_workbench_sse_runtime_stays_deleted(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        routes_source = (APP_ROOT / "routes_workbench.py").read_text(encoding="utf-8")

        self.assertFalse((SERVICES_ROOT / "workbench_events_active_stream_registry.py").exists())
        self.assertNotIn("WorkbenchEventsApiRoutes", routes_source)
        self.assertNotIn("/api/workbench/events", server_source)
        self.assertNotIn("text/event-stream", server_source)

    def test_workbench_refresh_status_contract_stays_retired(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        routes_source = (APP_ROOT / "routes_workbench.py").read_text(encoding="utf-8")

        self.assertFalse((SERVICES_ROOT / "workbench_refresh_status_payload.py").exists())
        for marker in (
            "WorkbenchRefreshStatusPayloadNormalizer",
            "_workbench_refresh_status_payload_normalizer",
            "_handle_api_workbench_refresh_status",
            "/api/workbench/refresh-status",
        ):
            self.assertNotIn(marker, server_source)
            self.assertNotIn(marker, routes_source)

    def test_retired_workbench_sse_status_provider_stays_deleted(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")

        self.assertFalse((SERVICES_ROOT / "workbench_refresh_status_payload_provider.py").exists())
        self.assertNotIn("WorkbenchRefreshStatusPayloadProvider", server_source)
        self.assertNotIn("_workbench_refresh_status_payload_provider", server_source)

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
        retired_repository_path = SERVICES_ROOT / "postgres_repositories" / "read_models.py"
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
        self.assertFalse(retired_repository_path.exists())

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

    def test_workbench_page_refresh_and_cache_runtime_stays_deleted(self) -> None:
        worker_source = (APP_ROOT / "worker.py").read_text(encoding="utf-8")
        self.assertFalse((SERVICES_ROOT / "workbench_read_model_refresh.py").exists())
        self.assertFalse((SERVICES_ROOT / "workbench_groups_page_cache.py").exists())

        for forbidden in (
            "WorkbenchGroupsPageCacheWarmer",
            "workbench_groups_sync_cache_warmup_enabled_from_env",
            "FIN_OPS_WORKBENCH_GROUPS_SYNC_CACHE_WARMUP_ENABLED",
            "post_refresh_warmer",
            'payload["cache_warmup"]',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, worker_source)

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
            "def snapshot(",
        ):
            if snippet not in port_source:
                violations.append(f"settings data reset pair snapshot port missing {snippet}")
        for forbidden in (
            "def save_pair_relations(",
            "save_pair_relation_snapshot",
        ):
            if forbidden in port_source:
                violations.append(f"settings data reset read port still owns write behavior {forbidden}")
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
        for snippet in (
            "self._state_store.reset_bank_transaction_data(",
            "self._state_store.reset_invoice_data(",
            "self._state_store.reset_oa_workbench_data(",
        ):
            if snippet not in service_class_source:
                violations.append(f"SettingsDataResetService reset no longer uses explicit transaction port {snippet}")
        for forbidden in (
            "_persist_import_reset_state(",
            "self._state_store.save(",
            "self._state_store.save_workbench_overrides(",
            "self._state_store.save_workbench_pair_relations(",
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
            "self._request_data_reset(",
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
        request_service_source = (SERVICES_ROOT / "settings_data_reset_request.py").read_text(encoding="utf-8")
        combined_source = f"{server_source}\n{routes_source}\n{request_service_source}"

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
        if "self._background_jobs.build_job(" not in request_service_source:
            violations.append("settings data reset request service no longer uses BackgroundJobService")
        if "self._request_data_reset(" not in routes_source:
            violations.append("settings route owner bypasses the atomic data reset request boundary")

        self.assertEqual(violations, [])

    def test_bank_details_relation_tags_read_only_canonical_relations(self) -> None:
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

        canonical_method = _function_source(tree, source, "_relation_tags_from_canonical_relations")
        if "active_relations_for_row_ids" not in canonical_method:
            violations.append(f"{_relative(path)} does not read canonical relations by requested row ids")

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
        allowed_path = (
            "backend/src/fin_ops_platform/services/"
            "oa_attachment_invoice_promotion_service.py"
        )

        for path in _python_files(APP_ROOT, SERVICES_ROOT, TOOLS_ROOT):
            rel_path = _relative(path)
            source = path.read_text(encoding="utf-8")
            if "allow_create=" not in source:
                continue
            if rel_path != allowed_path:
                violations.append(f"{rel_path} passes allow_create to OA attachment invoice upsert")

        service_path = SERVICES_ROOT / "oa_attachment_invoice_promotion_service.py"
        service_source = service_path.read_text(encoding="utf-8")
        promote_method = _function_source(_parse(service_path), service_source, "promote_candidates")
        if "InvoiceAttachmentRecognitionService" not in promote_method:
            violations.append("OA attachment promotion service does not use InvoiceAttachmentRecognitionService")
        if "allow_create=action == CREATE_INVOICE_AND_LINK" not in promote_method:
            violations.append("OA attachment promotion service does not gate create on CREATE_INVOICE_AND_LINK")

        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        for legacy_name in (
            "_handle_oa_attachment_invoice_cache_updated",
            "_promote_oa_attachment_invoices_to_canonical",
            "_formal_oa_attachment_invoice_candidates",
        ):
            if legacy_name in server_source:
                violations.append(f"server.py retains legacy OA attachment promotion path {legacy_name}")

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
            "backend/src/fin_ops_platform/services/postgres_repositories/settings_data_reset.py",
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

    def test_legacy_workbench_candidate_state_is_absent_from_runtime(self) -> None:
        legacy_terms = {
            "automatic_decision",
            "candidate_relation_distribution",
            "candidate_snapshot_version",
            "workbench_candidate",
            "workbench_reconciliation_decision",
        }
        violations: list[str] = []

        for path in _python_files(APP_ROOT, SERVICES_ROOT, TOOLS_ROOT):
            relative_path = _relative(path)
            source = path.read_text(encoding="utf-8")
            for term in legacy_terms:
                count = source.count(term)
                if not count:
                    continue
                violations.append(f"{relative_path} contains legacy Workbench state term {term}")
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

    def test_relation_preview_selection_is_preview_only_and_formal_commands_stay_canonical(self) -> None:
        from fin_ops_platform.services.workbench_write_facade import WorkbenchWriteFacade

        preview_sources = "\n".join(
            inspect.getsource(getattr(WorkbenchWriteFacade, method_name))
            for method_name in ("preview_confirm_link", "preview_withdraw_link")
        )
        formal_sources = "\n".join(
            inspect.getsource(getattr(WorkbenchWriteFacade, method_name))
            for method_name in ("confirm_link", "withdraw_link")
        )

        self.assertIn("relation_preview_selection", preview_sources)
        self.assertNotIn("relation_preview_selection", formal_sources)
        preview_projection_source = inspect.getsource(
            WorkbenchWriteFacade._withdraw_relation_preview_payload
        )
        forbidden_preview_scans = {
            "_expand_confirm_link_row_ids_for_existing_context",
            "_resolve_rows_for_amount_check",
            "_resolve_live_rows_direct",
            "_withdraw_rows_and_after_relations",
        }
        violations = [
            helper_name
            for helper_name in sorted(forbidden_preview_scans)
            if helper_name in preview_sources or helper_name in preview_projection_source
        ]
        self.assertEqual(violations, [])

    def test_workbench_write_facade_does_not_restore_retired_exception_write_entrypoints(self) -> None:
        from fin_ops_platform.services.workbench_write_facade import WorkbenchWriteFacade

        retired_methods = {
            "apply_exception",
            "mark_exception",
            "cancel_exception",
            "ignore_row",
            "unignore_row",
        }
        restored_methods = [
            method_name
            for method_name in sorted(retired_methods)
            if callable(getattr(WorkbenchWriteFacade, method_name, None))
        ]

        self.assertEqual(restored_methods, [])

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
            server_source.index("    def _handle_api_operations_page_audit")
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
            "audit_page_canonical_data.py",
        ):
            path = TOOLS_ROOT / file_name
            source = path.read_text(encoding="utf-8")
            with self.subTest(file_name=file_name):
                self.assertNotIn("/* check:", source)
                self.assertNotIn("_PREDICATE", source)
                self.assertEqual(_attribute_calls(_parse(path), {"fetch_one", "fetch_all", "execute"}), [])

        repository_source = (
            SERVICES_ROOT / "postgres_repositories" / "page_business_audit.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"input_invoice_usage": PageAuditContract(', repository_source)
        self.assertIn('"output_invoice_collection": PageAuditContract(', repository_source)

    def test_raw_postgres_sql_in_services_is_classified_by_platform_boundary(self) -> None:
        allowed_exact_paths = {
            "backend/src/fin_ops_platform/services/bank_account_balance_projection.py",
            "backend/src/fin_ops_platform/services/cost_statistics_canonical_repository.py",
            "backend/src/fin_ops_platform/services/file_object_migration.py",
            "backend/src/fin_ops_platform/services/import_job_queue.py",
            "backend/src/fin_ops_platform/services/oa_payment_status_service.py",
            "backend/src/fin_ops_platform/services/oa_role_sync_service.py",
            "backend/src/fin_ops_platform/services/operations_dashboard.py",
            "backend/src/fin_ops_platform/services/postgres_connection.py",
            "backend/src/fin_ops_platform/services/postgres_state_store.py",
            "backend/src/fin_ops_platform/services/runtime_monitoring.py",
            "backend/src/fin_ops_platform/services/runtime_queue.py",
            "backend/src/fin_ops_platform/services/workbench_canonical_rows.py",
            "backend/src/fin_ops_platform/services/bank_details_canonical_query.py",
            "backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py",
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

    def test_etc_invoice_refresh_does_not_enqueue_page_read_models(self) -> None:
        api_source = inspect.getsource(server_module.Application._refresh_after_etc_invoice_link)
        self.assertNotIn("search", api_source)
        self.assertNotIn("_execute_explicit_maintenance_lifecycle", api_source)
        self.assertNotIn("enqueue", api_source)

    def test_business_pages_do_not_restore_deleted_frontend_domain_events(self) -> None:
        forbidden_tokens = (
            "FINANCE_DOMAIN_EVENTS",
            "useActiveFinanceDomainEvent",
            "domainEvents",
            "finops:bank-transaction-tags-updated",
            "BroadcastChannel",
        )
        for path in (WEB_SRC_ROOT / "pages").glob("*.tsx"):
            with self.subTest(path=_relative(path)):
                source = path.read_text(encoding="utf-8")
                for token in forbidden_tokens:
                    self.assertNotIn(token, source)

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
