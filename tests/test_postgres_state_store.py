from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.services.postgres_connection import PostgresConfigurationError, PostgresSettings, redact_database_url
from fin_ops_platform.services.postgres_repositories.common import serialize_value
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.state_store_diff import diff_state_snapshots
from fin_ops_platform.services.state_store_factory import build_state_store
from fin_ops_platform.services.etc_service import EtcBatch
from fin_ops_platform.services.workbench_candidate_match_service import CANDIDATE_MATCH_SCHEMA_VERSION


def unwrap_jsonb(value):
    return getattr(value, "obj", value)


class FakePostgresConnection:
    def __init__(self) -> None:
        self.settings: dict[str, dict] = {}
        self.attachment_cache: dict[str, dict] = {}
        self.executed: list[tuple[str, tuple]] = []
        self.queries: list[str] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.queries.append(sql)
        if "from app.app_settings" in sql:
            payload = self.settings.get(params[0])
            return {"settings_payload": payload} if payload is not None else None
        if "from app.oa_attachment_invoice_cache" in sql:
            payload = self.attachment_cache.get(params[0])
            return {"normalized_payload": payload} if payload is not None else None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.queries.append(sql)
        return []

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((sql, params))
        if "insert into app.app_settings" in sql:
            self.settings[params[0]] = unwrap_jsonb(params[1])
            return 1
        if "insert into app.oa_attachment_invoice_cache(" in sql:
            self.attachment_cache[params[0]] = unwrap_jsonb(params[7])
            return 1
        return 1

    def health_summary(self) -> dict[str, object]:
        return {"postgres_status": "ready", "postgres_database": "fin_ops_test", "postgres_schema_version": 7}


class FakeLegacyFileReader:
    def __init__(self) -> None:
        self.reads: list[str] = []

    def read(self, stored_file_path: str) -> bytes:
        self.reads.append(stored_file_path)
        return f"bytes:{stored_file_path}".encode()


class EtcReadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from app.etc_submission_batches" in sql:
            rows = [
                {
                    "key": "current_state:submission_batches:1",
                    "raw_payload": {
                        "normalized_payload": {
                            "batches": {
                                "etc_batch_0019": {
                                    "id": "etc_batch_0019",
                                    "invoice_ids": ["etc_invoice_0025"],
                                }
                            }
                        }
                    },
                },
                {
                    "key": "etc_batch_0019",
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "etc_batch_0019",
                            "etc_batch_id": "ETC-BATCH-0019",
                            "invoice_ids": ["etc_invoice_0025"],
                            "invoice_count": 1,
                            "total_amount": "100.00",
                        }
                    },
                },
            ]
            if "coalesce(legacy_mongo_id, '') !~ '^current_state:'" in sql:
                return rows[1:]
            return rows
        return []


class EtcFormalAndFallbackConnection(FakePostgresConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from app.etc_invoices" in sql:
            return []
        if "from app.etc_import_batches" in sql:
            return []
        if "from app.etc_submission_batches" in sql:
            return [
                {
                    "key": "etc_batch_0019",
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "etc_batch_0019",
                            "invoice_ids": [],
                        }
                    },
                }
            ]
        if "from app.etc_business_batches" in sql:
            return []
        return []


class CandidateFormalAndFallbackConnection(FakePostgresConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from read_model.workbench_candidate_matches" in sql:
            return [
                {
                    "key": "candidate-stale",
                    "payload": {"candidate_key": "candidate-stale", "scope_month": "2026-05"},
                }
            ]
        return []


class CandidateFormalWithCompletedScopeRunsConnection(CandidateFormalAndFallbackConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from job.workbench_matching_dirty_scopes" in sql:
            return [
                {
                    "scope_month": "2026-05",
                    "source_versions": {"source_version": 7},
                    "generated_at": "2026-06-13 01:20:00+08",
                    "request_id": "worker:2026-05",
                    "reason": "write_event",
                }
            ]
        return super().fetch_all(sql, params)


class WorkbenchReadModelFormalAndFallbackConnection(FakePostgresConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from read_model.workbench_snapshots" in sql:
            return [
                {
                    "key": "2026-05",
                    "payload": {"scope_key": "2026-05", "payload": {"open": {"groups": []}}},
                }
            ]
        return []


class PostgresStateStoreTests(unittest.TestCase):
    def test_database_url_is_redacted_without_query_or_password(self) -> None:
        redacted = redact_database_url("postgresql://fin_ops:secret@db.example.com:5432/fin_ops?sslmode=require")

        self.assertEqual(redacted, "postgresql://fin_ops:***@db.example.com:5432/fin_ops")
        self.assertNotIn("secret", redacted)
        self.assertNotIn("sslmode", redacted)

    def test_postgres_settings_require_database_url_when_backend_is_enabled(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(PostgresConfigurationError, "requires FIN_OPS_POSTGRES_DATABASE_URL or DATABASE_URL"):
                PostgresSettings.from_env()

    def test_factory_default_does_not_require_postgres_configuration(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {}, clear=True):
            store = build_state_store(Path(temp_dir))

        self.assertEqual(store.storage_backend, "local_pickle")

    def test_factory_postgres_mode_requires_database_url(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"FIN_OPS_APP_STORAGE_BACKEND": "postgres"}, clear=True):
            with self.assertRaisesRegex(PostgresConfigurationError, "requires FIN_OPS_POSTGRES_DATABASE_URL or DATABASE_URL"):
                build_state_store(Path(temp_dir))

    def test_read_model_repositories_use_optional_read_connection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            write_connection = FakePostgresConnection()
            read_connection = FakePostgresConnection()
            store = PostgresStateStore(
                data_dir=Path(temp_dir),
                connection=write_connection,
                sql_read_connection=read_connection,
            )

        self.assertIs(store.workbench_sql_read_repository._connection, read_connection)
        self.assertIs(store.search_sql_read_repository._connection, read_connection)
        self.assertIs(store.tax_offset_sql_read_repository._repository._connection, read_connection)
        self.assertIs(store.output_invoice_collection_sql_read_repository._repository._connection, read_connection)
        self.assertIs(store._read_model_repository._connection, write_connection)

    def test_ready_health_summary_uses_lightweight_runtime_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            summary = store.ready_health_summary()

        runtime = summary["runtime_infrastructure"]
        executed_sql = "\n".join(connection.queries).lower()
        self.assertEqual(summary["postgres_status"], "ready")
        self.assertIn("queue_backlog", runtime)
        self.assertIn("worker_metrics", runtime)
        self.assertNotIn("read_model_refresh_by_key", runtime)
        self.assertNotIn("workbench_read_model", runtime)
        self.assertNotIn("slow_refresh_event_samples", executed_sql)
        self.assertNotIn("workbench_generation_status_counts", executed_sql)

    def test_postgres_store_settings_and_cache_round_trip_through_parameterized_sql(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            defaults = store.load_app_settings()
            self.assertIn("completed_project_ids", defaults)
            self.assertEqual(defaults["admin_usernames"], [])
            self.assertEqual(defaults["bank_transaction_tags"], {})
            self.assertEqual(defaults["pending_invoice_tag_groups"], {})

            store.save_app_settings({"admin_usernames": ["admin"], "workbench_column_layouts": {"invoice": ["amount"]}})
            self.assertEqual(store.load_app_settings()["admin_usernames"], ["admin"])
            self.assertEqual(store.load_app_settings()["bank_transaction_tags"], {})
            self.assertEqual(store.load_app_settings()["pending_invoice_tag_groups"], {})

            store.save_oa_attachment_invoice_cache_entry(
                "attachment-1",
                {"parser_version": "v1", "cache_schema_version": "s1", "invoices": [{"invoice_no": "001"}]},
            )
            self.assertEqual(
                store.load_oa_attachment_invoice_cache_entry("attachment-1"),
                {
                    "cache_key": "attachment-1",
                    "parser_version": "v1",
                    "cache_schema_version": "s1",
                    "invoices": [{"invoice_no": "001"}],
                },
            )
            self.assertTrue(all("%s" in sql for sql, _ in connection.executed))

    def test_postgres_store_snapshot_methods_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {"FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT": "1"},
        ):
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=FakePostgresConnection())

            store.save({"imports": {"batches": {"batch-1": {"id": "batch-1"}}}})
            self.assertEqual(store.load()["imports"]["batches"]["batch-1"]["id"], "batch-1")

            result = store.add_manual_oa_imports(["row-1", "row-1", "row-2"], actor_id="tester")
            self.assertEqual(result["imported"], ["row-1", "row-2"])
            self.assertTrue(store.remove_manual_oa_import("row-1", actor_id="tester"))
            self.assertEqual(store.load_manual_oa_imports()["row_ids"], ["row-2"])

            store.save_workbench_pair_relations({"pair_relations": {"case-1": {"case_id": "case-1"}}})
            self.assertEqual(store.load_workbench_pair_relations()["pair_relations"]["case-1"]["case_id"], "case-1")

    def test_etc_repository_ignores_legacy_current_state_aggregate_rows(self) -> None:
        snapshot = PostgresOpsTaxEtcRepository(EtcReadConnection()).load_etc_state()

        self.assertEqual(list(snapshot["batches"]), ["etc_batch_0019"])
        self.assertEqual(snapshot["batches"]["etc_batch_0019"]["etc_batch_id"], "ETC-BATCH-0019")

    def test_postgres_etc_state_preserves_fallback_runtime_counters_when_formal_rows_exist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = EtcFormalAndFallbackConnection()
            connection.settings["state:etc_state"] = {
                "invoice_counter": 25,
                "batch_counter": 19,
                "import_batch_counter": 3,
                "business_batch_counter": 7,
                "batch_day_counters": {"20260520": 1},
                "invoice_numbers": {"ETC001": "etc_invoice_0001"},
                "batches": {"etc_batch_0019": {"id": "etc_batch_0019", "legacy": True}},
            }
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load_etc_state()

        self.assertEqual(snapshot["invoice_counter"], 25)
        self.assertEqual(snapshot["batch_counter"], 19)
        self.assertEqual(snapshot["import_batch_counter"], 3)
        self.assertEqual(snapshot["business_batch_counter"], 7)
        self.assertEqual(snapshot["batch_day_counters"], {"20260520": 1})
        self.assertEqual(snapshot["invoice_numbers"], {"ETC001": "etc_invoice_0001"})
        self.assertEqual(snapshot["batches"]["etc_batch_0019"]["id"], "etc_batch_0019")

    def test_postgres_candidate_matches_ignore_runtime_snapshot_fallback(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = CandidateFormalAndFallbackConnection()
            connection.settings["state:workbench_candidate_matches"] = {
                "schema_version": "workbench_candidate_matches.v1",
                "scope_runs": {"2026-05": {"status": "processed"}},
                "candidates": {"candidate-current": {"candidate_key": "candidate-current", "scope_month": "2026-05"}},
            }
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load_workbench_candidate_matches()

        self.assertNotIn("schema_version", snapshot)
        self.assertNotIn("scope_runs", snapshot)
        self.assertEqual(list(snapshot["candidates"]), ["candidate-stale"])

    def test_postgres_candidate_matches_restore_completed_scope_runs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PostgresStateStore(
                data_dir=Path(temp_dir),
                connection=CandidateFormalWithCompletedScopeRunsConnection(),
            )

            snapshot = store.load_workbench_candidate_matches()

        self.assertEqual(snapshot["schema_version"], CANDIDATE_MATCH_SCHEMA_VERSION)
        self.assertEqual(list(snapshot["candidates"]), ["candidate-stale"])
        self.assertEqual(
            snapshot["scope_runs"]["2026-05"],
            {
                "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "source_versions": {"source_version": 7},
                "candidate_count": 0,
                "generated_at": "2026-06-13 01:20:00+08",
                "request_id": "worker:2026-05",
                "reason": "write_event",
            },
        )

    def test_postgres_workbench_read_models_ignore_runtime_snapshot_fallback(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = WorkbenchReadModelFormalAndFallbackConnection()
            connection.settings["state:workbench_read_models"] = {
                "read_models": {"all": {"scope_key": "all", "payload": {"legacy": True}}},
            }
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load_workbench_read_models()

        self.assertEqual(list(snapshot["read_models"]), ["2026-05"])
        self.assertNotIn("all", snapshot["read_models"])

    def test_postgres_workbench_read_models_do_not_fallback_to_runtime_snapshot_when_sql_empty(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            connection.settings["state:workbench_read_models"] = {
                "read_models": {"all": {"scope_key": "all", "payload": {"legacy": True}}},
            }
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load_workbench_read_models()

        self.assertEqual(snapshot, {})

    def test_postgres_cost_statistics_read_models_do_not_fallback_to_runtime_snapshot_when_sql_empty(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            connection.settings["state:cost_statistics_read_models"] = {
                "read_models": {"active:2026-05": {"scope_key": "active:2026-05", "payload": {"legacy": True}}},
            }
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load_cost_statistics_read_models()

        self.assertEqual(snapshot, {})

    def test_postgres_tax_offset_read_models_do_not_fallback_to_runtime_snapshot_when_sql_empty(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            connection.settings["state:tax_offset_read_models"] = {
                "read_models": {"2026-05": {"scope_key": "2026-05", "payload": {"legacy": True}}},
            }
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load_tax_offset_read_models()

        self.assertEqual(snapshot, {})

    def test_postgres_save_does_not_write_full_state_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            store.save({"imports": {"batches": {"batch-1": {"id": "batch-1"}}}})

        setting_keys = [
            params[0]
            for sql, params in connection.executed
            if "insert into app.app_settings" in sql
        ]
        self.assertNotIn("state:full_state", setting_keys)

    def test_state_diff_compares_dataclass_and_dict_snapshots_by_serialized_value(self) -> None:
        batch = EtcBatch(
            id="etc_batch_0019",
            etc_batch_id="ETC-BATCH-0019",
            invoice_ids=["etc_invoice_0025"],
            invoice_count=1,
            total_amount=Decimal("100.00"),
        )
        postgres_payload = serialize_value(batch)

        result = diff_state_snapshots(
            {"batches": {"etc_batch_0019": batch}},
            {"batches": {"etc_batch_0019": postgres_payload}},
            domain="etc_state",
        )

        self.assertTrue(result.matched)

    def test_state_diff_treats_numeric_string_and_number_as_equivalent_without_relaxing_strings(self) -> None:
        numeric_result = diff_state_snapshots({"parse_confidence": 1.0}, {"parse_confidence": "1.0"})
        string_result = diff_state_snapshots({"invoice_number": "001"}, {"invoice_number": "1"})

        self.assertTrue(numeric_result.matched)
        self.assertFalse(string_result.matched)

    def test_postgres_store_local_file_contract(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=FakePostgresConnection())

            stored_path = store.store_import_file(
                session_id="session-1",
                file_id="file-1",
                file_name="bank.xlsx",
                content=b"file-bytes",
            )

            self.assertEqual(store.read_import_file(stored_path), b"file-bytes")
            self.assertTrue(Path(stored_path).exists())
            self.assertEqual(store.delete_import_files([stored_path, stored_path]), 1)
            self.assertFalse(Path(stored_path).exists())

    def test_postgres_store_reads_legacy_gridfs_reference_with_injected_reader(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            reader = FakeLegacyFileReader()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection, legacy_file_reader=reader)

            legacy_uri = "gridfs://import_file_blobs/legacy-gridfs-id"

            self.assertEqual(store.read_import_file(legacy_uri), b"bytes:gridfs://import_file_blobs/legacy-gridfs-id")
            self.assertEqual(reader.reads, [legacy_uri])
            self.assertEqual(store.delete_import_files([legacy_uri, legacy_uri]), 1)
            self.assertIn("update app.import_files set status = 'deleted'", connection.executed[-1][0])


if __name__ == "__main__":
    unittest.main()
