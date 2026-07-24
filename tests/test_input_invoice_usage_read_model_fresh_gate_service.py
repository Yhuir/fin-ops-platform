from __future__ import annotations

import unittest

from fin_ops_platform.services.input_invoice_usage_read_model_fresh_gate_service import (
    InputInvoiceUsageReadModelFreshGateService,
)


class InputInvoiceUsageReadModelFreshGateServiceTests(unittest.TestCase):
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
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=repository,
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=StaticRelationReader(
                {
                    "2026-02": {"relation_generation": 3},
                    "2026-07": {"relation_generation": 4},
                }
            ),
            statistics_overlay=lambda: {"oa_reverse_batch_count": 0},
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
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=repository,
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=StaticRelationReader(
                {"2026-03": {"relation_generation": 2}}
            ),
            statistics_overlay=lambda: {"oa_reverse_batch_count": 0},
        )

        payload = service.rows({"month": ["2026-03"]})
        filter_payload = service.filter_options({"month": ["2026-03"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(filter_payload["read_model_status"], "refreshing")
        self.assertNotIn("read_model_refresh_scope_keys", payload)
        self.assertNotIn("read_model_refresh_scope_keys", filter_payload)
        self.assertEqual(enqueued, [])
        self.assertEqual(repository.rows_calls, 0)

    def test_active_refresh_event_does_not_requeue_for_other_month_statistics(self) -> None:
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
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=FreshRelationReader(),
            statistics_overlay=lambda: {"oa_reverse_batch_count": 0},
        )

        payload = service.rows({"month": ["2026-03"]})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["statistics_status"], "refreshing")
        self.assertEqual(enqueued, [])

    def test_semantic_relation_proof_ignores_unrelated_bank_only_relation_change(self) -> None:
        relation_proof = {
            "source": "workbench_pair_relations",
            "scope_key": "2026-02",
            "consumer": "input_invoice",
            "relation_count": 1,
            "relation_updated_at": "2026-07-24 09:00:00+08",
        }

        class Repository(RowsRepository):
            def input_invoice_usage_relation_source_versions(
                self,
                *,
                scope_keys: list[str],
                tenant_id: str,
            ) -> dict[str, dict[str, object]]:
                del tenant_id
                return {scope_key: dict(relation_proof) for scope_key in scope_keys}

        enqueued: list[tuple[str, str]] = []
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=Repository(
                {
                    "rows": [],
                    "pagination": {"page": 1, "pageSize": 50, "total": 0},
                    "refresh_status": "fresh",
                    "source_versions": {"schema": "v1"},
                    "statistics": {"invoice_count": 0},
                    "statistics_status": "fresh",
                    "statistics_source_versions": {"schema": "v1"},
                },
                scope_state={
                    "scope_keys": ["2026-02"],
                    "source_versions_by_scope": {
                        "2026-02": {
                            "schema": "v1",
                            "workbench_relation_source_versions": relation_proof,
                        }
                    },
                    "blocking_scope_keys": [],
                },
            ),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=None,
            statistics_overlay=lambda: {"oa_reverse_batch_count": 0},
        )

        payload = service.rows({"month": ["2026-06"]})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["statistics_status"], "fresh")
        self.assertEqual(enqueued, [])

    def test_semantic_relation_proof_refreshes_only_changed_statistics_shard(self) -> None:
        embedded_proof = {
            "source": "workbench_pair_relations",
            "scope_key": "2026-02",
            "consumer": "input_invoice",
            "relation_count": 1,
            "relation_updated_at": "2026-07-24 09:00:00+08",
        }
        current_proof = {
            **embedded_proof,
            "relation_count": 2,
            "relation_updated_at": "2026-07-24 09:01:00+08",
        }

        class Repository(RowsRepository):
            def input_invoice_usage_relation_source_versions(
                self,
                *,
                scope_keys: list[str],
                tenant_id: str,
            ) -> dict[str, dict[str, object]]:
                del tenant_id
                return {scope_key: dict(current_proof) for scope_key in scope_keys}

        enqueued: list[tuple[str, str]] = []
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=Repository(
                {
                    "rows": [],
                    "pagination": {"page": 1, "pageSize": 50, "total": 0},
                    "refresh_status": "fresh",
                    "source_versions": {"schema": "v1"},
                    "statistics": {"invoice_count": 0},
                    "statistics_status": "fresh",
                    "statistics_source_versions": {"schema": "v1"},
                },
                scope_state={
                    "scope_keys": ["2026-02"],
                    "source_versions_by_scope": {
                        "2026-02": {
                            "schema": "v1",
                            "workbench_relation_source_versions": embedded_proof,
                        }
                    },
                    "blocking_scope_keys": [],
                },
            ),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=None,
            statistics_overlay=lambda: {"oa_reverse_batch_count": 0},
        )

        payload = service.rows({"month": ["2026-06"]})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["statistics_status"], "refreshing")
        self.assertEqual(
            enqueued,
            [("2026-02", "api_statistics_relation_dependency_stale")],
        )

    def test_all_scope_fails_closed_without_dependency_port_or_all_refresh(self) -> None:
        enqueued: list[tuple[str, str]] = []
        repository = DependencyBlockedRepository(
            scope_state={
                "scope_keys": ["2026-02"],
                "source_versions_by_scope": {},
                "blocking_scope_keys": [],
            }
        )
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=repository,
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=None,
        )

        payload = service.rows({})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(
            payload["read_model_stale_reasons"],
            ["workbench_relation_dependency_port_unavailable"],
        )
        self.assertEqual(enqueued, [])
        self.assertEqual(repository.rows_calls, 0)

    def test_statistics_uses_current_oa_reverse_overlay_without_rebuilding_months(self) -> None:
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
                    "source_versions": {"schema": "v1"},
                    "statistics": {"invoice_count": 1, "oa_reverse_batch_count": 2},
                    "statistics_status": "fresh",
                    "statistics_source_versions": {
                        "schema": "v1",
                        "input_invoice_usage_oa_reverse_batch_source_version": (
                            "rows:2|max_created_at:2026-07-22 08:00:00+00"
                        )
                    },
                }
            ),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=FreshRelationReader(),
            statistics_overlay=lambda: {"oa_reverse_batch_count": 3},
        )

        payload = service.rows({"month": ["2026-05"]})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["rows"][0]["id"], "row-1")
        self.assertEqual(payload["statistics"]["oa_reverse_batch_count"], 3)
        self.assertEqual(payload["statistics_status"], "fresh")
        self.assertEqual(enqueued, [])

    def test_statistics_base_source_mismatch_hides_statistics_and_refreshes_all(self) -> None:
        enqueued: list[tuple[str, str]] = []
        generation = "rows:3|max_created_at:2026-07-22 09:00:00+00"
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=RowsRepository(
                {
                    "rows": [],
                    "pagination": {"page": 1, "pageSize": 50, "total": 0},
                    "refresh_status": "fresh",
                    "source_versions": {"schema": "rows-v1"},
                    "statistics": {"invoice_count": 0, "oa_reverse_batch_count": 3},
                    "statistics_status": "fresh",
                    "statistics_source_versions": {
                        "schema": "statistics-v1",
                        "input_invoice_usage_oa_reverse_batch_source_version": generation,
                    },
                }
            ),
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "rows-v1"},
            workbench_relation_reader=FreshRelationReader(),
            statistics_overlay=lambda: {"oa_reverse_batch_count": 3},
        )

        payload = service.rows({})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertIsNone(payload["statistics"])
        self.assertEqual(payload["statistics_status"], "refreshing")
        self.assertEqual(enqueued, [("2026-05", "api_statistics_source_versions_stale")])

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
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=FreshRelationReader(),
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
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "new"},
            workbench_relation_reader=FreshRelationReader(),
        )

        payload = service.rows({"month": ["2026-05"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_stale_reasons"], ["2026-05:schema_mismatch"])
        self.assertEqual(enqueued, [("2026-05", "api_relation_dependency_stale")])

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
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=FreshRelationReader(),
        )

        payload = service.filter_options({"month": ["2026-05"]})

        assert payload is not None
        fields = {field["field"]: field for field in payload["fields"] if isinstance(field, dict)}
        self.assertEqual(fields["payment_status"]["options"], [{"value": "pending", "label": "待处理", "count": 2}])
        self.assertEqual(fields["bank_direction"]["options"], [{"value": "outflow", "label": "支出", "count": 2}])
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(repository.calls, [("list_input_invoice_usage_filter_options", {"month": "2026-05", "keyword": None, "invoice_date_from": None, "invoice_date_to": None, "filters": None})])
        self.assertEqual(enqueued, [])

    def test_detail_miss_refreshes_requested_month_without_all_scope(self) -> None:
        enqueued: list[tuple[str, str]] = []
        repository = type(
            "MissingDetailRepository",
            (),
            {
                "get_input_invoice_usage_row_by_row_id": (
                    lambda _self, _row_id: None
                ),
            },
        )()
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=repository,
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
        )

        payload = service.relation_details(
            "missing-row",
            {"kind": ["oa"], "month": ["2026-05"]},
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(enqueued, [("2026-05", "api_detail_miss")])

    def test_detail_without_month_never_enqueues_all_scope(self) -> None:
        enqueued: list[tuple[str, str]] = []
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=None,
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
        )

        payload = service.relation_details("missing-row", {"kind": ["oa"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "all")
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
            requires_sql_read_model_runtime=lambda: True,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
            workbench_relation_reader=FreshRelationReader(),
        )

        payload = service.rows_by_invoice_ids(["invoice-1"])

        assert payload is not None
        self.assertEqual(payload["rows"], [{"id": "row-1", "invoiceId": "invoice-1"}])
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(repository.calls, [("list_input_invoice_usage_rows_by_invoice_ids", ["invoice-1"])])
        self.assertEqual(enqueued, [])

    def test_export_page_without_repository_fails_closed_without_live_query(self) -> None:
        enqueued: list[tuple[str, str]] = []
        service = InputInvoiceUsageReadModelFreshGateService(
            repository=None,
            requires_sql_read_model_runtime=lambda: False,
            enqueue_refresh=lambda scope_key, reason: enqueued.append((scope_key, reason)) or True,
            expected_source_versions=lambda **_: {"schema": "v1"},
        )

        payload = service.export_page(month="2026-05")

        assert payload is not None
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(enqueued, [("2026-05", "api_export_read_model_unavailable")])


class RowsRepository:
    def __init__(
        self,
        payload: dict[str, object],
        *,
        scope_state: dict[str, object] | None = None,
    ) -> None:
        self._payload = payload
        self._scope_state = scope_state

    def list_input_invoice_usage_rows(self, **_: object) -> dict[str, object]:
        return dict(self._payload)

    def input_invoice_usage_scope_source_versions(
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


class FilterOptionsRepository:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_input_invoice_usage_filter_options(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_input_invoice_usage_filter_options", dict(kwargs)))
        return dict(self._payload)

    def list_input_invoice_usage_rows(self, **_: object) -> dict[str, object]:
        raise AssertionError("filter options must not load full input invoice usage rows")

    def input_invoice_usage_scope_source_versions(
        self,
        *,
        scope_key: str,
        tenant_id: str,
    ) -> dict[str, object]:
        del tenant_id
        target_scope_key = scope_key if scope_key != "all" else "2026-05"
        return fresh_scope_state(
            target_scope_key,
            self._payload.get("source_versions"),
        )


class InvoiceIdLookupRepository:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls: list[tuple[str, object]] = []

    def list_input_invoice_usage_rows_by_invoice_ids(self, invoice_ids: list[str]) -> dict[str, object]:
        self.calls.append(("list_input_invoice_usage_rows_by_invoice_ids", list(invoice_ids)))
        return dict(self._payload)

    def list_input_invoice_usage_rows(self, **_: object) -> dict[str, object]:
        raise AssertionError("invoice id lookup must not load full input invoice usage rows")


class DependencyBlockedRepository:
    def __init__(self, *, scope_state: dict[str, object]) -> None:
        self._scope_state = scope_state
        self.rows_calls = 0

    def input_invoice_usage_scope_source_versions(self, **_: object) -> dict[str, object]:
        return dict(self._scope_state)

    def list_input_invoice_usage_rows(self, **_: object) -> dict[str, object]:
        self.rows_calls += 1
        raise AssertionError("non-fresh dependency must short-circuit the rows query")

    def list_input_invoice_usage_filter_options(self, **_: object) -> dict[str, object]:
        raise AssertionError("non-fresh dependency must short-circuit the filter query")


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
