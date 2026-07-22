from __future__ import annotations

from http import HTTPStatus
import unittest

from fin_ops_platform.app.routes_input_invoice_usage import InputInvoiceUsageApiRoutes
from fin_ops_platform.services.output_invoice_collection_read_application_service import (
    OutputInvoiceCollectionReadApplicationService,
)
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionError


class InvoiceUsageReadLiveFallbackGuardTests(unittest.TestCase):
    def test_input_usage_read_routes_fail_closed_when_sql_payload_is_missing(self) -> None:
        query_service = ExplodingInputUsageQueryService()
        routes = InputInvoiceUsageApiRoutes(
            invoice_detail_loader=query_service.invoice_detail,
            bank_transaction_detail_loader=query_service.bank_transaction_detail,
            oa_detail_loader=query_service.oa_detail,
            payment_status_rules_loader=query_service.payment_status_rules,
            rows_from_sql_read_model=lambda _query: None,
            filter_options_from_sql_read_model=lambda _query: None,
            relation_details_from_sql_read_model=lambda _row_id, _query: None,
            export_service=object(),
            resolve_read_session=lambda *_args, **_kwargs: (None, None),
            export_query_kwargs=lambda _query: {},
            export_error_response=lambda exc: exc,
            record_export_download=lambda *_args: None,
            xlsx_response=lambda filename, content: (filename, content),
            app_settings_service=object(),
            load_json_body=lambda _body: ({}, None),
            payment_rules_error_response=lambda exc: exc,
            json_response=lambda status, payload: (status, payload),
            input_usage_error_response=lambda exc: exc,
        )

        rows_status, rows_payload = routes.rows({"month": ["2026-05"]})
        filters_status, filters_payload = routes.filter_options({"month": ["2026-05"]})
        details_status, details_payload = routes.relation_details("usage-row-1", {"kind": ["oa"]})

        self.assertEqual(query_service.calls, [])
        self.assertEqual(rows_status, HTTPStatus.ACCEPTED)
        self.assertEqual(rows_payload["read_model_status"], "refreshing")
        self.assertEqual(rows_payload["readModelStatus"], "refreshing")
        self.assertEqual(rows_payload["read_model_scope_key"], "2026-05")
        self.assertEqual(filters_status, HTTPStatus.ACCEPTED)
        self.assertEqual(filters_payload["readModelStatus"], "refreshing")
        self.assertEqual(details_status, HTTPStatus.ACCEPTED)
        self.assertEqual(details_payload["readModelStatus"], "refreshing")
        self.assertEqual(details_payload["detailAvailable"], False)

    def test_output_collection_read_application_fails_closed_when_sql_payload_is_missing(self) -> None:
        query_service = ExplodingOutputCollectionQueryService()
        service = OutputInvoiceCollectionReadApplicationService(
            query_service=query_service,
            allow_live_fallback=False,
        )

        rows_payload = service.rows({"month": ["2026-05"]}, tenant_id="tenant-a")
        filters_payload = service.filter_options({"month": ["2026-05"]}, tenant_id="tenant-a")
        preview_payload = service.export_preview({"month": ["2026-05"]}, tenant_id="tenant-a")
        details_payload = service.relation_details("collection-row-1", {"kind": ["invoice"]})

        with self.assertRaises(OutputInvoiceCollectionError) as raised:
            service.export({"month": ["2026-05"]}, tenant_id="tenant-a")

        self.assertEqual(query_service.calls, [])
        for payload in (rows_payload, filters_payload, preview_payload):
            self.assertEqual(payload["read_model_status"], "refreshing")
            self.assertEqual(payload["readModelStatus"], "refreshing")
            self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(details_payload["readModelStatus"], "refreshing")
        self.assertEqual(details_payload["detailAvailable"], False)
        self.assertEqual(raised.exception.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(raised.exception.details["readModelStatus"], "refreshing")


class ExplodingInputUsageQueryService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_rows(self, **_kwargs: object) -> dict[str, object]:
        self.calls.append("list_rows")
        raise AssertionError("input usage rows must not use live query fallback")

    def filter_options(self, **_kwargs: object) -> dict[str, object]:
        self.calls.append("filter_options")
        raise AssertionError("input usage filter options must not use live query fallback")

    def row_relation_details(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        self.calls.append("row_relation_details")
        raise AssertionError("input usage relation details must not use live query fallback")

    def invoice_detail(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        self.calls.append("invoice_detail")
        raise AssertionError("input usage rows test must not call invoice detail")

    def bank_transaction_detail(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        self.calls.append("bank_transaction_detail")
        raise AssertionError("input usage rows test must not call bank detail")

    def oa_detail(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        self.calls.append("oa_detail")
        raise AssertionError("input usage rows test must not call oa detail")

    def payment_status_rules(self) -> dict[str, object]:
        self.calls.append("payment_status_rules")
        raise AssertionError("input usage rows test must not call payment rules")


class ExplodingOutputCollectionQueryService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_rows(self, **_kwargs: object) -> dict[str, object]:
        self.calls.append("list_rows")
        raise AssertionError("output collection rows must not use live query fallback")

    def filter_options(self, **_kwargs: object) -> dict[str, object]:
        self.calls.append("filter_options")
        raise AssertionError("output collection filter options must not use live query fallback")

    def export_preview(self, **_kwargs: object) -> dict[str, object]:
        self.calls.append("export_preview")
        raise AssertionError("output collection export preview must not use live query fallback")

    def export(self, **_kwargs: object) -> tuple[str, bytes]:
        self.calls.append("export")
        raise AssertionError("output collection export must not use live query fallback")

    def row_relation_details(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        self.calls.append("row_relation_details")
        raise AssertionError("output collection relation details must not use live query fallback")


if __name__ == "__main__":
    unittest.main()
