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
            "backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py": {
                "NoOaPairRelationSnapshotPort.restore",
            },
            "backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py": {
                "NoOaRelationRepairReadPort.active_relation_by_case_id",
                "NoOaRelationRepairReadPort.active_relations_for_row_ids",
            },
            "backend/src/fin_ops_platform/services/batch_accounting_service.py": {
                "BatchAccountingService._submit_unlocked",
                "BatchAccountingService.repair_legacy_case_id_collisions",
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
            "routes_legacy_workbench_actions.py": {
                "module": "fin_ops_platform.app.routes_legacy_workbench_actions",
                "class": "LegacyWorkbenchActionRoutes",
                "server_markers": ("_legacy_workbench_action_routes = LegacyWorkbenchActionRoutes(", "_handle_legacy_workbench_action("),
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
                "server_markers": ("def _output_invoice_collection_routes", "_output_invoice_collection_routes()."),
            },
            "routes_pending_invoices.py": {
                "module": "fin_ops_platform.app.routes_pending_invoices",
                "class": "PendingInvoiceApiRoutes",
                "server_markers": ("def _pending_invoice_routes", "_pending_invoice_routes()."),
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
                "class": "WorkbenchApiRoutes",
                "server_markers": ("_workbench_api_routes = WorkbenchApiRoutes(", "_workbench_api_routes."),
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
        if "_workbench_write_freshness_guard()" not in handler_source:
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

    def test_legacy_workbench_actions_stay_quarantined_in_route_owner(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        route_path = APP_ROOT / "routes_legacy_workbench_actions.py"
        route_source = route_path.read_text(encoding="utf-8")
        route_tree = _parse(route_path)
        violations: list[str] = []

        if not _class_source(route_tree, route_source, "LegacyWorkbenchActionRoutes"):
            violations.append("legacy Workbench action route owner is missing")
        if not _imports_name_from_module(
            server_tree,
            module="fin_ops_platform.app.routes_legacy_workbench_actions",
            name="LegacyWorkbenchActionRoutes",
        ):
            violations.append("server.py does not import LegacyWorkbenchActionRoutes")
        for marker in (
            "self._legacy_workbench_action_routes = LegacyWorkbenchActionRoutes(",
            'return self._handle_legacy_workbench_action("confirm", body)',
            'return self._handle_legacy_workbench_action("difference", body)',
            'return self._handle_legacy_workbench_action("exception", body)',
            'return self._handle_legacy_workbench_action("offline", body)',
            'return self._handle_legacy_workbench_action("offset", body)',
        ):
            if marker not in server_source:
                violations.append(f"server.py legacy route quarantine marker missing: {marker}")

        for old_handler in (
            "_handle_workbench_confirm",
            "_handle_workbench_difference",
            "_handle_workbench_exception",
            "_handle_workbench_offline",
            "_handle_workbench_offset",
            "_handle_legacy_workbench_exception_via_application",
        ):
            if _function_source(server_tree, server_source, old_handler):
                violations.append(f"server.py still owns legacy Workbench action handler {old_handler}")

        for marker in (
            "ManualReconciliationService",
            "LedgerReminderService",
            "confirm_manual_reconciliation(",
            "confirm_difference_reconciliation(",
            "record_exception(",
            "record_offline_reconciliation(",
            "record_offset_reconciliation(",
            "sync_from_case(",
        ):
            if marker not in route_source:
                violations.append(f"legacy route owner is missing compat behavior marker {marker}")
        for forbidden in (
            "WorkbenchWriteFacade",
            "WorkbenchRelationCommandService",
            "ReadModelRefreshGateway",
            "job.outbox_events",
            "job.read_model_dirty_scopes",
        ):
            if forbidden in route_source:
                violations.append(f"legacy route owner bypasses quarantine via {forbidden}")

        for handler_name, facade_method in {
            "_handle_live_workbench_confirm_link": "confirm_link",
            "_handle_live_workbench_cancel_link": "cancel_link",
            "_handle_live_workbench_withdraw_link": "withdraw_link",
            "_handle_live_workbench_mark_exception": "mark_exception",
            "_handle_live_workbench_update_bank_exception": "update_bank_exception",
            "_handle_live_workbench_oa_bank_exception": "oa_bank_exception",
            "_handle_live_workbench_confirm_personal_advance_repayment": "confirm_personal_advance_repayment",
            "_handle_live_workbench_cancel_exception": "cancel_exception",
            "_handle_workbench_ignore_row_payload": "ignore_row",
            "_handle_workbench_unignore_row_payload": "unignore_row",
        }.items():
            handler_source = _function_source(server_tree, server_source, handler_name)
            if f"self._workbench_write_facade().{facade_method}" not in handler_source:
                violations.append(f"{handler_name} no longer delegates to WorkbenchWriteFacade.{facade_method}")

        self.assertEqual(violations, [])

    def test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        routes_source = (APP_ROOT / "routes_bank_details.py").read_text(encoding="utf-8")
        service_source = (SERVICES_ROOT / "bank_details_application_service.py").read_text(encoding="utf-8")
        app_settings_source = (SERVICES_ROOT / "app_settings_service.py").read_text(encoding="utf-8")

        handler_delegates = {
            "_handle_api_bank_details_auto_tag_rules_update": "update_auto_tag_rules",
            "_handle_api_bank_details_auto_tag_rules_file_replacement": "replace_auto_tag_rules_from_file_source",
            "_handle_api_bank_details_auto_tag_rules_reapply": "reapply_auto_tag_rules",
            "_handle_api_bank_detail_category_confirmation": "confirm_category",
            "_handle_api_bank_detail_category_confirmation_delete": "revoke_category_confirmation",
            "_handle_api_bank_detail_category_assignment": "assign_category",
            "_handle_api_bank_detail_category_assignment_delete": "clear_category_assignment",
        }
        violations: list[str] = []

        for forbidden in (
            "def _finalize_bank_auto_tag_rules_update",
            "def _bank_detail_refresh_scope_keys_from_auto_tag_rules_payload",
        ):
            if forbidden in server_source:
                violations.append(f"server.py still owns legacy bank auto-tag write helper {forbidden}")

        for handler_name, route_method in handler_delegates.items():
            handler_source = _function_source(server_tree, server_source, handler_name)
            if f"_bank_details_routes().{route_method}" not in handler_source:
                violations.append(f"{handler_name} does not delegate to BankDetailsApiRoutes.{route_method}")
            for forbidden in (
                "update_bank_auto_tag_rules(",
                "replace_bank_auto_tag_rules_from_file_source(",
                "confirm_auto_category(",
                "assign_manual_category(",
                "clear_manual_category(",
                "_execute_derived_data_lifecycle_event(",
                "_enqueue_bank_detail_read_model_refreshes(",
                "_enqueue_turnover_ledger_read_model_refreshes(",
            ):
                if forbidden in handler_source:
                    violations.append(f"{handler_name} keeps application/write-side logic {forbidden}")

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

        if "bank_transaction_tags_write_forbidden" not in server_source:
            violations.append("workbench settings route no longer blocks legacy bank_transaction_tags writes")
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

    def test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        service_source = (SERVICES_ROOT / "bank_details_application_service.py").read_text(encoding="utf-8")
        service_tree = _parse(SERVICES_ROOT / "bank_details_application_service.py")
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
            "def clear_best_effort(",
            "clear_turnover_ledger_rows",
        ):
            if snippet not in turnover_producer_class:
                violations.append(f"turnover ledger refresh producer is missing boundary behavior {snippet}")
        direct_job_writes = _sql_write_table_references(turnover_producer_class)
        if direct_job_writes:
            violations.append(f"turnover ledger refresh producer writes job queue tables directly: {direct_job_writes}")

        factory_source = _function_source(server_tree, server_source, "_bank_details_application_service")
        if _function_source(server_tree, server_source, "_enqueue_turnover_ledger_read_model_refreshes"):
            violations.append("server.py still owns removed turnover ledger refresh enqueue helper")
        if _function_source(server_tree, server_source, "_clear_turnover_ledger_read_model_best_effort"):
            violations.append("server.py still owns removed turnover ledger read model clear helper")
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
        if '"cost_statistics_read_model": lambda domain_plan: self._cost_statistics_derived_lifecycle_executor().execute' not in server_source:
            violations.append("derived lifecycle registry does not use the explicit cost statistics executor")
        if "class CostStatisticsDerivedLifecycleExecutor" not in executor_source:
            violations.append("cost statistics lifecycle executor service is missing")
        for snippet in (
            "def execute(",
            'reason = str(domain_plan.get("reason") or "derived_lifecycle_cost_statistics")',
            'persist_empty = reason != "pending_invoice_rules_changed"',
            "runtime_service: CostStatisticsRuntimeService",
            '"deleted_counts": {"cost_statistics_read_models": len(deleted_scope_keys)}',
            '"enqueued_jobs": enqueued_jobs',
            '"cost_statistics.read_model.refresh"',
            '"cost_statistics_cache_warmup"',
        ):
            if snippet not in executor_source:
                violations.append(f"cost statistics lifecycle executor is missing behavior {snippet}")

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
            SERVICES_ROOT / "pending_invoice_service.py",
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
        }
        present = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in removed_handlers
        ]
        v2_route = _function_source(tree, source, "_route_api_etc_business_batch_v2")
        list_route = _function_source(tree, source, "_handle_api_etc_business_batches_route")

        violations: list[str] = []
        if present:
            violations.append(f"server.py keeps removed ETC business batch legacy handlers: {sorted(present)}")
        for required_delegate in (
            "routes.source_files(",
            "routes.preview_import(",
            "routes.confirm_import(",
            "routes.create_oa_draft(",
            "routes.manual_oa_status(",
        ):
            if required_delegate not in v2_route:
                violations.append(f"_route_api_etc_business_batch_v2 no longer delegates {required_delegate} to EtcBusinessBatchApiRoutes")
        for required_delegate in (
            "_etc_business_routes().list_batches(",
            "_etc_business_routes().create_batch(",
        ):
            if required_delegate not in list_route:
                violations.append(f"_handle_api_etc_business_batches_route no longer delegates {required_delegate} to EtcBusinessBatchApiRoutes")
        if "EtcBusinessBatchActor" in source:
            violations.append("server.py reintroduced direct EtcBusinessBatchActor construction instead of route-owned actor mapping")

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

        mutation_handlers = (
            ("submit", submit_source, route_submit_source, "_batch_accounting_routes().submit", "_service_factory().submit"),
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

        violations: list[str] = []
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

        self.assertEqual(violations, [])

    def test_workbench_matching_uses_relation_read_port_not_pair_service(self) -> None:
        checks = {
            "backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py": (
                "WorkbenchMatchingOrchestrator",
                "WorkbenchMatchingRelationReadPort",
            ),
            "backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py": (
                "WorkbenchReconciliationEngine",
                "WorkbenchMatchingRelationReadPort",
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

        self.assertEqual(violations, [])

    def test_server_workbench_payload_relation_reads_use_payload_read_port(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        port_source = (SERVICES_ROOT / "workbench_payload_relation_read_port.py").read_text(encoding="utf-8")

        checked_sources = {
            method_name: _function_source(tree, source, method_name)
            for method_name in (
                "_apply_pair_relations_to_payload",
                "_supplement_missing_active_pair_relation_rows",
                "_relation_for_group",
                "_resolve_live_rows_direct",
            )
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
        for required in ("get_active_relation_by_row_id", "list_active_relations"):
            if required not in port_source:
                violations.append(f"WorkbenchPayloadRelationReadPort is missing {required}")

        self.assertEqual(violations, [])

    def test_server_source_versions_use_relation_source_version_provider(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        provider_source = (SERVICES_ROOT / "workbench_relation_source_version_provider.py").read_text(encoding="utf-8")
        checked_sources = {
            method_name: _function_source(tree, source, method_name)
            for method_name in (
                "_no_oa_bank_batch_source_versions",
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

    def test_server_oa_invoice_offset_sync_uses_relation_read_port(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_sync_oa_invoice_offset_auto_pair_relations")
        port_source = (SERVICES_ROOT / "workbench_oa_invoice_offset_relation_read_port.py").read_text(encoding="utf-8")

        violations: list[str] = []
        if "class WorkbenchOaInvoiceOffsetRelationReadPort" not in port_source:
            violations.append("Workbench OA invoice offset relation read port is missing")
        if "def active_relations_for_mode" not in port_source:
            violations.append("WorkbenchOaInvoiceOffsetRelationReadPort does not expose active_relations_for_mode")
        if "_workbench_pair_relation_service.list_active_relations" in method_source:
            violations.append("_sync_oa_invoice_offset_auto_pair_relations still reads broad pair service directly")
        if "_workbench_oa_invoice_offset_relation_read_port()" not in method_source:
            violations.append("_sync_oa_invoice_offset_auto_pair_relations does not use OA invoice offset relation read port")
        if "active_relations_for_mode(OA_INVOICE_OFFSET_AUTO_MATCH_MODE)" not in method_source:
            violations.append("_sync_oa_invoice_offset_auto_pair_relations does not constrain reads to OA invoice offset mode")

        self.assertEqual(violations, [])

    def test_server_oa_attachment_repair_uses_relation_read_port(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_repair_active_relations_with_oa_attachment_context")
        port_source = (SERVICES_ROOT / "workbench_oa_attachment_repair_relation_read_port.py").read_text(encoding="utf-8")

        violations: list[str] = []
        if "class WorkbenchOaAttachmentRepairRelationReadPort" not in port_source:
            violations.append("Workbench OA attachment repair relation read port is missing")
        if "def list_active_relations" not in port_source:
            violations.append("WorkbenchOaAttachmentRepairRelationReadPort does not expose list_active_relations")
        if "_workbench_pair_relation_service.list_active_relations" in method_source:
            violations.append("_repair_active_relations_with_oa_attachment_context still reads broad pair service directly")
        if "_workbench_oa_attachment_repair_relation_read_port()" not in method_source:
            violations.append("_repair_active_relations_with_oa_attachment_context does not use OA attachment repair relation read port")
        if "replace_existing=True" not in method_source:
            violations.append("_repair_active_relations_with_oa_attachment_context no longer preserves replace-existing repair")
        if "before_relations=[before_relation]" not in method_source:
            violations.append("_repair_active_relations_with_oa_attachment_context no longer preserves before relation payload")

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

    def test_server_auto_pair_conflict_uses_relation_read_port(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_auto_pair_conflicts_with_manual_relation")
        port_source = (SERVICES_ROOT / "workbench_auto_pair_conflict_relation_read_port.py").read_text(encoding="utf-8")

        violations: list[str] = []
        if "class WorkbenchAutoPairConflictRelationReadPort" not in port_source:
            violations.append("Workbench auto-pair conflict relation read port is missing")
        if "def get_active_relation_by_row_id" not in port_source:
            violations.append("WorkbenchAutoPairConflictRelationReadPort does not expose get_active_relation_by_row_id")
        if "_workbench_pair_relation_service.get_active_relation_by_row_id" in method_source:
            violations.append("_auto_pair_conflicts_with_manual_relation still reads broad pair service directly")
        if "_workbench_auto_pair_conflict_relation_read_port()" not in method_source:
            violations.append("_auto_pair_conflicts_with_manual_relation does not use auto-pair conflict relation read port")
        if "SYSTEM_AUTO_PAIR_RELATION_MODES" not in method_source:
            violations.append("_auto_pair_conflicts_with_manual_relation no longer preserves system auto-pair mode allowlist")
        if "return True" not in method_source or "return False" not in method_source:
            violations.append("_auto_pair_conflicts_with_manual_relation no longer returns boolean conflict result")

        self.assertEqual(violations, [])

    def test_server_retained_oa_supplemental_uses_relation_read_port(self) -> None:
        path = APP_ROOT / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        method_source = _function_source(tree, source, "_supplemental_retained_oa_row_ids")
        port_source = (SERVICES_ROOT / "workbench_retained_oa_supplemental_relation_read_port.py").read_text(encoding="utf-8")

        violations: list[str] = []
        if "class WorkbenchRetainedOaSupplementalRelationReadPort" not in port_source:
            violations.append("Workbench retained-OA supplemental relation read port is missing")
        if "def list_active_relations" not in port_source:
            violations.append("WorkbenchRetainedOaSupplementalRelationReadPort does not expose list_active_relations")
        if "_workbench_pair_relation_service.list_active_relations" in method_source:
            violations.append("_supplemental_retained_oa_row_ids still reads broad pair service directly")
        if "_workbench_retained_oa_supplemental_relation_read_port()" not in method_source:
            violations.append("_supplemental_retained_oa_row_ids does not use retained-OA supplemental relation read port")
        for required in (
            "_manual_retained_oa_row_ids()",
            "_resolve_live_rows_direct(bank_row_ids, month_hint=\"all\")",
            "_row_is_on_or_after(row, cutoff_date, row_type=\"bank\")",
            "return sorted(retained_row_ids)",
        ):
            if required not in method_source:
                violations.append(f"_supplemental_retained_oa_row_ids no longer preserves {required}")

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

    def test_batch_accounting_pair_relation_restore_uses_explicit_service_boundary(self) -> None:
        server_path = APP_ROOT / "server.py"
        server_source = server_path.read_text(encoding="utf-8")
        server_tree = _parse(server_path)
        wrapper_source = _function_source(server_tree, server_source, "_restore_batch_accounting_pair_relation_snapshot")
        factory_source = _function_source(
            server_tree,
            server_source,
            "_batch_accounting_pair_relation_rollback_restore_service",
        )
        violations: list[str] = []

        if "_batch_accounting_pair_relation_rollback_restore_service().restore(" not in wrapper_source:
            violations.append("batch accounting pair relation restore wrapper does not delegate to service.restore")
        if "changed_case_ids=[]" not in wrapper_source:
            violations.append("batch accounting rollback restore no longer preserves no changed case id behavior")
        for forbidden in (
            "WorkbenchPairRelationService.from_snapshot",
            "_configure_workbench_exception_application_service()",
            "save_workbench_pair_relations(",
        ):
            if forbidden in wrapper_source:
                violations.append(f"batch accounting restore wrapper still owns behavior {forbidden}")
        if "WorkbenchPairRelationRollbackRestoreService(" not in factory_source:
            violations.append("server.py does not build batch accounting rollback restore service")
        if "state_store=None" not in factory_source:
            violations.append("batch accounting rollback restore service must stay in-memory and not persist rollback snapshot")
        if "replace_pair_relation_service=self._replace_workbench_pair_relation_service" not in factory_source:
            violations.append("batch accounting rollback restore service does not use shared pair service replacement")
        if (
            "configure_exception_application_service=self._configure_workbench_exception_application_service"
            not in factory_source
        ):
            violations.append("batch accounting rollback restore service does not reconfigure exception application service")

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
                "WorkbenchCandidateMatchService.from_snapshot",
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
                "WorkbenchCandidateMatchService.from_snapshot",
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
            "WorkbenchCandidateMatchService.from_snapshot(previous_candidate_snapshot)",
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
        engine_source = (SERVICES_ROOT / "workbench_reconciliation_engine.py").read_text(encoding="utf-8")

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
            "_candidate_match_service.upsert_candidate",
            "mark_scope_processed",
            "_invalidate_read_models(scope_month)",
            "WorkbenchReconciliationEngine",
            "_relation_read_port",
        ):
            if marker not in orchestrator_source:
                violations.append(f"Workbench matching orchestrator no longer owns reference marker {marker}")

        for marker in (
            "expire_stale(",
            "expire_missing_for_scope",
            "upsert_decisions",
            "confirm_relation(",
            "consume_by_row_ids",
        ):
            if marker not in engine_source:
                violations.append(f"Workbench reconciliation engine no longer owns decision/relation marker {marker}")

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
            "| 197 | `server-py:workbench-confirm-link-preview-route-owner-extraction` | pending"
            not in queue_source
        ):
            violations.append("Next pending slice should extract Workbench confirm-link preview route ownership")
        if "Do not implement Go, Go Fiber or Go Worker." not in next_prompt_source:
            violations.append("Next prompt no longer forbids Go implementation during the current slice")
        if "`server-py:workbench-confirm-link-preview-route-owner-extraction`" not in next_prompt_source:
            violations.append("Next prompt no longer points at Workbench confirm-link preview route owner extraction")

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
        if "workbench_pair_snapshot_port=SettingsDataResetPairSnapshotPort(" not in runtime_init_source:
            violations.append("Application settings reset wiring does not wrap pair service in explicit port")

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
