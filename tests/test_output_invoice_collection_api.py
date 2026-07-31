from __future__ import annotations

from http import HTTPStatus
import unittest
from typing import Any

from fin_ops_platform.app.routes_output_invoice_collections import (
    OutputInvoiceCollectionApiRoutes,
)
from fin_ops_platform.services.output_invoice_collection_service import (
    OutputInvoiceCollectionError,
)


class RecordingQueryService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, str]] = []
        self.error_on: str | None = None

    def _record(self, name: str, value: object, tenant_id: str) -> dict[str, Any]:
        self.calls.append((name, value, tenant_id))
        if self.error_on == name:
            raise OutputInvoiceCollectionError(
                "output_invoice_collection_invalid_request",
                "invalid request",
            )
        return {"source": name}

    def rows(self, query: object, *, tenant_id: str) -> dict[str, Any]:
        return self._record("rows", query, tenant_id)

    def filter_options(self, query: object, *, tenant_id: str) -> dict[str, Any]:
        return self._record("filter_options", query, tenant_id)

    def export_preview(self, query: object, *, tenant_id: str) -> dict[str, Any]:
        return self._record("export_preview", query, tenant_id)

    def export(self, query: object, *, tenant_id: str) -> tuple[str, bytes]:
        self._record("export", query, tenant_id)
        return "销项发票收款情况.xlsx", b"xlsx"

    def invoice_detail(self, invoice_id: str, *, tenant_id: str) -> dict[str, Any]:
        return self._record("invoice_detail", invoice_id, tenant_id)

    def bank_transaction_detail(
        self,
        bank_transaction_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        return self._record("bank_transaction_detail", bank_transaction_id, tenant_id)

    def relation_details(
        self,
        row_id: str,
        query: object,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        return self._record("relation_details", (row_id, query), tenant_id)


class OutputInvoiceCollectionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RecordingQueryService()
        self.routes = OutputInvoiceCollectionApiRoutes(
            query_service=self.service,
            json_response=lambda status, payload: {
                "status": int(status),
                "payload": payload,
            },
            xlsx_response=lambda filename, content: {
                "filename": filename,
                "content": content,
            },
            error_response=lambda exc: {
                "status": int(exc.status_code),
                "error": exc.error_code,
            },
        )

    def test_all_read_only_routes_dispatch_to_the_canonical_query_service(self) -> None:
        cases = [
            ("rows", "/api/output-invoice-collections/rows"),
            ("filter_options", "/api/output-invoice-collections/filter-options"),
            ("export_preview", "/api/output-invoice-collections/export-preview"),
            ("export", "/api/output-invoice-collections/export"),
            (
                "invoice_detail",
                "/api/output-invoice-collections/invoices/invoice%2F1/detail",
            ),
            (
                "bank_transaction_detail",
                "/api/output-invoice-collections/bank-transactions/bank%2F1/detail",
            ),
            (
                "relation_details",
                "/api/output-invoice-collections/rows/row%2F1/relation-details",
            ),
        ]

        for expected_call, path in cases:
            with self.subTest(path=path):
                response = self.routes.route(
                    "GET",
                    path,
                    {"kind": ["invoice"]},
                    None,
                    None,
                )
                self.assertIsNotNone(response)
                self.assertEqual(self.service.calls[-1][0], expected_call)
                self.assertEqual(self.service.calls[-1][2], "default")

        self.assertEqual(response, {"status": 200, "payload": {"source": "relation_details"}})

    def test_removed_mutation_and_legacy_routes_are_not_owned(self) -> None:
        removed = [
            ("GET", "/api/output-invoice-collections/status-rules"),
            ("GET", "/api/output-invoice-collections/receipts/history"),
            ("POST", "/api/output-invoice-collections/receipt-preview"),
            ("PUT", "/api/output-invoice-collections/rows/row-1/collection-status"),
            ("POST", "/api/output-invoice-collections/red-invoice-relations"),
            ("POST", "/api/output-invoice-collections/receipts"),
        ]

        for method, path in removed:
            with self.subTest(path=path):
                self.assertIsNone(self.routes.route(method, path, {}, "{}", None))

        self.assertEqual(self.service.calls, [])

    def test_read_auth_error_short_circuits_without_querying(self) -> None:
        routes = OutputInvoiceCollectionApiRoutes(
            query_service=self.service,
            resolve_read_session=lambda _headers: (
                None,
                {"status": int(HTTPStatus.UNAUTHORIZED)},
            ),
            json_response=lambda status, payload: (status, payload),
            xlsx_response=lambda filename, content: (filename, content),
            error_response=lambda exc: exc.error_code,
        )

        response = routes.route(
            "GET",
            "/api/output-invoice-collections/rows",
            {},
            None,
            {},
        )

        self.assertEqual(response, {"status": 401})
        self.assertEqual(self.service.calls, [])

    def test_domain_error_is_mapped_by_the_http_error_port(self) -> None:
        self.service.error_on = "rows"

        response = self.routes.route(
            "GET",
            "/api/output-invoice-collections/rows",
            {},
            None,
            None,
        )

        self.assertEqual(
            response,
            {
                "status": 400,
                "error": "output_invoice_collection_invalid_request",
            },
        )


if __name__ == "__main__":
    unittest.main()
