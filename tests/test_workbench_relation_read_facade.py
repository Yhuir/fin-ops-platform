from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_relation_distribution_mapper import (
    relation_dicts_from_distribution_payload,
    relation_dicts_by_row_id_from_distribution_payload,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade
from fin_ops_platform.services.workbench_relation_read_model_repository import WorkbenchRelationReadModelRepositoryPort


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class FakeRelationRepository:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload
        self.row_id_calls: list[dict[str, object]] = []
        self.batch_row_id_calls: list[dict[str, object]] = []
        self.month_calls: list[dict[str, object]] = []
        self.group_calls: list[dict[str, object]] = []

    def get_workbench_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object] | None:
        self.row_id_calls.append(
            {"row_ids": list(row_ids), "tenant_id": tenant_id, "scope_keys_hint": list(scope_keys_hint or [])}
        )
        return self.payload

    def get_batch_accounting_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
        submitted_year: str | None = None,
    ) -> dict[str, object] | None:
        call: dict[str, object] = {
            "row_ids": list(row_ids),
            "tenant_id": tenant_id,
            "scope_keys_hint": list(scope_keys_hint or []),
        }
        if submitted_year:
            call["submitted_year"] = submitted_year
        self.batch_row_id_calls.append(call)
        return self.payload

    def list_workbench_relation_rows(
        self,
        *,
        month: str,
        row_types: list[str] | None = None,
        relation_status: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.month_calls.append(
            {
                "month": month,
                "row_types": list(row_types or []),
                "relation_status": relation_status,
                "tenant_id": tenant_id,
            }
        )
        return self.payload

    def get_workbench_relation_groups_by_ids(
        self,
        group_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object] | None:
        self.group_calls.append(
            {"group_ids": list(group_ids), "tenant_id": tenant_id, "scope_keys_hint": list(scope_keys_hint or [])}
        )
        return self.payload


class UnderlyingWorkbenchRelationRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_workbench_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "get_workbench_relation_rows_by_ids",
                {"row_ids": list(row_ids), "tenant_id": tenant_id, "scope_keys_hint": list(scope_keys_hint or [])},
            )
        )
        return {"read_model_status": "fresh", "rows": [{"row_id": "txn-1"}]}

    def get_batch_accounting_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
        submitted_year: str | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "get_batch_accounting_relation_rows_by_ids",
                {
                    "row_ids": list(row_ids),
                    "tenant_id": tenant_id,
                    "scope_keys_hint": list(scope_keys_hint or []),
                    "submitted_year": submitted_year or "",
                },
            )
        )
        return {
            "read_model_status": "fresh",
            "rows": [{"row_id": "txn-batch-1"}] if row_ids else [],
            "submitted_count": 7 if submitted_year else 0,
        }

    def list_workbench_relation_rows(
        self,
        *,
        month: str,
        row_types: list[str] | None = None,
        relation_status: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object]:
        self.calls.append(
            (
                "list_workbench_relation_rows",
                {
                    "month": month,
                    "row_types": list(row_types or []),
                    "relation_status": relation_status or "",
                    "tenant_id": tenant_id,
                },
            )
        )
        return {"read_model_status": "fresh", "rows": [{"row_id": "txn-2"}]}

    def get_workbench_relation_groups_by_ids(
        self,
        group_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "get_workbench_relation_groups_by_ids",
                {"group_ids": list(group_ids), "tenant_id": tenant_id, "scope_keys_hint": list(scope_keys_hint or [])},
            )
        )
        return {"read_model_status": "fresh", "groups": [{"group_id": "case-1"}]}

    def workbench_relation_source_versions(self, *, scope_key: str, tenant_id: str = "default") -> dict[str, object]:
        self.calls.append(("workbench_relation_source_versions", {"scope_key": scope_key, "tenant_id": tenant_id}))
        return {"workbench_relation_schema_version": "test"}

    def workbench_relation_source_bundle_from_source(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
        tenant_id: str = "default",
    ) -> dict[str, object]:
        self.calls.append(
            (
                "workbench_relation_source_bundle_from_source",
                {"scope_key": scope_key, "row_ids": list(row_ids), "tenant_id": tenant_id},
            )
        )
        return {
            "rows": [{"case_id": "case-source-1", "row_ids": list(row_ids)}],
            "source_versions": {"source": "workbench_pair_relations", "relation_count": 1},
        }

    def workbench_relation_scope_summary(self, *, scope_key: str, tenant_id: str = "default") -> dict[str, object]:
        self.calls.append(("workbench_relation_scope_summary", {"scope_key": scope_key, "tenant_id": tenant_id}))
        return {
            "scope_key": scope_key,
            "row_count": 1,
            "group_count": 1,
            "source_versions": {"workbench_relation_schema_version": "test"},
        }

    def list_batch_accounting_relation_groups_by_year(
        self, *, year: str, tenant_id: str = "default"
    ) -> dict[str, object]:
        self.calls.append(("list_batch_accounting_relation_groups_by_year", {"year": year, "tenant_id": tenant_id}))
        return {
            "read_model_status": "fresh",
            "rows": [],
            "groups": [
                {
                    "group_id": "CASE-BATCH-txn-1",
                    "payload": {
                        "group_id": "CASE-BATCH-txn-1",
                        "relation_mode": "batch_accounting",
                        "relation_status": "linked",
                        "row_ids": ["txn-1", "oa-1"],
                        "row_types": ["bank", "oa"],
                        "special_metadata": {"source": "batch_accounting", "year": year},
                    },
                }
            ],
            "source_versions": {"workbench_relation_schema_version": "test"},
            "read_model_scope_keys": [f"{year}-{month:02d}" for month in range(1, 13)],
        }

    def save_workbench_relation_distribution(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        groups: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
        tenant_id: str = "default",
    ) -> None:
        self.calls.append(
            (
                "save_workbench_relation_distribution",
                {
                    "scope_key": scope_key,
                    "rows": list(rows),
                    "groups": list(groups),
                    "source_versions": dict(source_versions or {}),
                    "tenant_id": tenant_id,
                },
            )
        )

    def mark_workbench_relation_scope_empty(
        self,
        *,
        scope_key: str,
        source_versions: dict[str, object] | None = None,
        tenant_id: str = "default",
    ) -> None:
        self.calls.append(
            (
                "mark_workbench_relation_scope_empty",
                {"scope_key": scope_key, "source_versions": dict(source_versions or {}), "tenant_id": tenant_id},
            )
        )

    def list_pending_invoice_rows(self) -> dict[str, object]:
        raise AssertionError("workbench_relation port must not expose pending invoice reads")


class PartialFreshRelationConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_relation_rows" in normalized:
            requested_ids = set(params[1]) if len(params) > 1 and isinstance(params[1], list) else set()
            if "txn-present" not in requested_ids:
                return []
            return [
                {
                    "row_id": "txn-present",
                    "row_type": "bank_transaction",
                    "scope_key": "2026-03",
                    "scope_month": "2026-03-01",
                    "relation_status": "unlinked",
                    "group_ids": [],
                    "linked_oa": [],
                    "linked_bank_transactions": [],
                    "linked_input_invoices": [],
                    "linked_output_invoices": [],
                    "source_versions": {"workbench_relation_schema_version": "test"},
                    "payload": {"row_id": "txn-present", "row_type": "bank_transaction", "relation_status": "unlinked"},
                    "raw_payload": {},
                }
            ]
        if "from read_model.workbench_relation_groups" in normalized:
            return []
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_relation_scopes" in normalized:
            return {
                "scope_key": "2026-03",
                "row_count": 1,
                "group_count": 0,
                "source_versions": {"workbench_relation_schema_version": "test"},
                "cache_status": "fresh",
            }
        if "from job.read_model_dirty_scopes" in normalized:
            return None
        return None


class RelationGroupPayloadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_relation_rows" in normalized:
            return [
                {
                    "row_id": "txn-batch-1",
                    "row_type": "bank_transaction",
                    "scope_key": "2026-01",
                    "scope_month": "2026-01-01",
                    "relation_status": "linked",
                    "group_ids": ["CASE-BATCH-1"],
                    "linked_oa": [],
                    "linked_bank_transactions": [],
                    "linked_input_invoices": [],
                    "linked_output_invoices": [],
                    "source_versions": {"workbench_relation_schema_version": "stale-row"},
                    "payload": {"row_id": "txn-batch-1", "row_type": "bank_transaction"},
                    "raw_payload": {},
                }
            ]
        if "from read_model.workbench_relation_groups" in normalized:
            return [
                {
                    "group_id": "CASE-BATCH-1",
                    "scope_key": "2026-01",
                    "scope_month": "2026-01-01",
                    "relation_source": "manual",
                    "relation_kind": "oa_bank",
                    "relation_status": "linked",
                    "oa_row_ids": ["oa-batch-1"],
                    "bank_transaction_ids": ["txn-batch-1"],
                    "input_invoice_ids": [],
                    "output_invoice_ids": [],
                    "source_versions": {"workbench_relation_schema_version": "stale-group"},
                    "payload": {
                        "group_id": "CASE-BATCH-1",
                        "relation_mode": "manual_confirmed",
                        "relation_status": "linked",
                        "row_ids": ["txn-batch-1", "oa-batch-1"],
                        "row_types": ["bank", "oa"],
                        "special_metadata": {
                            "source": "batch_accounting",
                            "bank_row_id": "txn-batch-1",
                            "oa_row_ids": ["oa-batch-1"],
                            "year": "2026",
                        },
                    },
                    "raw_payload": {},
                }
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_relation_scopes" in normalized:
            return {
                "scope_key": "2026-01",
                "row_count": 1,
                "group_count": 1,
                "source_versions": {"workbench_relation_schema_version": "fresh-scope"},
                "cache_status": "fresh",
            }
        if "from job.read_model_dirty_scopes" in normalized:
            return None
        return None


class BatchAccountingBulkRelationConnection:
    def __init__(self, *, missing_scope: str = "", dirty_scope: str = "", dirty_status: str = "") -> None:
        self.missing_scope = missing_scope
        self.dirty_scope = dirty_scope
        self.dirty_status = dirty_status
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from unnest(%s::text[]) with ordinality" in normalized:
            return [
                {
                    "scope_key": scope_key,
                    "scope_exists": scope_key != self.missing_scope,
                    "source_versions": {"workbench_relation_schema_version": "bulk-v1"},
                    "dirty_status": self.dirty_status if scope_key == self.dirty_scope else None,
                }
                for scope_key in params[0]
            ]
        if "from read_model.workbench_relation_rows" in normalized:
            return [
                {
                    "row_id": "txn-batch-1",
                    "row_type": "bank_transaction",
                    "scope_key": "2026-01",
                    "scope_month": "2026-01-01",
                    "relation_status": "unlinked",
                    "group_ids": [],
                    "linked_oa": [],
                    "linked_bank_transactions": [],
                    "linked_input_invoices": [],
                    "linked_output_invoices": [],
                    "source_versions": {"workbench_relation_schema_version": "row-v1"},
                    "payload": {"row_id": "txn-batch-1", "row_type": "bank_transaction"},
                    "raw_payload": {},
                }
            ]
        if "from read_model.workbench_relation_groups" in normalized and "special_metadata" in normalized:
            return [
                {
                    "group_id": "CASE-BATCH-1",
                    "scope_key": "2026-01",
                    "scope_month": "2026-01-01",
                    "relation_source": "manual",
                    "relation_kind": "oa_bank",
                    "relation_status": "linked",
                    "oa_row_ids": ["oa-batch-1"],
                    "bank_transaction_ids": ["txn-batch-1"],
                    "input_invoice_ids": [],
                    "output_invoice_ids": [],
                    "source_versions": {"workbench_relation_schema_version": "group-v1"},
                    "payload": {
                        "group_id": "CASE-BATCH-1",
                        "relation_mode": "batch_accounting",
                        "relation_status": "linked",
                        "row_ids": ["txn-batch-1", "oa-batch-1"],
                        "row_types": ["bank", "oa"],
                        "special_metadata": {"source": "batch_accounting", "bank_year": "2026"},
                    },
                    "raw_payload": {},
                }
            ]
        if "from read_model.workbench_relation_groups" in normalized:
            return []
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "batch_accounting_relation_rows_scope_groups" in normalized:
            scope_keys = list(dict.fromkeys(["2026-01", *list(params[3] or [])]))
            return {
                "rows": [
                    {
                        "row_id": "txn-batch-1",
                        "row_type": "bank_transaction",
                        "scope_key": "2026-01",
                        "scope_month": "2026-01-01",
                        "relation_status": "unlinked",
                        "group_ids": [],
                        "linked_oa": [],
                        "linked_bank_transactions": [],
                        "linked_input_invoices": [],
                        "linked_output_invoices": [],
                        "source_versions": {"workbench_relation_schema_version": "row-v1"},
                        "payload": {"row_id": "txn-batch-1", "row_type": "bank_transaction"},
                        "raw_payload": {},
                    }
                ],
                "scope_proof": [
                    {
                        "scope_key": scope_key,
                        "scope_exists": scope_key != self.missing_scope,
                        "source_versions": {"workbench_relation_schema_version": "bulk-v1"},
                        "dirty_status": self.dirty_status if self.dirty_scope == scope_key else None,
                    }
                    for scope_key in scope_keys
                ],
                "groups": [],
                "submitted_count": 1,
            }
        if "count(distinct group_id)" in normalized:
            return {"submitted_count": 1}
        return None


class WorkbenchRelationReadModelRepositoryPortTests(unittest.TestCase):
    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        underlying = UnderlyingWorkbenchRelationRepository()
        port = WorkbenchRelationReadModelRepositoryPort(underlying)

        self.assertEqual(
            port.get_workbench_relation_rows_by_ids(
                ["txn-1"],
                tenant_id="tenant",
                scope_keys_hint=["2026-01"],
            )["rows"][0]["row_id"],
            "txn-1",
        )
        self.assertEqual(
            port.get_batch_accounting_relation_rows_by_ids(
                ["txn-batch-1"],
                tenant_id="tenant",
                scope_keys_hint=["2026-01"],
                submitted_year="2026",
            )["rows"][0]["row_id"],
            "txn-batch-1",
        )
        self.assertEqual(
            port.list_workbench_relation_rows(
                month="2026-01",
                row_types=["bank_transaction"],
                relation_status="linked",
                tenant_id="tenant",
            )["rows"][0]["row_id"],
            "txn-2",
        )
        self.assertEqual(
            port.get_workbench_relation_groups_by_ids(
                ["case-1"],
                tenant_id="tenant",
                scope_keys_hint=["2026-01"],
            )["groups"][0]["group_id"],
            "case-1",
        )
        self.assertEqual(
            port.workbench_relation_source_versions(scope_key="2026-01", tenant_id="tenant")[
                "workbench_relation_schema_version"
            ],
            "test",
        )
        self.assertEqual(
            port.workbench_relation_source_bundle_from_source(
                scope_key="2026-01",
                row_ids=["txn-1"],
                tenant_id="tenant",
            )["rows"][0]["case_id"],
            "case-source-1",
        )
        self.assertEqual(
            port.workbench_relation_scope_summary(scope_key="2026-01", tenant_id="tenant")["row_count"],
            1,
        )
        self.assertEqual(
            port.list_batch_accounting_relation_groups_by_year(year="2026", tenant_id="tenant")["groups"][0][
                "group_id"
            ],
            "CASE-BATCH-txn-1",
        )
        port.save_workbench_relation_distribution(
            scope_key="2026-01",
            rows=[{"row_id": "txn-1"}],
            groups=[{"group_id": "case-1"}],
            source_versions={"schema": "v1"},
            tenant_id="tenant",
        )
        port.mark_workbench_relation_scope_empty(
            scope_key="2026-02",
            source_versions={"schema": "v2"},
            tenant_id="tenant",
        )

        self.assertFalse(hasattr(port, "list_pending_invoice_rows"))
        self.assertEqual(
            [name for name, _payload in underlying.calls],
            [
                "get_workbench_relation_rows_by_ids",
                "get_batch_accounting_relation_rows_by_ids",
                "list_workbench_relation_rows",
                "get_workbench_relation_groups_by_ids",
                "workbench_relation_source_versions",
                "workbench_relation_source_bundle_from_source",
                "workbench_relation_scope_summary",
                "list_batch_accounting_relation_groups_by_year",
                "save_workbench_relation_distribution",
                "mark_workbench_relation_scope_empty",
            ],
        )


class WorkbenchRelationReadFacadeTests(unittest.TestCase):
    def test_batch_accounting_repository_uses_fixed_statement_counts(self) -> None:
        row_connection = BatchAccountingBulkRelationConnection()
        row_repository = PostgresReadModelRepository(row_connection)

        row_payload = row_repository.get_batch_accounting_relation_rows_by_ids(
            ["txn-batch-1"],
            scope_keys_hint=["2026-01"],
            submitted_year="2026",
        )

        self.assertEqual(row_payload["read_model_status"], "fresh")
        self.assertEqual(row_payload["submitted_count"], 1)
        self.assertEqual(len(row_connection.fetch_all_calls) + len(row_connection.fetch_one_calls), 1)
        self.assertEqual(
            sum(
                "batch_accounting_relation_rows_scope_groups" in sql
                for sql, _params in row_connection.fetch_one_calls
            ),
            1,
        )
        bundle_sql = row_connection.fetch_one_calls[0][0]
        self.assertNotIn("relation_row.payload", bundle_sql)
        self.assertNotIn("relation_row.raw_payload", bundle_sql)
        self.assertNotIn("group_row.raw_payload", bundle_sql)

        list_connection = BatchAccountingBulkRelationConnection()
        list_payload = PostgresReadModelRepository(list_connection).list_batch_accounting_relation_groups_by_year(
            year="2026"
        )
        self.assertEqual(list_payload["read_model_status"], "fresh")
        self.assertEqual(list_payload["groups"][0]["group_id"], "CASE-BATCH-1")
        self.assertEqual(len(list_connection.fetch_all_calls) + len(list_connection.fetch_one_calls), 2)

    def test_batch_accounting_bulk_proof_preserves_non_fresh_contract(self) -> None:
        missing_connection = BatchAccountingBulkRelationConnection(missing_scope="2026-12")
        missing_payload = PostgresReadModelRepository(missing_connection).get_batch_accounting_relation_rows_by_ids(
            ["txn-batch-1"],
            scope_keys_hint=["2026-01"],
            submitted_year="2026",
        )
        self.assertEqual(missing_payload["read_model_status"], "missing")
        self.assertIn("missing_scope:2026-12", missing_payload["stale_reasons"])
        self.assertEqual(missing_payload["submitted_count"], 0)
        self.assertEqual(len(missing_connection.fetch_all_calls) + len(missing_connection.fetch_one_calls), 1)
        self.assertIn("batch_accounting_relation_rows_scope_groups", missing_connection.fetch_one_calls[0][0])

        refreshing_connection = BatchAccountingBulkRelationConnection(
            dirty_scope="2026-06",
            dirty_status="processing",
        )
        refreshing_payload = PostgresReadModelRepository(
            refreshing_connection
        ).get_batch_accounting_relation_rows_by_ids(
            ["txn-batch-1"],
            scope_keys_hint=["2026-01"],
            submitted_year="2026",
        )
        self.assertEqual(refreshing_payload["read_model_status"], "refreshing")
        self.assertIn("refreshing:2026-06", refreshing_payload["stale_reasons"])
        self.assertEqual(refreshing_payload["submitted_count"], 0)
        self.assertEqual(
            len(refreshing_connection.fetch_all_calls) + len(refreshing_connection.fetch_one_calls),
            1,
        )
        self.assertIn("batch_accounting_relation_rows_scope_groups", refreshing_connection.fetch_one_calls[0][0])

    def test_batch_accounting_row_lookup_uses_dedicated_repository_io(self) -> None:
        repository = FakeRelationRepository(
            {
                "read_model_status": "fresh",
                "rows": [{"row_id": "txn-batch-1", "relation_status": "unlinked"}],
                "groups": [],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-01"],
                "stale_reasons": [],
            }
        )
        facade = WorkbenchRelationReadFacade(read_model_repository=repository)

        payload = facade.get_batch_accounting_by_row_ids(
            ["txn-batch-1"],
            scope_keys_hint=["2026-01"],
        )

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["rows"][0]["row_id"], "txn-batch-1")
        self.assertEqual(repository.row_id_calls, [])
        self.assertEqual(
            repository.batch_row_id_calls,
            [
                {
                    "row_ids": ["txn-batch-1"],
                    "tenant_id": "default",
                    "scope_keys_hint": ["2026-01"],
                }
            ],
        )

    def test_source_versions_for_month_uses_scope_metadata_without_loading_rows(self) -> None:
        repository = UnderlyingWorkbenchRelationRepository()
        facade = WorkbenchRelationReadFacade(read_model_repository=repository)

        payload = facade.source_versions_for_month("2026-01")

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["groups"], [])
        self.assertEqual(payload["source_versions"], {"workbench_relation_schema_version": "test"})
        self.assertEqual(
            repository.calls,
            [("workbench_relation_source_versions", {"scope_key": "2026-01", "tenant_id": "default"})],
        )

    def test_batch_accounting_row_bundle_includes_annual_count_without_separate_reader(self) -> None:
        repository = UnderlyingWorkbenchRelationRepository()
        facade = WorkbenchRelationReadFacade(read_model_repository=repository)

        payload = facade.get_batch_accounting_by_row_ids([], submitted_year="2026")

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["submitted_count"], 7)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["groups"], [])
        self.assertEqual(
            repository.calls,
            [
                (
                    "get_batch_accounting_relation_rows_by_ids",
                    {
                        "row_ids": [],
                        "tenant_id": "default",
                        "scope_keys_hint": [],
                        "submitted_year": "2026",
                    },
                )
            ],
        )

    def test_batch_accounting_year_list_uses_repository_reader_without_month_scan(self) -> None:
        repository = UnderlyingWorkbenchRelationRepository()
        facade = WorkbenchRelationReadFacade(read_model_repository=repository)

        payload = facade.list_batch_accounting_relations_by_year("2026")

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["groups"][0]["group_id"], "CASE-BATCH-txn-1")
        self.assertEqual(payload["read_model_scope_keys"], [f"2026-{month:02d}" for month in range(1, 13)])
        self.assertEqual(
            repository.calls,
            [("list_batch_accounting_relation_groups_by_year", {"year": "2026", "tenant_id": "default"})],
        )

    def test_get_by_row_ids_returns_fresh_linked_and_unlinked_contexts(self) -> None:
        repository = FakeRelationRepository(
            {
                "read_model_status": "fresh",
                "rows": [
                    {
                        "row_id": "txn-1",
                        "row_type": "bank_transaction",
                        "relation_status": "linked",
                        "group_ids": ["rel-1"],
                        "linked_oa": [{"id": "oa-1", "applicant": "田孟维"}],
                        "linked_bank_transactions": [{"id": "txn-1", "amount": "196.00"}],
                        "linked_input_invoices": [
                            {"id": "oa-att-inv-1", "invoice_no": "INV-001", "total_with_tax": "70.00"},
                            {"id": "oa-att-inv-2", "invoice_no": "INV-002", "total_with_tax": "126.00"},
                        ],
                        "linked_output_invoices": [],
                    },
                    {
                        "row_id": "txn-2",
                        "row_type": "bank_transaction",
                        "relation_status": "unlinked",
                        "group_ids": [],
                        "linked_oa": [],
                        "linked_bank_transactions": [{"id": "txn-2", "amount": "500.00"}],
                        "linked_input_invoices": [],
                        "linked_output_invoices": [],
                    },
                ],
                "groups": [{"group_id": "rel-1", "relation_kind": "oa_bank_input_invoice"}],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-01"],
            }
        )
        queue = QueueRecorder()
        facade = WorkbenchRelationReadFacade(read_model_repository=repository, queue_repository=queue)

        payload = facade.get_by_row_ids(["txn-1", "txn-2"], require_fresh=True, reason="unit_test")

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual([row["row_id"] for row in payload["rows"]], ["txn-1", "txn-2"])
        self.assertEqual(payload["rows"][0]["linked_input_invoices"][1]["invoice_no"], "INV-002")
        self.assertEqual(payload["rows"][1]["relation_status"], "unlinked")
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(repository.row_id_calls[0]["scope_keys_hint"], [])

    def test_repository_treats_missing_row_in_fresh_scope_as_unlinked_context(self) -> None:
        repository = PostgresReadModelRepository(PartialFreshRelationConnection())

        payload = repository.get_workbench_relation_rows_by_ids(["txn-present", "txn-missing"])

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual([row["row_id"] for row in payload["rows"]], ["txn-present"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-03"])

    def test_repository_treats_empty_rows_in_fresh_hinted_scope_as_fresh_empty_context(self) -> None:
        repository = PostgresReadModelRepository(PartialFreshRelationConnection())

        payload = repository.get_workbench_relation_rows_by_ids(["txn-missing"], scope_keys_hint=["2026-03"])

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["groups"], [])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-03"])

    def test_repository_preserves_relation_group_payload_for_distribution_mapping(self) -> None:
        repository = PostgresReadModelRepository(RelationGroupPayloadConnection())

        payload = repository.list_workbench_relation_rows(month="2026-01", row_types=["bank_transaction"])

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["groups"][0]["payload"]["special_metadata"]["source"], "batch_accounting")
        relation = relation_dicts_from_distribution_payload(payload)[0]
        self.assertEqual(relation["case_id"], "CASE-BATCH-1")
        self.assertEqual(relation["status"], "active")
        self.assertEqual(relation["special_metadata"]["bank_row_id"], "txn-batch-1")
        self.assertEqual(payload["source_versions"], {"workbench_relation_schema_version": "fresh-scope"})

    def test_repository_group_lookup_uses_scope_source_versions_over_relation_record(self) -> None:
        repository = PostgresReadModelRepository(RelationGroupPayloadConnection())

        payload = repository.get_workbench_relation_groups_by_ids(["CASE-BATCH-1"])

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["groups"][0]["group_id"], "CASE-BATCH-1")
        self.assertEqual(payload["source_versions"], {"workbench_relation_schema_version": "fresh-scope"})

    def test_facade_passes_scope_hint_for_empty_relation_context(self) -> None:
        repository = FakeRelationRepository(
            {
                "read_model_status": "fresh",
                "rows": [],
                "groups": [],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-03"],
            }
        )
        queue = QueueRecorder()
        facade = WorkbenchRelationReadFacade(read_model_repository=repository, queue_repository=queue)

        payload = facade.get_by_row_ids(["txn-missing"], month_hint="2026-03")

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["rows"], [])
        self.assertFalse(payload["refresh_enqueued"])
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(repository.row_id_calls[0]["scope_keys_hint"], ["2026-03"])

    def test_fresh_payload_with_canonical_version_drift_is_hidden_and_exact_scope_enqueued(self) -> None:
        repository = FakeRelationRepository(
            {
                "read_model_status": "fresh",
                "rows": [{"row_id": "txn-1", "relation_status": "linked"}],
                "groups": [{"group_id": "case-1"}],
                "source_versions": {"workbench_pair_relations_updated_at": "v1"},
                "read_model_scope_keys": ["2026-03"],
                "stale_reasons": [],
            }
        )
        queue = QueueRecorder()
        facade = WorkbenchRelationReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
            expected_source_versions=lambda scope_key: {
                "workbench_pair_relations_updated_at": "v2",
                "scope_key": scope_key,
            },
        )

        payload = facade.get_by_row_ids(
            ["txn-1"],
            month_hint="2026-03",
            require_fresh=True,
            reason="page_access",
        )

        self.assertEqual(payload["status"], "stale")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["groups"], [])
        self.assertTrue(payload["refresh_enqueued"])
        self.assertIn(
            "2026-03:workbench_pair_relations_updated_at_mismatch",
            payload["stale_reasons"],
        )
        self.assertEqual(queue.refreshes, [("workbench_relation", "2026-03", "page_access")])

    def test_matching_canonical_version_returns_fresh_without_enqueue(self) -> None:
        source_versions = {
            "workbench_pair_relations_updated_at": "v2",
            "scope_key": "2026-03",
        }
        repository = FakeRelationRepository(
            {
                "read_model_status": "fresh",
                "rows": [{"row_id": "txn-1", "relation_status": "linked"}],
                "groups": [{"group_id": "case-1"}],
                "source_versions": source_versions,
                "read_model_scope_keys": ["2026-03"],
                "stale_reasons": [],
            }
        )
        queue = QueueRecorder()
        facade = WorkbenchRelationReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
            expected_source_versions=lambda _scope_key: dict(source_versions),
        )

        payload = facade.get_by_row_ids(["txn-1"], month_hint="2026-03", require_fresh=True)

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["rows"][0]["row_id"], "txn-1")
        self.assertFalse(payload["refresh_enqueued"])
        self.assertEqual(queue.refreshes, [])

    def test_non_fresh_result_enqueues_refresh_when_required(self) -> None:
        repository = FakeRelationRepository(
            {
                "read_model_status": "missing",
                "rows": [],
                "groups": [],
                "source_versions": {},
                "read_model_scope_keys": ["2026-01"],
                "stale_reasons": ["read_model_missing"],
            }
        )
        queue = QueueRecorder()
        facade = WorkbenchRelationReadFacade(read_model_repository=repository, queue_repository=queue)

        payload = facade.get_by_row_ids(["txn-1"], require_fresh=True, reason="pending_invoice_projection")

        self.assertEqual(payload["status"], "missing")
        self.assertEqual(payload["rows"], [])
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(queue.refreshes, [("workbench_relation", "2026-01", "pending_invoice_projection")])

    def test_list_unlinked_filters_by_status_and_row_type(self) -> None:
        repository = FakeRelationRepository(
            {
                "read_model_status": "fresh",
                "rows": [{"row_id": "txn-2", "row_type": "bank_transaction", "relation_status": "unlinked"}],
                "groups": [],
                "source_versions": {},
                "read_model_scope_keys": ["2026-01"],
            }
        )
        facade = WorkbenchRelationReadFacade(read_model_repository=repository)

        payload = facade.list_unlinked("2026-01", row_types=["bank_transaction"])

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(repository.month_calls[0]["relation_status"], "unlinked")
        self.assertEqual(repository.month_calls[0]["row_types"], ["bank_transaction"])

    def test_distribution_mapper_drops_candidate_relation_groups(self) -> None:
        relations_by_row_id = relation_dicts_by_row_id_from_distribution_payload(
            {
                "rows": [
                    {
                        "row_id": "txn-candidate",
                        "row_type": "bank_transaction",
                        "relation_status": "unlinked",
                        "group_ids": ["decision-open-candidate"],
                    }
                ],
                "groups": [
                    {
                        "group_id": "decision-open-candidate",
                        "scope_month": "2026-01",
                        "relation_source": "unlinked_evidence",
                        "relation_status": "unlinked",
                        "payload": {
                            "row_ids": ["oa-candidate", "txn-candidate"],
                            "row_types": ["oa", "bank"],
                            "relation_mode": "unlinked_evidence",
                            "relation_status": "unlinked",
                        },
                    }
                ],
            }
        )

        self.assertEqual(relations_by_row_id["txn-candidate"], [])


if __name__ == "__main__":
    unittest.main()
