from __future__ import annotations

import unittest

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import (
    InputInvoiceUsageCanonicalQueryService,
)
from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageQueryService,
)
from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    PostgresInputInvoiceUsageQueryRepository,
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
            require_fresh_relations=False,
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


if __name__ == "__main__":
    unittest.main()
