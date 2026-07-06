from __future__ import annotations

from http import HTTPStatus
import unittest

from fin_ops_platform.services.output_invoice_collection_read_application_service import (
    OutputInvoiceCollectionReadApplicationService,
)
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionError


class OutputInvoiceCollectionReadApplicationServiceTests(unittest.TestCase):
    def test_rows_use_sql_read_model_and_apply_lifecycle_overlay(self) -> None:
        query_service = QueryServiceStub()
        service = OutputInvoiceCollectionReadApplicationService(
            query_service=query_service,
            sql_rows_provider=lambda _query: {
                "rows": [{"id": "row-page"}],
                "pagination": {"page": 1, "pageSize": 20, "total": 1},
                "summary": {"invoiceCount": 999},
                "read_model_status": "fresh",
            },
            sql_all_rows_provider=lambda _query: {
                "rows": [{"id": "row-all-1"}, {"id": "row-all-2"}],
                "read_model_status": "fresh",
                "read_model_scope_key": "2026-05",
            },
        )

        payload = service.rows({"page": ["1"]}, tenant_id="tenant-a")

        self.assertEqual(query_service.live_rows_calls, 0)
        self.assertEqual(payload["rows"], [{"id": "row-page", "overlayTenant": "tenant-a"}])
        self.assertEqual(payload["summary"], {"invoiceCount": 2})

    def test_filter_options_preserve_refreshing_payload_without_live_fallback(self) -> None:
        query_service = QueryServiceStub()
        service = OutputInvoiceCollectionReadApplicationService(
            query_service=query_service,
            sql_all_rows_provider=lambda _query: {
                "rows": [],
                "read_model_status": "refreshing",
                "read_model_scope_key": "all",
            },
        )

        payload = service.filter_options({})

        self.assertEqual(query_service.filter_options_for_rows_calls, 0)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["readModelStatus"], "refreshing")

    def test_export_rejects_refreshing_read_model(self) -> None:
        service = OutputInvoiceCollectionReadApplicationService(
            query_service=QueryServiceStub(),
            sql_all_rows_provider=lambda _query: {
                "rows": [],
                "read_model_status": "refreshing",
                "read_model_scope_key": "all",
            },
        )

        with self.assertRaises(OutputInvoiceCollectionError) as raised:
            service.export({})

        self.assertEqual(raised.exception.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(raised.exception.details["readModelStatus"], "refreshing")


class QueryServiceStub:
    def __init__(self) -> None:
        self.live_rows_calls = 0
        self.filter_options_for_rows_calls = 0

    def list_rows(self, **_kwargs: object) -> dict[str, object]:
        self.live_rows_calls += 1
        return {"rows": [], "pagination": {"total": 0}}

    def filter_options(self, **_kwargs: object) -> dict[str, object]:
        return {"fields": []}

    def filter_options_for_rows(self, **_kwargs: object) -> dict[str, object]:
        self.filter_options_for_rows_calls += 1
        return {"fields": []}

    def apply_lifecycle_overlays_to_rows(self, rows: list[dict[str, object]], *, tenant_id: str) -> list[dict[str, object]]:
        return [{**row, "overlayTenant": tenant_id} for row in rows]

    def summary_for_rows(self, rows: list[dict[str, object]]) -> dict[str, object]:
        return {"invoiceCount": len(rows)}

    def export_preview_for_rows(self, *, rows: list[dict[str, object]]) -> dict[str, object]:
        return {"row_count": len(rows), "read_model_status": "fresh", "readModelStatus": "fresh"}

    def export_for_rows(self, rows: list[dict[str, object]]) -> tuple[str, bytes]:
        return "output.xlsx", str(len(rows)).encode()

    def row_relation_details(self, row_id: str, *, kind: str) -> dict[str, object]:
        return {"rowId": row_id, "kind": kind}


if __name__ == "__main__":
    unittest.main()
