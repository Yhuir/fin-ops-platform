from __future__ import annotations

from contextlib import contextmanager
import unittest

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.services.invoice_relation_query_context import (
    DistributedInvoiceRelationContext,
)
from fin_ops_platform.services.output_invoice_collection_canonical_query_service import (
    OutputInvoiceCollectionCanonicalQueryService,
)
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    InvoiceUsageCollectionCanonicalSnapshot,
    PostgresInputInvoiceUsageQueryRepository,
    PostgresOutputInvoiceCollectionQueryRepository,
    _facet_counts,
)


class RecordingTransaction:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str, _params: object = None) -> None:
        self.statements.append(sql)

    def fetch_one(self, sql: str, _params: object = None) -> dict[str, object]:
        self.statements.append(sql)
        if "from app.app_settings" in sql:
            return {"settings_payload": {}}
        return {}

    def fetch_all(self, sql: str, _params: object = None) -> list[dict[str, object]]:
        self.statements.append(sql)
        return []


class RecordingConnection:
    def __init__(self) -> None:
        self.transactions: list[RecordingTransaction] = []

    @contextmanager
    def transaction(self):
        transaction = RecordingTransaction()
        self.transactions.append(transaction)
        yield transaction


class InputSummaryTransaction(RecordingTransaction):
    def fetch_one(self, sql: str, _params: object = None) -> dict[str, object]:
        self.statements.append(sql)
        if "from app.app_settings" in sql:
            return {"settings_payload": {}}
        if "selected_members as" in sql:
            return {
                "group_rows": [],
                "summary_row": {
                    "row_count": 1,
                    "invoice_count": 2,
                    "total_with_tax": "800.00",
                },
                "facet_rows": [],
            }
        return {}


class StaticTransactionConnection:
    def __init__(self, transaction: RecordingTransaction) -> None:
        self.current = transaction

    @contextmanager
    def transaction(self):
        yield self.current


class CountingImportService:
    def __init__(self) -> None:
        self.calls = 0

    def list_invoices(self, **_kwargs: object) -> list[object]:
        self.calls += 1
        return []


class RecordingOutputRowAssembler:
    def __init__(self) -> None:
        self.candidate_keys: list[str] = []

    def _row_payload(
        self,
        group: dict[str, object],
        candidates: list[dict[str, object]],
        **_kwargs: object,
    ) -> dict[str, object]:
        self.candidate_keys = [
            str(candidate.get("group_key") or "")
            for candidate in candidates
        ]
        return {"invoiceIdentityKey": group["identity_key"]}


class InvoiceUsageCollectionCanonicalQueryTests(unittest.TestCase):
    def test_input_rows_summary_and_facets_share_one_bounded_canonical_snapshot(self) -> None:
        connection = RecordingConnection()
        repository = PostgresInputInvoiceUsageQueryRepository(connection)

        payload = repository.load_page(
            page=1,
            page_size=200,
            keyword="供应商",
            invoice_date_from="2026-01-01",
            invoice_date_to="2026-12-31",
            month="2026-05",
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
            tenant_id="tenant-a",
        )

        self.assertEqual(payload.pagination, {"page": 1, "pageSize": 200, "total": 0})
        self.assertEqual(len(connection.transactions), 1)
        statements = connection.transactions[0].statements
        self.assertEqual(len(statements), 4)
        self.assertEqual(
            statements[0],
            "set transaction isolation level repeatable read read only",
        )
        sql = "\n".join(statements)
        self.assertIn("from app.invoices invoice", sql)
        self.assertIn("from app.workbench_pair_relations relation", sql)
        self.assertIn("where relation.status = 'active'", sql)
        self.assertIn("join app.oa_applications oa", sql)
        self.assertIn("join app.bank_transactions bank", sql)
        self.assertIn("with recursive", sql)
        self.assertIn("relation_reach(root_relation_id, relation_id)", sql)
        self.assertIn("join relation_members neighbour", sql)
        self.assertIn("bool_or(", sql)
        self.assertIn("filtered_rows as materialized", sql)
        self.assertIn("jsonb_agg(", sql)
        self.assertNotIn("read_model.input_invoice_usage", sql)
        self.assertNotIn("read_model.workbench_relation", sql)
        self.assertNotIn("read_model.invoice_lifecycle", sql)

    def test_output_rows_summary_and_facets_share_one_bounded_canonical_snapshot(self) -> None:
        connection = RecordingConnection()
        repository = PostgresOutputInvoiceCollectionQueryRepository(connection)

        payload = repository.load_page(
            page=10,
            page_size=200,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            month="2026-05",
            filters=[],
            sort_field="total_with_tax",
            sort_direction="asc",
            tenant_id="tenant-a",
        )

        self.assertEqual(payload.pagination, {"page": 10, "pageSize": 200, "total": 0})
        self.assertEqual(len(connection.transactions), 1)
        statements = connection.transactions[0].statements
        self.assertEqual(len(statements), 2)
        self.assertEqual(
            statements[0],
            "set transaction isolation level repeatable read read only",
        )
        sql = "\n".join(statements)
        self.assertIn("sum(member.total_with_tax)", sql)
        self.assertIn("bool_or(member.total_with_tax < 0)", sql)
        self.assertIn("from app.workbench_pair_relations relation", sql)
        self.assertIn("where relation.status = 'active'", sql)
        self.assertIn("then 'reversed_by_red'", sql)
        self.assertIn("then 'reverses_blue'", sql)
        self.assertIn("then 'unmatched_red'", sql)
        self.assertNotIn("app.output_invoice_collection_status_overrides", sql)
        self.assertNotIn("receipt_status", sql)
        self.assertNotIn("oa_applications", sql)
        self.assertIn("filtered_rows as materialized", sql)
        self.assertIn("jsonb_agg(", sql)
        self.assertNotIn("read_model.output_invoice_collection", sql)
        self.assertNotIn("read_model.workbench_relation", sql)
        self.assertNotIn("read_model.invoice_lifecycle", sql)

    def test_invalid_month_fails_before_opening_a_snapshot(self) -> None:
        connection = RecordingConnection()
        repository = PostgresInputInvoiceUsageQueryRepository(connection)

        with self.assertRaisesRegex(ValueError, "month must be YYYY-MM or all"):
            repository.load_page(
                page=1,
                page_size=50,
                keyword=None,
                invoice_date_from=None,
                invoice_date_to=None,
                month="2026-13",
                filters=[],
                sort_field="invoice_date",
                sort_direction="desc",
            )

        self.assertEqual(connection.transactions, [])

    def test_input_summary_counts_invoices_not_collapsed_relation_rows(self) -> None:
        transaction = InputSummaryTransaction()
        repository = PostgresInputInvoiceUsageQueryRepository(
            StaticTransactionConnection(transaction)
        )

        payload = repository.load_page(
            page=1,
            page_size=50,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            month="2026-05",
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
        )

        self.assertEqual(payload.summary["invoiceCount"], 2)
        self.assertEqual(payload.summary["totalWithTax"], "800.00")

    def test_invoice_lookup_map_is_reused_across_export_rows(self) -> None:
        import_service = CountingImportService()
        context = DistributedInvoiceRelationContext(import_service=import_service)

        first = context.invoices_by_id(month="all", invoice_type=InvoiceType.INPUT)
        second = context.invoices_by_id(month="all", invoice_type=InvoiceType.INPUT)

        self.assertIs(first, second)
        self.assertEqual(import_service.calls, 1)

    def test_relation_context_returns_the_full_active_connected_component(
        self,
    ) -> None:
        context = DistributedInvoiceRelationContext(
            import_service=CountingImportService(),
            relation_facade=None,
        )
        context.add_distributed_relations(
            [
                {
                    "case_id": "invoice-oa",
                    "row_ids": ["invoice-1", "oa-1"],
                    "row_types": ["invoice", "oa"],
                },
                {
                    "case_id": "oa-bank",
                    "row_ids": ["oa-1", "bank-1"],
                    "row_types": ["oa", "bank"],
                },
            ]
        )

        relations = context.distributed_relations_for_row_ids(["invoice-1"])

        self.assertEqual(
            {relation["case_id"] for relation in relations},
            {"invoice-oa", "oa-bank"},
        )

    def test_output_row_assembly_only_scans_sql_selected_red_pair_candidates(
        self,
    ) -> None:
        assembler = RecordingOutputRowAssembler()
        service = OutputInvoiceCollectionCanonicalQueryService(
            repository=None,
            row_assembler=assembler,
        )
        snapshot = InvoiceUsageCollectionCanonicalSnapshot(
            groups=[
                {
                    "group_key": "current",
                    "identity_key": "invoice:current",
                    "line_items": [],
                    "supporting_group_keys": ["related"],
                }
            ],
            supporting_groups=[
                {
                    "group_key": "related",
                    "identity_key": "invoice:related",
                    "line_items": [],
                },
                {
                    "group_key": "unrelated",
                    "identity_key": "invoice:unrelated",
                    "line_items": [],
                },
            ],
            relations=[],
            transactions=[],
            oa_records=[],
            overlays={},
            pagination={},
            summary={},
            statistics={},
            facet_counts={},
            payment_status_labels={},
        )

        service._rows_from_snapshot(snapshot)

        self.assertEqual(assembler.candidate_keys, ["current", "related"])

    def test_collection_status_facets_use_the_canonical_labels(self) -> None:
        counts = _facet_counts(
            [
                {
                    "field": "collection_status",
                    "value": "pending_collection",
                    "option_count": 1,
                },
                {
                    "field": "collection_status",
                    "value": "reversed_by_red",
                    "option_count": 2,
                },
            ],
            status_labels={
                "pending_collection": "待收款",
                "reversed_by_red": "已被红冲",
            },
        )

        self.assertEqual(
            counts["collection_status"],
            [
                {"value": "pending_collection", "label": "待收款", "count": 1},
                {"value": "reversed_by_red", "label": "已被红冲", "count": 2},
            ],
        )
        self.assertNotIn("receipt_status", counts)


if __name__ == "__main__":
    unittest.main()
