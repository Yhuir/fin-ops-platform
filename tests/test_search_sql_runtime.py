from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.workbench_canonical_query import (
    PostgresWorkbenchCanonicalQueryRepository,
)
from fin_ops_platform.services.search_read_model_refresh import (
    SearchReadModelRefreshService,
)
from fin_ops_platform.services.search_sql_projection import SearchSqlProjectionBuilder
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent

from postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class RecordingSearchRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []

    def search_index_scope_summary(self, *, month: str) -> None:
        _ = month
        return None

    def save_search_index_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object],
    ) -> None:
        self.saved.append(
            {
                "scope_key": scope_key,
                "rows": rows,
                "source_versions": source_versions,
            }
        )


class CanonicalSearchRepository:
    def list_workbench_search_scope_keys(self) -> list[str]:
        return ["2026-06", "bad", "2026-05"]

    def workbench_search_source_versions(
        self,
        *,
        scope_key: str,
    ) -> dict[str, object]:
        return {
            "search_index_schema_version": "2026-07-search-canonical-v1",
            "scope_key": scope_key,
            "relation_membership_version": "relations-v2",
        }

    def list_canonical_search_rows(
        self,
        *,
        scope_key: str,
    ) -> list[dict[str, object]]:
        return [
            {
                "row": {
                    "id": "bank-1",
                    "type": "bank",
                    "counterparty_name": "供应商甲",
                    "trade_time": f"{scope_key}-10",
                    "debit_amount": "88.00",
                    "remark": "测试",
                },
                "zone_hint": "paired",
                "group_id": "case-1",
                "project_names": ["项目甲"],
            }
        ]


class QueueRecorder:
    def __init__(self, *, current: bool = True) -> None:
        self.current = current
        self.completed: list[dict[str, object]] = []

    def read_model_refresh_is_current(self, **_kwargs: object) -> bool:
        return self.current

    def complete_read_model_refresh(self, **kwargs: object) -> None:
        self.completed.append(dict(kwargs))


class SearchSqlRuntimeTests(unittest.TestCase):
    def test_canonical_search_scan_uses_background_statement_timeout(self) -> None:
        class RecordingRepository(PostgresWorkbenchCanonicalQueryRepository):
            def __init__(self) -> None:
                self.statement_timeout_seconds = 0

            def _in_snapshot(
                self,
                _operation: object,
                *,
                statement_timeout_seconds: int = 2,
            ) -> list[dict[str, object]]:
                self.statement_timeout_seconds = statement_timeout_seconds
                return []

        repository = RecordingRepository()

        self.assertEqual(
            repository.list_canonical_search_rows(scope_key="2026-06"),
            [],
        )
        self.assertEqual(repository.statement_timeout_seconds, 90)

    def test_projection_uses_only_canonical_repository_contract(self) -> None:
        repository = RecordingSearchRepository()
        builder = SearchSqlProjectionBuilder(
            connection=object(),
            read_model_repository=repository,
            canonical_query_repository=CanonicalSearchRepository(),
        )

        self.assertEqual(
            builder.list_search_scope_shards("all"),
            ["2026-06", "2026-05"],
        )
        result = builder.rebuild_search_index_scope("2026-06")

        self.assertEqual(result["row_count"], 1)
        self.assertEqual(repository.saved[0]["scope_key"], "2026-06")
        row = repository.saved[0]["rows"][0]
        self.assertEqual(row["row_id"], "bank-1")
        self.assertEqual(row["status"], "paired")
        self.assertEqual(
            repository.saved[0]["source_versions"]["relation_membership_version"],
            "relations-v2",
        )

    def test_stale_event_cannot_rebuild_or_complete_scope(self) -> None:
        queue = QueueRecorder(current=False)

        class FailBuilder:
            def rebuild_search_index_scope(self, _scope_key: str) -> None:
                raise AssertionError("stale Search event must not rebuild")

        service = SearchReadModelRefreshService(
            projection_builder=FailBuilder(),
            queue_repository=queue,
        )
        result = service.handle_runtime_event(
            RuntimeQueueEvent(
                event_id="event-1",
                tenant_id="default",
                event_type="search.read_model.refresh",
                aggregate_type="read_model",
                aggregate_id="2026-06",
                scope_type="search",
                scope_key="2026-06",
                dedupe_key="search:2026-06",
                payload={"source_version": 1},
                attempts=0,
                status="processing",
                source_version=1,
            )
        )

        self.assertEqual(result["skip_reason"], "stale_source_version")
        self.assertEqual(queue.completed, [])

    def test_search_runtime_has_no_retired_workbench_or_pending_source(self) -> None:
        source = Path(
            "backend/src/fin_ops_platform/services/search_sql_projection.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("read_model.workbench_rows", source)
        self.assertNotIn("read_model.workbench_group_rows", source)
        self.assertNotIn("pending_invoice", source)


class SearchCanonicalPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(
                database_url=self.database_url,
                pool_enabled=False,
            )
        )
        self.repository = PostgresWorkbenchCanonicalQueryRepository(
            self.connection
        )

    def test_shards_and_versions_follow_canonical_membership(self) -> None:
        with self.connection.transaction() as transaction:
            transaction.execute(
                """
                insert into app.bank_transactions(
                    legacy_mongo_id, account_no, txn_direction,
                    counterparty_name_raw, amount, signed_amount,
                    txn_date, txn_month, status
                )
                values (
                    'bank-search-1', '62220001', 'outflow',
                    '供应商甲', 88, -88,
                    '2026-06-10', '2026-06-01', 'active'
                )
                """
            )

        self.assertIn(
            "2026-06",
            self.repository.list_workbench_search_scope_keys(),
        )
        before = self.repository.workbench_search_source_versions(
            scope_key="2026-06"
        )

        with self.connection.transaction() as transaction:
            transaction.execute(
                """
                insert into app.workbench_pair_relations(
                    case_id, relation_mode, status, month_scope,
                    row_ids, row_types
                )
                values (
                    'case-search-1', 'manual', 'active', '2026-06-01',
                    array['bank-search-1'], array['bank']
                )
                """
            )

        after = self.repository.workbench_search_source_versions(
            scope_key="2026-06"
        )
        self.assertNotEqual(
            before["relation_membership_version"],
            after["relation_membership_version"],
        )


if __name__ == "__main__":
    unittest.main()
