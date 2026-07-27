from __future__ import annotations

from contextlib import contextmanager
from time import monotonic
import unittest
from unittest.mock import patch

from fin_ops_platform.services.postgres_repositories import (
    workbench_canonical_query as canonical_query,
)
from fin_ops_platform.services.postgres_repositories.workbench_canonical_query import (
    PostgresWorkbenchCanonicalQueryRepository,
)
from fin_ops_platform.services.workbench_canonical_rows import (
    WorkbenchCanonicalRowsBuilder,
)
from fin_ops_platform.services.workbench_relation_preview_policy import (
    WorkbenchRelationPreviewSelectionError,
)


class RecordingTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_results: list[list[dict[str, object]]] = []
        self.fetch_one_results: list[dict[str, object] | None] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.calls.append((sql, params))
        return 0

    def fetch_one(
        self, sql: str, params: tuple[object, ...] = ()
    ) -> dict[str, object] | None:
        self.calls.append((sql, params))
        return self.fetch_one_results.pop(0) if self.fetch_one_results else {}

    def fetch_all(
        self, sql: str, params: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        self.calls.append((sql, params))
        return self.fetch_all_results.pop(0) if self.fetch_all_results else []


class RecordingConnection:
    def __init__(self) -> None:
        self.tx = RecordingTransaction()
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self.tx


class WorkbenchCanonicalQueryRepositoryTests(unittest.TestCase):
    def test_initial_page_uses_one_repeatable_read_snapshot_and_fixed_empty_query_count(
        self,
    ) -> None:
        for scope_key in ("all", "2026-07"):
            with self.subTest(scope_key=scope_key):
                connection = RecordingConnection()
                repository = PostgresWorkbenchCanonicalQueryRepository(connection)
                started = monotonic()

                payload = repository.get_workbench_initial_page(
                    scope_key=scope_key
                )
                duration_ms = (monotonic() - started) * 1000

                self.assertEqual(connection.transaction_count, 1)
                self.assertEqual(len(connection.tx.calls), 10)
                self.assertEqual(
                    connection.tx.calls[0][0],
                    "set transaction isolation level repeatable read read only",
                )
                self.assertEqual(
                    connection.tx.calls[1][0],
                    "set local statement_timeout = '2s'",
                )
                self.assertEqual(payload["paired"]["groups"], [])
                self.assertEqual(payload["unpaired"]["groups"], [])
                self.assertNotIn("read_model_status", payload)
                self.assertLess(duration_ms, 100)

    def test_public_payload_recursively_removes_legacy_runtime_fields(self) -> None:
        connection = RecordingConnection()
        repository = PostgresWorkbenchCanonicalQueryRepository(connection)

        with patch.object(
            PostgresWorkbenchCanonicalQueryRepository,
            "_initial_page",
            return_value={
                "read_model_status": "fresh",
                "nested": {
                    "read_model_version": 7,
                    "active_generation_id": "generation-7",
                    "source_versions": {"oa": 1},
                    "refresh_enqueued": True,
                    "status": "active",
                },
            },
        ):
            payload = repository.get_workbench_initial_page(scope_key="all")

        self.assertEqual(payload, {"nested": {"status": "active"}})

    def test_groups_page_uses_limit_offset_and_fixed_query_count(self) -> None:
        connection = RecordingConnection()
        repository = PostgresWorkbenchCanonicalQueryRepository(connection)

        payload = repository.get_workbench_groups_page(
            scope_key="all",
            zone="unpaired",
            page=4,
            page_size=20,
            search="供应商",
            sort="bank:desc",
            detail_level="summary",
        )

        self.assertEqual(len(connection.tx.calls), 4)
        page_sql, page_params = connection.tx.calls[-1]
        self.assertIn("limit %s offset %s", page_sql.lower())
        self.assertEqual(page_params[-2:], (21, 60))
        self.assertEqual(payload["page"], 4)
        self.assertEqual(payload["page_size"], 20)
        self.assertEqual(payload["groups"], [])

    def test_maximum_page_hydration_is_batched_not_per_group(self) -> None:
        connection = RecordingConnection()
        descriptors = [
            {
                "internal_key": f"row:oa:oa-{index}",
                "detail_key": f"oa-{index}",
                "group_kind": "unpaired",
                "zone": "unpaired",
                "member_ids": [f"oa-{index}"],
            }
            for index in range(200)
        ]
        connection.tx.fetch_all_results = [descriptors]
        repository = PostgresWorkbenchCanonicalQueryRepository(connection)

        with patch.object(
            PostgresWorkbenchCanonicalQueryRepository,
            "_hydrate_groups",
            return_value=[],
        ) as hydrate:
            repository.get_workbench_groups_page(
                scope_key="2026-07",
                zone="unpaired",
                page=1,
                page_size=200,
            )

        self.assertEqual(len(connection.tx.calls), 4)
        hydrate.assert_called_once()
        self.assertEqual(len(hydrate.call_args.kwargs["descriptors"]), 200)

    def test_group_and_row_detail_have_fixed_selector_query_counts(self) -> None:
        group_connection = RecordingConnection()
        group_repository = PostgresWorkbenchCanonicalQueryRepository(
            group_connection
        )
        row_connection = RecordingConnection()
        row_repository = PostgresWorkbenchCanonicalQueryRepository(row_connection)

        group = group_repository.get_workbench_group_detail(
            scope_key="all",
            zone="paired",
            group_id="case:missing",
            detail_key="missing",
        )
        row = row_repository.get_workbench_row_detail(
            scope_key="all",
            row_id="bank-missing",
        )

        self.assertIsNone(group)
        self.assertIsNone(row)
        self.assertEqual(len(group_connection.tx.calls), 3)
        self.assertEqual(len(row_connection.tx.calls), 3)

    def test_twenty_row_preview_hydrates_each_canonical_kind_once(self) -> None:
        row_ids = [f"oa-{index}" for index in range(20)]
        connection = RecordingConnection()
        connection.tx.fetch_all_results = [
            [
                {
                    "internal_key": "selection",
                    "detail_key": "selection",
                    "group_kind": "unpaired",
                    "zone": "unpaired",
                    "member_ids": row_ids,
                }
            ]
        ]
        repository = PostgresWorkbenchCanonicalQueryRepository(connection)
        oa_rows = [
            {"id": row_id, "type": "oa", "source_kind": "oa"}
            for row_id in row_ids
        ]
        grouped = {
            "paired": {"groups": []},
            "unpaired": {
                "groups": [
                    {
                        "group_id": "unpaired:selection",
                        "oa_rows": oa_rows,
                        "bank_rows": [],
                        "invoice_rows": [],
                    }
                ]
            },
        }

        with (
            patch.object(
                WorkbenchCanonicalRowsBuilder,
                "_oa_projection_rows_by_sql_ids",
                return_value=oa_rows,
            ) as oa_loader,
            patch.object(
                WorkbenchCanonicalRowsBuilder,
                "_bank_rows_by_ids",
                return_value=[],
            ) as bank_loader,
            patch.object(
                WorkbenchCanonicalRowsBuilder,
                "_invoice_rows_by_ids",
                return_value=[],
            ) as invoice_loader,
            patch.object(
                WorkbenchCanonicalRowsBuilder,
                "_group_payload",
                return_value=grouped,
            ) as group_payload,
            patch.object(
                PostgresWorkbenchCanonicalQueryRepository,
                "_oa_attachment_context_ids",
                return_value=[],
            ),
        ):
            payload = repository.get_workbench_relation_preview_selection(
                scope_key="all",
                row_ids=row_ids,
            )

        self.assertEqual(payload["selected_row_ids"], row_ids)
        self.assertEqual(len(payload["selected_rows"]), 20)
        oa_loader.assert_called_once()
        bank_loader.assert_called_once()
        invoice_loader.assert_called_once()
        group_payload.assert_called_once()
        self.assertEqual(len(connection.tx.calls), 3)

    def test_transaction_selection_validation_is_one_bounded_canonical_query(
        self,
    ) -> None:
        transaction = RecordingTransaction()
        transaction.fetch_all_results = [
            [
                {"row_id": "bank-1", "pane": "bank"},
                {"row_id": "oa-1", "pane": "oa"},
            ]
        ]
        repository = PostgresWorkbenchCanonicalQueryRepository(transaction)

        row_types = (
            repository.validate_workbench_relation_selection_in_current_transaction(
                scope_key="2026-07",
                row_ids=["oa-1", "bank-1"],
            )
        )

        self.assertEqual(row_types, {"bank-1": "bank", "oa-1": "oa"})
        self.assertEqual(len(transaction.calls), 1)
        sql, params = transaction.calls[0]
        self.assertIn("from canonical_groups groups", sql.lower())
        self.assertEqual(params[-1], ["oa-1", "bank-1"])

    def test_transaction_selection_validation_rejects_missing_canonical_identity(
        self,
    ) -> None:
        transaction = RecordingTransaction()
        transaction.fetch_all_results = [[{"row_id": "oa-1", "pane": "oa"}]]
        repository = PostgresWorkbenchCanonicalQueryRepository(transaction)

        with self.assertRaises(WorkbenchRelationPreviewSelectionError):
            repository.validate_workbench_relation_selection_in_current_transaction(
                scope_key="all",
                row_ids=["oa-1", "bank-1"],
            )

    def test_query_source_uses_only_canonical_facts_and_active_relations(self) -> None:
        source = canonical_query._CANONICAL_GROUPS_CTE.lower()

        for table in (
            "app.oa_applications",
            "app.bank_transactions",
            "app.invoices",
            "app.etc_business_batches",
            "app.etc_batch_invoice_links",
            "app.etc_invoices",
            "app.workbench_pair_relations",
        ):
            self.assertIn(table, source)
        self.assertIn("where relation.status = 'active'", source)
        self.assertIn("where link.link_status = 'active'", source)
        self.assertIn("from etc_link_batch_keys link", source)
        self.assertIn("from etc_business_batch_keys business", source)
        self.assertNotIn("read_model.workbench", source)
        self.assertNotIn("workbench_generations", source)
        self.assertNotIn("active_generation", source)


if __name__ == "__main__":
    unittest.main()
