from __future__ import annotations

import json
import hashlib
from decimal import Decimal
from http import HTTPStatus
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.app_health_service import AppHealthService
from fin_ops_platform.services.postgres_repositories.read_models import (
    WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION,
    PostgresReadModelRepository,
    _workbench_group_row_records,
    _workbench_row_payload_for_write,
)
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.runtime_worker_handlers import _RuntimeWorkerDerivedLifecycle
from fin_ops_platform.services.workbench_free_matching_engine import RULE_VERSION as WORKBENCH_FORMAL_RELATION_RULE_VERSION
from fin_ops_platform.services.workbench_groups_page_cache import WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION
from fin_ops_platform.services.workbench_read_model_refresh import WorkbenchReadModelRefreshService
from fin_ops_platform.services.workbench_sql_projection import (
    WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
    WorkbenchSqlProjectionBuilder,
)


def fresh_workbench_sql_source_versions(app: Application, scope_key: str = "2026-05") -> dict[str, object]:
    builder = (
        WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION
        if scope_key == "all"
        else WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION
    )
    return {
        "builder": builder,
        "workbench_formal_relation_rule_version": WORKBENCH_FORMAL_RELATION_RULE_VERSION,
        "bank_auto_tag_rules_version": app._current_bank_auto_tag_rules_version(),
        "oa_attachment_invoice_parser_version": app._current_oa_attachment_invoice_parser_version(),
        "oa_projection_sync_version": app._current_oa_projection_sync_version(),
    }


ACTIVE_MONTH_GENERATION_SET = [
    {
        "scope_key": "2026-05",
        "generation_id": "gen-active",
        "source_versions": {"source_version": 12},
    }
]
COMPOSED_ALL_VERSION = "workbench:all:active-generation-set:" + hashlib.sha256(
    json.dumps(
        ACTIVE_MONTH_GENERATION_SET,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()
ACTIVE_MONTH_SUMMARY_ROW = {
    "scope_key": "2026-05",
    "generation_id": "gen-active",
    "generation_source_versions": {"source_version": 12},
    "generated_at": "2026-05-28T09:00:00+00:00",
    "payload": {
        "month": "2026-05",
        "scope_key": "2026-05",
        "summary": {
            "oa_count": 1,
            "bank_count": 2,
            "invoice_count": 3,
            "paired_count": 4,
            "unpaired_count": 5,
            "exception_count": 0,
        },
        "invoice_inventory": {},
    },
}


def with_test_object_identities(rows_by_id: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    """Give hand-built projection fixtures the same canonical identity contract as SQL rows."""
    result: dict[str, dict[str, object]] = {}
    for row_id, source in rows_by_id.items():
        row = dict(source)
        row_type = str(row.get("type") or "").strip()
        if row_type == "bank":
            row["account_no"] = row.get("account_no") or f"test-account-{row_id}"
            trade_time = str(row.get("trade_time") or "2026-05-01 00:00:00")
            row["trade_time"] = f"{trade_time}:00" if len(trade_time) == 16 else trade_time
            row["txn_direction"] = row.get("txn_direction") or ("inflow" if row.get("credit_amount") else "outflow")
            row["amount"] = row.get("amount") or row.get("debit_amount") or row.get("credit_amount") or "0.01"
            row["counterparty_name"] = row.get("counterparty_name") or f"test-counterparty-{row_id}"
        elif row_type == "invoice" and not (row.get("digital_invoice_no") or row.get("invoice_no")):
            row["digital_invoice_no"] = f"{int(hashlib.sha256(row_id.encode()).hexdigest(), 16) % 10**20:020d}"
        invoice_no = str(row.get("digital_invoice_no") or row.get("invoice_no") or "").strip()
        row.setdefault(
            "object_identity_key",
            f"invoice:{invoice_no}" if row_type == "invoice" and invoice_no else f"{row_type}:{row_id}",
        )
        result[row_id] = row
    return result


class WorkbenchSqlProjectionRelationPayloadTests(unittest.TestCase):
    def test_oa_pending_in_progress_relation_uses_dedicated_bank_chip(self) -> None:
        payload = WorkbenchSqlProjectionBuilder._active_relation_payload(
            {
                "relation_mode": "manual_confirmed",
                "special_metadata": {"origin": "oa_pending_payment_in_progress"},
            }
        )

        self.assertEqual(payload, {"code": "oa_pending_payment_in_progress", "label": "已关联进行中OA", "tone": "success"})

    def test_sql_oa_row_promotes_application_time_when_completed_time_is_placeholder(self) -> None:
        row = WorkbenchSqlProjectionBuilder._oa_row_from_sql(
            {
                "row_id": "oa-pay-application-time",
                "applicant": "刘树刚",
                "application_date": "2026-01-01",
                "project_name": "云南溯源科技",
                "amount": "1872.93",
                "status": "unpaired",
                "workflow_status": "completed",
                "normalized_payload": {
                    "apply_type": "支付申请",
                    "reason": "ETC过路费",
                    "detail_fields": {
                        "审批完成时间": "—",
                        "申请日期": "2026-01-14 14:04:00",
                    },
                },
            }
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["apply_time"], "2026-01-14 14:04:00")
        self.assertEqual(row["application_time"], "2026-01-14 14:04:00")
        self.assertEqual(row["application_date"], "2026-01-14 14:04:00")
        self.assertIsNone(row["completed_at"])

    def test_invoice_rows_excludes_visible_formal_invoices_already_bound_to_submitted_etc_batches(self) -> None:
        connection = InvoiceRowsSqlCaptureConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        rows = builder._invoice_rows("2026-02")

        self.assertEqual(rows, [])
        self.assertEqual(len(connection.fetch_all_calls), 1)
        sql, _params = connection.fetch_all_calls[0]
        self.assertIn("app.etc_batch_invoice_links", sql)
        self.assertIn("link_status = 'active'", sql)
        self.assertIn("app.etc_invoices", sql)
        self.assertIn("app.etc_business_batches", sql)
        self.assertIn("manually_marked_submitted", sql)

    def test_etc_invoice_summary_rows_prefer_link_table_source(self) -> None:
        connection = EtcSummaryLinkTableConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        rows = builder._etc_invoice_summary_rows(month="2026-02")

        self.assertEqual(list(rows), ["etc_business_batch_hist_20260413_241125"])
        summary = rows["etc_business_batch_hist_20260413_241125"]
        self.assertEqual(summary["source_kind"], "etc_invoice_summary")
        self.assertEqual(summary["etc_invoice_count"], 1)
        self.assertEqual(summary["amount_value"], "19.19")
        self.assertIn("app.etc_batch_invoice_links", connection.fetch_all_calls[0][0])
        self.assertIn(
            "coalesce(business_batches.scope_month, invoices.invoice_month) = %s::date",
            connection.fetch_all_calls[0][0],
        )
        self.assertEqual(connection.fetch_all_calls[0][1], ("2026-02-01",))

    def test_etc_invoice_summary_does_not_use_legacy_fallback_in_another_month_when_link_owner_exists(self) -> None:
        connection = EtcSummaryCanonicalOwnerConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        rows = builder._etc_invoice_summary_rows(month="2026-05")

        self.assertEqual(rows, {})
        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("select distinct", queried_sql)
        self.assertIn("from app.etc_batch_invoice_links", queried_sql)
        self.assertIn("with submitted_batches as", queried_sql)

    def test_etc_invoice_summary_does_not_use_submission_fallback_when_business_owner_exists(self) -> None:
        connection = EtcSummaryBusinessOwnerConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        rows = builder._etc_invoice_summary_rows(month="2026-05")

        self.assertEqual(rows, {})
        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("from app.etc_business_batches batch", queried_sql)
        self.assertIn("with submitted_batches as", queried_sql)


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
                    "status": "unpaired",
                    "payload": {"id": "bank-row-1"},
                }
            ]
        return []


class LightweightWorkbenchSnapshotConnection(WorkbenchSqlReadConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.workbench_generations" in normalized and "status = 'active'" in normalized:
            return {"generation_id": "gen-lightweight"}
        if "from read_model.workbench_snapshots" in normalized:
            return {
                "generation_id": "gen-lightweight",
                "scope_key": "2026-05",
                "payload": {
                    "scope_key": "2026-05",
                    "payload": {
                        "month": "2026-05",
                        "summary": {
                            "oa_count": 1,
                            "bank_count": 1,
                            "invoice_count": 0,
                            "paired_count": 0,
                            "unpaired_count": 1,
                            "exception_count": 0,
                        },
                        "paired": {"groups": []},
                        "unpaired": {"groups": []},
                        "workbench_groups_materialized": True,
                    },
                    "source_versions": {"source_version": 12},
                },
                "cache_status": "fresh",
                "generated_at": "2026-05-22T10:00:00+00:00",
                "source_versions": {"source_version": 12},
                "row_count": 1,
            }
        if "from job.read_model_dirty_scopes" in normalized:
            return None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_groups" in normalized:
            return [
                {
                    "scope_key": "2026-05",
                    "generation_id": "gen-lightweight",
                    "zone": "unpaired",
                    "group_id": "case:LIGHT-1",
                    "payload": {
                        "group_id": "case:LIGHT-1",
                        "group_type": "candidate",
                        "row_count": 2,
                        "workbench_group_rows_materialized": True,
                    },
                }
            ]
        if "join read_model.workbench_group_rows" in normalized:
            return [
                {
                    "scope_key": "2026-05",
                    "generation_id": "gen-lightweight",
                    "zone": "unpaired",
                    "group_id": "case:LIGHT-1",
                    "pane": "oa",
                    "row_id": "oa-light-1",
                    "row_role": "normal",
                    "row_index": 0,
                    "source_kind": "oa_payment",
                    "status": "unpaired",
                    "row_payload": {
                        "id": "oa-light-1",
                        "type": "oa",
                        "detail_fields": {"项目名称": "轻量项目"},
                    },
                    "member_payload": {
                        "row_id": "oa-light-1",
                        "type": "oa",
                    },
                },
                {
                    "scope_key": "2026-05",
                    "generation_id": "gen-lightweight",
                    "zone": "unpaired",
                    "group_id": "case:LIGHT-1",
                    "pane": "bank",
                    "row_id": "bank-light-1",
                    "row_role": "normal",
                    "row_index": 1,
                    "source_kind": "bank_transaction",
                    "status": "unpaired",
                    "row_payload": {
                        "id": "bank-light-1",
                        "type": "bank",
                        "available_actions": ["cancel_link"],
                    },
                    "member_payload": {
                        "row_id": "bank-light-1",
                        "type": "bank",
                    },
                },
            ]
        return []


class InvoiceRowsSqlCaptureConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        return []


class EtcSummaryLinkTableConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from app.etc_batch_invoice_links" in normalized:
            return [
                {
                    "external_etc_batch_id": "etc_business_batch_hist_20260413_241125",
                    "business_batch_id": "etc_business_batch_hist_20260413_241125",
                    "business_invoice_count": 1,
                    "business_total_amount": Decimal("19.19"),
                    "business_batch_payload": {"total_amount": "19.19", "etc_invoice_count": 1},
                    "row_id": "invoice-link-table",
                    "invoice_type": "进项发票",
                    "invoice_no": "26537912570200055449",
                    "invoice_code": None,
                    "digital_invoice_no": "26537912570200055449",
                    "invoice_date": "2026-02-28",
                    "counterparty_name": "云南国道主干线昆明绕城高速公路建设有限公司",
                    "seller_name": "云南国道主干线昆明绕城高速公路建设有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "amount": Decimal("18.63"),
                    "tax_rate": "3%",
                    "tax_amount": Decimal("0.56"),
                    "total_with_tax": Decimal("19.19"),
                    "status": "pending",
                    "workbench_visibility": "hidden_after_etc_submission",
                    "raw_payload": {},
                }
            ]
        return []


class EtcSummaryCanonicalOwnerConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "select distinct" in normalized and "from app.etc_batch_invoice_links" in normalized:
            return [{"external_etc_batch_id": "etc-canonical-owner"}]
        if "from app.etc_batch_invoice_links" in normalized:
            return []
        if "with submitted_batches as" in normalized and "from app.invoices invoices" in normalized:
            return [
                {
                    "external_etc_batch_id": "etc-canonical-owner",
                    "row_id": "legacy-fallback-invoice",
                    "invoice_no": "legacy-fallback-invoice",
                    "total_with_tax": Decimal("88.00"),
                }
            ]
        return []


class EtcSummaryBusinessOwnerConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "select distinct" in normalized and "from app.etc_business_batches batch" in normalized:
            return [{"external_etc_batch_id": "etc-business-owner"}]
        if "with submitted_batches as" in normalized and "from app.invoices invoices" in normalized:
            return [
                {
                    "external_etc_batch_id": "etc-business-owner",
                    "row_id": "submission-fallback-invoice",
                    "invoice_no": "submission-fallback-invoice",
                    "total_with_tax": Decimal("31.00"),
                }
            ]
        return []


class ActiveAllWorkbenchSnapshotConnection(WorkbenchSqlReadConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.workbench_generations" in normalized and "status = 'active'" in normalized:
            return {"generation_id": "gen-all-active"}
        if "from read_model.workbench_snapshots" in normalized and "generation_id = %s" in normalized:
            return {
                "scope_key": "all",
                "generation_id": "gen-all-active",
                "cache_status": "fresh",
                "generated_at": "2026-05-22T10:00:00+00:00",
                "source_versions": {"source_version": 17, "workbench_formal_relation_rule_version": "rules-v2"},
                "row_count": 3,
                "payload": {
                    "month": "all",
                    "scope_key": "all",
                    "summary": {
                        "oa_count": 1,
                        "bank_count": 1,
                        "invoice_count": 1,
                        "paired_count": 1,
                        "unpaired_count": 0,
                        "exception_count": 0,
                    },
                    "unpaired": {"groups": []},
                    "paired": {
                        "groups": [
                            {
                                "group_id": "case:active-all",
                                "oa_rows": [{"id": "oa-active-all"}],
                                "bank_rows": [{"id": "bank-active-all"}],
                                "invoice_rows": [{"id": "invoice-active-all"}],
                            }
                        ]
                    },
                },
            }
        if "from job.read_model_dirty_scopes" in normalized:
            return None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_snapshots" in normalized and "scope_key <> 'all'" in normalized:
            return [
                {
                    "scope_key": "2026-04",
                    "row_count": 99,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "payload": {
                        "payload": {
                            "summary": {
                                "oa_count": 99,
                                "bank_count": 0,
                                "invoice_count": 0,
                                "paired_count": 0,
                                "unpaired_count": 99,
                            },
                            "unpaired": {"groups": [{"oa_rows": [{"id": "legacy-month"}], "bank_rows": [], "invoice_rows": []}]},
                            "paired": {"groups": []},
                        }
                    },
                }
            ]
        return super().fetch_all(sql, params)


class ReadModelRefreshTransactionConnection:
    def __init__(self) -> None:
        self.fetch_all_params: list[tuple] = []

    def fetch_all(self, _sql: str, params: tuple = ()) -> list[dict]:
        self.fetch_all_params.append(params)
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
                    "summary": {"oa_count": 1, "bank_count": 2, "invoice_count": 3, "paired_count": 4, "unpaired_count": 5},
                },
                {
                    "scope_key": "2026-04",
                    "row_count": 10,
                    "generated_at": "2026-05-21T08:00:00+00:00",
                    "cache_status": "fresh",
                    "summary": {"oa_count": 10, "bank_count": 20, "invoice_count": 30, "paired_count": 40, "unpaired_count": 50},
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


class ActiveAllRowsPageConnection(WorkbenchAllRowsPageConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.workbench_generations" in normalized and "status = 'active'" in normalized:
            return {"generation_id": "gen-all-active"}
        if "from read_model.workbench_summary" in normalized:
            return {
                "scope_key": "all",
                "generation_id": "gen-all-active",
                "payload": {
                    "month": "all",
                    "scope_key": "all",
                    "summary": {
                        "oa_count": 1,
                        "bank_count": 1,
                        "invoice_count": 1,
                        "paired_count": 1,
                        "unpaired_count": 0,
                        "exception_count": 0,
                    },
                    "generated_at": "2026-05-22T10:00:00+00:00",
                },
                "generated_at": "2026-05-22T10:00:00+00:00",
                "source_versions": {"source_version": 17, "workbench_formal_relation_rule_version": "rules-v2"},
            }
        if "count(*) as total_count" in normalized:
            return {"total_count": 1}
        if "from job.read_model_dirty_scopes" in normalized:
            return None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_snapshots" in normalized and "scope_key <> 'all'" in normalized:
            raise AssertionError("active all-scope rows_page must use active all summary instead of month snapshots")
        if "from job.read_model_dirty_scopes" in normalized:
            return []
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
                "zone": "unpaired",
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
                {"zone": "unpaired", "count": 2, "oa_count": 2, "bank_count": 2, "invoice_count": 5},
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
                    "zone": "unpaired",
                    "payload": {
                        "group_id": "case:1",
                        "group_type": "candidate",
                        "match_confidence": "medium",
                        "reason": "sql page",
                        "searchable_text": "large searchable text that must stay out of summary responses",
                        "source_versions": {"source_version": 12},
                        "group_metadata": {"debug": True},
                        "oa_rows": [
                            {
                                "id": f"oa-{index}",
                                "type": "oa",
                                "detail_fields": {"OA单号": f"215{index}"},
                                "source_versions": {"source_version": 12},
                                "object_identity": {"key": f"oa-{index}", "kind": "oa_row"},
                                "object_identity_key": f"oa-{index}",
                            }
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
                    "zone": "unpaired",
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
                        "unpaired_count": 14,
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
        if "count(*)::bigint as scope_count" in normalized and "from read_model.workbench_generations" in normalized:
            self.fetch_one_calls.append((normalized, params))
            return {
                "scope_count": 1,
                "source_version": 12,
                "generated_at": "2026-05-28T09:00:00+00:00",
            }
        if (
            "from read_model.workbench_generations" in normalized
            and "select generation_id" in normalized
            and "status = 'active'" in normalized
        ):
            self.fetch_one_calls.append((normalized, params))
            return {"generation_id": "gen-active"}
        return super().fetch_one(sql, params)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "select scope_key, generation_id, source_versions" in normalized:
            self.fetch_all_calls.append((normalized, params))
            return [
                {
                    **ACTIVE_MONTH_GENERATION_SET[0],
                    "generated_at": "2026-05-28T09:00:00+00:00",
                }
            ]
        if "left join read_model.workbench_summary" in normalized:
            self.fetch_all_calls.append((normalized, params))
            return [ACTIVE_MONTH_SUMMARY_ROW]
        if "select source_versions" in normalized and "from read_model.workbench_generations" in normalized:
            self.fetch_all_calls.append((normalized, params))
            return [{"source_versions": {"source_version": 12}}]
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


class SwitchingActiveWorkbenchGenerationConnection(WorkbenchSummaryGroupsConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "count(*)::bigint as scope_count" in normalized and "from read_model.workbench_generations" in normalized:
            self.fetch_one_calls.append((normalized, params))
            return {
                "scope_count": 1,
                "source_version": 12,
                "generated_at": "2026-05-28T09:00:00+00:00",
            }
        if "from read_model.workbench_generations" in normalized and "select generation_id" in normalized:
            self.fetch_one_calls.append((normalized, params))
            return {"generation_id": "gen-active"}
        if "from read_model.workbench_groups" in normalized and "group_id = %s" in normalized and "gen.source_versions" in normalized:
            self.fetch_one_calls.append((normalized, params))
            return {
                "group_id": "case:1",
                "zone": "unpaired",
                "scope_key": "all",
                "generation_id": "gen-active",
                "source_versions": {"source_version": 12},
                "payload": {
                    "group_id": "case:1",
                    "group_type": "candidate",
                    "match_confidence": "medium",
                    "reason": "detail",
                    "oa_rows": [{"id": "oa-1", "type": "oa"}],
                    "bank_rows": [],
                    "invoice_rows": [],
                },
            }
        if "from read_model.workbench_generations" in normalized and "select source_versions" in normalized:
            self.fetch_one_calls.append((normalized, params))
            if "generation_id = %s" in normalized:
                return {"source_versions": {"source_version": 12}}
            return {"source_versions": {"source_version": 99}}
        if "from read_model.workbench_summary" in normalized:
            self.fetch_one_calls.append((normalized, params))
            return {
                "scope_key": "all",
                "generation_id": "gen-active",
                "generated_at": "2026-05-28T09:00:00+00:00",
                "source_versions": {"source_version": 12},
                "payload": {
                    "month": "all",
                    "scope_key": "all",
                    "summary": {
                        "oa_count": 1,
                        "bank_count": 2,
                        "invoice_count": 3,
                        "paired_count": 4,
                        "unpaired_count": 5,
                        "exception_count": 0,
                    },
                    "invoice_inventory": {},
                },
            }
        return super().fetch_one(sql, params)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "select scope_key, generation_id, source_versions" in normalized:
            self.fetch_all_calls.append((normalized, params))
            return [
                {
                    **ACTIVE_MONTH_GENERATION_SET[0],
                    "generated_at": "2026-05-28T09:00:00+00:00",
                }
            ]
        if "left join read_model.workbench_summary" in normalized:
            self.fetch_all_calls.append((normalized, params))
            return [ACTIVE_MONTH_SUMMARY_ROW]
        if "select source_versions" in normalized and "from read_model.workbench_generations" in normalized:
            self.fetch_all_calls.append((normalized, params))
            return [{"source_versions": {"source_version": 12}}]
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


class WorkbenchGenerationStatsConnection(ActiveWorkbenchGenerationConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_generation_stats" in normalized:
            self.fetch_one_calls.append((normalized, params))
            return {
                "total_groups": 2,
                "oa_count": 3,
                "bank_count": 4,
                "invoice_count": 5,
                "row_count_total": 12,
            }
        return super().fetch_one(sql, params)


class BatchAccountingActiveGenerationConnection(WorkbenchSqlReadConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_rows" in normalized and "r.source_kind = 'bank'" in normalized:
            return [
                {
                    "row_id": "txn_imported_202601_batch_001",
                    "source_kind": "bank",
                    "status": "unpaired",
                    "payload": {
                        "id": "txn_imported_202601_batch_001",
                        "type": "bank",
                        "counterparty_name": "批量账务集中处理",
                        "trade_time": "2026-01-07 15:54:00",
                        "debit_amount": "1200.00",
                    },
                }
            ]
        if "from read_model.workbench_rows" in normalized and "r.source_kind = 'oa'" in normalized:
            return [
                {
                    "row_id": "oa-exp-ba-001",
                    "source_kind": "oa",
                    "status": "unpaired",
                    "payload": {
                        "id": "oa-exp-ba-001",
                        "type": "oa",
                        "apply_type": "日常报销",
                        "amount": "1200.00",
                    },
                }
            ]
        if "from read_model.workbench_rows" in normalized and "r.source_kind = 'oa_attachment_invoice'" in normalized:
            return [
                {
                    "row_id": "oa-att-inv-oa-exp-ba-001-01",
                    "source_kind": "oa_attachment_invoice",
                    "status": "unpaired",
                    "payload": {
                        "id": "oa-att-inv-oa-exp-ba-001-01",
                        "type": "invoice",
                        "derived_from_oa_id": "oa-exp-ba-001",
                    },
                }
            ]
        return []


class WorkbenchGenerationRetentionConnection(WorkbenchSqlReadConnection):
    def __init__(self) -> None:
        super().__init__()
        self.execute_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_generations" in normalized and "status <> 'active'" in normalized:
            return [
                {
                    "generation_id": "old-gen",
                    "scope_key": "2026-01",
                    "status": "superseded",
                    "activated_at": "2026-05-01T00:00:00+00:00",
                    "completed_at": "2026-05-01T00:00:00+00:00",
                    "updated_at": "2026-05-01T00:00:00+00:00",
                }
            ]
        return []

    def execute(self, sql: str, params: tuple = ()) -> int:
        normalized = " ".join(sql.lower().split())
        self.execute_calls.append((normalized, params))
        return 1

    def transaction(self):
        class Transaction:
            def __init__(self, connection: WorkbenchGenerationRetentionConnection) -> None:
                self.connection = connection

            def __enter__(self):
                return self.connection

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

        return Transaction(self)


class WorkbenchConsistencySqlConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        return []


class WorkbenchDuplicateIdentityConsistencyConnection(WorkbenchConsistencySqlConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        return [
            {
                "scope_key": "2026-02",
                "generation_id": "gen-identity-duplicate",
                "row_count": 2,
                "group_count": 2,
                "summary_count": 1,
                "build_metadata": {},
                "actual_row_count": 2,
                "actual_group_count": 2,
                "actual_group_row_count": 2,
                "actual_summary_count": 1,
                "duplicate_invoice_identity_count": 1,
                "duplicate_bank_identity_count": 0,
                "duplicate_identity_samples": [
                    {
                        "object_kind": "invoice",
                        "object_identity_key": "265320000000992",
                        "object_identity_kind": "digital_invoice_no",
                        "zones": ["unpaired", "paired"],
                        "row_ids": ["invoice-formal-project-1", "oa-att-inv-project-1"],
                    }
                ],
            }
        ]


class WorkbenchDuplicateRowMembershipConsistencyConnection(WorkbenchConsistencySqlConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        return [
            {
                "scope_key": "all",
                "generation_id": "gen-row-duplicate",
                "row_count": 2,
                "group_count": 2,
                "summary_count": 1,
                "build_metadata": {},
                "actual_row_count": 2,
                "actual_group_count": 2,
                "actual_group_row_count": 2,
                "actual_summary_count": 1,
                "duplicate_invoice_identity_count": 0,
                "duplicate_bank_identity_count": 0,
                "duplicate_identity_samples": [],
                "duplicate_row_membership_count": 1,
                "duplicate_row_membership_samples": [
                    {
                        "pane": "oa",
                        "row_id": "oa-pay-2050",
                        "zones": ["unpaired"],
                        "groups": [
                            "open:case:decision:2026-02:oa_bank_exact_sum:oa-pay-2050",
                            "open:scope:2026-03:temp:0001",
                        ],
                    }
                ],
            }
        ]


class WorkbenchActiveRelationOpenMembershipConsistencyConnection(WorkbenchConsistencySqlConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        return [
            {
                "scope_key": "all",
                "generation_id": "gen-open-active-relation",
                "row_count": 2,
                "group_count": 2,
                "summary_count": 1,
                "build_metadata": {},
                "actual_row_count": 2,
                "actual_group_count": 2,
                "actual_group_row_count": 2,
                "actual_summary_count": 1,
                "duplicate_invoice_identity_count": 0,
                "duplicate_bank_identity_count": 0,
                "duplicate_identity_samples": [],
                "duplicate_row_membership_count": 0,
                "duplicate_row_membership_samples": [],
                "active_relation_unpaired_membership_count": 2,
                "active_relation_unpaired_membership_samples": [
                    {
                        "case_id": "CASE-AUTO-0013",
                        "pane": "bank",
                        "row_id": "txn_imported_1284",
                        "group_id": "scope:2026-02:temp:0070",
                    }
                ],
            }
        ]


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


def all_scope_group_row_ids(connection: WorkbenchWriteConnection, group_id: str, pane: str) -> list[str]:
    return [
        str(params[4])
        for sql, params in connection.executed
        if "insert into read_model.workbench_group_rows" in sql
        and "values ( %s, 'all', null" in sql
        and params[2] == group_id
        and params[3] == pane
        and params[5] != "collapsed"
    ]


class BulkWorkbenchWriteConnection(WorkbenchWriteConnection):
    def __init__(self) -> None:
        super().__init__()
        self.execute_many_calls: list[tuple[str, list[tuple]]] = []

    def execute_many(self, sql: str, params_seq: list[tuple]) -> int:
        rows = list(params_seq)
        self.execute_many_calls.append((" ".join(sql.lower().split()), rows))
        return len(rows)


class EtcStateWriteConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((" ".join(sql.lower().split()), params))
        return 1


class StaleWorkbenchWriteConnection(WorkbenchWriteConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
        if "from read_model.workbench_snapshots" in self.fetch_one_calls[-1][0]:
            return {"source_versions": {"source_version": 5}}
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


class PendingClaimedBankProjectionConnection(WorkbenchProjectionSettingsConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transaction_relation_claims" in normalized:
            return [{"bank_transaction_id": "bank-claimed-by-progress-oa"}]
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "row_id": "bank-claimed-by-progress-oa",
                    "account_no": "622200001234",
                    "account_name": "交行 1234",
                    "txn_direction": "outflow",
                    "counterparty_name_raw": "进行中OA供应商",
                    "amount": "7000.00",
                    "txn_date": "2026-05-21",
                    "trade_time": "2026-05-21 10:00:00",
                    "summary": "货款",
                    "remark": "",
                    "project_id": None,
                    "raw_payload": {},
                },
                {
                    "row_id": "bank-unclaimed",
                    "account_no": "622200001234",
                    "account_name": "交行 1234",
                    "txn_direction": "outflow",
                    "counterparty_name_raw": "普通供应商",
                    "amount": "5000.00",
                    "txn_date": "2026-05-22",
                    "trade_time": "2026-05-22 10:00:00",
                    "summary": "货款",
                    "remark": "",
                    "project_id": None,
                    "raw_payload": {},
                },
            ]
        return super().fetch_all(sql, params)


class CrossMonthActiveRelationProjectionConnection(WorkbenchProjectionSettingsConnection):
    def __init__(self) -> None:
        super().__init__()
        self.active_relation_query = ""
        self.active_relation_params: tuple = ()

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.workbench_pair_relations" not in normalized:
            return super().fetch_all(sql, params)
        self.active_relation_query = normalized
        self.active_relation_params = params
        return [
            {
                "case_id": "decision:2026-05:bank_invoice_exact_amount:txn_imported_0118:inv_imported_0481",
                "relation_mode": "manual_confirmed",
                "month_scope": "2026-05-01",
                "row_ids": ["txn_imported_0118", "inv_imported_0481"],
                "row_types": ["bank", "invoice"],
                "amount_check": {},
                "special_metadata": {},
                "source_versions": {},
                "raw_payload": {},
            }
        ]


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


class EtcBusinessSummaryProjectionConnection(WorkbenchProjectionSettingsConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.workbench_pair_relations" in normalized:
            self.active_relation_query = normalized
            return []
        if "with submitted_batches as" in normalized and "from app.invoices invoices" in normalized:
            return []
        if "from app.etc_business_batches" in normalized and "join app.etc_invoices etc_invoices" in normalized:
            self.business_summary_query = normalized
            return [
                {
                    "external_etc_batch_id": "etc_20260520_001",
                    "business_batch_id": "etc_business_batch_0004",
                    "business_invoice_count": 0,
                    "business_total_amount": "0.00",
                    "business_batch_payload": {
                        "business_batch_id": "etc_business_batch_0004",
                        "submission_batch_id": "etc_20260520_001",
                        "invoice_ids": ["ETC001", "ETC002"],
                    },
                    "submission_batch_payload": {
                        "etc_batch_id": "etc_20260520_001",
                        "oa_total_amount": "1673.30",
                        "total_amount": "1673.30",
                        "etc_invoice_amount": "27.14",
                        "etc_invoice_count": 37,
                    },
                    "row_id": "ETC001",
                    "invoice_type": "进项发票",
                    "invoice_no": "ETC001",
                    "digital_invoice_no": "ETC001",
                    "invoice_date": "2026-05-20",
                    "counterparty_name": "高速公路通行费",
                    "seller_name": "高速公路通行费",
                    "buyer_name": "云南溯源科技",
                    "amount": "13.57",
                    "total_with_tax": "13.57",
                    "status": "submitted",
                    "workbench_visibility": "hidden_after_etc_submission",
                    "raw_payload": {},
                },
                {
                    "external_etc_batch_id": "etc_20260520_001",
                    "business_batch_id": "etc_business_batch_0004",
                    "business_invoice_count": 0,
                    "business_total_amount": "0.00",
                    "business_batch_payload": {
                        "business_batch_id": "etc_business_batch_0004",
                        "submission_batch_id": "etc_20260520_001",
                        "invoice_ids": ["ETC001", "ETC002"],
                    },
                    "submission_batch_payload": {
                        "etc_batch_id": "etc_20260520_001",
                        "oa_total_amount": "1673.30",
                        "total_amount": "1673.30",
                        "etc_invoice_amount": "27.14",
                        "etc_invoice_count": 37,
                    },
                    "row_id": "ETC002",
                    "invoice_type": "进项发票",
                    "invoice_no": "ETC002",
                    "digital_invoice_no": "ETC002",
                    "invoice_date": "2026-05-20",
                    "counterparty_name": "高速公路通行费",
                    "seller_name": "高速公路通行费",
                    "buyer_name": "云南溯源科技",
                    "amount": "13.57",
                    "total_with_tax": "13.57",
                    "status": "submitted",
                    "workbench_visibility": "hidden_after_etc_submission",
                    "raw_payload": {},
                },
            ]
        return super().fetch_all(sql, params)


class EtcBusinessSummaryWithActiveRelationConnection(EtcBusinessSummaryProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.workbench_pair_relations" in normalized:
            self.active_relation_query = normalized
            return [{"external_etc_batch_id": "etc_20260520_001"}]
        if "business_batches.external_etc_batch_id <> all" in normalized:
            self.business_summary_query = normalized
            return []
        return super().fetch_all(sql, params)


class WorkbenchScopeShardEtcConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from app.etc_business_batches" in normalized and "from app.etc_invoices" in normalized:
            return [{"scope_key": "2026-06"}, {"scope_key": "2026-05"}]
        return []


class ReadModelSnapshotRecorder:
    def __init__(self) -> None:
        self.saved_snapshots: list[tuple[dict[str, object], set[str] | None]] = []

    def save_workbench_read_models(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_keys: set[str] | None = None,
    ) -> None:
        self.saved_snapshots.append((snapshot, changed_scope_keys))


class FakeWorkbenchReadModelService:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_read_model(self, scope_key: str) -> None:
        self.deleted.append(scope_key)


class WorkbenchSqlRuntimeTests(unittest.TestCase):
    def test_transactional_cost_statistics_enqueue_expands_workbench_month_scope(self) -> None:
        from fin_ops_platform.services.postgres_repositories.workbench_relation import (
            _append_read_model_refresh,
            _enqueue_read_model_refreshes_in_transaction,
        )

        connection = ReadModelRefreshTransactionConnection()
        refreshes: list[dict[str, object]] = []

        _append_read_model_refresh(
            refreshes,
            scope_type="cost_statistics",
            scope_key="2026-05",
            reason="workbench_relation_changed",
        )
        _enqueue_read_model_refreshes_in_transaction(connection, refreshes)

        params = connection.fetch_all_params[0]
        scope_keys = [params[index + 3] for index in range(0, len(params), 9)]
        self.assertEqual(scope_keys, ["active:2026-05", "all:2026-05"])

    def test_workbench_sql_source_versions_include_matching_rules_version_for_freshness(self) -> None:
        app = object.__new__(Application)

        versions = app._workbench_sql_read_model_source_versions("2026-05")

        self.assertEqual(
            versions["workbench_formal_relation_rule_version"],
            WORKBENCH_FORMAL_RELATION_RULE_VERSION,
        )
        missing_rules_version = {
            key: value
            for key, value in versions.items()
            if key != "workbench_formal_relation_rule_version"
        }
        self.assertIn(
            "workbench_formal_relation_rule_version_missing",
            app._workbench_sql_read_model_stale_reasons(missing_rules_version, scope_key="2026-05"),
        )
        self.assertIn(
            "workbench_formal_relation_rule_version_mismatch",
            app._workbench_sql_read_model_stale_reasons(
                {**versions, "workbench_formal_relation_rule_version": "old-version"},
                scope_key="2026-05",
            ),
        )

    def test_workbench_sql_all_source_versions_expect_composed_active_month_shards(self) -> None:
        app = object.__new__(Application)

        versions = app._workbench_sql_read_model_source_versions("all")

        self.assertEqual(versions["builder"], WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION)

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
                            "unpaired_count": 1,
                            "exception_count": 0,
                        },
                        "paired": {"groups": []},
                        "unpaired": {"groups": []},
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
                        "summary": {"oa_count": 2, "bank_count": 0, "invoice_count": 1, "paired_count": 1, "unpaired_count": 2, "exception_count": 0},
                        "paired": {"groups": []},
                        "unpaired": {"groups": []},
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

    def test_sql_projection_excludes_bank_rows_claimed_by_in_progress_oa_relation(self) -> None:
        connection = PendingClaimedBankProjectionConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        claimed = set(builder._pending_claimed_bank_transaction_ids_for_month("2026-05"))
        rows = builder._bank_rows("2026-05", excluded_bank_transaction_ids=claimed)

        self.assertEqual([row["id"] for row in rows], ["bank-unclaimed"])


    def test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(connection=WorkbenchProjectionSettingsConnection())

        row = builder._invoice_row_from_sql(
            {
                "row_id": "oa-att-inv-oa-exp-001-stable",
                "invoice_type": "input",
                "invoice_no": "26532000000021026521",
                "digital_invoice_no": "26532000000021026521",
                "invoice_date": "2026-01-06",
                "counterparty_name": "云南城建物业运营集团",
                "seller_name": "云南城建物业运营集团",
                "seller_tax_no": "91530103MA6KHJWK8C",
                "buyer_name": "云南溯源科技有限公司",
                "buyer_tax_no": "915300007194052520",
                "amount": "566.04",
                "tax_rate": "6%",
                "tax_amount": "33.96",
                "total_with_tax": "600.00",
                "tags": ["人工导入"],
                "source_links": [
                    {"source_type": "manual_invoice_import", "batch_id": "batch-1"},
                    {
                        "source_type": "oa_attachment_invoice",
                        "source_workbench_row_id": "oa-att-inv-oa-exp-001-stable",
                        "derived_from_oa_id": "oa-exp-001",
                        "source_attachment_key": "attachment-1",
                        "source_attachment_name": "发票.pdf",
                    },
                ],
                "raw_payload": {"normalized_payload": {"invoice_source": "OA附件解析"}},
            }
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["source_kind"], "oa_attachment_invoice")
        self.assertEqual(row["derived_from_oa_id"], "oa-exp-001")
        self.assertEqual(row["source_workbench_row_id"], "oa-att-inv-oa-exp-001-stable")
        self.assertEqual(row["source_attachment_key"], "attachment-1")
        self.assertEqual(row["source_attachment_name"], "发票.pdf")
        self.assertEqual(row["tags"], ["人工导入", "OA附件"])
        self.assertEqual(row["summary_fields"]["发票来源"], "OA附件解析")

    def test_sql_projection_invoice_row_prefers_oa_attachment_source_link_with_context(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(connection=WorkbenchProjectionSettingsConnection())

        row = builder._invoice_row_from_sql(
            {
                "row_id": "inv-imported-001",
                "invoice_type": "input",
                "invoice_no": "26532000000021026521",
                "digital_invoice_no": "26532000000021026521",
                "invoice_date": "2026-01-06",
                "counterparty_name": "云南城建物业运营集团",
                "seller_name": "云南城建物业运营集团",
                "buyer_name": "云南溯源科技有限公司",
                "amount": "566.04",
                "total_with_tax": "600.00",
                "tags": ["人工导入"],
                "source_links": [
                    {"source_type": "oa_attachment_invoice", "source_id": "legacy-empty-context"},
                    {
                        "source_type": "oa_attachment_invoice",
                        "source_workbench_row_id": "oa-att-inv-oa-exp-1968-item-4",
                        "derived_from_oa_id": "oa-exp-1968:item:4:de54f988bd66",
                        "source_expense_item_id": "oa-exp-1968:item:4:de54f988bd66",
                    },
                ],
                "raw_payload": {"normalized_payload": {"invoice_source": "OA附件解析"}},
            }
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["derived_from_oa_id"], "oa-exp-1968:item:4:de54f988bd66")
        self.assertEqual(row["source_workbench_row_id"], "oa-att-inv-oa-exp-1968-item-4")

    def test_sql_projection_oa_projection_rows_exclude_attachment_invoice_rows(self) -> None:
        class FakeOAQueryService:
            def get_workbench(self, month: str) -> dict[str, object]:
                return {"month": month}

            def sync_oa_row_ids(self, row_ids: list[str]) -> None:
                return None

            def list_record_snapshots(self) -> list[dict[str, object]]:
                return [
                    {"id": "oa-exp-1", "type": "oa", "_month": "2026-01", "_section": "unpaired"},
                    {
                        "id": "oa-att-inv-oa-exp-1-001",
                        "type": "invoice",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-exp-1",
                        "_month": "2026-01",
                        "_section": "unpaired",
                    },
                ]

            def serialize_row(self, row: dict[str, object]) -> dict[str, object]:
                return {key: value for key, value in row.items() if not key.startswith("_")}

        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            oa_query_service=FakeOAQueryService(),
        )

        rows = builder._oa_projection_rows("2026-01")
        missing_rows = builder._oa_projection_rows_by_ids({"oa-att-inv-oa-exp-1-001"})

        self.assertEqual([row["id"] for row in rows], ["oa-exp-1"])
        self.assertEqual(missing_rows, [])

    def test_sql_projection_supplements_source_oa_for_attachment_invoice_rows(self) -> None:
        class FakeOAQueryService:
            def __init__(self) -> None:
                self.synced_row_ids: list[list[str]] = []

            def get_workbench(self, month: str) -> dict[str, object]:
                return {"month": month}

            def sync_oa_row_ids(self, row_ids: list[str]) -> None:
                self.synced_row_ids.append(list(row_ids))

            def list_record_snapshots(self) -> list[dict[str, object]]:
                return [
                    {
                        "id": "oa-exp-cross-month",
                        "type": "oa",
                        "_month": "2026-01",
                        "_section": "unpaired",
                        "amount": "178.00",
                    },
                ]

            def serialize_row(self, row: dict[str, object]) -> dict[str, object]:
                return {key: value for key, value in row.items() if not key.startswith("_")}

        fake_oa = FakeOAQueryService()
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            oa_query_service=fake_oa,
        )
        rows: dict[str, dict[str, object]] = {}
        invoice_rows = [
            {
                "id": "oa-att-inv-cross-month",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-exp-cross-month:item:2:0b1b85793f3d",
            }
        ]

        builder._supplement_source_oa_rows_for_attachment_invoices(rows, invoice_rows)

        self.assertEqual(fake_oa.synced_row_ids, [["oa-exp-cross-month"]])
        self.assertIn("oa-exp-cross-month", rows)
        self.assertEqual(rows["oa-exp-cross-month"]["source_kind"], "oa")

    def test_sql_projection_supplements_in_progress_source_oa_from_sql(self) -> None:
        class EmptyOAQueryService:
            def get_workbench(self, month: str) -> dict[str, object]:
                return {"month": month}

            def sync_oa_row_ids(self, row_ids: list[str]) -> None:
                return None

            def list_record_snapshots(self) -> list[dict[str, object]]:
                return []

            def serialize_row(self, row: dict[str, object]) -> dict[str, object]:
                return dict(row)

        class SourceOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_applications" in normalized and "where row_id = any" in normalized:
                    return [
                        {
                            "row_id": "oa-exp-in-progress",
                            "applicant": "马涛",
                            "application_date": "2026-05-01",
                            "project_name": "差旅",
                            "amount": "833.25",
                            "status": "unpaired",
                            "workflow_status": "in_progress",
                            "normalized_payload": {"reason": "出差"},
                            "raw_payload": {},
                        }
                    ]
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=SourceOAConnection(),
            oa_query_service=EmptyOAQueryService(),
        )
        rows: dict[str, dict[str, object]] = {}
        invoice_rows = [
            {
                "id": "oa-att-inv-in-progress",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-exp-in-progress:item:2:abc",
            }
        ]

        builder._supplement_source_oa_rows_for_attachment_invoices(rows, invoice_rows)

        self.assertIn("oa-exp-in-progress", rows)
        self.assertEqual(rows["oa-exp-in-progress"]["workflow_status"], "in_progress")
        self.assertEqual(rows["oa-exp-in-progress"]["source_kind"], "oa")

    def test_sql_projection_oa_row_keeps_header_amount_but_exposes_detail_sum_for_reconciliation(self) -> None:
        row = {
            "row_id": "oa-exp-daily-2038",
            "applicant": "刘涵静",
            "application_date": "2026-03-02",
            "project_name": "云南溯源科技",
            "amount": "2308.02",
            "normalized_payload": {
                "amount_source": "header",
                "amount_mismatch": {
                    "header_amount": "2308.02",
                    "detail_sum": "2038.02",
                    "difference": "270.00",
                },
                "detail_fields": {
                    "金额来源": "主表总金额",
                    "明细金额合计": "2038.02",
                    "金额差异": "主表总金额 2308.02；明细合计 2038.02；差异 270.00",
                },
            },
            "raw_payload": {},
        }

        payload = WorkbenchSqlProjectionBuilder._oa_row_from_sql(row)

        assert payload is not None
        self.assertEqual(payload["amount"], "2308.02")
        self.assertEqual(payload["reconciliation_amount"], "2038.02")
        self.assertEqual(payload["amount_source"], "header")

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

        payload = builder._group_payload("2026-02", with_test_object_identities(rows_by_id), [relation])

        groups = payload["paired"]["groups"]
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group["group_id"], "case:CASE-BATCH-txn_imported_1328")
        self.assertEqual(group["display_mode"], "collapsed_summary")
        self.assertTrue(group["default_collapsed"])
        self.assertEqual(group["collapsed_row_counts"], {"invoice": 2})
        self.assertEqual(len(group["oa_rows"]), 1)
        self.assertEqual(len(group["bank_rows"]), 1)
        self.assertEqual(group["invoice_rows"], [])
        self.assertEqual([row["id"] for row in group["collapsed_rows"]["invoice"]], ["inv-hidden-etc-1", "inv-hidden-etc-2"])
        oa_row = group["oa_rows"][0]
        self.assertEqual(oa_row["etc_batch_id"], "ETC-OA-20260215-154900")
        self.assertIn("ETC批量提交", oa_row["tags"])
        summary_row = group["summary_row"]
        self.assertEqual(summary_row["source_kind"], "etc_invoice_summary")
        self.assertEqual(summary_row["case_id"], "CASE-BATCH-txn_imported_1328")
        self.assertEqual(summary_row["invoice_bank_relation"]["label"], "已关联ETC发票")
        self.assertEqual(summary_row["etc_invoice_count"], 2)
        self.assertEqual(summary_row["total_with_tax"], "144.50")
        self.assertEqual(summary_row["etc_invoice_detail_count"], 2)


    def test_sql_projection_keeps_active_manual_oa_bank_relation_paired_without_invoice(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=ReadModelSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-exp-2046": {
                "id": "oa-exp-2046",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "4200.00",
                "applicant": "刘树刚",
                "project_name": "云南溯源科技",
                "apply_type": "日常报销",
            },
            "txn_imported_1387": {
                "id": "txn_imported_1387",
                "type": "bank",
                "source_kind": "bank",
                "status": "unpaired",
                "debit_amount": "4200.00",
                "counterparty_name": "普通供应商",
                "trade_time": "2026-03-12 10:16:00",
                "summary": "报销",
            },
        }
        relation = {
            "case_id": "CASE-MANUAL-PARTIAL",
            "relation_mode": "manual_confirmed",
            "row_ids": ["txn_imported_1387", "oa-exp-2046"],
            "row_types": ["bank", "oa"],
        }

        payload = builder._group_payload("2026-03", with_test_object_identities(rows_by_id), [relation])

        self.assertEqual(payload["unpaired"]["groups"], [])
        paired_groups = payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        group = paired_groups[0]
        self.assertEqual(group["group_id"], "case:CASE-MANUAL-PARTIAL")
        self.assertEqual(group["group_type"], "relation")
        self.assertEqual(group["relation_mode"], "manual_confirmed")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-exp-2046"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["txn_imported_1387"])
        self.assertTrue(all(row["status"] == "paired" for row in [*group["oa_rows"], *group["bank_rows"]]))
        self.assertTrue(all(row["case_id"] == "CASE-MANUAL-PARTIAL" for row in [*group["oa_rows"], *group["bank_rows"]]))

    def test_sql_projection_emits_source_oa_for_deterministic_multi_oa_relation_alignment(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=ReadModelSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-29350": {
                "id": "oa-29350",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "29350.00",
                "project_name": "大理卷烟厂余热综合利用项目",
            },
            "oa-88050": {
                "id": "oa-88050",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "88050.00",
                "project_name": "大理卷烟厂余热综合利用项目",
            },
            "bank-29350": {
                "id": "bank-29350",
                "type": "bank",
                "source_kind": "bank_transaction",
                "status": "unpaired",
                "debit_amount": "29350.00",
                "counterparty_name": "云南辰飞机电工程有限公司",
            },
            "bank-60000": {
                "id": "bank-60000",
                "type": "bank",
                "source_kind": "bank_transaction",
                "status": "unpaired",
                "debit_amount": "60000.00",
                "counterparty_name": "云南辰飞机电工程有限公司",
            },
            "bank-28050": {
                "id": "bank-28050",
                "type": "bank",
                "source_kind": "bank_transaction",
                "status": "unpaired",
                "debit_amount": "28050.00",
                "counterparty_name": "云南辰飞机电工程有限公司",
            },
            "invoice-117400": {
                "id": "invoice-117400",
                "type": "invoice",
                "source_kind": "manual_invoice_import",
                "status": "unpaired",
                "amount": "117400.00",
                "seller_name": "云南辰飞机电工程有限公司",
            },
        }
        relation = {
            "case_id": "CASE-MULTI-OA-ALIGNMENT",
            "relation_mode": "manual_confirmed",
            "row_ids": list(rows_by_id),
            "row_types": ["oa", "oa", "bank", "bank", "bank", "invoice"],
            "amount_check": {"status": "matched"},
        }

        payload = builder._group_payload("2026-05", with_test_object_identities(rows_by_id), [relation])

        groups = payload["paired"]["groups"]
        self.assertEqual(len(groups), 1)
        bank_rows = {row["id"]: row for row in groups[0]["bank_rows"]}
        self.assertEqual(bank_rows["bank-29350"]["source_oa_id"], "oa-29350")
        self.assertEqual(bank_rows["bank-29350"]["source_oa_row_id"], "oa-29350")
        self.assertEqual(bank_rows["bank-60000"]["source_oa_id"], "oa-88050")
        self.assertEqual(bank_rows["bank-28050"]["source_oa_id"], "oa-88050")
        self.assertEqual(
            bank_rows["bank-60000"]["special_metadata"]["row_alignment"]["links"][1]["bank_row_ids"],
            ["bank-60000", "bank-28050"],
        )

    def test_sql_projection_keeps_active_batch_accounting_oa_bank_relation_paired(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=ReadModelSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-exp-2045": {
                "id": "oa-exp-2045",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "1935.45",
                "applicant": "刘树刚",
                "project_name": "云南溯源科技",
                "apply_type": "日常报销",
            },
            "txn_imported_1386": {
                "id": "txn_imported_1386",
                "type": "bank",
                "source_kind": "bank",
                "status": "unpaired",
                "debit_amount": "1935.45",
                "counterparty_name": "批量账务集中处理",
                "trade_time": "2026-03-12 10:16:00",
                "summary": "报销",
            },
        }
        relation = {
            "case_id": "CASE-BATCH-txn_imported_1386",
            "relation_mode": "manual_confirmed",
            "row_ids": ["txn_imported_1386", "oa-exp-2045"],
            "row_types": ["bank", "oa"],
            "special_metadata": {
                "source": "batch_accounting",
                "created_by": "YNSYLP005",
                "bank_row_id": "txn_imported_1386",
                "oa_row_ids": ["oa-exp-2045"],
            },
        }

        payload = builder._group_payload("2026-03", with_test_object_identities(rows_by_id), [relation])

        self.assertEqual(payload["unpaired"]["groups"], [])
        paired_groups = payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        group = paired_groups[0]
        self.assertEqual(group["group_id"], "case:CASE-BATCH-txn_imported_1386")
        self.assertEqual(group["group_type"], "relation")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-exp-2045"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["txn_imported_1386"])
        self.assertEqual(group["bank_rows"][0]["special_metadata"]["source"], "batch_accounting")

    def test_sql_projection_keeps_active_batch_accounting_multi_oa_invoice_relation_paired(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=ReadModelSnapshotRecorder(),
        )
        rows_by_id = {
            "txn_imported_1393": {
                "id": "txn_imported_1393",
                "type": "bank",
                "source_kind": "bank",
                "status": "unpaired",
                "debit_amount": "1273.06",
                "counterparty_name": "批量账务集中处理",
                "trade_time": "2026-03-19 10:32:00",
                "summary": "报销",
            },
            "oa-exp-1991": {
                "id": "oa-exp-1991",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "470.40",
                "applicant": "马涛",
                "project_name": "昭通卷烟厂 2025-2028年度能源集中监控平台项目",
                "apply_type": "日常报销",
            },
            "oa-exp-2008": {
                "id": "oa-exp-2008",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "332.44",
                "applicant": "莫永洪",
                "project_name": "昭通卷烟厂 2025-2028年度能源集中监控平台项目",
                "apply_type": "日常报销",
            },
            "oa-exp-2003": {
                "id": "oa-exp-2003",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "150.00",
                "applicant": "莫永洪",
                "project_name": "云南溯源科技",
                "apply_type": "日常报销",
            },
            "oa-exp-1980": {
                "id": "oa-exp-1980",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "280.00",
                "applicant": "胡珞",
                "project_name": "玉溪卷烟厂复烤车间技术升级改造项目",
                "apply_type": "日常报销",
            },
            "oa-exp-2012": {
                "id": "oa-exp-2012",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "50.22",
                "applicant": "胡珞",
                "project_name": "玉溪卷烟厂复烤车间技术升级改造项目",
                "apply_type": "日常报销",
            },
            "inv_imported_0167": {
                "id": "inv_imported_0167",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "status": "unpaired",
                "amount": "470.40",
                "total_with_tax": "470.40",
                "seller_name": "交通服务商",
                "invoice_type": "进项发票",
            },
            "inv_imported_0171": {
                "id": "inv_imported_0171",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "status": "unpaired",
                "amount": "332.44",
                "total_with_tax": "332.44",
                "seller_name": "餐饮服务商",
                "invoice_type": "进项发票",
            },
            "inv_imported_0180": {
                "id": "inv_imported_0180",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "status": "unpaired",
                "amount": "150.00",
                "total_with_tax": "150.00",
                "seller_name": "事故处理服务商",
                "invoice_type": "进项发票",
            },
        }
        relation = {
            "case_id": "CASE-BATCH-txn_imported_1393",
            "relation_mode": "batch_accounting",
            "row_ids": list(rows_by_id),
            "row_types": [
                "bank",
                "oa",
                "oa",
                "oa",
                "oa",
                "oa",
                "invoice",
                "invoice",
                "invoice",
            ],
            "special_metadata": {
                "source": "batch_accounting",
                "created_by": "YNSYLP006",
                "bank_row_id": "txn_imported_1393",
                "oa_row_ids": ["oa-exp-1991", "oa-exp-2008", "oa-exp-2003", "oa-exp-1980", "oa-exp-2012"],
            },
            "amount_check": {
                "status": "mismatch",
                "direction": "expense",
                "bank_amount": "1273.06",
                "oa_amount": "1283.06",
                "amount_delta": "-10.00",
                "requires_note": True,
            },
        }

        payload = builder._group_payload("2026-03", with_test_object_identities(rows_by_id), [relation])

        self.assertEqual(payload["unpaired"]["groups"], [])
        paired_groups = payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        group = paired_groups[0]
        self.assertEqual(group["group_id"], "case:CASE-BATCH-txn_imported_1393")
        self.assertEqual(group["group_type"], "relation")
        self.assertEqual(group["reason"], "active_formal_relation")
        self.assertEqual(group["relation_mode"], "batch_accounting")
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["txn_imported_1393"])
        self.assertCountEqual(
            [row["id"] for row in group["oa_rows"]],
            ["oa-exp-1991", "oa-exp-2008", "oa-exp-2003", "oa-exp-1980", "oa-exp-2012"],
        )
        self.assertCountEqual(
            [row["id"] for row in group["invoice_rows"]],
            ["inv_imported_0167", "inv_imported_0171", "inv_imported_0180"],
        )
        self.assertEqual(group["bank_rows"][0]["special_metadata"]["source"], "batch_accounting")

    def test_sql_projection_attaches_etc_summary_from_relation_metadata_batch_link(self) -> None:
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
            "special_metadata": {
                "source": "batch_accounting",
                "etc_batch_link": {
                    "external_etc_batch_id": "ETC-OA-20260215-154900",
                    "source": "existing_etc_batch_link",
                },
            },
            "amount_check": {"status": "matched"},
        }

        payload = builder._group_payload("2026-02", with_test_object_identities(rows_by_id), [relation])

        groups = payload["paired"]["groups"]
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group["group_id"], "case:CASE-BATCH-txn_imported_1328")
        self.assertEqual(group["invoice_rows"], [])
        self.assertEqual(group["summary_row"]["source_kind"], "etc_invoice_summary")
        self.assertEqual(group["summary_row"]["case_id"], "CASE-BATCH-txn_imported_1328")
        self.assertEqual(group["oa_rows"][0]["etc_batch_id"], "ETC-OA-20260215-154900")

    def test_sql_projection_creates_unpaired_etc_summary_from_submitted_business_batch(self) -> None:
        connection = EtcBusinessSummaryProjectionConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        rows = builder._unpaired_etc_invoice_summary_rows("2026-05")

        self.assertEqual(len(rows), 1)
        summary_row = rows[0]
        self.assertEqual(summary_row["source_kind"], "etc_invoice_summary")
        self.assertEqual(summary_row["etc_batch_id"], "etc_20260520_001")
        self.assertEqual(summary_row["total_with_tax"], "27.14")
        self.assertEqual(summary_row["amount"], "27.14")
        self.assertEqual(summary_row["amount_value"], "27.14")
        self.assertEqual(summary_row["etc_invoice_count"], 2)
        self.assertEqual(summary_row["invoice_bank_relation"]["code"], "pending_oa_bank_match")
        self.assertIn("ETC001", summary_row["detail_fields"]["发票清单"])
        self.assertIn("ETC002", summary_row["detail_fields"]["发票清单"])
        self.assertIn("business_batches.scope_month = %s::date", connection.business_summary_query)
        self.assertNotIn("etc_invoices.scope_month = %s::date", connection.business_summary_query)
        self.assertEqual([row["id"] for row in summary_row["etc_invoice_detail_rows"]], ["ETC001", "ETC002"])


    def test_sql_projection_excludes_unpaired_etc_summary_when_batch_has_active_relation(self) -> None:
        connection = EtcBusinessSummaryWithActiveRelationConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        rows = builder._unpaired_etc_invoice_summary_rows("2026-05")

        self.assertEqual(rows, [])
        self.assertIn("from app.workbench_pair_relations", connection.active_relation_query)

    def test_sql_projection_reads_cross_month_active_relations_by_canonical_member_month(self) -> None:
        connection = CrossMonthActiveRelationProjectionConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        relations = builder._active_pair_relations_for_month("2026-06", {"inv_imported_0481"})

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["case_id"], "decision:2026-05:bank_invoice_exact_amount:txn_imported_0118:inv_imported_0481")
        self.assertIn("relation.month_scope = %s::date", connection.active_relation_query)
        self.assertIn("join app.bank_transactions bank", connection.active_relation_query)
        self.assertIn("join app.invoices invoice", connection.active_relation_query)
        self.assertIn("join app.oa_applications oa", connection.active_relation_query)
        self.assertEqual(
            connection.active_relation_params,
            (["inv_imported_0481"], "2026-06-01", "2026-06-01", "2026-06-01", "2026-06-01"),
        )

    def test_sql_projection_scope_shards_include_etc_business_sources_and_active_month_generations(self) -> None:
        connection = WorkbenchScopeShardEtcConnection()
        builder = WorkbenchSqlProjectionBuilder(connection=connection)

        shards = builder.list_workbench_scope_shards("all")

        self.assertEqual(shards, ["2026-06", "2026-05"])
        query = connection.fetch_all_calls[0][0]
        self.assertIn("from app.etc_business_batches", query)
        self.assertIn("from app.etc_invoices", query)
        self.assertIn("from read_model.workbench_generations", query)


    def test_etc_state_repository_persists_business_batch_reported_submission_amount(self) -> None:
        connection = EtcStateWriteConnection()
        repository = PostgresOpsTaxEtcRepository(connection)

        repository.save_etc_state({
            "batches": {
                "etc_20260520_001": {
                    "status": "submitted_confirmed",
                    "issue_start_date": "2026-05-20",
                    "invoice_ids": ["ETC001", "ETC002"],
                    "oa_total_amount": "1673.30",
                    "total_amount": "1673.30",
                    "etc_invoice_amount": "27.14",
                    "etc_invoice_count": 37,
                }
            },
            "business_batches": {
                "etc_business_batch_0004": {
                    "status": "manually_marked_submitted",
                    "submission_batch_id": "etc_20260520_001",
                    "invoice_ids": ["ETC001", "ETC002"],
                    "created_at": "2026-05-20T09:00:00+08:00",
                }
            },
        })

        business_batch_writes = [
            params
            for sql, params in connection.executed
            if "insert into app.etc_business_batches" in sql
        ]
        self.assertEqual(len(business_batch_writes), 1)
        params = business_batch_writes[0]
        self.assertEqual(params[4], "2026-05-01")
        self.assertEqual(params[5], 37)
        self.assertEqual(params[6], "1673.30")

    def test_repository_reads_workbench_snapshot_and_dirty_status_without_state_fallback(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_row={
                "scope_key": "2026-05",
                "cache_status": "fresh",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "payload": {"unpaired": {"groups": []}},
                "raw_payload": {},
            },
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="2026-05")

        self.assertEqual(view["payload"], {"unpaired": {"groups": []}})
        self.assertEqual(view["refresh_status"], "refreshing")
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_reads_paginated_workbench_rows_from_sql_read_model(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_row={
                "scope_key": "2026-05",
                "cache_status": "fresh",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "payload": {"unpaired": {"groups": []}},
                "row_count": 1,
            }
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(
            scope_key="2026-05",
            page=2,
            page_size=25,
            status="unpaired",
            source_kind="bank_transaction",
            search="供应商",
        )

        self.assertEqual(view["rows_page"]["page"], 2)
        self.assertEqual(view["rows_page"]["page_size"], 25)
        self.assertEqual(view["rows_page"]["rows"], [{"id": "bank-row-1"}])
        self.assertTrue(any("from read_model.workbench_rows" in sql for sql, _params in connection.fetch_all_calls))


    def test_repository_reads_all_scope_view_from_active_generation_snapshot(self) -> None:
        connection = ActiveAllWorkbenchSnapshotConnection()
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="all")

        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        self.assertEqual(view["active_generation_id"], "gen-all-active")
        self.assertEqual(view["read_model_version"], "gen-all-active")
        self.assertEqual(view["row_count"], 3)
        self.assertEqual(view["source_versions"]["workbench_formal_relation_rule_version"], "rules-v2")
        self.assertEqual(view["payload"]["paired"]["groups"][0]["group_id"], "case:active-all")
        self.assertFalse(
            any(
                "from read_model.workbench_snapshots" in sql and "scope_key <> 'all'" in sql
                for sql, _params in all_queries
            )
        )



    def test_repository_fails_closed_when_all_scope_active_generation_is_missing(self) -> None:
        connection = WorkbenchAllRowsPageConnection()
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(
            scope_key="all",
            page=1,
            page_size=50,
            source_kind="oa_attachment_invoice",
        )

        self.assertIsNone(view)
        self.assertFalse(
            any(
                "from read_model.workbench_snapshots" in sql and "scope_key <> 'all'" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_repository_reads_all_scope_filtered_page_from_active_all_summary(self) -> None:
        connection = ActiveAllRowsPageConnection()
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(
            scope_key="all",
            page=1,
            page_size=50,
            source_kind="oa_attachment_invoice",
        )

        self.assertEqual(view["payload"]["summary"]["oa_count"], 1)
        self.assertEqual(view["source_versions"]["workbench_formal_relation_rule_version"], "rules-v2")
        self.assertEqual(view["refresh_status"], "fresh")
        self.assertEqual(view["rows_page"]["rows"][0]["id"], "oa-att-inv-1")
        self.assertFalse(
            any(
                "from read_model.workbench_snapshots" in sql and "scope_key <> 'all'" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_repository_materializes_legacy_workbench_view_from_groups_when_snapshot_is_lightweight(self) -> None:
        connection = LightweightWorkbenchSnapshotConnection()
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="2026-05")

        self.assertEqual(view["source_versions"]["source_version"], 12)
        self.assertEqual(view["payload"]["summary"]["oa_count"], 1)
        self.assertEqual(view["payload"]["unpaired"]["groups"][0]["group_id"], "case:LIGHT-1")
        self.assertEqual(view["payload"]["unpaired"]["groups"][0]["oa_rows"][0]["id"], "oa-light-1")
        self.assertEqual(view["payload"]["unpaired"]["groups"][0]["bank_rows"][0]["id"], "bank-light-1")
        self.assertNotIn("workbench_group_rows_materialized", view["payload"]["unpaired"]["groups"][0])
        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        self.assertTrue(
            any(
                "from read_model.workbench_groups" in sql
                and params == ("2026-05", "gen-lightweight")
                for sql, params in all_queries
            )
        )
        self.assertTrue(any("join read_model.workbench_group_rows" in sql for sql, _params in all_queries))

    def test_repository_reads_workbench_summary_without_full_snapshot_payloads(self) -> None:
        connection = MaterializedWorkbenchSummaryConnection()
        repository = PostgresReadModelRepository(connection)

        summary = repository.get_workbench_summary(scope_key="all")

        self.assertEqual(summary["summary"]["oa_count"], 10)
        self.assertEqual(summary["summary"]["bank_count"], 11)
        self.assertEqual(summary["summary"]["invoice_count"], 12)
        self.assertEqual(summary["summary"]["paired_count"], 13)
        self.assertEqual(summary["summary"]["unpaired_count"], 14)
        self.assertEqual(summary["invoice_inventory"]["system_total"], 99)
        self.assertEqual(summary["read_model_status"], "fresh")
        self.assertEqual(summary["generated_at"], "2026-05-22T10:00:00+00:00")
        self.assertFalse(
            any("jsonb_array_length(payload->'bank_rows')" in sql for sql, _params in connection.fetch_all_calls)
        )
        self.assertFalse(
            any(
                "from read_model.workbench_snapshots" in sql and "payload, raw_payload" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_repository_missing_workbench_summary_does_not_repair_from_group_rows(self) -> None:
        connection = WorkbenchSummaryGroupsConnection(dirty_status="processing")
        repository = PostgresReadModelRepository(connection)

        summary = repository.get_workbench_summary(scope_key="all")

        self.assertIsNone(summary)
        self.assertTrue(any("from read_model.workbench_summary" in sql for sql, _params in connection.fetch_one_calls))
        self.assertFalse(
            any("left join read_model.workbench_group_rows" in sql for sql, _params in connection.fetch_all_calls)
        )
        self.assertFalse(any("from app.invoices" in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_reads_materialized_workbench_summary_without_hot_path_repair(self) -> None:
        connection = MaterializedWorkbenchSummaryConnection()
        repository = PostgresReadModelRepository(connection)

        summary = repository.get_workbench_summary(scope_key="all")

        self.assertEqual(summary["summary"]["oa_count"], 10)
        self.assertEqual(summary["summary"]["bank_count"], 11)
        self.assertEqual(summary["summary"]["invoice_count"], 12)
        self.assertEqual(summary["summary"]["paired_count"], 13)
        self.assertEqual(summary["summary"]["unpaired_count"], 14)
        self.assertNotIn("diagnostics", summary)
        self.assertEqual(summary["invoice_inventory"]["system_total"], 99)
        self.assertEqual(summary["read_model_status"], "fresh")
        self.assertTrue(any("from read_model.workbench_summary" in sql for sql, _params in connection.fetch_one_calls))
        self.assertFalse(
            any("left join read_model.workbench_group_rows" in sql for sql, _params in connection.fetch_all_calls)
        )
        self.assertFalse(any("from app.bank_transactions" in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_reads_workbench_groups_page_from_structured_groups(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="unpaired",
            page=1,
            page_size=1,
            source_kind="bank_transaction",
            search="供应商",
            sort="bank:desc",
        )

        self.assertEqual(page["zone"], "unpaired")
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

        page = repository.get_workbench_groups_page(scope_key="all", zone="unpaired", page=1, page_size=25)

        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        self.assertEqual(page["active_generation_id"], COMPOSED_ALL_VERSION)
        self.assertEqual(page["read_model_version"], COMPOSED_ALL_VERSION)
        self.assertTrue(
            any(
                "join read_model.workbench_generations gen" in sql
                and "g.scope_key <> 'all'" in sql
                and "gen.status = 'active'" in sql
                for sql, _params in all_queries
            )
        )
        self.assertFalse(any("g.generation_id = %s" in sql and "gen-active" in params for sql, params in all_queries))
        self.assertTrue(any("r.generation_id = physical_group.generation_id" in sql for sql, _params in all_queries))
        self.assertTrue(
            any("r.group_id = physical_group.group_id" in sql for sql, _params in all_queries)
        )


    def test_batch_accounting_loader_reads_only_active_workbench_generations(self) -> None:
        connection = BatchAccountingActiveGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        payload = repository.load_batch_accounting_workbench_payload(bank_year="2026")

        self.assertEqual(payload["unpaired"]["groups"][0]["bank_rows"][0]["id"], "txn_imported_202601_batch_001")
        self.assertEqual(payload["unpaired"]["groups"][0]["oa_rows"][0]["id"], "oa-exp-ba-001")
        self.assertEqual(payload["unpaired"]["groups"][0]["invoice_rows"][0]["id"], "oa-att-inv-oa-exp-ba-001-01")
        workbench_row_queries = [
            sql for sql, _params in connection.fetch_all_calls if "from read_model.workbench_rows" in sql
        ]
        self.assertEqual(len(workbench_row_queries), 3)
        for sql in workbench_row_queries:
            self.assertIn("join read_model.workbench_generations", sql)
            self.assertIn("status = 'active'", sql)
            self.assertIn("generation_id", sql)
        bank_query = next(sql for sql in workbench_row_queries if "r.source_kind = 'bank'" in sql)
        oa_query = next(sql for sql in workbench_row_queries if "r.source_kind = 'oa'" in sql)
        invoice_query = next(sql for sql in workbench_row_queries if "r.source_kind = 'oa_attachment_invoice'" in sql)
        self.assertIn("r.scope_month >= %s::date", bank_query)
        self.assertIn("r.payload->>'apply_type' like %s", oa_query)
        self.assertIn("r.payload->>'expense_type' like %s", oa_query)
        self.assertNotIn("r.scope_month >= %s::date", oa_query)
        self.assertNotIn("r.scope_month >= %s::date", invoice_query)

    def test_repository_groups_page_pins_versions_counts_and_rows_to_single_active_generation(self) -> None:
        connection = SwitchingActiveWorkbenchGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(scope_key="all", zone="paired", page=1, page_size=25)

        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        self.assertEqual(page["active_generation_id"], COMPOSED_ALL_VERSION)
        self.assertEqual(
            page["source_versions"],
            {"builder": WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION, "source_version": 12},
        )
        self.assertTrue(
            any(
                "count(*) as total_count" in sql
                and "join read_model.workbench_generations gen" in sql
                and "g.scope_key <> 'all'" in sql
                for sql, params in connection.fetch_one_calls
            )
        )
        self.assertTrue(
            any(
                "select group_id, source_group_id, zone, payload, raw_payload" in sql
                and "join read_model.workbench_generations gen" in sql
                and "g.scope_key <> 'all'" in sql
                for sql, params in connection.fetch_all_calls
            )
        )

    def test_repository_summary_source_versions_are_pinned_to_active_generation(self) -> None:
        connection = SwitchingActiveWorkbenchGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        summary = repository.get_workbench_summary(scope_key="all")

        self.assertEqual(summary["active_generation_id"], COMPOSED_ALL_VERSION)
        self.assertEqual(
            summary["source_versions"],
            {"builder": WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION, "source_version": 12},
        )

    def test_repository_composed_all_groups_counts_without_materialized_generation_stats(self) -> None:
        connection = WorkbenchGenerationStatsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(scope_key="all", zone="paired", page=1, page_size=25)

        self.assertEqual(page["total"], 2)
        self.assertEqual(page["row_counts"], {"oa": 3, "bank": 4, "invoice": 5, "rows": 12})
        self.assertFalse(
            any("from read_model.workbench_generation_stats" in sql for sql, _params in connection.fetch_one_calls)
        )
        self.assertTrue(
            any(
                "count(distinct (r.pane, coalesce(nullif(r.object_identity_key, ''), r.row_id))) filter" in sql
                for sql, _params in connection.fetch_one_calls
            )
        )

    def test_repository_workbench_groups_cache_version_uses_active_generation(self) -> None:
        connection = ActiveWorkbenchGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        version = repository.workbench_groups_cache_version(scope_key="all")

        self.assertEqual(version, f"{WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION}:{COMPOSED_ALL_VERSION}")
        self.assertTrue(
            any(
                "select scope_key, generation_id, source_versions" in sql
                and "scope_key <> 'all'" in sql
                and "status = 'active'" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_repository_workbench_generation_retention_never_deletes_active_generations(self) -> None:
        connection = WorkbenchGenerationRetentionConnection()
        repository = PostgresReadModelRepository(connection)

        result = repository.prune_workbench_generations(
            keep_recent_generations_per_scope=2,
            keep_days=7,
            dry_run=False,
        )

        self.assertEqual(result["deleted_count"], 1)
        self.assertTrue(connection.execute_calls)
        self.assertTrue(
            any(
                "delete from read_model.workbench_generations" in sql
                and "status <> 'active'" in sql
                for sql, _params in connection.execute_calls
            )
        )

    def test_repository_generation_consistency_filters_active_generations_before_aggregating_read_models(self) -> None:
        connection = WorkbenchConsistencySqlConnection()

        failures = PostgresReadModelRepository._workbench_generation_consistency_failures(
            connection,
            scope_key="all",
        )

        self.assertEqual(failures, [])
        sql = connection.fetch_all_calls[0][0]
        self.assertIn("with target_generations as", sql)
        self.assertIn("join target_generations", sql)
        self.assertNotIn(
            "with row_counts as ( select generation_id, scope_key, count(distinct row_id)::bigint as actual_row_count from read_model.workbench_rows group by generation_id, scope_key",
            sql,
        )

    def test_repository_generation_consistency_reports_cross_zone_invoice_identity_duplicates(self) -> None:
        connection = WorkbenchDuplicateIdentityConsistencyConnection()

        failures = PostgresReadModelRepository._workbench_generation_consistency_failures(
            connection,
            scope_key="2026-02",
        )

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["duplicate_invoice_identity_count"], 1)
        self.assertIn("duplicate_invoice_identity_cross_zone count=1", failures[0]["reasons"])
        self.assertEqual(
            failures[0]["duplicate_identity_samples"][0]["object_identity_key"],
            "265320000000992",
        )
        sql = connection.fetch_all_calls[0][0]
        self.assertIn("duplicate_identity_counts as", sql)
        self.assertIn("object_identity_kind in ('digital_invoice_no', 'invoice_code_no')", sql)

    def test_repository_generation_consistency_reports_duplicate_row_memberships(self) -> None:
        connection = WorkbenchDuplicateRowMembershipConsistencyConnection()

        failures = PostgresReadModelRepository._workbench_generation_consistency_failures(
            connection,
            scope_key="all",
        )

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["duplicate_row_membership_count"], 1)
        self.assertIn("duplicate_row_membership count=1", failures[0]["reasons"])
        self.assertEqual(
            failures[0]["duplicate_row_membership_samples"][0]["row_id"],
            "oa-pay-2050",
        )
        sql = connection.fetch_all_calls[0][0]
        self.assertIn("duplicate_row_membership_counts as", sql)

    def test_repository_generation_consistency_reports_active_relation_rows_in_unpaired_zone(self) -> None:
        connection = WorkbenchActiveRelationOpenMembershipConsistencyConnection()

        failures = PostgresReadModelRepository._workbench_generation_consistency_failures(
            connection,
            scope_key="all",
        )

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["active_relation_unpaired_membership_count"], 2)
        self.assertIn("active_relation_unpaired_membership count=2", failures[0]["reasons"])
        self.assertEqual(
            failures[0]["active_relation_unpaired_membership_samples"][0]["row_id"],
            "txn_imported_1284",
        )
        sql = connection.fetch_all_calls[0][0]
        self.assertIn("active_relation_unpaired_membership_counts as", sql)
        self.assertIn("join app.workbench_pair_relations rel", sql)


    def test_workbench_refresh_status_api_maps_statement_timeout_to_retryable_unavailable(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = SimpleNamespace(queue_repository=QueueRecorder(), redis_helper=None)
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_refresh_status": lambda _self, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("canceling statement due to statement timeout")
                )
            },
        )()

        response = app._handle_api_workbench_refresh_status("all")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.SERVICE_UNAVAILABLE))
        self.assertEqual(payload["error"], "read_model_temporarily_unavailable")
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["scope_key"], "all")
        self.assertEqual(payload["retryable"], True)

    def test_prune_workbench_generations_cli_defaults_to_dry_run(self) -> None:
        from fin_ops_platform.tools import prune_workbench_generations

        calls: list[dict[str, object]] = []

        class FakeRepository:
            def __init__(self, _connection: object) -> None:
                pass

            def prune_workbench_generations(self, **kwargs: object) -> dict[str, object]:
                calls.append(dict(kwargs))
                return {
                    "dry_run": kwargs.get("dry_run"),
                    "candidate_count": 1,
                    "deleted_count": 0,
                    "generations": [{"generation_id": "old-gen"}],
                }

        with patch.object(prune_workbench_generations.PostgresSettings, "from_env", return_value=object()):
            with patch.object(prune_workbench_generations, "PostgresConnection", return_value=object()):
                with patch.object(prune_workbench_generations, "PostgresReadModelRepository", FakeRepository):
                    exit_code = prune_workbench_generations.main([], stdout=StringIO())

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0]["keep_recent_generations_per_scope"], 1)
        self.assertEqual(calls[0]["keep_days"], 0)
        self.assertEqual(calls[0]["limit"], 500)
        self.assertEqual(calls[0]["dry_run"], True)

    def test_prune_workbench_generations_cli_allows_zero_keep_days_for_emergency_cleanup(self) -> None:
        from fin_ops_platform.tools import prune_workbench_generations

        calls: list[dict[str, object]] = []

        class FakeRepository:
            def __init__(self, _connection: object) -> None:
                pass

            def prune_workbench_generations(self, **kwargs: object) -> dict[str, object]:
                calls.append(dict(kwargs))
                return {
                    "dry_run": kwargs.get("dry_run"),
                    "candidate_count": 1,
                    "deleted_count": 0,
                    "generations": [{"generation_id": "old-gen"}],
                }

        with patch.object(prune_workbench_generations.PostgresSettings, "from_env", return_value=object()):
            with patch.object(prune_workbench_generations, "PostgresConnection", return_value=object()):
                with patch.object(prune_workbench_generations, "PostgresReadModelRepository", FakeRepository):
                    exit_code = prune_workbench_generations.main(
                        ["--keep-days", "0", "--dry-run"],
                        stdout=StringIO(),
                    )

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0]["keep_days"], 0)
        self.assertEqual(calls[0]["dry_run"], True)

    def test_repository_retention_preview_allows_zero_keep_days(self) -> None:
        class PreviewConnection:
            def __init__(self) -> None:
                self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

            def fetch_all(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
                self.fetch_all_calls.append((sql, params))
                return []

        connection = PreviewConnection()
        repository = PostgresReadModelRepository(connection)

        result = repository.preview_workbench_generation_retention(
            keep_recent_generations_per_scope=1,
            keep_days=0,
            limit=10,
        )

        self.assertEqual(result["keep_days"], 0)
        self.assertEqual(connection.fetch_all_calls[0][1], (1, 0, 10))

    def test_repository_filters_workbench_groups_page_from_structured_group_rows(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.get_workbench_groups_page(
            scope_key="all",
            zone="unpaired",
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
            zone="unpaired",
            page=1,
            page_size=25,
            search_by_pane={"bank": "建行"},
            column_filters={"bank": {"amount": ["支出"]}},
        )

        all_queries = [*connection.fetch_one_calls, *connection.fetch_all_calls]
        group_row_queries = [(sql, params) for sql, params in all_queries if "read_model.workbench_group_rows" in sql]
        self.assertTrue(group_row_queries)
        self.assertTrue(any("case when left(r.group_id, 5) = 'case:'" in sql for sql, _params in group_row_queries))
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
            zone="unpaired",
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
                "case when left(r_linked_search.group_id, 5) = 'case:'" in sql
                and "r_linked_search.searchable_text ilike %s" in sql
                and "%花%" in params
                for sql, params in group_row_queries
            )
        )
        self.assertTrue(
            any(
                "case when left(r.group_id, 5) = 'case:'" in sql
                and "r.pane = %s" in sql
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
            zone="unpaired",
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
                            "zone": "unpaired",
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
            zone="unpaired",
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
                            "zone": "unpaired",
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
            zone="unpaired",
            page=1,
            page_size=25,
            detail_level="summary",
            column_filters={"bank": {"amount": ["支出", "建行 8106"]}},
        )

        group = page["groups"][0]
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-expense-ccb"])

    def test_repository_reads_all_scope_groups_from_active_month_shards(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.get_workbench_groups_page(scope_key="all", zone="unpaired", page=1, page_size=1)

        group_queries = [
            (sql, params)
            for sql, params in [*connection.fetch_one_calls, *connection.fetch_all_calls]
            if "from read_model.workbench_groups" in sql
        ]
        self.assertTrue(group_queries)
        self.assertTrue(
            any(
                "join read_model.workbench_generations gen" in sql
                and "g.scope_key <> 'all'" in sql
                and "gen.status = 'active'" in sql
                for sql, _params in group_queries
            )
        )
        self.assertFalse(any("scope_key = %s" in sql and params[:1] == ("all",) for sql, params in group_queries))

    def test_repository_composed_all_scope_prefixes_non_mergeable_group_ids(self) -> None:
        class NonMergeableGroupConnection(WorkbenchSummaryGroupsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "select group_id, source_group_id, zone, payload, raw_payload" in normalized:
                    return [
                        {
                            "group_id": "scope:2026-05:temp:bank-open",
                            "source_group_id": "temp:bank-open",
                            "scope_key": "2026-05",
                            "generation_id": "gen-2026-05",
                            "zone": "unpaired",
                            "payload": {
                                "group_id": "temp:bank-open",
                                "bank_rows": [{"id": "bank-open-1", "type": "bank"}],
                                "oa_rows": [],
                                "invoice_rows": [],
                            },
                        }
                    ]
                return super().fetch_all(sql, params)

        connection = NonMergeableGroupConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(scope_key="all", zone="unpaired", page=1, page_size=1)

        self.assertEqual(page["groups"][0]["group_id"], "scope:2026-05:temp:bank-open")
        self.assertTrue(
            any(
                "'scope:' || g.scope_key || ':' || g.group_id" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )
        self.assertFalse(
            any(
                "like 'case:%'" in sql
                or "like 'turnover:%'" in sql
                or "like 'batch-accounting:%'" in sql
                or "like 'source:oa_attachment:%'" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )


    def test_repository_bounds_all_scope_groups_page_query(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(scope_key="all", zone="paired", page=2, page_size=500)

        page_queries = [
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "select group_id, source_group_id, zone, payload, raw_payload" in sql
            and "from read_model.workbench_groups" in sql
        ]
        self.assertTrue(page_queries)
        sql, params = page_queries[-1]
        self.assertIn("limit %s offset %s", sql)
        self.assertEqual(params[-2:], (201, 200))
        self.assertEqual(page["page_size"], 200)

    def test_repository_reads_workbench_groups_summary_page_without_heavy_details(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="unpaired",
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
        self.assertNotIn("searchable_text", group)
        self.assertNotIn("source_versions", group)
        self.assertNotIn("group_metadata", group)
        self.assertNotIn("detail_fields", group["oa_rows"][0])
        self.assertNotIn("source_versions", group["oa_rows"][0])
        self.assertNotIn("object_identity", group["oa_rows"][0])
        self.assertNotIn("object_identity_key", group["oa_rows"][0])
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
                "coalesce(r.source_kind, '') not in" in sql
                and "no_oa_bank_batch_summary" in sql
                and "bank_flow_rule_batch_summary" in sql
                for sql, _params in connection.fetch_one_calls
            )
        )

    def test_repository_groups_page_row_counts_apply_pane_row_filters(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        repository.get_workbench_groups_page(
            scope_key="all",
            zone="unpaired",
            page=1,
            page_size=25,
            search_by_pane={"bank": "建行"},
            column_filters={"bank": {"amount": ["支出"]}},
            time_filters={"bank": {"mode": "month", "month": "2026-04"}},
        )

        row_filter_queries = [
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "select group_id, source_group_id, zone, payload, raw_payload" in sql
            and "r.column_values @> %s::jsonb" in sql
        ]
        self.assertTrue(row_filter_queries)
        self.assertTrue(
            any(
                "r.column_values @> %s::jsonb" in sql
                and "r.time_date >= %s::date and r.time_date < %s::date" in sql
                and "r.searchable_text ilike %s" in sql
                and '"direction": "支出"' in str(params)
                and "2026-04-01" in str(params)
                and "%建行%" in params
                for sql, params in row_filter_queries
            )
        )

    def test_repository_summary_diagnostics_helper_reconciles_bank_detail_and_ignored_counts(self) -> None:
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

        summary = {
            "bank_count": 4,
            "zone_counts": {
                "paired": {"groups": 1, "oa": 1, "bank": 2, "invoice": 0, "rows": 3},
                "unpaired": {"groups": 2, "oa": 2, "bank": 2, "invoice": 5, "rows": 9},
            },
        }
        diagnostics = repository._workbench_bank_count_diagnostics(
            scope_key="all",
            summary=summary,
            generation_id="gen-active",
        )

        self.assertEqual(summary["bank_count"], 4)
        self.assertEqual(
            summary["bank_count"],
            summary["zone_counts"]["paired"]["bank"] + summary["zone_counts"]["unpaired"]["bank"],
        )
        self.assertEqual(diagnostics["bank_detail_count"], 5)
        self.assertEqual(diagnostics["ignored_bank_count"], 1)
        self.assertEqual(
            diagnostics["bank_detail_count"],
            summary["bank_count"] + diagnostics["ignored_bank_count"],
        )
        self.assertEqual(diagnostics["bank_detail_reconciliation_status"], "matched")
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
                        "zone": "unpaired",
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
                            "zone": "unpaired",
                            "payload": polluted_group_payload,
                        }
                    ]
                return super().fetch_all(sql, params)

        connection = PollutedOaAttachmentEvidenceConnection()
        repository = PostgresReadModelRepository(connection)

        page = repository.get_workbench_groups_page(
            scope_key="all",
            zone="unpaired",
            page=1,
            page_size=1,
            detail_level="summary",
        )
        detail = repository.get_workbench_group_detail(
            scope_key="all",
            zone="unpaired",
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
                        "bank_rows": [{"id": "bank-1", "type": "bank", "status": "unpaired"}],
                    }
                ]
            },
            "unpaired": {
                "groups": [
                    {
                        "group_id": "case:open",
                        "oa_rows": [{"id": "oa-1", "type": "oa", "status": "paired"}],
                    }
                ]
            },
        }

        rows = PostgresReadModelRepository._iter_workbench_rows(payload)

        self.assertEqual({row["id"]: row["status"] for row in rows}, {"bank-1": "paired", "oa-1": "unpaired"})

    def test_workbench_rows_materialize_collapsed_detail_rows_for_row_detail_reads(self) -> None:
        payload = {
            "paired": {
                "groups": [
                    {
                        "group_id": "case:collapsed",
                        "bank_rows": [{"id": "bank-summary", "type": "bank"}],
                        "collapsed_rows": {
                            "bank": [{"id": "bank-detail", "type": "bank", "amount": "12.34"}],
                            "invoice": [{"id": "etc-detail", "source_kind": "etc_invoice", "amount": "5.67"}],
                        },
                    }
                ]
            }
        }

        rows = PostgresReadModelRepository._iter_workbench_rows(payload)

        self.assertEqual(
            {row["id"]: row["status"] for row in rows},
            {"bank-summary": "paired", "bank-detail": "paired", "etc-detail": "paired"},
        )

    def test_workbench_persistence_materializes_detached_etc_summary_row(self) -> None:
        group = {
            "group_id": "case:etc-linked",
            "zone": "paired",
            "oa_rows": [{"id": "oa-1", "type": "oa"}],
            "bank_rows": [],
            "invoice_rows": [],
            "summary_row": {
                "id": "etc-summary-batch-1",
                "type": "invoice",
                "source_kind": "etc_invoice_summary",
                "status": "paired",
            },
            "collapsed_rows": {
                "invoice": [
                    {
                        "id": "etc-invoice-1",
                        "type": "invoice",
                        "source_kind": "etc_invoice",
                        "status": "paired",
                    }
                ]
            },
        }
        payload = {"paired": {"groups": [group]}}

        rows = PostgresReadModelRepository._iter_workbench_rows(payload)
        group_rows = _workbench_group_row_records(group)

        self.assertEqual(
            {row["id"] for row in rows},
            {"oa-1", "etc-summary-batch-1", "etc-invoice-1"},
        )
        self.assertIn(
            ("etc-summary-batch-1", "summary", "etc_invoice_summary"),
            {
                (row["row_id"], row["row_role"], row["source_kind"])
                for row in group_rows
            },
        )

        unpaired_payload = _workbench_row_payload_for_write(
            {
                "id": "oa-pay-1982",
                "type": "oa",
                "status": "unpaired",
                "workbench_reconciliation_decision": {"decision_status": "paired"},
            }
        )
        self.assertNotIn("workbench_reconciliation_decision", unpaired_payload)

    def test_repository_reads_single_workbench_group_detail(self) -> None:
        connection = WorkbenchSummaryGroupsConnection()
        repository = PostgresReadModelRepository(connection)

        group = repository.get_workbench_group_detail(scope_key="all", zone="unpaired", group_id="case:1")

        self.assertIsNotNone(group)
        self.assertEqual(group["group_id"], "case:1")
        self.assertEqual(group["oa_rows"][0]["id"], "oa-1")
        self.assertTrue(any("group_id = %s" in sql for sql, _params in connection.fetch_one_calls))


    def test_repository_group_detail_reads_only_active_generation(self) -> None:
        connection = ActiveWorkbenchGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        group = repository.get_workbench_group_detail(scope_key="all", zone="unpaired", group_id="case:1")

        self.assertIsNotNone(group)
        self.assertEqual(group["active_generation_id"], COMPOSED_ALL_VERSION)
        self.assertEqual(group["read_model_version"], COMPOSED_ALL_VERSION)
        self.assertTrue(
            any(
                "from read_model.workbench_groups" in sql
                and "join read_model.workbench_generations gen" in sql
                and "g.scope_key <> 'all'" in sql
                and "gen.status = 'active'" in sql
                for sql, _params in connection.fetch_one_calls
            )
        )

    def test_repository_group_detail_includes_active_generation_freshness_contract(self) -> None:
        connection = SwitchingActiveWorkbenchGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        group = repository.get_workbench_group_detail(scope_key="all", zone="unpaired", group_id="case:1")

        self.assertIsNotNone(group)
        self.assertEqual(group["active_generation_id"], COMPOSED_ALL_VERSION)
        self.assertEqual(group["read_model_version"], COMPOSED_ALL_VERSION)
        self.assertEqual(
            group["source_versions"],
            {"builder": WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION, "source_version": 12},
        )
        self.assertEqual(group["read_model_status"], "fresh")
        self.assertTrue(
            any(
                "join read_model.workbench_generations" in sql
                and "g.scope_key <> 'all'" in sql
                and "gen.status = 'active'" in sql
                for sql, _params in connection.fetch_one_calls
            )
        )

    def test_repository_all_scope_group_detail_uses_all_scope_freshness_contract(self) -> None:
        class AllScopeSourceGroupDetailConnection(ActiveWorkbenchGenerationConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                if "g.source_group_id = %s" in normalized and "gen.source_versions" in normalized:
                    self.fetch_one_calls.append((normalized, params))
                    return {
                        "group_id": "scope:2026-05:temp:1",
                        "source_group_id": "temp:1",
                        "zone": "unpaired",
                        "scope_key": "2026-05",
                        "generation_id": "gen-2026-05",
                        "source_versions": {"source_version": 12},
                        "payload": {
                            "group_id": "temp:1",
                            "group_type": "candidate",
                            "match_confidence": "medium",
                            "reason": "source group detail",
                            "oa_rows": [{"id": "oa-1", "type": "oa"}],
                            "bank_rows": [],
                            "invoice_rows": [],
                        },
                    }
                return super().fetch_one(sql, params)

        connection = AllScopeSourceGroupDetailConnection()
        repository = PostgresReadModelRepository(connection)

        group = repository.get_workbench_group_detail(scope_key="all", zone="unpaired", group_id="temp:1")

        self.assertIsNotNone(group)
        self.assertEqual(group["group_id"], "scope:2026-05:temp:1")
        self.assertEqual(group["scope_key"], "all")
        self.assertEqual(group["source_scope_key"], "2026-05")
        self.assertEqual(group["read_model_status"], "fresh")
        detail_queries = [
            (sql, params)
            for sql, params in connection.fetch_one_calls
            if "g.source_group_id = %s" in sql and "gen.source_versions" in sql
        ]
        self.assertTrue(detail_queries)
        self.assertEqual(detail_queries[-1][1][-2:], ("temp:1", "temp:1"))

    def test_repository_reports_workbench_refresh_status(self) -> None:
        connection = WorkbenchSummaryGroupsConnection(dirty_status="failed")
        repository = PostgresReadModelRepository(connection)

        status = repository.get_workbench_refresh_status(scope_key="2026-05")

        self.assertEqual(status["read_model_status"], "stale")
        self.assertEqual(status["dirty_scopes"][0]["scope_key"], "2026-05")
        self.assertEqual(status["last_error"], "worker timeout")
        self.assertEqual(status["worker_lag_seconds"], 12.0)
        self.assertEqual(status["outbox_backlog"]["failed"], 1)

    def test_repository_reports_failed_workbench_generation_without_promoting_it(self) -> None:
        connection = FailedWorkbenchGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        status = repository.get_workbench_refresh_status(scope_key="2026-05")

        self.assertEqual(status["read_model_status"], "stale")
        self.assertEqual(status["active_generation_id"], "gen-active")
        self.assertEqual(status["failed_generation_id"], "gen-failed")
        self.assertEqual(status["last_error"], "projection failed")
        self.assertEqual(status["read_model_version"], "gen-active")

    def test_repository_ignores_older_failed_workbench_generation_after_active_recovery(self) -> None:
        class RecoveredWorkbenchGenerationConnection(FailedWorkbenchGenerationConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                rows = super().fetch_all(sql, params)
                normalized = " ".join(sql.lower().split())
                if "from read_model.workbench_generations" in normalized:
                    rows[0]["activated_at"] = "2026-05-28T09:02:00+00:00"
                    rows[0]["source_versions"] = {"source_version": 14}
                    rows[1]["completed_at"] = "2026-05-28T09:01:00+00:00"
                    rows[1]["source_versions"] = {"source_version": 13}
                return rows

        repository = PostgresReadModelRepository(RecoveredWorkbenchGenerationConnection())

        status = repository.get_workbench_refresh_status(scope_key="2026-05")

        self.assertEqual(status["read_model_status"], "fresh")
        self.assertEqual(status["active_generation_id"], "gen-active")
        self.assertEqual(status["failed_generation_id"], "gen-failed")
        self.assertIsNone(status["last_error"])


    def test_repository_ignores_empty_materialized_all_generation_when_active_month_shards_exist(self) -> None:
        class EmptyAllWithParentGenerationConnection(WorkbenchSummaryGroupsConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "parent_generation_summary" in normalized:
                    return {
                        "all_generation_id": "gen-all-empty",
                        "all_row_count": 0,
                        "all_group_count": 0,
                        "all_source_version": 0,
                        "parent_scope_count": 2,
                        "parent_row_count": 41,
                        "parent_group_count": 9,
                        "parent_source_version": 19,
                        "parent_scope_keys": ["2026-03", "2026-02"],
                    }
                if "as group_count" in normalized and "as current_group_count" in normalized:
                    return {"group_count": 0, "current_group_count": 0}
                return super().fetch_one(sql, params)

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "actual_group_count" in normalized and "from read_model.workbench_generations" in normalized:
                    return []
                if "from read_model.workbench_generations" in normalized:
                    return [
                        {
                            "generation_id": "gen-all-empty",
                            "status": "active",
                            "activated_at": "2026-07-03T10:00:00+08:00",
                            "source_versions": {"source_version": 0},
                            "row_count": 0,
                            "group_count": 0,
                            "build_metadata": {},
                        }
                    ]
                return super().fetch_all(sql, params)

        connection = EmptyAllWithParentGenerationConnection()
        repository = PostgresReadModelRepository(connection)

        status = repository.get_workbench_refresh_status(scope_key="all")
        groups_status = repository.get_workbench_groups_freshness_status(scope_key="all")

        self.assertEqual(status["read_model_status"], "fresh")
        self.assertEqual(groups_status["read_model_status"], "fresh")
        self.assertNotIn("all_scope_parent_generation_out_of_sync", status["read_model_stale_reasons"])
        self.assertEqual(status["all_scope_parent_failures"], [])
        self.assertFalse(any("parent_generation_summary" in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_persists_workbench_groups_alongside_rows_and_snapshot(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {
                            "unpaired": {
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
                                                "status": "unpaired",
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
        self.assertNotIn("on conflict (generation_id, scope_key, row_id)", sql)
        self.assertNotIn("on conflict (generation_id, scope_key, zone, group_id)", sql)
        self.assertNotIn("on conflict (generation_id, scope_key, zone, group_id, pane, row_role, row_id)", sql)
        self.assertIn("status = 'active'", sql)

    def test_repository_prunes_old_workbench_generations_after_publish_for_changed_scope(self) -> None:
        class RetentionAfterPublishConnection(WorkbenchWriteConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_generations" in normalized and "status <> 'active'" in normalized:
                    return [
                        {
                            "generation_id": "old-2026-05-gen",
                            "scope_key": "2026-05",
                            "status": "superseded",
                            "activated_at": "2026-05-01T00:00:00+00:00",
                            "completed_at": "2026-05-01T00:00:00+00:00",
                            "updated_at": "2026-05-01T00:00:00+00:00",
                        }
                    ]
                return []

        connection = RetentionAfterPublishConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {"paired": {"groups": []}, "unpaired": {"groups": []}},
                        "source_versions": {"source_version": 6},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        retention_query = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "from read_model.workbench_generations" in sql and "status <> 'active'" in sql
        )
        self.assertIn("scope_key = any(%s)", retention_query[0])
        self.assertEqual(retention_query[1][0], ["2026-05"])
        generation_deletes = [
            (sql, params)
            for sql, params in connection.executed
            if "delete from read_model.workbench_generations" in sql
        ]
        self.assertEqual(len(generation_deletes), 1)
        self.assertIn("status <> 'active'", generation_deletes[0][0])
        self.assertEqual(generation_deletes[0][1], (["old-2026-05-gen"],))

    def test_repository_skips_sync_retention_for_all_scope_publish(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository._prune_workbench_generations_after_publish({"all"})

        self.assertFalse(connection.fetch_all_calls)
        self.assertFalse(connection.executed)

    def test_repository_retention_failure_does_not_rollback_published_workbench_generation(self) -> None:
        class FailingRetentionAfterPublishConnection(WorkbenchWriteConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_generations" in normalized and "status <> 'active'" in normalized:
                    raise TimeoutError("retention query timed out")
                return []

        connection = FailingRetentionAfterPublishConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {"paired": {"groups": []}, "unpaired": {"groups": []}},
                        "source_versions": {"source_version": 6},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertIn("insert into read_model.workbench_generations", sql)
        self.assertIn("set status = 'active'", sql)
        self.assertNotIn("delete from read_model.workbench_generations", sql)










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
                            "unpaired": {"groups": []},
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

    def test_repository_treats_bank_flow_rule_batch_summary_source_kind_as_display_only(self) -> None:
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
                                        "group_id": "case:BANK-FLOW-BATCH",
                                        "group_type": "auto_closed",
                                        "match_confidence": "high",
                                        "reason": "流水规则批次",
                                        "oa_rows": [],
                                        "bank_rows": [
                                            {
                                                "id": "bank_flow_rule_summary:batch-1",
                                                "type": "bank",
                                                "source_kind": "bank_flow_rule_batch_summary",
                                                "summary": "流水规则批次摘要",
                                            }
                                        ],
                                        "invoice_rows": [],
                                        "collapsed_rows": {
                                            "bank": [
                                                {"id": "bank-1", "type": "bank", "source_kind": "bank"},
                                                {"id": "bank-2", "type": "bank"},
                                            ]
                                        },
                                    }
                                ]
                            },
                            "unpaired": {"groups": []},
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
            if "insert into read_model.workbench_groups" in sql and params[1] == "case:BANK-FLOW-BATCH"
        )
        group_payload = group_insert[19].obj
        self.assertEqual(group_insert[8], 2)
        self.assertEqual(group_payload["row_counts"], {"oa": 0, "bank": 2, "invoice": 0, "rows": 2})
        self.assertEqual(group_payload["display_row_counts"], {"oa": 0, "bank": 1, "invoice": 0, "rows": 1})

        group_row_roles = [
            (params[5], params[6], params[7], params[9])
            for sql, params in connection.executed
            if "insert into read_model.workbench_group_rows" in sql and params[4] == "case:BANK-FLOW-BATCH"
        ]
        self.assertIn(
            ("bank", "bank_flow_rule_summary:batch-1", "summary", "bank_flow_rule_batch_summary"),
            group_row_roles,
        )
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
                            "unpaired": {"groups": []},
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



    def test_workbench_api_returns_sql_read_model_without_sync_build(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
	                "get_workbench_view": lambda _self, **_kwargs: {
	                    "payload": {"unpaired": {"groups": []}},
	                    "refresh_status": "fresh",
	                    "source_versions": fresh_workbench_sql_source_versions(app),
	                }
	            },
	        )()

        def explode_builder(_month: str):
            raise AssertionError("API request path must not synchronously build workbench payload")

        app._build_raw_workbench_payload = explode_builder

        response = app._handle_api_workbench("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["unpaired"], {"groups": []})
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(queue.refreshes, [])

    def test_workbench_api_sql_contract_preserves_backend_only_fields(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_view": lambda _self, **_kwargs: {
                    "payload": {
                        "month": "2026-05",
                        "unpaired": {"groups": []},
                        "diagnostics": {"read_model_source": "sql"},
                        "invoice_inventory": {"system_total": 9},
                        # TODO: PF-P006 verify safe to remove.
                        "active_generation_id": "gen-sql-1",
                        "read_model_version": 17,
                    },
                    "refresh_status": "fresh",
                    "generated_at": "2026-05-22T09:30:00+00:00",
                    "source_versions": fresh_workbench_sql_source_versions(app),
                    "rows_page": {
                        "page": 1,
                        "page_size": 50,
                        "rows": [{"id": "bank-row-1", "source_kind": "bank_transaction"}],
                        "has_more": False,
                    },
                }
            },
        )()
        app._build_api_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("SQL read model hit must not fallback to legacy builder")
        )

        response = app._handle_api_workbench("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(payload["read_model_generated_at"], "2026-05-22T09:30:00+00:00")
        self.assertEqual(payload["diagnostics"], {"read_model_source": "sql"})
        self.assertEqual(payload["invoice_inventory"], {"system_total": 9})
        self.assertEqual(payload["active_generation_id"], "gen-sql-1")
        self.assertEqual(payload["read_model_version"], 17)
        self.assertEqual(payload["rows_page"]["rows"][0]["id"], "bank-row-1")
        self.assertEqual(queue.refreshes, [])

    def test_workbench_api_legacy_endpoint_falls_back_when_sql_runtime_not_required(self) -> None:
        app = object.__new__(Application)
        app._bootstrap_mode = "legacy"
        app._workbench_sql_read_repository = None
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        builder_calls: list[str] = []

        def legacy_builder(month: str) -> dict[str, object]:
            builder_calls.append(month)
            return {
                "month": month,
                "summary": {"oa_count": 1},
                "unpaired": {"groups": []},
                # TODO: PF-P006 verify safe to remove.
                "diagnostics": {"legacy_builder": True},
            }

        app._build_api_workbench_payload = legacy_builder

        response = app._handle_api_workbench("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(builder_calls, ["2026-05"])
        self.assertEqual(payload["diagnostics"], {"legacy_builder": True})

    def test_workbench_api_production_runtime_without_sql_repository_returns_unavailable(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._bootstrap_mode = "production"
        app._state_store = SimpleNamespace(storage_backend="postgres")
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = None
        app._build_api_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("PostgreSQL production runtime must not fallback to legacy builder")
        )

        response = app._handle_api_workbench("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.SERVICE_UNAVAILABLE))
        self.assertEqual(payload["error"], "read_model_unavailable")
        self.assertEqual(payload["read_model_status"], "unavailable")
        self.assertEqual(payload["scope_key"], "2026-05")
        self.assertEqual(queue.refreshes, [("workbench", "2026-05", "api_sql_repository_unavailable")])

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
	                    "summary": {"oa_count": 1, "bank_count": 2, "invoice_count": 3, "paired_count": 4, "unpaired_count": 5, "exception_count": 0},
	                    "read_model_status": "fresh",
	                    "generated_at": "2026-05-22T09:30:00+00:00",
	                    "source_versions": fresh_workbench_sql_source_versions(app, "all"),
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

    def test_workbench_summary_api_missing_payload_enqueues_refreshing_contract(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue, "redis_helper": None})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {"get_workbench_summary": lambda _self, **_kwargs: None},
        )()

        response = app._handle_api_workbench_summary("all")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["month"], "all")
        self.assertEqual(payload["scope_key"], "all")
        self.assertEqual(payload["summary"]["oa_count"], 0)
        self.assertEqual(payload["summary"]["bank_count"], 0)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIsNone(payload["generated_at"])
        self.assertEqual(queue.refreshes, [("workbench", "all", "api_summary_miss")])

    def test_workbench_summary_api_stale_source_versions_preserves_backend_only_fields(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue, "redis_helper": None})()
        app._workbench_query_service = type(
            "WorkbenchQueryService",
            (),
            {"oa_status_payload": lambda _self: {"code": "ready", "message": "OA projection ready"}},
        )()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_summary": lambda _self, **_kwargs: {
                    "month": "all",
                    "scope_key": "all",
                    "summary": {"oa_count": 1, "bank_count": 2, "invoice_count": 3, "paired_count": 4, "unpaired_count": 5, "exception_count": 0},
                    "read_model_status": "fresh",
                    "generated_at": "2026-05-22T09:30:00+00:00",
                    "diagnostics": {"bank_detail_reconciliation_status": "stale"},
                    "invoice_inventory": {"system_total": 9},
                    # TODO: PF-P006 verify safe to remove.
                    "active_generation_id": "gen-summary-1",
                    "source_versions": {"builder": "old-builder"},
                }
            },
        )()

        response = app._handle_api_workbench_summary("all")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "stale")
        self.assertIn("builder_mismatch", payload["read_model_stale_reasons"])
        self.assertIn("bank_auto_tag_rules_version_missing", payload["read_model_stale_reasons"])
        self.assertEqual(payload["diagnostics"], {"bank_detail_reconciliation_status": "stale"})
        self.assertEqual(payload["invoice_inventory"], {"system_total": 9})
        self.assertEqual(payload["active_generation_id"], "gen-summary-1")
        self.assertEqual(payload["oa_status"], {"code": "ready", "message": "OA projection ready"})
        self.assertEqual(queue.refreshes, [("workbench", "all", "api_summary_source_versions_stale")])

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
                    "zone": "unpaired",
                    "page": 1,
                    "page_size": 50,
                    "total": 1,
	                    "has_more": False,
	                    "groups": [{"group_id": "case:1", "oa_rows": [], "bank_rows": [], "invoice_rows": []}],
	                    "read_model_status": "fresh",
	                    "source_versions": fresh_workbench_sql_source_versions(app, "all"),
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
            zone="unpaired",
            page="1",
            page_size="50",
            status="unpaired",
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
                    "zone": "unpaired",
                    "page": "1",
                    "page_size": "50",
                    "status": "unpaired",
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
                    "source_versions": fresh_workbench_sql_source_versions(app, "all"),
                    "read_model_status": "fresh",
                }

        repository = SqlWorkbench()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": None})()
        app._workbench_sql_read_repository = repository

        response = app._handle_api_workbench_group_detail("all", zone="unpaired", group_id="case:1")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["group"]["oa_rows"][0]["detail_fields"], {"OA单号": "2151"})
        self.assertEqual(
            repository.kwargs,
            {
                "scope_key": "all",
                "zone": "unpaired",
                "group_id": "case:1",
                "expected_read_model_version": None,
            },
        )

    def test_workbench_groups_api_redis_hit_does_not_query_database_cache_version(self) -> None:
        app = object.__new__(Application)
        cache_key = app._workbench_groups_redis_cache_key_from_version(
            cache_version="v7",
            scope_key="all",
            zone="unpaired",
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
                        "zone": "unpaired",
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

        response = app._handle_api_workbench_groups("all", zone="unpaired", page="1", page_size="50")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["groups"][0]["group_id"], "cached")
        self.assertEqual(redis.get_text_calls, ["workbench:groups:version:all"])

    def test_workbench_groups_api_stale_refresh_status_bypasses_redis_payload(self) -> None:
        app = object.__new__(Application)
        cache_key = app._workbench_groups_redis_cache_key_from_version(
            cache_version="v7",
            scope_key="all",
            zone="unpaired",
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
                        "zone": "unpaired",
                        "groups": [{"group_id": "stale-cached"}],
                    }
                }
            },
        )
        queue = QueueRecorder()
        page_calls: list[dict[str, object]] = []

        class SqlWorkbench:
            def get_workbench_refresh_status(self, **_kwargs):
                return {"read_model_status": "refreshing", "dirty_scopes": [{"scope_key": "all"}]}

            def get_workbench_groups_page(self, **kwargs):
                page_calls.append(kwargs)
                return {
                    "month": "all",
                    "zone": "unpaired",
                    "page": 1,
                    "page_size": 50,
                    "total": 1,
                    "has_more": False,
                    "groups": [{"group_id": "fresh-db", "oa_rows": [], "bank_rows": [], "invoice_rows": []}],
                    "read_model_status": "fresh",
                    "source_versions": fresh_workbench_sql_source_versions(app, "all"),
                }

            def workbench_groups_cache_version(self, **_kwargs):
                raise AssertionError("version key should be resolved from Redis text value")

        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue, "redis_helper": redis})()
        app._workbench_sql_read_repository = SqlWorkbench()

        response = app._handle_api_workbench_groups("all", zone="unpaired", page="1", page_size="50")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["groups"][0]["group_id"], "fresh-db")
        self.assertEqual(redis.get_text_calls, ["workbench:groups:version:all"])
        self.assertEqual(redis.get_json_calls, [])
        self.assertEqual(redis.set_json_calls, [])
        self.assertEqual(page_calls[0]["scope_key"], "all")
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [])

    def test_workbench_groups_api_redis_cache_is_separated_by_detail_level(self) -> None:
        app = object.__new__(Application)
        redis = RedisRecorder(text_values={"workbench:groups:version:all": "v7"})

        class SqlWorkbench:
            def get_workbench_groups_page(self, **_kwargs):
                return {
                    "month": "all",
                    "zone": "unpaired",
                    "page": 1,
                    "page_size": 50,
                    "total": 1,
                    "has_more": False,
	                    "groups": [{"group_id": "fresh", "oa_rows": [], "bank_rows": [], "invoice_rows": []}],
	                    "read_model_status": "fresh",
	                    "detail_level": "summary",
	                    "source_versions": fresh_workbench_sql_source_versions(app, "all"),
	                }

            def workbench_groups_cache_version(self, **_kwargs):
                raise AssertionError("Redis version key should avoid SQL cache version lookup")

        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": redis})()
        app._workbench_sql_read_repository = SqlWorkbench()

        app._handle_api_workbench_groups("all", zone="unpaired", page="1", page_size="50", detail_level="summary")
        app._handle_api_workbench_groups("all", zone="unpaired", page="1", page_size="50", detail_level="full")

        self.assertEqual(len(redis.set_json_calls), 2)
        self.assertNotEqual(redis.set_json_calls[0][0], redis.set_json_calls[1][0])

    def test_workbench_groups_api_redis_cache_key_includes_canonical_filters(self) -> None:
        app = object.__new__(Application)

        base_kwargs = {
            "cache_version": "v7",
            "scope_key": "all",
            "zone": "unpaired",
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
            "zone": "unpaired",
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

    def test_workbench_groups_api_redis_cache_key_hashes_colon_version(self) -> None:
        app = object.__new__(Application)

        key = app._workbench_groups_redis_cache_key_from_version(
            cache_version=COMPOSED_ALL_VERSION,
            scope_key="all",
            zone="unpaired",
            page="1",
            page_size="50",
            status=None,
            source_kind=None,
            search=None,
            sort=None,
            detail_level="summary",
        )

        self.assertIsNotNone(key)
        parsed_version = app._workbench_groups_redis_cache_version_from_key(key or "")
        self.assertIsNotNone(parsed_version)
        self.assertNotEqual(parsed_version, "workbench")
        self.assertNotIn(":", parsed_version or "")
        self.assertEqual(len(parsed_version or ""), 24)

    def test_workbench_groups_api_redis_cache_key_includes_groups_page_schema_version(self) -> None:
        app = object.__new__(Application)
        kwargs = {
            "cache_version": "v7",
            "scope_key": "all",
            "zone": "unpaired",
            "page": "1",
            "page_size": "50",
            "status": None,
            "source_kind": None,
            "search": None,
            "sort": None,
            "detail_level": "summary",
        }

        with patch("fin_ops_platform.app.server.WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION", "schema-a"):
            key_a = app._workbench_groups_redis_cache_key_from_version(**kwargs)
        with patch("fin_ops_platform.app.server.WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION", "schema-b"):
            key_b = app._workbench_groups_redis_cache_key_from_version(**kwargs)

        self.assertNotEqual(key_a, key_b)

    def test_workbench_groups_page_cache_version_tracks_projection_schema(self) -> None:
        self.assertEqual(
            WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION,
            WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
        )

    def test_workbench_groups_api_reports_missing_groups_table_as_unavailable(self) -> None:
        app = object.__new__(Application)

        class SqlWorkbench:
            def get_workbench_groups_page(self, **_kwargs):
                raise RuntimeError('relation "read_model.workbench_groups" does not exist')

            def workbench_groups_cache_version(self, **_kwargs):
                return "v0"

        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": None})()
        app._workbench_sql_read_repository = SqlWorkbench()

        response = app._handle_api_workbench_groups("all", zone="unpaired")
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

    def test_workbench_refresh_status_api_treats_requeued_failed_scope_as_refreshing(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder(), "redis_helper": None})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {
                "get_workbench_refresh_status": lambda _self, **_kwargs: {
                    "read_model_status": "refreshing",
                    "dirty_scopes": [
                        {
                            "scope_key": "2026-03",
                            "status": "failed",
                            "last_error": "workbench_all_scope_parent_inconsistent: active_relation_open_membership count=4",
                            "source_version": 12,
                        },
                        {
                            "scope_key": "2026-03",
                            "status": "processing",
                            "source_version": 13,
                        },
                    ],
                    "worker_lag_seconds": 1.0,
                }
            },
        )()

        response = app._handle_api_workbench_refresh_status("all")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIsNone(payload["last_error"])
        self.assertFalse(payload["retryable"])

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
	                    "source_versions": fresh_workbench_sql_source_versions(app, "all"),
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

    def test_workbench_events_stream_exposes_no_buffering_headers_and_heartbeat(self) -> None:
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
                    "source_versions": fresh_workbench_sql_source_versions(app, "all"),
                }
            },
        )()

        response = app._handle_api_workbench_events("all")
        stream = iter(response.body)
        first_event = next(stream)
        heartbeat = next(stream)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertTrue(response.stream)
        self.assertEqual(response.headers["Content-Type"], "text/event-stream; charset=utf-8")
        self.assertEqual(response.headers["Cache-Control"], "no-cache, no-transform")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        self.assertIn("event: workbench.read_model.completed", first_event)
        self.assertIn("event: heartbeat", heartbeat)
        self.assertIn('"scope_key": "all"', heartbeat)
        self.assertIn('"read_model_status": "fresh"', heartbeat)

    def test_workbench_events_stream_maps_statuses_without_redis_pubsub(self) -> None:
        app = object.__new__(Application)
        app._app_health_service = AppHealthService()

        class ExplodingRedisHelper:
            def __getattr__(self, name: str):
                raise AssertionError(f"SSE polling path must not use Redis PubSub helper: {name}")

        app._runtime_repositories = SimpleNamespace(redis_helper=ExplodingRedisHelper())

        expected_events = {
            "fresh": "workbench.read_model.completed",
            "refreshing": "workbench.read_model.progress",
            "stale": "workbench.read_model.progress",
            "failed": "workbench.read_model.failed",
        }
        calls: list[tuple[str, dict[str, object]]] = []

        class SqlWorkbench:
            def __init__(self, status: str) -> None:
                self.status = status

            def get_workbench_refresh_status(self, **kwargs):
                calls.append((self.status, kwargs))
                return {
                    "scope_key": "all",
                    "read_model_status": self.status,
                    "generated_at": "2026-05-28T10:00:00+08:00",
                    "dirty_scopes": [],
                    "source_versions": fresh_workbench_sql_source_versions(app, "all"),
                }

        for status, event_name in expected_events.items():
            app._workbench_sql_read_repository = SqlWorkbench(status)

            response = app._handle_api_workbench_events("all")
            first_event = next(iter(response.body))

            self.assertEqual(response.status_code, int(HTTPStatus.OK))
            self.assertEqual(response.headers["X-Accel-Buffering"], "no")
            self.assertIn(f"event: {event_name}", first_event)
            self.assertIn(f'"read_model_status": "{status}"', first_event)

        self.assertEqual(
            calls,
            [
                ("fresh", {"scope_key": "all"}),
                ("refreshing", {"scope_key": "all"}),
                ("stale", {"scope_key": "all"}),
                ("failed", {"scope_key": "all"}),
            ],
        )

    def test_workbench_events_stream_close_releases_active_stream_slot(self) -> None:
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
                    "source_versions": fresh_workbench_sql_source_versions(app, "all"),
                }
            },
        )()

        response = app._handle_api_workbench_events("all")
        stream = iter(response.body)

        first_event = next(stream)
        self.assertIn("event: workbench.read_model.completed", first_event)
        self.assertEqual(app._workbench_events_stream_registry().snapshot(), {"all": 1})

        stream.close()

        self.assertEqual(app._workbench_events_stream_registry().snapshot(), {})

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
                    "payload": {"unpaired": {"groups": []}},
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
            status="unpaired",
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
                    "status": "unpaired",
                    "source_kind": "bank_transaction",
                    "search": "供应商",
                }
            ],
        )

    def test_row_detail_prefers_live_service_and_applies_override_without_fallback(self) -> None:
        app = object.__new__(Application)
        app._etc_invoice_summary_row_detail = lambda _row_id: None
        app._live_workbench_service = type(
            "LiveWorkbench",
            (),
            {"get_row_detail": lambda _self, row_id: {"id": row_id, "source": "live"}},
        )()
        app._resolve_rows_from_cached_read_models = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("live row detail hit must not read cached read models")
        )
        app._workbench_api_routes = type(
            "Routes",
            (),
            {
                "get_row_detail": lambda _self, _row_id: (_ for _ in ()).throw(
                    AssertionError("live row detail hit must not fallback to route service")
                )
            },
        )()
        override_calls: list[str] = []

        def apply_live_override(row: dict[str, object]) -> dict[str, object]:
            override_calls.append(str(row["id"]))
            return {**row, "override_applied": True}

        app._workbench_override_service = type(
            "Overrides",
            (),
            {"apply_to_row": lambda _self, row: apply_live_override(row)},
        )()

        payload = app._get_api_workbench_row_detail_payload("bank-row-live")

        self.assertEqual(payload["row"], {"id": "bank-row-live", "source": "live", "override_applied": True})
        self.assertEqual(override_calls, ["bank-row-live"])

    def test_row_detail_route_fallback_applies_override_after_live_and_cache_miss(self) -> None:
        app = object.__new__(Application)
        live_calls: list[str] = []
        cache_calls: list[tuple[list[str], str | None]] = []
        route_calls: list[str] = []
        override_calls: list[str] = []
        app._etc_invoice_summary_row_detail = lambda _row_id: None

        def live_miss(row_id: str) -> dict[str, object]:
            live_calls.append(row_id)
            raise KeyError(row_id)

        app._live_workbench_service = type(
            "LiveWorkbench",
            (),
            {"get_row_detail": lambda _self, row_id: live_miss(row_id)},
        )()
        app._row_month_scope_from_row_id = lambda _row_id: None

        def cached_miss(row_ids: list[str], *, month_hint: str | None = None) -> dict[str, dict[str, object]]:
            cache_calls.append((list(row_ids), month_hint))
            return {}

        app._resolve_rows_from_cached_read_models = cached_miss
        app._workbench_query_service = SimpleNamespace(_looks_like_oa_row_id=lambda _row_id: False)

        def route_detail(row_id: str) -> dict[str, object]:
            route_calls.append(row_id)
            return {"row": {"id": row_id, "source": "route"}}

        app._workbench_api_routes = SimpleNamespace(get_row_detail=route_detail)

        def apply_override(row: dict[str, object]) -> dict[str, object]:
            override_calls.append(str(row["id"]))
            return {**row, "override_applied": True}

        app._workbench_override_service = SimpleNamespace(apply_to_row=apply_override)

        payload = app._get_api_workbench_row_detail_payload("bank-row-route")

        self.assertEqual(live_calls, ["bank-row-route"])
        self.assertEqual(cache_calls, [(["bank-row-route"], None)])
        self.assertEqual(route_calls, ["bank-row-route"])
        self.assertEqual(override_calls, ["bank-row-route"])
        self.assertEqual(payload["row"], {"id": "bank-row-route", "source": "route", "override_applied": True})

    def test_row_detail_production_sql_runtime_blocks_route_fallback_after_live_and_cache_miss(self) -> None:
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = SimpleNamespace(storage_backend="postgres")
        app._etc_invoice_summary_row_detail = lambda _row_id: None
        app._live_workbench_service = SimpleNamespace(
            get_row_detail=lambda row_id: (_ for _ in ()).throw(KeyError(row_id))
        )
        app._row_month_scope_from_row_id = lambda _row_id: None
        app._resolve_rows_from_cached_read_models = lambda _row_ids, **_kwargs: {}
        app._workbench_query_service = SimpleNamespace(
            _looks_like_oa_row_id=lambda _row_id: False,
            _records_by_id={},
        )
        route_calls: list[str] = []

        def route_detail(row_id: str) -> dict[str, object]:
            route_calls.append(row_id)
            return {"row": {"id": row_id, "source": "route"}}

        app._workbench_api_routes = SimpleNamespace(get_row_detail=route_detail)
        app._workbench_override_service = SimpleNamespace(
            apply_to_row=lambda row: (_ for _ in ()).throw(
                AssertionError("production SQL runtime route fallback must not produce a row")
            )
        )

        response = app._handle_api_workbench_row_detail("bank-row-route")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.NOT_FOUND))
        self.assertEqual(payload, {"error": "workbench_row_not_found", "row_id": "bank-row-route"})
        self.assertEqual(route_calls, [])

    def test_row_detail_production_sql_runtime_blocks_route_fallback_even_with_in_memory_record(self) -> None:
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = SimpleNamespace(storage_backend="postgres")
        app._etc_invoice_summary_row_detail = lambda _row_id: None
        app._live_workbench_service = SimpleNamespace(
            get_row_detail=lambda row_id: (_ for _ in ()).throw(KeyError(row_id))
        )
        app._row_month_scope_from_row_id = lambda _row_id: None
        app._resolve_rows_from_cached_read_models = lambda _row_ids, **_kwargs: {}
        app._workbench_query_service = SimpleNamespace(
            _looks_like_oa_row_id=lambda _row_id: False,
            _records_by_id={"bank-row-route": {"id": "bank-row-route", "source": "legacy-memory"}},
        )
        route_calls: list[str] = []

        def route_detail(row_id: str) -> dict[str, object]:
            route_calls.append(row_id)
            return {"row": {"id": row_id, "source": "route"}}

        app._workbench_api_routes = SimpleNamespace(
            _query_service=app._workbench_query_service,
            get_row_detail=route_detail,
        )
        app._workbench_override_service = SimpleNamespace(
            apply_to_row=lambda row: (_ for _ in ()).throw(
                AssertionError("production SQL runtime must not apply legacy route fallback rows")
            )
        )

        response = app._handle_api_workbench_row_detail("bank-row-route")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.NOT_FOUND))
        self.assertEqual(payload, {"error": "workbench_row_not_found", "row_id": "bank-row-route"})
        self.assertEqual(route_calls, [])

    def test_row_detail_production_sql_runtime_ignores_stale_cached_read_model_row(self) -> None:
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = SimpleNamespace(storage_backend="postgres")
        app._etc_invoice_summary_row_detail = lambda _row_id: None
        app._live_workbench_service = SimpleNamespace(
            get_row_detail=lambda row_id: (_ for _ in ()).throw(KeyError(row_id))
        )
        app._row_month_scope_from_row_id = lambda _row_id: "2026-05"
        app._workbench_read_model_service = SimpleNamespace(
            get_read_model=lambda _scope_key: {
                "scope_key": "2026-05",
                "source_versions": {"builder": "old-builder"},
                "payload": {
                    "unpaired": {
                        "groups": [
                            {
                                "bank_rows": [
                                    {"id": "bank-row-stale", "source_kind": "bank_transaction", "amount": "100.00"}
                                ]
                            }
                        ]
                    }
                },
            },
            list_scope_keys=lambda: ["2026-05"],
        )
        app._workbench_sql_read_model_stale_reasons = lambda _source_versions, **_kwargs: ["builder_mismatch"]
        app._workbench_query_service = SimpleNamespace(
            _looks_like_oa_row_id=lambda _row_id: False,
            _records_by_id={},
        )
        app._workbench_api_routes = SimpleNamespace(
            get_row_detail=lambda row_id: (_ for _ in ()).throw(
                AssertionError(f"stale cached row must not fallback to route detail: {row_id}")
            )
        )
        app._workbench_override_service = SimpleNamespace(apply_to_row=lambda row: row)

        response = app._handle_api_workbench_row_detail("bank-row-stale")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.NOT_FOUND))
        self.assertEqual(payload, {"error": "workbench_row_not_found", "row_id": "bank-row-stale"})

    def test_row_detail_sql_runtime_uses_query_facade_for_opaque_oa_after_live_and_cache_miss(self) -> None:
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = SimpleNamespace(storage_backend="postgres")
        app._etc_invoice_summary_row_detail = lambda _row_id: None
        app._live_workbench_service = SimpleNamespace(
            get_row_detail=lambda row_id: (_ for _ in ()).throw(KeyError(row_id))
        )
        app._row_month_scope_from_row_id = lambda _row_id: None
        app._resolve_rows_from_cached_read_models = lambda _row_ids, **_kwargs: {}
        app._workbench_query_service = SimpleNamespace(
            _looks_like_oa_row_id=lambda row_id: str(row_id).startswith("oa-"),
            _records_by_id={},
        )
        app._workbench_api_routes = SimpleNamespace(
            get_row_detail=lambda row_id: (_ for _ in ()).throw(
                AssertionError(f"opaque OA detail must not fallback to legacy route: {row_id}")
            )
        )
        app._workbench_override_service = SimpleNamespace(apply_to_row=lambda row: row)
        facade_calls: list[tuple[str | None, str]] = []

        class Facade:
            def row_detail(self, month: str | None, *, row_id: str):
                facade_calls.append((month, row_id))
                return SimpleNamespace(
                    status_code=HTTPStatus.OK,
                    payload={
                        "row": {
                            "id": row_id,
                            "type": "oa",
                            "applicant": "刘际涛",
                            "detail_fields": {"OA单号": row_id},
                        },
                        "read_model_status": "fresh",
                    },
                )

        app._workbench_query_facade = lambda: Facade()

        response = app._handle_api_workbench_row_detail("oa-pay-1976")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["row"]["id"], "oa-pay-1976")
        self.assertEqual(facade_calls, [(None, "oa-pay-1976")])

    def test_amount_check_row_resolution_sql_runtime_skips_live_bank_fallback(self) -> None:
        app = object.__new__(Application)
        app._requires_sql_read_model_runtime = lambda: True
        app._resolve_rows_from_cached_read_models = lambda _row_ids, **_kwargs: {}
        app._row_types_for_row_ids = lambda row_ids: ["bank" for _row_id in row_ids]
        app._resolve_live_rows_direct = lambda row_ids, **_kwargs: (_ for _ in ()).throw(
            AssertionError(f"sql runtime must not use live bank fallback: {row_ids}")
        )
        detail_calls: list[dict[str, object]] = []

        def row_detail(row_id: str, *, month: str | None = None) -> dict[str, object]:
            detail_calls.append({"row_id": row_id, "month": month})
            return {"row": {"id": row_id, "type": "bank"}}

        app._get_api_workbench_row_detail_payload = row_detail
        app._serialize_value = lambda value: value

        rows = app._resolve_rows_for_amount_check(["txn_imported_0396"], month="all", allow_direct=True)

        self.assertEqual(rows, [{"id": "txn_imported_0396", "type": "bank"}])
        self.assertEqual(detail_calls, [{"row_id": "txn_imported_0396", "month": "all"}])

    def test_repository_persists_workbench_rows_alongside_snapshot(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {
                            "unpaired": {
                                "groups": [
                                    {
                                        "bank_rows": [
                                            {
                                                "id": "bank-row-1",
                                                "source_kind": "bank_transaction",
                                                "status": "unpaired",
                                                "counterparty_name": "供应商A",
                                                "amount": "1,000.00",
                                                "amount_value": "1000.00",
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
        self.assertNotIn("on conflict (generation_id, scope_key, row_id)", sql)
        row_write = next(params for statement, params in connection.executed if "insert into read_model.workbench_rows" in statement)
        self.assertEqual(row_write[9], "1000.00")
        group_row_write = next(
            params for statement, params in connection.executed if "insert into read_model.workbench_group_rows" in statement
        )
        self.assertIn("1000.00", group_row_write[14])

    def test_repository_batches_workbench_generation_rows_when_supported(self) -> None:
        connection = BulkWorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {
                            "unpaired": {
                                "groups": [
                                    {
                                        "group_id": "case:BULK-1",
                                        "group_type": "candidate",
                                        "bank_rows": [
                                            {
                                                "id": "bank-row-1",
                                                "source_kind": "bank_transaction",
                                                "status": "unpaired",
                                                "counterparty_name": "供应商A",
                                                "amount_value": "1000.00",
                                            },
                                            {
                                                "id": "bank-row-2",
                                                "source_kind": "bank_transaction",
                                                "status": "unpaired",
                                                "counterparty_name": "供应商B",
                                                "amount_value": "2000.00",
                                            },
                                        ],
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

        workbench_row_batches = [
            params for statement, params in connection.execute_many_calls
            if "insert into read_model.workbench_rows" in statement
        ]
        workbench_group_batches = [
            params for statement, params in connection.execute_many_calls
            if "insert into read_model.workbench_groups" in statement
        ]
        workbench_group_row_batches = [
            params for statement, params in connection.execute_many_calls
            if "insert into read_model.workbench_group_rows" in statement
        ]

        self.assertEqual([2], [len(batch) for batch in workbench_row_batches])
        self.assertEqual([1], [len(batch) for batch in workbench_group_batches])
        self.assertEqual([2], [len(batch) for batch in workbench_group_row_batches])
        self.assertFalse(any("insert into read_model.workbench_rows" in statement for statement, _params in connection.executed))
        self.assertFalse(any("insert into read_model.workbench_groups" in statement for statement, _params in connection.executed))
        self.assertFalse(any("insert into read_model.workbench_group_rows" in statement for statement, _params in connection.executed))

    def test_repository_writes_workbench_payload_without_duplicate_raw_payload(self) -> None:
        connection = BulkWorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {
                            "unpaired": {
                                "groups": [
                                    {
                                        "group_id": "case:RAW-1",
                                        "group_type": "candidate",
                                        "bank_rows": [
                                            {
                                                "id": "bank-row-1",
                                                "source_kind": "bank_transaction",
                                                "status": "unpaired",
                                                "counterparty_name": "供应商A",
                                                "amount_value": "1000.00",
                                                "object_identity": {
                                                    "key": "bank-business-fields-1",
                                                    "kind": "business_fields",
                                                    "source": "bank_transaction",
                                                },
                                                "object_identity_key": "bank-business-fields-1",
                                                "object_identity_kind": "business_fields",
                                                "object_identity_source": "bank_transaction",
                                                "object_identity_confidence": "stable",
                                            }
                                        ],
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

        snapshot_params = next(params for statement, params in connection.executed if "insert into read_model.workbench_snapshots" in statement)
        summary_params = next(params for statement, params in connection.executed if "insert into read_model.workbench_summary" in statement)
        row_batch = next(params for statement, params in connection.execute_many_calls if "insert into read_model.workbench_rows" in statement)
        group_batch = next(params for statement, params in connection.execute_many_calls if "insert into read_model.workbench_groups" in statement)
        group_row_batch = next(
            params for statement, params in connection.execute_many_calls if "insert into read_model.workbench_group_rows" in statement
        )

        self.assertEqual(snapshot_params[8].obj, {})
        self.assertEqual(summary_params[9].obj, {})
        self.assertEqual(row_batch[0][18].obj, {})
        self.assertEqual(group_batch[0][20].obj, {})
        self.assertEqual(group_row_batch[0][23].obj, {})
        self.assertEqual(snapshot_params[7].obj["payload"]["unpaired"]["groups"], [])
        self.assertTrue(snapshot_params[7].obj["payload"]["workbench_groups_materialized"])
        self.assertEqual(row_batch[0][17].obj["id"], "bank-row-1")
        self.assertNotIn("object_identity", row_batch[0][17].obj)
        self.assertEqual(row_batch[0][17].obj["object_identity_key"], "bank-business-fields-1")
        self.assertEqual(group_batch[0][19].obj["group_id"], "case:RAW-1")
        self.assertEqual(group_row_batch[0][19].obj, {})
        self.assertEqual(group_row_batch[0][22].obj, {})

    def test_repository_reads_workbench_row_detail_from_active_generation_rows(self) -> None:
        class RowDetailConnection(WorkbenchWriteConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_rows r" in normalized and "join read_model.workbench_generations gen" in normalized:
                    return {
                        "row_id": "oa-pay-1976",
                        "source_kind": "oa",
                        "status": "paired",
                        "scope_key": "2026-01",
                        "generation_id": "gen-2026-01-active",
                        "source_versions": {"builder": "workbench-sql:v1"},
                        "payload": {
                            "id": "oa-pay-1976",
                            "type": "oa",
                            "applicant": "刘际涛",
                            "detail_fields": {"OA单号": "oa-pay-1976"},
                        },
                    }
                return None

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
                if "from job.read_model_dirty_scopes" in self.fetch_all_calls[-1][0]:
                    return []
                return []

        connection = RowDetailConnection()
        repository = PostgresReadModelRepository(connection)

        payload = repository.get_workbench_row_detail(scope_key="2026-01", row_id="oa-pay-1976")

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["row"]["id"], "oa-pay-1976")
        self.assertEqual(payload["scope_key"], "2026-01")
        self.assertEqual(payload["source_versions"], {"builder": "workbench-sql:v1"})
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertTrue(any("from read_model.workbench_rows r" in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_reads_all_scope_row_detail_from_active_month_rows(self) -> None:
        class RowDetailConnection(WorkbenchWriteConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_rows r" in normalized and params == ("txn_imported_0396", "all"):
                    return {
                        "row_id": "txn_imported_0396",
                        "source_kind": "bank",
                        "status": "unpaired",
                        "scope_key": "2026-06",
                        "generation_id": "gen-2026-06-active",
                        "source_versions": {"builder": "workbench-sql:v1"},
                        "payload": {
                            "id": "txn_imported_0396",
                            "type": "bank",
                            "counterparty_name": "中招国际招标有限公司云南分公司",
                        },
                    }
                return None

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
                if "from job.read_model_dirty_scopes" in self.fetch_all_calls[-1][0]:
                    return []
                return []

        connection = RowDetailConnection()
        repository = PostgresReadModelRepository(connection)

        payload = repository.get_workbench_row_detail(scope_key="all", row_id="txn_imported_0396")

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["row"]["id"], "txn_imported_0396")
        self.assertEqual(payload["scope_key"], "2026-06")
        self.assertEqual(payload["read_model_status"], "fresh")
        sql = connection.fetch_one_calls[0][0]
        self.assertIn("and true", sql)
        self.assertNotIn("r.scope_key in (%s, 'all')", sql)

    def test_repository_reads_legacy_group_member_payload_when_row_detail_row_is_missing(self) -> None:
        class LegacyGroupMemberConnection(WorkbenchWriteConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_rows r" in normalized:
                    return None
                if "from read_model.workbench_group_rows gr" in normalized:
                    return {
                        "row_id": "oa-pay-legacy",
                        "pane": "oa",
                        "source_kind": "oa",
                        "status": "unpaired",
                        "scope_key": "2026-05",
                        "generation_id": "gen-2026-05-active",
                        "source_versions": {"builder": "workbench-sql:v1"},
                        "member_payload": {
                            "id": "oa-pay-legacy",
                            "type": "oa",
                            "amount": "1500.00",
                            "applicant": "刘际涛",
                        },
                    }
                if "from job.read_model_dirty_scopes" in normalized:
                    return None
                return None

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
                if "from job.read_model_dirty_scopes" in self.fetch_all_calls[-1][0]:
                    return []
                return []

        connection = LegacyGroupMemberConnection()
        repository = PostgresReadModelRepository(connection)

        payload = repository.get_workbench_row_detail(scope_key="all", row_id="oa-pay-legacy")

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["row"]["id"], "oa-pay-legacy")
        self.assertEqual(payload["row"]["amount"], "1500.00")
        self.assertEqual(payload["scope_key"], "2026-05")
        self.assertEqual(payload["active_generation_id"], "gen-2026-05-active")
        self.assertTrue(any("from read_model.workbench_group_rows gr" in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_does_not_synthesize_row_detail_from_empty_group_member_payload(self) -> None:
        class EmptyGroupMemberConnection(WorkbenchWriteConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_rows r" in normalized:
                    return None
                if "from read_model.workbench_group_rows gr" in normalized:
                    return {
                        "row_id": "oa-pay-empty",
                        "pane": "oa",
                        "source_kind": "oa",
                        "status": "unpaired",
                        "scope_key": "2026-05",
                        "generation_id": "gen-2026-05-active",
                        "member_payload": {},
                    }
                return None

        connection = EmptyGroupMemberConnection()
        repository = PostgresReadModelRepository(connection)

        payload = repository.get_workbench_row_detail(scope_key="all", row_id="oa-pay-empty")

        self.assertIsNone(payload)

    def test_repository_finds_workbench_row_active_month_scope_key(self) -> None:
        class RowScopeConnection(WorkbenchWriteConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "select r.scope_key from read_model.workbench_rows r" in normalized:
                    return {"scope_key": "2026-06"}
                return None

        connection = RowScopeConnection()
        repository = PostgresReadModelRepository(connection)

        scope_key = repository.find_workbench_row_scope_key(row_id="txn_imported_0396")

        self.assertEqual(scope_key, "2026-06")
        self.assertEqual(connection.fetch_one_calls[0][1], ("txn_imported_0396",))
        self.assertIn("gen.status = 'active'", connection.fetch_one_calls[0][0])
        self.assertIn("r.scope_key <> 'all'", connection.fetch_one_calls[0][0])

    def test_repository_does_not_delete_generation_rows_when_scope_snapshot_is_absent(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        with self.assertRaisesRegex(ValueError, "changed_scope_keys must reference payloads written in this call"):
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
                        "payload": {"unpaired": {"groups": []}},
                        "source_versions": {"source_version": 4},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertNotIn("insert into read_model.workbench_snapshots", sql)
        self.assertNotIn("delete from read_model.workbench_rows", sql)

    def test_repository_publishes_workbench_snapshot_when_builder_changes_despite_lower_source_version(self) -> None:
        class BuilderChangedConnection(StaleWorkbenchWriteConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
                if "from read_model.workbench_snapshots" in self.fetch_one_calls[-1][0]:
                    return {"source_versions": {"source_version": 5, "builder": "old-builder"}}
                return None

        connection = BuilderChangedConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "scope_month": "2026-05",
                        "payload": {
                            "month": "2026-05",
                            "scope_key": "2026-05",
                            "paired": {"groups": []},
                            "unpaired": {"groups": []},
                            "summary": {},
                        },
                        "source_versions": {"source_version": 4, "builder": "new-builder"},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertIn("insert into read_model.workbench_snapshots", sql)
        self.assertIn("update read_model.workbench_generations", sql)


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

    def test_repository_reports_inconsistent_workbench_generation_as_refreshing_during_active_repair(self) -> None:
        class RepairingInconsistentGenerationConnection(WorkbenchSummaryGroupsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from job.read_model_dirty_scopes" in normalized:
                    return [
                        {
                            "scope_key": "2026-03",
                            "status": "processing",
                            "updated_at": "2026-06-21T22:48:00+08:00",
                            "last_error": "previous generation mismatch",
                            "source_version": 9,
                        }
                    ]
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

        repository = PostgresReadModelRepository(RepairingInconsistentGenerationConnection())

        status = repository.get_workbench_refresh_status(scope_key="2026-03")

        self.assertEqual(status["read_model_status"], "refreshing")
        self.assertEqual(status["consistency_status"], "failed")
        self.assertIn("generation_metadata_actual_mismatch", status["read_model_stale_reasons"])
        self.assertIsNone(status["last_error"])

    def test_repository_treats_covered_dirty_workbench_scope_as_fresh(self) -> None:
        class CoveredDirtyScopeConnection(ActiveWorkbenchGenerationConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from job.read_model_dirty_scopes" in normalized:
                    return [
                        {
                            "scope_key": "2026-03",
                            "status": "processing",
                            "updated_at": "2026-06-21T22:48:00+08:00",
                            "last_error": None,
                            "source_version": 7,
                        }
                    ]
                return super().fetch_all(sql, params)

        repository = PostgresReadModelRepository(CoveredDirtyScopeConnection())

        status = repository.get_workbench_refresh_status(scope_key="2026-03")

        self.assertEqual(status["read_model_status"], "fresh")
        self.assertEqual(status["dirty_scopes"][0]["status"], "processing")
        self.assertEqual(status["generations"][0]["source_versions"]["source_version"], 12)

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
                        "payload": {"paired": {"groups": []}, "unpaired": {"groups": []}},
                        "source_versions": {"source_version": 3},
                    }
                }
            },
            changed_scope_keys={"2026-01"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertNotIn("workbench_all_scope_parent_inconsistent", sql)
        self.assertFalse(
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

    def test_workbench_refresh_handler_requires_projection_builder_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "projection_builder is required"):
            WorkbenchReadModelRefreshService(queue_repository=object())

    def test_workbench_refresh_handler_skips_stale_source_version(self) -> None:
        class FakeBuilder:
            def rebuild_workbench_read_model_scope(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                raise AssertionError(f"stale event should not rebuild {scope_key}:{source_version}")

        class FakeQueue:
            def __init__(self) -> None:
                self.current_checks: list[tuple[str, str, str, object]] = []

            def read_model_refresh_is_current(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object,
            ) -> bool:
                self.current_checks.append((tenant_id, scope_type, scope_key, source_version))
                return False

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-stale",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 2},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(queue.current_checks, [("tenant-a", "workbench", "2026-05", 2)])
        self.assertEqual(
            result,
            {
                "scope_key": "2026-05",
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": 2,
            },
        )

    def test_workbench_refresh_handler_runs_all_aggregate_after_shard_publish_even_if_all_scope_source_is_newer(self) -> None:
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
                return {
                    "scope_key": scope_key,
                    "aggregate_only": True,
                    "read_model_status": "fresh",
                    "active_generation_id": "gen-all-clean",
                }

        class FakeQueue:
            def __init__(self) -> None:
                self.current_checks: list[tuple[str, str, str, object]] = []
                self.completed: list[tuple[str, str, str, object]] = []

            def read_model_refresh_is_current(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object,
            ) -> bool:
                self.current_checks.append((tenant_id, scope_type, scope_key, source_version))
                return False

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
            event_id="event-all-aggregate-after-shard",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="workbench",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all", "aggregate_only": True, "source_version": 1147, "parent_scope_keys": ["2026-02"]},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(queue.current_checks, [])
        self.assertEqual(builder.calls, [("all", 1147)])
        self.assertEqual(queue.completed, [("tenant-a", "workbench", "all", 1147)])
        self.assertEqual(result["active_generation_id"], "gen-all-clean")

    def test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_refreshing(self) -> None:
        class FakeBuilder:
            def refresh_workbench_all_scope_from_active_shards(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                raise AssertionError(f"parent scope should refresh before aggregate {scope_key}:{source_version}")

        class FakeQueue:
            def __init__(self) -> None:
                self.active_checks: list[tuple[str, str, str]] = []
                self.completed: list[tuple[str, str, str, object]] = []

            def read_model_refresh_is_active(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
            ) -> bool:
                self.active_checks.append((tenant_id, scope_type, scope_key))
                return scope_key == "2026-02"

            def complete_read_model_refresh(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object = None,
            ) -> None:
                self.completed.append((tenant_id, scope_type, scope_key, source_version))

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all-aggregate-parent-refreshing",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="workbench",
            scope_key="all",
            dedupe_key=None,
            payload={
                "scope_key": "all",
                "aggregate_only": True,
                "source_version": 1148,
                "parent_scope_keys": ["2026-02"],
            },
            attempts=1,
            status="processing",
        )

        with self.assertRaisesRegex(RuntimeError, "workbench_read_model_not_fresh"):
            service.handle_runtime_event(event)

        self.assertEqual(queue.active_checks, [("tenant-a", "workbench", "2026-02")])
        self.assertEqual(queue.completed, [])

    def test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_failed(self) -> None:
        class FakeBuilder:
            def refresh_workbench_all_scope_from_active_shards(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                raise AssertionError(f"failed parent scope should refresh before aggregate {scope_key}:{source_version}")

        class FakeQueue:
            def __init__(self) -> None:
                self.active_checks: list[tuple[str, str, str]] = []
                self.fresh_checks: list[tuple[str, str, str]] = []
                self.completed: list[tuple[str, str, str, object]] = []

            def read_model_refresh_is_active(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
            ) -> bool:
                self.active_checks.append((tenant_id, scope_type, scope_key))
                return False

            def read_model_refresh_is_fresh(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
            ) -> bool:
                self.fresh_checks.append((tenant_id, scope_type, scope_key))
                return False

            def complete_read_model_refresh(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object = None,
            ) -> None:
                self.completed.append((tenant_id, scope_type, scope_key, source_version))

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all-aggregate-parent-failed",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="workbench",
            scope_key="all",
            dedupe_key=None,
            payload={
                "scope_key": "all",
                "aggregate_only": True,
                "source_version": 1149,
                "parent_scope_keys": ["2026-02"],
            },
            attempts=1,
            status="processing",
        )

        with self.assertRaisesRegex(RuntimeError, "workbench_read_model_not_fresh"):
            service.handle_runtime_event(event)

        self.assertEqual(queue.active_checks, [("tenant-a", "workbench", "2026-02")])
        self.assertEqual(queue.fresh_checks, [("tenant-a", "workbench", "2026-02")])
        self.assertEqual(queue.completed, [])

    def test_workbench_refresh_handler_does_not_enqueue_all_aggregate_after_month_publish_by_default(self) -> None:
        class FakeBuilder:
            def rebuild_workbench_read_model_scope(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                return {"scope_key": scope_key, "active_generation_id": "gen-2026-05", "source_version": source_version}

        class FakeQueue:
            def __init__(self) -> None:
                self.completed: list[tuple[str, str, str, object]] = []
                self.enqueued: list[dict[str, object]] = []

            def complete_read_model_refresh(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object = None,
            ) -> None:
                self.completed.append((tenant_id, scope_type, scope_key, source_version))

            def enqueue(self, **kwargs: object) -> None:
                self.enqueued.append(dict(kwargs))

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-month",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 19},
            attempts=1,
            status="processing",
            priority="high",
            trace_id="trace-workbench-month",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(queue.completed, [("tenant-a", "workbench", "2026-05", 19)])
        self.assertNotIn("aggregate_enqueued", result)
        self.assertEqual(queue.enqueued, [])

    def test_workbench_month_publish_enqueues_cost_statistics_after_projection_commit(self) -> None:
        calls: list[str] = []

        class FakeBuilder:
            def rebuild_workbench_read_model_scope(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                calls.append(f"published:{scope_key}:{source_version}")
                return {"scope_key": scope_key, "active_generation_id": "gen-2026-05"}

        class FakeQueue:
            def __init__(self) -> None:
                self.refreshes: list[dict[str, object]] = []
                self.completed: list[tuple[str, str, str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                calls.append(f"enqueued:{kwargs['scope_type']}:{kwargs['scope_key']}")
                self.refreshes.append(dict(kwargs))

            def complete_read_model_refresh(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object = None,
            ) -> None:
                calls.append(f"completed:{scope_type}:{scope_key}")
                self.completed.append((tenant_id, scope_type, scope_key, source_version))

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-month-cost-fanout",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 19},
            attempts=1,
            status="processing",
            priority="high",
            trace_id="trace-workbench-cost-fanout",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(
            result["cost_statistics_enqueued_scope_keys"],
            ["active:2026-05", "all:2026-05"],
        )
        self.assertEqual(
            [(item["scope_type"], item["scope_key"], item["reason"]) for item in queue.refreshes],
            [
                ("cost_statistics", "active:2026-05", "workbench_shard_published"),
                ("cost_statistics", "all:2026-05", "workbench_shard_published"),
            ],
        )
        self.assertEqual(
            calls,
            [
                "published:2026-05:19",
                "enqueued:cost_statistics:active:2026-05",
                "enqueued:cost_statistics:all:2026-05",
                "completed:workbench:2026-05",
            ],
        )

    def test_workbench_all_aggregate_does_not_enqueue_cost_statistics(self) -> None:
        class FakeBuilder:
            def refresh_workbench_all_scope_from_active_shards(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                return {
                    "scope_key": scope_key,
                    "active_generation_id": "gen-all",
                    "read_model_status": "fresh",
                    "source_version": source_version,
                }

        class FakeQueue:
            def __init__(self) -> None:
                self.refreshes: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.refreshes.append(dict(kwargs))

            def complete_read_model_refresh(self, **_kwargs: object) -> None:
                return None

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all-no-cost-fanout",
            tenant_id="default",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="workbench",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all", "aggregate_only": True},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertNotIn("cost_statistics_enqueued_scope_keys", result)
        self.assertEqual(queue.refreshes, [])

    def test_workbench_refresh_handler_uses_coalescing_all_aggregate_enqueue_when_available(self) -> None:
        class FakeBuilder:
            def rebuild_workbench_read_model_scope(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                return {"scope_key": scope_key, "active_generation_id": f"gen-{scope_key}", "source_version": source_version}

        class FakeQueue:
            def __init__(self) -> None:
                self.completed: list[tuple[str, str, str, object]] = []
                self.enqueued: list[dict[str, object]] = []
                self.aggregate_enqueued: list[dict[str, object]] = []

            def complete_read_model_refresh(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object = None,
            ) -> None:
                self.completed.append((tenant_id, scope_type, scope_key, source_version))

            def enqueue(self, **kwargs: object) -> None:
                self.enqueued.append(dict(kwargs))

            def enqueue_workbench_all_aggregate_refresh(self, **kwargs: object) -> None:
                self.aggregate_enqueued.append(dict(kwargs))

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-month",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 19, "publish_all_aggregate": True},
            attempts=1,
            status="processing",
            priority="high",
            trace_id="trace-workbench-month",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(queue.completed, [("tenant-a", "workbench", "2026-05", 19)])
        self.assertEqual(result["aggregate_enqueued"], True)
        self.assertEqual(queue.enqueued, [])
        self.assertEqual(
            queue.aggregate_enqueued,
            [
                {
                    "tenant_id": "tenant-a",
                    "parent_scope_keys": ["2026-05"],
                    "source_version": 19,
                    "reason": "workbench_shard_published",
                    "priority": "high",
                    "delay_seconds": 0.0,
                    "trace_id": "trace-workbench-month",
                }
            ],
        )

    def test_workbench_relation_refresh_does_not_enqueue_all_aggregate_for_write_visibility(self) -> None:
        class FakeBuilder:
            def rebuild_workbench_read_model_scope(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                return {"scope_key": scope_key, "active_generation_id": f"gen-{scope_key}", "source_version": source_version}

        class FakeQueue:
            def __init__(self) -> None:
                self.completed: list[tuple[str, str, str, object]] = []
                self.aggregate_enqueued: list[dict[str, object]] = []

            def complete_read_model_refresh(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object = None,
            ) -> None:
                self.completed.append((tenant_id, scope_type, scope_key, source_version))

            def enqueue_workbench_all_aggregate_refresh(self, **kwargs: object) -> None:
                self.aggregate_enqueued.append(dict(kwargs))

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-relation-month",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={
                "scope_key": "2026-05",
                "source_version": 19,
                "reason": "workbench_relation_changed",
                "metadata": {
                    "action_name": "withdraw_link",
                    "row_ids": ["oa-1", "bank-1"],
                    "case_ids": ["CASE-1"],
                },
            },
            attempts=1,
            status="processing",
            priority="high",
            trace_id="trace-workbench-relation-month",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(queue.completed, [("tenant-a", "workbench", "2026-05", 19)])
        self.assertNotIn("aggregate_enqueued", result)
        self.assertEqual(queue.aggregate_enqueued, [])

    def test_workbench_refresh_handler_can_enqueue_aggregate_without_legacy_enqueue_method(self) -> None:
        class FakeBuilder:
            def rebuild_workbench_read_model_scope(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                return {"scope_key": scope_key, "active_generation_id": f"gen-{scope_key}", "source_version": source_version}

        class FakeQueue:
            def __init__(self) -> None:
                self.aggregate_enqueued: list[dict[str, object]] = []

            def complete_read_model_refresh(self, **_kwargs: object) -> None:
                return None

            def enqueue_workbench_all_aggregate_refresh(self, **kwargs: object) -> None:
                self.aggregate_enqueued.append(dict(kwargs))

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-month",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 19, "publish_all_aggregate": True},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result["aggregate_enqueued"], True)
        self.assertEqual(queue.aggregate_enqueued[0]["parent_scope_keys"], ["2026-05"])
        self.assertEqual(queue.aggregate_enqueued[0]["priority"], "low")
        self.assertEqual(queue.aggregate_enqueued[0]["delay_seconds"], 3.0)

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
                self.refreshes: list[tuple[str, str, str, str, str | None]] = []
                self.completed: list[tuple[str, str, str, object]] = []
                self.enqueued: list[dict[str, object]] = []

            def enqueue_read_model_refresh(
                self,
                *,
                scope_type: str,
                scope_key: str,
                reason: str,
                priority: str = "normal",
                trace_id: str | None = None,
                **_kwargs: object,
            ) -> None:
                self.refreshes.append((scope_type, scope_key, reason, priority, trace_id))

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
            priority="high",
            trace_id="trace-workbench-all",
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
            [
                ("workbench", "2026-05", "workbench_all_shard", "high", "trace-workbench-all"),
                ("workbench", "2026-04", "workbench_all_shard", "high", "trace-workbench-all"),
            ],
        )
        self.assertEqual(queue.completed, [])
        self.assertEqual(len(queue.enqueued), 1)
        self.assertEqual(queue.enqueued[0]["scope_key"], "all")
        self.assertEqual(queue.enqueued[0]["payload"]["aggregate_only"], True)
        self.assertEqual(queue.enqueued[0]["priority"], "high")
        self.assertEqual(queue.enqueued[0]["trace_id"], "trace-workbench-all")

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

    def test_workbench_refresh_handler_does_not_complete_dirty_scope_when_all_aggregate_did_not_publish(self) -> None:
        class FakeBuilder:
            def refresh_workbench_all_scope_from_active_shards(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                return {
                    "scope_key": scope_key,
                    "aggregate_only": True,
                    "read_model_status": "refreshing",
                    "active_generation_id": None,
                }

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

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all-aggregate-miss",
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

        with self.assertRaisesRegex(RuntimeError, "workbench_all_scope_aggregate_not_published"):
            service.handle_runtime_event(event)

        self.assertEqual(queue.completed, [])

    def test_workbench_refresh_handler_completes_all_when_aggregate_publish_is_confirmed_despite_self_dirty_status(self) -> None:
        class FakeBuilder:
            def refresh_workbench_all_scope_from_active_shards(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                return {
                    "scope_key": scope_key,
                    "aggregate_only": True,
                    "aggregate_published": True,
                    "read_model_status": "refreshing",
                    "active_generation_id": "workbench:all:published",
                }

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

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all-aggregate-self-dirty",
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

        self.assertEqual(result["active_generation_id"], "workbench:all:published")
        self.assertEqual(queue.completed, [("tenant-a", "workbench", "all", 9)])

    def test_workbench_refresh_handler_warms_homepage_pages_after_publish(self) -> None:
        class FakeBuilder:
            def rebuild_workbench_read_model_scope(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
                return {"scope_key": scope_key, "active_generation_id": "gen-2026-05", "source_version": source_version}

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

        warmed: list[str] = []
        service = WorkbenchReadModelRefreshService(
            projection_builder=FakeBuilder(),
            queue_repository=FakeQueue(),
            post_refresh_warmer=lambda scope_key: warmed.append(scope_key) or {"warmed": True},
        )
        event = RuntimeQueueEvent(
            event_id="event-month-warm",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 17},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(warmed, ["2026-05"])
        self.assertEqual(result["cache_warmup"], {"warmed": True})

    def test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate(self) -> None:
        class FakeQueue:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.calls.append(dict(kwargs))

        class FakeSearch:
            def __init__(self) -> None:
                self.clear_count = 0

            def clear_cache(self) -> None:
                self.clear_count += 1

        class FakeStateStore:
            def __init__(self) -> None:
                self.saved_payloads: list[dict[str, object]] = []

            def save_import_delta(self, payload: dict[str, object]) -> None:
                self.saved_payloads.append(payload)

        queue = FakeQueue()
        lifecycle = _RuntimeWorkerDerivedLifecycle(
            queue_repository=queue,
            state_store=FakeStateStore(),
            search_service=FakeSearch(),
            workbench_source_versions_provider=lambda: {},
        )
        lifecycle.persist_confirmed_import_delta(
            import_state_payload={"imports": {}, "file_imports": {}},
            cost_statistics_scope_keys=["2026-05"],
        )

        workbench_calls = [call for call in queue.calls if call["scope_type"] == "workbench"]
        self.assertEqual(workbench_calls, [{"scope_type": "workbench", "scope_key": "2026-05", "reason": "import_state_changed"}])
        month_scoped_types = {
            "workbench_relation",
            "invoice_lifecycle",
            "search",
            "input_invoice_usage",
            "output_invoice_collection",
            "oa_pending_payment",
        }
        for scope_type in month_scoped_types:
            with self.subTest(scope_type=scope_type):
                self.assertIn(
                    {"scope_type": scope_type, "scope_key": "2026-05", "reason": "import_state_changed"},
                    queue.calls,
                )
                self.assertNotIn(
                    {"scope_type": scope_type, "scope_key": "all", "reason": "import_state_changed"},
                    queue.calls,
                )
        self.assertIn(
            {"scope_type": "cost_statistics", "scope_key": "active:2026-05", "reason": "import_state_changed"},
            queue.calls,
        )
        self.assertIn(
            {"scope_type": "cost_statistics", "scope_key": "all:2026-05", "reason": "import_state_changed"},
            queue.calls,
        )
        pending_invoice_calls = [call for call in queue.calls if call["scope_type"] == "pending_invoice"]
        self.assertEqual(
            pending_invoice_calls,
            [
                {"scope_type": "pending_invoice", "scope_key": "expense:all:2026-05", "reason": "import_state_changed"},
                {"scope_type": "pending_invoice", "scope_key": "income:all:2026-05", "reason": "import_state_changed"},
                {"scope_type": "pending_invoice", "scope_key": "income:cash_income:2026-05", "reason": "import_state_changed"},
            ],
        )

    def test_import_state_invalidation_skips_unaffected_invoice_relation_read_models(self) -> None:
        class FakeQueue:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.calls.append(dict(kwargs))

        class FakeSearch:
            def clear_cache(self) -> None:
                return None

        class FakeStateStore:
            def save_import_delta(self, _payload: dict[str, object]) -> None:
                return None

        queue = FakeQueue()
        lifecycle = _RuntimeWorkerDerivedLifecycle(
            queue_repository=queue,
            state_store=FakeStateStore(),
            search_service=FakeSearch(),
            workbench_source_versions_provider=lambda: {},
        )
        lifecycle.persist_confirmed_import_delta(
            import_state_payload={"imports": {}, "file_imports": {}},
            cost_statistics_scope_keys=["2026-05"],
            input_invoice_usage_scope_keys=["2026-05"],
            output_invoice_collection_scope_keys=[],
        )

        self.assertIn(
            {"scope_type": "input_invoice_usage", "scope_key": "2026-05", "reason": "import_state_changed"},
            queue.calls,
        )
        self.assertNotIn(
            {"scope_type": "output_invoice_collection", "scope_key": "2026-05", "reason": "import_state_changed"},
            queue.calls,
        )
        self.assertNotIn(
            {"scope_type": "workbench", "scope_key": "all", "reason": "import_state_changed"},
            queue.calls,
        )
        self.assertNotIn(
            {"scope_type": "pending_invoice", "scope_key": "expense:all", "reason": "import_state_changed"},
            queue.calls,
        )

    def test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes(self) -> None:
        class FakeQueue:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.calls.append(dict(kwargs))

        class FakeStateStore:
            def save_import_delta(self, _payload: dict[str, object]) -> None:
                return None

        lifecycle = _RuntimeWorkerDerivedLifecycle(
            queue_repository=FakeQueue(),
            state_store=FakeStateStore(),
            search_service=SimpleNamespace(clear_cache=lambda: None),
            workbench_source_versions_provider=lambda: {},
        )
        lifecycle.persist_confirmed_import_delta(
            import_state_payload={"imports": {}, "file_imports": {}},
            cost_statistics_scope_keys=["2026-05"],
            bank_detail_scope_keys=["2026-06"],
        )

        queue = lifecycle._queue_repository
        bank_detail_calls = [call for call in queue.calls if call["scope_type"] == "bank_detail"]
        self.assertEqual(
            bank_detail_calls,
            [{"scope_type": "bank_detail", "scope_key": "2026-06", "reason": "import_facts_changed"}],
        )
        bank_account_balance_calls = [call for call in queue.calls if call["scope_type"] == "bank_account_balance"]
        self.assertEqual(
            bank_account_balance_calls,
            [{"scope_type": "bank_account_balance", "scope_key": "all", "reason": "import_state_changed"}],
        )

    def test_workbench_refresh_handler_reports_warmup_error_without_failing_publish(self) -> None:
        class FakeBuilder:
            def refresh_workbench_all_scope_from_active_shards(
                self,
                scope_key: str,
                *,
                source_version: object = None,
            ) -> dict[str, object]:
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

        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(
            projection_builder=FakeBuilder(),
            queue_repository=queue,
            post_refresh_warmer=lambda _scope_key: (_ for _ in ()).throw(RuntimeError("redis unavailable")),
        )
        event = RuntimeQueueEvent(
            event_id="event-all-warm-error",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="workbench",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all", "aggregate_only": True, "source_version": 18},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(queue.completed, [("tenant-a", "workbench", "all", 18)])
        self.assertEqual(result["active_generation_id"], "gen-all")
        self.assertEqual(result["cache_warmup"], {"status": "failed", "error": "redis unavailable"})



    def test_sql_projection_prevents_same_invoice_identity_in_paired_and_open_zones(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=ReadModelSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-project-1": {
                "id": "oa-project-1",
                "type": "oa",
                "source_kind": "oa",
                "status": "unpaired",
                "amount": "300.00",
                "counterparty_name": "云南元大工程咨询有限责任公司",
                "project_name": "昆明卷烟厂动力设备控制系统升级改造项目",
            },
            "bank-project-1": {
                "id": "bank-project-1",
                "type": "bank",
                "source_kind": "bank_transaction",
                "status": "unpaired",
                "debit_amount": "300.00",
                "amount": "300.00",
                "counterparty_name": "云南元大工程咨询有限责任公司",
                "txn_direction": "outflow",
                "trade_time": "2026-02-12 15:08:35",
                "account_no": "622200008106",
                "summary": "招标文件费用",
            },
            "oa-att-inv-project-1": {
                "id": "oa-att-inv-project-1",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "status": "unpaired",
                "derived_from_oa_id": "oa-project-1",
                "digital_invoice_no": "265320000000992",
                "invoice_no": "265320000000992",
                "total_with_tax": "300.00",
                "amount": "283.02",
                "tax_amount": "16.98",
                "tax_rate": "6%",
                "seller_name": "溯源科技有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-20",
            },
            "invoice-formal-project-1": {
                "id": "invoice-formal-project-1",
                "type": "invoice",
                "source_kind": "invoice",
                "status": "unpaired",
                "digital_invoice_no": "265320000000992",
                "invoice_no": "265320000000992",
                "total_with_tax": "300.00",
                "amount": "283.02",
                "tax_amount": "16.98",
                "tax_rate": "6%",
                "seller_name": "溯源科技有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-20",
            },
        }
        relation = {
            "case_id": "CASE-PROJECT-1",
            "relation_mode": "manual_confirmed",
            "row_ids": ["oa-project-1", "bank-project-1"],
            "row_types": ["oa", "bank"],
        }

        payload = builder._group_payload("2026-02", with_test_object_identities(rows_by_id), [relation])

        paired_invoice_ids = [
            row["id"]
            for group in payload["paired"]["groups"]
            for row in group.get("invoice_rows", [])
        ]
        open_invoice_ids = [
            row["id"]
            for group in payload["unpaired"]["groups"]
            for row in group.get("invoice_rows", [])
        ]
        self.assertEqual(paired_invoice_ids, [])
        self.assertEqual(open_invoice_ids, ["invoice-formal-project-1"])
        unpaired_invoice_rows = [
            row
            for group in payload["unpaired"]["groups"]
            for row in group.get("invoice_rows", [])
            if row["id"] == "invoice-formal-project-1"
        ]
        self.assertEqual(unpaired_invoice_rows[0]["identity_alias_rows"]["invoice"][0]["id"], "oa-att-inv-project-1")


    def test_sql_projection_keeps_turnover_manual_closure_bank_only_case_paired(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=ReadModelSnapshotRecorder(),
        )
        rows_by_id = {
            "bank-in-1": {
                "id": "bank-in-1",
                "type": "bank",
                "source_kind": "bank",
                "credit_amount": "100000.00",
                "counterparty_name": "贾小花",
                "trade_time": "2026-02-04 17:07:45",
                "summary": "暂借款",
            },
            "bank-in-2": {
                "id": "bank-in-2",
                "type": "bank",
                "source_kind": "bank",
                "credit_amount": "200000.00",
                "counterparty_name": "贾小花",
                "trade_time": "2026-02-04 13:20:48",
                "summary": "暂借款",
            },
            "bank-out-1": {
                "id": "bank-out-1",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "300000.00",
                "counterparty_name": "贾小花",
                "trade_time": "2026-03-04 15:24:58",
                "summary": "还暂借款",
            },
        }
        relation = {
            "case_id": "turnover:turnover_rel_jia_xiaohua",
            "relation_mode": "turnover_manual_closure",
            "row_ids": ["bank-in-1", "bank-in-2", "bank-out-1"],
            "row_types": ["bank", "bank", "bank"],
        }

        payload = builder._group_payload("2026-03", with_test_object_identities(rows_by_id), [relation])

        self.assertEqual(payload["unpaired"]["groups"], [])
        paired_groups = payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        self.assertEqual(paired_groups[0]["group_id"], "case:turnover:turnover_rel_jia_xiaohua")
        self.assertEqual(paired_groups[0]["group_type"], "relation")
        self.assertEqual(paired_groups[0]["relation_mode"], "turnover_manual_closure")
        self.assertCountEqual(
            [row["id"] for row in paired_groups[0]["bank_rows"]],
            ["bank-in-1", "bank-in-2", "bank-out-1"],
        )
        self.assertTrue(all(row["case_id"] == relation["case_id"] for row in paired_groups[0]["bank_rows"]))
        self.assertTrue(all(row["invoice_relation"]["label"] == "收支闭环" for row in paired_groups[0]["bank_rows"]))
        self.assertTrue(all(row["status"] == "paired" for row in paired_groups[0]["bank_rows"]))

    def test_sql_projection_pairs_turnover_manual_closure_when_no_invoice_required(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=ReadModelSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-turnover-1": {
                "id": "oa-turnover-1",
                "type": "oa",
                "source_kind": "oa",
                "amount": "150000.00",
                "applicant": "刘际涛",
                "counterparty_name": "杨丽萍",
                "payment_date": "2026-05-22",
            },
            "bank-turnover-1": {
                "id": "bank-turnover-1",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "150000.00",
                "counterparty_name": "杨丽萍",
                "trade_time": "2026-05-22 14:40:07",
                "summary": "还5月9-11日借入款",
            },
        }
        relation = {
            "case_id": "turnover:turnover_rel_no_invoice",
            "relation_mode": "turnover_manual_closure",
            "row_ids": ["oa-turnover-1", "bank-turnover-1"],
            "row_types": ["oa", "bank"],
            "special_metadata": {
                "requires_oa": True,
                "requires_invoice": False,
                "paired_requirement_tag_codes": ["external_turnover"],
                "paired_requirement_source": "no_oa_bank_batch_tag_selection",
            },
        }

        payload = builder._group_payload("2026-05", with_test_object_identities(rows_by_id), [relation])

        self.assertEqual(payload["unpaired"]["groups"], [])
        paired_groups = payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        self.assertEqual(paired_groups[0]["group_id"], "case:turnover:turnover_rel_no_invoice")
        self.assertEqual(paired_groups[0]["relation_mode"], "turnover_manual_closure")
        self.assertEqual([row["id"] for row in paired_groups[0]["oa_rows"]], ["oa-turnover-1"])
        self.assertEqual([row["id"] for row in paired_groups[0]["bank_rows"]], ["bank-turnover-1"])

    def test_sql_projection_active_no_oa_relation_uses_grouping_contract(self) -> None:
        recorder = ReadModelSnapshotRecorder()
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

        payload = builder._group_payload("2026-05", with_test_object_identities(rows_by_id), [relation])

        paired = payload["paired"]["groups"]
        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0]["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(paired[0]["display_mode"], "collapsed_summary")
        self.assertEqual([row["id"] for row in paired[0]["bank_rows"]], ["relation_summary:CASE-NO-OA-1"])
        self.assertCountEqual([row["id"] for row in paired[0]["collapsed_rows"]["bank"]], ["bank-a", "bank-b"])
        self.assertEqual(paired[0]["special_metadata"]["source_batch_id"], "batch-no-oa-fee-001")
        self.assertEqual(paired[0]["bank_rows"][0]["relation_mode"], "no_oa_bank_batch")

    def test_sql_projection_pairs_bank_flow_rule_batch_ten_fee_rows_without_oa_or_invoice(self) -> None:
        recorder = ReadModelSnapshotRecorder()
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=recorder,
        )
        row_ids = [f"bank-flow-fee-{index:02d}" for index in range(1, 11)]
        rows_by_id = {
            row_id: {
                "id": row_id,
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "8.00",
                "credit_amount": "",
                "trade_time": f"2026-05-{index:02d} 09:00",
                "counterparty_name": "手续费",
            }
            for index, row_id in enumerate(row_ids, start=1)
        }
        relation = {
            "case_id": "CASE-BANK-FLOW-FEE-010",
            "relation_mode": "bank_flow_rule_batch",
            "row_ids": row_ids,
            "row_types": ["bank" for _row_id in row_ids],
            "special_metadata": {
                "source": "bank_flow_rule_batch",
                "relation_mode": "bank_flow_rule_batch",
                "source_batch_id": "bank-flow-fee-batch-010",
                "batch_type": "fee",
                "batch_label": "手续费",
                "flow_rule_tag_code": "fee",
                "flow_rule_version": 7,
                "requires_oa": False,
                "requires_invoice": False,
                "source_row_count": 10,
                "collapsed_bank_rows": True,
                "total_amount": "80.00",
                "withdrawable": True,
                "display_tags": ["流水规则", "手续费"],
            },
            "display_tags": ["流水规则", "手续费"],
        }

        payload = builder._group_payload("2026-05", with_test_object_identities(rows_by_id), [relation])

        self.assertEqual(payload["unpaired"]["groups"], [])
        paired = payload["paired"]["groups"]
        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0]["relation_mode"], "bank_flow_rule_batch")
        self.assertEqual(paired[0]["display_mode"], "collapsed_summary")
        self.assertEqual([row["id"] for row in paired[0]["bank_rows"]], ["relation_summary:CASE-BANK-FLOW-FEE-010"])
        self.assertCountEqual([row["id"] for row in paired[0]["collapsed_rows"]["bank"]], row_ids)
        summary_row = paired[0]["summary_row"]
        self.assertEqual(summary_row["source_kind"], "bank_flow_rule_batch_summary")
        self.assertEqual(summary_row["relation_mode"], "bank_flow_rule_batch")
        self.assertEqual(paired[0]["special_metadata"]["source_batch_id"], "bank-flow-fee-batch-010")
        self.assertIn("流水规则", paired[0]["display_tags"])
        self.assertIn("手续费", paired[0]["display_tags"])
        self.assertNotEqual(summary_row["relation_mode"], "no_oa_bank_batch")

    def test_sql_projection_applies_row_overrides_before_grouping(self) -> None:
        recorder = ReadModelSnapshotRecorder()
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

        payload = builder._group_payload("2026-05", with_test_object_identities(rows_by_id), [])

        row = payload["unpaired"]["groups"][0]["bank_rows"][0]
        self.assertTrue(row["ignored"])
        self.assertEqual(row["case_id"], "CASE-OVERRIDE-1")
        self.assertEqual(row["invoice_relation"]["code"], "manual_exception")

    def test_sql_projection_applies_active_exception_case_projection(self) -> None:
        recorder = ReadModelSnapshotRecorder()
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

        payload = builder._group_payload("2026-05", with_test_object_identities(rows_by_id), [])

        row = payload["unpaired"]["groups"][0]["bank_rows"][0]
        self.assertEqual(row["exception_case_id"], "CASE-EXCEPTION-1")
        self.assertEqual(row["case_id"], "CASE-EXCEPTION-1")
        self.assertEqual(row["invoice_relation"]["tone"], "danger")


if __name__ == "__main__":
    unittest.main()
