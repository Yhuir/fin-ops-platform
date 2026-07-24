from __future__ import annotations

import json
import unittest

from fin_ops_platform.services.invoice_usage_collection_source_versions import (
    input_invoice_usage_source_versions,
    invoice_relation_dependency_status,
)
from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresReadModelRepository,
)
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class InvoiceUsageCollectionFreshnessPostgresIntegrationTests(unittest.TestCase):
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
        self.repository = PostgresReadModelRepository(self.connection)

    def test_canonical_invoice_change_invalidates_only_affected_scope(self) -> None:
        first_updated_at = self._insert_input_invoice(
            legacy_mongo_id="invoice-one",
            invoice_no="1001",
            updated_at="2026-07-24 01:00:00+00",
        )
        source_versions = {
            **input_invoice_usage_source_versions(),
            "invoice_usage_source_row_count": 1,
            "invoice_usage_source_updated_at": first_updated_at,
            "workbench_relation_source_versions": {
                "relation_generation": 1,
            },
        }
        self.connection.execute(
            """
            insert into read_model.input_invoice_usage_scopes(
                scope_key,
                scope_month,
                row_count,
                cache_status,
                source_versions
            )
            values ('2026-07', '2026-07-01', 1, 'fresh', %s::jsonb)
            """,
            (json.dumps(source_versions),),
        )

        initial_state = self.repository.input_invoice_usage_scope_source_versions(
            scope_key="all",
        )
        initial_dependency = invoice_relation_dependency_status(
            scope_state=initial_state,
            relation_state=self._relation_state(),
            base_source_versions=input_invoice_usage_source_versions(),
        )
        self.assertEqual(initial_dependency["status"], "fresh")

        self._insert_input_invoice(
            legacy_mongo_id="invoice-two",
            invoice_no="1002",
            updated_at="2026-07-24 02:00:00+00",
        )
        changed_state = self.repository.input_invoice_usage_scope_source_versions(
            scope_key="all",
        )
        changed_dependency = invoice_relation_dependency_status(
            scope_state=changed_state,
            relation_state=self._relation_state(),
            base_source_versions=input_invoice_usage_source_versions(),
        )

        self.assertEqual(
            changed_state["canonical_source_versions_by_scope"]["2026-07"][
                "invoice_usage_source_row_count"
            ],
            2,
        )
        self.assertEqual(changed_dependency["status"], "refreshing")
        self.assertEqual(
            changed_dependency["refresh_scope_keys"],
            ["2026-07"],
        )

    def _insert_input_invoice(
        self,
        *,
        legacy_mongo_id: str,
        invoice_no: str,
        updated_at: str,
    ) -> str:
        row = self.connection.fetch_one(
            """
            insert into app.invoices(
                legacy_mongo_id,
                invoice_type,
                invoice_no,
                invoice_date,
                invoice_month,
                amount,
                signed_amount,
                total_with_tax,
                status,
                updated_at
            )
            values (
                %s,
                'input',
                %s,
                '2026-07-10',
                '2026-07-01',
                100,
                100,
                106,
                'active',
                %s::timestamptz
            )
            returning updated_at::text as updated_at
            """,
            (legacy_mongo_id, invoice_no, updated_at),
        )
        return str((row or {})["updated_at"])

    @staticmethod
    def _relation_state() -> dict[str, object]:
        return {
            "status": "fresh",
            "read_model_scope_source_versions": {
                "2026-07": {"relation_generation": 1},
            },
            "refresh_scope_keys": [],
            "stale_reasons": [],
        }


if __name__ == "__main__":
    unittest.main()
