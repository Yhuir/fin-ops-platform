import unittest

from fin_ops_platform.domain.enums import BatchType, IntegrationSyncStatus
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.integrations import IntegrationHubService


class IntegrationHubServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.import_service = ImportNormalizationService()
        self.audit_service = AuditTrailService()
        self.integration_service = IntegrationHubService(
            self.import_service,
            self.audit_service,
        )

    def test_sync_counterparties_maps_existing_counterparty_and_records_run(self) -> None:
        self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "033501",
                    "invoice_no": "OA-MAP-001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )

        run = self.integration_service.sync(scope="counterparties", triggered_by="user_finance_01")
        counterparty = self.import_service.find_counterparty_by_name("Acme Supplies")
        mappings = self.integration_service.list_mappings(object_type="counterparty")

        self.assertEqual(run.status, IntegrationSyncStatus.SUCCEEDED)
        self.assertEqual(counterparty.oa_external_id, "OA-CP-001")
        self.assertEqual(len(mappings), 2)
        self.assertEqual(mappings[0].object_type.value, "counterparty")
        self.assertEqual(self.audit_service.list_entries()[-1].action, "oa_sync_completed")

    def test_sync_all_persists_projects_documents_and_supports_retry_linkage(self) -> None:
        first_run = self.integration_service.sync(scope="all", triggered_by="user_finance_01")
        dashboard = self.integration_service.build_dashboard()
        retry_run = self.integration_service.sync(triggered_by="user_finance_01", retry_run_id=first_run.id)

        self.assertEqual(first_run.status, IntegrationSyncStatus.SUCCEEDED)
        self.assertGreaterEqual(len(dashboard["projects"]), 2)
        self.assertGreaterEqual(len(dashboard["documents"]), 4)
        self.assertGreaterEqual(len(dashboard["runs"]), 1)
        self.assertEqual(retry_run.retry_of_run_id, first_run.id)
        self.assertEqual(retry_run.scope, "all")

    def _confirm(self, batch_type: BatchType, rows: list[dict[str, str]]) -> None:
        preview = self.import_service.preview_import(
            batch_type=batch_type,
            source_name=f"{batch_type.value}.json",
            imported_by="user_finance_01",
            rows=rows,
        )
        self.import_service.confirm_import(preview.id)


if __name__ == "__main__":
    unittest.main()
