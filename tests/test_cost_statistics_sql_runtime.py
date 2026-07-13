from __future__ import annotations

import json
import unittest
from http import HTTPStatus

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.cost_statistics_read_model_refresh import CostStatisticsReadModelRefreshService
from fin_ops_platform.services.cost_statistics_read_model_repository import CostStatisticsReadModelRepositoryPort
from fin_ops_platform.services.cost_statistics_read_model_service import COST_STATISTICS_READ_MODEL_SCHEMA_VERSION
from fin_ops_platform.services.cost_statistics_query_service import CostStatisticsQueryService
from fin_ops_platform.services.cost_tax_sql_projection import CostStatisticsSqlProjectionBuilder
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> None:
        self.completed.append((tenant_id, scope_type, scope_key))


class RedisRecorder:
    def __init__(self, value: dict | None = None) -> None:
        self.value = value
        self.gets: list[str] = []
        self.sets: list[tuple[str, dict, int]] = []
        self.deletes: list[str] = []

    def get_json(self, key: str) -> dict | None:
        self.gets.append(key)
        return self.value

    def set_json(self, key: str, value: dict, *, ttl_seconds: int) -> bool:
        self.sets.append((key, value, ttl_seconds))
        return True

    def delete(self, key: str) -> bool:
        self.deletes.append(key)
        return True


class CostStatisticsAppSettingsStub:
    def get_bank_auto_tag_rules_payload(self, **_kwargs: object) -> dict[str, object]:
        return {"version": 7, "active_rules": []}

    def get_bank_account_mappings_payload(self) -> list[dict[str, str]]:
        return [{"bank_name": "工商银行", "last4": "0001", "id": "bank_mapping_0001", "short_name": ""}]

    def get_cost_statistics_source_settings_payload(self) -> dict[str, object]:
        return {
            "bank_transaction_tags": {"version": 7, "active_rules": []},
            "bank_account_mappings": self.get_bank_account_mappings_payload(),
        }

    def get_cost_statistics_tag_selection_payload(self, *, can_save: bool = False) -> dict[str, object]:
        del can_save
        return {
            "version": 1,
            "bank_auto_tag_rules_version": 7,
            "effective_selected_tag_codes": None,
            "selected_tag_codes": None,
        }


class CostStatisticsRuntimeStub:
    def request_scope_key(self, month: str, project_scope: str) -> str:
        return f"{project_scope}:{month}"

    def expected_source_versions(self, scope_key: str) -> dict[str, object]:
        return {"scope_key": scope_key, "schema": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION}

    def redis_cache_key(self, scope_key: str, *, source_versions: dict[str, object]) -> str:
        return f"explorer:{scope_key}:{json.dumps(source_versions, sort_keys=True)}"

    def month_redis_cache_key(self, scope_key: str, *, source_versions: dict[str, object]) -> str:
        return f"month:{scope_key}:{json.dumps(source_versions, sort_keys=True)}"

    def redis_ttl_seconds(self) -> int:
        return 120

    def enqueue_read_model_refresh(self, scope_key: str, *, reason: str) -> bool:
        del scope_key, reason
        return True


class CostStatisticsSqlReadRepositoryStub:
    def __init__(self, payload: dict[str, object], source_versions: dict[str, object]) -> None:
        self.payload = payload
        self.source_versions = source_versions

    def get_cost_statistics_view(self, *, scope_key: str) -> dict[str, object]:
        return {
            "scope_key": scope_key,
            "payload": self.payload,
            "refresh_status": "fresh",
            "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            "generated_at": "2026-05-21T09:00:00+00:00",
            "source_versions": self.source_versions,
        }


def redis_fresh_payload(
    payload: dict[str, object],
    *,
    scope_key: str,
    source_versions: dict[str, object],
) -> dict[str, object]:
    cached_payload = dict(payload)
    cached_payload["read_model_status"] = "fresh"
    cached_payload["read_model_scope_key"] = scope_key
    cached_payload["read_model_schema_version"] = COST_STATISTICS_READ_MODEL_SCHEMA_VERSION
    cached_payload["source_versions"] = dict(source_versions)
    return {
        "payload": cached_payload,
        "fresh_gate": {
            "scope_key": scope_key,
            "read_model_status": "fresh",
            "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            "source_versions": dict(source_versions),
        },
    }


class CostStatisticsQueryServiceTagFilterTests(unittest.TestCase):
    def test_tag_rules_filter_oa_and_bank_flow_totals_with_separate_contracts(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        source_versions = runtime.expected_source_versions("active:2026-05")
        payload = {
            "month": "2026-05",
            "summary": {"row_count": 2, "transaction_count": 2, "total_amount": "130.00"},
            "time_rows": [
                {
                    "transaction_id": "oa-fee",
                    "trade_time": "2026-05-21 09:00:00",
                    "direction": "支出",
                    "project_name": "项目A",
                    "expense_type": "材料",
                    "expense_content": "钢材",
                    "amount": "100.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "fee",
                    "bank_tag_label": "费用",
                    "bank_tag_primary_label": "费用",
                    "bank_tag_sub_label": "材料",
                    "bank_tag_label_path": ["费用", "材料"],
                },
                {
                    "transaction_id": "oa-travel",
                    "trade_time": "2026-05-22 09:00:00",
                    "direction": "支出",
                    "project_name": "项目B",
                    "expense_type": "交通",
                    "expense_content": "打车",
                    "amount": "30.00",
                    "counterparty_name": "司机",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "travel",
                    "bank_tag_label": "交通",
                    "bank_tag_primary_label": "差旅",
                    "bank_tag_sub_label": "交通",
                    "bank_tag_label_path": ["差旅", "交通"],
                },
            ],
            "bank_flow_summary": {"row_count": 4, "transaction_count": 4, "total_amount": "355.00"},
            "bank_flow_time_rows": [
                {
                    "transaction_id": "oa-fee",
                    "trade_time": "2026-05-21 09:00:00",
                    "direction": "支出",
                    "project_name": "项目A",
                    "expense_type": "材料",
                    "expense_content": "钢材",
                    "amount": "100.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "fee",
                    "bank_tag_label": "费用",
                    "bank_tag_primary_label": "费用",
                    "bank_tag_sub_label": "材料",
                    "bank_tag_label_path": ["费用", "材料"],
                },
                {
                    "transaction_id": "flow-fee",
                    "trade_time": "2026-05-23 09:00:00",
                    "direction": "支出",
                    "project_name": "未配对OA",
                    "expense_type": "材料",
                    "expense_content": "耗材",
                    "amount": "50.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "fee",
                    "bank_tag_label": "费用",
                    "bank_tag_primary_label": "费用",
                    "bank_tag_sub_label": "材料",
                    "bank_tag_label_path": ["费用", "材料"],
                },
                {
                    "transaction_id": "flow-uncategorized",
                    "trade_time": "2026-05-24 09:00:00",
                    "direction": "支出",
                    "project_name": "未配对OA",
                    "expense_type": "未分类",
                    "expense_content": "其他",
                    "amount": "5.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "",
                    "bank_tag_label": "未标记",
                    "bank_tag_primary_label": "未标记",
                    "bank_tag_sub_label": "未标记",
                    "bank_tag_label_path": ["未标记"],
                },
                {
                    "transaction_id": "income-fee",
                    "trade_time": "2026-05-25 09:00:00",
                    "direction": "收入",
                    "project_name": "未配对OA",
                    "expense_type": "材料",
                    "expense_content": "退款",
                    "amount": "200.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "fee",
                    "bank_tag_label": "费用",
                    "bank_tag_primary_label": "费用",
                    "bank_tag_sub_label": "材料",
                    "bank_tag_label_path": ["费用", "材料"],
                },
            ],
            "bank_accounts": [],
            "project_rows": [],
            "expense_type_rows": [],
        }
        provider = type(
            "Provider",
            (),
            {
                "get_cost_statistics_tag_selection_payload": lambda self, *, can_save=False: {
                    "version": 2,
                    "bank_auto_tag_rules_version": 7,
                    "effective_selected_tag_codes": ["fee"],
                    "selected_tag_codes": ["fee"],
                }
            },
        )()
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=CostStatisticsSqlReadRepositoryStub(payload, source_versions),
            tag_selection_provider=provider,
        )

        explorer, _cache_hit = service.get_explorer("2026-05", "active")

        self.assertEqual([row["transaction_id"] for row in explorer["time_rows"]], ["oa-fee"])
        self.assertEqual(explorer["summary"]["total_amount"], "100.00")
        self.assertEqual(explorer["project_rows"][0]["total_amount"], "100.00")
        self.assertEqual(explorer["expense_type_rows"][0]["total_amount"], "100.00")
        self.assertEqual(
            [row["transaction_id"] for row in explorer["bank_flow_time_rows"]],
            ["oa-fee", "flow-fee", "income-fee"],
        )
        self.assertEqual(explorer["bank_flow_summary"]["expense_amount"], "150.00")
        self.assertEqual(explorer["bank_flow_summary"]["income_amount"], "200.00")
        self.assertEqual(explorer["bank_flow_summary"]["expense_transaction_count"], 2)
        self.assertEqual(explorer["bank_flow_summary"]["income_transaction_count"], 1)
        detail_source_versions = runtime.expected_source_versions("active:all")
        detail_service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=CostStatisticsSqlReadRepositoryStub(payload, detail_source_versions),
            tag_selection_provider=provider,
        )
        income_detail = detail_service.get_transaction_detail("income-fee", project_scope="active")
        self.assertEqual(income_detail["transaction"]["direction"], "收入")
        self.assertEqual(income_detail["transaction"]["amount"], "200.00")


class CostStatisticsReadConnection:
    def __init__(self, *, read_model_row: dict | None = None, cost_rows: list[dict] | None = None, dirty: bool = False) -> None:
        self.read_model_row = read_model_row
        self.cost_rows = list(cost_rows or [])
        self.dirty = dirty
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.cost_statistics_read_models" in normalized:
            return self.read_model_row
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-21T09:00:00+00:00"} if self.dirty else None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.cost_statistics_rows" in normalized:
            return self.cost_rows
        return []


class CostStatisticsWriteConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> int:
        normalized = " ".join(sql.lower().split())
        self.executed.append((normalized, params))
        if "insert into read_model.cost_statistics_rows" in normalized and params[2] is None:
            raise AssertionError("parent cost statistics scope must not write rows with null scope_month")
        return 1


class CostStatisticsProjectionConnection:
    def __init__(self, *, include_open_candidate: bool = False) -> None:
        self.include_open_candidate = include_open_candidate
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "read_model.workbench_groups" in normalized:
            rows = [
                {
                    "group_id": "group-1",
                    "zone": "paired",
                    "payload": {
                        "group_id": "group-1",
                        "group_type": "manual_confirmed",
                        "relation_status": "linked",
                        "workbench_group_rows_materialized": True,
                    },
                    "raw_payload": {},
                    "pane": "oa",
                    "row_id": "oa-1",
                    "row_role": "normal",
                    "row_index": 0,
                    "row_payload": {
                        "id": "oa-1",
                        "type": "oa",
                        "project_name": "项目A",
                        "project_id": "P-A",
                        "expense_type": "材料",
                        "expense_content": "钢材",
                        "applicant": "张三",
                    },
                    "member_payload": {"row_id": "oa-1", "type": "oa"},
                },
                {
                    "group_id": "group-1",
                    "zone": "paired",
                    "payload": {
                        "group_id": "group-1",
                        "group_type": "manual_confirmed",
                        "relation_status": "linked",
                        "workbench_group_rows_materialized": True,
                    },
                    "raw_payload": {},
                    "pane": "bank",
                    "row_id": "bank-1",
                    "row_role": "normal",
                    "row_index": 1,
                    "row_payload": {
                        "id": "bank-1",
                        "type": "bank",
                        "trade_time": "2026-05-02 10:00:00",
                        "counterparty_name": "供应商A",
                        "payment_account_label": "建行",
                        "direction": "支出",
                        "remark": "采购",
                        "amount": "10.00",
                    },
                    "member_payload": {"row_id": "bank-1", "type": "bank"},
                }
            ]
            if self.include_open_candidate:
                rows.extend(
                    [
                        {
                            "group_id": "group-candidate",
                            "zone": "open",
                            "payload": {
                                "group_id": "group-candidate",
                                "group_type": "candidate",
                                "relation_status": "candidate",
                                "reason": "attached_unique_candidate",
                                "workbench_group_rows_materialized": True,
                            },
                            "raw_payload": {},
                            "pane": "oa",
                            "row_id": "oa-candidate",
                            "row_role": "normal",
                            "row_index": 0,
                            "row_payload": {
                                "id": "oa-candidate",
                                "type": "oa",
                                "project_name": "项目A",
                                "project_id": "P-A",
                                "expense_type": "材料",
                                "expense_content": "候选材料",
                                "applicant": "李四",
                            },
                            "member_payload": {"row_id": "oa-candidate", "type": "oa"},
                        },
                        {
                            "group_id": "group-candidate",
                            "zone": "open",
                            "payload": {
                                "group_id": "group-candidate",
                                "group_type": "candidate",
                                "relation_status": "candidate",
                                "reason": "attached_unique_candidate",
                                "workbench_group_rows_materialized": True,
                            },
                            "raw_payload": {},
                            "pane": "bank",
                            "row_id": "bank-candidate",
                            "row_role": "normal",
                            "row_index": 1,
                            "row_payload": {
                                "id": "bank-candidate",
                                "type": "bank",
                                "trade_time": "2026-05-03 10:00:00",
                                "counterparty_name": "候选供应商",
                                "payment_account_label": "建行",
                                "direction": "支出",
                                "remark": "候选采购",
                                "amount": "999.00",
                                "available_actions": ["detail", "view_relation", "cancel_link"],
                            },
                            "member_payload": {"row_id": "bank-candidate", "type": "bank"},
                        },
                    ]
                )
            return rows
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_account_mappings": [
                        {"bank_name": "工商银行", "last4": "0001"},
                        {"bank_name": "民生银行", "last4": "9486"},
                    ],
                    "projects": [{"name": "项目A", "active": True}],
                    "bank_transaction_tags": {"version": 7},
                }
            }
        return None


class CostStatisticsBankTagFacade:
    def __init__(self, *, status: str = "fresh") -> None:
        self.status = status
        self.source_version_calls: list[tuple[list[str], dict[str, object]]] = []
        self.category_calls: list[tuple[list[str], dict[str, object]]] = []
        self.month_calls: list[tuple[str, dict[str, object]]] = []

    def source_versions_for_scope_keys(self, scope_keys: list[str], **kwargs: object) -> dict[str, object]:
        self.source_version_calls.append((list(scope_keys), dict(kwargs)))
        return {
            "status": self.status,
            "source_versions": {"bank_detail_scope_version": "bank-detail-v2"},
            "scope_keys": list(scope_keys),
        }

    def category_records_by_transaction_ids(self, transaction_ids: list[str], **kwargs: object) -> dict[str, dict[str, object]]:
        self.category_calls.append((list(transaction_ids), dict(kwargs)))
        if self.status != "fresh":
            raise RuntimeError("bank_detail_read_model_not_fresh")
        return {
            "bank-1": {
                "effective_category_code": "project_material",
                "effective_category_label": "设备材料",
                "effective_category_primary_label": "项目开销",
                "effective_category_sub_label": "设备材料",
                "effective_category_label_path": ["项目开销", "设备材料"],
            }
        }

    def list_by_month(self, month: str, **kwargs: object) -> dict[str, object]:
        self.month_calls.append((month, dict(kwargs)))
        return {
            "status": self.status,
            "rows": [
                {
                    "transaction_id": "bank-expense",
                    "trade_time": "2026-05-04 10:00:00",
                    "direction": "expense",
                    "amount": "20.00",
                    "counterparty_name": "供应商",
                    "bank_name": "工商银行",
                    "account_last4": "0001",
                    "summary": "采购",
                    "effective_category_code": "project_material",
                    "effective_category_label": "设备材料",
                },
                {
                    "transaction_id": "bank-income",
                    "trade_time": "2026-05-05 10:00:00",
                    "direction": "income",
                    "amount": "30.00",
                    "counterparty_name": "客户",
                    "bank_name": "工商银行",
                    "account_last4": "0001",
                    "summary": "回款",
                    "effective_category_code": "project_collection",
                    "effective_category_label": "项目回款",
                },
            ],
        }


class CostStatisticsParentAggregationConnection:
    def __init__(self, *, missing_or_stale_shards: list[str] | None = None) -> None:
        self.missing_or_stale_shards = list(missing_or_stale_shards or [])
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_groups" in normalized:
            raise RuntimeError("parent rebuild must not read workbench all payload")
        if "from read_model.cost_statistics_rows" in normalized:
            return [
                {
                    "scope_key": "active:2026-05",
                    "project_scope": "active",
                    "scope_month": "2026-05-01",
                    "row_key": "txn-1:0",
                    "transaction_id": "txn-1",
                    "group_id": "group-1",
                    "trade_time_text": "2026-05-02 10:00:00",
                    "trade_date": "2026-05-02",
                    "counterparty_name": "供应商A",
                    "payment_account_label": "建行",
                    "direction": "支出",
                    "remark": "采购",
                    "project_id": "P-A",
                    "project_name": "项目A",
                    "expense_type": "材料",
                    "expense_content": "钢材",
                    "amount": "10.00",
                    "oa_applicant": "张三",
                    "source_versions": {"scope": "active:2026-05"},
                    "generated_at": "2026-06-04T10:00:00+00:00",
                    "cache_status": "fresh",
                    "payload": {
                        "transaction_id": "txn-1",
                        "group_id": "group-1",
                        "trade_time": "2026-05-02 10:00:00",
                        "direction": "支出",
                        "project_name": "项目A",
                        "project_id": "P-A",
                        "expense_type": "材料",
                        "expense_content": "钢材",
                        "amount": "10.00",
                        "counterparty_name": "供应商A",
                        "payment_account_label": "建行",
                        "remark": "采购",
                        "oa_applicant": "张三",
                        "bank_tag_code": "project_material",
                        "bank_tag_label": "设备材料",
                        "bank_tag_primary_label": "项目开销",
                        "bank_tag_sub_label": "设备材料",
                        "bank_tag_label_path": ["项目开销", "设备材料"],
                    },
                    "raw_payload": {},
                },
                {
                    "scope_key": "active:2026-04",
                    "project_scope": "active",
                    "scope_month": "2026-04-01",
                    "row_key": "txn-2:0",
                    "transaction_id": "txn-2",
                    "group_id": "group-2",
                    "trade_time_text": "2026-04-11 09:00:00",
                    "trade_date": "2026-04-11",
                    "counterparty_name": "供应商B",
                    "payment_account_label": "招行",
                    "direction": "支出",
                    "remark": "服务",
                    "project_id": "P-B",
                    "project_name": "项目B",
                    "expense_type": "服务",
                    "expense_content": "咨询",
                    "amount": "5.50",
                    "oa_applicant": "李四",
                    "source_versions": {"scope": "active:2026-04"},
                    "generated_at": "2026-06-04T10:01:00+00:00",
                    "cache_status": "fresh",
                    "payload": {
                        "transaction_id": "txn-2",
                        "group_id": "group-2",
                        "trade_time": "2026-04-11 09:00:00",
                        "direction": "支出",
                        "project_name": "项目B",
                        "project_id": "P-B",
                        "expense_type": "服务",
                        "expense_content": "咨询",
                        "amount": "5.50",
                        "counterparty_name": "供应商B",
                        "payment_account_label": "招行",
                        "remark": "服务",
                        "oa_applicant": "李四",
                    },
                    "raw_payload": {},
                },
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_account_mappings": [{"bank_name": "工商银行", "last4": "0001"}],
                    "bank_transaction_tags": {"version": 7},
                }
            }
        return None


class CostStatisticsSaveRecorder:
    def __init__(self) -> None:
        self.saved: list[tuple[dict, set[str] | None]] = []
        self.workbench_source_versions: dict[str, object] = {}

    def active_workbench_source_versions(self, *, scope_key: str) -> dict[str, object]:
        del scope_key
        return dict(self.workbench_source_versions)

    def save_cost_statistics_read_models(self, snapshot: dict, *, changed_scope_keys: set[str] | None = None) -> None:
        self.saved.append((snapshot, changed_scope_keys))


class UnchangedCostStatisticsSaveRecorder(CostStatisticsSaveRecorder):
    def __init__(self, *, refresh_status: str = "fresh") -> None:
        super().__init__()
        self.refresh_status = refresh_status
        self.source_versions: dict[str, object] = {}
        self.views: list[str] = []
        self.workbench_source_versions = {"workbench_generation": "stable-v1", "source_version": 42}

    def get_cost_statistics_view(self, *, scope_key: str) -> dict[str, object]:
        self.views.append(scope_key)
        return {
            "scope_key": scope_key,
            "refresh_status": self.refresh_status,
            "entry_count": 1,
            "payload": {"time_rows": [{"transaction_id": "bank-1"}]},
            "source_versions": dict(self.source_versions),
        }

    def save_cost_statistics_read_models(self, snapshot: dict, *, changed_scope_keys: set[str] | None = None) -> None:
        raise AssertionError("unchanged cost statistics scope must not be rewritten")


class CostStatisticsReadModelRepositoryPortTests(unittest.TestCase):
    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        class Repository:
            def load_cost_statistics_read_models(self) -> dict[str, object]:
                return {"read_models": {}}

            def get_cost_statistics_view(self, *, scope_key: str) -> dict[str, object]:
                return {"scope_key": scope_key, "payload": {}}

            def active_workbench_source_versions(self, *, scope_key: str) -> dict[str, object]:
                return {"scope_key": scope_key, "source_version": 42}

            def save_cost_statistics_read_models(
                self,
                snapshot: dict[str, object],
                *,
                changed_scope_keys: set[str] | None = None,
            ) -> None:
                self.saved = (snapshot, changed_scope_keys)

            def get_tax_offset_view(self, *, scope_key: str) -> dict[str, object]:
                raise AssertionError("tax offset should not be exposed through cost statistics port")

            def list_turnover_ledger_view(self, **_kwargs) -> dict[str, object]:
                raise AssertionError("turnover should not be exposed through cost statistics port")

            def save_search_index_rows(self, **_kwargs) -> None:
                raise AssertionError("search should not be exposed through cost statistics port")

        port = CostStatisticsReadModelRepositoryPort(Repository())

        self.assertEqual(port.load_cost_statistics_read_models(), {"read_models": {}})
        self.assertEqual(port.get_cost_statistics_view(scope_key="active:2026-05")["scope_key"], "active:2026-05")
        self.assertEqual(
            port.active_workbench_source_versions(scope_key="2026-05"),
            {"scope_key": "2026-05", "source_version": 42},
        )
        port.save_cost_statistics_read_models({"read_models": {}}, changed_scope_keys={"active:2026-05"})
        self.assertFalse(hasattr(port, "get_tax_offset_view"))
        self.assertFalse(hasattr(port, "list_turnover_ledger_view"))
        self.assertFalse(hasattr(port, "save_search_index_rows"))


class CostStatisticsSqlRuntimeTests(unittest.TestCase):
    def test_shared_postgres_repository_exposes_active_workbench_versions_to_cost_port(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.fetch_one_calls: list[tuple[str, tuple]] = []

            def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
                self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
                return {"source_versions": {"builder": "workbench-v5", "source_version": 2512}}

        connection = Connection()
        repository = PostgresReadModelRepository(connection)
        port = CostStatisticsReadModelRepositoryPort(repository)

        self.assertEqual(
            port.active_workbench_source_versions(scope_key="2026-05"),
            {"builder": "workbench-v5", "source_version": 2512},
        )
        sql, params = connection.fetch_one_calls[0]
        self.assertIn("from read_model.workbench_generations", sql)
        self.assertIn("status = 'active'", sql)
        self.assertEqual(params, ("2026-05",))

    def test_repository_parses_grouped_display_amount_into_structured_cost_row(self) -> None:
        connection = CostStatisticsWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_cost_statistics_read_models(
            {
                "read_models": {
                    "all:2026-05": {
                        "scope_key": "all:2026-05",
                        "month": "2026-05",
                        "project_scope": "all",
                        "generated_at": "2026-07-10T10:00:00+00:00",
                        "entry_count": 1,
                        "source_versions": {"proof": "v1"},
                        "payload": {
                            "month": "2026-05",
                            "project_scope": "all",
                            "summary": {"transaction_count": 1, "total_amount": "1,872.93"},
                            "time_rows": [
                                {
                                    "transaction_id": "txn-1",
                                    "trade_time": "2026-05-02 10:00:00",
                                    "project_name": "项目A",
                                    "expense_type": "材料",
                                    "amount": "1,872.93",
                                }
                            ],
                        },
                    }
                }
            },
            changed_scope_keys={"all:2026-05"},
        )

        insert = next(
            params
            for sql, params in connection.executed
            if "insert into read_model.cost_statistics_rows" in sql
        )
        self.assertEqual(insert[16], "1872.93")

    def test_repository_saves_parent_scope_snapshot_without_writing_month_rows(self) -> None:
        connection = CostStatisticsWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_cost_statistics_read_models(
            {
                "read_models": {
                    "active:all": {
                        "scope_key": "active:all",
                        "month": "all",
                        "project_scope": "active",
                        "generated_at": "2026-06-06T10:00:00+00:00",
                        "entry_count": 1,
                        "source_versions": {"cost_statistics_parent_source": "materialized_shards"},
                        "payload": {
                            "month": "all",
                            "project_scope": "active",
                            "summary": {"row_count": 1, "total_amount": "10.00"},
                            "time_rows": [
                                {
                                    "transaction_id": "txn-parent-1",
                                    "trade_time": "2026-05-02 10:00:00",
                                    "trade_date": "2026-05-02",
                                    "project_name": "项目A",
                                    "expense_type": "材料",
                                    "amount": "10.00",
                                }
                            ],
                            "project_rows": [],
                            "expense_type_rows": [],
                        },
                    }
                }
            },
            changed_scope_keys={"active:all"},
        )

        self.assertTrue(any("insert into read_model.cost_statistics_read_models" in sql for sql, _params in connection.executed))
        self.assertTrue(any("delete from read_model.cost_statistics_rows where scope_key" in sql for sql, _params in connection.executed))
        self.assertFalse(any("insert into read_model.cost_statistics_rows" in sql for sql, _params in connection.executed))

    def test_repository_reads_cost_statistics_view_and_dirty_status_from_sql(self) -> None:
        connection = CostStatisticsReadConnection(
            read_model_row={
                "scope_key": "active:2026-05",
                "project_scope": "active",
                "scope_month": "2026-05-01",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "entry_count": 1,
                "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                "payload": {"month": "2026-05", "time_rows": [{"transaction_id": "txn-1"}]},
            },
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_cost_statistics_view(scope_key="active:2026-05")

        self.assertEqual(view["payload"]["time_rows"], [{"transaction_id": "txn-1"}])
        self.assertEqual(view["refresh_status"], "refreshing")
        self.assertEqual(view["schema_version"], COST_STATISTICS_READ_MODEL_SCHEMA_VERSION)
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_reads_cost_statistics_schema_version_from_payload_not_table_column(self) -> None:
        connection = CostStatisticsReadConnection(
            read_model_row={
                "scope_key": "active:2026-05",
                "project_scope": "active",
                "scope_month": "2026-05-01",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "entry_count": 1,
                "payload": {
                    "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                    "month": "2026-05",
                    "time_rows": [{"transaction_id": "txn-1"}],
                },
            },
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_cost_statistics_view(scope_key="active:2026-05")

        self.assertEqual(view["schema_version"], COST_STATISTICS_READ_MODEL_SCHEMA_VERSION)
        parent_sql = next(
            sql
            for sql, _params in connection.fetch_one_calls
            if "from read_model.cost_statistics_read_models" in sql
        )
        self.assertNotIn("schema_version", parent_sql)

    def test_repository_prefers_cost_statistics_row_table_over_snapshot_payload(self) -> None:
        connection = CostStatisticsReadConnection(
            read_model_row={
                "scope_key": "active:2026-05",
                "project_scope": "active",
                "scope_month": "2026-05-01",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "entry_count": 1,
                "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                "payload": {
                    "month": "2026-05",
                    "time_rows": [{"transaction_id": "stale-json"}],
                    "bank_accounts": [
                        {
                            "bank_name": "工商银行",
                            "account_last4": "0001",
                            "payment_account_label": "工商银行 账户 0001",
                            "source": "settings",
                        }
                    ],
                },
            },
            cost_rows=[
                {
                    "scope_key": "active:2026-05",
                    "project_scope": "active",
                    "scope_month": "2026-05-01",
                    "row_key": "txn-1:0",
                    "transaction_id": "txn-1",
                    "trade_time_text": "2026-05-02 10:00:00",
                    "project_name": "项目A",
                    "expense_type": "材料",
                    "expense_content": "钢材",
                    "amount": "10.00",
                    "payload": {"transaction_id": "txn-1", "project_name": "项目A"},
                }
            ],
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_cost_statistics_view(scope_key="active:2026-05")

        self.assertEqual(view["payload"]["time_rows"][0]["transaction_id"], "txn-1")
        self.assertEqual(view["payload"]["bank_accounts"][0]["payment_account_label"], "工商银行 账户 0001")
        self.assertEqual(view["payload"]["summary"]["total_amount"], "10.00")
        self.assertEqual(view["payload"]["project_rows"][0]["expense_type_count"], 1)

    def test_cost_statistics_api_reads_redis_hot_cache_without_sql_or_sync_build(self) -> None:
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        source_versions = app._cost_statistics_expected_source_versions("active:2026-05")
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {
                "queue_repository": QueueRecorder(),
                "redis_helper": RedisRecorder(
                    redis_fresh_payload(
                        {
                            "month": "2026-05",
                            "summary": {"total_amount": "0.00", "transaction_count": 0},
                            "time_rows": [],
                            "bank_accounts": [],
                            "project_rows": [],
                            "expense_type_rows": [],
                        },
                        scope_key="active:2026-05",
                        source_versions=source_versions,
                    )
                ),
            },
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {"get_cost_statistics_view": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("SQL should not be hit on Redis cache"))},
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API miss must not sync rebuild"))},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"month": ["2026-05"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["month"], "2026-05")
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_cost_statistics_api_miss_enqueues_refresh_and_returns_refreshing(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {"get_cost_statistics_view": lambda *_args, **_kwargs: None},
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API miss must not sync rebuild"))},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"month": ["2026-05"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_miss")])

    def test_production_postgres_cost_statistics_requires_sql_read_model_without_sync_build(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()
        app._cost_statistics_sql_read_repository = None
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("production API must not sync rebuild"))},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"month": ["2026-05"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["error"], "read_model_unavailable")
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_sql_repository_unavailable")])

    def test_cost_statistics_month_summary_miss_enqueues_refresh_without_sync_build(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {"get_cost_statistics_view": lambda *_args, **_kwargs: None},
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_month_statistics": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API miss must not sync rebuild"))},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics",
            {"month": ["2026-05"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_month_miss")])

    def test_cost_statistics_month_summary_reads_sql_aggregate_and_populates_redis(self) -> None:
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_view": lambda *_args, **_kwargs: {
                    "payload": {
                        "month": "2026-05",
                        "time_rows": [
                            {
                                "transaction_id": "txn-1",
                                "project_name": "项目A",
                                "expense_type": "材料",
                                "expense_content": "钢材",
                                "amount": "10.00",
                            },
                            {
                                "transaction_id": "txn-2",
                                "project_name": "项目A",
                                "expense_type": "材料",
                                "expense_content": "钢材",
                                "amount": "5.50",
                            },
                        ],
                    },
                    "refresh_status": "fresh",
                    "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "source_versions": app._cost_statistics_expected_source_versions("active:2026-05"),
                }
            },
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_month_statistics": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API SQL hit must not sync rebuild"))},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics",
            {"month": ["2026-05"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["summary"]["total_amount"], "15.50")
        self.assertEqual(payload["summary"]["transaction_count"], 2)
        self.assertEqual(payload["rows"][0]["amount"], "15.50")
        self.assertTrue(
            redis.sets[0][0].startswith(
                f"cost_statistics:month:active:2026-05:schema:{COST_STATISTICS_READ_MODEL_SCHEMA_VERSION}:sources:"
            )
        )
        self.assertLessEqual(redis.sets[0][2], 120)

    def test_cost_statistics_api_reads_sql_and_populates_short_redis_cache(self) -> None:
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_view": lambda *_args, **_kwargs: {
                    "payload": {
                        "month": "2026-05",
                        "summary": {"row_count": 1, "transaction_count": 1, "total_amount": "100.00"},
                        "time_rows": [
                            {
                                "transaction_id": "txn-1",
                                "trade_time": "2026-05-21 09:00:00",
                                "direction": "支出",
                                "project_name": "云南溯源科技",
                                "expense_type": "设备货款及材料费",
                                "expense_content": "PLC 模块采购",
                                "amount": "100.00",
                                "counterparty_name": "供应商",
                                "payment_account_label": "工行",
                                "remark": "",
                            }
                        ],
                        "bank_accounts": [],
                        "project_rows": [
                            {
                                "project_name": "云南溯源科技",
                                "total_amount": "100.00",
                                "transaction_count": 1,
                                "expense_type_count": 1,
                            }
                        ],
                        "expense_type_rows": [
                            {
                                "expense_type": "设备货款及材料费",
                                "total_amount": "100.00",
                                "transaction_count": 1,
                                "project_count": 1,
                            }
                        ],
                    },
                    "refresh_status": "fresh",
                    "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "source_versions": app._cost_statistics_expected_source_versions("active:2026-05"),
                }
            },
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API SQL hit must not sync rebuild"))},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"month": ["2026-05"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["time_rows"][0]["transaction_id"], "txn-1")
        self.assertTrue(
            redis.sets[0][0].startswith(
                f"cost_statistics:explorer:active:2026-05:schema:{COST_STATISTICS_READ_MODEL_SCHEMA_VERSION}:sources:"
            )
        )
        self.assertLessEqual(redis.sets[0][2], 120)

    def test_cost_statistics_api_rejects_old_bank_tag_schema_parent_payload_without_old_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_view": lambda *_args, **_kwargs: {
                    "payload": {
                        "month": "all",
                        "summary": {"row_count": 145, "transaction_count": 145, "total_amount": "19016.25"},
                        "time_rows": [
                            {
                                "transaction_id": "old-parent-row",
                                "trade_time": "2026-06-23 09:45:03",
                                "direction": "支出",
                                "project_name": "项目A",
                                "expense_type": "火车费",
                                "expense_content": "火车费",
                                "amount": "145.00",
                                "counterparty_name": "陈佳玉",
                                "payment_account_label": "建设银行 8106",
                                "remark": "",
                                "bank_tag_primary_label": "未标记",
                                "bank_tag_sub_label": "未标记",
                                "bank_tag_label_path": ["未标记"],
                            }
                        ],
                        "bank_accounts": [],
                        "project_rows": [],
                        "expense_type_rows": [],
                    },
                    "refresh_status": "fresh",
                    "schema_version": "2026-07-cost-statistics-bank-accounts-v3",
                    "generated_at": "2026-07-06T10:00:00+08:00",
                    "source_versions": app._cost_statistics_expected_source_versions("active:all"),
                }
            },
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("stale SQL payload must not sync rebuild"))},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"month": ["all"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "active:all")
        self.assertEqual(payload["read_model_stale_reasons"], ["schema_version_mismatch"])
        self.assertEqual(payload["time_rows"], [])
        self.assertEqual(payload["project_rows"], [])
        self.assertEqual(payload["expense_type_rows"], [])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:all", "api_source_versions_stale")])

    def test_cost_statistics_api_rejects_malformed_fresh_sql_payload_and_requeues(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_view": lambda *_args, **_kwargs: {
                    "payload": {
                        "month": "2026-05",
                        "summary": {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"},
                        "rows": [],
                    },
                    "refresh_status": "fresh",
                    "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "source_versions": app._cost_statistics_expected_source_versions("active:2026-05"),
                }
            },
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("malformed SQL payload must not sync rebuild"))},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"month": ["2026-05"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "active:2026-05")
        self.assertEqual(payload["read_model_stale_reasons"], ["api_payload_shape_invalid"])
        self.assertEqual(payload["time_rows"], [])
        self.assertEqual(payload["project_rows"], [])
        self.assertEqual(payload["expense_type_rows"], [])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_payload_shape_invalid")])
        self.assertEqual(redis.sets, [])

    def test_cost_statistics_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def rebuild_cost_statistics_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.rebuilt.append(scope_key)
                return {"scope_key": scope_key, "entry_count": 1}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = CostStatisticsReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:2026-05",
            scope_type="cost_statistics",
            scope_key="active:2026-05",
            dedupe_key=None,
            payload={"scope_key": "active:2026-05"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt, ["active:2026-05"])
        self.assertEqual(queue.completed, [("tenant-a", "cost_statistics", "active:2026-05")])
        self.assertEqual(result["entry_count"], 1)

    def test_cost_statistics_refresh_handler_requires_projection_builder_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "projection_builder is required"):
            CostStatisticsReadModelRefreshService(queue_repository=object())

    def test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts(self) -> None:
        repository = CostStatisticsSaveRecorder()
        connection = CostStatisticsProjectionConnection(include_open_candidate=True)
        tag_facade = CostStatisticsBankTagFacade()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
            bank_transaction_tag_read_facade=tag_facade,
        )

        result = builder.rebuild_cost_statistics_read_model_scope("active:2026-05")

        self.assertEqual(result["entry_count"], 1)
        snapshot, changed_scope_keys = repository.saved[0]
        self.assertEqual(changed_scope_keys, {"active:2026-05"})
        payload = snapshot["read_models"]["active:2026-05"]["payload"]
        self.assertEqual(payload["summary"]["transaction_count"], 1)
        self.assertEqual(payload["summary"]["total_amount"], "10.00")
        self.assertEqual(
            [(row["transaction_id"], row["direction"]) for row in payload["bank_flow_time_rows"]],
            [("bank-income", "收入"), ("bank-expense", "支出")],
        )
        self.assertEqual(payload["bank_flow_summary"]["expense_amount"], "20.00")
        self.assertEqual(payload["bank_flow_summary"]["income_amount"], "30.00")
        self.assertNotIn("direction", tag_facade.month_calls[0][1])
        self.assertEqual([row["transaction_id"] for row in payload["time_rows"]], ["bank-1"])
        self.assertEqual(payload["time_rows"][0]["group_id"], "group-1")
        self.assertEqual(payload["time_rows"][0]["project_id"], "P-A")
        self.assertEqual(payload["time_rows"][0]["bank_tag_primary_label"], "项目开销")
        self.assertEqual(payload["time_rows"][0]["bank_tag_sub_label"], "设备材料")
        self.assertEqual(payload["time_rows"][0]["bank_tag_label_path"], ["项目开销", "设备材料"])
        self.assertEqual(tag_facade.source_version_calls[0][0], ["2026-05"])
        self.assertEqual(tag_facade.category_calls[0][0], ["bank-1"])
        self.assertEqual(
            snapshot["read_models"]["active:2026-05"]["source_versions"]["bank_detail_source_versions"],
            {"bank_detail_scope_version": "bank-detail-v2"},
        )
        self.assertEqual(
            payload["bank_accounts"],
            [
                {
                    "bank_name": "工商银行",
                    "account_last4": "0001",
                    "payment_account_label": "工商银行 账户 0001",
                    "source": "settings",
                },
                {
                    "bank_name": "民生银行",
                    "account_last4": "9486",
                    "payment_account_label": "民生银行 账户 9486",
                    "source": "settings",
                },
            ],
        )
        self.assertIn(
            "bank_account_mappings_fingerprint",
            snapshot["read_models"]["active:2026-05"]["source_versions"],
        )
        workbench_sql, workbench_params = next(
            (sql, params) for sql, params in connection.fetch_all_calls if "read_model.workbench_groups" in sql
        )
        self.assertEqual(workbench_params, ("2026-05", "2026-05"))
        self.assertIn("with active_generation as", workbench_sql)
        self.assertIn("join read_model.workbench_groups", workbench_sql)
        self.assertIn("join read_model.workbench_group_rows", workbench_sql)
        self.assertIn("left join read_model.workbench_rows", workbench_sql)
        self.assertIn("g.generation_id = active.generation_id", workbench_sql)
        self.assertNotIn("jsonb_path_exists", workbench_sql)
        settings_reads = [
            sql
            for sql, _params in connection.fetch_one_calls
            if "from app.app_settings" in sql
        ]
        self.assertEqual(len(settings_reads), 1)

    def test_cost_statistics_sql_projection_defers_when_bank_detail_tags_are_not_fresh(self) -> None:
        repository = CostStatisticsSaveRecorder()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=CostStatisticsProjectionConnection(),
            read_model_repository=repository,
            bank_transaction_tag_read_facade=CostStatisticsBankTagFacade(status="refreshing"),
        )

        with self.assertRaisesRegex(RuntimeError, "bank_detail_read_model_not_fresh"):
            builder.rebuild_cost_statistics_read_model_scope("active:2026-05")

        self.assertEqual(repository.saved, [])

    def test_cost_statistics_expected_source_versions_include_bank_detail_scope_versions(self) -> None:
        app = object.__new__(Application)
        tag_facade = CostStatisticsBankTagFacade()
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._bank_transaction_tag_read_facade = tag_facade
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "active_workbench_source_versions": lambda *_args, **_kwargs: {
                    "builder": "workbench-v5",
                    "source_version": 2511,
                }
            },
        )()
        app._current_oa_attachment_invoice_parser_version = lambda: "parser-v1"
        app._current_oa_projection_sync_version = lambda: "oa-sync-v1"

        source_versions = app._cost_statistics_source_versions("active:2026-05")

        self.assertEqual(
            source_versions["bank_detail_source_versions"],
            {"bank_detail_scope_version": "bank-detail-v2"},
        )
        self.assertEqual(tag_facade.source_version_calls[0][0], ["2026-05"])
        self.assertEqual(tag_facade.source_version_calls[0][1]["require_fresh"], False)
        self.assertEqual(
            source_versions["workbench_source_versions"],
            {"builder": "workbench-v5", "source_version": 2511},
        )

    def test_cost_statistics_api_rejects_snapshot_built_from_old_workbench_generation(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._bank_transaction_tag_read_facade = CostStatisticsBankTagFacade()
        app._current_oa_attachment_invoice_parser_version = lambda: "parser-v1"
        app._current_oa_projection_sync_version = lambda: "oa-sync-v1"
        current_workbench_versions = {"builder": "workbench-v5", "source_version": 2511}
        old_workbench_versions = {"builder": "workbench-v5", "source_version": 2504}

        class SqlCostStats:
            def active_workbench_source_versions(self, *, scope_key: str) -> dict[str, object]:
                self.scope_key = scope_key
                return dict(current_workbench_versions)

            def get_cost_statistics_view(self, *, scope_key: str) -> dict[str, object]:
                source_versions = app._cost_statistics_expected_source_versions(scope_key)
                source_versions["workbench_source_versions"] = old_workbench_versions
                return {
                    "payload": {
                        "month": "2026-05",
                        "summary": {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"},
                        "time_rows": [],
                        "bank_accounts": [],
                        "project_rows": [],
                        "expense_type_rows": [],
                    },
                    "refresh_status": "fresh",
                    "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                    "generated_at": "2026-07-12T19:20:29+08:00",
                    "source_versions": source_versions,
                }

        repository = SqlCostStats()
        app._cost_statistics_sql_read_repository = repository
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"month": ["2026-05"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "active:2026-05")
        self.assertEqual(payload["read_model_stale_reasons"], ["workbench_source_versions_mismatch"])
        self.assertEqual(payload["time_rows"], [])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_source_versions_stale")])

    def test_cost_statistics_scope_shards_are_listed_from_active_workbench_generations(self) -> None:
        class Connection(CostStatisticsProjectionConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_rows" in normalized:
                    raise AssertionError("cost statistics shard discovery must not scan historical workbench rows")
                if "from read_model.workbench_generations" in normalized:
                    return [
                        {"scope_key": "2026-06"},
                        {"scope_key": "all"},
                        {"scope_key": "legacy"},
                        {"scope_key": "2026-05"},
                    ]
                return []

        connection = Connection()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=CostStatisticsSaveRecorder(),
        )

        self.assertEqual(
            builder.list_cost_statistics_scope_shards("active:all"),
            ["active:2026-06", "active:2026-05"],
        )
        workbench_sql = next(sql for sql, _params in connection.fetch_all_calls if "from read_model.workbench_generations" in sql)
        self.assertIn("status = 'active'", workbench_sql)

    def test_cost_statistics_sql_projection_skips_unchanged_month_scope_without_workbench_scan(self) -> None:
        class Connection(CostStatisticsProjectionConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_generations" in normalized:
                    return {"source_versions": {"workbench_generation": "stable-v1", "source_version": 42}}
                return super().fetch_one(sql, params)

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.workbench_groups" in normalized:
                    raise AssertionError("unchanged cost statistics scope must not scan workbench groups")
                return super().fetch_all(sql, params)

        repository = UnchangedCostStatisticsSaveRecorder()
        connection = Connection()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )
        repository.source_versions = builder._source_versions("2026-05")

        result = builder.rebuild_cost_statistics_read_model_scope("active:2026-05")

        self.assertEqual(repository.views, ["active:2026-05"])
        self.assertEqual(result["scope_key"], "active:2026-05")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["skip_reason"], "source_versions_unchanged")
        self.assertTrue(result["skipped"])
        self.assertEqual(result["source_versions"]["workbench_source_versions"]["workbench_generation"], "stable-v1")

    def test_cost_statistics_sql_projection_skips_unchanged_scope_while_dirty_scope_is_processing(self) -> None:
        class Connection(CostStatisticsProjectionConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_generations" in normalized:
                    return {"source_versions": {"workbench_generation": "stable-v1", "source_version": 42}}
                return super().fetch_one(sql, params)

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.workbench_groups" in normalized:
                    raise AssertionError("current dirty scope must not defeat unchanged source-version skip")
                return super().fetch_all(sql, params)

        repository = UnchangedCostStatisticsSaveRecorder(refresh_status="refreshing")
        connection = Connection()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )
        repository.source_versions = builder._source_versions("2026-05")

        result = builder.rebuild_cost_statistics_read_model_scope("active:2026-05")

        self.assertEqual(result["skip_reason"], "source_versions_unchanged")
        self.assertTrue(result["skipped"])

    def test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows(self) -> None:
        repository = CostStatisticsSaveRecorder()
        connection = CostStatisticsParentAggregationConnection()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        result = builder.rebuild_cost_statistics_read_model_scope("active:all")

        self.assertEqual(result["scope_key"], "active:all")
        self.assertEqual(result["month"], "all")
        self.assertEqual(result["project_scope"], "active")
        self.assertEqual(result["entry_count"], 2)
        self.assertTrue(all("workbench_groups" not in sql for sql, _params in connection.fetch_all_calls))
        snapshot, changed_scope_keys = repository.saved[0]
        self.assertEqual(changed_scope_keys, {"active:all"})
        self.assertIn("active:all", snapshot["read_models"])
        payload = snapshot["read_models"]["active:all"]["payload"]
        self.assertEqual(payload["month"], "all")
        self.assertEqual(payload["summary"]["total_amount"], "15.50")
        self.assertEqual(payload["project_rows"][0]["project_name"], "项目A")
        self.assertEqual(payload["expense_type_rows"][0]["expense_type"], "材料")
        self.assertEqual(payload["time_rows"][0]["bank_tag_primary_label"], "项目开销")
        self.assertEqual(payload["time_rows"][0]["bank_tag_sub_label"], "设备材料")
        self.assertEqual(payload["bank_accounts"][0]["payment_account_label"], "工商银行 账户 0001")
        self.assertEqual(snapshot["read_models"]["active:all"]["source_versions"]["source_shard_count"], 2)

    def test_cost_statistics_sql_projection_rebuilds_all_all_as_first_class_read_model(self) -> None:
        repository = CostStatisticsSaveRecorder()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=CostStatisticsParentAggregationConnection(),
            read_model_repository=repository,
        )

        result = builder.rebuild_cost_statistics_read_model_scope("all:all")

        self.assertEqual(result["scope_key"], "all:all")
        self.assertEqual(result["month"], "all")
        self.assertEqual(result["project_scope"], "all")
        self.assertEqual(repository.saved[0][1], {"all:all"})

    def test_cost_statistics_parent_rebuild_removes_obsolete_month_scopes(self) -> None:
        class Connection(CostStatisticsParentAggregationConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.workbench_generations" in normalized:
                    return [{"scope_key": "2026-05"}, {"scope_key": "2026-04"}]
                if "from read_model.cost_statistics_read_models" in normalized:
                    return [
                        {"scope_key": "active:2026-05"},
                        {"scope_key": "active:2026-04"},
                        {"scope_key": "active:2023-05"},
                    ]
                return super().fetch_all(sql, params)

        repository = CostStatisticsSaveRecorder()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=Connection(),
            read_model_repository=repository,
        )

        builder.rebuild_cost_statistics_read_model_scope("active:all")

        self.assertEqual(repository.saved[0], ({"read_models": {}}, {"active:2023-05"}))
        self.assertEqual(repository.saved[1][1], {"active:all"})

    def test_cost_statistics_refresh_handler_enqueues_missing_shards_before_parent_rebuild(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def missing_or_stale_cost_statistics_shards(self, scope_key: str) -> list[str]:
                return ["active:2026-05", "active:2026-04"]

            def rebuild_cost_statistics_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.rebuilt.append(scope_key)
                raise AssertionError("parent rebuild must wait for shard convergence")

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = CostStatisticsReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:all",
            scope_type="cost_statistics",
            scope_key="active:all",
            dedupe_key=None,
            payload={"scope_key": "active:all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt, [])
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "cost_statistics_all_shard"),
                ("cost_statistics", "active:2026-04", "cost_statistics_all_shard"),
            ],
        )
        self.assertEqual(queue.completed, [])
        self.assertEqual(result["scope_key"], "active:all")
        self.assertEqual(result["readiness_status"], "refreshing")
        self.assertEqual(result["enqueued_scope_keys"], ["active:2026-05", "active:2026-04"])

    def test_cost_statistics_refresh_handler_publishes_parent_after_shards_converge(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt_parent: list[str] = []

            def missing_or_stale_cost_statistics_shards(self, scope_key: str) -> list[str]:
                return []

            def rebuild_cost_statistics_parent_scope(self, scope_key: str) -> dict[str, object]:
                self.rebuilt_parent.append(scope_key)
                return {"scope_key": scope_key, "entry_count": 2, "source_shard_count": 2}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = CostStatisticsReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:all",
            scope_type="cost_statistics",
            scope_key="active:all",
            dedupe_key=None,
            payload={"scope_key": "active:all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt_parent, ["active:all"])
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(queue.completed, [("tenant-a", "cost_statistics", "active:all")])
        self.assertEqual(result["scope_key"], "active:all")
        self.assertEqual(result["readiness_status"], "fresh")
        self.assertEqual(result["refresh_kind"], "parent")

    def test_cost_statistics_invalidation_marks_dirty_even_when_no_cached_model_exists(self) -> None:
        class EmptyCostReadModelService:
            def invalidate_months(self, *_args, **_kwargs) -> list[str]:
                return []

            def snapshot(self) -> dict[str, object]:
                return {"read_models": {}}

            def scope_key(self, month: str, project_scope: str) -> str:
                return f"{project_scope}:{month}"

        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._cost_statistics_read_model_service = EmptyCostReadModelService()
        app._persist_cost_statistics_read_models_best_effort = lambda **_kwargs: None
        app._schedule_cost_statistics_cache_warmup = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("SQL runtime invalidation should enqueue durable refresh when queue exists")
        )

        deleted = app._invalidate_cost_statistics_read_model_scopes(["2026-05"], reason="unit_test")

        self.assertEqual(deleted, [])
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "unit_test"),
                ("cost_statistics", "all:2026-05", "unit_test"),
            ],
        )
        self.assertIn("cost_statistics:explorer:active:2026-05", redis.deletes)
        self.assertIn("cost_statistics:month:active:2026-05", redis.deletes)
        self.assertIn("cost_statistics:explorer:all:2026-05", redis.deletes)
        self.assertIn("cost_statistics:month:all:2026-05", redis.deletes)
        self.assertTrue(any(f":schema:{COST_STATISTICS_READ_MODEL_SCHEMA_VERSION}:sources:" in key for key in redis.deletes))

    def test_generic_cost_statistics_enqueue_expands_month_scopes(self) -> None:
        class EmptyCostReadModelService:
            def scope_key(self, month: str, project_scope: str) -> str:
                return f"{project_scope}:{month}"

        queue = QueueRecorder()
        app = object.__new__(Application)
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._cost_statistics_read_model_service = EmptyCostReadModelService()

        enqueued = app._enqueue_generic_read_model_refreshes(
            "cost_statistics",
            ["2026-05", "all"],
            reason="unit_test",
        )

        self.assertTrue(enqueued)
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "unit_test"),
                ("cost_statistics", "all:2026-05", "unit_test"),
                ("cost_statistics", "active:all", "unit_test"),
                ("cost_statistics", "all:all", "unit_test"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
