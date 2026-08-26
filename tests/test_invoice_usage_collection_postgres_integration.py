from __future__ import annotations

import unittest

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import (
    InputInvoiceUsageCanonicalQueryService,
)
from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageQueryService,
)
from fin_ops_platform.services.output_invoice_collection_canonical_query_service import (
    OutputInvoiceCollectionCanonicalQueryService,
)
from fin_ops_platform.services.output_invoice_collection_service import (
    OutputInvoiceCollectionQueryService,
)
from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    PostgresInputInvoiceUsageQueryRepository,
    PostgresOutputInvoiceCollectionQueryRepository,
)
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class _UnexpectedPaymentRulesProvider:
    def __init__(self) -> None:
        self.evaluate_count = 0

    def payment_status_rules_payload(self, *, can_save: bool = True) -> dict[str, object]:
        del can_save
        return {}

    def rules_source_version(self) -> int:
        return 1

    def evaluate(self, _context: object) -> dict[str, str]:
        self.evaluate_count += 1
        raise AssertionError("row assembly must reuse snapshot payment rules")


class InvoiceUsageCollectionPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )

    def tearDown(self) -> None:
        self.connection.close()
        truncate_test_database(self.database_url)

    def test_rows_reuse_snapshot_payment_rules_without_row_level_settings_reads(
        self,
    ) -> None:
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                seller_name, amount, signed_amount, tax_amount, total_with_tax, status
            ) values (
                'input-snapshot-rule-1', 'input', 'INV-001', '2026-07-31', '2026-07-01',
                '材料供应商', 100, 100, 18, 118, 'pending'
            )
            """
        )
        legacy_provider = _UnexpectedPaymentRulesProvider()
        row_assembler = InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(),
            payment_rules_provider=legacy_provider,
        )

        payload = InputInvoiceUsageCanonicalQueryService(
            repository=PostgresInputInvoiceUsageQueryRepository(self.connection),
            row_assembler=row_assembler,
        ).list_rows(page=1, page_size=20, include_statistics=False)

        self.assertEqual(payload["pagination"]["total"], 1)
        [row] = payload["rows"]
        self.assertEqual(row["invoiceId"], "input-snapshot-rule-1")
        self.assertEqual(row["paymentStatus"]["code"], "pending")
        self.assertEqual(legacy_provider.evaluate_count, 0)

    def test_output_reversal_page_keeps_exact_summary_order_and_supporting_group(self) -> None:
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                seller_name, buyer_name, amount, signed_amount, tax_amount,
                total_with_tax, status
            ) values
                (
                    'output-blue-1', 'output', 'OUT-BLUE-001', '2026-07-10',
                    '2026-07-01', '销售方', '购买方', 100, 100, 18, 118, 'pending'
                ),
                (
                    'output-red-1', 'output', 'OUT-RED-001', '2026-07-11',
                    '2026-07-01', '销售方', '购买方', -100, -100, -18, -118, 'pending'
                )
            """
        )
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'output-reversal-1', 'output_invoice_reversal', 'active', 1,
                '2026-07-01', array['output-blue-1', 'output-red-1'],
                array['output_invoice', 'output_invoice'], '{}'::jsonb,
                '{}'::jsonb, '{}'::jsonb
            )
            """
        )

        repository = PostgresOutputInvoiceCollectionQueryRepository(self.connection)
        snapshot = repository.load_page(
            page=1,
            page_size=1,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            month="2026-07",
            filters=[],
            sort_field="total_with_tax",
            sort_direction="desc",
        )

        self.assertEqual(snapshot.pagination, {"page": 1, "pageSize": 1, "total": 2})
        self.assertEqual(
            snapshot.summary,
            {
                "invoiceCount": 2,
                "totalWithTax": "0.00",
                "collectedAmount": "0.00",
                "pendingAmount": "0.00",
                "pendingCollectionCount": 0,
                "partialCollectionCount": 0,
            },
        )
        self.assertEqual(
            snapshot.statistics,
            {
                "invoiceCount": 2,
                "incomeBankTransactionCount": 0,
                "blueInvoiceCount": 1,
                "redInvoiceCount": 1,
            },
        )
        self.assertEqual(
            snapshot.statistics["blueInvoiceCount"]
            + snapshot.statistics["redInvoiceCount"],
            snapshot.statistics["invoiceCount"],
        )
        self.assertEqual(
            [group["primary"].id for group in snapshot.groups],
            ["output-blue-1"],
        )
        self.assertEqual(snapshot.groups[0]["status_code"], "reversed_by_red")
        self.assertEqual(
            [group["primary"].id for group in snapshot.supporting_groups],
            ["output-red-1"],
        )
        self.assertEqual(snapshot.supporting_groups[0]["status_code"], "reverses_blue")

        query_service = OutputInvoiceCollectionCanonicalQueryService(
            repository=repository,
            row_assembler=OutputInvoiceCollectionQueryService(
                import_service=ImportNormalizationService(),
            ),
        )
        rows = query_service.list_rows(page=1, page_size=20, month="2026-07")["rows"]
        blue_row = next(row for row in rows if row["invoiceId"] == "output-blue-1")

        details = query_service.relation_details(
            blue_row["id"],
            {"kind": ["invoice"]},
        )

        self.assertEqual(details["rowId"], blue_row["id"])
        self.assertEqual(details["relationCount"], 2)
        self.assertEqual(
            [summary["invoiceId"] for summary in details["summaries"]],
            ["output-blue-1", "output-red-1"],
        )

    def test_output_over_collection_is_collected_with_zero_pending_amount(self) -> None:
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                seller_name, buyer_name, amount, signed_amount, tax_amount,
                total_with_tax, status
            ) values (
                'output-over-collected-1', 'output', 'OUT-OVER-001', '2026-07-10',
                '2026-07-01', '销售方', '购买方', 100, 100, 0, 100, 'pending'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status
            ) values (
                'output-over-collected-bank-1', '62220001', 'inflow', '购买方',
                120, 120, '2026-07-12', '2026-07-01', 'pending'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'output-over-collected-relation-1', 'manual', 'active', 1,
                '2026-07-01',
                array['output-over-collected-1', 'output-over-collected-bank-1'],
                array['output_invoice', 'bank_transaction'], '{}'::jsonb,
                '{}'::jsonb, '{}'::jsonb
            )
            """
        )

        snapshot = PostgresOutputInvoiceCollectionQueryRepository(
            self.connection
        ).load_page(
            page=1,
            page_size=20,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            month="2026-07",
            filters=[],
            sort_field="total_with_tax",
            sort_direction="desc",
        )

        self.assertEqual(snapshot.pagination, {"page": 1, "pageSize": 20, "total": 1})
        self.assertEqual(snapshot.groups[0]["status_code"], "collected")
        self.assertEqual(snapshot.groups[0]["pending_amount"], "0.00")
        self.assertEqual(
            snapshot.summary,
            {
                "invoiceCount": 1,
                "totalWithTax": "100.00",
                "collectedAmount": "120.00",
                "pendingAmount": "0.00",
                "pendingCollectionCount": 0,
                "partialCollectionCount": 0,
            },
        )
        self.assertEqual(
            snapshot.statistics,
            {
                "invoiceCount": 1,
                "incomeBankTransactionCount": 1,
                "blueInvoiceCount": 1,
                "redInvoiceCount": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
