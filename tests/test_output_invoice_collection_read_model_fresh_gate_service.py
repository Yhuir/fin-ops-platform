from __future__ import annotations

import unittest

from fin_ops_platform.services.output_invoice_collection_read_model_fresh_gate_service import (
    OutputInvoiceCollectionReadModelFreshGateService,
)


class OutputInvoiceCollectionReadModelFreshGateServiceTests(unittest.TestCase):
    def test_all_rows_requests_title_statistics_only_on_first_page(self) -> None:
        repository = PagedRowsRepository()
        service = OutputInvoiceCollectionReadModelFreshGateService(
            repository=repository,
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda *_args: True,
            expected_source_versions=lambda **_: {"schema": "v1"},
        )

        payload = service.all_rows({"month": ["2026-05"]})

        self.assertEqual(len(payload["rows"]), 201)
        self.assertEqual([call["include_statistics"] for call in repository.calls], [True, False])

    def test_schema_stale_payload_enqueues_refresh_without_marking_fresh(self) -> None:
        enqueued: list[tuple[str, str]] = []
        service = OutputInvoiceCollectionReadModelFreshGateService(
            repository=RowsRepository(
                {
                    "rows": [{"id": "row-1", "invoice": {}, "collectionStatus": {}}],
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
        self.assertEqual(payload["readModelStatus"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(enqueued, [("2026-05", "api_schema_stale")])

    def test_source_version_stale_payload_includes_stale_reasons(self) -> None:
        enqueued: list[tuple[str, str]] = []
        service = OutputInvoiceCollectionReadModelFreshGateService(
            repository=RowsRepository(
                {
                    "rows": [
                        {
                            "id": "row-1",
                            "invoice": {},
                            "collectionStatus": {},
                            "oa": {},
                            "bankTransactions": {},
                            "invoiceRelations": {},
                            "redInvoiceRelation": {},
                            "receipt": {},
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
        self.assertEqual(payload["readModelStatus"], "refreshing")
        self.assertEqual(payload["read_model_stale_reasons"], ["schema_mismatch"])
        self.assertEqual(enqueued, [("2026-05", "api_source_versions_stale")])


class RowsRepository:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def list_output_invoice_collection_rows(self, **_: object) -> dict[str, object]:
        return dict(self._payload)


class PagedRowsRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def list_output_invoice_collection_rows(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        page = int(kwargs.get("page") or 1)
        count = 200 if page == 1 else 1
        rows = [
            {
                "id": f"row-{page}-{index}",
                "invoice": {},
                "collectionStatus": {},
                "oa": {},
                "bankTransactions": {},
                "invoiceRelations": {},
                "redInvoiceRelation": {},
                "receipt": {},
            }
            for index in range(count)
        ]
        return {
            "rows": rows,
            "pagination": {"page": page, "pageSize": 200, "total": 201},
            "summary": {},
            "statistics": {"invoice_count": 201},
            "statistics_status": "fresh",
            "statistics_source_versions": {"schema": "v1"},
            "refresh_status": "fresh",
            "source_versions": {"schema": "v1"},
        }


class QueryServiceStub:
    def _parse_filters(self, _filters: object) -> list[object]:
        return []

    def _parse_sort(self, sort_field: object, sort_direction: object) -> tuple[str, str]:
        return str(sort_field), str(sort_direction)

    def _filter_config(self) -> list[object]:
        return []


if __name__ == "__main__":
    unittest.main()
