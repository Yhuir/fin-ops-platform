from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.services.postgres_connection import PostgresConfigurationError, PostgresSettings, redact_database_url
from fin_ops_platform.services.postgres_repositories.common import serialize_value
from fin_ops_platform.services.postgres_repositories.bank_flow_rule_batch_canonical_query import (
    BankFlowRuleBatchCanonicalQueryRepository,
)
from fin_ops_platform.services.bank_flow_rule_batch_canonical_query import (
    bank_flow_rule_batch_candidate_guard,
    bank_flow_rule_batch_rule_proof,
    bank_flow_rule_batch_selected_row_proofs,
    build_live_bank_flow_rule_batch_service,
)
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_repositories.settings_data_reset import (
    PostgresSettingsDataResetRepository,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.state_store_diff import diff_state_snapshots
from fin_ops_platform.services.state_store_factory import build_state_store
from fin_ops_platform.services.etc_service import EtcBatch


def unwrap_jsonb(value):
    return getattr(value, "obj", value)


class FakePostgresConnection:
    def __init__(self) -> None:
        self.settings: dict[str, dict] = {}
        self.attachment_cache: dict[str, dict] = {}
        self.manual_oa_imports: dict[str, dict] = {}
        self.oa_sync_watermarks: dict[str, dict] = {}
        self.historical_etc_repair_bundles: dict[str, dict] = {}
        self.historical_etc_repair_parsed_seeds: dict[str, dict] = {}
        self.historical_etc_repair_states: dict[str, dict] = {}
        self.executed: list[tuple[str, tuple]] = []
        self.queries: list[str] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.queries.append(sql)
        normalized = " ".join(sql.lower().split())
        if "with canonical_groups as" in normalized and "canonical_members as" in normalized:
            return {
                "paired_count": 0,
                "unpaired_count": 0,
                "oa_count": 0,
                "bank_count": 0,
                "invoice_count": 0,
                "exception_count": 0,
                "paired_oa_count": 0,
                "paired_bank_count": 0,
                "paired_invoice_count": 0,
                "unpaired_oa_count": 0,
                "unpaired_bank_count": 0,
                "unpaired_invoice_count": 0,
            }
        if "from app.app_settings" in sql:
            payload = self.settings.get(params[0])
            return {"settings_payload": payload} if payload is not None else None
        if "from app.oa_attachment_invoice_cache" in sql:
            payload = self.attachment_cache.get(params[0])
            return {"normalized_payload": payload} if payload is not None else None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.queries.append(sql)
        normalized = " ".join(sql.lower().split())
        if "select scope_key, generation_id, source_versions" in normalized:
            active_updates = [
                update_params
                for statement, update_params in self.executed
                if "set status = 'active'" in " ".join(statement.lower().split())
                and "status = 'building'" in " ".join(statement.lower().split())
            ]
            return [
                {
                    "scope_key": str(update_params[3]),
                    "generation_id": str(update_params[4]),
                    "source_versions": {},
                    "generated_at": "2026-05-28T09:00:00+00:00",
                }
                for update_params in active_updates
            ]
        if "from app.manual_oa_imports" in sql:
            return [
                {
                    "row_id": row_id,
                    "source": payload.get("source"),
                    "actor_id": payload.get("actor_id"),
                    "imported_at": payload.get("imported_at"),
                    "audit_payload": payload.get("audit") or {},
                    "raw_payload": {"normalized_payload": payload},
                }
                for row_id, payload in sorted(self.manual_oa_imports.items())
                if payload.get("status", "active") == "active"
            ]
        if "from app.oa_sync_watermarks" in sql:
            return [
                {"sync_key": sync_key, "payload": payload, "raw_payload": {"normalized_payload": payload}}
                for sync_key, payload in sorted(self.oa_sync_watermarks.items())
            ]
        if "from app.historical_etc_repair_bundles" in sql:
            return [
                {"key": bundle_id, "raw_payload": {"normalized_payload": payload}}
                for bundle_id, payload in sorted(self.historical_etc_repair_bundles.items())
            ]
        if "from app.historical_etc_repair_parsed_seeds" in sql:
            return [
                {"key": bundle_id, "parsed_payload": payload, "raw_payload": {"normalized_payload": payload}}
                for bundle_id, payload in sorted(self.historical_etc_repair_parsed_seeds.items())
            ]
        if "from app.historical_etc_repair_states" in sql:
            return [
                {"key": state_id, "state_payload": payload, "raw_payload": {"normalized_payload": payload}}
                for state_id, payload in sorted(self.historical_etc_repair_states.items())
            ]
        return []

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((sql, params))
        if "insert into app.app_settings" in sql:
            self.settings[params[0]] = unwrap_jsonb(params[1])
            return 1
        if "insert into app.oa_attachment_invoice_cache(" in sql:
            self.attachment_cache[params[0]] = unwrap_jsonb(params[7])
            return 1
        if "update app.manual_oa_imports set status = 'inactive'" in sql:
            active_row_ids = set(params[0]) if params else set()
            for row_id, payload in self.manual_oa_imports.items():
                if row_id not in active_row_ids:
                    payload["status"] = "inactive"
            return 1
        if "insert into app.manual_oa_imports(" in sql:
            raw_payload = unwrap_jsonb(params[5])
            normalized = dict(raw_payload.get("normalized_payload") if isinstance(raw_payload, dict) else {})
            normalized["status"] = "active"
            self.manual_oa_imports[params[0]] = normalized
            return 1
        if "insert into app.oa_sync_watermarks(" in sql:
            self.oa_sync_watermarks[params[0]] = unwrap_jsonb(params[1])
            return 1
        if "insert into app.historical_etc_repair_bundles(" in sql:
            raw_payload = unwrap_jsonb(params[5])
            self.historical_etc_repair_bundles[params[1]] = dict(raw_payload.get("normalized_payload") or {})
            return 1
        if "insert into app.historical_etc_repair_parsed_seeds(" in sql:
            raw_payload = unwrap_jsonb(params[5])
            self.historical_etc_repair_parsed_seeds[params[2]] = dict(raw_payload.get("normalized_payload") or {})
            return 1
        if "insert into app.historical_etc_repair_states(" in sql:
            self.historical_etc_repair_states[params[1]] = unwrap_jsonb(params[4])
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


class MatchingFormalAndFallbackConnection(FakePostgresConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from app.matching_runs" in sql:
            return [
                {
                    "key": "run-current",
                    "raw_payload": {
                        "normalized_payload": {
                            "run_id": "run-current",
                            "status": "completed",
                        }
                    },
                }
            ]
        if "from app.matching_results" in sql:
            return [
                {
                    "key": "result-current",
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "result-current",
                            "run_id": "run-current",
                        }
                    },
                }
            ]
        return []


class PostgresStateStoreTests(unittest.TestCase):
    def test_import_delta_port_rejects_cross_domain_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PostgresStateStore(
                data_dir=Path(temp_dir),
                connection=FakePostgresConnection(),
            )

            store.save_import_delta({"imports": {}, "file_imports": {}})
            with self.assertRaisesRegex(ValueError, "only imports and file_imports"):
                store.save_import_delta(
                    {
                        "imports": {},
                        "file_imports": {},
                        "tax_certified_imports": {},
                    }
                )

    def test_database_url_is_redacted_without_query_or_password(self) -> None:
        redacted = redact_database_url("postgresql://fin_ops:secret@db.example.com:5432/fin_ops?sslmode=require")

        self.assertEqual(redacted, "postgresql://fin_ops:***@db.example.com:5432/fin_ops")
        self.assertNotIn("secret", redacted)
        self.assertNotIn("sslmode", redacted)

    def test_postgres_settings_require_database_url_when_backend_is_enabled(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(PostgresConfigurationError, "requires FIN_OPS_POSTGRES_DATABASE_URL or DATABASE_URL"):
                PostgresSettings.from_env()

    def test_factory_default_requires_postgres_backend(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "requires FIN_OPS_APP_STORAGE_BACKEND=postgres"):
                build_state_store(Path(temp_dir))

    def test_factory_production_guard_rejects_default_local_storage(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"FIN_OPS_PRODUCTION_RUNTIME_GUARD": "1"}, clear=True):
            with self.assertRaisesRegex(ValueError, "requires FIN_OPS_APP_STORAGE_BACKEND=postgres"):
                build_state_store(Path(temp_dir))

    def test_factory_production_guard_rejects_explicit_local_storage(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                "FIN_OPS_PRODUCTION_RUNTIME_GUARD": "1",
                "FIN_OPS_APP_STORAGE_BACKEND": "local_pickle",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "requires FIN_OPS_APP_STORAGE_BACKEND=postgres"):
                build_state_store(Path(temp_dir))

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

        self.assertIs(store.workbench_relation_sql_read_repository._repository._connection, read_connection)
        self.assertFalse(hasattr(store, "search_sql_read_repository"))
        self.assertFalse(hasattr(store, "cost_statistics_sql_read_repository"))
        self.assertFalse(hasattr(store, "tax_offset_sql_read_repository"))
        self.assertFalse(hasattr(store, "input_invoice_usage_sql_read_repository"))
        self.assertFalse(hasattr(store, "output_invoice_collection_sql_read_repository"))
        self.assertFalse(hasattr(store, "no_oa_bank_batch_sql_read_repository"))
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
        self.assertEqual(runtime["rabbitmq_metric_error"], "ready_health_rabbitmq_metrics_skipped")
        self.assertNotIn("read_model_refresh_by_key", runtime)
        self.assertNotIn("workbench_read_model", runtime)
        self.assertNotIn("slow_refresh_event_samples", executed_sql)
        self.assertNotIn("workbench_generation_status_counts", executed_sql)

    def test_bank_flow_rule_batch_mutation_uses_scoped_batch_write_only(self) -> None:
        transaction = object()

        class TransactionContext:
            def __enter__(self) -> object:
                return transaction

            def __exit__(self, *_args: object) -> None:
                return None

        class Connection:
            def transaction(self) -> TransactionContext:
                return TransactionContext()

        store = object.__new__(PostgresStateStore)
        store._connection = Connection()
        calls: list[tuple[str, object]] = []

        class TransactionBoundRepository:
            def __init__(self, connection: object) -> None:
                self._connection = connection
                calls.append(("repository_connection", connection))

            def save_workbench_pair_relations(
                self,
                snapshot: dict[str, object],
                *,
                changed_case_ids: set[str],
            ) -> None:
                calls.append(
                    (
                        "pair_relations",
                        {
                            "snapshot": snapshot,
                            "changed_case_ids": changed_case_ids,
                        },
                    )
                )

            def save_bank_flow_rule_batch_items(
                self,
                snapshot: dict[str, object],
                *,
                batch_ids: set[str],
            ) -> None:
                calls.append(
                    (
                        "bank_flow_items",
                        {
                            "snapshot": snapshot,
                            "batch_ids": batch_ids,
                        },
                    )
                )

        with patch(
            "fin_ops_platform.services.postgres_state_store.PostgresWorkbenchRepository",
            TransactionBoundRepository,
        ):
            store.save_bank_flow_rule_batch_mutation(
                pair_relation_snapshot={
                    "pair_relations": {
                        "CASE-1": {
                            "case_id": "CASE-1",
                            "special_metadata": {"source_batch_id": "batch-1"},
                        }
                    }
                },
                bank_flow_rule_batch_snapshot={
                    "batches": {
                        "batch-1": {"batch_id": "batch-1", "relation_case_id": "CASE-1"},
                        "batch-2": {"batch_id": "batch-2", "relation_case_id": "CASE-2"},
                    }
                },
                changed_case_ids=["CASE-1"],
                changed_scope_keys=["all", "visibility:paired:2026-02", "2026-02"],
                changed_batch_ids=["batch-2"],
            )

        self.assertEqual(
            calls,
            [
                ("repository_connection", transaction),
                (
                    "pair_relations",
                    {
                        "snapshot": {
                            "pair_relations": {
                                "CASE-1": {
                                    "case_id": "CASE-1",
                                    "special_metadata": {"source_batch_id": "batch-1"},
                                }
                            }
                        },
                        "changed_case_ids": {"CASE-1"},
                    },
                ),
                (
                    "bank_flow_items",
                    {
                        "snapshot": {
                            "batches": {
                                "batch-1": {"batch_id": "batch-1", "relation_case_id": "CASE-1"},
                                "batch-2": {"batch_id": "batch-2", "relation_case_id": "CASE-2"},
                            }
                        },
                        "batch_ids": {"CASE-1", "batch-1", "batch-2"},
                    },
                ),
            ],
        )

    def test_bank_flow_mutations_roll_back_relation_and_batch_when_event_write_fails(self) -> None:
        class Transaction:
            def __init__(self) -> None:
                self.relations: dict[str, object] = {}
                self.history: list[object] = []
                self.batches: dict[str, object] = {}
                self.events: list[object] = []

        class TransactionContext:
            def __init__(self, connection: "Connection") -> None:
                self._connection = connection
                self.transaction = Transaction()

            def __enter__(self) -> Transaction:
                self._connection.transaction_count += 1
                return self.transaction

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                _exc: BaseException | None,
                _traceback: object,
            ) -> None:
                if exc_type is None:
                    self._connection.committed = self.transaction
                else:
                    self._connection.rollback_count += 1

        class Connection:
            def __init__(self) -> None:
                self.committed = Transaction()
                self.transaction_count = 0
                self.rollback_count = 0

            def transaction(self) -> TransactionContext:
                return TransactionContext(self)

        class FailingEventRepository:
            def __init__(self, transaction: Transaction) -> None:
                if not isinstance(transaction, Transaction):
                    raise AssertionError("repository must bind to the caller-owned transaction")
                self._transaction = transaction

            def save_workbench_pair_relations(
                self,
                snapshot: dict[str, object],
                *,
                changed_case_ids: set[str],
            ) -> None:
                self._transaction.relations.update(
                    {
                        case_id: dict(payload)
                        for case_id, payload in dict(
                            snapshot.get("pair_relations") or {}
                        ).items()
                        if case_id in changed_case_ids
                    }
                )
                self._transaction.history.extend(
                    list(snapshot.get("pair_relation_history") or [])
                )

            def save_bank_flow_rule_batch_items(
                self,
                snapshot: dict[str, object],
                *,
                batch_ids: set[str],
            ) -> None:
                self._transaction.batches.update(
                    {
                        batch_id: dict(payload)
                        for batch_id, payload in dict(
                            snapshot.get("batches") or {}
                        ).items()
                        if batch_id in batch_ids
                    }
                )
                raise RuntimeError("injected bank-flow event write failure")

        for mutation_type in (
            "single_submit",
            "selected_row_submit",
            "withdraw",
            "reset_submitted",
        ):
            with self.subTest(mutation_type=mutation_type):
                connection = Connection()
                store = object.__new__(PostgresStateStore)
                store._connection = connection
                with patch(
                    "fin_ops_platform.services.postgres_state_store.PostgresWorkbenchRepository",
                    FailingEventRepository,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "injected bank-flow event write failure",
                    ):
                        store.save_bank_flow_rule_batch_mutation(
                            pair_relation_snapshot={
                                "pair_relations": {
                                    f"CASE-{mutation_type}": {
                                        "case_id": f"CASE-{mutation_type}",
                                        "status": (
                                            "cancelled"
                                            if mutation_type in {"withdraw", "reset_submitted"}
                                            else "active"
                                        ),
                                    }
                                },
                                "pair_relation_history": [
                                    {
                                        "case_id": f"CASE-{mutation_type}",
                                        "operation_type": mutation_type,
                                    }
                                ],
                            },
                            bank_flow_rule_batch_snapshot={
                                "batches": {
                                    f"batch-{mutation_type}": {
                                        "batch_id": f"batch-{mutation_type}",
                                        "relation_case_id": f"CASE-{mutation_type}",
                                        "status": (
                                            "withdrawn"
                                            if mutation_type in {"withdraw", "reset_submitted"}
                                            else "submitted"
                                        ),
                                    }
                                },
                                "audit_log": [
                                    {
                                        "batch_id": f"batch-{mutation_type}",
                                        "operation": mutation_type,
                                    }
                                ],
                            },
                            changed_case_ids=[f"CASE-{mutation_type}"],
                            changed_scope_keys=["2026-05"],
                            changed_batch_ids=[f"batch-{mutation_type}"],
                        )

                self.assertEqual(connection.transaction_count, 1)
                self.assertEqual(connection.rollback_count, 1)
                self.assertEqual(connection.committed.relations, {})
                self.assertEqual(connection.committed.history, [])
                self.assertEqual(connection.committed.batches, {})
                self.assertEqual(connection.committed.events, [])

    def test_candidate_guard_fails_closed_when_rule_eligibility_changes(self) -> None:
        class Transaction:
            def __init__(self) -> None:
                self.executed: list[str] = []
                self.lock_queries: list[str] = []

            def execute(self, sql: str, _params: tuple[object, ...] = ()) -> int:
                self.executed.append(sql)
                return 0

            def fetch_all(
                self,
                sql: str,
                _params: tuple[object, ...] = (),
            ) -> list[dict[str, object]]:
                self.lock_queries.append(sql)
                return []

        transaction = Transaction()
        now_ineligible_source = {
            "candidate_rows": [
                {
                    "id": "bank-out-188500",
                    "trade_time": "2026-05-14T09:00:00",
                    "account_key": "CCB:8106",
                    "direction": "expense",
                    "amount": "188500.00",
                    "category_code": "internal_transfer",
                },
                {
                    "id": "bank-in-188500",
                    "trade_time": "2026-05-14T09:30:00",
                    "account_key": "ICBC:6386",
                    "direction": "income",
                    "amount": "188500.00",
                    "category_code": "internal_transfer",
                },
            ],
            "active_relations": [],
            "formal_items": [],
            "tag_policy": {
                "active_tags": [{"code": "internal_transfer"}],
                "requirements_by_tag_code": {
                    "internal_transfer": {
                        "requires_oa": True,
                        "requires_invoice": False,
                    }
                },
            },
        }

        with patch.object(
            BankFlowRuleBatchCanonicalQueryRepository,
            "read_candidate_guard_source",
            return_value=now_ineligible_source,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "bank_flow_rule_batch_candidate_guard_conflict",
            ):
                PostgresStateStore._assert_bank_flow_rule_batch_candidate_guard(
                    transaction,
                    {
                        "batch_id": "bank_flow_rule_batch_stale",
                        "scope_month": "2026-05",
                        "batch_type": "internal_transfer",
                        "row_ids": ["bank-in-188500", "bank-out-188500"],
                        "total_amount": "188500.00",
                        "version": 1,
                    },
                )

        self.assertEqual(
            transaction.executed,
            ["set transaction isolation level serializable"],
        )
        self.assertEqual(len(transaction.lock_queries), 5)
        self.assertTrue(
            any(
                "from app.app_settings" in query
                for query in transaction.lock_queries
            )
        )

    def test_candidate_guard_accepts_auto_only_internal_transfer_pair(self) -> None:
        class Transaction:
            def execute(self, _sql: str, _params: tuple[object, ...] = ()) -> int:
                return 0

            def fetch_all(
                self,
                _sql: str,
                _params: tuple[object, ...] = (),
            ) -> list[dict[str, object]]:
                return []

        source = {
            "candidate_rows": [
                {
                    "id": "bank-out-188500",
                    "trade_time": "2026-05-14T09:00:00",
                    "account_key": "CCB:8106",
                    "counterparty_name": "云南溯源科技有限公司",
                    "direction": "expense",
                    "amount": "188500.00",
                },
                {
                    "id": "bank-in-188500",
                    "trade_time": "2026-05-14T09:30:00",
                    "account_key": "ICBC:6386",
                    "counterparty_name": "云南溯源科技有限公司",
                    "direction": "income",
                    "amount": "188500.00",
                },
            ],
            "active_relations": [],
            "formal_items": [],
            "tag_policy": {
                "active_tags": [{"code": "internal_transfer"}],
                "requirements_by_tag_code": {
                    "internal_transfer": {
                        "requires_oa": False,
                        "requires_invoice": False,
                    }
                },
            },
        }

        with patch.object(
            BankFlowRuleBatchCanonicalQueryRepository,
            "read_candidate_guard_source",
            return_value=source,
        ):
            candidate = build_live_bank_flow_rule_batch_service(
                source
            ).list_batches()[0]
            PostgresStateStore._assert_bank_flow_rule_batch_candidate_guard(
                Transaction(),
                {
                    **bank_flow_rule_batch_candidate_guard(candidate),
                    "rule_proof": bank_flow_rule_batch_rule_proof(
                        source["tag_policy"],
                        "internal_transfer",
                    ),
                },
            )

    def test_selected_row_guard_fails_closed_on_canonical_fact_drift(self) -> None:
        class Transaction:
            def execute(self, _sql: str, _params: tuple[object, ...] = ()) -> int:
                return 0

            def fetch_all(
                self,
                _sql: str,
                _params: tuple[object, ...] = (),
            ) -> list[dict[str, object]]:
                return []

        source = {
            "candidate_rows": [
                {
                    "id": "bank-fee-1",
                    "trade_time": "2026-06-03 10:20:00",
                    "account_key": "ccb:8106",
                    "direction": "expense",
                    "amount": "9.80",
                    "category_code": "fee",
                }
            ],
            "active_relations": [],
            "formal_items": [],
            "tag_policy": {
                "active_tags": [{"code": "fee"}],
                "requirements_by_tag_code": {
                    "fee": {
                        "requires_oa": False,
                        "requires_invoice": False,
                    }
                },
            },
        }

        with patch.object(
            BankFlowRuleBatchCanonicalQueryRepository,
            "read_candidate_guard_source",
            return_value=source,
        ), self.assertRaisesRegex(
            RuntimeError,
            "bank_flow_rule_batch_candidate_guard_conflict",
        ):
            PostgresStateStore._assert_bank_flow_rule_batch_candidate_guard(
                Transaction(),
                {
                    "batch_id": "bank_flow_rule_batch_selected",
                    "scope_month": "2026-06",
                    "batch_type": "fee",
                    "row_ids": ["bank-fee-1"],
                    "total_amount": "8.80",
                    "version": 1,
                    "guard_mode": "selected_rows",
                    "selected_row_proofs": [
                        {
                            "row_id": "bank-fee-1",
                            "scope_month": "2026-06",
                            "category_code": "fee",
                            "amount": "8.80",
                            "direction": "expense",
                            "account_key": "ccb:8106",
                            "trade_time": "2026-06-03 10:20:00",
                        }
                    ],
                    "rule_proof": bank_flow_rule_batch_rule_proof(
                        source["tag_policy"],
                        "fee",
                    ),
                },
            )

    def test_selected_row_guard_fails_closed_when_rule_requirement_changes(self) -> None:
        class Transaction:
            def execute(self, _sql: str, _params: tuple[object, ...] = ()) -> int:
                return 0

            def fetch_all(
                self,
                _sql: str,
                _params: tuple[object, ...] = (),
            ) -> list[dict[str, object]]:
                return []

        row = {
            "id": "bank-fee-1",
            "trade_time": "2026-06-03 10:20:00",
            "account_key": "ccb:8106",
            "direction": "expense",
            "amount": "8.80",
            "category_code": "fee",
        }
        initial_policy = {
            "version": 10,
            "active_tags": [{"code": "fee"}],
            "requirements_by_tag_code": {
                "fee": {"requires_oa": False, "requires_invoice": False},
            },
        }
        changed_source = {
            "candidate_rows": [row],
            "active_relations": [],
            "formal_items": [],
            "tag_policy": {
                "version": 11,
                "active_tags": [{"code": "fee"}],
                "requirements_by_tag_code": {
                    "fee": {"requires_oa": False, "requires_invoice": True},
                },
            },
        }

        with patch.object(
            BankFlowRuleBatchCanonicalQueryRepository,
            "read_candidate_guard_source",
            return_value=changed_source,
        ), self.assertRaisesRegex(
            RuntimeError,
            "bank_flow_rule_batch_candidate_guard_conflict",
        ):
            PostgresStateStore._assert_bank_flow_rule_batch_candidate_guard(
                Transaction(),
                {
                    "batch_id": "bank_flow_rule_batch_selected",
                    "scope_month": "2026-06",
                    "batch_type": "fee",
                    "row_ids": ["bank-fee-1"],
                    "total_amount": "8.80",
                    "version": 1,
                    "guard_mode": "selected_rows",
                    "selected_row_proofs": bank_flow_rule_batch_selected_row_proofs(
                        [row],
                        {"bank-fee-1": {"effective_category_code": "fee"}},
                    ),
                    "rule_proof": bank_flow_rule_batch_rule_proof(
                        initial_policy,
                        "fee",
                    ),
                },
            )

    def test_selected_row_guard_accepts_equivalent_trade_time_serializations(
        self,
    ) -> None:
        class Transaction:
            def execute(self, _sql: str, _params: tuple[object, ...] = ()) -> int:
                return 0

            def fetch_all(
                self,
                _sql: str,
                _params: tuple[object, ...] = (),
            ) -> list[dict[str, object]]:
                return []

        initial_row = {
            "id": "bank-fee-1",
            "trade_time": "2026-08-01 15:24:03",
            "account_key": "ccb:8106",
            "direction": "expense",
            "amount": "4.50",
            "category_code": "fee",
        }
        canonical_row = {
            **initial_row,
            "trade_time": "2026-08-01T15:24:03+08:00",
        }
        source = {
            "candidate_rows": [canonical_row],
            "active_relations": [],
            "formal_items": [],
            "tag_policy": {
                "active_tags": [{"code": "fee"}],
                "requirements_by_tag_code": {
                    "fee": {"requires_oa": False, "requires_invoice": False}
                },
            },
        }

        with patch.object(
            BankFlowRuleBatchCanonicalQueryRepository,
            "read_candidate_guard_source",
            return_value=source,
        ):
            PostgresStateStore._assert_bank_flow_rule_batch_candidate_guard(
                Transaction(),
                {
                    "batch_id": "bank_flow_rule_batch_selected",
                    "scope_month": "2026-08",
                    "batch_type": "fee",
                    "row_ids": ["bank-fee-1"],
                    "total_amount": "4.50",
                    "version": 1,
                    "guard_mode": "selected_rows",
                    "selected_row_proofs": bank_flow_rule_batch_selected_row_proofs(
                        [initial_row],
                        {"bank-fee-1": {"effective_category_code": "fee"}},
                    ),
                    "rule_proof": bank_flow_rule_batch_rule_proof(
                        source["tag_policy"],
                        "fee",
                    ),
                },
            )

    def test_selected_row_guard_still_rejects_real_trade_time_drift(self) -> None:
        class Transaction:
            def execute(self, _sql: str, _params: tuple[object, ...] = ()) -> int:
                return 0

            def fetch_all(
                self,
                _sql: str,
                _params: tuple[object, ...] = (),
            ) -> list[dict[str, object]]:
                return []

        initial_row = {
            "id": "bank-fee-1",
            "trade_time": "2026-08-01 15:24:03",
            "account_key": "ccb:8106",
            "direction": "expense",
            "amount": "4.50",
            "category_code": "fee",
        }
        source = {
            "candidate_rows": [
                {**initial_row, "trade_time": "2026-08-01T15:24:04+08:00"}
            ],
            "active_relations": [],
            "formal_items": [],
            "tag_policy": {
                "active_tags": [{"code": "fee"}],
                "requirements_by_tag_code": {
                    "fee": {"requires_oa": False, "requires_invoice": False}
                },
            },
        }

        with patch.object(
            BankFlowRuleBatchCanonicalQueryRepository,
            "read_candidate_guard_source",
            return_value=source,
        ), self.assertRaisesRegex(
            RuntimeError,
            "bank_flow_rule_batch_candidate_guard_conflict",
        ):
            PostgresStateStore._assert_bank_flow_rule_batch_candidate_guard(
                Transaction(),
                {
                    "batch_id": "bank_flow_rule_batch_selected",
                    "scope_month": "2026-08",
                    "batch_type": "fee",
                    "row_ids": ["bank-fee-1"],
                    "total_amount": "4.50",
                    "version": 1,
                    "guard_mode": "selected_rows",
                    "selected_row_proofs": bank_flow_rule_batch_selected_row_proofs(
                        [initial_row],
                        {"bank-fee-1": {"effective_category_code": "fee"}},
                    ),
                    "rule_proof": bank_flow_rule_batch_rule_proof(
                        source["tag_policy"],
                        "fee",
                    ),
                },
            )

    def test_workbench_pair_relation_scoped_loader_delegates_to_canonical_repository(self) -> None:
        class RelationRepository:
            def __init__(self) -> None:
                self.full_snapshot_loaded = False
                self.scoped_calls: list[dict[str, object]] = []

            def load_workbench_pair_relations(self) -> dict[str, object]:
                self.full_snapshot_loaded = True
                return {
                    "pair_relations": {
                        "unrelated-case": {
                            "case_id": "unrelated-case",
                            "row_ids": ["unrelated-row"],
                        }
                    }
                }

            def load_workbench_pair_relations_for_row_ids(
                self,
                row_ids: list[str],
                *,
                case_ids: list[str] | None = None,
            ) -> dict[str, object]:
                self.scoped_calls.append({"row_ids": list(row_ids), "case_ids": list(case_ids or [])})
                return {
                    "pair_relations": {
                        "case-1": {
                            "case_id": "case-1",
                            "row_ids": ["bank-row-1", "bank-row-2"],
                            "status": "confirmed",
                        }
                    },
                    "pair_relation_history": [
                        {
                            "request_id": "request-1",
                            "after_relations": [{"case_id": "case-1"}],
                        }
                    ],
                }

        repository = RelationRepository()
        store = object.__new__(PostgresStateStore)
        store._workbench_relation_repository = repository

        snapshot = store.load_workbench_pair_relations_for_row_ids(["bank-row-1"], case_ids=["case-1"])

        self.assertFalse(repository.full_snapshot_loaded)
        self.assertEqual(repository.scoped_calls, [{"row_ids": ["bank-row-1"], "case_ids": ["case-1"]}])
        self.assertEqual(list(snapshot["pair_relations"]), ["case-1"])
        self.assertEqual(snapshot["pair_relations"]["case-1"]["row_ids"], ["bank-row-1", "bank-row-2"])
        self.assertEqual(snapshot["pair_relation_history"][0]["request_id"], "request-1")

    def test_active_workbench_pair_relation_loader_skips_history(self) -> None:
        class RelationRepository:
            def __init__(self) -> None:
                self.calls: list[dict[str, list[str]]] = []

            def load_active_workbench_pair_relations_for_row_ids(
                self,
                row_ids: list[str],
                *,
                case_ids: list[str] | None = None,
            ) -> dict[str, object]:
                self.calls.append({"row_ids": list(row_ids), "case_ids": list(case_ids or [])})
                return {
                    "pair_relations": {
                        "case-1": {
                            "case_id": "case-1",
                            "row_ids": ["bank-row-1"],
                            "status": "active",
                        }
                    }
                }

        repository = RelationRepository()
        store = object.__new__(PostgresStateStore)
        store._workbench_relation_repository = repository

        snapshot = store.load_active_workbench_pair_relations_for_row_ids(
            ["bank-row-1"],
            case_ids=["case-1"],
        )

        self.assertEqual(
            repository.calls,
            [{"row_ids": ["bank-row-1"], "case_ids": ["case-1"]}],
        )
        self.assertEqual(list(snapshot["pair_relations"]), ["case-1"])

    def test_postgres_store_settings_and_cache_round_trip_through_parameterized_sql(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            defaults = store.load_app_settings()
            self.assertIn("completed_project_ids", defaults)
            self.assertEqual(defaults["admin_usernames"], ["YNSYLP005"])
            self.assertEqual(defaults["bank_transaction_tags"], {})
            self.assertEqual(defaults["pending_invoice_tag_groups"], {})

            store.save_app_settings({"admin_usernames": ["admin"], "workbench_column_layouts": {"invoice": ["amount"]}})
            self.assertEqual(store.load_app_settings()["admin_usernames"], ["YNSYLP005"])
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

    def test_postgres_store_snapshot_methods_round_trip_without_full_state_fallback(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {"FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT": "1"},
        ):
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            store.save({"imports": {"batches": {"batch-1": {"id": "batch-1"}}}})
            setting_keys = [
                params[0]
                for sql, params in connection.executed
                if "insert into app.app_settings" in sql
            ]
            self.assertNotIn("state:full_state", setting_keys)

            store.save_oa_sync_state({"poll_fingerprints": {"2026-03": "fingerprint-001"}})
            self.assertEqual(store.load_oa_sync_state()["poll_fingerprints"], {"2026-03": "fingerprint-001"})
            self.assertNotIn("state:oa_sync_state", connection.settings)
            self.assertIn("oa_sync_state", connection.oa_sync_watermarks)
            self.assertNotIn("state:oa_sync_state", connection.oa_sync_watermarks)

            result = store.add_manual_oa_imports(["row-1", "row-1", "row-2"], actor_id="tester")
            self.assertEqual(result["imported"], ["row-1", "row-2"])
            self.assertTrue(store.remove_manual_oa_import("row-1", actor_id="tester"))
            self.assertEqual(store.load_manual_oa_imports()["row_ids"], ["row-2"])
            self.assertNotIn("state:manual_oa_imports", connection.settings)

            store.save_workbench_pair_relations({"pair_relations": {"case-1": {"case_id": "case-1"}}})
            self.assertNotIn("state:workbench_pair_relations", connection.settings)

    def test_postgres_canonical_fact_snapshots_do_not_fallback_to_runtime_settings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            connection.settings.update(
                {
                    "state:workbench_pair_relations": {"pair_relations": {"legacy-case": {"case_id": "legacy-case"}}},
                    "state:no_oa_bank_batches": {"batches": {"legacy-batch": {"batch_id": "legacy-batch"}}},
                    "state:bank_transaction_categories": {"categories": {"legacy": {"category_id": "legacy"}}},
                    "state:turnover_relations": {"relations": {"legacy": {"relation_id": "legacy"}}},
                    "state:turnover_ledger_extras": {"version": 9, "extras": [{"legacy": True}]},
                    "state:tax_certified_imports": {"records": {"legacy": {"record_id": "legacy"}}},
                    "state:pending_invoice_commands": {"legacy-command": {"request_id": "legacy-command"}},
                    "state:workbench_overrides": {"row_overrides": {"legacy-row": {"row_id": "legacy-row"}}},
                    "state:workbench_exception_cases": {"cases": {"legacy-case": {"case_id": "legacy-case"}}},
                    "state:manual_oa_imports": {"row_ids": ["legacy-row"], "entries": {"legacy-row": {"row_id": "legacy-row"}}},
                    "state:oa_sync_state": {"poll_fingerprints": {"legacy": "fingerprint"}},
                }
            )
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            self.assertEqual(store.load_workbench_pair_relations(), {})
            self.assertEqual(store.load_no_oa_bank_batches(), {})
            self.assertEqual(store.load_bank_transaction_categories()["categories"], {})
            self.assertEqual(store.load_bank_transaction_categories()["audit_log"], [])
            self.assertEqual(store.load_turnover_relations()["relations"], [])
            self.assertEqual(store.load_turnover_relations()["audit_log"], [])
            self.assertEqual(store.load_turnover_ledger_extras(), {"version": 1, "extras": []})
            self.assertEqual(store.load_tax_certified_imports(), {})
            self.assertEqual(store.load_pending_invoice_commands(), {})
            self.assertEqual(store.load_workbench_overrides(), {})
            self.assertEqual(store.load_workbench_exception_cases(), {})
            self.assertEqual(store.load()["workbench_overrides"], {})
            self.assertEqual(store.load_manual_oa_imports()["row_ids"], [])
            self.assertEqual(store.load_oa_sync_state(), {})

    def test_postgres_canonical_fact_saves_do_not_write_runtime_settings_snapshots(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            store.save_workbench_pair_relations({"pair_relations": {"case-1": {"case_id": "case-1"}}})
            store.save_no_oa_bank_batches({"batches": {"batch-1": {"batch_id": "batch-1"}}})
            self.assertFalse(hasattr(store, "save_bank_transaction_categories"))
            store.save_turnover_relations({"relations": {"rel-1": {"relation_id": "rel-1"}}})
            store.save_turnover_ledger_extras({"version": 1, "extras": [{"id": "extra-1"}]})
            store.save_tax_certified_imports({"records": {"record-1": {"record_id": "record-1"}}})
            store.save_pending_invoice_commands({"cmd-1": {"request_id": "cmd-1", "status": "pending"}})
            store.save_workbench_overrides({"row_overrides": {"row-1": {"row_id": "row-1"}}})
            store.save_workbench_exception_cases({"cases": {"case-1": {"case_id": "case-1"}}})
            store.save_manual_oa_imports({"row_ids": ["row-1"], "entries": {"row-1": {"row_id": "row-1"}}})
            store.save_oa_sync_state({"poll_fingerprints": {"2026-03": "fingerprint-001"}})

            self.assertNotIn("state:workbench_pair_relations", connection.settings)
            self.assertNotIn("state:no_oa_bank_batches", connection.settings)
            self.assertNotIn("state:bank_transaction_categories", connection.settings)
            self.assertNotIn("state:turnover_relations", connection.settings)
            self.assertNotIn("state:turnover_ledger_extras", connection.settings)
            self.assertNotIn("state:tax_certified_imports", connection.settings)
            self.assertNotIn("state:pending_invoice_commands", connection.settings)
            self.assertNotIn("state:workbench_overrides", connection.settings)
            self.assertNotIn("state:workbench_exception_cases", connection.settings)
            self.assertNotIn("state:manual_oa_imports", connection.settings)
            self.assertNotIn("state:oa_sync_state", connection.settings)
            self.assertIn("oa_sync_state", connection.oa_sync_watermarks)
            self.assertNotIn("state:oa_sync_state", connection.oa_sync_watermarks)

    def test_postgres_imports_do_not_fallback_to_runtime_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            connection.settings["state:imports"] = {"batches": {"legacy-batch": {"id": "legacy-batch"}}}
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load_imports_snapshot()

        self.assertEqual(snapshot, {})

    def test_postgres_file_imports_do_not_fallback_to_runtime_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            connection.settings["state:file_imports"] = {"sessions": {"legacy-session": {"id": "legacy-session"}}}
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load_file_imports_snapshot()

        self.assertEqual(snapshot, {})

    def test_postgres_matching_does_not_fallback_to_runtime_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = MatchingFormalAndFallbackConnection()
            connection.settings["state:matching"] = {
                "runs": {"run-legacy": {"run_id": "run-legacy"}},
                "results": {"result-legacy": {"id": "result-legacy"}},
            }
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load_matching_snapshot()

        self.assertEqual(list(snapshot["runs"]), ["run-current"])
        self.assertEqual(list(snapshot["results"]), ["result-current"])
        self.assertNotIn("run-legacy", snapshot["runs"])
        self.assertNotIn("result-legacy", snapshot["results"])

    def test_postgres_save_matching_does_not_write_runtime_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            store.save({"matching": {"runs": {"run-legacy": {"run_id": "run-legacy"}}}})

        self.assertNotIn("state:matching", connection.settings)

    def test_etc_repository_ignores_legacy_current_state_aggregate_rows(self) -> None:
        snapshot = PostgresOpsTaxEtcRepository(EtcReadConnection()).load_etc_state()

        self.assertEqual(list(snapshot["batches"]), ["etc_batch_0019"])
        self.assertEqual(snapshot["batches"]["etc_batch_0019"]["etc_batch_id"], "ETC-BATCH-0019")

    def test_postgres_etc_state_ignores_fallback_runtime_counters_when_formal_rows_exist(self) -> None:
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

        self.assertEqual(snapshot["invoice_counter"], 0)
        self.assertEqual(snapshot["batch_counter"], 19)
        self.assertEqual(snapshot["import_batch_counter"], 0)
        self.assertEqual(snapshot["business_batch_counter"], 0)
        self.assertEqual(snapshot["batch_day_counters"], {})
        self.assertEqual(snapshot["invoice_numbers"], {})
        self.assertEqual(snapshot["batches"]["etc_batch_0019"]["id"], "etc_batch_0019")

    def test_postgres_etc_states_do_not_fallback_to_runtime_snapshot_when_sql_empty(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            connection.settings["state:etc_state"] = {"invoice_counter": 25}
            connection.settings["state:etc_reconciliation_state"] = {"task_counter": 9}
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            self.assertEqual(store.load_etc_state(), {})
            self.assertEqual(store.load_etc_reconciliation_state(), {})

    def test_postgres_save_etc_states_do_not_write_runtime_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            store.save_etc_state({"invoices": {"etc_invoice_0001": {"id": "etc_invoice_0001"}}})
            store.save_etc_reconciliation_state({"tasks": {"ETC-RECON-000001": {"task_id": "ETC-RECON-000001"}}})

        self.assertNotIn("state:etc_state", connection.settings)
        self.assertNotIn("state:etc_reconciliation_state", connection.settings)

    def test_postgres_historical_etc_repair_does_not_use_runtime_snapshots(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            connection.settings.update(
                {
                    "state:historical_etc_repair_bundles": {"legacy": {"bundle_id": "legacy"}},
                    "state:historical_etc_repair_parsed_seeds": {"legacy": {"bundle_id": "legacy"}},
                    "state:historical_etc_repair_states": {"legacy": {"status": "legacy"}},
                }
            )
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            bundle = store.save_historical_etc_repair_bundle(
                bundle_id="bundle-1",
                file_name="seed.zip",
                content=b"seed-content",
                metadata={"source": "unit"},
            )
            seed = store.save_historical_etc_repair_parsed_seed(
                bundle_id="bundle-1",
                parsed_seed={"status": "parsed"},
            )
            store.save_historical_etc_repair_states({"bundle-1": {"status": "completed"}})

            self.assertEqual(store.load_historical_etc_repair_bundle_metadata()["bundle-1"]["sha256"], bundle["sha256"])
            self.assertEqual(store.load_historical_etc_repair_parsed_seed("bundle-1")["status"], seed["status"])
            self.assertEqual(store.load_historical_etc_repair_states()["bundle-1"]["status"], "completed")

        self.assertNotIn("legacy", connection.historical_etc_repair_bundles)
        self.assertNotIn("legacy", connection.historical_etc_repair_parsed_seeds)
        self.assertNotIn("legacy", connection.historical_etc_repair_states)
        self.assertEqual(connection.settings["state:historical_etc_repair_bundles"], {"legacy": {"bundle_id": "legacy"}})




    def test_postgres_full_state_snapshot_omits_cost_statistics_read_model(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            snapshot = store.load()
            store.save(
                {
                    "cost_statistics_read_models": {
                        "read_models": {
                            "active:2026-05": {
                                "scope_key": "active:2026-05",
                                "payload": {"legacy": True},
                            }
                        }
                    }
                }
            )

        self.assertNotIn("cost_statistics_read_models", snapshot)
        self.assertNotIn("read_model.cost_statistics_read_models", "\n".join(connection.queries).lower())
        self.assertNotIn(
            "read_model.cost_statistics_read_models",
            "\n".join(sql for sql, _params in connection.executed).lower(),
        )



    def test_postgres_runtime_jobs_and_health_do_not_fallback_to_runtime_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            connection.settings["state:background_jobs"] = {"job-legacy": {"job_id": "job-legacy"}}
            connection.settings["state:app_health_alerts"] = {"records": {"alert-legacy": {"alert_id": "alert-legacy"}}}
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            self.assertEqual(store.load_background_jobs(), {})
            self.assertEqual(store.load_app_health_alerts(), {})

    def test_postgres_runtime_jobs_and_health_do_not_write_runtime_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            store.save_background_job({"job_id": "job-1", "status": "queued"})
            store.save_app_health_alerts({"records": {"alert-1": {"alert_id": "alert-1", "status": "unpaired"}}})

        self.assertNotIn("state:background_jobs", connection.settings)
        self.assertNotIn("state:app_health_alerts", connection.settings)

    def test_background_job_point_io_canonicalizes_stale_raw_job_id(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)
            with patch.object(
                connection,
                "fetch_one",
                return_value={
                    "job_id": "job-canonical",
                    "raw_payload": {
                        "normalized_payload": {
                            "job_id": "job-stale",
                            "type": "file_import",
                            "status": "queued",
                        }
                    },
                },
            ):
                payload = store.load_background_job("job-canonical")

            store.save_background_job(payload or {})

        self.assertEqual(payload["job_id"], "job-canonical")
        self.assertFalse(any("order by created_at" in " ".join(sql.lower().split()) for sql in connection.queries))
        background_job_writes = [
            params
            for sql, params in connection.executed
            if "insert into job.background_jobs" in " ".join(sql.lower().split())
        ]
        self.assertEqual(len(background_job_writes), 1)
        self.assertEqual(background_job_writes[0][0], "job-canonical")

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

    def test_postgres_store_marks_missing_import_file_deleted_for_idempotent_retry(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)
            missing_path = str(Path(temp_dir) / "already-missing.xlsx")

            self.assertEqual(store.delete_import_files([missing_path]), 1)
            self.assertIn(
                "update app.import_files set status = 'deleted'",
                connection.executed[-1][0],
            )

    def test_postgres_reset_uses_normalized_file_type_and_deleting_intent(
        self,
    ) -> None:
        connection = FakePostgresConnection()

        repository = PostgresSettingsDataResetRepository(connection)
        with patch.object(repository, "_validate_guard"):
            repository.reset_bank_transaction_data(
                expected_impact_fingerprint="a" * 64,
                recovery_receipt_id="00000000-0000-0000-0000-000000000001",
                job_id="job-1",
                actor_id="YNSYLP005",
                reason="管理员重置银行流水域数据",
            )

        import_file_sql = [
            " ".join(sql.lower().split())
            for sql, _params in connection.executed
            if "app.import_files" in sql.lower()
        ]
        self.assertTrue(import_file_sql)
        self.assertTrue(
            any("set status = 'deleting'" in sql for sql in import_file_sql)
        )
        self.assertTrue(all("import_batch_id" not in sql for sql in import_file_sql))

    def test_postgres_store_rejects_legacy_gridfs_reference(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FakePostgresConnection()
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection)

            legacy_uri = "gridfs://import_file_blobs/legacy-gridfs-id"

            with self.assertRaisesRegex(RuntimeError, "Legacy GridFS file access is disabled"):
                store.read_import_file(legacy_uri)
            self.assertEqual(store.delete_import_files([legacy_uri, legacy_uri]), 1)
            self.assertIn("update app.import_files set status = 'deleted'", connection.executed[-1][0])


if __name__ == "__main__":
    unittest.main()
