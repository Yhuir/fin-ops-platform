from __future__ import annotations

import unittest

from fin_ops_platform.services.input_invoice_usage_read_model_fresh_gate_service import (
    InputInvoiceUsageReadModelFreshGateService,
)


class InputInvoiceUsageReadModelFreshGateServiceTests(unittest.TestCase):
    def test_schema_stale_payload_enqueues_refresh_without_marking_fresh(self) -> None:
        enqueued: list[tuple[str, str]] = []
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=RowsRepository(
                {
                    "rows": [{"id": "row-1", "invoice": {}}],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "refresh_status": "fresh",
                    "source_versions": {"schema": "v1"},
                }
            ),
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
        )

        payload = service.rows({"month": ["2026-05"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(enqueued, [("2026-05", "api_schema_stale")])

    def test_source_version_stale_payload_includes_stale_reasons(self) -> None:
        enqueued: list[tuple[str, str]] = []
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=RowsRepository(
                {
                    "rows": [
                        {
                            "id": "row-1",
                            "invoice": {},
                            "paymentStatus": {},
                            "oa": {},
                            "bankTransactions": {},
                        }
                    ],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "refresh_status": "fresh",
                    "source_versions": {"schema": "old"},
                }
            ),
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "new"},
        )

        payload = service.rows({"month": ["2026-05"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_stale_reasons"], ["schema_mismatch"])
        self.assertEqual(enqueued, [("2026-05", "api_source_versions_stale")])

    def test_filter_options_use_repository_projection_without_loading_all_rows(self) -> None:
        enqueued: list[tuple[str, str]] = []
        repository = FilterOptionsRepository(
            {
                "options": {
                    "payment_status": [{"value": "pending", "label": "待处理", "count": 2}],
                    "bank_direction": [{"value": "outflow", "label": "支出", "count": 2}],
                },
                "refresh_status": "fresh",
                "source_versions": {"schema": "v1"},
            }
        )
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=repository,
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
        )

        payload = service.filter_options({"month": ["2026-05"]})

        assert payload is not None
        fields = {field["field"]: field for field in payload["fields"] if isinstance(field, dict)}
        self.assertEqual(fields["payment_status"]["options"], [{"value": "pending", "label": "待处理", "count": 2}])
        self.assertEqual(fields["bank_direction"]["options"], [{"value": "outflow", "label": "支出", "count": 2}])
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(repository.calls, [("list_input_invoice_usage_filter_options", {"month": "2026-05", "keyword": None, "invoice_date_from": None, "invoice_date_to": None, "filters": None})])
        self.assertEqual(enqueued, [])

    def test_invoice_id_lookup_validates_source_versions_without_loading_all_rows(self) -> None:
        enqueued: list[tuple[str, str]] = []
        repository = InvoiceIdLookupRepository(
            {
                "rows": [{"id": "row-1", "invoiceId": "invoice-1"}],
                "missing_invoice_ids": [],
                "refresh_status": "fresh",
                "source_versions_by_scope": {"2026-05": {"schema": "v1"}},
                "read_model_scope_keys": ["2026-05"],
            }
        )
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=repository,
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
        )

        payload = service.rows_by_invoice_ids(["invoice-1"])

        assert payload is not None
        self.assertEqual(payload["rows"], [{"id": "row-1", "invoiceId": "invoice-1"}])
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(repository.calls, [("list_input_invoice_usage_rows_by_invoice_ids", ["invoice-1"])])
        self.assertEqual(enqueued, [])


class RowsRepository:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def list_input_invoice_usage_rows(self, **_: object) -> dict[str, object]:
        return dict(self._payload)


class FilterOptionsRepository:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_input_invoice_usage_filter_options(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_input_invoice_usage_filter_options", dict(kwargs)))
        return dict(self._payload)

    def list_input_invoice_usage_rows(self, **_: object) -> dict[str, object]:
        raise AssertionError("filter options must not load full input invoice usage rows")


class InvoiceIdLookupRepository:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls: list[tuple[str, object]] = []

    def list_input_invoice_usage_rows_by_invoice_ids(self, invoice_ids: list[str]) -> dict[str, object]:
        self.calls.append(("list_input_invoice_usage_rows_by_invoice_ids", list(invoice_ids)))
        return dict(self._payload)

    def list_input_invoice_usage_rows(self, **_: object) -> dict[str, object]:
        raise AssertionError("invoice id lookup must not load full input invoice usage rows")


class QueryServiceStub:
    def _parse_filters(self, _filters: object) -> list[object]:
        return []

    def _parse_sort(self, sort_field: object, sort_direction: object) -> tuple[str, str]:
        return str(sort_field), str(sort_direction)

    def _filter_config(self) -> list[object]:
        return [
            {"field": "payment_status", "label": "支付状态", "mode": "enum_multi", "operators": ["in"], "sortable": True},
            {"field": "bank_direction", "label": "收支", "mode": "enum_multi", "operators": ["in"], "sortable": True},
        ]

    def list_rows(self, **_: object) -> dict[str, object]:
        return {"rows": [], "pagination": {"page": 1, "pageSize": 50, "total": 0}, "summary": {}}


if __name__ == "__main__":
    unittest.main()
