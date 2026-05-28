from __future__ import annotations

import json
from http import HTTPStatus
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.app_health_service import AppHealthService
from fin_ops_platform.services.postgres_repositories.read_models import (
    WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION,
    PostgresReadModelRepository,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_CONSUMED,
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DISPLAY_STATE_OPEN,
    DISPLAY_STATE_PAIRED,
    MATCH_DOMAIN_FREE,
    WARNING_INVOICE_AMOUNT_MISMATCH,
)
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
        if "read_model.workbench_group_rows" in normalized and "as oa_count" in normalized:
            return {"oa_count": 3, "bank_count": 4, "invoice_count": 5}
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
        if "from read_model.workbench_groups" in normalized and ("group by zone" in normalized or "group by g.zone" in normalized):
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
                        "invoice_rows": [
                            {
                                "id": "oa-att-inv-summary-1",
                                "type": "invoice",
                                "source_kind": "oa_attachment_invoice",
                                "issue_date": "2026-03-28",
                                "detail_fields": {
                                    "发票代码": "053002200111",
                                    "发票号码": "40512344",
                                    "数电发票号码": "—",
                                    "税率": "6%",
                                    "税额": "22.64",
                                },
                            }
                        ],
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
                    "diagnostics": {
                        "bank_detail_count": 999,
                        "ignored_bank_count": 888,
                        "bank_detail_reconciliation_status": "stale",
                    },
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
        return super().fetch_all(sql, params)


class ActiveWorkbenchGenerationConnection(WorkbenchSummaryGroupsConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_generations" in normalized and "status = 'active'" in normalized:
            self.fetch_one_calls.append((normalized, params))
            return {"generation_id": "gen-active"}
        return super().fetch_one(sql, params)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_generations" in normalized:
            self.fetch_all_calls.append((normalized, params))
            return [
                {
                    "generation_id": "gen-active",
                    "status": "active",
                    "activated_at": "2026-05-28T09:00:00+00:00",
                    "source_versions": {"source_version": 12},
                    "row_count": 100,
                    "group_count": 20,
                    "build_metadata": {},
                }
            ]
        return super().fetch_all(sql, params)


class FailedWorkbenchGenerationConnection(WorkbenchSummaryGroupsConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_generations" in normalized:
            self.fetch_all_calls.append((normalized, params))
            return [
                {
                    "generation_id": "gen-active",
                    "status": "active",
                    "activated_at": "2026-05-28T09:00:00+00:00",
                    "source_versions": {"source_version": 12},
                    "row_count": 100,
                    "group_count": 20,
                    "build_metadata": {},
                },
                {
                    "generation_id": "gen-failed",
                    "status": "failed",
                    "completed_at": "2026-05-28T09:01:00+00:00",
                    "last_error": "projection failed",
                    "source_versions": {"source_version": 13},
                    "build_metadata": {},
                },
            ]
        return super().fetch_all(sql, params)


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str]] = []
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def enqueue(self, **kwargs):
        self.enqueued.append(dict(kwargs))
        return RuntimeQueueEvent(
            event_id=f"event-{len(self.enqueued)}",
            tenant_id="default",
            event_type=str(kwargs.get("event_type") or ""),
            aggregate_type=kwargs.get("aggregate_type"),
            aggregate_id=kwargs.get("aggregate_id"),
            scope_type=kwargs.get("scope_type"),
            scope_key=kwargs.get("scope_key"),
            dedupe_key=kwargs.get("dedupe_key"),
            payload=dict(kwargs.get("payload") or {}),
            attempts=0,
            status="pending",
        )


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


class InvoiceRowsProjectionConnection(WorkbenchProjectionSettingsConnection):
    def __init__(self, *, raw_payload_only: bool = False) -> None:
        super().__init__()
        self.raw_payload_only = raw_payload_only

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.invoices" not in normalized:
            return super().fetch_all(sql, params)

        row = {
            "row_id": "inv-manual-tax-001",
            "invoice_type": "进项发票",
            "invoice_no": "26532000000141671581",
            "digital_invoice_no": "26532000000141671581",
            "invoice_date": "2026-01-27",
            "counterparty_name": "云南建筑技术发展中心",
            "seller_name": "云南建筑技术发展中心",
            "buyer_name": "云南溯源科技有限公司",
            "amount": "377.36",
            "total_with_tax": "400.00",
            "status": "active",
            "raw_payload": {"税率": "6%", "税额": "22.64"} if self.raw_payload_only else {},
        }
        if "tax_rate" in normalized and not self.raw_payload_only:
            row["tax_rate"] = "6%"
        if "tax_amount" in normalized and not self.raw_payload_only:
            row["tax_amount"] = "22.64"
        return [row]


class EtcSummaryProjectionConnection(WorkbenchProjectionSettingsConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "with submitted_batches as" in normalized and "from app.invoices invoices" in normalized:
            return [
                {
                    "external_etc_batch_id": "ETC-OA-20260215-154900",
                    "row_id": "inv-hidden-etc-1",
                    "invoice_type": "进项发票",
                    "invoice_no": "26537911970100000001",
                    "digital_invoice_no": "26537911970100000001",
                    "invoice_date": "2026-01-03",
                    "counterparty_name": "高速公路通行费",
                    "seller_name": "高速公路通行费",
                    "buyer_name": "云南溯源科技",
                    "amount": "100.00",
                    "total_with_tax": "100.00",
                    "status": "submitted",
                    "workbench_visibility": "hidden_after_etc_submission",
                    "raw_payload": {"workbench_visibility": "hidden_after_etc_submission"},
                },
                {
                    "external_etc_batch_id": "ETC-OA-20260215-154900",
                    "row_id": "inv-hidden-etc-2",
                    "invoice_type": "进项发票",
                    "invoice_no": "26537911970100000002",
                    "digital_invoice_no": "26537911970100000002",
                    "invoice_date": "2026-01-05",
                    "counterparty_name": "高速公路通行费",
                    "seller_name": "高速公路通行费",
                    "buyer_name": "云南溯源科技",
                    "amount": "44.50",
                    "total_with_tax": "44.50",
                    "status": "submitted",
                    "workbench_visibility": "hidden_after_etc_submission",
                    "raw_payload": {"workbench_visibility": "hidden_after_etc_submission"},
                },
            ]
        return super().fetch_all(sql, params)


class CandidateSnapshotRecorder:
    def __init__(self, *, reconciliation_decisions: list[dict[str, object]] | None = None) -> None:
        self.saved_snapshots: list[tuple[dict[str, object], set[str] | None]] = []
        self.reconciliation_decisions = list(reconciliation_decisions or [])

    def save_workbench_candidate_matches(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_months: set[str] | None = None,
    ) -> None:
        self.saved_snapshots.append((snapshot, changed_scope_months))

    def list_workbench_reconciliation_decisions(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        statuses: set[str] | None = None,
    ) -> list[dict[str, object]]:
        status_filter = set(statuses or [])
        return [
            dict(decision)
            for decision in self.reconciliation_decisions
            if decision.get("scope_month") == scope_month
            and (not status_filter or decision.get("decision_status") in status_filter)
        ]


def reconciliation_decision_payload(
    decision_key: str,
    *,
    status: str,
    display_state: str,
    row_ids: list[str],
    warnings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "decision_id": decision_key,
        "decision_key": decision_key,
        "scope_month": "2026-05",
        "display_state": display_state,
        "decision_status": status,
        "match_domain": MATCH_DOMAIN_FREE,
        "match_shape": "oa_bank_invoice" if any(row_id.startswith("invoice-") for row_id in row_ids) else "oa_bank",
        "rule_code": "free.test",
        "rule_version": "test",
        "row_ids": list(row_ids),
        "oa_row_ids": [row_id for row_id in row_ids if row_id.startswith("oa-")],
        "bank_row_ids": [row_id for row_id in row_ids if row_id.startswith("bank-")],
        "invoice_row_ids": [row_id for row_id in row_ids if row_id.startswith("invoice-")],
        "amount": "100.00",
        "direction": "expense",
        "payment_amount_closed": True,
        "invoice_amount_closed": display_state == DISPLAY_STATE_PAIRED,
        "warnings": list(warnings or []),
        "evidence": {"source": "unit-test"},
        "blockers": [],
        "source_versions": {"rules": "v1"},
    }


class FakeWorkbenchReadModelService:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_read_model(self, scope_key: str) -> None:
        self.deleted.append(scope_key)


class WorkbenchSqlRuntimeTests(unittest.TestCase):
    def test_workbench_api_queues_oa_sync_when_sql_snapshot_parser_version_is_stale(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)
        app._workbench_query_service = SimpleNamespace(_oa_adapter=object())
        app._workbench_sql_read_repository = PostgresReadModelRepository(
            WorkbenchSqlReadConnection(
                snapshot_row={
                    "scope_key": "2026-03",
                    "scope_month": "2026-03-01",
                    "source_versions": {
                        "builder": "old-builder",
                        "oa_attachment_invoice_parser_version": "old-parser",
                        "oa_projection_sync_version": app._current_oa_projection_sync_version(),
                    },
                    "generated_at": "2026-05-28T10:00:00+08:00",
                    "cache_status": "fresh",
                    "row_count": 1,
                    "payload": {
                        "month": "2026-03",
                        "oa_status": {"code": "ready", "message": "OA projection ready"},
                        "summary": {
                            "oa_count": 1,
                            "bank_count": 0,
                            "invoice_count": 0,
                            "paired_count": 0,
                            "open_count": 1,
                            "exception_count": 0,
                        },
                        "paired": {"groups": []},
                        "open": {"groups": []},
                    },
                }
            )
        )

        response = app._handle_api_workbench("2026-03")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_refresh_reason"], "oa_attachment_invoice_parser_version_changed")
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(len(queue.enqueued), 1)
        event = queue.enqueued[0]
        expected_parser_version = app._current_oa_attachment_invoice_parser_version()
        self.assertEqual(event["event_type"], "oa.sync")
        self.assertEqual(event["scope_key"], "2026-03")
        self.assertEqual(event["dedupe_key"], f"oa.sync:2026-03:attachment-parser:{expected_parser_version}")
        expected_projection_version = app._current_oa_projection_sync_version()
        self.assertEqual(
            event["payload"],
            {
                "scope_key": "2026-03",
                "triggered_by": "system",
                "reason": "oa_attachment_invoice_parser_version_changed",
                "oa_attachment_invoice_parser_version": expected_parser_version,
                "oa_projection_sync_version": expected_projection_version,
            },
        )

    def test_workbench_api_queues_oa_sync_when_sql_snapshot_projection_sync_version_is_stale(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)
        app._workbench_query_service = SimpleNamespace(_oa_adapter=object())
        app._workbench_sql_read_repository = PostgresReadModelRepository(
            WorkbenchSqlReadConnection(
                snapshot_row={
                    "scope_key": "2026-03",
                    "scope_month": "2026-03-01",
                    "source_versions": {
                        "oa_attachment_invoice_parser_version": app._current_oa_attachment_invoice_parser_version(),
                        "oa_projection_sync_version": "old-projection-sync",
                    },
                    "generated_at": "2026-05-28T10:00:00+08:00",
                    "cache_status": "fresh",
                    "row_count": 1,
                    "payload": {
                        "month": "2026-03",
                        "oa_status": {"code": "ready", "message": "OA projection ready"},
                        "summary": {"oa_count": 2, "bank_count": 0, "invoice_count": 1, "paired_count": 1, "open_count": 2, "exception_count": 0},
                        "paired": {"groups": []},
                        "open": {"groups": []},
                    },
                }
            )
        )

        response = app._handle_api_workbench("2026-03")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_refresh_reason"], "oa_projection_sync_version_changed")
        self.assertEqual(len(queue.enqueued), 1)
        event = queue.enqueued[0]
        expected_projection_version = app._current_oa_projection_sync_version()
        self.assertEqual(event["event_type"], "oa.sync")
        self.assertEqual(event["dedupe_key"], f"oa.sync:2026-03:projection:{expected_projection_version}")
        self.assertEqual(event["payload"]["reason"], "oa_projection_sync_version_changed")
        self.assertEqual(event["payload"]["oa_projection_sync_version"], expected_projection_version)

    def test_sql_projection_manual_invoice_rows_include_tax_meta_for_amount_cell(self) -> None:
        connection = InvoiceRowsProjectionConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        rows = builder._invoice_rows("2026-01")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount"], "377.36")
        self.assertEqual(rows[0]["tax_rate"], "6%")
        self.assertEqual(rows[0]["tax_amount"], "22.64")
        self.assertEqual(rows[0]["summary_fields"]["税率"], "6%")
        self.assertEqual(rows[0]["summary_fields"]["税额"], "22.64")

    def test_sql_projection_manual_invoice_rows_fall_back_to_raw_payload_tax_meta(self) -> None:
        connection = InvoiceRowsProjectionConnection(raw_payload_only=True)
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        rows = builder._invoice_rows("2026-01")

        self.assertEqual(rows[0]["tax_rate"], "6%")
        self.assertEqual(rows[0]["tax_amount"], "22.64")
        self.assertEqual(rows[0]["summary_fields"]["税率"], "6%")
        self.assertEqual(rows[0]["summary_fields"]["税额"], "22.64")

    def test_sql_projection_attaches_existing_etc_summary_to_active_relation(self) -> None:
        connection = EtcSummaryProjectionConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)
        rows_by_id = {
            "oa-exp-1994": {
                "id": "oa-exp-1994",
                "type": "oa",
                "applicant": "刘树刚",
                "project_name": "云南溯源科技",
                "amount": "1549.00",
            },
            "txn_imported_1328": {
                "id": "txn_imported_1328",
                "type": "bank",
                "source_kind": "bank_transaction",
                "debit_amount": "1549.00",
                "counterparty_name": "批量账务集中处理",
            },
        }
        relation = {
            "case_id": "CASE-BATCH-txn_imported_1328",
            "relation_mode": "manual_confirmed",
            "row_ids": ["txn_imported_1328", "oa-exp-1994"],
            "row_types": ["bank", "oa"],
            "amount_check": {
                "external_etc_batch_id": "ETC-OA-20260215-154900",
                "invoice_count": 2,
                "invoice_total": "144.50",
                "status": "mismatch",
            },
        }

        payload = builder._group_payload("2026-02", rows_by_id, [relation])

        groups = payload["paired"]["groups"]
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group["group_id"], "case:CASE-BATCH-txn_imported_1328")
        self.assertEqual(len(group["oa_rows"]), 1)
        self.assertEqual(len(group["bank_rows"]), 1)
        self.assertEqual(len(group["invoice_rows"]), 1)
        oa_row = group["oa_rows"][0]
        self.assertEqual(oa_row["etc_batch_id"], "ETC-OA-20260215-154900")
        self.assertIn("ETC批量提交", oa_row["tags"])
        summary_row = group["invoice_rows"][0]
        self.assertEqual(summary_row["source_kind"], "etc_invoice_summary")
        self.assertEqual(summary_row["case_id"], "CASE-BATCH-txn_imported_1328")
        self.assertEqual(summary_row["invoice_bank_relation"]["label"], "已关联ETC发票")
        self.assertEqual(summary_row["etc_invoice_count"], 2)
        self.assertEqual(summary_row["total_with_tax"], "144.50")

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
            any("jsonb_array_length(payload->'bank_rows')" in sql for sql, _params in connection.fetch_all_calls)
        )
        self.assertFalse(
            any(
                "from read_model.workbench_snapshots" in sql and "payload, raw_payload" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_repository_repairs_materialized_workbench_summary_counts_from_structured_rows(self) -> None:
        connection = MaterializedWorkbenchSummaryConnection()
        repository = PostgresReadModelRepository(connection)

        summary = repository.get_workbench_summary(scope_key="all")

        self.assertEqual(summary["summary"]["oa_count"], 3)
        self.assertEqual(summary["summary"]["bank_count"], 4)
        self.assertEqual(summary["summary"]["invoice_count"], 5)
        self.assertEqual(summary["summary"]["paired_count"], 1)
        self.assertEqual(summary["summary"]["open_count"], 2)
        self.assertEqual(summary["diagnostics"]["bank_detail_count"], 4)
        self.assertEqual(summary["diagnostics"]["ignored_bank_count"], 0)
        self.assertEqual(summary["diagnostics"]["bank_detail_reconciliation_status"], "unavailable")
        self.assertEqual(summary["invoice_inventory"]["system_total"], 99)
        self.assertEqual(summary["read_model_status"], "fresh")
        self.assertTrue(any("from read_model.workbench_summary" in sql for sql, _params in connection.fetch_one_calls))
        self.assertTrue(
            any(
                "from read_model.workbench_groups" in sql
                and "left join read_model.workbench_group_rows" in sql
                and "coalesce(r.row_role, '') <> 'summary'" in sql
                and "coalesce(r.source_kind, '') <> 'no_oa_bank_batch_summary'" in sql
                for sql, _params in connection.fetch_all_calls
            )
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

    def test_repository_pins_workbench_groups_page_to_active_generation(self) -> None:
        connection = ActiveWorkbenchGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(scope_key="all", zone="open", page=1, page_size=25)

        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        self.assertEqual(page["active_generation_id"], "gen-active")
        self.assertEqual(page["read_model_version"], "gen-active")
        self.assertTrue(any("g.generation_id = %s" in sql and "gen-active" in params for sql, params in all_queries))
        self.assertTrue(any("r.generation_id = g.generation_id" in sql for sql, _params in all_queries))

    def test_repository_workbench_groups_cache_version_uses_active_generation(self) -> None:
        connection = ActiveWorkbenchGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        version = repository.workbench_groups_cache_version(scope_key="all")

        self.assertEqual(version, "gen-active")
        self.assertFalse(
            any(
                "max((source_versions->>'source_version')::bigint)" in sql
                for sql, _params in connection.fetch_one_calls
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

    def test_repository_intersects_pane_search_with_structured_group_row_filters(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=25,
            search_by_pane={"bank": "建行"},
            column_filters={"bank": {"amount": ["支出"]}},
        )

        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        group_row_queries = [(sql, params) for sql, params in all_queries if "read_model.workbench_group_rows" in sql]
        self.assertTrue(group_row_queries)
        self.assertTrue(any("r.searchable_text ilike %s" in sql for sql, _params in group_row_queries))
        self.assertTrue(
            any(
                "%建行%" in params
                and '"direction": "支出"' in str(params)
                for _sql, params in group_row_queries
            )
        )

    def test_repository_filters_linked_context_search_from_any_structured_group_row(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=25,
            search="花",
            search_mode="linked_context",
            column_filters={"bank": {"amount": ["支出"]}},
        )

        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        group_row_queries = [(sql, params) for sql, params in all_queries if "read_model.workbench_group_rows" in sql]
        self.assertTrue(group_row_queries)
        self.assertTrue(
            any(
                "r_linked_search.searchable_text ilike %s" in sql
                and "%花%" in params
                for sql, params in group_row_queries
            )
        )
        self.assertTrue(
            any(
                "r.pane = %s" in sql
                and "bank" in params
                and '"direction": "支出"' in str(params)
                for sql, params in group_row_queries
            )
        )

    def test_repository_requires_all_selected_filter_values_in_structured_group_row_sql(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=25,
            column_filters={"bank": {"amount": ["支出", "建行 8106"]}},
        )

        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        group_row_queries = [(sql, params) for sql, params in all_queries if "read_model.workbench_group_rows" in sql]
        self.assertTrue(group_row_queries)
        self.assertTrue(
            any(
                "(r.column_values @> %s::jsonb or r.column_values @> %s::jsonb) and "
                "(r.column_values @> %s::jsonb or r.column_values @> %s::jsonb)" in sql
                and '"direction": "支出"' in str(params)
                and '"paymentAccount": "建行 8106"' in str(params)
                for sql, params in group_row_queries
            )
        )

    def test_repository_filters_summary_preview_rows_with_intersected_pane_criteria(self) -> None:
        class PreviewRowsConnection(WorkbenchSummaryGroupsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_groups" in normalized and "group by zone" not in normalized:
                    return [
                        {
                            "group_id": "case:preview",
                            "zone": "open",
                            "payload": {
                                "group_id": "case:preview",
                                "group_type": "candidate",
                                "match_confidence": "medium",
                                "reason": "preview filter",
                                "oa_rows": [],
                                "bank_rows": [
                                    {
                                        "id": "bank-income-ccb",
                                        "type": "bank",
                                        "direction": "收入",
                                        "payment_account_label": "建行 8106",
                                        "counterparty_name": "建行客户",
                                    },
                                    {
                                        "id": "bank-expense-ms",
                                        "type": "bank",
                                        "direction": "支出",
                                        "payment_account_label": "民生 9486",
                                        "counterparty_name": "民生供应商",
                                    },
                                    {
                                        "id": "bank-expense-ccb",
                                        "type": "bank",
                                        "direction": "支出",
                                        "payment_account_label": "建行 8106",
                                        "counterparty_name": "建行供应商",
                                    },
                                ],
                                "invoice_rows": [],
                            },
                        }
                    ]
                return super().fetch_all(sql, params)

        connection = PreviewRowsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=25,
            detail_level="summary",
            search_by_pane={"bank": "建行"},
            column_filters={"bank": {"amount": ["支出"]}},
        )

        group = page["groups"][0]
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-expense-ccb"])
        self.assertEqual(group["row_counts"]["bank"], 3)

    def test_repository_requires_all_selected_bank_amount_filter_values_on_same_row(self) -> None:
        class PreviewRowsConnection(WorkbenchSummaryGroupsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_groups" in normalized and "group by zone" not in normalized:
                    return [
                        {
                            "group_id": "case:preview",
                            "zone": "open",
                            "payload": {
                                "group_id": "case:preview",
                                "group_type": "candidate",
                                "match_confidence": "medium",
                                "reason": "preview filter",
                                "oa_rows": [],
                                "bank_rows": [
                                    {
                                        "id": "bank-income-ccb",
                                        "type": "bank",
                                        "direction": "收入",
                                        "payment_account_label": "建行 8106",
                                        "counterparty_name": "建行客户",
                                    },
                                    {
                                        "id": "bank-expense-ms",
                                        "type": "bank",
                                        "direction": "支出",
                                        "payment_account_label": "民生 9486",
                                        "counterparty_name": "民生供应商",
                                    },
                                    {
                                        "id": "bank-expense-ccb",
                                        "type": "bank",
                                        "direction": "支出",
                                        "payment_account_label": "建行 8106",
                                        "counterparty_name": "建行供应商",
                                    },
                                ],
                                "invoice_rows": [],
                            },
                        }
                    ]
                return super().fetch_all(sql, params)

        connection = PreviewRowsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=25,
            detail_level="summary",
            column_filters={"bank": {"amount": ["支出", "建行 8106"]}},
        )

        group = page["groups"][0]
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-expense-ccb"])

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
        self.assertEqual(group["row_counts"], {"oa": 9, "bank": 0, "invoice": 1, "rows": 10})
        self.assertEqual(group["display_row_counts"], {"oa": 5, "bank": 0, "invoice": 1, "rows": 6})
        self.assertEqual(group["collapsed_row_counts"], {"oa": 4})
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-1", "oa-2", "oa-3", "oa-4", "oa-5"])
        self.assertEqual(group["invoice_rows"][0]["invoice_code"], "053002200111")
        self.assertEqual(group["invoice_rows"][0]["invoice_no"], "40512344")
        self.assertEqual(group["invoice_rows"][0]["digital_invoice_no"], "—")
        self.assertEqual(group["invoice_rows"][0]["tax_rate"], "6%")
        self.assertEqual(group["invoice_rows"][0]["tax_amount"], "22.64")
        self.assertNotIn("detail_fields", group["invoice_rows"][0])
        self.assertEqual([row["id"] for row in group["collapsed_rows"]["oa"]], ["collapsed-oa-1", "collapsed-oa-2", "collapsed-oa-3"])
        self.assertEqual(group["oa_rows"][0]["id"], "oa-1")
        self.assertEqual(page["row_counts"], {"oa": 3, "bank": 4, "invoice": 5, "rows": 12})
        self.assertNotIn("detail_fields", group["oa_rows"][0])
        self.assertNotIn("raw_payload", group)

    def test_repository_groups_page_row_counts_use_fact_rows_before_pagination(self) -> None:
        class FactRowCountsConnection(WorkbenchSummaryGroupsConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_groups g" in normalized and "count(*) as total_count" in normalized:
                    return {"total_count": 2}
                if "read_model.workbench_group_rows" in normalized and "as oa_count" in normalized:
                    return {"oa_count": 1, "bank_count": 3, "invoice_count": 0}
                return super().fetch_one(sql, params)

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_groups" in normalized and "group by" not in normalized:
                    return [
                        {
                            "group_id": "case:first-page",
                            "zone": "paired",
                            "payload": {
                                "group_id": "case:first-page",
                                "group_type": "candidate",
                                "match_confidence": "medium",
                                "reason": "first page",
                                "oa_rows": [{"id": "oa-1", "type": "oa"}],
                                "bank_rows": [
                                    {
                                        "id": "no_oa_summary:batch-1",
                                        "type": "bank",
                                        "source_kind": "no_oa_bank_batch_summary",
                                    }
                                ],
                                "invoice_rows": [],
                                "collapsed_rows": {
                                    "bank": [
                                        {"id": "bank-1", "type": "bank", "source_kind": "bank"},
                                        {"id": "bank-2", "type": "bank"},
                                    ]
                                },
                            },
                        }
                    ]
                return super().fetch_all(sql, params)

        connection = FactRowCountsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(scope_key="all", zone="paired", page=1, page_size=1)

        self.assertEqual(page["total"], 2)
        self.assertEqual(page["row_counts"], {"oa": 1, "bank": 3, "invoice": 0, "rows": 4})
        self.assertEqual(len(page["groups"]), 1)
        self.assertFalse(
            any("jsonb_array_length(payload->'bank_rows')" in sql for sql, _params in connection.fetch_one_calls)
        )
        self.assertTrue(
            any(
                "coalesce(r.row_role, '') <> 'summary'" in sql
                and
                "coalesce(r.source_kind, '') <> 'no_oa_bank_batch_summary'" in sql
                for sql, _params in connection.fetch_one_calls
            )
        )

    def test_repository_groups_page_row_counts_apply_pane_row_filters(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=25,
            search_by_pane={"bank": "建行"},
            column_filters={"bank": {"amount": ["支出"]}},
            time_filters={"bank": {"mode": "month", "month": "2026-04"}},
        )

        row_count_queries = [
            (sql, params)
            for sql, params in connection.fetch_one_calls
            if "count(distinct r.row_id) filter" in sql
        ]
        self.assertTrue(row_count_queries)
        self.assertTrue(
            any(
                "r.column_values @> %s::jsonb" in sql
                and "r.time_date >= %s::date and r.time_date < %s::date" in sql
                and "r.searchable_text ilike %s" in sql
                and '"direction": "支出"' in str(params)
                and "2026-04-01" in str(params)
                and "%建行%" in params
                for sql, params in row_count_queries
            )
        )

    def test_repository_summary_diagnostics_reconciles_bank_detail_and_ignored_counts(self) -> None:
        class DiagnosticsConnection(WorkbenchSummaryGroupsConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from app.bank_transactions" in normalized:
                    return {"bank_detail_count": 5}
                if "from read_model.workbench_rows" in normalized and "ignored_bank_count" in normalized:
                    return {"ignored_bank_count": 1}
                return super().fetch_one(sql, params)

        connection = DiagnosticsConnection()
        repository = PostgresReadModelRepository(connection)

        summary = repository.get_workbench_summary(scope_key="all")

        self.assertEqual(summary["summary"]["bank_count"], 4)
        self.assertEqual(
            summary["summary"]["bank_count"],
            summary["summary"]["zone_counts"]["paired"]["bank"] + summary["summary"]["zone_counts"]["open"]["bank"],
        )
        self.assertEqual(summary["diagnostics"]["bank_detail_count"], 5)
        self.assertEqual(summary["diagnostics"]["ignored_bank_count"], 1)
        self.assertEqual(
            summary["diagnostics"]["bank_detail_count"],
            summary["summary"]["bank_count"] + summary["diagnostics"]["ignored_bank_count"],
        )
        self.assertEqual(summary["diagnostics"]["bank_detail_reconciliation_status"], "matched")
        self.assertTrue(
            any(
                "source_kind in ('bank', 'bank_transaction')" in sql
                for sql, _params in connection.fetch_one_calls
            )
        )

    def test_repository_group_detail_returns_fact_and_display_counts_for_collapsed_bank_rows(self) -> None:
        class CollapsedGroupDetailConnection(WorkbenchSummaryGroupsConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_groups" in normalized and "group_id = %s" in normalized:
                    return {
                        "group_id": "case:no-oa",
                        "zone": "paired",
                        "payload": {
                            "group_id": "case:no-oa",
                            "group_type": "auto_closed",
                            "match_confidence": "high",
                            "reason": "detail",
                            "oa_rows": [],
                            "bank_rows": [
                                {
                                    "id": "no_oa_summary:batch-1",
                                    "type": "bank",
                                    "source_kind": "no_oa_bank_batch_summary",
                                }
                            ],
                            "invoice_rows": [],
                            "collapsed_rows": {
                                "bank": [
                                    {"id": "bank-1", "type": "bank", "source_kind": "bank"},
                                    {"id": "bank-2", "type": "bank"},
                                ]
                            },
                        },
                    }
                return super().fetch_one(sql, params)

        connection = CollapsedGroupDetailConnection()
        repository = PostgresReadModelRepository(connection)

        group = repository.get_workbench_group_detail(scope_key="all", zone="paired", group_id="case:no-oa")

        assert group is not None
        self.assertEqual(group["row_counts"], {"oa": 0, "bank": 2, "invoice": 0, "rows": 2})
        self.assertEqual(group["display_row_counts"], {"oa": 0, "bank": 1, "invoice": 0, "rows": 1})
        self.assertEqual([row["id"] for row in group["collapsed_rows"]["bank"]], ["bank-1", "bank-2"])

    def test_repository_keeps_all_oa_attachment_invoice_rows_in_summary_page(self) -> None:
        class OaAttachmentInvoiceRowsConnection(WorkbenchSummaryGroupsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_groups" in normalized and "group by zone" not in normalized:
                    return [
                        {
                            "group_id": "case:oa-attachments-many",
                            "zone": "paired",
                            "payload": {
                                "group_id": "case:oa-attachments-many",
                                "group_type": "paired",
                                "match_confidence": "high",
                                "reason": "oa attachment invoices",
                                "oa_rows": [{"id": "oa-exp-many", "type": "oa", "source_kind": "oa"}],
                                "bank_rows": [],
                                "invoice_rows": [
                                    {
                                        "id": f"oa-att-inv-{index}",
                                        "type": "invoice",
                                        "source_kind": "oa_attachment_invoice",
                                        "invoice_no": f"OAATT{index:03d}",
                                    }
                                    for index in range(1, 6)
                                ],
                            },
                        }
                    ]
                return super().fetch_all(sql, params)

        connection = OaAttachmentInvoiceRowsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="paired",
            page=1,
            page_size=1,
            detail_level="summary",
        )

        group = page["groups"][0]
        self.assertEqual(group["row_counts"]["invoice"], 5)
        self.assertEqual(
            [row["id"] for row in group["invoice_rows"]],
            [f"oa-att-inv-{index}" for index in range(1, 6)],
        )

    def test_repository_filters_non_invoice_oa_attachment_evidence_from_summary_and_detail(self) -> None:
        polluted_group_payload = {
            "group_id": "case:oa-attachment-with-payment-receipt",
            "group_type": "source_linked",
            "match_confidence": "high",
            "reason": "oa attachment evidence",
            "oa_rows": [{"id": "oa-exp-payment", "type": "oa", "source_kind": "oa"}],
            "bank_rows": [],
            "invoice_rows": [
                {
                    "id": "oa-att-inv-formal",
                    "type": "invoice",
                    "source_kind": "oa_attachment_invoice",
                    "invoice_no": "FORMAL-001",
                },
                {
                    "id": "oa-att-pay-receipt",
                    "type": "invoice",
                    "source_kind": "oa_attachment_payment_receipt",
                },
                {
                    "id": "oa-att-unknown",
                    "type": "invoice",
                    "source_kind": "oa_attachment_unknown",
                },
            ],
        }

        class PollutedOaAttachmentEvidenceConnection(WorkbenchSummaryGroupsConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_groups" in normalized and "group_id = %s" in normalized:
                    return {
                        "group_id": "case:oa-attachment-with-payment-receipt",
                        "zone": "open",
                        "payload": polluted_group_payload,
                    }
                return super().fetch_one(sql, params)

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_groups" in normalized and "group by zone" not in normalized:
                    return [
                        {
                            "group_id": "case:oa-attachment-with-payment-receipt",
                            "zone": "open",
                            "payload": polluted_group_payload,
                        }
                    ]
                return super().fetch_all(sql, params)

        connection = PollutedOaAttachmentEvidenceConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="open",
            page=1,
            page_size=1,
            detail_level="summary",
        )
        detail = repository.get_workbench_group_detail(
            scope_key="all",
            zone="open",
            group_id="case:oa-attachment-with-payment-receipt",
        )

        self.assertEqual([row["id"] for row in page["groups"][0]["invoice_rows"]], ["oa-att-inv-formal"])
        self.assertEqual([row["id"] for row in detail["invoice_rows"]], ["oa-att-inv-formal"])

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

    def test_repository_reports_failed_workbench_generation_without_promoting_it(self) -> None:
        connection = FailedWorkbenchGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        status = repository.get_workbench_refresh_status(scope_key="all")

        self.assertEqual(status["read_model_status"], "stale")
        self.assertEqual(status["active_generation_id"], "gen-active")
        self.assertEqual(status["failed_generation_id"], "gen-failed")
        self.assertEqual(status["last_error"], "projection failed")
        self.assertEqual(status["read_model_version"], "gen-active")

    def test_repository_marks_all_scope_groups_stale_when_aggregate_builder_changes(self) -> None:
        class StaleAggregateBuilderConnection(WorkbenchSummaryGroupsConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "as group_count" in normalized and "as current_group_count" in normalized:
                    return {"group_count": 2, "current_group_count": 0}
                return super().fetch_one(sql, params)

        connection = StaleAggregateBuilderConnection()
        repository = PostgresReadModelRepository(connection)

        status = repository.get_workbench_refresh_status(scope_key="all")

        self.assertEqual(status["read_model_status"], "stale")
        self.assertIn("builder_schema_mismatch", status["read_model_stale_reasons"])
        self.assertTrue(
            any(
                params and params[0] == WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION
                for _sql, params in connection.fetch_one_calls
            )
        )

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
        self.assertNotIn("delete from read_model.workbench_groups", sql)
        self.assertNotIn("delete from read_model.workbench_group_rows", sql)
        self.assertIn("insert into read_model.workbench_generations", sql)
        self.assertIn("insert into read_model.workbench_groups", sql)
        self.assertIn("insert into read_model.workbench_group_rows", sql)
        self.assertIn("insert into read_model.workbench_summary", sql)
        self.assertIn("on conflict (generation_id, scope_key, zone, group_id)", sql)
        self.assertIn("status = 'active'", sql)

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
            if "insert into read_model.workbench_groups" in sql and "values ( %s, %s, 'all'" in sql
        )
        group_payload = aggregate_group_insert[16].obj
        self.assertEqual(group_payload["row_count"], 4)
        self.assertEqual([row["id"] for row in group_payload["oa_rows"]], ["oa-1"])
        self.assertEqual([row["id"] for row in group_payload["bank_rows"]], ["bank-1"])
        self.assertEqual(
            [row["id"] for row in group_payload["invoice_rows"]],
            ["oa-att-inv-1", "oa-att-inv-2"],
        )
        self.assertEqual(group_payload["row_counts"], {"oa": 1, "bank": 1, "invoice": 2, "rows": 4})
        self.assertEqual(group_payload["display_row_counts"], {"oa": 1, "bank": 1, "invoice": 2, "rows": 4})
        self.assertNotIn("collapsed_row_counts", group_payload)
        aggregate_source_versions = next(
            params[14].obj
            for sql, params in connection.executed
            if "insert into read_model.workbench_groups" in sql and "values ( %s, %s, 'all'" in sql
        )
        self.assertEqual(aggregate_source_versions["builder"], WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION)

    def test_repository_persists_no_oa_collapsed_group_fact_and_display_counts(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {
                            "paired": {
                                "groups": [
                                    {
                                        "group_id": "case:NO-OA-BATCH",
                                        "group_type": "auto_closed",
                                        "match_confidence": "high",
                                        "reason": "免OA批次",
                                        "oa_rows": [],
                                        "bank_rows": [
                                            {
                                                "id": "no_oa_summary:batch-1",
                                                "type": "bank",
                                                "source_kind": "no_oa_bank_batch_summary",
                                                "summary": "免OA批次摘要",
                                            }
                                        ],
                                        "invoice_rows": [],
                                        "collapsed_rows": {
                                            "bank": [
                                                {"id": "bank-1", "type": "bank", "source_kind": "bank"},
                                                {"id": "bank-2", "type": "bank"},
                                                {"id": "bank-3", "type": "bank", "source_kind": ""},
                                            ]
                                        },
                                    }
                                ]
                            },
                            "open": {"groups": []},
                        },
                        "source_versions": {"source_version": 7},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        group_insert = next(
            params
            for sql, params in connection.executed
            if "insert into read_model.workbench_groups" in sql and params[1] == "case:NO-OA-BATCH"
        )
        group_payload = group_insert[19].obj
        self.assertEqual(group_insert[8], 3)
        self.assertEqual(group_payload["row_counts"], {"oa": 0, "bank": 3, "invoice": 0, "rows": 3})
        self.assertEqual(group_payload["display_row_counts"], {"oa": 0, "bank": 1, "invoice": 0, "rows": 1})

        group_row_roles = [
            (params[5], params[6], params[7], params[9])
            for sql, params in connection.executed
            if "insert into read_model.workbench_group_rows" in sql and params[4] == "case:NO-OA-BATCH"
        ]
        self.assertIn(("bank", "no_oa_summary:batch-1", "summary", "no_oa_bank_batch_summary"), group_row_roles)
        self.assertIn(("bank", "bank-1", "collapsed", "bank"), group_row_roles)

    def test_repository_treats_row_role_summary_as_display_only_even_with_bank_source_kind(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {
                            "paired": {
                                "groups": [
                                    {
                                        "group_id": "case:ROLE-SUMMARY",
                                        "group_type": "auto_closed",
                                        "oa_rows": [],
                                        "bank_rows": [
                                            {
                                                "id": "summary-bank-source-kind",
                                                "type": "bank",
                                                "source_kind": "bank",
                                                "row_role": "summary",
                                            }
                                        ],
                                        "invoice_rows": [],
                                        "collapsed_rows": {
                                            "bank": [
                                                {"id": "bank-1", "type": "bank", "source_kind": "bank"},
                                                {"id": "bank-2", "type": "bank", "source_kind": "bank"},
                                            ]
                                        },
                                    }
                                ]
                            },
                            "open": {"groups": []},
                        },
                        "source_versions": {"source_version": 8},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        group_insert = next(
            params
            for sql, params in connection.executed
            if "insert into read_model.workbench_groups" in sql and params[1] == "case:ROLE-SUMMARY"
        )
        group_payload = group_insert[19].obj
        self.assertEqual(group_payload["row_counts"], {"oa": 0, "bank": 2, "invoice": 0, "rows": 2})
        self.assertEqual(group_payload["display_row_counts"], {"oa": 0, "bank": 1, "invoice": 0, "rows": 1})

        group_row_roles = [
            (params[5], params[6], params[7], params[9])
            for sql, params in connection.executed
            if "insert into read_model.workbench_group_rows" in sql and params[4] == "case:ROLE-SUMMARY"
        ]
        self.assertIn(("bank", "summary-bank-source-kind", "summary", "bank"), group_row_roles)

    def test_repository_keeps_synthetic_all_scope_groups_separate_by_month_shard(self) -> None:
        class AggregateAllSyntheticGroupsConnection(WorkbenchWriteConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_groups" not in normalized or "scope_key <> 'all'" not in normalized:
                    return []
                return [
                    {
                        "scope_key": "2026-05",
                        "scope_month": "2026-05-01",
                        "zone": "open",
                        "group_id": "temp:0001",
                        "generated_at": "2026-05-24T00:02:00+00:00",
                        "source_versions": {"source_version": 2},
                        "payload": {
                            "group_id": "temp:0001",
                            "zone": "open",
                            "group_type": "source_linked",
                            "oa_rows": [{"id": "oa-may", "type": "oa", "source_kind": "oa"}],
                            "bank_rows": [],
                            "invoice_rows": [
                                {
                                    "id": "oa-att-inv-may",
                                    "type": "invoice",
                                    "source_kind": "oa_attachment_invoice",
                                    "derived_from_oa_id": "oa-may",
                                }
                            ],
                        },
                    },
                    {
                        "scope_key": "2026-04",
                        "scope_month": "2026-04-01",
                        "zone": "open",
                        "group_id": "temp:0001",
                        "generated_at": "2026-05-24T00:01:00+00:00",
                        "source_versions": {"source_version": 1},
                        "payload": {
                            "group_id": "temp:0001",
                            "zone": "open",
                            "group_type": "source_linked",
                            "oa_rows": [{"id": "oa-apr", "type": "oa", "source_kind": "oa"}],
                            "bank_rows": [],
                            "invoice_rows": [
                                {
                                    "id": "oa-att-inv-apr",
                                    "type": "invoice",
                                    "source_kind": "oa_attachment_invoice",
                                    "derived_from_oa_id": "oa-apr",
                                }
                            ],
                        },
                    },
                ]

        connection = AggregateAllSyntheticGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {"paired": {"groups": []}, "open": {"groups": []}},
                        "source_versions": {"source_version": 3},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        aggregate_group_payloads = [
            params[16].obj
            for sql, params in connection.executed
            if "insert into read_model.workbench_groups" in sql and "values ( %s, %s, 'all'" in sql
        ]

        self.assertEqual(
            sorted(group["group_id"] for group in aggregate_group_payloads),
            ["scope:2026-04:temp:0001", "scope:2026-05:temp:0001"],
        )
        rows_by_group_id = {
            group["group_id"]: (
                [row["id"] for row in group["oa_rows"]],
                [row["id"] for row in group["invoice_rows"]],
            )
            for group in aggregate_group_payloads
        }
        self.assertEqual(rows_by_group_id["scope:2026-05:temp:0001"], (["oa-may"], ["oa-att-inv-may"]))
        self.assertEqual(rows_by_group_id["scope:2026-04:temp:0001"], (["oa-apr"], ["oa-att-inv-apr"]))

    def test_workbench_api_returns_sql_read_model_without_sync_build(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_view": lambda _self, **_kwargs: {
                    "payload": {"open": {"groups": []}},
                    "refresh_status": "fresh",
                    "source_versions": {
                        "oa_attachment_invoice_parser_version": app._current_oa_attachment_invoice_parser_version(),
                        "oa_projection_sync_version": app._current_oa_projection_sync_version(),
                    },
                }
            },
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
            search_mode="linked_context",
            search_by_pane='{"bank":"建行"}',
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
                    "search_mode": "linked_context",
                    "search_by_pane": {"bank": "建行"},
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

    def test_workbench_groups_api_redis_cache_key_includes_search_mode(self) -> None:
        app = object.__new__(Application)
        base_kwargs = {
            "cache_version": "v7",
            "scope_key": "all",
            "zone": "open",
            "page": "1",
            "page_size": "200",
            "status": None,
            "source_kind": None,
            "search": "花",
            "sort": None,
            "detail_level": "summary",
            "column_filters": {},
            "time_filters": {},
        }

        linked_key = app._workbench_groups_redis_cache_key_from_version(
            **base_kwargs,
            search_mode="linked_context",
        )
        pane_key = app._workbench_groups_redis_cache_key_from_version(
            **base_kwargs,
            search_mode="pane",
        )

        self.assertNotEqual(linked_key, pane_key)

    def test_workbench_groups_api_redis_cache_key_includes_read_model_schema_version(self) -> None:
        app = object.__new__(Application)
        kwargs = {
            "cache_version": "v7",
            "scope_key": "all",
            "zone": "open",
            "page": "1",
            "page_size": "50",
            "status": None,
            "source_kind": None,
            "search": None,
            "sort": None,
            "detail_level": "summary",
        }

        with patch("fin_ops_platform.app.server.WORKBENCH_READ_MODEL_SCHEMA_VERSION", "schema-a"):
            key_a = app._workbench_groups_redis_cache_key_from_version(**kwargs)
        with patch("fin_ops_platform.app.server.WORKBENCH_READ_MODEL_SCHEMA_VERSION", "schema-b"):
            key_b = app._workbench_groups_redis_cache_key_from_version(**kwargs)

        self.assertNotEqual(key_a, key_b)

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

    def test_workbench_refresh_status_api_normalizes_failed_dirty_scope(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": None})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_refresh_status": lambda _self, **_kwargs: {
                    "read_model_status": "stale",
                    "dirty_scopes": [
                        {
                            "scope_key": "2026-05",
                            "status": "failed",
                            "last_error": "projection boom",
                            "source_version": 12,
                        }
                    ],
                    "worker_lag_seconds": 8.0,
                }
            },
        )()

        response = app._handle_api_workbench_refresh_status("all")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "failed")
        self.assertEqual(payload["last_error"], "projection boom")
        self.assertEqual(payload["read_model_version"], 12)
        self.assertTrue(payload["retryable"])

    def test_workbench_events_stream_emits_refresh_status_event(self) -> None:
        app = object.__new__(Application)
        app._app_health_service = AppHealthService()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_refresh_status": lambda _self, **_kwargs: {
                    "scope_key": "all",
                    "read_model_status": "fresh",
                    "generated_at": "2026-05-28T10:00:00+08:00",
                    "dirty_scopes": [],
                    "worker_lag_seconds": 1.5,
                }
            },
        )()

        response = app._handle_api_workbench_events("all")
        stream = iter(response.body)
        first_event = next(stream)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(response.headers["Content-Type"], "text/event-stream; charset=utf-8")
        self.assertIn("event: workbench.read_model.completed", first_event)
        self.assertIn('"read_model_status": "fresh"', first_event)

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
                    "source_versions": {
                        "oa_attachment_invoice_parser_version": app._current_oa_attachment_invoice_parser_version(),
                        "oa_projection_sync_version": app._current_oa_projection_sync_version(),
                    },
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
        self.assertNotIn("delete from read_model.workbench_rows", sql)
        self.assertIn("insert into read_model.workbench_generations", sql)
        self.assertIn("insert into read_model.workbench_rows", sql)
        self.assertIn("on conflict (generation_id, scope_key, row_id)", sql)

    def test_repository_does_not_delete_generation_rows_when_scope_snapshot_is_absent(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models({"read_models": {}}, changed_scope_keys={"2026-05"})

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertNotIn("delete from read_model.workbench_snapshots where scope_key", sql)
        self.assertNotIn("delete from read_model.workbench_summary where scope_key", sql)
        self.assertNotIn("delete from read_model.workbench_rows where scope_key", sql)
        self.assertNotIn("delete from read_model.workbench_groups where scope_key", sql)
        self.assertNotIn("delete from read_model.workbench_group_rows where scope_key", sql)

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

    def test_repository_reports_inconsistent_active_workbench_generation_as_failed(self) -> None:
        class InconsistentGenerationConnection(WorkbenchSummaryGroupsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "actual_group_count" in normalized and "from read_model.workbench_generations" in normalized:
                    return [
                        {
                            "scope_key": "2026-03",
                            "generation_id": "gen-2026-03",
                            "row_count": 253,
                            "group_count": 151,
                            "summary_count": 1,
                            "actual_row_count": 0,
                            "actual_group_count": 0,
                            "actual_group_row_count": 0,
                            "actual_summary_count": 1,
                            "build_metadata": {},
                        }
                    ]
                return super().fetch_all(sql, params)

        repository = PostgresReadModelRepository(InconsistentGenerationConnection())

        status = repository.get_workbench_refresh_status(scope_key="2026-03")

        self.assertEqual(status["read_model_status"], "failed")
        self.assertEqual(status["consistency_status"], "failed")
        self.assertIn("generation_metadata_actual_mismatch", status["read_model_stale_reasons"])
        self.assertIn("gen-2026-03", status["last_error"])

    def test_repository_does_not_publish_all_scope_when_month_generation_is_inconsistent(self) -> None:
        class InconsistentAggregateConnection(WorkbenchWriteConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "actual_group_count" in normalized and "from read_model.workbench_generations" in normalized:
                    return [
                        {
                            "scope_key": "2026-03",
                            "generation_id": "gen-2026-03",
                            "row_count": 253,
                            "group_count": 151,
                            "summary_count": 1,
                            "actual_row_count": 0,
                            "actual_group_count": 0,
                            "actual_group_row_count": 0,
                            "actual_summary_count": 1,
                            "build_metadata": {},
                        }
                    ]
                if "from read_model.workbench_groups" in normalized and "scope_key <> 'all'" in normalized:
                    return [
                        {
                            "scope_key": "2025-12",
                            "scope_month": "2025-12-01",
                            "zone": "paired",
                            "group_id": "case:survivor",
                            "generated_at": "2026-05-24T00:01:00+00:00",
                            "source_versions": {"source_version": 1},
                            "payload": {
                                "group_id": "case:survivor",
                                "zone": "paired",
                                "oa_rows": [{"id": "oa-1", "type": "oa", "source_kind": "oa"}],
                                "bank_rows": [],
                                "invoice_rows": [],
                            },
                        }
                    ]
                return []

        connection = InconsistentAggregateConnection()
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

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertIn("status = 'failed'", sql)
        self.assertTrue(
            any(
                any("workbench_all_scope_parent_inconsistent" in str(param) for param in params)
                for _statement, params in connection.executed
            )
        )
        self.assertFalse(
            any(
                "insert into read_model.workbench_groups" in statement and "values ( %s, %s, 'all'" in statement
                for statement, _params in connection.executed
            )
        )

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
                self.enqueued: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.refreshes.append((scope_type, scope_key, reason))

            def enqueue(self, **kwargs):
                self.enqueued.append(dict(kwargs))

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
        self.assertEqual(
            result,
            {
                "scope_key": "all",
                "enqueued_scope_keys": ["2026-05", "2026-04"],
                "aggregate_enqueued": True,
                "row_count": 0,
            },
        )
        self.assertEqual(
            queue.refreshes,
            [("workbench", "2026-05", "workbench_all_shard"), ("workbench", "2026-04", "workbench_all_shard")],
        )
        self.assertEqual(queue.completed, [])
        self.assertEqual(len(queue.enqueued), 1)
        self.assertEqual(queue.enqueued[0]["scope_key"], "all")
        self.assertEqual(queue.enqueued[0]["payload"]["aggregate_only"], True)
        self.assertEqual(queue.enqueued[0]["priority"], "low")

    def test_workbench_refresh_handler_completes_all_after_aggregate_only_event(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.calls: list[tuple[str, object]] = []

            def refresh_workbench_all_scope_from_active_shards(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                self.calls.append((scope_key, source_version))
                return {"scope_key": scope_key, "aggregate_only": True, "active_generation_id": "gen-all"}

        class FakeQueue:
            def __init__(self) -> None:
                self.completed: list[tuple[str, str, str, object]] = []

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
            event_id="event-all-aggregate",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="workbench",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all", "aggregate_only": True, "source_version": 9},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.calls, [("all", 9)])
        self.assertEqual(queue.completed, [("tenant-a", "workbench", "all", 9)])
        self.assertEqual(result["active_generation_id"], "gen-all")

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
        self.assertEqual(rows[0]["invoice_no"], "INV-STRUCT-001")
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

    def test_sql_projection_projects_paired_reconciliation_decisions_without_candidate_write(self) -> None:
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
            "invoice-1": {
                "id": "invoice-1",
                "type": "invoice",
                "source_kind": "invoice",
                "total_with_tax": "99.00",
                "seller_name": "杭州测试供应商",
                "issue_date": "2026-05-12",
            },
        }
        decision = reconciliation_decision_payload(
            "decision-paired",
            status=DECISION_STATUS_PAIRED,
            display_state=DISPLAY_STATE_PAIRED,
            row_ids=["oa-1", "bank-1", "invoice-1"],
            warnings=[
                {
                    "code": WARNING_INVOICE_AMOUNT_MISMATCH,
                    "message": "附件发票合计与 OA/流水金额不一致",
                }
            ],
        )

        payload = builder._group_payload("2026-05", rows_by_id, [], decisions=[decision])

        self.assertEqual(recorder.saved_snapshots, [])
        self.assertEqual(payload["open"]["groups"], [])
        paired_groups = payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        self.assertNotEqual(paired_groups[0]["group_type"], "candidate")
        paired_rows = [
            row
            for group in paired_groups
            for row in [*group.get("oa_rows", []), *group.get("bank_rows", []), *group.get("invoice_rows", [])]
        ]
        self.assertEqual({row["id"] for row in paired_rows}, {"oa-1", "bank-1", "invoice-1"})
        self.assertTrue(all(row["status"] == "paired" for row in paired_rows))
        self.assertTrue(all(row["case_id"] == "decision-paired" for row in paired_rows))
        self.assertTrue(
            all(
                row["workbench_reconciliation_decision"]["warnings"][0]["code"] == WARNING_INVOICE_AMOUNT_MISMATCH
                for row in paired_rows
            )
        )

    def test_sql_projection_groups_multi_payment_single_invoice_decision(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-a": {
                "id": "oa-a",
                "type": "oa",
                "source_kind": "oa",
                "amount": "9414.30",
                "counterparty_name": "北京标志卓信科技有限公司",
                "application_date": "2026-03-06",
                "project_name": "昭通卷烟厂能源集中监控平台系统维护采购项目",
            },
            "bank-a": {
                "id": "bank-a",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "9414.30",
                "counterparty_name": "北京标志卓信科技有限公司",
                "trade_time": "2026-03-06 11:44:52",
                "summary": "预付货款",
            },
            "oa-b": {
                "id": "oa-b",
                "type": "oa",
                "source_kind": "oa",
                "amount": "21966.70",
                "counterparty_name": "北京标志卓信科技有限公司",
                "application_date": "2026-03-27",
                "project_name": "昭通卷烟厂能源集中监控平台系统维护采购项目",
            },
            "bank-b": {
                "id": "bank-b",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "21966.70",
                "counterparty_name": "北京标志卓信科技有限公司",
                "trade_time": "2026-03-27 10:45:13",
                "summary": "货款",
            },
            "invoice-combined": {
                "id": "invoice-combined",
                "type": "invoice",
                "source_kind": "invoice",
                "total_with_tax": "31381.00",
                "seller_name": "北京标志卓信科技有限公司",
                "issue_date": "2026-03-28",
            },
        }
        decision = reconciliation_decision_payload(
            "decision-multi-payment-invoice",
            status=DECISION_STATUS_PAIRED,
            display_state=DISPLAY_STATE_PAIRED,
            row_ids=["oa-a", "oa-b", "bank-a", "bank-b", "invoice-combined"],
        )

        payload = builder._group_payload("2026-05", rows_by_id, [], decisions=[decision])

        paired_groups = payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        group = paired_groups[0]
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-a", "oa-b"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-a", "bank-b"])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["invoice-combined"])
        paired_rows = [*group["oa_rows"], *group["bank_rows"], *group["invoice_rows"]]
        self.assertTrue(all(row["status"] == "paired" for row in paired_rows))
        self.assertTrue(all(row["case_id"] == "decision-multi-payment-invoice" for row in paired_rows))

    def test_sql_projection_projects_open_reconciliation_decisions_as_independent_open_rows(self) -> None:
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
        decision = reconciliation_decision_payload(
            "decision-open",
            status=DECISION_STATUS_OPEN,
            display_state=DISPLAY_STATE_OPEN,
            row_ids=["oa-1", "bank-1"],
        )

        payload = builder._group_payload("2026-05", rows_by_id, [], decisions=[decision])

        self.assertEqual(recorder.saved_snapshots, [])
        self.assertEqual(payload["paired"]["groups"], [])
        open_groups = payload["open"]["groups"]
        self.assertEqual(len(open_groups), 2)
        self.assertTrue(all(group["group_type"] == "open" for group in open_groups))
        self.assertTrue(all(sum(len(group[f"{kind}_rows"]) for kind in ("oa", "bank", "invoice")) == 1 for group in open_groups))
        self.assertEqual(
            {
                row["id"]
                for group in open_groups
                for row in [*group["oa_rows"], *group["bank_rows"], *group["invoice_rows"]]
            },
            {"oa-1", "bank-1"},
        )

    def test_sql_projection_ignores_non_projectable_reconciliation_decisions(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-1": {"id": "oa-1", "type": "oa", "source_kind": "oa", "amount": "100.00"},
            "bank-1": {"id": "bank-1", "type": "bank", "source_kind": "bank", "debit_amount": "100.00"},
        }
        decision = reconciliation_decision_payload(
            "decision-consumed",
            status=DECISION_STATUS_CONSUMED,
            display_state=DISPLAY_STATE_PAIRED,
            row_ids=["oa-1", "bank-1"],
        )

        payload = builder._group_payload("2026-05", rows_by_id, [], decisions=[decision])

        row_payloads = [
            row
            for section in ("paired", "open")
            for group in payload[section]["groups"]
            for row in [*group.get("oa_rows", []), *group.get("bank_rows", []), *group.get("invoice_rows", [])]
        ]
        self.assertTrue(all("workbench_reconciliation_decision" not in row for row in row_payloads))
        self.assertEqual(payload["paired"]["groups"], [])

    def test_sql_projection_keeps_active_manual_relation_ahead_of_automatic_decision(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-1": {"id": "oa-1", "type": "oa", "source_kind": "oa", "amount": "100.00"},
            "bank-1": {"id": "bank-1", "type": "bank", "source_kind": "bank", "debit_amount": "100.00"},
            "invoice-1": {"id": "invoice-1", "type": "invoice", "source_kind": "invoice", "total_with_tax": "100.00"},
        }
        relation = {
            "case_id": "CASE-MANUAL-1",
            "relation_mode": "manual_confirmed",
            "row_ids": ["oa-1", "bank-1", "invoice-1"],
            "row_types": ["oa", "bank", "invoice"],
        }
        decision = reconciliation_decision_payload(
            "decision-overlap",
            status=DECISION_STATUS_PAIRED,
            display_state=DISPLAY_STATE_PAIRED,
            row_ids=["oa-1", "bank-1", "invoice-1"],
        )

        payload = builder._group_payload("2026-05", rows_by_id, [relation], decisions=[decision])

        paired_group = payload["paired"]["groups"][0]
        paired_rows = [*paired_group["oa_rows"], *paired_group["bank_rows"], *paired_group["invoice_rows"]]
        self.assertEqual(paired_group["group_id"], "case:CASE-MANUAL-1")
        self.assertTrue(all(row["case_id"] == "CASE-MANUAL-1" for row in paired_rows))
        self.assertTrue(all("workbench_reconciliation_decision" not in row for row in paired_rows))

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
            "special_metadata": {
                "source": "no_oa_bank_batch",
                "source_batch_id": "batch-no-oa-fee-001",
                "batch_type": "fee",
                "batch_label": "手续费",
                "batch_version": 3,
                "row_count": 2,
                "total_amount": "20.00",
                "withdrawable": True,
                "relation_mode": "no_oa_bank_batch",
                "display_tags": ["免OA", "手续费"],
            },
            "display_tags": ["免OA", "手续费"],
        }

        payload = builder._group_payload("2026-05", rows_by_id, [relation])

        paired = payload["paired"]["groups"]
        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0]["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(paired[0]["display_mode"], "collapsed_summary")
        self.assertEqual([row["id"] for row in paired[0]["bank_rows"]], ["no_oa_summary:batch-no-oa-fee-001"])
        self.assertCountEqual([row["id"] for row in paired[0]["collapsed_rows"]["bank"]], ["bank-a", "bank-b"])
        self.assertEqual(paired[0]["summary_row"]["special_metadata"]["source_batch_id"], "batch-no-oa-fee-001")
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
