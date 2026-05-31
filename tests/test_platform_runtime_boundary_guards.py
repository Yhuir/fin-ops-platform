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

    def test_oa_mongo_adapter_direct_use_is_allowlisted(self) -> None:
        allowed_paths = {
            "backend/src/fin_ops_platform/app/oa_attachment_audit.py",
            "backend/src/fin_ops_platform/app/server.py",
            "backend/src/fin_ops_platform/app/worker.py",
            "backend/src/fin_ops_platform/services/etc_oa_detection.py",
            "backend/src/fin_ops_platform/services/oa_manual_import_service.py",
            "backend/src/fin_ops_platform/services/search_pending_sql_projection.py",
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
