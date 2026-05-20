from __future__ import annotations

from datetime import UTC, datetime

from fin_ops_platform.domain.enums import BatchStatus, BatchType, ImportDecision, InvoiceStatus, InvoiceType
from fin_ops_platform.services.import_file_service import FileImportService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository


class CoreReadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from app.import_batches" in sql and "left join" not in sql:
            return [
                {
                    "legacy_id": "batch_1",
                    "batch_type": BatchType.INPUT_INVOICE.value,
                    "source_name": "input.xlsx",
                    "imported_by": "tester",
                    "row_count": 1,
                    "success_count": 1,
                    "error_count": 0,
                    "duplicate_count": 0,
                    "suspected_duplicate_count": 0,
                    "updated_count": 0,
                    "status": BatchStatus.COMPLETED.value,
                    "imported_at": datetime(2026, 3, 1, tzinfo=UTC),
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "batch_1",
                            "batch_type": BatchType.INPUT_INVOICE.value,
                            "source_name": "input.xlsx",
                            "imported_by": "tester",
                            "row_count": 1,
                            "success_count": 1,
                            "error_count": 0,
                            "status": BatchStatus.COMPLETED.value,
                        }
                    },
                }
            ]
        if "from app.invoices" in sql:
            return [
                {
                    "legacy_id": "invoice_1",
                    "invoice_type": InvoiceType.INPUT.value,
                    "invoice_no": "INV-001",
                    "invoice_date": "2026-03-01",
                    "counterparty_id": "counterparty_1",
                    "counterparty_name": "供应商A",
                    "amount": "100.00",
                    "signed_amount": "100.00",
                    "written_off_amount": "0.00",
                    "currency": "CNY",
                    "legacy_source_batch_id": "batch_1",
                    "workbench_visibility": "visible",
                    "status": InvoiceStatus.PENDING.value,
                    "tags": ["input"],
                    "source_links": [{"source_type": "import", "batch_id": "batch_1"}],
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "invoice_1",
                            "invoice_type": InvoiceType.INPUT.value,
                            "invoice_no": "INV-001",
                            "invoice_date": "2026-03-01",
                            "counterparty": {
                                "id": "counterparty_1",
                                "name": "供应商A",
                                "normalized_name": "供应商A",
                                "counterparty_type": "vendor",
                            },
                            "amount": "100.00",
                            "signed_amount": "100.00",
                            "source_batch_id": "batch_1",
                        }
                    },
                }
            ]
        if "from app.bank_transactions" in sql:
            return []
        if "from app.import_batch_rows" in sql:
            return [
                {
                    "legacy_id": "row_1",
                    "legacy_batch_id": "batch_1",
                    "joined_batch_id": "batch_1",
                    "row_no": 1,
                    "source_record_type": "invoice",
                    "decision": ImportDecision.CREATED.value,
                    "decision_reason": "Ready to create new invoice.",
                    "linked_object_type": "invoice",
                    "linked_object_id": "invoice_1",
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "row_1",
                            "batch_id": "batch_1",
                            "row_no": 1,
                            "source_record_type": "invoice",
                            "decision": ImportDecision.CREATED.value,
                            "decision_reason": "Ready to create new invoice.",
                            "linked_object_type": "invoice",
                            "linked_object_id": "invoice_1",
                            "normalized_row": {
                                "invoice_type": InvoiceType.INPUT.value,
                                "invoice_no": "INV-001",
                                "invoice_date": "2026-03-01",
                                "counterparty_name": "供应商A",
                                "amount": "100.00",
                                "signed_amount": "100.00",
                            },
                        }
                    },
                }
            ]
        if "from app.import_files" in sql:
            return [
                {
                    "legacy_id": "file_1",
                    "session_id": "session_1",
                    "stored_file_path": "/tmp/input.xlsx",
                    "original_filename": "input.xlsx",
                    "template_kind": "invoice_export",
                    "status": "confirmed",
                    "uploaded_by": "tester",
                    "uploaded_at": datetime(2026, 3, 1, tzinfo=UTC),
                    "joined_batch_id": "batch_1",
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "file_1",
                            "file_name": "input.xlsx",
                            "template_code": "invoice_export",
                            "batch_type": BatchType.INPUT_INVOICE.value,
                            "status": "confirmed",
                            "row_count": 1,
                            "success_count": 1,
                            "batch_id": "batch_1",
                            "stored_file_path": "/tmp/input.xlsx",
                            "session_id": "session_1",
                        }
                    },
                }
            ]
        return []


def test_core_repository_loads_domain_snapshots_accepted_by_services() -> None:
    repository = PostgresCoreRepository(CoreReadConnection())

    imports_snapshot = repository.load_imports()
    import_service = ImportNormalizationService.from_snapshot(imports_snapshot)

    assert list(imports_snapshot["batches"]) == ["batch_1"]
    assert import_service.list_invoices()[0].id == "invoice_1"
    assert import_service.list_invoices()[0].source_batch_id == "batch_1"

    file_snapshot = repository.load_file_imports()
    file_service = FileImportService.from_snapshot(import_service, file_snapshot)

    sessions = file_service.snapshot()["sessions"]
    assert sessions["session_1"].files[0].id == "file_1"
    assert sessions["session_1"].files[0].batch_id == "batch_1"
