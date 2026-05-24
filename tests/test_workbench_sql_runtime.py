from __future__ import annotations

import json
from http import HTTPStatus
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.workbench_read_model_refresh import WorkbenchReadModelRefreshService
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder


class WorkbenchSqlReadConnection:
    def __init__(
        self,
        *,
        snapshot_row: dict | None = None,
        snapshot_rows: list[dict] | None = None,
        dirty: bool = False,
    ) -> None:
        self.snapshot_row = snapshot_row
        self.snapshot_rows = list(snapshot_rows or [])
        self.dirty = dirty
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.workbench_snapshots" in normalized:
            return self.snapshot_row
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-21T09:00:00+00:00"} if self.dirty else None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_snapshots" in normalized:
            return list(self.snapshot_rows)
        if "from read_model.workbench_rows" in normalized:
            return [
                {
                    "row_id": "bank-row-1",
                    "source_kind": "bank_transaction",
                    "status": "open",
                    "payload": {"id": "bank-row-1"},
                }
            ]
        return []


class WorkbenchAllRowsPageConnection(WorkbenchSqlReadConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "count(*) as total_count" in normalized:
            return {"total_count": 1}
        return super().fetch_one(sql, params)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_snapshots" in normalized:
            if "payload, raw_payload" in normalized:
                raise AssertionError("all-scope filtered rows_page must not load full grouped workbench snapshots")
            return [
                {
                    "scope_key": "2026-05",
                    "row_count": 100,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "cache_status": "fresh",
                    "summary": {"oa_count": 1, "bank_count": 2, "invoice_count": 3, "paired_count": 4, "open_count": 5},
                },
                {
                    "scope_key": "2026-04",
                    "row_count": 10,
                    "generated_at": "2026-05-21T08:00:00+00:00",
                    "cache_status": "fresh",
                    "summary": {"oa_count": 10, "bank_count": 20, "invoice_count": 30, "paired_count": 40, "open_count": 50},
                },
            ]
        if "from read_model.workbench_rows" in normalized:
            return [
                {
                    "row_id": "oa-att-inv-1",
                    "source_kind": "oa_attachment_invoice",
                    "status": "paired",
                    "payload": {"id": "oa-att-inv-1", "source_kind": "oa_attachment_invoice"},
                }
            ]
        return []


class WorkbenchSummaryGroupsConnection(WorkbenchSqlReadConnection):
    def __init__(self, *, dirty_status: str | None = None) -> None:
        super().__init__()
        self.dirty_status = dirty_status

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.workbench_groups" in normalized and "count(*) as total_count" in normalized:
            return {"total_count": 2}
        if "from read_model.workbench_groups" in normalized and "jsonb_array_length" in normalized:
            return {"oa_count": 3, "bank_count": 4, "invoice_count": 5}
        if "from read_model.workbench_groups" in normalized and "max(generated_at)" in normalized:
            return {"generated_at": "2026-05-22T09:30:00+00:00"}
        if "from read_model.workbench_groups" in normalized and "group_id = %s" in normalized:
            return {
                "group_id": "case:1",
                "zone": "open",
                "payload": {
                    "group_id": "case:1",
                    "group_type": "candidate",
                    "match_confidence": "medium",
                    "reason": "detail",
                    "oa_rows": [{"id": "oa-1", "type": "oa", "detail_fields": {"OA单号": "2151"}}],
                    "bank_rows": [],
                    "invoice_rows": [],
                },
            }
        if "from app.invoices" in normalized:
            return {
                "system_total": 9,
                "manual_import_total": 7,
                "workbench_visible_total": 4,
                "hidden_submitted_etc_total": 2,
                "extra_etc_total": 1,
            }
        if "from app.etc_business_batches" in normalized:
            return {"etc_summary_batch_count": 3}
        if "from read_model.workbench_rows" in normalized and "source_kind = 'oa_attachment_invoice'" in normalized:
            return {"oa_attachment_total": 5}
        return super().fetch_one(sql, params)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "%workbench%" in normalized:
            raise AssertionError("psycopg SQL uses % placeholders; ilike patterns must be query parameters")
        if "from read_model.workbench_snapshots" in normalized and "payload, raw_payload" in normalized:
            raise AssertionError("summary/groups hot path must not load full workbench snapshots")
        if "from read_model.workbench_groups" in normalized and "group by zone" in normalized:
            return [
                {"zone": "paired", "count": 1, "oa_count": 1, "bank_count": 2, "invoice_count": 0},
                {"zone": "open", "count": 2, "oa_count": 2, "bank_count": 2, "invoice_count": 5},
            ]
        if "from read_model.workbench_rows" in normalized and "group by row_type" in normalized:
            return [
                {"row_type": "oa", "count": 3},
                {"row_type": "bank", "count": 4},
                {"row_type": "invoice", "count": 5},
            ]
        if "from job.read_model_dirty_scopes" in normalized:
            if self.dirty_status is None:
                return []
            return [
                {
                    "scope_key": "2026-05",
                    "status": self.dirty_status,
                    "updated_at": "2026-05-22T09:31:00+00:00",
                    "last_error": "worker timeout" if self.dirty_status == "failed" else None,
                    "source_version": 7,
                }
            ]
        if "from job.runtime_worker_heartbeats" in normalized:
            return [
                {
                    "worker_id": "worker-workbench-1",
                    "worker_kind": "workbench",
                    "status": "processing",
                    "last_seen_at": "2026-05-22T09:31:05+00:00",
                    "lag_seconds": 12.0,
                    "payload": {"event_id": "event-1"},
                }
            ]
        if "from job.outbox_events" in normalized and "group by status" in normalized:
            return [{"status": "pending", "count": 2}, {"status": "failed", "count": 1}]
        if "from read_model.workbench_groups" in normalized:
            return [
                {
                    "group_id": "case:1",
                    "zone": "open",
                    "payload": {
                        "group_id": "case:1",
                        "group_type": "candidate",
                        "match_confidence": "medium",
                        "reason": "sql page",
                        "oa_rows": [
                            {"id": f"oa-{index}", "type": "oa", "detail_fields": {"OA单号": f"215{index}"}}
                            for index in range(1, 6)
                        ],
                        "bank_rows": [],
                        "invoice_rows": [],
                        "collapsed_rows": {
                            "oa": [
                                {"id": f"collapsed-oa-{index}", "type": "oa", "detail_fields": {"OA单号": f"C{index}"}}
                                for index in range(1, 5)
                            ]
                        },
                        "raw_payload": {"large": True},
                    },
                },
                {
                    "group_id": "case:2",
                    "zone": "open",
                    "payload": {
                        "group_id": "case:2",
                        "group_type": "candidate",
                        "match_confidence": "medium",
                        "reason": "sql page",
                        "oa_rows": [],
                        "bank_rows": [{"id": "bank-2", "type": "bank"}],
                        "invoice_rows": [],
                    },
                },
            ]
        return []


class MaterializedWorkbenchSummaryConnection(WorkbenchSummaryGroupsConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.workbench_summary" in normalized:
            return {
                "scope_key": "all",
                "payload": {
                    "month": "all",
                    "scope_key": "all",
                    "summary": {
                        "oa_count": 10,
                        "bank_count": 11,
                        "invoice_count": 12,
                        "paired_count": 13,
                        "open_count": 14,
                        "exception_count": 0,
                    },
                    "invoice_inventory": {"system_total": 99},
                    "generated_at": "2026-05-22T10:00:00+00:00",
                },
                "generated_at": "2026-05-22T10:00:00+00:00",
                "source_versions": {"source_version": 9},
            }
        return super().fetch_one(sql, params)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from job.read_model_dirty_scopes" in normalized:
            return []
        if "from read_model.workbench_groups" in normalized or "from read_model.workbench_rows" in normalized:
            raise AssertionError("materialized summary fast path must not recalculate summary from groups or rows")
        return []


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class RedisRecorder:
    def __init__(self, json_values: dict[str, dict] | None = None, text_values: dict[str, str] | None = None) -> None:
        self.json_values = dict(json_values or {})
        self.text_values = dict(text_values or {})
        self.get_json_calls: list[str] = []
        self.set_json_calls: list[tuple[str, dict, int]] = []
        self.get_text_calls: list[str] = []
        self.set_text_calls: list[tuple[str, str, int]] = []

    def get_json(self, key: str) -> dict | None:
        self.get_json_calls.append(key)
        return self.json_values.get(key)

    def set_json(self, key: str, value: dict, *, ttl_seconds: int) -> bool:
        self.set_json_calls.append((key, value, ttl_seconds))
        self.json_values[key] = value
        return True

    def get_text(self, key: str) -> str | None:
        self.get_text_calls.append(key)
        return self.text_values.get(key)

    def set_text(self, key: str, value: str, *, ttl_seconds: int) -> bool:
        self.set_text_calls.append((key, value, ttl_seconds))
        self.text_values[key] = value
        return True


class WorkbenchWriteConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
        return []

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((" ".join(sql.lower().split()), params))
        return 1


class StaleWorkbenchWriteConnection(WorkbenchWriteConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
        if "from read_model.workbench_snapshots" in self.fetch_one_calls[-1][0]:
            return {"source_versions": {"source_version": 5}}
        if "from read_model.workbench_candidate_matches" in self.fetch_one_calls[-1][0]:
            return {"source_version": 5}
        return None


class WorkbenchProjectionSettingsConnection:
    def __init__(
        self,
        *,
        overrides: list[dict[str, object]] | None = None,
        exception_cases: list[dict[str, object]] | None = None,
        bank_account_mappings: list[dict[str, object]] | None = None,
    ) -> None:
        self.overrides = list(overrides or [])
        self.exception_cases = list(exception_cases or [])
        self.bank_account_mappings = list(bank_account_mappings or [])

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "oa_invoice_offset": {"applicant_names": []},
                    "bank_account_mappings": self.bank_account_mappings,
                }
            }
        if "from job.read_model_dirty_scopes" in normalized:
            return {"source_version": 1}
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.workbench_row_overrides" in normalized:
            return list(self.overrides)
        if "from app.workbench_exception_cases" in normalized:
            return list(self.exception_cases)
        return []


class CandidateSnapshotRecorder:
    def __init__(self) -> None:
        self.saved_snapshots: list[tuple[dict[str, object], set[str] | None]] = []

    def save_workbench_candidate_matches(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_months: set[str] | None = None,
    ) -> None:
        self.saved_snapshots.append((snapshot, changed_scope_months))


class FakeWorkbenchReadModelService:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_read_model(self, scope_key: str) -> None:
        self.deleted.append(scope_key)


class WorkbenchSqlRuntimeTests(unittest.TestCase):
    def test_repository_reads_workbench_snapshot_and_dirty_status_without_state_fallback(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_row={
                "scope_key": "2026-05",
                "cache_status": "fresh",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "payload": {"open": {"groups": []}},
                "raw_payload": {},
            },
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="2026-05")

        self.assertEqual(view["payload"], {"open": {"groups": []}})
        self.assertEqual(view["refresh_status"], "refreshing")
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_reads_paginated_workbench_rows_from_sql_read_model(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_row={
                "scope_key": "2026-05",
                "cache_status": "fresh",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "payload": {"open": {"groups": []}},
                "row_count": 1,
            }
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(
            scope_key="2026-05",
            page=2,
            page_size=25,
            status="open",
            source_kind="bank_transaction",
            search="供应商",
        )

        self.assertEqual(view["rows_page"]["page"], 2)
        self.assertEqual(view["rows_page"]["page_size"], 25)
        self.assertEqual(view["rows_page"]["rows"], [{"id": "bank-row-1"}])
        self.assertTrue(any("from read_model.workbench_rows" in sql for sql, _params in connection.fetch_all_calls))

    def test_repository_synthesizes_all_workbench_view_from_month_snapshots(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_rows=[
                {
                    "scope_key": "2026-05",
                    "row_count": 1,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "payload": {
                        "payload": {
                            "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 1},
                            "open": {"groups": [{"oa_rows": [{"id": "oa-1"}], "bank_rows": [], "invoice_rows": []}]},
                            "paired": {"groups": []},
                        }
                    },
                },
                {
                    "scope_key": "2026-04",
                    "row_count": 1,
                    "generated_at": "2026-05-21T08:00:00+00:00",
                    "payload": {
                        "payload": {
                            "summary": {"oa_count": 0, "bank_count": 1, "invoice_count": 0, "paired_count": 1, "open_count": 0},
                            "open": {"groups": []},
                            "paired": {"groups": [{"oa_rows": [], "bank_rows": [{"id": "bank-1"}], "invoice_rows": []}]},
                        }
                    },
                },
            ],
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="all")

        self.assertEqual(view["row_count"], 2)
        self.assertEqual(view["refresh_status"], "refreshing")
        self.assertEqual(view["payload"]["summary"]["oa_count"], 1)
        self.assertEqual(view["payload"]["summary"]["bank_count"], 1)
        self.assertEqual(len(view["payload"]["open"]["groups"]), 1)
        self.assertEqual(len(view["payload"]["paired"]["groups"]), 1)

    def test_repository_dedupes_all_scope_groups_by_row_identity(self) -> None:
        duplicate_paired_group = {
            "group_id": "case:CASE-DUPLICATE-1",
            "group_type": "manual_confirmed",
            "match_confidence": "high",
            "reason": "existing_case_group",
            "oa_rows": [{"id": "oa-duplicate", "type": "oa"}],
            "bank_rows": [{"id": "bank-duplicate", "type": "bank"}],
            "invoice_rows": [{"id": "invoice-duplicate", "type": "invoice"}],
        }
        connection = WorkbenchSqlReadConnection(
            snapshot_rows=[
                {
                    "scope_key": "2026-02",
                    "row_count": 3,
                    "generated_at": "2026-05-22T09:00:00+00:00",
                    "payload": {
                        "payload": {
                            "summary": {"oa_count": 1, "bank_count": 1, "invoice_count": 1, "paired_count": 1, "open_count": 0},
                            "paired": {"groups": [duplicate_paired_group]},
                            "open": {"groups": []},
                        }
                    },
                },
                {
                    "scope_key": "2026-01",
                    "row_count": 3,
                    "generated_at": "2026-05-22T08:00:00+00:00",
                    "payload": {
                        "payload": {
                            "summary": {"oa_count": 1, "bank_count": 1, "invoice_count": 1, "paired_count": 1, "open_count": 0},
                            "paired": {"groups": [{**duplicate_paired_group, "group_id": "case:DIFFERENT-GROUP-ID"}]},
                            "open": {"groups": []},
                        }
                    },
                },
            ],
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="all")

        self.assertEqual(len(view["payload"]["paired"]["groups"]), 1)
        self.assertEqual(view["payload"]["summary"]["paired_count"], 1)
        self.assertEqual(view["payload"]["summary"]["oa_count"], 1)
        self.assertEqual(view["payload"]["summary"]["bank_count"], 1)
        self.assertEqual(view["payload"]["summary"]["invoice_count"], 1)

    def test_repository_ignores_stale_all_workbench_snapshot_and_synthesizes_from_months(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_row={
                "scope_key": "all",
                "row_count": 1,
                "generated_at": "2026-05-21T10:00:00+00:00",
                "payload": {
                    "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 1},
                    "open": {"groups": [{"oa_rows": [{"id": "stale-oa"}], "bank_rows": [], "invoice_rows": []}]},
                    "paired": {"groups": []},
                },
            },
            snapshot_rows=[
                {
                    "scope_key": "2026-04",
                    "row_count": 2,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "payload": {
                        "payload": {
                            "summary": {
                                "oa_count": 0,
                                "bank_count": 1,
                                "invoice_count": 1,
                                "paired_count": 1,
                                "open_count": 1,
                            },
                            "open": {"groups": [{"oa_rows": [], "bank_rows": [], "invoice_rows": [{"id": "invoice-open"}]}]},
                            "paired": {"groups": [{"oa_rows": [], "bank_rows": [{"id": "bank-paired"}], "invoice_rows": []}]},
                        }
                    },
                },
            ],
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="all")

        self.assertEqual(view["row_count"], 2)
        self.assertEqual(view["payload"]["summary"]["invoice_count"], 1)
        self.assertEqual(view["payload"]["open"]["groups"][0]["invoice_rows"][0]["id"], "invoice-open")
        self.assertEqual(view["payload"]["paired"]["groups"][0]["bank_rows"][0]["id"], "bank-paired")
        self.assertNotEqual(view["payload"]["open"]["groups"][0]["oa_rows"], [{"id": "stale-oa"}])

    def test_repository_reads_all_scope_filtered_page_without_full_snapshot_payloads(self) -> None:
        connection = WorkbenchAllRowsPageConnection()
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(
            scope_key="all",
            page=1,
            page_size=50,
            source_kind="oa_attachment_invoice",
        )

        self.assertEqual(view["payload"]["summary"]["invoice_count"], 33)
        self.assertEqual(view["payload"]["paired"]["groups"], [])
        self.assertEqual(view["payload"]["open"]["groups"], [])
        self.assertEqual(view["rows_page"]["total"], 1)
        self.assertEqual(view["rows_page"]["rows"][0]["id"], "oa-att-inv-1")
        self.assertTrue(any("from read_model.workbench_rows" in sql for sql, _params in connection.fetch_all_calls))
        self.assertFalse(
            any(
                "from read_model.workbench_snapshots" in sql and "payload, raw_payload" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_repository_reads_workbench_summary_without_full_snapshot_payloads(self) -> None:
        connection = WorkbenchSummaryGroupsConnection(dirty_status="processing")
        repository = PostgresReadModelRepository(connection)

        summary = repository.get_workbench_summary(scope_key="all")

        self.assertEqual(summary["summary"]["oa_count"], 3)
        self.assertEqual(summary["summary"]["bank_count"], 4)
        self.assertEqual(summary["summary"]["invoice_count"], 5)
        self.assertEqual(summary["summary"]["paired_count"], 1)
        self.assertEqual(summary["summary"]["open_count"], 2)
        self.assertEqual(summary["invoice_inventory"]["system_total"], 9)
        self.assertEqual(summary["invoice_inventory"]["oa_attachment_total"], 5)
        self.assertEqual(summary["read_model_status"], "refreshing")
        self.assertEqual(summary["generated_at"], "2026-05-22T09:30:00+00:00")
        self.assertEqual(
            summary["summary"]["zone_counts"],
            {
                "paired": {"groups": 1, "oa": 1, "bank": 2, "invoice": 0, "rows": 3},
                "open": {"groups": 2, "oa": 2, "bank": 2, "invoice": 5, "rows": 9},
            },
        )
        self.assertFalse(
            any(
                "from read_model.workbench_snapshots" in sql and "payload, raw_payload" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_repository_reads_materialized_workbench_summary_when_available(self) -> None:
        connection = MaterializedWorkbenchSummaryConnection()
        repository = PostgresReadModelRepository(connection)

        summary = repository.get_workbench_summary(scope_key="all")

        self.assertEqual(summary["summary"]["oa_count"], 10)
        self.assertEqual(summary["summary"]["open_count"], 14)
        self.assertEqual(summary["invoice_inventory"]["system_total"], 99)
        self.assertEqual(summary["read_model_status"], "fresh")
        self.assertTrue(any("from read_model.workbench_summary" in sql for sql, _params in connection.fetch_one_calls))
        self.assertFalse(
            any("from read_model.workbench_groups" in sql or "from read_model.workbench_rows" in sql for sql, _params in connection.fetch_all_calls)
        )

    def test_repository_reads_workbench_groups_page_from_structured_groups(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=1,
            source_kind="bank_transaction",
            search="供应商",
            sort="bank:desc",
        )

        self.assertEqual(page["zone"], "open")
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["page_size"], 1)
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["has_more"], True)
        self.assertEqual(page["groups"][0]["group_id"], "case:1")
        self.assertTrue(any("from read_model.workbench_groups" in sql for sql, _params in connection.fetch_all_calls))
        self.assertTrue(any("bank_sort_max desc nulls last" in sql for sql, _params in connection.fetch_all_calls))
        self.assertFalse(
            any(
                "from read_model.workbench_snapshots" in sql and "payload, raw_payload" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_repository_filters_workbench_groups_page_from_structured_group_rows(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=25,
            column_filters={
                "bank": {
                    "amount": ["支出", "建行 8106"],
                    "counterparty": ["云南溯源科技有限公司"],
                }
            },
            time_filters={"bank": {"mode": "month", "month": "2026-04"}},
        )

        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        group_row_queries = [(sql, params) for sql, params in all_queries if "read_model.workbench_group_rows" in sql]
        self.assertTrue(group_row_queries)
        self.assertTrue(any("column_values @> %s::jsonb" in sql for sql, _params in group_row_queries))
        self.assertTrue(any("time_date >= %s::date and r.time_date < %s::date" in sql for sql, _params in group_row_queries))
        self.assertTrue(any('"direction": "支出"' in str(params) and "2026-04-01" in str(params) for _sql, params in group_row_queries))

    def test_repository_reads_all_scope_groups_from_materialized_all_groups(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.get_workbench_groups_page(scope_key="all", zone="open", page=1, page_size=1)

        group_queries = [
            (sql, params)
            for sql, params in [*connection.fetch_one_calls, *connection.fetch_all_calls]
            if "from read_model.workbench_groups" in sql
        ]
        self.assertTrue(group_queries)
        self.assertTrue(any("scope_key = %s" in sql and params[:1] == ("all",) for sql, params in group_queries))
        self.assertFalse(any("scope_key <> 'all'" in sql for sql, _params in group_queries))

    def test_repository_reads_workbench_groups_summary_page_without_heavy_details(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=1,
            detail_level="summary",
        )

        group = page["groups"][0]
        self.assertEqual(page["detail_level"], "summary")
        self.assertEqual(group["group_id"], "case:1")
        self.assertEqual(group["row_counts"], {"oa": 5, "bank": 0, "invoice": 0})
        self.assertEqual(group["collapsed_row_counts"], {"oa": 4})
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-1", "oa-2", "oa-3"])
        self.assertEqual([row["id"] for row in group["collapsed_rows"]["oa"]], ["collapsed-oa-1", "collapsed-oa-2", "collapsed-oa-3"])
        self.assertEqual(group["oa_rows"][0]["id"], "oa-1")
        self.assertEqual(page["row_counts"], {"oa": 3, "bank": 4, "invoice": 5, "rows": 12})
        self.assertNotIn("detail_fields", group["oa_rows"][0])
        self.assertNotIn("raw_payload", group)

    def test_workbench_rows_inherit_status_from_containing_group_zone(self) -> None:
        payload = {
            "paired": {
                "groups": [
                    {
                        "group_id": "case:paired",
                        "bank_rows": [{"id": "bank-1", "type": "bank", "status": "open"}],
                    }
                ]
            },
            "open": {
                "groups": [
                    {
                        "group_id": "case:open",
                        "oa_rows": [{"id": "oa-1", "type": "oa", "status": "paired"}],
                    }
                ]
            },
        }

        rows = PostgresReadModelRepository._iter_workbench_rows(payload)

        self.assertEqual({row["id"]: row["status"] for row in rows}, {"bank-1": "paired", "oa-1": "open"})

    def test_repository_reads_single_workbench_group_detail(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        group = repository.get_workbench_group_detail(scope_key="all", zone="open", group_id="case:1")

        self.assertIsNotNone(group)
        self.assertEqual(group["group_id"], "case:1")
        self.assertEqual(group["oa_rows"][0]["id"], "oa-1")
        self.assertTrue(any("group_id = %s" in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_reports_workbench_refresh_status(self) -> None:
        connection = WorkbenchSummaryGroupsConnection(dirty_status="failed")
        repository = PostgresReadModelRepository(connection)

        status = repository.get_workbench_refresh_status(scope_key="all")

        self.assertEqual(status["read_model_status"], "stale")
        self.assertEqual(status["dirty_scopes"][0]["scope_key"], "2026-05")
        self.assertEqual(status["last_error"], "worker timeout")
        self.assertEqual(status["worker_lag_seconds"], 12.0)
        self.assertEqual(status["outbox_backlog"]["failed"], 1)

    def test_repository_persists_workbench_groups_alongside_rows_and_snapshot(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {
                            "open": {
                                "groups": [
                                    {
                                        "group_id": "case:CASE-1",
                                        "group_type": "candidate",
                                        "match_confidence": "medium",
                                        "reason": "候选",
                                        "oa_rows": [
                                            {
                                                "id": "oa-row-1",
                                                "type": "oa",
                                                "source_kind": "oa",
                                                "status": "open",
                                                "project_name": "项目A",
                                            }
                                        ],
                                        "bank_rows": [],
                                        "invoice_rows": [],
                                    }
                                ]
                            }
                        },
                        "source_versions": {"source_version": 6},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertIn("delete from read_model.workbench_groups", sql)
        self.assertIn("delete from read_model.workbench_group_rows", sql)
        self.assertIn("insert into read_model.workbench_groups", sql)
        self.assertIn("insert into read_model.workbench_group_rows", sql)
        self.assertIn("insert into read_model.workbench_summary", sql)

    def test_repository_rebuilds_all_scope_from_month_group_shards(self) -> None:
        class AggregateAllWorkbenchConnection(WorkbenchWriteConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_groups" not in normalized or "scope_key <> 'all'" not in normalized:
                    return []
                return [
                    {
                        "scope_key": "2026-01",
                        "scope_month": "2026-01-01",
                        "zone": "paired",
                        "group_id": "case:CASE-1",
                        "generated_at": "2026-05-24T00:02:00+00:00",
                        "source_versions": {"source_version": 2},
                        "payload": {
                            "group_id": "case:CASE-1",
                            "zone": "paired",
                            "oa_rows": [{"id": "oa-1", "type": "oa", "source_kind": "oa"}],
                            "bank_rows": [{"id": "bank-1", "type": "bank", "source_kind": "bank"}],
                            "invoice_rows": [
                                {"id": "oa-att-inv-1", "type": "invoice", "source_kind": "oa_attachment_invoice"}
                            ],
                        },
                    },
                    {
                        "scope_key": "2025-12",
                        "scope_month": "2025-12-01",
                        "zone": "paired",
                        "group_id": "case:CASE-1",
                        "generated_at": "2026-05-24T00:01:00+00:00",
                        "source_versions": {"source_version": 1},
                        "payload": {
                            "group_id": "case:CASE-1",
                            "zone": "paired",
                            "oa_rows": [{"id": "oa-1", "type": "oa", "source_kind": "oa"}],
                            "bank_rows": [],
                            "invoice_rows": [
                                {"id": "oa-att-inv-1", "type": "invoice", "source_kind": "oa_attachment_invoice"},
                                {"id": "oa-att-inv-2", "type": "invoice", "source_kind": "oa_attachment_invoice"},
                            ],
                        },
                    },
                ]

        connection = AggregateAllWorkbenchConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-01": {
                        "scope_key": "2026-01",
                        "payload": {"paired": {"groups": []}, "open": {"groups": []}},
                        "source_versions": {"source_version": 3},
                    }
                }
            },
            changed_scope_keys={"2026-01"},
        )

        aggregate_group_insert = next(
            params
            for sql, params in connection.executed
            if "insert into read_model.workbench_groups" in sql and "values ( %s, 'all'" in sql
        )
        group_payload = aggregate_group_insert[15].obj
        self.assertEqual(group_payload["row_count"], 4)
        self.assertEqual([row["id"] for row in group_payload["oa_rows"]], ["oa-1"])
        self.assertEqual([row["id"] for row in group_payload["bank_rows"]], ["bank-1"])
        self.assertEqual(
            [row["id"] for row in group_payload["invoice_rows"]],
            ["oa-att-inv-1", "oa-att-inv-2"],
        )
        self.assertNotIn("row_counts", group_payload)
        self.assertNotIn("collapsed_row_counts", group_payload)

    def test_workbench_api_returns_sql_read_model_without_sync_build(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {"get_workbench_view": lambda _self, **_kwargs: {"payload": {"open": {"groups": []}}, "refresh_status": "fresh"}},
        )()

        def explode_builder(_month: str):
            raise AssertionError("API request path must not synchronously build workbench payload")

        app._build_raw_workbench_payload = explode_builder

        response = app._handle_api_workbench("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["open"], {"groups": []})
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(queue.refreshes, [])

    def test_workbench_summary_api_uses_sql_summary_contract(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue, "redis_helper": None})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_summary": lambda _self, **_kwargs: {
                    "month": "all",
                    "summary": {"oa_count": 1, "bank_count": 2, "invoice_count": 3, "paired_count": 4, "open_count": 5, "exception_count": 0},
                    "read_model_status": "fresh",
                    "generated_at": "2026-05-22T09:30:00+00:00",
                }
            },
        )()
        app._build_raw_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("summary API must not build full workbench payload")
        )

        response = app._handle_api_workbench_summary("all")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["summary"]["bank_count"], 2)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(queue.refreshes, [])

    def test_workbench_summary_api_reports_missing_groups_table_as_unavailable(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": None})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_summary": lambda _self, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError('relation "read_model.workbench_groups" does not exist')
                )
            },
        )()

        response = app._handle_api_workbench_summary("all")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.SERVICE_UNAVAILABLE))
        self.assertEqual(payload["error"], "read_model_unavailable")
        self.assertEqual(payload["read_model_status"], "unavailable")

    def test_workbench_summary_api_logs_stale_unavailable_status_metric(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": None})()
        app._workbench_sql_read_repository = None

        with patch("builtins.print") as print_mock:
            response = app._handle_api_workbench_summary("all")

        self.assertEqual(response.status_code, int(HTTPStatus.SERVICE_UNAVAILABLE))
        metric_payloads = [
            json.loads(call.args[0])
            for call in print_mock.call_args_list
            if call.args and json.loads(call.args[0]).get("kind") == "workbench_read_model_status_metric"
        ]
        self.assertEqual(metric_payloads[0]["metric"], "workbench.read_model.status.count")
        self.assertEqual(metric_payloads[0]["endpoint"], "/api/workbench/summary")
        self.assertEqual(metric_payloads[0]["read_model_status"], "unavailable")

    def test_workbench_groups_api_uses_sql_groups_contract(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        calls: list[dict[str, object]] = []

        class SqlWorkbench:
            def get_workbench_groups_page(self, **kwargs):
                calls.append(kwargs)
                return {
                    "month": "all",
                    "zone": "open",
                    "page": 1,
                    "page_size": 50,
                    "total": 1,
                    "has_more": False,
                    "groups": [{"group_id": "case:1", "oa_rows": [], "bank_rows": [], "invoice_rows": []}],
                    "read_model_status": "fresh",
                }

            def workbench_groups_cache_version(self, **_kwargs):
                return "v7"

        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue, "redis_helper": None})()
        app._workbench_sql_read_repository = SqlWorkbench()
        app._build_raw_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("groups API must not build full workbench payload")
        )

        response = app._handle_api_workbench_groups(
            "all",
            zone="open",
            page="1",
            page_size="50",
            status="open",
            source_kind="bank_transaction",
            search="供应商",
            sort="bank:desc",
            detail_level="summary",
            column_filters='{"bank":{"amount":["支出"]}}',
            time_filters='{"bank":{"mode":"month","month":"2026-04"}}',
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["groups"][0]["group_id"], "case:1")
        self.assertEqual(
            calls,
            [
                {
                    "scope_key": "all",
                    "zone": "open",
                    "page": "1",
                    "page_size": "50",
                    "status": "open",
                    "source_kind": "bank_transaction",
                    "search": "供应商",
                    "sort": "bank:desc",
                    "detail_level": "summary",
                    "column_filters": {"bank": {"amount": ["支出"]}},
                    "time_filters": {"bank": {"mode": "month", "month": "2026-04"}},
                }
            ],
        )

    def test_workbench_group_detail_api_returns_full_group(self) -> None:
        app = object.__new__(Application)

        class SqlWorkbench:
            def get_workbench_group_detail(self, **kwargs):
                self.kwargs = kwargs
                return {
                    "group_id": "case:1",
                    "group_type": "candidate",
                    "match_confidence": "medium",
                    "reason": "detail",
                    "oa_rows": [{"id": "oa-1", "type": "oa", "detail_fields": {"OA单号": "2151"}}],
                    "bank_rows": [],
                    "invoice_rows": [],
                }

        repository = SqlWorkbench()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": None})()
        app._workbench_sql_read_repository = repository

        response = app._handle_api_workbench_group_detail("all", zone="open", group_id="case:1")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["group"]["oa_rows"][0]["detail_fields"], {"OA单号": "2151"})
        self.assertEqual(repository.kwargs, {"scope_key": "all", "zone": "open", "group_id": "case:1"})

    def test_workbench_groups_api_redis_hit_does_not_query_database_cache_version(self) -> None:
        app = object.__new__(Application)
        cache_key = app._workbench_groups_redis_cache_key_from_version(
            cache_version="v7",
            scope_key="all",
            zone="open",
            page="1",
            page_size="50",
            status=None,
            source_kind=None,
            search=None,
            sort=None,
            detail_level="full",
        )
        self.assertIsNotNone(cache_key)
        redis = RedisRecorder(
            text_values={"workbench:groups:version:all": "v7"},
            json_values={
                cache_key: {
                    "payload": {
                        "month": "all",
                        "zone": "open",
                        "page": 1,
                        "page_size": 50,
                        "total": 1,
                        "has_more": False,
                        "groups": [{"group_id": "cached"}],
                    }
                }
            },
        )

        class SqlWorkbench:
            def get_workbench_groups_page(self, **_kwargs):
                raise AssertionError("Redis hit must not query SQL page")

            def workbench_groups_cache_version(self, **_kwargs):
                raise AssertionError("Redis hit must not query SQL cache version")

        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": redis})()
        app._workbench_sql_read_repository = SqlWorkbench()

        response = app._handle_api_workbench_groups("all", zone="open", page="1", page_size="50")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["groups"][0]["group_id"], "cached")
        self.assertEqual(redis.get_text_calls, ["workbench:groups:version:all"])

    def test_workbench_groups_api_redis_cache_is_separated_by_detail_level(self) -> None:
        app = object.__new__(Application)
        redis = RedisRecorder(text_values={"workbench:groups:version:all": "v7"})

        class SqlWorkbench:
            def get_workbench_groups_page(self, **_kwargs):
                return {
                    "month": "all",
                    "zone": "open",
                    "page": 1,
                    "page_size": 50,
                    "total": 1,
                    "has_more": False,
                    "groups": [{"group_id": "fresh", "oa_rows": [], "bank_rows": [], "invoice_rows": []}],
                    "read_model_status": "fresh",
                    "detail_level": "summary",
                }

            def workbench_groups_cache_version(self, **_kwargs):
                raise AssertionError("Redis version key should avoid SQL cache version lookup")

        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": redis})()
        app._workbench_sql_read_repository = SqlWorkbench()

        app._handle_api_workbench_groups("all", zone="open", page="1", page_size="50", detail_level="summary")
        app._handle_api_workbench_groups("all", zone="open", page="1", page_size="50", detail_level="full")

        self.assertEqual(len(redis.set_json_calls), 2)
        self.assertNotEqual(redis.set_json_calls[0][0], redis.set_json_calls[1][0])

    def test_workbench_groups_api_redis_cache_key_includes_canonical_filters(self) -> None:
        app = object.__new__(Application)

        base_kwargs = {
            "cache_version": "v7",
            "scope_key": "all",
            "zone": "open",
            "page": "1",
            "page_size": "200",
            "status": None,
            "source_kind": None,
            "search": None,
            "sort": None,
            "detail_level": "summary",
            "time_filters": {"bank": {"mode": "month", "month": "2026-04"}},
        }
        key_a = app._workbench_groups_redis_cache_key_from_version(
            **base_kwargs,
            column_filters={"bank": {"amount": ["支出", "建行 8106"]}},
        )
        key_b = app._workbench_groups_redis_cache_key_from_version(
            **base_kwargs,
            column_filters={"bank": {"amount": ["建行 8106", "支出"]}},
        )
        key_c = app._workbench_groups_redis_cache_key_from_version(
            **base_kwargs,
            column_filters={"bank": {"amount": ["收入"]}},
        )

        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)

    def test_workbench_groups_api_reports_missing_groups_table_as_unavailable(self) -> None:
        app = object.__new__(Application)

        class SqlWorkbench:
            def get_workbench_groups_page(self, **_kwargs):
                raise RuntimeError('relation "read_model.workbench_groups" does not exist')

            def workbench_groups_cache_version(self, **_kwargs):
                return "v0"

        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": None})()
        app._workbench_sql_read_repository = SqlWorkbench()

        response = app._handle_api_workbench_groups("all", zone="open")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.SERVICE_UNAVAILABLE))
        self.assertEqual(payload["error"], "read_model_unavailable")
        self.assertEqual(payload["read_model_status"], "unavailable")

    def test_workbench_refresh_status_api_exposes_dirty_scopes_and_worker_lag(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": None})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_refresh_status": lambda _self, **_kwargs: {
                    "read_model_status": "refreshing",
                    "dirty_scopes": [{"scope_key": "2026-05", "status": "processing"}],
                    "worker_lag_seconds": 8.0,
                    "last_error": None,
                }
            },
        )()

        response = app._handle_api_workbench_refresh_status("all")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["dirty_scopes"][0]["scope_key"], "2026-05")

    def test_workbench_api_miss_enqueues_refresh_and_returns_refreshing(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {"get_workbench_view": lambda _self, **_kwargs: None},
        )()
        app._build_raw_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("API request path must not synchronously build workbench payload")
        )

        response = app._handle_api_workbench("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("workbench", "2026-05", "api_miss")])

    def test_workbench_api_passes_page_and_filter_to_sql_read_model(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        calls: list[dict[str, object]] = []

        class SqlWorkbench:
            def get_workbench_view(self, **kwargs):
                calls.append(kwargs)
                return {
                    "payload": {"open": {"groups": []}},
                    "refresh_status": "fresh",
                    "rows_page": {"page": 3, "page_size": 10, "rows": [{"id": "bank-row-1"}], "has_more": False},
                }

        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = SqlWorkbench()
        app._build_raw_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("API request path must not synchronously build workbench payload")
        )

        response = app._handle_api_workbench(
            "2026-05",
            page="3",
            page_size="10",
            status="open",
            source_kind="bank_transaction",
            search="供应商",
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows_page"]["rows"], [{"id": "bank-row-1"}])
        self.assertEqual(
            calls,
            [
                {
                    "scope_key": "2026-05",
                    "page": "3",
                    "page_size": "10",
                    "status": "open",
                    "source_kind": "bank_transaction",
                    "search": "供应商",
                }
            ],
        )

    def test_repository_persists_workbench_rows_alongside_snapshot(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {
                            "open": {
                                "groups": [
                                    {
                                        "bank_rows": [
                                            {
                                                "id": "bank-row-1",
                                                "source_kind": "bank_transaction",
                                                "status": "open",
                                                "counterparty_name": "供应商A",
                                                "amount": "100.00",
                                            }
                                        ]
                                    }
                                ]
                            }
                        },
                        "source_versions": {"case_snapshot_version": "v1"},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertIn("delete from read_model.workbench_rows", sql)
        self.assertIn("insert into read_model.workbench_rows", sql)

    def test_repository_deletes_workbench_rows_when_scope_snapshot_is_removed(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models({"read_models": {}}, changed_scope_keys={"2026-05"})

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertIn("delete from read_model.workbench_snapshots", sql)
        self.assertIn("delete from read_model.workbench_rows", sql)

    def test_repository_skips_stale_workbench_snapshot_write_by_source_version(self) -> None:
        connection = StaleWorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {"open": {"groups": []}},
                        "source_versions": {"source_version": 4},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertNotIn("insert into read_model.workbench_snapshots", sql)
        self.assertNotIn("delete from read_model.workbench_rows", sql)

    def test_repository_skips_stale_workbench_candidate_write_by_source_version(self) -> None:
        connection = StaleWorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_candidate_matches(
            {
                "candidates": {
                    "candidate-old": {
                        "candidate_key": "candidate-old",
                        "scope_month": "2026-05",
                        "status": "incomplete",
                        "row_ids": ["bank-1"],
                        "source_versions": {"source_version": 4},
                    }
                },
                "scope_runs": {"2026-05": {"source_versions": {"source_version": 4}}},
            },
            changed_scope_months={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertNotIn("delete from read_model.workbench_candidate_matches", sql)
        self.assertNotIn("insert into read_model.workbench_candidate_matches", sql)

    def test_workbench_invalidation_marks_dirty_scope_without_sync_rebuild(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_read_model_service = FakeWorkbenchReadModelService()
        app._expand_workbench_read_model_scope_keys_for_base_scopes = lambda scope_keys: scope_keys
        app._invalidate_cost_statistics_read_model_scopes = lambda *_args, **_kwargs: []
        app._build_raw_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("Invalidation must only enqueue refresh, not rebuild synchronously")
        )

        changed = app._invalidate_workbench_read_model_scopes(["2026-05"], invalidate_cost_statistics=False)

        self.assertEqual(changed, ["2026-05"])
        self.assertEqual(queue.refreshes, [("workbench", "2026-05", "workbench_scope_invalidated")])

    def test_workbench_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[tuple[str, object]] = []

            def rebuild_workbench_read_model_scope(self, scope_key: str, *, source_version: object = None) -> dict[str, object]:
                self.rebuilt.append((scope_key, source_version))
                return {"scope_key": scope_key, "row_count": 1}

        class FakeQueue:
            def __init__(self) -> None:
                self.completed: list[tuple[str, str, str]] = []

            def complete_read_model_refresh(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object = None,
            ) -> None:
                self.completed.append((tenant_id, scope_type, scope_key, source_version))

        builder = FakeBuilder()
        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 7},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt, [("2026-05", 7)])
        self.assertEqual(queue.completed, [("tenant-a", "workbench", "2026-05", 7)])
        self.assertEqual(result["scope_key"], "2026-05")
        self.assertEqual(result["row_count"], 1)

    def test_workbench_refresh_handler_expands_all_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def list_workbench_scope_shards(self, scope_key: str) -> list[str]:
                self.calls.append(scope_key)
                return ["2026-05", "2026-04"]

            def rebuild_workbench_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        class FakeQueue:
            def __init__(self) -> None:
                self.refreshes: list[tuple[str, str, str]] = []
                self.completed: list[tuple[str, str, str, object]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.refreshes.append((scope_type, scope_key, reason))

            def complete_read_model_refresh(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object = None,
            ) -> None:
                self.completed.append((tenant_id, scope_type, scope_key, source_version))

        builder = FakeBuilder()
        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="workbench",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.calls, ["all"])
        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05", "2026-04"], "row_count": 0})
        self.assertEqual(
            queue.refreshes,
            [("workbench", "2026-05", "workbench_all_shard"), ("workbench", "2026-04", "workbench_all_shard")],
        )
        self.assertEqual(queue.completed, [("tenant-a", "workbench", "all", None)])

    def test_sql_projection_pairs_materialized_attachment_rows_by_source_oa_relation(self) -> None:
        relation = {
            "row_ids": ["oa-exp-1", "legacy-attachment-row-id"],
            "row_types": ["oa", "invoice"],
        }
        rows_by_id = {
            "oa-exp-1": {"id": "oa-exp-1", "type": "oa", "source_kind": "oa"},
            "oa-att-inv-new": {
                "id": "oa-att-inv-new",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-exp-1",
            },
            "oa-att-pay-new": {
                "id": "oa-att-pay-new",
                "type": "invoice",
                "source_kind": "oa_attachment_payment_receipt",
                "derived_from_oa_id": "oa-exp-1",
            },
            "oa-att-unk-new": {
                "id": "oa-att-unk-new",
                "type": "invoice",
                "source_kind": "oa_attachment_unknown",
                "derived_from_oa_id": "oa-exp-1",
            },
        }

        row_ids = WorkbenchSqlProjectionBuilder._attachment_row_ids_for_relation(relation, rows_by_id)

        self.assertEqual(row_ids, ["oa-att-inv-new"])

    def test_sql_projection_materializes_invoice_like_expense_item_artifacts_only(self) -> None:
        payload = {
            "id": "oa-exp-files",
            "expense_items": [
                {
                    "expense_item_id": "item-1",
                    "row_index": "0",
                    "attachment_artifacts": [
                        {"source_attachment_name": "交通发票.pdf", "source_attachment_key": "invoice-pdf"},
                        {"source_attachment_name": "付款截图.jpg", "source_attachment_key": "screenshot", "suffix": "jpg"},
                    ],
                }
            ]
        }

        evidences = WorkbenchSqlProjectionBuilder._attachment_evidences_from_expense_items(payload)

        self.assertEqual(len(evidences), 1)
        self.assertEqual(evidences[0]["source_attachment_key"], "invoice-pdf")
        self.assertEqual(evidences[0]["source_expense_item_id"], "item-1")
        self.assertEqual(evidences[0]["source_expense_row_index"], "0")

    def test_sql_projection_materializes_invoice_like_expense_item_attachment_files(self) -> None:
        payload = {
            "id": "oa-exp-files",
            "expense_items": [
                {
                    "expense_item_id": "item-1",
                    "row_index": "0",
                    "attachment_files": [
                        {"fileName": "交通发票.pdf", "filePath": "/交通发票.pdf", "suffix": "pdf"},
                        {"fileName": "付款截图.jpg", "filePath": "/付款截图.jpg", "suffix": "jpg"},
                    ],
                }
            ],
        }

        evidences = WorkbenchSqlProjectionBuilder._attachment_evidences_from_expense_items(payload)

        self.assertEqual(len(evidences), 1)
        self.assertEqual(evidences[0]["source_attachment_name"], "交通发票.pdf")
        self.assertEqual(evidences[0]["source_attachment_key"], "oa-exp-files:attachment:item-1:0:交通发票.pdf")
        self.assertEqual(evidences[0]["source_expense_item_id"], "item-1")
        self.assertEqual(evidences[0]["source_expense_row_index"], "0")

    def test_sql_projection_does_not_materialize_plain_pdf_attachment_without_parsed_evidence(self) -> None:
        payload = {
            "id": "oa-exp-files",
            "expense_items": [
                {
                    "expense_item_id": "item-1",
                    "row_index": "0",
                    "attachment_files": [
                        {"fileName": "云服务器费用70元.pdf", "filePath": "/云服务器费用70元.pdf", "suffix": "pdf"},
                        {"fileName": "费用截图.jpg", "filePath": "/费用截图.jpg", "suffix": "jpg"},
                    ],
                }
            ],
        }

        evidences = WorkbenchSqlProjectionBuilder._attachment_evidences_from_expense_items(payload)

        self.assertEqual(evidences, [])

    def test_sql_projection_ignores_expense_item_artifact_when_same_attachment_has_parsed_invoice(self) -> None:
        payload = {
            "id": "oa-exp-files",
            "expense_items": [
                {
                    "expense_item_id": "item-1",
                    "row_index": "0",
                    "attachment_invoices": [
                        {
                            "source_attachment_key": "invoice-pdf",
                            "source_attachment_name": "交通发票.pdf",
                            "seller_name": "供应商A",
                            "total_with_tax": "167.00",
                        }
                    ],
                    "attachment_artifacts": [
                        {
                            "source_attachment_key": "invoice-pdf",
                            "source_attachment_name": "交通发票.pdf",
                            "document_kind": "发票附件",
                        }
                    ],
                }
            ]
        }

        evidences = WorkbenchSqlProjectionBuilder._attachment_evidences_from_expense_items(payload)

        self.assertEqual(len(evidences), 1)
        self.assertEqual(evidences[0]["seller_name"], "供应商A")
        self.assertEqual(evidences[0]["total_with_tax"], "167.00")

    def test_sql_projection_materializes_attachment_invoice_rows_from_structured_oa_tables(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    return [
                        {
                            "oa_row_id": "oa-exp-structured",
                            "scope_month": "2026-05-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-structured:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "oa-exp-structured:invoice:1",
                                "filename": "发票.pdf",
                            },
                            "cache_invoices": [
                                {
                                    "invoice_no": "INV-STRUCT-001",
                                    "seller_name": "杭州供应商",
                                    "total_with_tax": "199.00",
                                }
                            ],
                            "cache_evidences": [],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return []
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-05",
            {
                "oa-exp-structured": {
                    "id": "oa-exp-structured",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "199.00",
                    "counterparty_name": "杭州供应商",
                    "detail_fields": {"申请日期": "2026-05-02"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_kind"], "oa_attachment_invoice")
        self.assertEqual(rows[0]["derived_from_oa_id"], "oa-exp-structured")
        self.assertEqual(rows[0]["source_expense_item_id"], "oa-exp-structured:item:1")
        self.assertEqual(rows[0]["source_attachment_key"], "oa-exp-structured:invoice:1")
        self.assertIn("INV-STRUCT-001", rows[0]["detail_fields"]["发票号码"])

    def test_sql_projection_structured_cache_excludes_payment_receipt_evidence_rows(self) -> None:
        selected = WorkbenchSqlProjectionBuilder._select_structured_attachment_evidences(
            invoices=[],
            evidences=[
                {
                    "evidence_type": "tax_invoice",
                    "invoice_no": "INV-ONLY-001",
                    "source_attachment_key": "formal-invoice",
                    "seller_name": "发票供应商",
                    "total_with_tax": "196.00",
                },
                {
                    "evidence_type": "payment_receipt",
                    "transaction_no": "wx-pay-001",
                    "source_attachment_key": "payment-voucher",
                    "source_attachment_name": "付款凭证.jpg",
                    "amount": "196.00",
                },
            ],
            artifacts=[],
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["source_attachment_key"], "formal-invoice")
        self.assertEqual(selected[0]["evidence_type"], "tax_invoice")

    def test_sql_projection_bank_account_label_uses_settings_mapping_not_account_name(self) -> None:
        connection = WorkbenchProjectionSettingsConnection(
            bank_account_mappings=[
                {"last4": "6386", "bank_name": "工商银行", "short_name": "工行"},
            ]
        )
        builder = WorkbenchSqlProjectionBuilder(
            connection=connection,
            read_model_repository=CandidateSnapshotRecorder(),
        )

        row = builder._bank_row_from_sql(
            {
                "row_id": "bank-company-account-name",
                "account_no": "bank_mapping_6386",
                "account_name": "云南溯源科技有限公司",
                "txn_direction": "outflow",
                "counterparty_name_raw": "云南溯源科技有限公司",
                "amount": "4.500000",
                "signed_amount": "-4.500000",
                "txn_date": "2026-04-23",
                "trade_time": "2026-04-23T17:22:27+08:00",
                "pay_receive_time": "2026-04-23T17:22:27+08:00",
                "summary": "单位国内汇款手续费收入",
                "remark": "企业网银同城他行",
                "raw_payload": {},
            }
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["counterparty_name"], "云南溯源科技有限公司")
        self.assertEqual(row["payment_account_label"], "工商银行 账户 6386")
        self.assertEqual(row["summary_fields"]["支付账户"], "工商银行 账户 6386")

    def test_sql_projection_matches_legacy_attachment_cache_by_nested_source_key(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    if "oa_attachment_invoice_cache_sources" not in normalized:
                        return []
                    return [
                        {
                            "oa_row_id": "oa-exp-legacy-cache",
                            "scope_month": "2026-05-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-legacy-cache:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "actual-attachment-key",
                                "filename": "历史发票.pdf",
                            },
                            "cache_invoices": [
                                {
                                    "source_attachment_key": "actual-attachment-key",
                                    "invoice_no": "INV-LEGACY-CACHE-001",
                                    "seller_name": "历史供应商",
                                    "total_with_tax": "299.00",
                                }
                            ],
                            "cache_evidences": [],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return []
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-05",
            {
                "oa-exp-legacy-cache": {
                    "id": "oa-exp-legacy-cache",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "299.00",
                    "counterparty_name": "历史供应商",
                    "detail_fields": {"申请日期": "2026-05-02"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_attachment_key"], "actual-attachment-key")
        self.assertIn("INV-LEGACY-CACHE-001", rows[0]["detail_fields"]["发票号码"])

    def test_sql_projection_matches_cache_source_bridge_with_legacy_cache_key(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    if "oa_attachment_invoice_cache_sources" not in normalized:
                        return []
                    return [
                        {
                            "oa_row_id": "oa-exp-cache-bridge",
                            "scope_month": "2026-05-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-cache-bridge:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "current-structured-attachment-key",
                                "filename": "迁移后发票.pdf",
                            },
                            "cache_source_attachment_key": "legacy-parser-cache-key",
                            "cache_invoices": [
                                {
                                    "source_attachment_key": "legacy-parser-cache-key",
                                    "invoice_no": "INV-BRIDGED-001",
                                    "seller_name": "桥接供应商",
                                    "total_with_tax": "399.00",
                                }
                            ],
                            "cache_evidences": [],
                            "cache_artifacts": [],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return []
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-05",
            {
                "oa-exp-cache-bridge": {
                    "id": "oa-exp-cache-bridge",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "399.00",
                    "counterparty_name": "桥接供应商",
                    "detail_fields": {"申请日期": "2026-05-02"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_attachment_key"], "current-structured-attachment-key")
        self.assertIn("INV-BRIDGED-001", rows[0]["detail_fields"]["发票号码"])

    def test_sql_projection_matches_cache_by_attachment_source_identity(self) -> None:
        inspected_sql: list[str] = []

        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    inspected_sql.append(normalized)
                    return [
                        {
                            "oa_row_id": "oa-exp-cache-identity",
                            "scope_month": "2026-01-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-cache-identity:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "current-file-key",
                                "source_attachment_name": "云服务器费用70元.pdf",
                                "filename": "云服务器费用70元.pdf",
                            },
                            "cache_source_attachment_key": "legacy-cache-key",
                            "cache_invoices": [
                                {
                                    "source_attachment_key": "legacy-parser-key",
                                    "source_expense_item_id": "oa-exp-cache-identity:item:1",
                                    "source_attachment_name": "云服务器费用70元.pdf",
                                    "invoice_no": "26322000000128086591",
                                    "seller_name": "中科视拓（南京）科技有限公司",
                                    "buyer_name": "云南溯源科技有限公司",
                                    "total_with_tax": "70.00",
                                    "issue_date": "2026-01-07",
                                }
                            ],
                            "cache_evidences": [],
                            "cache_artifacts": [],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return []
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-01",
            {
                "oa-exp-cache-identity": {
                    "id": "oa-exp-cache-identity",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "196.00",
                    "counterparty_name": "",
                    "detail_fields": {"申请日期": "2026-01-07"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertTrue(any("source_expense_item_id" in sql and "source_attachment_name" in sql for sql in inspected_sql))
        self.assertEqual(rows[0]["source_attachment_key"], "current-file-key")
        self.assertEqual(rows[0]["seller_name"], "中科视拓（南京）科技有限公司")
        self.assertIn("26322000000128086591", rows[0]["detail_fields"]["发票号码"])

    def test_sql_projection_ignores_artifact_placeholders_when_cache_has_parsed_invoice(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    return [
                        {
                            "oa_row_id": "oa-exp-with-artifact-placeholder",
                            "scope_month": "2026-02-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-with-artifact-placeholder:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "attachment-key-1",
                                "filename": "发票.pdf",
                            },
                            "cache_invoices": [
                                {
                                    "source_attachment_key": "attachment-key-1",
                                    "seller_name": "供应商A",
                                    "buyer_name": "云南溯源科技有限公司",
                                    "amount": "165.35",
                                    "tax_amount": "1.65",
                                    "total_with_tax": "167.00",
                                    "issue_date": "2026-02-04",
                                }
                            ],
                            "cache_evidences": [],
                            "cache_artifacts": [
                                {
                                    "source_attachment_key": "attachment-key-1",
                                    "source_attachment_name": "发票.pdf",
                                    "document_kind": "发票附件",
                                }
                            ],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return []
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-02",
            {
                "oa-exp-with-artifact-placeholder": {
                    "id": "oa-exp-with-artifact-placeholder",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "652.99",
                    "counterparty_name": "",
                    "detail_fields": {"申请日期": "2026-02-26"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["seller_name"], "供应商A")
        self.assertEqual(rows[0]["amount"], "165.35")
        self.assertEqual(rows[0]["total_with_tax"], "167.00")

    def test_sql_projection_does_not_fallback_to_payload_artifact_for_structured_attachment(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    return [
                        {
                            "oa_row_id": "oa-exp-structured-and-payload",
                            "scope_month": "2026-02-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-structured-and-payload:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "shared-attachment-key",
                                "filename": "发票.pdf",
                            },
                            "cache_invoices": [
                                {
                                    "source_attachment_key": "shared-attachment-key",
                                    "seller_name": "供应商A",
                                    "buyer_name": "云南溯源科技有限公司",
                                    "amount": "165.35",
                                    "tax_amount": "1.65",
                                    "total_with_tax": "167.00",
                                    "issue_date": "2026-02-04",
                                }
                            ],
                            "cache_evidences": [],
                            "cache_artifacts": [],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return [
                        {
                            "row_id": "oa-exp-structured-and-payload",
                            "scope_month": "2026-02-01",
                            "normalized_payload": {
                                "expense_items": [
                                    {
                                        "expense_item_id": "oa-exp-structured-and-payload:item:1",
                                        "row_index": "0",
                                        "attachment_artifacts": [
                                            {
                                                "source_attachment_key": "shared-attachment-key",
                                                "source_attachment_name": "发票.pdf",
                                            }
                                        ],
                                    }
                                ]
                            },
                            "raw_payload": {},
                        }
                    ]
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-02",
            {
                "oa-exp-structured-and-payload": {
                    "id": "oa-exp-structured-and-payload",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "652.99",
                    "counterparty_name": "",
                    "detail_fields": {"申请日期": "2026-02-26"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_attachment_key"], "shared-attachment-key")
        self.assertEqual(rows[0]["total_with_tax"], "167.00")

    def test_sql_projection_does_not_duplicate_structured_attachment_with_file_fallback_key(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    return [
                        {
                            "oa_row_id": "oa-exp-file-fallback",
                            "scope_month": "2026-02-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-file-fallback:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "structured-cache-key",
                                "source_attachment_name": "同一发票.pdf",
                                "filename": "同一发票.pdf",
                            },
                            "cache_source_attachment_key": "legacy-cache-key",
                            "cache_invoices": [
                                {
                                    "source_attachment_key": "legacy-cache-key",
                                    "source_attachment_name": "同一发票.pdf",
                                    "invoice_no": "INV-DEDUP-001",
                                    "seller_name": "供应商A",
                                    "total_with_tax": "167.00",
                                }
                            ],
                            "cache_evidences": [],
                            "cache_artifacts": [],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return [
                        {
                            "row_id": "oa-exp-file-fallback",
                            "scope_month": "2026-02-01",
                            "normalized_payload": {
                                "expense_items": [
                                    {
                                        "expense_item_id": "oa-exp-file-fallback:item:1",
                                        "row_index": "0",
                                        "attachment_files": [
                                            {
                                                "fileName": "同一发票.pdf",
                                                "filePath": "/同一发票.pdf",
                                                "suffix": "pdf",
                                            }
                                        ],
                                    }
                                ]
                            },
                            "raw_payload": {},
                        }
                    ]
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-02",
            {
                "oa-exp-file-fallback": {
                    "id": "oa-exp-file-fallback",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "167.00",
                    "counterparty_name": "",
                    "detail_fields": {"申请日期": "2026-02-26"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_attachment_key"], "structured-cache-key")
        self.assertIn("INV-DEDUP-001", rows[0]["detail_fields"]["发票号码"])

    def test_sql_projection_skips_structured_attachment_placeholders_without_invoice_identity(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    return [
                        {
                            "oa_row_id": "oa-exp-duplicate-structured",
                            "scope_month": "2026-05-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-duplicate-structured:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "hash-source-key",
                                "source_attachment_name": "重复发票.pdf",
                                "filename": "重复发票.pdf",
                            },
                            "cache_source_attachment_key": "",
                            "cache_invoices": [],
                            "cache_evidences": [],
                            "cache_artifacts": [
                                {
                                    "source_attachment_key": "hash-source-key",
                                    "source_attachment_name": "重复发票.pdf",
                                    "document_kind": "发票附件",
                                }
                            ],
                        },
                        {
                            "oa_row_id": "oa-exp-duplicate-structured",
                            "scope_month": "2026-05-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-duplicate-structured:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "fallback-source-key",
                                "source_attachment_name": "重复发票.pdf",
                                "filename": "重复发票.pdf",
                            },
                            "cache_source_attachment_key": "",
                            "cache_invoices": [],
                            "cache_evidences": [],
                            "cache_artifacts": [
                                {
                                    "source_attachment_key": "fallback-source-key",
                                    "source_attachment_name": "重复发票.pdf",
                                    "document_kind": "发票附件",
                                }
                            ],
                        },
                    ]
                if "from app.oa_applications" in normalized:
                    return []
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-05",
            {
                "oa-exp-duplicate-structured": {
                    "id": "oa-exp-duplicate-structured",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "399.00",
                    "counterparty_name": "",
                    "detail_fields": {"申请日期": "2026-05-08"},
                }
            },
        )

        self.assertEqual(rows, [])

    def test_sql_projection_deduplicates_payload_attachment_files_by_item_and_name(self) -> None:
        payload = {
            "id": "oa-exp-payload-duplicates",
            "expense_items": [
                {
                    "expense_item_id": "oa-exp-payload-duplicates:item:1",
                    "row_index": "0",
                    "attachment_files": [
                        {
                            "fileName": "重复发票.pdf",
                            "filePath": "/重复发票.pdf",
                            "suffix": "pdf",
                        },
                        {
                            "fileName": "重复发票.pdf",
                            "filePath": "/重复发票.pdf",
                            "suffix": "pdf",
                        },
                    ],
                }
            ],
        }

        evidences = WorkbenchSqlProjectionBuilder._attachment_evidences_from_expense_items(payload)

        self.assertEqual(len(evidences), 1)
        self.assertEqual(evidences[0]["source_attachment_name"], "重复发票.pdf")

    def test_sql_projection_keeps_attachment_invoice_rows_source_bound_to_parent_oa(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-left": {
                "id": "oa-left",
                "type": "oa",
                "source_kind": "oa",
                "status": "open",
                "amount": "100.00",
                "counterparty_name": "供应商A",
                "apply_type": "付款",
                "pay_receive_time": "2026-02-10",
            },
            "oa-right": {
                "id": "oa-right",
                "type": "oa",
                "source_kind": "oa",
                "status": "open",
                "amount": "100.00",
                "counterparty_name": "供应商A",
                "apply_type": "付款",
                "pay_receive_time": "2026-02-10",
            },
            "oa-left-att-inv": {
                "id": "oa-left-att-inv",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "status": "open",
                "derived_from_oa_id": "oa-left",
                "seller_name": "供应商A",
                "buyer_name": "云南溯源科技有限公司",
                "invoice_type": "进项发票",
                "amount": "100.00",
                "total_with_tax": "100.00",
                "issue_date": "2026-02-10",
            },
        }

        payload = builder._group_payload("2026-02", rows_by_id, [])
        groups = payload["open"]["groups"]
        linked_groups = [
            group
            for group in groups
            if any(row.get("source_kind") == "oa_attachment_invoice" for row in group["invoice_rows"])
        ]

        self.assertEqual(len(linked_groups), 1)
        self.assertEqual([row["id"] for row in linked_groups[0]["oa_rows"]], ["oa-left"])
        self.assertEqual(
            {row["derived_from_oa_id"] for row in linked_groups[0]["invoice_rows"]},
            {"oa-left"},
        )

    def test_sql_projection_rebuilds_candidate_matches_from_sql_rows(self) -> None:
        recorder = CandidateSnapshotRecorder()
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=recorder,
        )
        rows_by_id = {
            "oa-1": {
                "id": "oa-1",
                "type": "oa",
                "source_kind": "oa",
                "amount": "100.00",
                "counterparty_name": "杭州测试供应商",
                "application_date": "2026-05-10",
                "project_name": "测试项目",
                "reason": "测试采购",
            },
            "bank-1": {
                "id": "bank-1",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "100.00",
                "counterparty_name": "杭州测试供应商",
                "trade_time": "2026-05-11 10:00",
                "summary": "测试采购付款",
            },
        }

        payload = builder._group_payload("2026-05", rows_by_id, [])

        snapshot, months = recorder.saved_snapshots[-1]
        candidates = snapshot["candidates"]
        self.assertEqual(months, {"2026-05"})
        self.assertTrue(any(candidate["status"] == "incomplete" for candidate in candidates.values()))
        open_rows = [
            row
            for group in payload["open"]["groups"]
            for row in [*group.get("oa_rows", []), *group.get("bank_rows", [])]
        ]
        self.assertEqual({row["id"] for row in open_rows}, {"oa-1", "bank-1"})
        self.assertTrue(all(str(row.get("case_id", "")).startswith("candidate:") for row in open_rows))
        self.assertTrue(any(group["group_type"] == "candidate" for group in payload["open"]["groups"]))

    def test_sql_projection_active_no_oa_relation_uses_grouping_contract(self) -> None:
        recorder = CandidateSnapshotRecorder()
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=recorder,
        )
        rows_by_id = {
            "bank-a": {
                "id": "bank-a",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "12.00",
                "trade_time": "2026-05-01 09:00",
                "counterparty_name": "手续费",
            },
            "bank-b": {
                "id": "bank-b",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "8.00",
                "trade_time": "2026-05-02 09:00",
                "counterparty_name": "手续费",
            },
        }
        relation = {
            "case_id": "CASE-NO-OA-1",
            "relation_mode": "no_oa_bank_batch",
            "row_ids": ["bank-a", "bank-b"],
            "row_types": ["bank", "bank"],
        }

        payload = builder._group_payload("2026-05", rows_by_id, [relation])

        paired = payload["paired"]["groups"]
        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0]["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(paired[0]["bank_rows"][0]["invoice_relation"]["code"], "no_oa_bank_batch")

    def test_sql_projection_applies_row_overrides_before_grouping(self) -> None:
        recorder = CandidateSnapshotRecorder()
        connection = WorkbenchProjectionSettingsConnection(
            overrides=[
                {
                    "row_id": "bank-override",
                    "override_payload": {
                        "ignored": True,
                        "case_id": "CASE-OVERRIDE-1",
                        "relation": {"code": "manual_exception", "label": "人工异常", "tone": "danger"},
                    },
                }
            ]
        )
        builder = WorkbenchSqlProjectionBuilder(connection=connection, read_model_repository=recorder)
        rows_by_id = {
            "bank-override": {
                "id": "bank-override",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "10.00",
                "counterparty_name": "供应商",
            }
        }

        payload = builder._group_payload("2026-05", rows_by_id, [])

        row = payload["open"]["groups"][0]["bank_rows"][0]
        self.assertTrue(row["ignored"])
        self.assertEqual(row["case_id"], "CASE-OVERRIDE-1")
        self.assertEqual(row["invoice_relation"]["code"], "manual_exception")

    def test_sql_projection_applies_active_exception_case_projection(self) -> None:
        recorder = CandidateSnapshotRecorder()
        connection = WorkbenchProjectionSettingsConnection(
            exception_cases=[
                {
                    "case_id": "CASE-EXCEPTION-1",
                    "raw_payload": {
                        "case_id": "CASE-EXCEPTION-1",
                        "id": "CASE-EXCEPTION-1",
                        "status": "confirmed",
                        "exception_code": "bank_fee",
                        "exception_label": "银行手续费",
                        "category": "bank",
                        "row_ids": ["bank-exception"],
                        "row_types": ["bank"],
                        "scope_months": ["2026-05"],
                        "resolution": {"action_code": "manual_review"},
                    },
                }
            ]
        )
        builder = WorkbenchSqlProjectionBuilder(connection=connection, read_model_repository=recorder)
        rows_by_id = {
            "bank-exception": {
                "id": "bank-exception",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "10.00",
                "counterparty_name": "银行",
            }
        }

        payload = builder._group_payload("2026-05", rows_by_id, [])

        row = payload["open"]["groups"][0]["bank_rows"][0]
        self.assertEqual(row["exception_case_id"], "CASE-EXCEPTION-1")
        self.assertEqual(row["case_id"], "CASE-EXCEPTION-1")
        self.assertEqual(row["invoice_relation"]["tone"], "danger")


if __name__ == "__main__":
    unittest.main()
