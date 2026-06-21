from __future__ import annotations

import ast
from decimal import Decimal
import inspect
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.app import server as server_module
from fin_ops_platform.services.etc_existing_invoice_link_service import EtcExistingInvoiceLinkService
from fin_ops_platform.services.etc_service import EtcImportItem, EtcImportResult
from fin_ops_platform.services.runtime_worker_handlers import _link_etc_import_result_to_existing_invoices
from fin_ops_platform.services.runtime_bootstrap import LegacySnapshotBootstrap


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "backend" / "src" / "fin_ops_platform"
APP_ROOT = SOURCE_ROOT / "app"
SERVICES_ROOT = SOURCE_ROOT / "services"
TOOLS_ROOT = SOURCE_ROOT / "tools"
SCRIPTS_ROOT = REPO_ROOT / "scripts"


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
                "BatchAccountingService.withdraw",
                "BatchAccountingService._withdraw_unlocked",
            },
            "backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py": {
                "NoOaBankBatchApplicationService._validate_internal_transfer_selection",
                "NoOaBankBatchApplicationService._restore_snapshots",
                "NoOaBankBatchApplicationService.pair_relation_snapshot_by_case_id",
            },
            "backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py": {
                "NoOaBankBatchService._repair_submitted_no_oa_relation_consistency",
                "NoOaBankBatchService._has_active_no_oa_relation",
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

    def test_downstream_relation_query_services_do_not_accept_pair_relation_service(self) -> None:
        downstream_query_service_paths = {
            SERVICES_ROOT / "input_invoice_usage_service.py",
            SERVICES_ROOT / "oa_pending_payment_service.py",
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

    def test_etc_summary_relation_delete_uses_workbench_relation_command_boundary(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        cancel_method = _function_source(tree, source, "_cancel_etc_summary_relations_for_batch")
        delete_method = _function_source(tree, source, "_handle_api_etc_business_batch_delete")
        task_delete_method = _function_source(tree, source, "_delete_reconciliation_task_business_batch_sources")

        violations: list[str] = []
        if "cancel_relations_for_row_ids" not in cancel_method:
            violations.append("_cancel_etc_summary_relations_for_batch does not delegate row cancellation to command service")
        if "cancel_active_relations_for_row_ids" in cancel_method:
            violations.append("_cancel_etc_summary_relations_for_batch directly mutates pair relation service")
        if "_workbench_pair_relation_service" in cancel_method:
            violations.append("_cancel_etc_summary_relations_for_batch reaches app pair relation service directly")
        if "_assert_etc_summary_relation_write_precondition_for_batch(batch)" not in delete_method:
            violations.append("ETC business batch API delete lacks relation freshness preflight before local mutation")
        if "_assert_etc_summary_relation_write_precondition_for_batch(business_batch)" not in task_delete_method:
            violations.append("ETC reconciliation task delete lacks relation freshness preflight before local mutation")

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

        self.assertEqual(violations, [])

    def test_batch_accounting_submit_has_no_direct_pair_write_fallback(self) -> None:
        path = SERVICES_ROOT / "batch_accounting_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        submit_source = _function_source(tree, source, "_submit_unlocked")

        violations: list[str] = []
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

    def test_batch_accounting_repair_has_no_direct_pair_write_fallback(self) -> None:
        path = SERVICES_ROOT / "batch_accounting_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        repair_source = _function_source(tree, source, "repair_legacy_case_id_collisions")

        violations: list[str] = []
        if "confirm_relation" not in repair_source:
            violations.append("BatchAccountingService.repair does not delegate relation repair to command service")
        if "batch_accounting_relation_command_unavailable" not in repair_source:
            violations.append("BatchAccountingService.repair does not fail fast when relation command service is unavailable")
        for forbidden in (
            "_pair_relation_service.create_active_relation",
            "_pair_relation_service.record_history",
        ):
            if forbidden in repair_source:
                violations.append(f"BatchAccountingService.repair keeps direct pair write fallback {forbidden}")

        self.assertEqual(violations, [])

    def test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback(self) -> None:
        path = SERVICES_ROOT / "turnover_ledger_write_adapters.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        port_source = _class_source(tree, source, "TurnoverLedgerWorkbenchPairPort")

        violations: list[str] = []
        for forbidden in (
            "replace_with_confirmed_relation",
            "cancel_relation(case_id)",
            "_persist_pair_relations(",
        ):
            if forbidden in port_source:
                violations.append(f"TurnoverLedgerWorkbenchPairPort keeps direct pair write fallback {forbidden}")
        if "workbench_relation_command_unavailable" not in port_source:
            violations.append("TurnoverLedgerWorkbenchPairPort does not fail fast when relation command service is unavailable")

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

    def test_server_active_relation_repairs_use_relation_command_boundary(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        checked_sources = {
            method_name: _function_source(tree, source, method_name)
            for method_name in (
                "_sync_oa_invoice_offset_auto_pair_relations",
                "_repair_active_relations_with_oa_attachment_context",
            )
        }

        violations: list[str] = []
        for method_name, method_source in checked_sources.items():
            if "confirm_relation" not in method_source:
                violations.append(f"{method_name} does not delegate relation creation/repair to command service")
            for forbidden in (
                "_workbench_pair_relation_service.create_active_relation",
                "_workbench_pair_relation_service.cancel_relation",
                "_workbench_pair_relation_service.record_history",
            ):
                if forbidden in method_source:
                    violations.append(f"{method_name} keeps direct pair relation write {forbidden}")

        self.assertEqual(violations, [])

    def test_no_oa_read_model_refresh_does_not_run_relation_repairs(self) -> None:
        path = SERVICES_ROOT / "no_oa_bank_batch_read_model_refresh.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        handler_source = _function_source(tree, source, "handle_runtime_event")

        violations: list[str] = []
        if "apply_relation_repairs=False" not in handler_source:
            violations.append("No-OA read model refresh must call refresh_batches with apply_relation_repairs=False")
        for forbidden in (
            "save_workbench_pair_relations",
            "save_no_oa_bank_batch_mutation",
            "create_active_relation",
            "cancel_relation",
        ):
            if forbidden in handler_source:
                violations.append(f"No-OA read model refresh keeps relation write side effect {forbidden}")

        self.assertEqual(violations, [])

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

    def test_bank_details_relation_tags_only_read_relation_distribution_facade(self) -> None:
        path = SERVICES_ROOT / "bank_details_relation_tag_projection_service.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        violations: list[str] = []

        forbidden_snippets = {
            "_build_raw_workbench_payload",
            "WorkbenchCandidateMatchService",
            "workbench_candidate_match_service",
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
            (SERVICES_ROOT / "runtime_worker_handlers.py", "_link_etc_invoices_to_existing_invoices"),
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
            "backend/src/fin_ops_platform/app/oa_attachment_audit.py",
            "backend/src/fin_ops_platform/app/server.py",
            "backend/src/fin_ops_platform/app/worker.py",
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

    def test_raw_postgres_sql_in_services_is_classified_by_platform_boundary(self) -> None:
        allowed_exact_paths = {
            "backend/src/fin_ops_platform/services/bank_account_balance_projection.py",
            "backend/src/fin_ops_platform/services/cutover_preflight.py",
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
    def test_existing_invoice_link_service_uses_import_items_to_load_existing_invoices(self) -> None:
        upserted: list[object] = []

        class ImportService:
            def upsert_etc_invoice(self, etc_invoice: object) -> object:
                upserted.append(etc_invoice)
                return SimpleNamespace(invoice_date=getattr(etc_invoice, "issue_date", None))

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
                return linked_invoice

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
                return SimpleNamespace(invoice_date=getattr(etc_invoice, "issue_date", None))

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
        link = _link_etc_import_result_to_existing_invoices(ImportService(), etc_service)

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

    def test_link_etc_import_result_tolerates_missing_canonical_invoice_without_creation(self) -> None:
        upserted: list[object] = []

        class ImportService:
            def upsert_etc_invoice(self, etc_invoice: object) -> None:
                upserted.append(etc_invoice)
                return None

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

        link = _link_etc_import_result_to_existing_invoices(ImportService(), EtcService())

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
        self.assertEqual(months, ["2026-04"])

    def test_runtime_etc_import_link_never_calls_canonical_invoice_create_api(self) -> None:
        forbidden_calls: list[str] = []

        class ImportService:
            def upsert_etc_invoice(self, etc_invoice: object) -> None:
                return None

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

        link = _link_etc_import_result_to_existing_invoices(ImportService(), EtcService())

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

        self.assertEqual(months, ["2026-04"])
        self.assertEqual(forbidden_calls, [])


if __name__ == "__main__":
    unittest.main()
