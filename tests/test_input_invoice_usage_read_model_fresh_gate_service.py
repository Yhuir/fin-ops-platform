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


class RowsRepository:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def list_input_invoice_usage_rows(self, **_: object) -> dict[str, object]:
        return dict(self._payload)


class QueryServiceStub:
    def _parse_filters(self, _filters: object) -> list[object]:
        return []

    def _parse_sort(self, sort_field: object, sort_direction: object) -> tuple[str, str]:
        return str(sort_field), str(sort_direction)

    def _filter_config(self) -> list[object]:
        return []

    def list_rows(self, **_: object) -> dict[str, object]:
        return {"rows": [], "pagination": {"page": 1, "pageSize": 50, "total": 0}, "summary": {}}


if __name__ == "__main__":
    unittest.main()
