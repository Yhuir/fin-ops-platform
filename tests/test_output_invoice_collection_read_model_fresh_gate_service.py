from __future__ import annotations

import unittest

from fin_ops_platform.services.output_invoice_collection_read_model_fresh_gate_service import (
    OutputInvoiceCollectionReadModelFreshGateService,
)


class OutputInvoiceCollectionReadModelFreshGateServiceTests(unittest.TestCase):
    def test_all_scope_relation_mismatch_enqueues_only_exact_months_before_rows_query(self) -> None:
        enqueued: list[tuple[str, str]] = []
        repository = DependencyBlockedRepository(
            scope_state={
                "scope_keys": ["2026-02", "2026-07"],
                "source_versions_by_scope": {
                    "2026-02": {
                        "schema": "v1",
                        "workbench_relation_source_versions": {"relation_generation": 1},
                    },
                    "2026-07": {
                        "schema": "v1",
                        "workbench_relation_source_versions": {"relation_generation": 2},
                    },
                },
                "blocking_scope_keys": [],
            }
        )
        service = OutputInvoiceCollectionReadModelFreshGateService(
            repository=repository,
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=StaticRelationReader(
                {
                    "2026-02": {"relation_generation": 3},
                    "2026-07": {"relation_generation": 4},
                }
            ),
        )

        payload = service.rows({})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_refresh_scope_keys"], ["2026-02", "2026-07"])
        self.assertEqual(
            enqueued,
            [
                ("2026-02", "api_relation_dependency_stale"),
                ("2026-07", "api_relation_dependency_stale"),
            ],
        )
        self.assertNotIn("all", [scope_key for scope_key, _reason in enqueued])
        self.assertEqual(repository.rows_calls, 0)

    def test_active_refresh_event_blocks_rows_without_duplicate_enqueue(self) -> None:
        enqueued: list[tuple[str, str]] = []
        repository = DependencyBlockedRepository(
            scope_state={
                "scope_keys": ["2026-03"],
                "source_versions_by_scope": {
                    "2026-03": {
                        "schema": "v1",
                        "workbench_relation_source_versions": {
                            "relation_generation": 1,
                        },
                    },
                },
                "blocking_scope_keys": ["2026-03"],
                "active_event_scope_keys": ["2026-03"],
            }
        )
        service = OutputInvoiceCollectionReadModelFreshGateService(
            repository=repository,
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=StaticRelationReader(
                {"2026-03": {"relation_generation": 2}}
            ),
        )

        payload = service.rows({"month": ["2026-03"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertNotIn("read_model_refresh_scope_keys", payload)
        self.assertEqual(enqueued, [])
        self.assertEqual(repository.rows_calls, 0)

    def test_active_refresh_event_does_not_requeue_for_other_month_statistics(self) -> None:
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
                    "source_versions": {"schema": "v1"},
                    "statistics": {"invoice_count": 1},
                    "statistics_status": "fresh",
                    "statistics_source_versions": {"schema": "v1"},
                },
                scope_state={
                    "scope_keys": ["2026-02", "2026-03"],
                    "source_versions_by_scope": {
                        "2026-02": {
                            "schema": "v1",
                            "workbench_relation_source_versions": {
                                "relation_generation": 1,
                            },
                        },
                        "2026-03": {
                            "schema": "v1",
                            "workbench_relation_source_versions": {
                                "relation_generation": 1,
                            },
                        },
                    },
                    "blocking_scope_keys": ["2026-02"],
                    "active_event_scope_keys": ["2026-02"],
                },
            ),
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=FreshRelationReader(),
        )

        payload = service.rows({"month": ["2026-03"]})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["statistics_status"], "refreshing")
        self.assertEqual(enqueued, [])

    def test_all_scope_fails_closed_without_dependency_port_or_all_refresh(self) -> None:
        enqueued: list[tuple[str, str]] = []
        repository = DependencyBlockedRepository(
            scope_state={
                "scope_keys": ["2026-02"],
                "source_versions_by_scope": {},
                "blocking_scope_keys": [],
            }
        )
        service = OutputInvoiceCollectionReadModelFreshGateService(
            repository=repository,
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=None,
        )

        payload = service.rows({})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["readModelStatus"], "refreshing")
        self.assertEqual(
            payload["read_model_stale_reasons"],
            ["workbench_relation_dependency_port_unavailable"],
        )
        self.assertEqual(enqueued, [])
        self.assertEqual(repository.rows_calls, 0)

    def test_all_rows_skips_title_statistics_on_every_page(self) -> None:
        repository = PagedRowsRepository()
        service = OutputInvoiceCollectionReadModelFreshGateService(
            repository=repository,
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda *_args: True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=FreshRelationReader(),
        )

        payload = service.all_rows({"month": ["2026-05"]})

        self.assertEqual(len(payload["rows"]), 201)
        self.assertEqual([call["include_statistics"] for call in repository.calls], [False, False])
        self.assertNotIn("statistics", payload)
        self.assertNotIn("statistics_status", payload)

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
            workbench_relation_reader=FreshRelationReader(),
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
            workbench_relation_reader=FreshRelationReader(),
        )

        payload = service.rows({"month": ["2026-05"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["readModelStatus"], "refreshing")
        self.assertEqual(payload["read_model_stale_reasons"], ["2026-05:schema_mismatch"])
        self.assertEqual(enqueued, [("2026-05", "api_relation_dependency_stale")])

    def test_detail_miss_refreshes_requested_month_without_all_scope(self) -> None:
        enqueued: list[tuple[str, str]] = []
        repository = type(
            "MissingDetailRepository",
            (),
            {
                "get_output_invoice_collection_row_by_row_id": (
                    lambda _self, _row_id: None
                ),
            },
        )()
        service = OutputInvoiceCollectionReadModelFreshGateService(
            repository=repository,
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
        )

        payload = service.relation_details(
            "missing-row",
            {"kind": ["invoice"], "month": ["2026-05"]},
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["readModelStatus"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(enqueued, [("2026-05", "api_detail_miss")])

    def test_detail_without_month_never_enqueues_all_scope(self) -> None:
        enqueued: list[tuple[str, str]] = []
        service = OutputInvoiceCollectionReadModelFreshGateService(
            repository=None,
            query_service=QueryServiceStub(),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
        )

        payload = service.relation_details(
            "missing-row",
            {"kind": ["invoice"]},
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["readModelStatus"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "all")
        self.assertEqual(enqueued, [])


class RowsRepository:
    def __init__(
        self,
        payload: dict[str, object],
        *,
        scope_state: dict[str, object] | None = None,
    ) -> None:
        self._payload = payload
        self._scope_state = scope_state

    def list_output_invoice_collection_rows(self, **_: object) -> dict[str, object]:
        return dict(self._payload)

    def output_invoice_collection_scope_source_versions(
        self,
        *,
        scope_key: str,
        tenant_id: str,
    ) -> dict[str, object]:
        del tenant_id
        if self._scope_state is not None:
            return dict(self._scope_state)
        target_scope_key = scope_key if scope_key != "all" else "2026-05"
        return fresh_scope_state(
            target_scope_key,
            self._payload.get("source_versions"),
        )


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

    def output_invoice_collection_scope_source_versions(
        self,
        *,
        scope_key: str,
        tenant_id: str,
    ) -> dict[str, object]:
        del tenant_id
        target_scope_key = scope_key if scope_key != "all" else "2026-05"
        return fresh_scope_state(
            target_scope_key,
            {"schema": "v1"},
        )


class DependencyBlockedRepository:
    def __init__(self, *, scope_state: dict[str, object]) -> None:
        self._scope_state = scope_state
        self.rows_calls = 0

    def output_invoice_collection_scope_source_versions(self, **_: object) -> dict[str, object]:
        return dict(self._scope_state)

    def list_output_invoice_collection_rows(self, **_: object) -> dict[str, object]:
        self.rows_calls += 1
        raise AssertionError("non-fresh dependency must short-circuit the rows query")


class StaticRelationReader:
    def __init__(self, source_versions_by_scope: dict[str, dict[str, object]]) -> None:
        self._source_versions_by_scope = source_versions_by_scope

    def source_versions_for_scopes(
        self,
        scope_keys: list[str],
        **_: object,
    ) -> dict[str, object]:
        return {
            "status": "fresh",
            "read_model_scope_source_versions": {
                scope_key: dict(self._source_versions_by_scope[scope_key])
                for scope_key in scope_keys
            },
            "refresh_scope_keys": [],
            "stale_reasons": [],
        }


class QueryServiceStub:
    def _parse_filters(self, _filters: object) -> list[object]:
        return []

    def _parse_sort(self, sort_field: object, sort_direction: object) -> tuple[str, str]:
        return str(sort_field), str(sort_direction)

    def _filter_config(self) -> list[object]:
        return []


class FreshRelationReader:
    def source_versions_for_scopes(
        self,
        scope_keys: list[str],
        **_: object,
    ) -> dict[str, object]:
        return {
            "status": "fresh",
            "read_model_scope_source_versions": {
                scope_key: {"relation_generation": 1}
                for scope_key in scope_keys
            },
            "refresh_scope_keys": [],
            "stale_reasons": [],
        }


def fresh_scope_state(
    scope_key: str,
    source_versions: object,
) -> dict[str, object]:
    versions = dict(source_versions) if isinstance(source_versions, dict) else {}
    versions["workbench_relation_source_versions"] = {
        "relation_generation": 1,
    }
    return {
        "scope_keys": [scope_key],
        "source_versions_by_scope": {
            scope_key: versions,
        },
        "statuses_by_scope": {scope_key: "fresh"},
        "blocking_scope_keys": [],
    }


if __name__ == "__main__":
    unittest.main()
