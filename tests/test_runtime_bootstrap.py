from __future__ import annotations

import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import build_application
from fin_ops_platform.app import server as server_module
from fin_ops_platform.services import file_object_migration as file_object_migration_module
from fin_ops_platform.services.import_file_service import FileImportSession
from fin_ops_platform.services import postgres_state_store as postgres_state_store_module
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services import runtime_bootstrap as runtime_bootstrap_module
from fin_ops_platform.services.state_store import ApplicationStateStore


class LoadTrackingStore:
    def __init__(self) -> None:
        self.load_calls = 0
        self.bootstrap_load_calls = 0

    @property
    def data_dir(self) -> Path:
        return Path("/tmp/fin-ops-bootstrap-test")

    @property
    def storage_backend(self) -> str:
        return "postgres"

    @property
    def storage_mode(self) -> str:
        return "postgres"

    @property
    def mongo_database_name(self) -> str | None:
        return None

    def load(self) -> dict[str, object]:
        self.load_calls += 1
        return {}

    def load_bootstrap_snapshot(self) -> dict[str, object]:
        self.bootstrap_load_calls += 1
        return {}

    def load_oa_sync_state(self) -> dict[str, object]:
        return {}

    def health_summary(self) -> dict[str, object]:
        return {"postgres_status": "ready"}

    def __getattr__(self, name: str):
        if name.startswith("load_"):
            return lambda *args, **kwargs: {}
        if name.startswith("save_"):
            return lambda *args, **kwargs: None
        raise AttributeError(name)


class ImportFactBootstrapConnection:
    def __init__(self) -> None:
        self.fetch_all_sql: list[str] = []
        self.fetch_one_sql: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_sql.append((normalized, params))
        if "from app.app_settings" in normalized and params and str(params[0]) in {"state:imports", "state:file_imports", "state:full_state"}:
            raise AssertionError(f"production import bootstrap must not read legacy snapshot key {params[0]}")
        if "count(*)" in normalized:
            return {"total": 0}
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_sql.append(normalized)
        if "from app.invoices" in normalized or "from app.bank_transactions" in normalized:
            raise AssertionError(f"production import bootstrap must not full-load facts: {sql}")
        return []

    def execute(self, sql: str, params: tuple = ()) -> int:
        return 1


class RuntimeBootstrapQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.enqueued.append((scope_type, scope_key, reason))


class MissingBankAccountBalanceRepository:
    def list_bank_account_balances(self, **_kwargs: object) -> dict[str, object] | None:
        raise RuntimeError('relation "read_model.bank_account_balances" does not exist')


class RuntimeBootstrapTests(unittest.TestCase):
    def test_postgres_file_import_boundary_reloads_current_session_without_full_state_load(self) -> None:
        session = FileImportSession(
            id="import_session_0021",
            imported_by="operator",
            file_count=0,
            status="preview_ready",
            files=[],
        )
        calls: list[str] = []
        store = SimpleNamespace(
            storage_backend="postgres",
            import_fact_repository=None,
            load_imports_snapshot=lambda: calls.append("imports") or {},
            load_file_imports_snapshot=lambda: calls.append("file_imports")
            or {
                "session_counter": 21,
                "file_counter": 63,
                "sessions": {session.id: session},
            },
        )
        app = object.__new__(server_module.Application)
        app._state_store = store

        app._reload_file_import_runtime_state()

        self.assertEqual(calls, ["imports", "file_imports"])
        self.assertIs(app._file_import_service.get_session(session.id), session)
        self.assertEqual(store.__dict__.get("load_calls", 0), 0)

    def test_lightweight_bootstrap_does_not_call_full_state_load_and_exposes_repositories(self) -> None:
        store = LoadTrackingStore()
        with patch("fin_ops_platform.app.server.build_state_store", return_value=store):
            app = build_application(data_dir=Path("/tmp/ignored"), bootstrap_mode="lightweight")

        self.assertEqual(store.load_calls, 0)
        summary = app.readiness_summary()
        self.assertEqual(summary["bootstrap"]["mode"], "lightweight")
        self.assertTrue(summary["bootstrap"]["legacy_snapshot_disabled"])
        self.assertTrue(hasattr(app, "runtime_repositories"))
        self.assertIs(app.runtime_repositories.state_store, store)

    def test_default_production_bootstrap_does_not_call_full_state_load(self) -> None:
        store = LoadTrackingStore()
        with patch("fin_ops_platform.app.server.build_state_store", return_value=store):
            app = build_application(data_dir=Path("/tmp/ignored"))

        self.assertEqual(store.load_calls, 0)
        summary = app.readiness_summary()
        self.assertEqual(summary["bootstrap"]["mode"], "production")
        self.assertTrue(summary["bootstrap"]["legacy_snapshot_disabled"])

    def test_application_init_does_not_call_legacy_full_snapshot_adapter_in_production(self) -> None:
        store = LoadTrackingStore()
        self.assertFalse(hasattr(server_module, "LegacySnapshotBootstrap"))
        with patch("fin_ops_platform.app.server.build_state_store", return_value=store):
            app = build_application(data_dir=Path("/tmp/ignored"))

        self.assertEqual(app.readiness_summary()["bootstrap"]["mode"], "production")

    def test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter(self) -> None:
        store = LoadTrackingStore()
        self.assertFalse(hasattr(server_module, "MongoOAAdapter"))
        with patch("fin_ops_platform.app.server.build_state_store", return_value=store):
            app = build_application(data_dir=Path("/tmp/ignored"))

        self.assertEqual(app.readiness_summary()["bootstrap"]["mode"], "production")

    def test_production_postgres_bootstrap_does_not_seed_demo_workbench_rows(self) -> None:
        store = LoadTrackingStore()
        with patch("fin_ops_platform.app.server.build_state_store", return_value=store), patch.object(
            server_module.WorkbenchQueryService,
            "_seed_all_rows",
            side_effect=AssertionError("production PostgreSQL bootstrap must not seed demo workbench rows"),
        ):
            app = build_application(data_dir=Path("/tmp/ignored"))

        self.assertEqual(app.readiness_summary()["bootstrap"]["mode"], "production")

    def test_postgres_state_store_does_not_expose_legacy_gridfs_reader(self) -> None:
        connection = ImportFactBootstrapConnection()
        self.assertFalse(hasattr(postgres_state_store_module, "LegacyGridFSFileReader"))
        self.assertFalse(hasattr(file_object_migration_module, "LegacyGridFSFileReader"))
        store = PostgresStateStore(data_dir=Path("/tmp/fin-ops-bootstrap-test"), connection=connection)

        self.assertFalse(hasattr(store, "_legacy_file_reader"))

    def test_runtime_bootstrap_does_not_expose_legacy_full_snapshot_adapter(self) -> None:
        self.assertFalse(hasattr(runtime_bootstrap_module, "LegacySnapshotBootstrap"))
        self.assertFalse(hasattr(runtime_bootstrap_module, "LEGACY_SNAPSHOT_ALLOWLIST"))
        self.assertFalse(hasattr(runtime_bootstrap_module, "LEGACY_FULL_SNAPSHOT_REASON_PREFIXES"))

    def test_application_server_does_not_call_state_store_load_directly(self) -> None:
        server_path = Path("backend/src/fin_ops_platform/app/server.py")
        source = server_path.read_text(encoding="utf-8")
        direct_calls = [
            match.group(0)
            for match in re.finditer(r"self\._state_store\.load\s*\(", source)
        ]

        self.assertEqual(direct_calls, [])

    def test_application_server_production_path_does_not_call_load_persisted_state(self) -> None:
        source = Path("backend/src/fin_ops_platform/app/server.py").read_text(encoding="utf-8")

        self.assertNotIn("LegacySnapshotBootstrap", source)
        self.assertNotIn("_legacy_bootstrap", source)
        self.assertNotIn("load_full_snapshot", source)
        self.assertNotIn("def _load_persisted_state", source)
        self.assertNotIn("_initialize_runtime_services(self._load_persisted_state", source)

    def test_production_postgres_workbench_requires_sql_read_model_repository(self) -> None:
        app = object.__new__(server_module.Application)
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        app._workbench_sql_read_repository = None
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": None})()
        response = app._handle_api_workbench("2026-05")

        self.assertEqual(response.status_code, 503)
        self.assertIn("read_model_unavailable", response.body)

    def test_production_postgres_bank_details_transactions_fail_closed_without_canonical_query(self) -> None:
        app = object.__new__(server_module.Application)
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        app._bank_detail_sql_read_repository = None
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": None})()
        app._bank_details_service = type(
            "LegacyBankDetails",
            (),
            {
                "list_transactions": lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("production bank details API must not fallback to legacy service")
                ),
                "_bank_transaction_tags_payload": lambda *args, **kwargs: {},
            },
        )()

        response = app._bank_details_routes().route(
            "GET",
            "/api/bank-details/transactions",
            {
                "date_from": ["2026-04-01"],
                "date_to": ["2026-04-30"],
                "page": ["1"],
                "page_size": ["100"],
            },
            None,
            {},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("bank_details_canonical_query_unavailable", response.body)

    def test_production_postgres_bank_details_accounts_fail_closed_without_canonical_query(self) -> None:
        app = object.__new__(server_module.Application)
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        app._bank_detail_sql_read_repository = None
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": None})()
        app._bank_details_service = type(
            "LegacyBankDetails",
            (),
            {
                "list_accounts": lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("production bank details accounts API must not fallback to legacy service")
                ),
            },
        )()

        response = app._bank_details_routes().route(
            "GET",
            "/api/bank-details/accounts",
            {"date_from": ["2026-04-01"], "date_to": ["2026-04-30"]},
            None,
            {},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("bank_details_canonical_query_unavailable", response.body)

    def test_production_postgres_bank_details_accounts_do_not_enqueue_retired_balance_refresh(self) -> None:
        app = object.__new__(server_module.Application)
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        app._bank_detail_sql_read_repository = object()
        app._bank_account_balance_sql_read_repository = MissingBankAccountBalanceRepository()
        queue = RuntimeBootstrapQueue()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._bank_details_service = type(
            "LegacyBankDetails",
            (),
            {
                "list_accounts": lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("production bank details accounts API must not fallback to legacy service")
                ),
            },
        )()

        response = app._bank_details_routes().route(
            "GET",
            "/api/bank-details/accounts",
            {"date_from": ["2026-04-01"], "date_to": ["2026-04-30"]},
            None,
            {},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("bank_details_canonical_query_unavailable", response.body)
        self.assertEqual(queue.enqueued, [])

    def test_production_snapshot_reads_are_confined_to_legacy_allowlist(self) -> None:
        allowed_paths = {
            Path("backend/src/fin_ops_platform/services/runtime_bootstrap.py"),
        }
        scanned_roots = (
            Path("backend/src/fin_ops_platform/app"),
            Path("backend/src/fin_ops_platform/services"),
        )
        violations: list[str] = []

        for root in scanned_roots:
            for path in root.rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                if path in allowed_paths:
                    continue
                if re.search(r"_state_store\.load\s*\(", source):
                    violations.append(str(path))

        self.assertEqual(violations, [])

    def test_postgres_state_store_does_not_expose_bootstrap_snapshot_loader(self) -> None:
        store = PostgresStateStore(data_dir=Path("/tmp/fin-ops-bootstrap-test"), connection=ImportFactBootstrapConnection())

        self.assertFalse(hasattr(store, "load_bootstrap_snapshot"))

    def test_application_state_store_does_not_expose_bootstrap_snapshot_loader(self) -> None:
        store = ApplicationStateStore(data_dir=Path("/tmp/fin-ops-bootstrap-test"), read_only=True)

        self.assertFalse(hasattr(store, "load_bootstrap_snapshot"))

    def test_server_downstream_bank_tag_consumers_use_runtime_tag_reader_boundary(self) -> None:
        source = Path("backend/src/fin_ops_platform/app/server.py").read_text(encoding="utf-8")

        self.assertIn("def _bank_transaction_tag_reader", source)
        self.assertEqual(
            source.count(
                "category_provider=self._bank_transaction_effective_category_provider"
            ),
            1,
        )
        self.assertIn("LocalCostStatisticsCanonicalRepository(", source)
        self.assertNotIn("effective_category_provider=self._bank_transaction_effective_category_provider", source)
        self.assertNotIn("self._bank_transaction_effective_category_provider.bulk_get_for_rows(", source)
        self.assertIn("effective_category_provider=self._bank_transaction_tag_reader()", source)

    def test_runtime_worker_handlers_use_canonical_effective_category_provider(self) -> None:
        source = Path("backend/src/fin_ops_platform/services/runtime_worker_handlers.py").read_text(encoding="utf-8")

        self.assertIn("BankTransactionEffectiveCategoryProvider", source)
        self.assertNotIn("BankTransactionTagReadFacade", source)
        self.assertNotIn("SearchService()", source)
        self.assertNotIn("_runtime_search_service", source)

    def test_standalone_worker_uses_canonical_category_provider_for_retained_workers(self) -> None:
        source = Path("backend/src/fin_ops_platform/app/worker.py").read_text(encoding="utf-8")

        self.assertNotIn("BankTransactionTagReadFacade", source)
        self.assertNotIn("bank_transaction_tag_read_facade", source)
        self.assertNotIn("CostStatisticsSqlProjectionBuilder(", source)
        self.assertNotIn("SearchPendingSqlProjectionBuilder(", source)
        self.assertNotIn("BankTransactionEffectiveCategoryProvider", source)

    def test_production_services_do_not_depend_on_retired_bank_tag_facade(self) -> None:
        paths = Path("backend/src/fin_ops_platform").rglob("*.py")
        violations = [
            str(path)
            for path in paths
            if "bank_transaction_tag_read_facade" in path.read_text(encoding="utf-8")
            or "BankTransactionTagReadFacade" in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(violations, [])

    def test_bank_transaction_tag_reader_always_uses_canonical_provider(self) -> None:
        app = object.__new__(server_module.Application)
        provider = object()
        app._bank_transaction_effective_category_provider = provider

        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        self.assertIs(app._bank_transaction_tag_reader(), provider)

        app._bootstrap_mode = "legacy"
        self.assertIs(app._bank_transaction_tag_reader(), provider)

        app._bootstrap_mode = "production"
        app._state_store = type("MongoStore", (), {"storage_backend": "mongo"})()
        self.assertIs(app._bank_transaction_tag_reader(), provider)

    def test_category_rebinding_keeps_downstream_services_on_canonical_provider(self) -> None:
        app = object.__new__(server_module.Application)
        provider = object()
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        app._turnover_ledger_service = type("TurnoverService", (), {})()
        app._live_workbench_service = type("LiveWorkbenchService", (), {})()
        app._pending_invoice_query_service = type("PendingInvoiceService", (), {})()

        app._bind_local_bank_transaction_category_runtime(
            category_service=object(),
            auto_category_service=object(),
            effective_category_provider=provider,
        )

        self.assertIs(app._bank_transaction_effective_category_provider, provider)
        self.assertIs(app._turnover_ledger_service._category_provider, provider)
        self.assertIs(app._live_workbench_service._category_provider, provider)
        self.assertIs(app._pending_invoice_query_service._effective_category_provider, provider)


if __name__ == "__main__":
    unittest.main()
