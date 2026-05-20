from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.postgres_connection import PostgresConfigurationError


class FakeStore:
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
        return {"postgres_status": "ready", "postgres_database": "fin_ops_test", "postgres_schema_version": 7}

    def load_oa_sync_state(self) -> dict:
        return {}

    def load(self) -> dict:
        return {}

    def load_app_settings(self) -> dict:
        return {
            "completed_project_ids": [],
            "manual_projects": [],
            "synced_projects": [],
            "bank_account_mappings": [],
            "allowed_usernames": [],
            "readonly_export_usernames": [],
            "admin_usernames": [],
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
    def test_default_build_application_does_not_require_postgres_url(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {}, clear=True):
            app = build_application(data_dir=Path(temp_dir))

        self.assertEqual(app.readiness_summary()["storage"]["backend"], "local_pickle")

    def test_postgres_backend_without_database_url_fails_clearly(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"FIN_OPS_APP_STORAGE_BACKEND": "postgres"}, clear=True):
            with self.assertRaises(PostgresConfigurationError):
                build_application(data_dir=Path(temp_dir))

    def test_readiness_includes_postgres_status_without_uri(self) -> None:
        with TemporaryDirectory() as temp_dir, patch("fin_ops_platform.app.server.build_state_store", return_value=FakeStore()):
            app = build_application(data_dir=Path(temp_dir))

        storage = app.readiness_summary()["storage"]
        self.assertEqual(storage["backend"], "postgres")
        self.assertEqual(storage["postgres_status"], "ready")
        self.assertEqual(storage["postgres_schema_version"], 7)
        self.assertNotIn("url", str(storage).lower())
        self.assertNotIn("password", str(storage).lower())


if __name__ == "__main__":
    unittest.main()
