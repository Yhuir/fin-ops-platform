from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import Application, build_application
from fin_ops_platform.services.postgres_connection import PostgresConfigurationError


class FakeStore:
    def __init__(
        self,
        *,
        runtime_snapshots: dict[str, dict] | None = None,
        runtime_infrastructure: dict[str, object] | None = None,
    ) -> None:
        self.runtime_snapshots = runtime_snapshots or {}
        self.runtime_infrastructure = runtime_infrastructure
        self.runtime_loader_calls: list[str] = []
        self.health_summary_calls = 0
        self.ready_health_summary_calls = 0
        self.full_snapshot_load_called = False

    def __getattr__(self, name: str):
        if name.startswith("load_"):
            return lambda *args, **kwargs: {}
        if name.startswith("save_"):
            return lambda *args, **kwargs: None
        if name.endswith("_exists"):
            return lambda *args, **kwargs: False
        raise AttributeError(name)

    @property
    def data_dir(self) -> Path:
        return Path("/tmp/fin-ops-fake")

    @property
    def storage_backend(self) -> str:
        return "postgres"

    @property
    def storage_mode(self) -> str:
        return "postgres"

    @property
    def mongo_database_name(self) -> str | None:
        return None

    def health_summary(self) -> dict[str, object]:
        self.health_summary_calls += 1
        return self._health_summary_payload()

    def ready_health_summary(self) -> dict[str, object]:
        self.ready_health_summary_calls += 1
        return self._health_summary_payload()

    def _health_summary_payload(self) -> dict[str, object]:
        return {
            "postgres_status": "ready",
            "postgres_database": "fin_ops_test",
            "postgres_schema_version": 7,
            "runtime_infrastructure": self.runtime_infrastructure or {
                "missing_required_worker_count": 0,
                "stale_required_worker_count": 0,
                "mismatched_required_worker_count": 0,
                "worker_metrics": [],
            },
        }

    def load_oa_sync_state(self) -> dict:
        return {}

    def load(self) -> dict:
        self.full_snapshot_load_called = True
        return {}

    def load_workbench_pair_relations(self) -> dict:
        self.runtime_loader_calls.append("load_workbench_pair_relations")
        return self.runtime_snapshots.get("workbench_pair_relations", {})

    def load_app_settings(self) -> dict:
        return {
            "completed_project_ids": [],
            "manual_projects": [],
            "synced_projects": [],
            "bank_account_mappings": [],
            "allowed_usernames": ["YNSYLP005", "test_finops_user"],
            "readonly_export_usernames": [],
            "admin_usernames": ["YNSYLP005"],
            "full_access_usernames": ["test_finops_user"],
            "access_control_version": 1,
            "workbench_column_layouts": {},
            "oa_retention": {},
            "oa_import": {},
            "oa_invoice_offset": {},
        }

    def load_tax_certified_imports(self) -> dict:
        return {}

    def load_etc_state(self) -> dict:
        return {}

    def load_etc_reconciliation_state(self) -> dict:
        return {}

    def load_historical_etc_repair_bundle_metadata(self) -> dict:
        return {}

    def load_historical_etc_repair_parsed_seeds(self) -> dict:
        return {}

    def load_historical_etc_repair_states(self) -> dict:
        return {}

    def load_background_jobs(self) -> dict:
        return {}

    def save_background_jobs(self, snapshot: dict) -> None:
        return None

    def load_app_health_alerts(self) -> dict:
        return {}

    def save_app_health_alerts(self, snapshot: dict) -> None:
        return None


class AppPostgresModeTests(unittest.TestCase):
    def test_default_build_application_requires_postgres_backend(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "requires FIN_OPS_APP_STORAGE_BACKEND=postgres"):
                build_application(data_dir=Path(temp_dir))

    def test_postgres_backend_without_database_url_fails_clearly(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"FIN_OPS_APP_STORAGE_BACKEND": "postgres"}, clear=True):
            with self.assertRaises(PostgresConfigurationError):
                build_application(data_dir=Path(temp_dir))

    def test_readiness_includes_postgres_status_without_uri(self) -> None:
        with TemporaryDirectory() as temp_dir, patch("fin_ops_platform.app.server.build_state_store", return_value=FakeStore()):
            app = build_application(data_dir=Path(temp_dir))

        summary = app.readiness_summary()
        storage = summary["storage"]
        self.assertEqual(storage["backend"], "postgres")
        self.assertEqual(storage["postgres_status"], "ready")
        self.assertEqual(storage["postgres_schema_version"], 7)
        self.assertEqual(summary["runtime_infrastructure"]["missing_required_worker_count"], 0)
        self.assertEqual(summary["runtime_infrastructure"]["stale_required_worker_count"], 0)
        self.assertEqual(summary["runtime_infrastructure"]["mismatched_required_worker_count"], 0)
        self.assertNotIn("url", str(storage).lower())
        self.assertNotIn("password", str(storage).lower())

    def test_ready_endpoint_exposes_runtime_infrastructure_contract(self) -> None:
        runtime_infrastructure = {
            "queue_backlog": {"dead_lettered": 3},
            "dirty_scopes": {"done": 10, "pending": 2},
            "failed_jobs": 3,
            "stale_dirty_scope_count": 2,
            "missing_required_worker_count": 0,
            "stale_required_worker_count": 0,
            "mismatched_required_worker_count": 1,
            "worker_metrics": [
                {"worker_instance": "workbench", "worker_kind": "workbench", "status": "available", "required": True},
                {
                    "worker_instance": "legacy-drain",
                    "worker_kind": "cost-tax-read-model",
                    "status": "mismatch",
                    "warning_code": "worker_event_type_mismatch",
                    "required": False,
                    "current_effective": False,
                },
            ],
            "dirty_scopes_by_scope": [
                {"scope_type": "workbench_relation", "scope_key": "all", "status": "pending", "count": 1},
                {"scope_type": "workbench_relation", "scope_key": "all", "status": "pending", "count": 1},
            ],
            "pending_outbox_events_by_scope": [
                {"event_type": "workbench_relation.read_model.refresh", "scope_key": "all", "status": "dead_lettered"}
            ],
        }
        store = FakeStore(runtime_infrastructure=runtime_infrastructure)
        with TemporaryDirectory() as temp_dir, patch(
            "fin_ops_platform.app.server.build_state_store",
            return_value=store,
        ):
            app = build_application(data_dir=Path(temp_dir))

        response = app.handle_request("GET", "/health/ready")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["runtime_infrastructure"]["missing_required_worker_count"], 0)
        self.assertEqual(payload["runtime_infrastructure"]["stale_required_worker_count"], 0)
        self.assertEqual(payload["runtime_infrastructure"]["mismatched_required_worker_count"], 1)
        self.assertNotIn("runtime_infrastructure", payload["storage"])
        self.assertNotIn("worker_metrics", payload["runtime_infrastructure"])
        self.assertEqual(payload["runtime_infrastructure"]["worker_metric_count"], 2)
        self.assertEqual(payload["runtime_infrastructure"]["worker_status_counts"], {"available": 1})
        self.assertEqual(store.ready_health_summary_calls, 1)
        self.assertEqual(store.health_summary_calls, 0)
        self.assertEqual(
            payload["runtime_infrastructure"]["worker_problem_samples"][0]["warning_code"],
            "worker_event_type_mismatch",
        )
        self.assertEqual(payload["runtime_infrastructure"]["dirty_scopes_by_scope_summary"]["count"], 2)
        self.assertEqual(payload["runtime_infrastructure"]["pending_outbox_events_by_scope_summary"]["count"], 1)

    def test_health_endpoint_exposes_workbench_relation_distribution_status(self) -> None:
        runtime_infrastructure = {
            "missing_required_worker_count": 0,
            "stale_required_worker_count": 0,
            "mismatched_required_worker_count": 0,
            "worker_metrics": [],
            "dirty_scopes_by_scope": [
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-01",
                    "status": "pending",
                    "count": 2,
                    "oldest_age_seconds": 15.0,
                },
                {
                    "scope_type": "pending_invoice",
                    "scope_key": "expense:2026-01",
                    "status": "pending",
                    "count": 9,
                },
            ],
            "pending_outbox_events_by_scope": [
                {
                    "event_type": "workbench_relation.read_model.refresh",
                    "status": "dead_lettered",
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-01",
                    "last_error": "boom",
                }
            ],
        }
        with TemporaryDirectory() as temp_dir, patch(
            "fin_ops_platform.app.server.build_state_store",
            return_value=FakeStore(runtime_infrastructure=runtime_infrastructure),
        ):
            app = build_application(data_dir=Path(temp_dir))

        payload = app.readiness_summary()["workbench_relation_read_model"]

        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["dirty_backlog"], 2)
        self.assertEqual(payload["stale_scopes"][0]["scope_key"], "2026-01")
        self.assertEqual(payload["last_failure_reason"], "boom")
        self.assertIn("workbench_relation_schema_version", payload["source_versions"])

    def test_postgres_runtime_bootstrap_loads_pair_relations_without_full_snapshot(self) -> None:
        pair_snapshot = {
            "pair_relations": {
                "case-1": {
                    "case_id": "case-1",
                    "row_ids": ["txn-1", "invoice-1"],
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-05",
                    "created_by": "test",
                    "created_at": "2026-05-21T00:00:00+00:00",
                    "updated_at": "2026-05-21T00:00:00+00:00",
                }
            }
        }
        store = FakeStore(runtime_snapshots={"workbench_pair_relations": pair_snapshot})

        with TemporaryDirectory() as temp_dir, patch("fin_ops_platform.app.server.build_state_store", return_value=store):
            app = build_application(data_dir=Path(temp_dir))

        self.assertFalse(store.full_snapshot_load_called)
        self.assertEqual(store.runtime_loader_calls, ["load_workbench_pair_relations"])
        active_relations = app._workbench_pair_relation_service.list_active_relations()
        self.assertEqual(len(active_relations), 1)
        self.assertEqual(active_relations[0]["case_id"], "case-1")
        self.assertEqual(active_relations[0]["row_ids"], ["txn-1", "invoice-1"])
        self.assertEqual(active_relations[0]["relation_mode"], "manual_confirmed")
        self.assertEqual(active_relations[0]["month_scope"], "2026-05")

    def test_postgres_runtime_uses_sql_workbench_projection_without_legacy_maintenance_entrypoint(self) -> None:
        self.assertTrue(hasattr(Application, "rebuild_workbench_read_model_scope"))
        self.assertTrue(hasattr(Application, "_enqueue_workbench_read_model_refresh"))
        self.assertFalse(hasattr(Application, "_refresh_workbench_read_model_scopes_for_maintenance"))


if __name__ == "__main__":
    unittest.main()
