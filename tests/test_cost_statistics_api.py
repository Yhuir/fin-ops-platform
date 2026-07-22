import json
import unittest
from dataclasses import replace
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from urllib.parse import quote

from fin_ops_platform.services.cost_statistics_source_versions import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
    cost_statistics_source_versions,
)
from fin_ops_platform.services.cost_statistics_sql_projection import CostStatisticsSqlProjectionBuilder
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_object_identity_arbitration import (
    WorkbenchObjectIdentityArbitrationService,
)
from fin_ops_platform.services.workbench_relation_grouping import WorkbenchRelationGroupingService
from openpyxl import load_workbook

from tests.app_test_support import build_local_state_application as build_application


def _cost_statistics_gate_snapshot(app, scope_key: str) -> dict[str, object]:
    _project_scope, month = str(scope_key).split(":", 1)
    source_settings = app._app_settings_service.get_cost_statistics_source_settings_payload()
    dependency_versions = {"source_version": 1} if month != "all" else None
    return {
        "source_settings": source_settings,
        "workbench_source_versions": dict(dependency_versions or {}),
        "bank_detail_source_versions": dict(dependency_versions or {}),
        "source_versions": cost_statistics_source_versions(
            month=month,
            settings_payload=source_settings,
            workbench_source_versions=dependency_versions,
            bank_detail_source_versions=dependency_versions,
        ),
    }


class _CostStatsOAAdapter:
    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        if month != "2026-03":
            return []
        return [
            OAApplicationRecord(
                id="oa-cost-api-001",
                month="2026-03",
                section="paired",
                case_id="CASE-COST-001",
                applicant="刘际涛",
                project_name="云南溯源科技",
                apply_type="日常报销",
                amount="1250",
                counterparty_name="昆明设备供应商",
                reason="PLC 模块采购",
                relation_code="fully_linked",
                relation_label="完全关联",
                relation_tone="success",
                expense_type="设备货款及材料费",
                expense_content="PLC 模块采购",
                detail_fields={
                    "费用类型": "设备货款及材料费",
                    "费用内容": "PLC 模块采购",
                },
            )
        ]


class _FallbackCostStatsOAAdapter:
    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        if month != "2026-03":
            return []
        return [
            OAApplicationRecord(
                id="oa-cost-fallback-001",
                month="2026-03",
                section="unpaired",
                case_id=None,
                applicant="刘际涛",
                project_name="云南溯源科技",
                apply_type="支付申请",
                amount="1250",
                counterparty_name="昆明设备供应商",
                reason="PLC 模块采购",
                relation_code="pending_match",
                relation_label="待找流水与发票",
                relation_tone="warn",
                expense_type="",
                expense_content="",
                detail_fields={
                    "费用类型": "设备货款及材料费",
                    "费用内容": "PLC 模块采购",
                },
            )
        ]


def _confirm_active_cost_relation(
    app,
    *,
    month: str,
    oa_row_id: str,
    bank_row_id: str,
    case_id: str,
) -> None:
    rows = app._resolve_live_rows_direct([oa_row_id, bank_row_id], month_hint=month)
    rows_by_id = {str(row["id"]): row for row in rows}
    app._workbench_pair_relation_service.create_active_relation(
        case_id=case_id,
        row_ids=[oa_row_id, bank_row_id],
        row_types=[str(rows_by_id[row_id]["type"]) for row_id in (oa_row_id, bank_row_id)],
        relation_mode="manual_confirmed",
        created_by="cost_statistics_test",
        month_scope=month,
        note="cost statistics active relation fixture",
        special_metadata={"requires_oa": True, "requires_invoice": False},
    )


def _grouped_cost_workbench_payload(app, month: str) -> dict[str, object]:
    relations = [
        relation
        for relation in app._workbench_pair_relation_service.list_active_relations()
        if month == "all" or str(relation.get("month_scope") or "all") in {"all", month}
    ]
    row_ids = [
        str(row_id)
        for relation in relations
        for row_id in list(relation.get("row_ids") or [])
        if str(row_id).strip()
    ]
    rows = app._resolve_live_rows_direct(row_ids, month_hint=month) if row_ids else []
    rows_by_id = {str(row["id"]): row for row in rows}
    WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)
    return WorkbenchRelationGroupingService().group_payload(
        month,
        rows_by_id=rows_by_id,
        active_relations=relations,
    )


class _CostStatisticsProjectionFixtureConnection:
    def __init__(self, settings_payload: dict[str, object]) -> None:
        self._settings_payload = settings_payload

    def fetch_one(self, sql: str, _params: tuple = ()) -> dict[str, object] | None:
        if "from app.app_settings" in " ".join(sql.lower().split()):
            return {"settings_payload": self._settings_payload}
        return None


def _project_cost_statistics_payload(app, month: str, project_scope: str) -> dict[str, object]:
    grouped_payload = _grouped_cost_workbench_payload(app, month)
    groups = list(((grouped_payload.get("paired") or {}).get("groups") or []))
    builder = CostStatisticsSqlProjectionBuilder(
        connection=_CostStatisticsProjectionFixtureConnection(app._app_settings_service.get_settings_payload()),
        read_model_repository=object(),
    )
    return builder._build_explorer_payload(
        month,
        project_scope=project_scope,
        workbench_groups=groups,
        bank_detail_payload={"rows": [], "month_rows": []},
    )


def _canonical_bank_flow_projection(app, month: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows: list[dict[str, object]] = []
    total_amount = 0
    expense_amount = 0
    income_amount = 0
    expense_count = 0
    income_count = 0
    for transaction in app._import_service.list_transactions():
        transaction_month = str(transaction.txn_date or "")[:7]
        if month != "all" and transaction_month != month:
            continue
        amount = transaction.amount
        total_amount += amount
        is_income = str(transaction.txn_direction.value) == "inflow"
        if is_income:
            income_amount += amount
            income_count += 1
        else:
            expense_amount += amount
            expense_count += 1
        rows.append(
            {
                "transaction_id": transaction.id,
                "trade_time": transaction.trade_time or transaction.pay_receive_time or transaction.txn_date,
                "direction": "收入" if is_income else "支出",
                "project_name": "未配对OA",
                "expense_type": "未分类",
                "expense_content": transaction.summary or transaction.remark or "未分类",
                "amount": f"{amount:.2f}",
                "counterparty_name": transaction.counterparty_name_raw,
                "payment_account_label": transaction.account_no,
                "remark": transaction.remark or "",
                "bank_tag_code": "",
                "bank_tag_label": "未标记",
                "bank_tag_primary_label": "未标记",
                "bank_tag_sub_label": "未标记",
                "bank_tag_label_path": ["未标记"],
            }
        )
    return rows, {
        "row_count": len(rows),
        "transaction_count": len(rows),
        "total_amount": f"{total_amount:.2f}",
        "expense_amount": f"{expense_amount:.2f}",
        "income_amount": f"{income_amount:.2f}",
        "expense_transaction_count": expense_count,
        "income_transaction_count": income_count,
    }


class _MemoryCostStatisticsSqlRepository:
    def __init__(
        self,
        gate_snapshot_provider,
    ) -> None:
        self.read_models: dict[str, dict[str, object]] = {}
        self._gate_snapshot_provider = gate_snapshot_provider

    @staticmethod
    def scope_key(month: str, project_scope: str) -> str:
        return f"{project_scope}:{month}"

    def get_read_model(self, month: str, project_scope: str) -> dict[str, object] | None:
        return self.read_models.get(self.scope_key(month, project_scope))

    def upsert_read_model(
        self,
        month: str,
        project_scope: str,
        payload: dict[str, object],
        generated_at: str | None = None,
        source_scope_keys: list[str] | None = None,
        source_versions: dict[str, object] | None = None,
        schema_version: str = COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
        cache_status: str = "ready",
        refresh_status: str = "fresh",
    ) -> dict[str, object]:
        scope_key = self.scope_key(month, project_scope)
        read_model = {
            "scope_key": scope_key,
            "month": month,
            "project_scope": project_scope,
            "payload": payload,
            "generated_at": generated_at,
            "source_scope_keys": list(source_scope_keys or []),
            "source_versions": dict(source_versions or {}),
            "schema_version": schema_version,
            "cache_status": cache_status,
            "refresh_status": refresh_status,
        }
        self.read_models[scope_key] = read_model
        return read_model

    def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object] | None:
        view = self._stored_view(scope_key=scope_key)
        if not isinstance(view, dict):
            return None
        gate_snapshot = self._gate_snapshot_provider(scope_key)
        return {
            "scope_key": scope_key,
            "schema_version": view.get("schema_version"),
            "generated_at": view.get("generated_at"),
            "source_versions": view.get("source_versions") if isinstance(view.get("source_versions"), dict) else {},
            "source_settings": dict(gate_snapshot["source_settings"]),
            "workbench_source_versions": dict(gate_snapshot["workbench_source_versions"]),
            "bank_detail_source_versions": dict(gate_snapshot["bank_detail_source_versions"]),
            "published_source_version": int(view.get("published_source_version") or 0),
            "dirty_source_version": None,
            "refresh_status": view.get("refresh_status") or "fresh",
            "stale_reasons": [],
        }

    def _stored_view(self, *, scope_key: str) -> dict[str, object] | None:
        read_model = self.read_models.get(scope_key)
        if not isinstance(read_model, dict):
            return None
        payload = read_model.get("payload")
        if not isinstance(payload, dict):
            return None
        source_versions = read_model.get("source_versions")
        if not isinstance(source_versions, dict) or not source_versions:
            source_versions = self._gate_snapshot_provider(scope_key)["source_versions"]
        return {
            "scope_key": scope_key,
            "project_scope": read_model.get("project_scope"),
            "scope_month": read_model.get("month"),
            "payload": payload,
            "raw_payload": payload,
            "generated_at": read_model.get("generated_at") or "2026-07-05T00:00:00",
            "entry_count": len(payload.get("time_rows") or []),
            "source_versions": dict(source_versions or {}),
            "schema_version": read_model.get("schema_version") or COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            "refresh_status": read_model.get("refresh_status") or "fresh",
            "published_source_version": int(read_model.get("published_source_version") or 0),
        }

    def get_cost_statistics_page(
        self,
        *,
        project_scope: str,
        scope_kind: str,
        scope_value: str | None,
        view: str,
        filters: dict[str, str],
        selected_tag_codes: list[str] | None,
        cursor_values: tuple[str, str, str, str] | None,
        page_size: int,
    ) -> dict[str, object] | None:
        del selected_tag_codes, cursor_values
        scope_month = scope_value if scope_kind == "month" else "all"
        stored = self._stored_view(scope_key=f"{project_scope}:{scope_month}")
        payload = stored.get("payload") if isinstance(stored, dict) else None
        if not isinstance(payload, dict):
            return None
        rows_key = "bank_flow_time_rows" if view in {"time", "bank_tag"} else "time_rows"
        rows = [dict(row) for row in list(payload.get(rows_key) or payload.get("time_rows") or []) if isinstance(row, dict)]
        if filters.get("project_name"):
            rows = [row for row in rows if row.get("project_name") == filters["project_name"]]
        if filters.get("expense_type"):
            rows = [row for row in rows if row.get("expense_type") == filters["expense_type"]]
        if filters.get("payment_account_label"):
            rows = [row for row in rows if row.get("payment_account_label") == filters["payment_account_label"]]
        if filters.get("bank_tag_primary_label"):
            rows = [row for row in rows if row.get("bank_tag_primary_label") == filters["bank_tag_primary_label"]]
        if filters.get("bank_tag_sub_label"):
            rows = [row for row in rows if row.get("bank_tag_sub_label") == filters["bank_tag_sub_label"]]
        if view == "project" and not (filters.get("project_name") and filters.get("expense_type")):
            rows = []
        if view == "bank" and not (filters.get("payment_account_label") and filters.get("project_name")):
            rows = []
        if view == "expense_type" and not filters.get("expense_type"):
            rows = []
        if view == "bank_tag" and not (
            filters.get("bank_tag_primary_label") and filters.get("bank_tag_sub_label")
        ):
            rows = []
        return {
            "summary": (
                payload.get("bank_flow_summary") or payload.get("summary")
                if view in {"time", "bank_tag"}
                else payload.get("summary")
            ),
            "available_years": sorted(
                {str(row.get("trade_time") or "")[:4] for row in rows if str(row.get("trade_time") or "")[:4]},
                reverse=True,
            ),
            "primary_facets": (
                payload.get("project_rows")
                if view == "project"
                else payload.get("expense_type_rows")
                if view == "expense_type"
                else []
            ),
            "secondary_facets": payload.get("expense_type_rows") if view == "project" and filters.get("project_name") else [],
            "rows": rows[:page_size],
            "row_count": len(rows),
            "next_cursor_values": None,
        }

    def get_cost_statistics_export_page(
        self,
        *,
        project_scope: str,
        month: str,
        start_month: str | None,
        end_month: str | None,
        start_date: str | None,
        end_date: str | None,
        project_names: list[str],
        expense_types: list[str],
        selected_tag_codes: list[str] | None,
        row_shape: str,
        offset: int,
        page_size: int,
        include_summary: bool,
    ) -> dict[str, object] | None:
        scope_month = month if month != "all" else "all"
        stored = self._stored_view(scope_key=f"{project_scope}:{scope_month}")
        payload = stored.get("payload") if isinstance(stored, dict) else None
        if not isinstance(payload, dict):
            return None
        rows_key = "bank_flow_time_rows" if row_shape == "raw_bank" else "time_rows"
        rows = [dict(row) for row in list(payload.get(rows_key) or []) if isinstance(row, dict)]
        if start_month and end_month and start_month > end_month:
            start_month, end_month = end_month, start_month
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date
        filtered: list[dict[str, object]] = []
        for row in rows:
            trade_time = str(row.get("trade_time") or "")
            row_month = str(row.get("month") or "")[:7] or trade_time[:7]
            trade_date = trade_time[:10]
            tag_code = str(row.get("bank_tag_code") or "").strip() or "__uncategorized__"
            if start_month and row_month < start_month:
                continue
            if end_month and row_month > end_month:
                continue
            if start_date and trade_date < start_date:
                continue
            if end_date and trade_date > end_date:
                continue
            if project_names and row.get("project_name") not in project_names:
                continue
            if expense_types and row.get("expense_type") not in expense_types:
                continue
            if selected_tag_codes is not None and tag_code not in selected_tag_codes:
                continue
            filtered.append(row)

        result_rows: list[dict[str, object]]
        if row_shape in {"project_month", "project_year", "month_summary"}:
            grouped: dict[tuple[str, ...], dict[str, object]] = {}
            for row in filtered:
                trade_time = str(row.get("trade_time") or "")
                if row_shape == "project_month":
                    key = (
                        trade_time[:7],
                        str(row.get("project_name") or ""),
                        str(row.get("expense_type") or ""),
                        str(row.get("expense_content") or ""),
                    )
                elif row_shape == "project_year":
                    key = (
                        trade_time[:4],
                        str(row.get("project_name") or ""),
                        str(row.get("expense_type") or ""),
                        str(row.get("expense_content") or ""),
                    )
                else:
                    key = (
                        str(row.get("project_name") or ""),
                        str(row.get("expense_type") or ""),
                        str(row.get("expense_content") or ""),
                    )
                bucket = grouped.setdefault(key, {"amount": Decimal("0.00"), "transaction_count": 0})
                bucket["amount"] = Decimal(str(bucket["amount"])) + Decimal(str(row.get("amount") or "0").replace(",", ""))
                bucket["transaction_count"] = int(bucket["transaction_count"]) + 1
            result_rows = []
            for key, bucket in sorted(grouped.items()):
                if row_shape in {"project_month", "project_year"}:
                    period_label, project_name, expense_type, expense_content = key
                    result_rows.append(
                        {
                            "period_label": period_label,
                            "project_name": project_name,
                            "expense_type": expense_type,
                            "expense_content": expense_content,
                            "amount": str(bucket["amount"]),
                            "transaction_count": bucket["transaction_count"],
                        }
                    )
                else:
                    project_name, expense_type, expense_content = key
                    result_rows.append(
                        {
                            "project_name": project_name,
                            "expense_type": expense_type,
                            "expense_content": expense_content,
                            "amount": str(bucket["amount"]),
                            "transaction_count": bucket["transaction_count"],
                        }
                    )
        else:
            result_rows = sorted(
                filtered,
                key=lambda row: (str(row.get("trade_time") or ""), str(row.get("transaction_id") or "")),
                reverse=True,
            )
        page_rows = result_rows[offset : offset + page_size]
        total_amount = sum(
            (Decimal(str(row.get("amount") or "0").replace(",", "")) for row in filtered),
            start=Decimal("0.00"),
        )
        expense_rows = [row for row in filtered if row.get("direction") == "支出"]
        income_rows = [row for row in filtered if row.get("direction") == "收入"]
        summary = None
        if include_summary:
            summary = {
                "source_row_count": len(filtered),
                "row_count": len(result_rows),
                "transaction_count": len({str(row.get("transaction_id") or "") for row in filtered}),
                "total_amount": str(total_amount),
                "expense_amount": str(sum((Decimal(str(row.get("amount") or "0").replace(",", "")) for row in expense_rows), start=Decimal("0.00"))),
                "income_amount": str(sum((Decimal(str(row.get("amount") or "0").replace(",", "")) for row in income_rows), start=Decimal("0.00"))),
                "expense_transaction_count": len(expense_rows),
                "income_transaction_count": len(income_rows),
                "expense_type_count": len({str(row.get("expense_type") or "") for row in filtered}),
            }
        return {
            "summary": summary,
            "rows": page_rows,
            "next_offset": offset + len(page_rows) if len(page_rows) == page_size else None,
        }

    def get_cost_statistics_transaction(
        self,
        *,
        project_scope: str,
        transaction_id: str,
    ) -> dict[str, object] | None:
        view = self._stored_view(scope_key=f"{project_scope}:all")
        if not isinstance(view, dict):
            return None
        payload = view.get("payload")
        if not isinstance(payload, dict):
            return None
        for rows_key in ("time_rows", "bank_flow_time_rows"):
            for row in list(payload.get(rows_key) or []):
                if isinstance(row, dict) and row.get("transaction_id") == transaction_id:
                    return dict(row)
        return None


class _CostStatisticsQueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str, **_kwargs: object) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def read_model_refresh_is_active(self, **_kwargs: object) -> bool:
        return False


class CostStatisticsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = build_application()
        self.app._workbench_query_service = self.app._workbench_query_service.__class__(oa_adapter=_CostStatsOAAdapter())
        self.cost_repository = _MemoryCostStatisticsSqlRepository(
            lambda scope_key: _cost_statistics_gate_snapshot(self.app, scope_key),
        )
        self.app._cost_statistics_sql_read_repository = self.cost_repository

    def _install_queue_recorder(self) -> _CostStatisticsQueueRecorder:
        queue = _CostStatisticsQueueRecorder()
        self.app._runtime_repositories = replace(self.app._runtime_repositories, queue_repository=queue)
        return queue

    def _prime_cost_statistics_read_model(self, month: str = "2026-03", project_scope: str | None = None) -> None:
        if month != "all":
            bank_row = next(
                transaction
                for transaction in reversed(self.app._import_service.list_transactions())
                if str(transaction.txn_date or "").startswith(month)
            )
            _confirm_active_cost_relation(
                self.app,
                month=month,
                oa_row_id="oa-cost-api-001",
                bank_row_id=bank_row.id,
                case_id=f"CASE-COST-ACTIVE-{bank_row.id}",
            )
        project_scopes = [project_scope] if project_scope else ["active", "all"]
        months = [month]
        if month != "all":
            months.append("all")
        for scope in project_scopes:
            for target_month in months:
                payload = _project_cost_statistics_payload(self.app, target_month, scope)
                bank_flow_rows, bank_flow_summary = _canonical_bank_flow_projection(self.app, target_month)
                payload["bank_flow_time_rows"] = bank_flow_rows
                payload["bank_flow_summary"] = bank_flow_summary
                scope_key = self.cost_repository.scope_key(target_month, scope)
                self.cost_repository.upsert_read_model(
                    target_month,
                    scope,
                    payload,
                    generated_at="2026-07-05T00:00:00",
                    source_scope_keys=[target_month],
                    source_versions=_cost_statistics_gate_snapshot(self.app, scope_key)["source_versions"],
                    schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                    refresh_status="fresh",
                )

    def test_cost_statistics_explorer_cache_hit_does_not_rebuild(self) -> None:
        cached_payload = {
            "month": "2026-03",
            "summary": {"row_count": 1, "transaction_count": 1, "total_amount": "88.00"},
            "time_rows": [{"transaction_id": "cached-sentinel"}],
            "bank_accounts": [],
            "project_rows": [],
            "expense_type_rows": [],
        }
        self.cost_repository.upsert_read_model("2026-03", "active", cached_payload)

        response = self.app.handle_request("GET", "/api/cost-statistics/explorer?scope=2026-03&view=time")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["rows"][0]["transaction_id"], "cached-sentinel")

    def test_cost_statistics_route_owner_delegates_explorer_to_query_service(self) -> None:
        from fin_ops_platform.app.routes_cost_statistics import CostStatisticsApiRoutes
        from fin_ops_platform.app.server import Response

        calls: list[tuple[str, str, str]] = []

        class QueryService:
            def get_explorer_page(self, **kwargs: object):
                calls.append(("explorer", str(kwargs["scope"]), str(kwargs["project_scope"])))
                return {
                    "scope": kwargs["scope"],
                    "view": kwargs["view"],
                    "summary": {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"},
                    "available_years": [],
                    "facets": {},
                    "rows": [],
                    "row_count": 0,
                    "next_cursor": None,
                }, False, '"etag"', False

        routes = CostStatisticsApiRoutes(
            query_service=QueryService(),
            json_response=lambda status, payload, headers=None: Response(
                status_code=int(status), body=json.dumps(payload), headers=headers or {}
            ),
            file_response=lambda _filename, _content: Response(status_code=200, body=b""),
        )

        explorer_response = routes.route(
            "GET",
            "/api/cost-statistics/explorer",
            {"scope": ["2026-04"], "view": ["time"], "project_scope": ["all"]},
        )

        self.assertEqual(explorer_response.status_code, 200)
        self.assertEqual(calls, [("explorer", "2026-04", "all")])

    def test_cost_statistics_secondary_read_routes_delegate_to_query_service_and_fail_closed(self) -> None:
        from fin_ops_platform.app.routes_cost_statistics import CostStatisticsApiRoutes
        from fin_ops_platform.app.server import Response
        from fin_ops_platform.services.cost_statistics_query_service import CostStatisticsReadModelNotFreshError

        calls: list[tuple[str, object]] = []

        class QueryService:
            def get_export_preview(self, **kwargs: object) -> dict[str, object]:
                calls.append(("preview", kwargs.get("project_scope")))
                return {"view": kwargs.get("view"), "summary": {}, "rows": []}

            def export_view(self, **kwargs: object) -> tuple[str, bytes]:
                calls.append(("export", kwargs.get("project_scope")))
                return "cost.xlsx", b"xlsx"

            def get_transaction_detail(self, _transaction_id: str, *, project_scope: str) -> dict[str, object]:
                calls.append(("transaction", project_scope))
                raise CostStatisticsReadModelNotFreshError(
                    {
                        "read_model_status": "refreshing",
                        "read_model_scope_key": f"{project_scope}:all",
                        "read_model_stale_reasons": ["api_miss"],
                    },
                    message="成本统计数据正在刷新，请稍后重试。",
                )

        routes = CostStatisticsApiRoutes(
            query_service=QueryService(),
            json_response=lambda status, payload: Response(status_code=int(status), body=json.dumps(payload)),
            file_response=lambda filename, content: Response(status_code=200, body=content, headers={"X-Filename": filename}),
        )

        preview_response = routes.route(
            "GET",
            "/api/cost-statistics/export-preview",
            {"month": ["2026-03"], "view": ["time"], "project_scope": ["all"]},
        )
        export_response = routes.route(
            "GET",
            "/api/cost-statistics/export",
            {"month": ["2026-03"], "view": ["time"], "project_scope": ["all"]},
        )
        transaction_response = routes.route(
            "GET",
            "/api/cost-statistics/transactions/txn-1",
            {"project_scope": ["active"]},
        )

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(transaction_response.status_code, 409)
        transaction_payload = json.loads(transaction_response.body)
        self.assertEqual(transaction_payload["error"], "cost_statistics_read_model_not_fresh")
        self.assertEqual(
            calls,
            [
                ("preview", "all"),
                ("export", "all"),
                ("transaction", "active"),
            ],
        )

    def test_cost_statistics_explorer_reads_sql_read_model_and_logs_hit_metrics(self) -> None:
        cached_payload = {
            "month": "2026-03",
            "summary": {"row_count": 2, "transaction_count": 2, "total_amount": "120.00"},
            "time_rows": [{"transaction_id": "txn-1"}, {"transaction_id": "txn-2"}],
            "bank_accounts": [],
            "project_rows": [],
            "expense_type_rows": [],
        }
        scope_key = "active:2026-03"
        self.cost_repository.upsert_read_model(
            "2026-03",
            "active",
            cached_payload,
            generated_at="2026-07-05T00:00:00",
            source_versions=_cost_statistics_gate_snapshot(self.app, scope_key)["source_versions"],
        )

        with patch("builtins.print") as print_mock:
            first_response = self.app.handle_request("GET", "/api/cost-statistics/explorer?scope=2026-03&view=time")
            second_response = self.app.handle_request("GET", "/api/cost-statistics/explorer?scope=2026-03&view=time")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(json.loads(second_response.body)["rows"], cached_payload["time_rows"])
        metric_payloads = [
            json.loads(call.args[0])
            for call in print_mock.call_args_list
            if call.args and json.loads(call.args[0]).get("kind") == "cost_statistics_explorer_metric"
        ]
        self.assertEqual([payload["cache_hit"] for payload in metric_payloads], [False, False])
        self.assertEqual([payload["entry_count"] for payload in metric_payloads], [2, 2])

    def test_cost_statistics_explorer_miss_returns_refreshing_without_warmup_job(self) -> None:
        queue = self._install_queue_recorder()
        with (
            patch.object(self.app._background_job_service, "create_or_get_idempotent_job_with_created") as create_job,
            patch.object(self.app._background_job_service, "run_job") as run_job,
        ):
            response = self.app.handle_request("GET", "/api/cost-statistics/explorer?scope=2026-03&view=time")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_reason"], "api_page_miss")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["facets"]["projects"], [])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-03", "api_page_miss")])
        create_job.assert_not_called()
        run_job.assert_not_called()

    def test_cost_statistics_all_month_miss_returns_refreshing_without_warmup_job(self) -> None:
        queue = self._install_queue_recorder()
        with (
            patch.object(self.app._background_job_service, "create_or_get_idempotent_job_with_created") as create_job,
            patch.object(self.app._background_job_service, "run_job") as run_job,
        ):
            response = self.app.handle_request("GET", "/api/cost-statistics/explorer?scope=all&view=time&project_scope=active")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["scope"], "all")
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_reason"], "api_page_miss")
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:all", "api_page_miss")])
        create_job.assert_not_called()
        run_job.assert_not_called()

    def test_workbench_scope_invalidation_only_enqueues_durable_cost_refresh(self) -> None:
        queue = self._install_queue_recorder()
        repository = self.cost_repository
        for month in ("2026-03", "all"):
            for project_scope in ("active", "all"):
                repository.upsert_read_model(
                    month,
                    project_scope,
                    {
                        "month": month,
                        "summary": {"row_count": 1, "transaction_count": 1, "total_amount": "1.00"},
                        "time_rows": [{"transaction_id": f"{project_scope}-{month}"}],
                        "bank_accounts": [],
                        "project_rows": [],
                        "expense_type_rows": [],
                    },
                )

        with (
            patch.object(self.app._background_job_service, "create_or_get_idempotent_job_with_created") as create_job,
            patch.object(self.app._background_job_service, "run_job") as run_job,
        ):
            deleted_workbench_scopes = self.app._invalidate_workbench_read_model_scopes(["2026-03"])

        self.assertEqual(deleted_workbench_scopes, ["2026-03"])
        self.assertIsNotNone(repository.get_read_model("2026-03", "active"))
        self.assertIsNotNone(repository.get_read_model("2026-03", "all"))
        cost_refreshes = [refresh for refresh in queue.refreshes if refresh[0] == "cost_statistics"]
        self.assertEqual(
            cost_refreshes,
            [
                ("cost_statistics", "active:2026-03", "workbench_scope_invalidated"),
                ("cost_statistics", "all:2026-03", "workbench_scope_invalidated"),
            ],
        )
        create_job.assert_not_called()
        run_job.assert_not_called()

        for project_scope in ("active", "all"):
            repository.upsert_read_model(
                "all",
                project_scope,
                {
                    "month": "all",
                    "summary": {"row_count": 1, "transaction_count": 1, "total_amount": "1.00"},
                    "time_rows": [{"transaction_id": f"{project_scope}-all-rebuilt"}],
                    "bank_accounts": [],
                    "project_rows": [],
                    "expense_type_rows": [],
                },
            )
        queue.refreshes.clear()

        self.app._invalidate_workbench_read_model_scopes(["all"])

        self.assertIsNotNone(repository.get_read_model("all", "active"))
        self.assertIsNotNone(repository.get_read_model("all", "all"))
        cost_refreshes = [refresh for refresh in queue.refreshes if refresh[0] == "cost_statistics"]
        self.assertEqual(
            cost_refreshes,
            [
                ("cost_statistics", "active:all", "workbench_scope_invalidated"),
                ("cost_statistics", "all:all", "workbench_scope_invalidated"),
            ],
        )

    def test_get_cost_statistics_routes_return_expected_shapes(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-statistics.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)
        self._prime_cost_statistics_read_model()

        time_payload = json.loads(
            self.app.handle_request("GET", "/api/cost-statistics/explorer?scope=2026-03&view=time").body
        )
        self.assertEqual(time_payload["scope"], "2026-03")
        self.assertEqual(time_payload["summary"]["transaction_count"], 1)
        self.assertEqual(time_payload["rows"][0]["project_name"], "未配对OA")
        self.assertEqual(time_payload["rows"][0]["expense_type"], "未分类")
        self.assertEqual(time_payload["rows"][0]["expense_content"], "PLC 模块采购")
        transaction_id = time_payload["rows"][0]["transaction_id"]

        detail_payload = json.loads(
            self.app.handle_request("GET", f"/api/cost-statistics/transactions/{transaction_id}").body
        )
        self.assertEqual(detail_payload["transaction"]["id"], transaction_id)
        self.assertEqual(detail_payload["transaction"]["project_name"], "云南溯源科技")
        self.assertEqual(detail_payload["transaction"]["expense_type"], "设备货款及材料费")

        explorer_payload = json.loads(
            self.app.handle_request("GET", "/api/cost-statistics/explorer?scope=2026-03&view=project").body
        )
        self.assertEqual(explorer_payload["scope"], "2026-03")
        self.assertEqual(explorer_payload["summary"]["transaction_count"], 1)
        self.assertEqual(explorer_payload["rows"], [])
        self.assertEqual(explorer_payload["facets"]["projects"][0]["project_name"], "云南溯源科技")

    def test_project_scope_defaults_active_allows_all_and_rejects_invalid_scope(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-statistics-project-scope.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-SCOPE-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)
        settings_payload = self.app._app_settings_service.create_manual_project(
            actor_id="settings_test",
            project_code="LOCAL-COST-001",
            project_name="云南溯源科技",
        )
        completed_project_id = settings_payload["projects"]["active"][0]["id"]
        self.app._app_settings_service.update_settings(
            completed_project_ids=[completed_project_id],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
        )
        self._prime_cost_statistics_read_model("2026-03")

        default_payload = json.loads(
            self.app.handle_request("GET", "/api/cost-statistics/explorer?scope=2026-03&view=project").body
        )
        all_payload = json.loads(
            self.app.handle_request(
                "GET", "/api/cost-statistics/explorer?scope=2026-03&view=project&project_scope=all"
            ).body
        )
        preview_payload = json.loads(
            self.app.handle_request(
                "GET",
                "/api/cost-statistics/export-preview?month=2026-03&view=time&project_scope=all",
            ).body
        )
        invalid_response = self.app.handle_request(
            "GET",
            "/api/cost-statistics/explorer?scope=2026-03&view=time&project_scope=finished",
        )
        invalid_payload = json.loads(invalid_response.body)

        self.assertEqual(default_payload["summary"]["transaction_count"], 0)
        self.assertEqual(all_payload["summary"]["transaction_count"], 1)
        self.assertEqual(preview_payload["summary"]["transaction_count"], 1)
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_payload["error"], "invalid_cost_statistics_project_scope")

    def test_cost_statistics_export_returns_xlsx_for_each_view(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)
        self._prime_cost_statistics_read_model()

        month_response = self.app.handle_request("GET", "/api/cost-statistics/export?month=2026-03&view=month")
        self.assertEqual(month_response.status_code, 200)
        self.assertEqual(
            month_response.headers["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("filename*=", month_response.headers["Content-Disposition"])
        self.assertIn("%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03_%E6%9C%88%E4%BB%BD%E6%B1%87%E6%80%BB.xlsx", month_response.headers["Content-Disposition"])
        self.assertIsInstance(month_response.headers["Content-Disposition"].encode("latin-1"), bytes)
        month_workbook = load_workbook(BytesIO(month_response.body))
        month_sheet = month_workbook.active
        self.assertEqual(month_sheet.title, "月份汇总")
        self.assertEqual(month_sheet["A2"].value, "云南溯源科技")
        self.assertEqual(month_sheet["B2"].value, "设备货款及材料费")

        project_name = quote("云南溯源科技", safe="")
        project_response = self.app.handle_request(
            "GET",
            f"/api/cost-statistics/export?month=2026-03&view=project&project_name={project_name}",
        )
        self.assertEqual(project_response.status_code, 200)
        self.assertIn("filename*=", project_response.headers["Content-Disposition"])
        self.assertIn(
            "%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03_%E9%A1%B9%E7%9B%AE%E6%98%8E%E7%BB%86_%E4%BA%91%E5%8D%97%E6%BA%AF%E6%BA%90%E7%A7%91%E6%8A%80.xlsx",
            project_response.headers["Content-Disposition"],
        )
        project_workbook = load_workbook(BytesIO(project_response.body))
        self.assertEqual(
            project_workbook.sheetnames,
            [
                "导出说明",
                "项目汇总",
                "按费用类型汇总",
                "按费用内容汇总",
                "流水明细",
                "OA关联明细",
                "发票关联明细",
                "异常与未闭环",
            ],
        )
        summary_sheet = project_workbook["项目汇总"]
        self.assertEqual(summary_sheet["A2"].value, "项目名称")
        self.assertEqual(summary_sheet["B2"].value, "云南溯源科技")
        transaction_sheet = project_workbook["流水明细"]
        self.assertEqual(transaction_sheet["A2"].value, "2026-03-10 21:27:55")
        self.assertEqual(transaction_sheet["B2"].value, "txn_imported_0001")
        self.assertEqual(transaction_sheet["H2"].value, "云南溯源科技")
        self.assertEqual(transaction_sheet["I2"].value, "设备货款及材料费")

        transaction_response = self.app.handle_request(
            "GET",
            "/api/cost-statistics/export?month=2026-03&view=transaction&transaction_id=txn_imported_0001",
        )
        self.assertEqual(transaction_response.status_code, 200)
        self.assertIn("filename*=", transaction_response.headers["Content-Disposition"])
        transaction_workbook = load_workbook(BytesIO(transaction_response.body))
        detail_sheet = transaction_workbook.active
        self.assertEqual(detail_sheet.title, "流水详情")
        self.assertEqual(detail_sheet["A2"].value, "交易ID")
        self.assertEqual(detail_sheet["B2"].value, "txn_imported_0001")

        time_response = self.app.handle_request("GET", "/api/cost-statistics/export?month=2026-03&view=time")
        self.assertEqual(time_response.status_code, 200)
        self.assertIn("filename*=", time_response.headers["Content-Disposition"])
        self.assertIn("%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03_%E6%8C%89%E6%97%B6%E9%97%B4%E7%BB%9F%E8%AE%A1.xlsx", time_response.headers["Content-Disposition"])
        time_workbook = load_workbook(BytesIO(time_response.body))
        time_sheet = time_workbook.active
        self.assertEqual(time_sheet.title, "按时间统计")
        self.assertEqual(time_sheet["A2"].value, "2026-03-10 21:27:55")
        self.assertEqual(time_sheet["B2"].value, "未配对OA")

        bank_tag_response = self.app.handle_request(
            "GET",
            "/api/cost-statistics/export?month=2026-03&view=bank_tag",
        )
        self.assertEqual(bank_tag_response.status_code, 200)
        self.assertIn(
            "%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03_%E6%8C%89%E6%A0%87%E7%AD%BE%E7%BB%9F%E8%AE%A1.xlsx",
            bank_tag_response.headers["Content-Disposition"],
        )
        bank_tag_sheet = load_workbook(BytesIO(bank_tag_response.body)).active
        self.assertEqual(bank_tag_sheet.title, "按标签统计")
        self.assertEqual(bank_tag_sheet["B1"].value, "主标签")
        self.assertEqual(bank_tag_sheet["D1"].value, "资金方向")

        expense_type = quote("设备货款及材料费", safe="")
        expense_response = self.app.handle_request(
            "GET",
            f"/api/cost-statistics/export?month=2026-03&view=expense_type&expense_type={expense_type}",
        )
        self.assertEqual(expense_response.status_code, 200)
        self.assertIn("filename*=", expense_response.headers["Content-Disposition"])
        expense_workbook = load_workbook(BytesIO(expense_response.body))
        expense_sheet = expense_workbook.active
        self.assertEqual(expense_sheet.title, "按费用类型统计")
        self.assertEqual(expense_sheet["A2"].value, "2026-03-10 21:27:55")
        self.assertEqual(expense_sheet["B2"].value, "云南溯源科技")

    def test_cost_statistics_export_limit_returns_structured_error(self) -> None:
        from fin_ops_platform.app.routes_cost_statistics import CostStatisticsApiRoutes
        from fin_ops_platform.app.server import Response
        from fin_ops_platform.services.cost_statistics_query_service import (
            COST_STATISTICS_EXPORT_ROW_LIMIT,
            CostStatisticsExportLimitError,
        )

        class ExportLimitQueryService:
            def get_export_preview(self, **_kwargs: object) -> dict[str, object]:
                raise CostStatisticsExportLimitError(view="time", total=COST_STATISTICS_EXPORT_ROW_LIMIT + 1)

            def export_view(self, **_kwargs: object) -> tuple[str, bytes]:
                raise CostStatisticsExportLimitError(view="time", total=COST_STATISTICS_EXPORT_ROW_LIMIT + 1)

        routes = CostStatisticsApiRoutes(
            query_service=ExportLimitQueryService(),
            json_response=lambda status, payload: Response(status_code=int(status), body=json.dumps(payload)),
            file_response=lambda _filename, _content: Response(status_code=200, body=b""),
        )

        preview_response = routes.route(
            "GET",
            "/api/cost-statistics/export-preview",
            {"month": ["2026-03"], "view": ["time"]},
        )
        export_response = routes.route(
            "GET",
            "/api/cost-statistics/export",
            {"month": ["2026-03"], "view": ["time"]},
        )

        expected_details = {
            "view": "time",
            "total": COST_STATISTICS_EXPORT_ROW_LIMIT + 1,
            "limit": COST_STATISTICS_EXPORT_ROW_LIMIT,
        }
        preview_payload = json.loads(preview_response.body)
        export_payload = json.loads(export_response.body)
        self.assertEqual(preview_response.status_code, 400)
        self.assertEqual(export_response.status_code, 400)
        self.assertEqual(preview_payload["error"], "cost_statistics_export_row_limit_exceeded")
        self.assertEqual(export_payload["error"], "cost_statistics_export_row_limit_exceeded")
        self.assertEqual(preview_payload["details"], expected_details)
        self.assertEqual(export_payload["details"], expected_details)

    def test_cost_statistics_tag_rules_route_reads_and_saves_selection_without_read_model_barrier(self) -> None:
        from fin_ops_platform.app.routes_cost_statistics import CostStatisticsApiRoutes
        from fin_ops_platform.app.server import Response

        class SettingsService:
            def __init__(self) -> None:
                self.saved_payload: dict[str, object] | None = None

            def get_cost_statistics_tag_selection_payload(self, *, can_save: bool = True) -> dict[str, object]:
                return {
                    "version": 3,
                    "bank_auto_tag_rules_version": 8,
                    "selected_tag_codes": ["fee", "__uncategorized__"],
                    "effective_selected_tag_codes": ["fee", "__uncategorized__"],
                    "inactive_selected_tag_codes": [],
                    "active_tags": [
                        {"code": "fee", "label": "费用", "path": ["费用", "材料"]},
                        {"code": "__uncategorized__", "label": "未分类", "path": ["未分类", "未分类"]},
                    ],
                    "can_save": can_save,
                }

            def update_cost_statistics_tag_selection(self, payload: dict[str, object], *, actor_id: str) -> dict[str, object]:
                self.saved_payload = {**payload, "actor_id": actor_id}
                return {
                    **self.get_cost_statistics_tag_selection_payload(can_save=True),
                    "version": 4,
                    "selected_tag_codes": list(payload.get("selected_tag_codes") or []),
                    "effective_selected_tag_codes": list(payload.get("selected_tag_codes") or []),
                }

        settings = SettingsService()
        routes = CostStatisticsApiRoutes(
            query_service=object(),
            app_settings_service=settings,
            json_response=lambda status, payload: Response(status_code=int(status), body=json.dumps(payload)),
            file_response=lambda _filename, _content: Response(status_code=200, body=b""),
            resolve_read_session=lambda _headers: (None, None),
            resolve_write_session=lambda _headers: (None, None),
            load_json_body=lambda body: (json.loads(body or "{}"), None),
        )

        get_response = routes.route("GET", "/api/cost-statistics/tag-rules", {}, None, {})
        put_response = routes.route(
            "PUT",
            "/api/cost-statistics/tag-rules",
            {},
            json.dumps({
                "expected_version": 3,
                "selected_tag_codes": ["fee"],
            }),
            {},
        )

        get_payload = json.loads(get_response.body)
        put_payload = json.loads(put_response.body)
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_payload["active_tags"][1]["label"], "未分类")
        self.assertEqual(put_response.status_code, 200)
        self.assertEqual(settings.saved_payload["selected_tag_codes"], ["fee"])
        self.assertEqual(put_payload["selected_tag_codes"], ["fee"])
        self.assertNotIn("operation_barrier_targets", put_payload)
        self.assertNotIn("freshness_targets", put_payload)

    def test_cost_statistics_tag_rules_update_rejects_missing_write_permission(self) -> None:
        from fin_ops_platform.app.routes_cost_statistics import CostStatisticsApiRoutes
        from fin_ops_platform.app.server import Response

        class SettingsService:
            called = False

            def update_cost_statistics_tag_selection(self, _payload: dict[str, object], *, actor_id: str) -> dict[str, object]:
                self.called = True
                return {}

        settings = SettingsService()
        permission_error = Response(
            status_code=403,
            body=json.dumps({
                "error": "forbidden",
                "message": "当前账户没有保存成本统计标签规则权限。",
            }),
        )
        routes = CostStatisticsApiRoutes(
            query_service=object(),
            app_settings_service=settings,
            json_response=lambda status, payload: Response(status_code=int(status), body=json.dumps(payload)),
            file_response=lambda _filename, _content: Response(status_code=200, body=b""),
            resolve_write_session=lambda _headers: (None, permission_error),
            load_json_body=lambda body: (json.loads(body or "{}"), None),
        )

        response = routes.route(
            "PUT",
            "/api/cost-statistics/tag-rules",
            {},
            json.dumps({"selected_tag_codes": ["fee"]}),
            {},
        )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "forbidden")
        self.assertFalse(settings.called)

    def test_project_export_honors_advanced_export_options(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export-advanced.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-ADV-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)
        self._prime_cost_statistics_read_model()

        project_name = quote("云南溯源科技", safe="")
        response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export"
                "?month=all"
                "&view=project"
                f"&project_name={project_name}"
                "&start_month=2026-03"
                "&end_month=2026-04"
                "&include_oa_details=false"
                "&include_invoice_details=false"
                "&include_exception_rows=false"
                "&include_ignored_rows=false"
                "&include_expense_content_summary=false"
                "&sort_by=amount_desc"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("filename*=", response.headers["Content-Disposition"])
        self.assertIn(
            "%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03%E8%87%B32026-04_%E9%A1%B9%E7%9B%AE%E6%98%8E%E7%BB%86_%E4%BA%91%E5%8D%97%E6%BA%AF%E6%BA%90%E7%A7%91%E6%8A%80.xlsx",
            response.headers["Content-Disposition"],
        )
        workbook = load_workbook(BytesIO(response.body))
        self.assertEqual(
            workbook.sheetnames,
            [
                "导出说明",
                "项目汇总",
                "按费用类型汇总",
                "流水明细",
            ],
        )

    def test_cost_statistics_export_preview_supports_filtered_views(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export-preview.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-PREVIEW-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)
        self._prime_cost_statistics_read_model()

        project_name = quote("云南溯源科技", safe="")
        preview_response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export-preview"
                "?month=all"
                "&view=project"
                f"&project_name={project_name}"
                f"&expense_type={quote('设备货款及材料费', safe='')}"
            ),
        )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["view"], "project")
        self.assertEqual(preview_payload["summary"]["transaction_count"], 1)
        self.assertIn("项目汇总", preview_payload["sheet_names"])
        self.assertEqual(preview_payload["columns"][0], "时间")
        self.assertEqual(preview_payload["rows"][0][0], "2026-03-10 21:27:55")

        expense_preview_response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export-preview"
                "?month=all"
                "&view=expense_type"
                "&start_month=2026-03"
                "&end_month=2026-04"
                f"&expense_type={quote('设备货款及材料费', safe='')}"
            ),
        )
        self.assertEqual(expense_preview_response.status_code, 200)
        expense_preview_payload = json.loads(expense_preview_response.body)
        self.assertEqual(expense_preview_payload["view"], "expense_type")
        self.assertEqual(expense_preview_payload["sheet_names"], ["按费用类型统计"])

    def test_cost_statistics_export_preview_and_export_support_exact_date_range(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export-date-range.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-DATE-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)
        self._prime_cost_statistics_read_model()

        preview_response = self.app.handle_request(
            "GET",
            "/api/cost-statistics/export-preview?month=all&view=time&start_date=2026-03-10&end_date=2026-03-10",
        )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["scope_label"], "2026-03-10至2026-03-10")
        self.assertEqual(preview_payload["summary"]["transaction_count"], 1)
        self.assertEqual(preview_payload["rows"][0][0], "2026-03-10 21:27:55")

        export_response = self.app.handle_request(
            "GET",
            "/api/cost-statistics/export?month=all&view=time&start_date=2026-03-10&end_date=2026-03-10",
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertIn(
            "%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03-10%E8%87%B32026-03-10_%E6%8C%89%E6%97%B6%E9%97%B4%E7%BB%9F%E8%AE%A1.xlsx",
            export_response.headers["Content-Disposition"],
        )

    def test_export_filters_project_and_expense_type_views_by_expense_types(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export-filtered.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-FILTER-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)
        self._prime_cost_statistics_read_model()

        project_name = quote("云南溯源科技", safe="")
        expense_type = quote("设备货款及材料费", safe="")
        project_response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export"
                "?month=all"
                "&view=project"
                f"&project_name={project_name}"
                f"&expense_type={expense_type}"
            ),
        )
        self.assertEqual(project_response.status_code, 200)
        project_workbook = load_workbook(BytesIO(project_response.body))
        project_transaction_sheet = project_workbook["流水明细"]
        self.assertEqual(project_transaction_sheet.max_row, 2)
        self.assertEqual(project_transaction_sheet["I2"].value, "设备货款及材料费")

        expense_response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export"
                "?month=all"
                "&view=expense_type"
                "&start_month=2026-03"
                "&end_month=2026-04"
                f"&expense_type={expense_type}"
            ),
        )
        self.assertEqual(expense_response.status_code, 200)
        expense_workbook = load_workbook(BytesIO(expense_response.body))
        expense_sheet = expense_workbook.active
        self.assertEqual(expense_sheet.title, "按费用类型统计")
        self.assertEqual(expense_sheet.max_row, 2)
        self.assertEqual(expense_sheet["D2"].value, "PLC 模块采购")

    def test_cost_statistics_uses_oa_detail_fields_after_manual_confirm_link(self) -> None:
        app = build_application()
        app._workbench_query_service = app._workbench_query_service.__class__(oa_adapter=_FallbackCostStatsOAAdapter())
        cost_repository = _MemoryCostStatisticsSqlRepository(
            lambda scope_key: _cost_statistics_gate_snapshot(app, scope_key),
        )
        app._cost_statistics_sql_read_repository = cost_repository

        _confirm_active_cost_relation(
            app,
            month="2026-03",
            oa_row_id="oa-cost-fallback-001",
            bank_row_id="bk-o-202603-001",
            case_id="CASE-COST-FALLBACK",
        )

        cost_repository.upsert_read_model(
            "2026-03",
            "active",
            _project_cost_statistics_payload(app, "2026-03", "active"),
            generated_at="2026-07-05T00:00:00",
            source_versions=_cost_statistics_gate_snapshot(app, "active:2026-03")["source_versions"],
        )
        project_name = quote("云南溯源科技", safe="")
        expense_type = quote("设备货款及材料费", safe="")
        payload = json.loads(
            app.handle_request(
                "GET",
                (
                    "/api/cost-statistics/explorer?scope=2026-03&view=project"
                    f"&project_name={project_name}&expense_type={expense_type}"
                ),
            ).body
        )
        self.assertEqual(payload["row_count"], 1)
        self.assertEqual(payload["rows"][0]["project_name"], "云南溯源科技")
        self.assertEqual(payload["rows"][0]["expense_type"], "设备货款及材料费")
        self.assertEqual(payload["rows"][0]["expense_content"], "PLC 模块采购")


if __name__ == "__main__":
    unittest.main()
